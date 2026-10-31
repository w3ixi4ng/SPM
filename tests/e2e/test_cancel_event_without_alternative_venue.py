"""TC-E2E-269 (S-89): a Coordinator cancels an event its closed venue left
without a home, and the Organiser sees why.

The rules -- which events qualify, the reason, the release and who is told --
are TC-EVENTS-208 onward and TC-EVENTREQUESTS-129 onward. This proves the
Cancel event action appearing on the flag, the slide-over, and the result on
both sides, working together through Kong.
"""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env
from .test_venue_availability import add_venue, d

pytestmark = requires_env

REASON = "V is closed for repairs and no other venue fits."


def test_a_coordinator_cancels_an_event_its_closed_venue_left_without_a_home(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    venue = add_venue(admin, staff, f"S89 {uuid.uuid4().hex[:6]}")
    day = d(3)
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"], "assigned_coordinator_id": coordinator["id"],
        "status": "planning", "decision": "approved",
        "decided_at": "2026-10-01T00:00:00+00:00", "submitted_at": "2026-09-30T00:00:00+00:00",
        "name": f"spm-e2e S89 Event {uuid.uuid4().hex[:6]}", "purpose": "Coordinator cancellation",
        "start_date": day.isoformat(), "start_time": "18:00",
        "end_date": day.isoformat(), "end_time": "21:00", "expected_attendance": 40,
    }).execute().data[0]
    admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"], "venue_id": venue["id"], "coordinator_id": coordinator["id"],
        "coordinator_name": "E2E Tester", "coordinator_email": coordinator["email"],
        "booking_date": day.isoformat(), "start_time": "18:00", "end_time": "21:00",
        "event_name": event["name"], "event_purpose": event["purpose"], "expected_attendance": 40,
        "venue_name": venue["name"], "status": "confirmed",
        "decided_by": staff["id"], "decided_at": "2026-10-01T00:00:00+00:00",
    }).execute()
    admin.schema("bookings").table("blocks").insert({
        "venue_id": venue["id"], "venue_name": venue["name"], "start_date": day.isoformat(),
        "start_time": "08:00", "end_date": day.isoformat(), "end_time": "23:00",
        "reason": "maintenance", "created_by": staff["id"],
    }).execute()
    when = f"{day.day} {day:%b} {day.year}"
    today = d(0)
    cancelled_on = f"{today.day} {today:%b} {today.year}"

    # 1. The flagged booking offers Cancel event.
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    sent = page.get_by_role("list", name="Venue requests sent")
    expect(sent.get_by_role("listitem").filter(has_text=venue["name"])).to_contain_text(
        "Needs alternative arrangements", timeout=20000
    )

    # 2. Cancel it with a reason in the slide-over.
    page.get_by_role("button", name="Cancel event", exact=True).click()
    panel = page.get_by_role("dialog", name="Cancel this event?")
    panel.get_by_label("Why is the event being cancelled?").fill(REASON)
    panel.get_by_role("button", name="Cancel event", exact=True).click()
    expect(panel).to_have_count(0, timeout=20000)
    expect(page.get_by_role("status").filter(
        has_text="Event cancelled. 1 venue booking released. The Organiser was notified."
    )).to_be_visible(timeout=20000)

    # 3. After a reload: no venues, the recorded reason, no Cancel event.
    page.reload()
    expect(page.get_by_text(f"You cancelled this event on {cancelled_on}: {REASON}")).to_be_visible(timeout=20000)
    expect(page.get_by_text("No venue requests sent yet.")).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Cancel event", exact=True)).to_have_count(0)
    assert admin.schema("bookings").table("bookings").select("id").eq(
        "event_id", event["id"]
    ).execute().data == []

    # 4. The Organiser is told, with the reason.
    page.get_by_role("link", name="Back to workspace").click()
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)
    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    inbox = page.get_by_role("region", name="Notifications")
    expect(inbox).to_contain_text(
        f"Your event {event['name']}, {when}, 6:00 pm – 9:00 pm, "
        f"was cancelled by your Event Coordinator: {REASON}",
        timeout=20000,
    )
