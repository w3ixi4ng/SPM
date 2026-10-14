"""TC-E2E-230 (S-76): Venue Staff are told which booking blocks an approval,
and a confirmed clash stays on the dashboard across a reload.

The message and the clash rule are TC-BOOKINGS-042 and TC-VENUEBOOKINGS-060;
this proves the request page and the dashboard show them through Kong.
"""

import re
import uuid

from playwright.sync_api import expect

from .conftest import open_request, requires_env
from .test_setup_turnaround import seed
from .test_venue_availability import add_event, add_venue, d

pytestmark = requires_env


def test_staff_are_told_which_booking_blocks_an_approval_and_the_clash_stays_listed(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    venue = add_venue(admin, staff, uuid.uuid4().hex[:6])
    events = {label: add_event(admin, organiser, coordinator, label, d(3)) for label in "ABCE"}
    # All valid at 0/0; the times below make A block B, and C clash with E.
    seed(admin, events["A"], venue, coordinator, staff, "confirmed", "10:00", "12:00")
    b = seed(admin, events["B"], venue, coordinator, staff, "pending", "12:30", "14:00")
    seed(admin, events["C"], venue, coordinator, staff, "confirmed", "15:00", "16:00")
    seed(admin, events["E"], venue, coordinator, staff, "confirmed", "16:30", "17:00")
    admin.schema("venues").table("venues").update(
        {"setup_minutes": 30, "turnaround_minutes": 45}).eq("id", venue["id"]).execute()
    day = d(3)

    # 1. Approving B is refused, naming A and when it occupies the venue.
    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    open_request(page, events["B"]["name"])
    page.get_by_role("radio", name="Approve", exact=True).check()
    page.get_by_role("button", name="Save decision").click()
    expect(page.get_by_role("alert").filter(has_text="Can't confirm this booking")).to_have_text(
        f"Can't confirm this booking: it overlaps {events['A']['name']} (confirmed), which occupies "
        f"{venue['name']} on {day.day} {day:%b} {day.year} from 09:30 to 12:45 "
        "(event 10:00–12:00, 30 min setup, 45 min turnaround).",
        timeout=20000,
    )
    stored = admin.schema("bookings").table("bookings").select("status").eq("id", b["id"]).execute().data[0]
    assert stored["status"] == "pending"

    # 2. The C-E clash is on the dashboard, before and after a reload.
    page.get_by_role("link", name="Back to dashboard").click()
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    for _ in range(2):
        review = page.get_by_role("list", name="Clashes to review")
        ours = review.locator("> li").filter(has_text=venue["name"])
        expect(ours).to_contain_text(events["C"]["name"], timeout=20000)
        expect(ours).to_contain_text(events["E"]["name"])
        expect(page.get_by_role("region", name="Clashes to review").get_by_role("button", name="Dismiss")).to_have_count(0)
        page.reload()

    statuses = admin.schema("bookings").table("bookings").select("status").eq("venue_id", venue["id"]).execute().data
    assert sorted(row["status"] for row in statuses) == ["confirmed", "confirmed", "confirmed", "pending"]
