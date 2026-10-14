"""TC-E2E-231 — Safety Officer review queue, detail and decision."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def test_safety_officer_approves_an_enriched_confirmed_event(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    support = make_user("technical_support")
    officer = make_user("safety_officer")
    venue_staff = make_user("venue_staff")
    suffix = uuid.uuid4().hex[:6]
    event_name = f"Safety Review {suffix}"

    venue = admin.schema("venues").table("venues").insert(
        {
            "name": f"Safety Hall {suffix}",
            "location": "Building A",
            "capacity": 200,
            "facilities": ["sound_system"],
            "accessibility": ["wheelchair_access"],
            "room_layouts": ["theatre"],
            "operating_hours": [
                {"day": "wed", "open": "08:00:00", "close": "18:00:00"}
            ],
            "description": "No open flame; keep north exit clear",
            "created_by": venue_staff["id"],
        }
    ).execute().data[0]
    equipment = admin.schema("equipment").table("equipment").insert(
        {
            "type": f"Wireless microphone {suffix}",
            "description": "Keep cables behind barriers",
            "total_quantity": 10,
            "created_by": support["id"],
        }
    ).execute().data[0]
    event = admin.schema("events").table("events").insert(
        {
            "organiser_id": organiser["id"],
            "assigned_coordinator_id": coordinator["id"],
            "status": "confirmed",
            "name": event_name,
            "purpose": "Exercise the S-86 browser workflow",
            "start_date": "2026-11-18",
            "start_time": "09:00",
            "end_date": "2026-11-18",
            "end_time": "12:00",
            "expected_attendance": 120,
            "special_requirements": "Keep emergency access clear and control crowd movement",
            "room_layout": "theatre",
            "required_facilities": ["sound_system"],
            "required_accessibility": ["wheelchair_access"],
            "decision": "approved",
            "decided_at": "2026-10-01T00:00:00Z",
            "submitted_at": "2026-09-30T00:00:00Z",
            "technical_support_required": True,
            "technical_support_details": "Place speakers away from exit routes",
            "assigned_technical_support_id": support["id"],
            "technical_support_assigned_at": "2026-10-01T01:00:00Z",
        }
    ).execute().data[0]
    admin.schema("equipment").table("requirements").insert(
        {
            "event_id": event["id"],
            "equipment_item_id": equipment["id"],
            "required_quantity": 4,
            "recorded_by_coordinator_id": coordinator["id"],
        }
    ).execute()
    admin.schema("bookings").table("bookings").insert(
        {
            "event_id": event["id"],
            "venue_id": venue["id"],
            "coordinator_id": coordinator["id"],
            "coordinator_name": "E2E Tester",
            "coordinator_email": coordinator["email"],
            "status": "confirmed",
            "booking_date": "2026-11-18",
            "start_time": "09:00",
            "end_time": "12:00",
            "event_name": event_name,
            "event_purpose": "Exercise the S-86 browser workflow",
            "expected_attendance": 120,
            "special_requirements": "Keep emergency access clear",
            "required_accessibility": ["wheelchair_access"],
            "required_facilities": ["sound_system"],
            "room_layout": "theatre",
            "notes": "Use north entrance",
            "venue_name": venue["name"],
            "decided_by": venue_staff["id"],
            "decided_at": "2026-10-02T00:00:00Z",
        }
    ).execute()

    sign_in(officer)
    page.wait_for_url(re.compile(r"/dashboard/safety-officer$"), timeout=20000)
    expect(page.get_by_role("heading", name="Operational safety checks")).to_be_visible(
        timeout=20000
    )
    page.get_by_role("link", name=re.compile(event_name)).click()
    page.wait_for_url(re.compile(r"/safety-checks/[^/]+$"), timeout=20000)
    expect(page.get_by_text("120", exact=True)).to_be_visible()
    expect(page.get_by_text("Capacity: 200", exact=True)).to_be_visible()
    expect(page.get_by_text("No open flame; keep north exit clear", exact=False)).to_be_visible()
    expect(page.get_by_text("Place speakers away from exit routes", exact=False)).to_be_visible()
    expect(page.get_by_text("Wireless microphone", exact=False)).to_be_visible()

    page.get_by_role("radio", name="Approve", exact=True).check()
    page.get_by_role("button", name="Record safety decision").click()
    expect(page.get_by_role("status")).to_contain_text(
        "Operational safety decision recorded", timeout=20000
    )

    stored = admin.schema("events").table("events").select(
        "status,safety_decision,safety_officer_id"
    ).eq("id", event["id"]).single().execute().data
    assert stored == {
        "status": "preparation",
        "safety_decision": "approved",
        "safety_officer_id": officer["id"],
    }
