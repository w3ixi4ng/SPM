"""TC-E2E-226 and 227 (S-75): setup and turnaround times, and Venue Staff's
compact request list with one page per request.

The counting rules are TC-VENUEBOOKINGS-050 onward and TC-FRONTEND-081
onward. These prove the venue form, the clash list, the Coordinator's
warning, the calendar and the request page work together through Kong.
"""

import re
import uuid

from playwright.sync_api import expect

from .conftest import open_request, requires_env
from .test_venue_availability import add_event, add_venue, d, day_cell, day_detail, open_calendar, show_month

pytestmark = requires_env


def seed(admin, event, venue, coordinator, staff, status, start, end):
    row = {
        "event_id": event["id"], "venue_id": venue["id"], "coordinator_id": coordinator["id"],
        "coordinator_name": "E2E Tester", "coordinator_email": coordinator["email"],
        "booking_date": d(3).isoformat(), "start_time": start, "end_time": end,
        "event_name": event["name"], "event_purpose": event["purpose"], "expected_attendance": 40,
        "venue_name": venue["name"], "status": status,
    }
    if status == "confirmed":
        row.update(decided_by=staff["id"], decided_at="2026-10-01T00:00:00+00:00")
    if status == "held":
        row.update(held_by=staff["id"], held_at="2026-10-01T00:00:00+00:00")
    return admin.schema("bookings").table("bookings").insert(row).execute().data[0]


def world(admin, make_user):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    venue = add_venue(admin, staff, uuid.uuid4().hex[:6])
    event_a = add_event(admin, organiser, coordinator, "A", d(3))
    event_b = add_event(admin, organiser, coordinator, "B", d(3))
    seed(admin, event_a, venue, coordinator, staff, "confirmed", "10:00", "12:00")
    seed(admin, event_b, venue, coordinator, staff, "held", "12:30", "14:00")
    return coordinator, staff, organiser, venue, event_a, event_b


# --- TC-E2E-226 -----------------------------------------------------------
def test_staff_set_setup_and_turnaround_see_the_clash_and_the_coordinator_is_warned(admin, page, make_user, sign_in):
    coordinator, staff, _, venue, event_a, event_b = world(admin, make_user)

    # 1. Staff edit the venue's times and save.
    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    page.get_by_role("link", name=f"Edit {venue['name']}", exact=True).click()
    page.get_by_label("Setup time (minutes)").fill("30")
    page.get_by_label("Turnaround time (minutes)").fill("45")
    page.get_by_role("button", name="Save venue").click()
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    clashing = page.get_by_role("list", name="Clashing bookings")
    expect(clashing).to_contain_text(event_a["name"], timeout=20000)
    expect(clashing).to_contain_text(event_b["name"])
    stored = admin.schema("venues").table("venues").select("setup_minutes,turnaround_minutes").eq("id", venue["id"]).execute().data[0]
    assert stored == {"setup_minutes": 30, "turnaround_minutes": 45}
    statuses = admin.schema("bookings").table("bookings").select("status").eq("venue_id", venue["id"]).execute().data
    assert sorted(row["status"] for row in statuses) == ["confirmed", "held"]  # neither removed

    # 2. The Coordinator sees the warning on B, and the calendar's times.
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=30000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=30000)
    page.goto(f"/coordinator/events/{event_b['id']}")
    sent = page.get_by_role("list", name="Venue requests sent")
    expect(sent.get_by_role("alert")).to_contain_text("Clashes with another confirmed booking", timeout=20000)
    expect(sent.get_by_role("alert")).to_contain_text("venue in use 09:30–12:45")

    open_calendar(page, venue["name"], "/dashboard/event-coordinator")
    expect(page.get_by_text("Setup 30 min · Turnaround 45 min")).to_be_visible(timeout=20000)
    show_month(page, d(3))
    day_cell(page, d(3)).click()
    expect(day_detail(page, d(3))).to_contain_text("Booked 10:00–12:00 · venue in use 09:30–12:45")


# --- TC-E2E-227 -----------------------------------------------------------
def test_staff_open_a_request_from_a_compact_list_and_decide_it_on_its_page(admin, page, make_user, sign_in):
    coordinator, staff, organiser, venue, _, _ = world(admin, make_user)
    event_p = add_event(admin, organiser, coordinator, "P", d(3))
    p = seed(admin, event_p, venue, coordinator, staff, "pending", "16:00", "17:00")

    # 1. One compact row per request, with no forms in the list.
    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    pending = page.get_by_role("list", name="Pending booking requests")
    row = pending.get_by_role("link").filter(has_text=event_p["name"])
    expect(row).to_contain_text(venue["name"], timeout=20000)
    expect(row).to_contain_text("16:00–17:00")
    expect(row).to_contain_text("Pending")
    expect(pending.get_by_role("button", name="Place hold")).to_have_count(0)
    expect(pending.get_by_role("button", name="Save decision")).to_have_count(0)

    # 2. The request's own page, which survives a reload.
    open_request(page, event_p["name"])
    assert page.url.endswith(f"/venue-bookings/{p['id']}")
    page.reload()
    expect(page.get_by_role("heading", name=event_p["name"])).to_be_visible(timeout=20000)
    expect(page.get_by_role("link", name="Back to dashboard")).to_be_visible()

    # 3. Hold, then approve; back on the dashboard once, and P has left the list.
    page.get_by_role("button", name="Place hold").click()
    expect(page.get_by_role("button", name="Release hold")).to_be_visible(timeout=20000)
    page.get_by_role("radio", name="Approve", exact=True).check()
    page.get_by_role("button", name="Save decision").click()
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    expect(page.get_by_role("status").filter(has_text=f"Booking for {event_p['name']} at {venue['name']} confirmed.")).to_be_visible(timeout=20000)
    expect(pending.get_by_role("link").filter(has_text=event_p["name"])).to_have_count(0, timeout=20000)
    page.reload()
    expect(page.get_by_text(f"Booking for {event_p['name']}")).to_have_count(0)
