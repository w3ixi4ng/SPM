"""TC-E2E-220 and 221 -- a venue's availability calendar (S-30).

The day rules are TC-FRONTEND-067 to 070 and the API is TC-VENUEBOOKINGS-035
onward. These prove the calendar is reachable through Kong and the SPA
fallback, shows each state apart, greys out days before tomorrow, and shows
changes made elsewhere on the next open or Refresh.
"""

import re
import uuid
from datetime import date, timedelta

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env

EVERY_DAY = [
    {"day": day, "open": "08:00:00", "close": "18:00:00"}
    for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
]


def d(days: int) -> date:
    # The browser runs on this machine, so its today is this today.
    return date.today() + timedelta(days=days)


def day_name(day: date) -> str:
    """How a day cell and the day's detail are named, e.g. "12 November 2026"."""
    return f"{day.day} {day:%B} {day.year}"


def add_venue(admin, staff, suffix):
    name = f"spm-e2e S30 Venue {suffix}"
    venue = admin.schema("venues").table("venues").insert({
        "name": name, "location": "10 Anson Road", "capacity": 150,
        "room_layouts": ["theatre"], "facilities": [], "accessibility": [],
        "operating_hours": EVERY_DAY, "created_by": staff["id"],
    }).execute().data[0]
    return venue


def add_event(admin, organiser, coordinator, label, day: date):
    return admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "assigned_coordinator_id": coordinator["id"],
        "status": "planning",
        "decision": "approved",
        "decided_at": "2026-10-01T00:00:00+00:00",
        "submitted_at": "2026-09-30T00:00:00+00:00",
        "name": f"spm-e2e S30 Event {label} {uuid.uuid4().hex[:6]}",
        "purpose": "Availability calendar testing",
        "start_date": day.isoformat(), "start_time": "08:00",
        "end_date": day.isoformat(), "end_time": "18:00",
        "expected_attendance": 40,
    }).execute().data[0]


def open_calendar(page, venue_name, dashboard):
    """From the role's dashboard, choose Availability on the venue's row."""
    page.goto(dashboard)
    if dashboard.endswith("event-coordinator"):
        page.get_by_role("tab", name="Venues").click()
    page.get_by_role("link", name=f"Availability for {venue_name}").click()
    page.wait_for_url(re.compile(r"/venues/[^/]+/availability$"), timeout=20000)
    page.get_by_role("heading", name=f"{venue_name} availability").wait_for(timeout=20000)


def show_month(page, day: date):
    """Move the calendar to the month `day` is in, with the dropdowns. The
    year goes first, so no step lands on a month before the first one."""
    page.get_by_label("Year", exact=True).select_option(str(day.year))
    page.get_by_label("Month", exact=True).select_option(str(day.month))
    page.get_by_role("region", name=f"{day:%B} {day.year}").wait_for(timeout=20000)


def day_cell(page, day: date):
    return page.get_by_role("button", name=re.compile(rf"\b{re.escape(day_name(day))}: "))


def day_detail(page, day: date):
    return page.get_by_role("region", name=re.compile(rf"\b{re.escape(day_name(day))}$"))


