"""TC-E2E-234 -- a Coordinator approves a cancellation request, and the event
shows as Cancelled for both sides (S-61).

Decline, retries and every refusal are TC-EVENTS-131..138 and
TC-EVENTREQUESTS-064..067/111's job and are not restaged here. This proves
the Coordinator's review journey through Kong, the confirm step, and that
the venue booking disappears.
"""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env

DAY = "2026-11-12"


# --- TC-E2E-234 -----------------------------------------------------------
def test_a_coordinator_approves_a_cancellation_and_both_sides_see_cancelled(
    admin, page, make_user, sign_in
):
    coordinator = make_user("event_coordinator")
    organiser = make_user("event_organiser")
    staff = make_user("venue_staff")
    tag = uuid.uuid4().hex[:6]
    # Attributed to the staff member, organiser and coordinator, so
    # make_user's teardown deletes them.
    venue = admin.schema("venues").table("venues").insert({
        "name": f"spm-e2e Hall {tag}", "location": "10 Anson Road", "capacity": 300,
        "room_layouts": ["theatre"], "facilities": [],
        "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
        "created_by": staff["id"],
    }).execute().data[0]
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"], "assigned_coordinator_id": coordinator["id"],
        "status": "planning", "name": f"spm-e2e Cancel {tag}", "purpose": "Cancellation review",
        "start_date": DAY, "start_time": "09:00", "end_date": DAY, "end_time": "18:00",
        "expected_attendance": 120, "decision": "approved",
        "decided_at": "2026-10-01T00:00:00+00:00", "submitted_at": "2026-09-30T00:00:00+00:00",
        "cancellation_reason": "Keynote speaker withdrew",
        "cancellation_requested_at": "2026-10-11T09:00:00+00:00",
        "cancellation_requested_by": organiser["id"],
    }).execute().data[0]
    admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"], "venue_id": venue["id"], "coordinator_id": coordinator["id"],
        "coordinator_name": "E2E Tester", "coordinator_email": coordinator["email"],
        "booking_date": DAY, "start_time": "09:00", "end_time": "12:00",
        "event_name": event["name"], "event_purpose": "Cancellation review",
        "expected_attendance": 120, "venue_name": venue["name"], "status": "confirmed",
        "decided_by": staff["id"], "decided_at": "2026-10-02T00:00:00+00:00",
    }).execute()

    def bookings_left():
        return admin.schema("bookings").table("bookings").select("id").eq("event_id", event["id"]).execute().data

    def event_row():
        return admin.schema("events").table("events").select("status").eq("id", event["id"]).execute().data[0]

    # 1. The dashboard flags the request.
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.get_by_role("tab", name="Events").click()
    row = page.get_by_role("listitem").filter(has_text=event["name"])
    expect(row.get_by_text("Cancellation requested", exact=True)).to_be_visible(timeout=20000)
    row.get_by_role("link").first.click()
    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}$"), timeout=20000)

    # 2. The reason is shown; Keep event changes nothing.
    expect(page.get_by_text("Keynote speaker withdrew")).to_be_visible(timeout=20000)
    page.get_by_role("button", name="Approve cancellation").click()
    panel = page.get_by_role("dialog")
    expect(panel.get_by_text("1 venue booking will be removed and its time freed.")).to_be_visible(timeout=20000)
    panel.get_by_role("button", name="Keep event").click()
    expect(panel).to_have_count(0)
    assert event_row()["status"] == "planning"
    assert len(bookings_left()) == 1

    # 3. Cancel event.
    page.get_by_role("button", name="Approve cancellation").click()
    panel.get_by_role("button", name="Cancel event").click()
    expect(page.get_by_text("Event cancelled. 1 venue booking was released.")).to_be_visible(timeout=20000)

    # 4. After a reload: Cancelled, no bookings, no decision buttons.
    page.reload()
    expect(page.get_by_text("Cancelled", exact=True).first).to_be_visible(timeout=20000)
    # The venue list loads on its own after the event, so wait as long as for the rest.
    expect(page.get_by_text("No venue requests sent yet.")).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Approve cancellation")).to_have_count(0)
    assert event_row()["status"] == "cancelled"
    assert bookings_left() == []

    # 5. The Organiser sees Cancelled, with no tag.
    page.goto("/dashboard/event-coordinator")
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=30000)
    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=30000)
    organiser_row = page.get_by_role("listitem").filter(has_text=event["name"])
    expect(organiser_row.get_by_text("Cancelled", exact=True)).to_be_visible(timeout=20000)
    expect(organiser_row.get_by_text("Cancellation requested", exact=True)).to_have_count(0)
    expect(organiser_row.get_by_text("Cancellation declined", exact=True)).to_have_count(0)

    # The event page explains the cancellation, with no empty decision
    # banner, and the event can no longer be edited.
    organiser_row.get_by_role("link").first.click()
    page.wait_for_url(re.compile(rf"/events/{event['id']}$"), timeout=20000)
    expect(page.get_by_text("Your cancellation request was approved. This event is cancelled.")).to_be_visible(timeout=20000)
    expect(page.get_by_text("This request has been approved and is in planning.")).to_have_count(0)
    expect(page.get_by_label("Event name")).to_be_disabled()
