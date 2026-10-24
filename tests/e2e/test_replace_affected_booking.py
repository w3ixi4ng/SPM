"""TC-E2E-242 (S-78): a Coordinator replaces a booking an unavailable period
affects, without re-entering the event, and approval clears the flag.

The search rules, the one-at-a-time rule and resolving are TC-VENUEBOOKINGS-079
onward and TC-BOOKINGS-051 onward. This proves the way in from the flagged
booking, the replacement screen, and the original's state after Venue Staff
approve, working together through Kong.
"""

import re
import uuid

from playwright.sync_api import expect

from .conftest import open_request, requires_env
from .test_venue_availability import add_event, add_venue, d

pytestmark = requires_env


def test_a_coordinator_replaces_a_flagged_booking_and_approval_clears_the_flag(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    tag = uuid.uuid4().hex[:6]
    venue_a = add_venue(admin, staff, f"A {tag}")
    venue_b = add_venue(admin, staff, f"B {tag}")
    day = d(3)
    event = add_event(admin, organiser, coordinator, "S78", day)
    k = admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"], "venue_id": venue_a["id"], "coordinator_id": coordinator["id"],
        "coordinator_name": "E2E Tester", "coordinator_email": coordinator["email"],
        "booking_date": day.isoformat(), "start_time": "10:00", "end_time": "12:00",
        "event_name": event["name"], "event_purpose": event["purpose"], "expected_attendance": 40,
        "venue_name": venue_a["name"], "status": "confirmed",
        "decided_by": staff["id"], "decided_at": "2026-10-01T00:00:00+00:00",
    }).execute().data[0]
    admin.schema("bookings").table("blocks").insert({
        "venue_id": venue_a["id"], "venue_name": venue_a["name"], "start_date": day.isoformat(),
        "start_time": "09:00", "end_date": day.isoformat(), "end_time": "13:00",
        "reason": "maintenance", "created_by": staff["id"],
    }).execute()

    def k_row():
        sent = page.get_by_role("list", name="Venue requests sent")
        return sent.get_by_role("listitem").filter(has_text=venue_a["name"]).filter(has_not_text="Replacement for")

    # 1. From K's row to the replacement screen.
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    k_row().get_by_role("link", name="Find a replacement venue").click()
    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}/bookings/{k['id']}/replacement$"), timeout=20000)
    expect(page.get_by_text(f"For {event['name']}, instead of {venue_a['name']}")).to_be_visible(timeout=20000)
    expect(page.get_by_text(f"{day.day} {day:%b} {day.year} · 10:00–12:00")).to_be_visible()
    choices = page.get_by_role("list", name="Available venues")
    expect(choices.get_by_text(venue_b["name"], exact=True)).to_be_visible()
    expect(choices.get_by_text(venue_a["name"], exact=True)).to_have_count(0)
    for kind in ("date", "time", "number"):
        expect(page.locator(f"input[type={kind}]")).to_have_count(0)

    # 2. Send it. K stays flagged, with the request waiting.
    choices.get_by_label(re.compile(re.escape(venue_b["name"]))).check()
    page.get_by_role("button", name="Send replacement request").click()
    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}$"), timeout=20000)
    expect(page.get_by_role("status").filter(has_text=f"Replacement request sent to {venue_b['name']}.")).to_be_visible(
        timeout=20000
    )
    expect(k_row()).to_contain_text("Needs alternative arrangements", timeout=20000)
    expect(k_row()).to_contain_text(f"Replacement requested: {venue_b['name']}, waiting for Venue Staff")

    # 3. Venue Staff see what it replaces, and approve it.
    page.get_by_role("link", name="Back to workspace").click()
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)
    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    open_request(page, venue_b["name"])
    expect(page.get_by_text(f"Replacement for {venue_a['name']}")).to_be_visible(timeout=20000)
    page.get_by_role("radio", name="Approve", exact=True).check()
    page.get_by_role("button", name="Save decision").click()
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)

    # 4. K is replaced and no longer flagged; Venue B is confirmed.
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    expect(k_row()).to_contain_text(f"Replaced by {venue_b['name']}", timeout=20000)
    expect(k_row()).not_to_contain_text("Needs alternative arrangements")
    sent = page.get_by_role("list", name="Venue requests sent")
    expect(sent.get_by_role("listitem").filter(has_text=f"Replacement for {venue_a['name']}")).to_contain_text(
        "Confirmed"
    )

    rows = admin.schema("bookings").table("bookings").select("id,status,replaces_booking_id").eq(
        "event_id", event["id"]
    ).execute().data
    by_id = {row["id"]: row for row in rows}
    assert by_id[k["id"]]["status"] == "replaced"
    [replacement] = [row for row in rows if row["id"] != k["id"]]
    assert replacement["status"] == "confirmed"
    assert replacement["replaces_booking_id"] == k["id"]