# --- TC-E2E-220 -----------------------------------------------------------
def test_a_coordinator_sees_booked_held_unavailable_and_past_days_apart(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    venue = add_venue(admin, staff, uuid.uuid4().hex[:6])
    event_a = add_event(admin, organiser, coordinator, "A", d(2))
    event_b = add_event(admin, organiser, coordinator, "B", d(2))

    def booking(event, start, end, status):
        row = {
            "event_id": event["id"], "venue_id": venue["id"],
            "coordinator_id": coordinator["id"], "coordinator_name": "E2E Tester",
            "coordinator_email": coordinator["email"], "booking_date": d(2).isoformat(),
            "start_time": start, "end_time": end, "event_name": event["name"],
            "event_purpose": event["purpose"], "expected_attendance": 40, "venue_name": venue["name"],
            "status": status,
        }
        if status == "confirmed":
            row.update(decided_by=staff["id"], decided_at="2026-10-01T00:00:00+00:00")
        admin.schema("bookings").table("bookings").insert(row).execute()

    booking(event_a, "09:00", "12:00", "confirmed")
    booking(event_b, "14:00", "16:00", "pending")
    admin.schema("bookings").table("blocks").insert({
        "venue_id": venue["id"], "venue_name": venue["name"],
        "start_date": d(3).isoformat(), "end_date": d(4).isoformat(),
        "reason": "maintenance", "note": "spm-e2e private note", "created_by": staff["id"],
    }).execute()

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    open_calendar(page, venue["name"], "/dashboard/event-coordinator")

    # The SPA fallback and the session survive a reload on the page's own URL.
    page.reload()
    page.get_by_role("heading", name=f"{venue['name']} availability").wait_for(timeout=20000)
    expect(page.get_by_role("link", name="Back to dashboard")).to_be_visible()

    # It opens on tomorrow's month, and nothing earlier can be reached.
    expect(page.get_by_label("Month", exact=True)).to_have_value(str(d(1).month))
    expect(page.get_by_label("Year", exact=True)).to_have_value(str(d(1).year))
    expect(page.get_by_role("button", name="Previous month")).to_be_disabled()
    if d(0).month == d(1).month:
        # Today's cell is greyed out and cannot be clicked.
        expect(day_cell(page, d(0))).to_be_disabled()

    show_month(page, d(2))
    day_cell(page, d(2)).click()
    detail = day_detail(page, d(2))
    expect(detail).to_contain_text("Booked 09:00–12:00", timeout=20000)
    expect(detail).to_contain_text("Tentatively held 14:00–16:00")

    for day in (d(3), d(4)):
        show_month(page, day)
        day_cell(page, day).click()
        expect(day_detail(page, day)).to_contain_text("Unavailable — Maintenance")
    show_month(page, d(5))
    day_cell(page, d(5)).click()
    expect(day_detail(page, d(5))).to_contain_text("Available")

    legend = page.get_by_role("list", name="What the colours mean")
    for label in ("Available", "Tentatively held", "Booked", "Unavailable", "Closed"):
        expect(legend).to_contain_text(label)

    for private in (event_a["name"], event_b["name"], "spm-e2e private note"):
        expect(page.get_by_text(private)).to_have_count(0)
    expect(page.get_by_role("button", name="Mark unavailable")).to_have_count(0)


# --- TC-E2E-221 -----------------------------------------------------------
def test_a_new_hold_a_new_block_and_a_removed_block_all_show_up(admin, browser, base_url, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    venue = add_venue(admin, staff, uuid.uuid4().hex[:6])
    first = add_event(admin, organiser, coordinator, "First", d(5))
    second = add_event(admin, organiser, coordinator, "Second", d(5))

    # 1. The Coordinator opens the calendar: D+5 is free.
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    open_calendar(page, venue["name"], "/dashboard/event-coordinator")
    if d(5).month != d(1).month:
        page.get_by_role("button", name="Next month").click()
    day_cell(page, d(5)).click()
    expect(day_detail(page, d(5))).to_contain_text("Available", timeout=20000)

    # 2. A request from the first event holds D+5; the second event is refused.
    def request(event, start, end):
        page.goto(f"/coordinator/events/{event['id']}/request-venue")
        page.get_by_role("heading", name="Request a venue").wait_for(timeout=20000)
        row = page.get_by_role("list", name="Venues").get_by_role("listitem").filter(has_text=venue["name"])
        row.get_by_role("radio").check()
        page.get_by_label("Date", exact=True).fill(d(5).isoformat())
        page.get_by_label("From", exact=True).fill(start)
        page.get_by_label("To", exact=True).fill(end)
        page.get_by_role("button", name="Send request").click()

    request(first, "10:00", "11:00")
    page.wait_for_url(re.compile(rf"/coordinator/events/{first['id']}$"), timeout=20000)
    open_calendar(page, venue["name"], "/dashboard/event-coordinator")
    show_month(page, d(5))
    day_cell(page, d(5)).click()
    expect(day_detail(page, d(5))).to_contain_text("Tentatively held 10:00–11:00", timeout=20000)

    request(second, "10:30", "11:30")
    refused = page.get_by_role("alert").filter(has_text="already tentatively held")
    expect(refused).to_contain_text(f"{venue['name']} is already tentatively held on", timeout=20000)
    expect(refused).to_contain_text("from 10:00 to 11:00")

    open_calendar(page, venue["name"], "/dashboard/event-coordinator")
    show_month(page, d(6))

    # 3. Venue Staff, in their own browser, mark D+6 unavailable.
    staff_context = browser.new_context(base_url=base_url)
    try:
        staff_page = staff_context.new_page()
        staff_page.goto("/login")
        staff_page.fill("input[name=email]", staff["email"])
        staff_page.fill("input[name=password]", staff["password"])
        staff_page.click("button[type=submit]")
        staff_page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
        open_calendar(staff_page, venue["name"], "/dashboard/venue-staff")
        show_month(staff_page, d(6))

        staff_page.get_by_role("button", name="Mark unavailable").click()
        panel = staff_page.get_by_role("dialog", name="Mark unavailable")
        panel.get_by_label("First day").fill(d(6).isoformat())
        panel.get_by_label("Last day").fill(d(6).isoformat())
        panel.get_by_label("Reason").select_option(label="Renovation")
        panel.get_by_role("button", name="Mark unavailable").click()
        expect(panel).to_have_count(0, timeout=20000)

        # Staff see it straight away.
        day_cell(staff_page, d(6)).click()
        expect(day_detail(staff_page, d(6))).to_contain_text("Unavailable — Renovation", timeout=20000)

        # 4. The Coordinator's open calendar shows it on Refresh.
        page.get_by_role("button", name="Refresh").click()
        day_cell(page, d(6)).click()
        expect(day_detail(page, d(6))).to_contain_text("Unavailable — Renovation", timeout=20000)

        # 5. Staff remove it; the Coordinator's Refresh shows the day free again.
        day_detail(staff_page, d(6)).get_by_role("button", name="Remove").click()
        expect(day_detail(staff_page, d(6))).to_contain_text("Available", timeout=20000)
    finally:
        staff_context.close()

    page.get_by_role("button", name="Refresh").click()
    day_cell(page, d(6)).click()
    expect(day_detail(page, d(6))).to_contain_text("Available", timeout=20000)
