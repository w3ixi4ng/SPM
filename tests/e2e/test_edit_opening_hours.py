"""TC-E2E-460 -- Venue Staff shorten a venue's opening hours; the booking it
no longer fits is kept, listed for them and flagged for the Coordinator
(S-28 reopened, manual UAT check M2-01).

The rules are TC-VENUES-037 onward, TC-VENUEBOOKINGS-460 onward and
TC-FRONTEND-410 to 413.
"""

import re
import uuid
from datetime import date, timedelta

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env

EVERY_DAY = [{"day": d, "open": "08:00:00", "close": "20:00:00"}
             for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]


def next_thursday(at_least: int = 7) -> date:
    day = date.today() + timedelta(days=at_least)
    return day + timedelta(days=(3 - day.weekday()) % 7)


def test_staff_shorten_opening_hours_and_the_booking_is_kept_and_flagged(admin, page, make_user, sign_in):
    staff = make_user("venue_staff")
    coordinator = make_user("event_coordinator")
    organiser = make_user("event_organiser")
    day = next_thursday()
    label = f"{day.day} {day:%b} {day.year}"
    tag = uuid.uuid4().hex[:6]
    venue = admin.schema("venues").table("venues").insert({
        "name": f"S28 Hall {tag}", "location": "10 Anson Road", "capacity": 100,
        "room_layouts": ["theatre"], "facilities": [], "accessibility": [],
        "operating_hours": EVERY_DAY, "created_by": staff["id"],
    }).execute().data[0]
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"], "assigned_coordinator_id": coordinator["id"],
        "status": "planning", "decision": "approved",
        "decided_at": "2026-10-01T00:00:00+00:00", "submitted_at": "2026-09-30T00:00:00+00:00",
        "name": f"spm-e2e S28 Event {tag}", "purpose": "Opening hours edit",
        "start_date": day.isoformat(), "start_time": "08:00", "end_date": day.isoformat(),
        "end_time": "18:00", "expected_attendance": 40,
    }).execute().data[0]
    booking = admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"], "venue_id": venue["id"], "venue_name": venue["name"],
        "coordinator_id": coordinator["id"], "coordinator_name": "E2E Tester",
        "coordinator_email": coordinator["email"], "booking_date": day.isoformat(),
        "start_time": "09:00", "end_time": "11:00", "event_name": event["name"],
        "event_purpose": event["purpose"], "expected_attendance": 40, "status": "confirmed",
        "decided_by": staff["id"], "decided_at": "2026-10-01T00:00:00+00:00",
    }).execute().data[0]
    warning = "Outside the venue's opening hours: it is now open 10:00–16:00 on Thursdays."

    # 1. Shorten Thursday and save.
    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    page.get_by_role("link", name=f"Edit {venue['name']}", exact=True).click()
    form = page.get_by_role("form", name="Edit venue", exact=True)
    expect(form.get_by_label("Thursday opening time")).to_have_value("08:00", timeout=20000)
    form.get_by_label("Thursday opening time").fill("10:00")
    form.get_by_label("Thursday closing time").fill("16:00")
    form.get_by_role("button", name="Save venue").click()
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=30000)
    outside = page.get_by_role("list", name="Bookings outside opening hours")
    expect(outside).to_contain_text(event["name"], timeout=20000)
    expect(outside).to_contain_text(f"{label}, 09:00–11:00")
    expect(outside).to_contain_text(warning)
    row = page.get_by_role("list", name="Venues", exact=True).get_by_role("listitem").filter(has_text=venue["name"])
    expect(row).to_contain_text("10:00–16:00", timeout=20000)

    # 2. Still listed after reload; Edit shows the new hours; the booking is kept.
    page.reload()
    review = page.get_by_role("list", name="Clashes to review")
    expect(review).to_contain_text(event["name"], timeout=20000)
    expect(review).to_contain_text(warning)
    page.get_by_role("link", name=f"Edit {venue['name']}", exact=True).click()
    expect(form.get_by_label("Thursday opening time")).to_have_value("10:00", timeout=20000)
    expect(form.get_by_label("Thursday closing time")).to_have_value("16:00")
    stored = admin.schema("bookings").table("bookings").select("status").eq("id", booking["id"]).execute().data
    assert stored == [{"status": "confirmed"}]

    # 3. The Coordinator sees the same warning on the booking, still Confirmed.
    page.get_by_role("link", name="Cancel", exact=True).click()
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=30000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    mine = page.get_by_role("list", name="Venue requests sent").get_by_role("listitem").filter(has_text=venue["name"])
    expect(mine.get_by_role("alert").filter(has_text="opening hours")).to_contain_text(warning, timeout=20000)
    expect(mine).to_contain_text("Confirmed")
