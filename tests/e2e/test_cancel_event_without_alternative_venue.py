"""TC-E2E-400..401 (S-89): a Coordinator cancels an event whose venue became
unavailable, and an unaffected event never offers it.

The affected rule, the guarded write, partial failures and notification text
are TC-EVENTREQUESTS-400 onward and TC-EVENTS-400 onward. This proves the
way in from the flagged event, the slide-over, and what the Coordinator and
Organiser then see, working together through Kong and the SPA.
"""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env
from .test_venue_availability import add_event, add_venue, d

pytestmark = requires_env

REASON = "Hall A is closed for structural repairs on the event date"
ALTERNATIVES = "Discussed Hall B and Seminar Room 3 with the Organiser; neither fits"


def _booking(admin, event, venue, coordinator, staff, day, start, end):
    return admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"], "venue_id": venue["id"], "coordinator_id": coordinator["id"],
        "coordinator_name": "E2E Tester", "coordinator_email": coordinator["email"],
        "booking_date": day.isoformat(), "start_time": start, "end_time": end,
        "event_name": event["name"], "event_purpose": event["purpose"], "expected_attendance": 40,
        "venue_name": venue["name"], "status": "confirmed",
        "decided_by": staff["id"], "decided_at": "2026-10-01T00:00:00+00:00",
    }).execute().data[0]


def test_a_coordinator_cancels_an_event_whose_venue_became_unavailable(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    attendee = make_user("attendee")
    tag = uuid.uuid4().hex[:6]
    venue_a = add_venue(admin, staff, f"A {tag}")
    venue_b = add_venue(admin, staff, f"B {tag}")
    day = d(4)
    event = add_event(admin, organiser, coordinator, "S89", day)
    _booking(admin, event, venue_a, coordinator, staff, day, "09:00", "12:00")
    _booking(admin, event, venue_b, coordinator, staff, day, "13:00", "17:00")
    admin.schema("registrations").table("registrations").insert(
        {"event_id": event["id"], "attendee_id": attendee["id"]}).execute()
    admin.schema("bookings").table("blocks").insert({
        "venue_id": venue_a["id"], "venue_name": venue_a["name"], "start_date": day.isoformat(),
        "start_time": "08:00", "end_date": day.isoformat(), "end_time": "13:00",
        "reason": "maintenance", "created_by": staff["id"],
    }).execute()

    try:
        sent = page.get_by_role("list", name="Venue requests sent")

        # 1. The flagged event offers cancellation.
        sign_in(coordinator)
        page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
        page.goto(f"/coordinator/events/{event['id']}")
        expect(sent.get_by_role("listitem").filter(has_text=venue_a["name"])).to_contain_text(
            "Needs alternative arrangements", timeout=20000,
        )
        section = page.get_by_role("region", name="Venue unavailable")
        trigger = section.get_by_role("button", name="Cancel event")
        expect(trigger).to_be_visible()

        # 2. The slide-over opens on the reason.
        trigger.click()
        panel = page.get_by_role("dialog", name="Cancel event")
        expect(panel).to_be_visible()
        expect(panel.get_by_label("Reason for cancelling")).to_be_focused()

        # 3. Both fields are required; nothing is sent.
        panel.get_by_role("button", name="Cancel event").click()
        expect(panel.get_by_text("Enter why the event is being cancelled.")).to_be_visible()
        expect(panel.get_by_text("Describe the alternatives you discussed with the Organiser.")).to_be_visible()
        assert admin.schema("events").table("events").select("status").eq(
            "id", event["id"]).execute().data[0]["status"] == "planning"

        # 4. Cancel.
        panel.get_by_label("Reason for cancelling").fill(REASON)
        panel.get_by_label("Alternatives considered").fill(ALTERNATIVES)
        panel.get_by_role("button", name="Cancel event").click()
        expect(panel).to_have_count(0, timeout=30000)
        record = page.get_by_role("region", name="Event cancelled")
        expect(record).to_contain_text(REASON, timeout=20000)
        expect(record).to_contain_text("Every booking was released and everyone was notified.")
        for venue in (venue_a, venue_b):
            expect(sent.get_by_role("listitem").filter(has_text=venue["name"])).to_contain_text(
                "Released", timeout=20000,
            )

        # 5. A reload shows the same, with nothing left to finish.
        page.reload()
        record = page.get_by_role("region", name="Event cancelled")
        expect(record).to_contain_text(REASON, timeout=20000)
        expect(page.get_by_role("button", name="Finish cancellation")).to_have_count(0)
        expect(page.get_by_role("button", name="Cancel event")).to_have_count(0)

        # 6. The Organiser's inbox explains it.
        page.get_by_role("link", name="Back to workspace").click()
        page.get_by_role("button", name="Sign out").click()
        page.wait_for_url(re.compile(r"/login"), timeout=20000)
        sign_in(organiser)
        page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
        inbox = page.get_by_role("region", name="Notifications")
        expect(inbox).to_contain_text(event["name"], timeout=20000)
        expect(inbox).to_contain_text(REASON)

        rows = admin.schema("bookings").table("bookings").select("status").eq(
            "event_id", event["id"]).execute().data
        assert sorted(row["status"] for row in rows) == ["released", "released"]
    finally:
        admin.schema("notifications").table("notifications").delete().eq("event_id", event["id"]).execute()
        admin.schema("bookings").table("closed_events").delete().eq("event_id", event["id"]).execute()


def test_an_unaffected_event_never_offers_this_cancellation(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    venue = add_venue(admin, staff, f"G {uuid.uuid4().hex[:6]}")
    day = d(5)
    event = add_event(admin, organiser, coordinator, "S89 unaffected", day)
    _booking(admin, event, venue, coordinator, staff, day, "09:00", "12:00")

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    sent = page.get_by_role("list", name="Venue requests sent")
    row = sent.get_by_role("listitem").filter(has_text=venue["name"])
    expect(row).to_contain_text("Confirmed", timeout=20000)
    expect(row).not_to_contain_text("Needs alternative arrangements")
    expect(page.get_by_role("button", name="Cancel event")).to_have_count(0)
    expect(page.get_by_role("region", name="Venue unavailable")).to_have_count(0)
