"""TC-E2E-241: Coordinator sees readiness derived from current service data."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def test_coordinator_readiness_tracks_current_underlying_data(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    support = make_user("technical_support")
    venue_staff = make_user("venue_staff")
    suffix = uuid.uuid4().hex[:6]
    event_name = f"Readiness Review {suffix}"

    venue = admin.schema("venues").table("venues").insert({
        "name": f"Readiness Hall {suffix}",
        "location": "Building R",
        "capacity": 100,
        "facilities": [],
        "accessibility": [],
        "room_layouts": ["theatre"],
        "operating_hours": [{"day": "fri", "open": "08:00:00", "close": "18:00:00"}],
        "created_by": venue_staff["id"],
    }).execute().data[0]
    item = admin.schema("equipment").table("equipment").insert({
        "type": f"Readiness projector {suffix}",
        "total_quantity": 2,
        "created_by": support["id"],
    }).execute().data[0]
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "assigned_coordinator_id": coordinator["id"],
        "status": "planning",
        "name": event_name,
        "purpose": "Prove the S-24 readiness view",
        "start_date": "2026-11-20",
        "start_time": "09:00",
        "end_date": "2026-11-20",
        "end_time": "12:00",
        "expected_attendance": 60,
        "decision": "approved",
        "decided_at": "2026-10-01T00:00:00Z",
        "submitted_at": "2026-09-30T00:00:00Z",
        "assigned_technical_support_id": support["id"],
        "technical_support_required": True,
        "technical_support_assigned_at": "2026-10-01T01:00:00Z",
        "equipment_preparation_status": "ready",
        "equipment_preparation_updated_by": support["id"],
        "equipment_preparation_updated_at": "2026-10-02T00:00:00Z",
    }).execute().data[0]
    admin.schema("equipment").table("requirements").insert({
        "event_id": event["id"],
        "equipment_item_id": item["id"],
        "required_quantity": 1,
        "recorded_by_coordinator_id": coordinator["id"],
    }).execute()
    admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"],
        "venue_id": venue["id"],
        "coordinator_id": coordinator["id"],
        "coordinator_name": "E2E Tester",
        "coordinator_email": coordinator["email"],
        "status": "confirmed",
        "booking_date": "2026-11-20",
        "start_time": "09:00",
        "end_time": "12:00",
        "event_name": event_name,
        "event_purpose": "Prove the S-24 readiness view",
        "expected_attendance": 60,
        "required_accessibility": [],
        "required_facilities": [],
        "room_layout": "theatre",
        "venue_name": venue["name"],
        "decided_by": venue_staff["id"],
        "decided_at": "2026-10-02T00:00:00Z",
        "venue_preparation_status": "ready",
        "venue_preparation_updated_by": venue_staff["id"],
        "venue_preparation_updated_at": "2026-10-02T01:00:00Z",
        "venue_preparation_version": 1,
    }).execute()

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    panel = page.get_by_role("region", name="Event readiness")
    expect(panel).to_contain_text("3 of 3 implemented areas complete", timeout=20000)
    for label in ("Venue", "Equipment", "Technical support", "Programme", "Registration"):
        expect(panel.get_by_text(label, exact=True)).to_be_visible()
    expect(panel.get_by_text("Complete", exact=True)).to_have_count(3)
    expect(panel.get_by_text("Not available yet", exact=True)).to_have_count(2)

    admin.schema("events").table("events").update({
        "equipment_preparation_status": "in_progress",
    }).eq("id", event["id"]).execute()
    page.reload()
    expect(panel).to_contain_text("2 of 3 implemented areas complete", timeout=20000)
    expect(panel.get_by_text("Equipment preparation is In Progress", exact=True)).to_be_visible()
