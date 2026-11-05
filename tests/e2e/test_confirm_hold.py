"""TC-E2E-480 (S-81 reopened): the Coordinator confirms a tentative hold, the
Venue Staff who placed it are told, and only then can they approve it.

The rules are TC-BOOKINGS-470 onward, TC-VENUEBOOKINGS-480 onward and
TC-FRONTEND-420 onward. This proves both roles' screens, the inbox and the
gate work together through Kong.
"""

import re
import uuid

from playwright.sync_api import expect

from .conftest import open_request, requires_env
from .test_setup_turnaround import seed
from .test_venue_availability import add_event, add_venue, d

pytestmark = requires_env

WAITING = ("Waiting for the Event Coordinator to confirm this hold. You can reject it or release "
           "the hold, but not approve it yet.")


def test_the_coordinator_confirms_a_hold_and_venue_staff_then_approve_it(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    venue = add_venue(admin, staff, uuid.uuid4().hex[:6])
    event = add_event(admin, organiser, coordinator, "Hold", d(3))
    booking = seed(admin, event, venue, coordinator, staff, "pending", "10:00", "12:00")

    def sign_out():
        # The request and event pages have no Sign out button; drop the
        # httpOnly session cookies instead, as signing out does.
        page.context.clear_cookies()

    # 1. Venue Staff hold the request.
    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    open_request(page, event["name"])
    page.get_by_label("Hold expiry").fill("2099-01-01T12:00")
    page.get_by_role("button", name="Place hold").click()
    expect(page.get_by_role("button", name="Release hold")).to_be_visible(timeout=20000)
    expect(page.get_by_text(WAITING)).to_be_visible()

    # 2. Approve is not available yet; Reject and Release hold are.
    expect(page.get_by_role("radio", name="Approve", exact=True)).to_be_disabled()
    expect(page.get_by_role("radio", name="Reject", exact=True)).to_be_enabled()
    expect(page.get_by_role("button", name="Release hold")).to_be_enabled()

    # 3. The Coordinator confirms the hold on the event.
    sign_out()
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=30000)
    page.goto(f"/coordinator/events/{event['id']}")
    sent = page.get_by_role("list", name="Venue requests sent")
    expect(sent).to_contain_text(
        "Venue Staff are holding this venue for you. Confirm the hold so they can approve it.", timeout=20000)
    sent.get_by_role("button", name=f"Confirm hold on {venue['name']}").click()
    confirmed_text = "Hold confirmed. Waiting for Venue Staff to approve it."
    expect(sent).to_contain_text(confirmed_text, timeout=20000)
    expect(sent.get_by_role("button", name=f"Confirm hold on {venue['name']}")).to_have_count(0)

    # 4. It survives a reload.
    page.reload()
    expect(page.get_by_role("list", name="Venue requests sent")).to_contain_text(confirmed_text, timeout=20000)

    # 5. Venue Staff are told, and Approve is available.
    sign_out()
    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    when = f"{d(3).day} {d(3):%b %Y}, 10:00–12:00"
    expect(page.get_by_role("region", name="Notifications")).to_contain_text(
        f"confirmed the tentative hold for {venue['name']} on {when} ({event['name']}). "
        "You can now approve it before the hold expires.", timeout=20000)
    open_request(page, event["name"])
    expect(page.get_by_text("The Event Coordinator confirmed this hold.")).to_be_visible(timeout=20000)
    approve = page.get_by_role("radio", name="Approve", exact=True)
    expect(approve).to_be_enabled()

    # 6. Approved.
    approve.check()
    page.get_by_role("button", name="Save decision").click()
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    expect(page.get_by_role("status").filter(
        has_text=f"Booking for {event['name']} at {venue['name']} confirmed.")).to_be_visible(timeout=20000)
    stored = admin.schema("bookings").table("bookings").select("status").eq("id", booking["id"]).execute().data[0]
    assert stored["status"] == "confirmed"
