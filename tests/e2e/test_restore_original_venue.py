"""TC-E2E-270 (S-90): once the original venue is free again, a Coordinator
asks to keep it, Venue Staff confirm from their dashboard, and the event keeps
its first-choice venue.

The free-venue check, the one-request rule and what confirming writes are
TC-BOOKINGS-124..130 and TC-VENUEBOOKINGS-131..136. This proves the
Coordinator's button and the Venue Staff section are wired to them through
Kong, for the two roles access.js gives them to.
"""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env
from .test_venue_availability import add_event, add_venue, d

pytestmark = requires_env


def test_a_coordinator_restores_the_original_venue_and_venue_staff_confirm_it(
    admin, page, make_user, sign_in
):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    tag = uuid.uuid4().hex[:6]
    venue_v = add_venue(admin, staff, f"V {tag}")
    venue_w = add_venue(admin, staff, f"W {tag}")
    day = d(3)
    event = add_event(admin, organiser, coordinator, "S90", day)
    common = {
        "event_id": event["id"], "coordinator_id": coordinator["id"],
        "coordinator_name": "E2E Tester", "coordinator_email": coordinator["email"],
        "booking_date": day.isoformat(), "start_time": "10:00", "end_time": "12:00",
        "event_name": event["name"], "event_purpose": event["purpose"], "expected_attendance": 40,
    }
    bookings = admin.schema("bookings").table("bookings")
    original = bookings.insert({
        **common, "venue_id": venue_v["id"], "venue_name": venue_v["name"], "status": "confirmed",
        "decided_by": staff["id"], "decided_at": "2026-10-01T00:00:00+00:00",
    }).execute().data[0]
    bookings.insert({
        **common, "venue_id": venue_w["id"], "venue_name": venue_w["name"], "status": "pending",
        "replaces_booking_id": original["id"],
    }).execute()

    def rows():
        return page.get_by_role("list", name="Venue requests sent").get_by_role("listitem")

    def original_row():
        return rows().filter(has_text=venue_v["name"]).filter(
            has_not_text="Replacement for").filter(has_not_text="Withdrawn")

    def sign_out():
        page.goto("/dashboard")
        page.get_by_role("button", name="Sign out").click()
        page.wait_for_url(re.compile(r"/login"), timeout=20000)

    # 1. The Coordinator asks to keep V.
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    expect(original_row()).to_contain_text(
        f"Replacement requested: {venue_w['name']}, waiting for Venue Staff. {venue_v['name']} is free again.",
        timeout=20000,
    )
    original_row().get_by_role("button", name="Restore original venue").click()
    expect(original_row()).to_contain_text(
        f"Restore requested: waiting for Venue Staff to confirm {venue_v['name']}", timeout=20000
    )
    expect(page.get_by_role("button", name="Restore original venue")).to_have_count(0)
    sign_out()

    # 2. Venue Staff confirm it from their dashboard.
    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    requests = page.get_by_role("list", name="Restore requests")
    row = requests.get_by_role("listitem").filter(has_text=event["name"])
    expect(row).to_contain_text(f"Keep {venue_v['name']}", timeout=20000)
    expect(row).to_contain_text(f"Withdraw the request for {venue_w['name']}")
    row.get_by_role("button", name="Confirm restore").click()
    expect(page.get_by_role("status").filter(
        has_text=f"{venue_v['name']} restored for {event['name']}.")).to_be_visible(timeout=20000)
    expect(requests.get_by_role("listitem").filter(has_text=event["name"])).to_have_count(0)
    sign_out()

    # 3. The event keeps V; the request for W is withdrawn.
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    expect(original_row()).to_contain_text("Resolved: Restored to the original venue", timeout=20000)
    withdrawn = rows().filter(has_text=venue_w["name"]).filter(has_text="Withdrawn")
    expect(withdrawn).to_contain_text(f"Withdrawn: {venue_v['name']} was restored")
