"""TC-E2E-251: Venue Staff preparation reaches Coordinator readiness."""
import re
import uuid

import pytest
from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def test_staff_prepare_each_venue_and_coordinator_sees_readiness(admin, page, make_user, sign_in):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    suffix = uuid.uuid4().hex[:6]
    venues = admin.schema("venues").table("venues").insert([
        {
            "name": f"S-25 Hall {suffix}", "location": "10 Anson Road", "capacity": 100,
            "facilities": [], "accessibility": [], "room_layouts": ["theatre"],
            "operating_hours": [{"day": "fri", "open": "08:00", "close": "20:00"}],
            "created_by": staff["id"],
        },
        {
            "name": f"S-25 Studio {suffix}", "location": "12 Anson Road", "capacity": 60,
            "facilities": [], "accessibility": [], "room_layouts": ["classroom"],
            "operating_hours": [{"day": "fri", "open": "08:00", "close": "20:00"}],
            "created_by": staff["id"],
        },
    ]).execute().data
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"], "assigned_coordinator_id": coordinator["id"],
        "status": "preparation", "name": f"S-25 Event {suffix}",
        "purpose": "Prove venue preparation in the browser",
        "start_date": "2026-11-20", "start_time": "09:00",
        "end_date": "2026-11-20", "end_time": "12:00", "expected_attendance": 50,
        "decision": "approved", "decided_at": "2026-10-01T00:00:00Z",
        "submitted_at": "2026-09-30T00:00:00Z",
        "safety_decision": "approved", "safety_officer_id": coordinator["id"],
        "safety_decided_at": "2026-10-20T09:00:00Z",
    }).execute().data[0]
    admin.schema("bookings").table("bookings").insert([
        {
            "event_id": event["id"], "venue_id": venue["id"],
            "coordinator_id": coordinator["id"], "coordinator_name": "E2E Tester",
            "coordinator_email": coordinator["email"], "status": "confirmed",
            "decided_by": staff["id"], "decided_at": "2026-10-20T08:00:00Z",
            "booking_date": "2026-11-20", "start_time": "09:00", "end_time": "12:00",
            "event_name": event["name"], "event_purpose": event["purpose"],
            "expected_attendance": 50, "venue_name": venue["name"],
        }
        for venue in venues
    ]).execute()

    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    first_status = page.get_by_label(
        f"Preparation status for {venues[0]['name']}, {event['name']}"
    )
    second_status = page.get_by_label(
        f"Preparation status for {venues[1]['name']}, {event['name']}"
    )
    expect(first_status).to_have_value("not_started", timeout=30000)
    expect(second_status).to_have_value("not_started")
    first_status.select_option("in_progress")
    expect(first_status).to_have_value("in_progress")
    first_status.select_option("ready")
    expect(first_status).to_have_value("ready")
    second_status.select_option("ready")
    expect(second_status).to_have_value("ready")

    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=30000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    panel = page.get_by_role("region", name="Event readiness")
    expect(panel).to_contain_text(venues[0]["name"], timeout=20000)
    expect(panel).to_contain_text(venues[1]["name"])
    expect(panel).to_contain_text("2 of 2 confirmed venues Ready")
