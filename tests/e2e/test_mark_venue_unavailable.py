"""TC-E2E-234 (S-77): Venue Staff mark a venue unavailable over a confirmed
booking, and its Coordinator sees the notification and the flag.

The overlap rules, reasons and status codes are TC-BOOKINGS-044 onward and
TC-VENUEBOOKINGS-067 onward. This proves the panel, the affected-bookings
summary, and the flag and notification reaching the Coordinator work
together through Kong.
"""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env
from .test_venue_availability import add_event, add_venue, d, open_calendar

pytestmark = requires_env


def test_staff_mark_a_period_over_a_confirmed_booking_and_its_coordinator_is_told(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    venue = add_venue(admin, staff, uuid.uuid4().hex[:6])
    day = d(3)
    event = add_event(admin, organiser, coordinator, "S77", day)
    booking = admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"], "venue_id": venue["id"], "coordinator_id": coordinator["id"],
        "coordinator_name": "E2E Tester", "coordinator_email": coordinator["email"],
        "booking_date": day.isoformat(), "start_time": "10:00", "end_time": "12:00",
        "event_name": event["name"], "event_purpose": event["purpose"], "expected_attendance": 40,
        "venue_name": venue["name"], "status": "confirmed",
        "decided_by": staff["id"], "decided_at": "2026-10-01T00:00:00+00:00",
    }).execute().data[0]
    when = f"{day.day} {day:%b} {day.year}"

    # 1-3. Staff mark the period; the description is required for Other.
    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    open_calendar(page, venue["name"], "/dashboard/venue-staff")
    page.get_by_role("button", name="Mark unavailable").click()
    panel = page.get_by_role("dialog", name="Mark unavailable")
    panel.get_by_label("Start date").fill(day.isoformat())
    panel.get_by_label("Start time").fill("09:00")
    panel.get_by_label("End date").fill(day.isoformat())
    panel.get_by_label("End time").fill("13:00")
    panel.get_by_label("Reason").select_option(label="Other operational reason")
    panel.get_by_role("button", name="Mark unavailable").click()
    expect(panel.get_by_role("alert")).to_contain_text("Describe the operational reason.")
    assert admin.schema("bookings").table("blocks").select("id").eq("venue_id", venue["id"]).execute().data == []

    panel.get_by_label("Description").fill("Water leak in ceiling")
    panel.get_by_role("button", name="Mark unavailable").click()
    saved = page.get_by_role("dialog", name=f"{venue['name']} marked unavailable")
    expect(saved).to_contain_text(
        "1 booking needs alternative arrangements. Their Coordinators have been notified.", timeout=20000,
    )
    expect(saved.get_by_role("list", name="Affected bookings")).to_contain_text(
        f"{event['name']} · {day.day} {day:%b} {day.year} · 10:00–12:00 · Booked"
    )
    saved.get_by_role("button", name="Done").click()

    # 4. The Coordinator is notified on their dashboard.
    page.get_by_role("link", name="Back to dashboard").click()
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    inbox = page.get_by_role("region", name="Notifications")
    expect(inbox).to_contain_text(venue["name"], timeout=20000)
    expect(inbox).to_contain_text("needs alternative arrangements.")

    # 5. The event page flags the booking, which is otherwise unchanged.
    page.goto(f"/coordinator/events/{event['id']}")
    sent = page.get_by_role("list", name="Venue requests sent")
    row = sent.get_by_role("listitem").filter(has_text=venue["name"])
    expect(row).to_contain_text("Needs alternative arrangements", timeout=20000)
    expect(row).to_contain_text(f"from {when} 09:00 to {when} 13:00")
    expect(row).to_contain_text("Other operational reason: Water leak in ceiling")
    expect(row).to_contain_text("Confirmed")
    expect(page.get_by_text("Planning", exact=True).first).to_be_visible()

    stored = admin.schema("bookings").table("bookings").select("status").eq("id", booking["id"]).execute().data
    assert stored == [{"status": "confirmed"}]
    events = admin.schema("events").table("events").select("status").eq("id", event["id"]).execute().data
    assert events == [{"status": "planning"}]
