"""TC-E2E-216: staff decisions and Coordinator visibility; .env.test only."""
import re
import uuid
from playwright.sync_api import expect
from .conftest import requires_env

pytestmark = requires_env


def test_staff_decisions_appear_to_requesting_coordinator(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    venue_name = f"spm-e2e Venue {suffix}"
    event_name = f"spm-e2e Event {suffix}"

    # Attributed to the staff member and the organiser, so make_user's
    # teardown deletes both; the booking goes with the coordinator.
    venue = admin.schema("venues").table("venues").insert(
        {
            "name": venue_name,
            "location": "10 Anson Road",
            "capacity": 150,
            "room_layouts": ["theatre"],
            "facilities": ["projector"],
            "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
            "created_by": staff["id"],
        }
    ).execute().data[0]
    event = (
        admin.schema("events")
        .table("events")
        .insert(
            {
                "organiser_id": organiser["id"],
                "status": "planning",
                "assigned_coordinator_id": coordinator["id"],
                "name": event_name,
                "purpose": "Reconnect graduates with faculty",
                "start_date": "2026-11-12",
                "start_time": "09:00",
                "end_date": "2026-11-12",
                "end_time": "18:00",
                "expected_attendance": 120,
                "room_layout": "theatre",
                "required_facilities": ["projector"],
                "decision": "approved",
                "decided_at": "2026-10-01T00:00:00+00:00",
                "submitted_at": "2026-09-30T00:00:00+00:00",
            }
        )
        .execute()
        .data[0]
    )

    bookings = []
    for index in range(3):
        bookings.append(admin.schema("bookings").table("bookings").insert({
            "event_id": event["id"], "venue_id": venue["id"],
            "coordinator_id": coordinator["id"], "coordinator_name": "E2E Tester",
            "coordinator_email": coordinator["email"], "event_name": event_name,
            "event_purpose": "Decision testing", "expected_attendance": 100,
            "venue_name": f"{venue_name} {index}", "booking_date": "2026-11-12",
            "start_time": "09:00", "end_time": "12:00",
        }).execute().data[0])

    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    pending = page.get_by_role("list", name="Pending booking requests")
    first = pending.get_by_role("listitem").filter(has_text=bookings[0]["venue_name"])
    first.get_by_role("radio", name="Approve", exact=True).check()
    first.get_by_role("button", name="Save decision").click()
    expect(first).to_have_count(0, timeout=20000)

    second = pending.get_by_role("listitem").filter(has_text=bookings[1]["venue_name"])
    second.get_by_role("radio", name="Reject", exact=True).check()
    second.get_by_role("button", name="Save decision").click()
    expect(second.get_by_role("alert")).to_contain_text("Provide a reason or alternative")
    second.get_by_label("Alternative venue or time (optional)").fill("Try Studio C at 14:00")
    second.get_by_role("button", name="Save decision").click()
    expect(second).to_have_count(0, timeout=20000)

    third = pending.get_by_role("listitem").filter(has_text=bookings[2]["venue_name"])
    third.get_by_role("radio", name="Approve", exact=True).check()
    # Another staff decision wins while this browser is showing stale Pending.
    admin.schema("bookings").table("bookings").update({
        "status": "rejected", "decision_reason": "Repairs",
        "decided_by": staff["id"], "decided_at": "2026-09-28T01:00:00Z",
    }).eq("id", bookings[2]["id"]).execute()
    third.get_by_role("button", name="Save decision").click()
    expect(third.get_by_role("alert")).to_contain_text("already been decided", timeout=20000)

    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    sent = page.get_by_role("list", name="Venue requests sent")
    expect(sent.get_by_role("listitem").filter(has_text=bookings[0]["venue_name"])).to_contain_text("Confirmed", timeout=20000)
    rejected = sent.get_by_role("listitem").filter(has_text=bookings[1]["venue_name"])
    expect(rejected).to_contain_text("Rejected")
    expect(rejected).to_contain_text("Alternative: Try Studio C at 14:00")
    expect(page.get_by_role("button", name="Save decision")).to_have_count(0)
    page.reload()
    expect(rejected).to_contain_text("Alternative: Try Studio C at 14:00", timeout=20000)
    assert len(admin.schema("bookings").table("bookings").select("id").eq("event_id", event["id"]).execute().data) == 3
