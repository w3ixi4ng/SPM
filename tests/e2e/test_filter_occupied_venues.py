"""TC-E2E-450 -- a Coordinator's date and time filter leaves out occupied
venues (S-34 reopened, manual UAT check A05).

The overlap rules are TC-FRONTEND-405 to 409 and the route is
TC-VENUEBOOKINGS-450 onward. This proves the Venues tab asks for the date's
occupied times through Kong and the list follows them.
"""

import re
import uuid
from datetime import date, timedelta

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env

EVERY_DAY = [{"day": d, "open": "08:00:00", "close": "20:00:00"}
             for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]


def test_a_coordinators_date_and_time_filter_leaves_out_occupied_venues(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    day = (date.today() + timedelta(days=12)).isoformat()
    tag = uuid.uuid4().hex[:6]
    names = {label: f"S34 {label} {tag}" for label in ("Buffer", "Held", "Blocked", "Free")}

    def venue(label, setup=0, turnaround=0):
        # Attributed to the staff member, so make_user's teardown deletes it.
        return admin.schema("venues").table("venues").insert({
            "name": names[label], "location": "10 Anson Road", "capacity": 100,
            "room_layouts": ["theatre"], "facilities": [], "accessibility": [],
            "operating_hours": EVERY_DAY, "setup_minutes": setup, "turnaround_minutes": turnaround,
            "created_by": staff["id"],
        }).execute().data[0]

    buffer, held, blocked = venue("Buffer", 30, 30), venue("Held"), venue("Blocked")
    venue("Free")
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"], "assigned_coordinator_id": coordinator["id"],
        "status": "planning", "decision": "approved",
        "decided_at": "2026-10-01T00:00:00+00:00", "submitted_at": "2026-09-30T00:00:00+00:00",
        "name": f"spm-e2e S34 Event {tag}", "purpose": "Occupied venue filter",
        "start_date": day, "start_time": "08:00", "end_date": day, "end_time": "18:00",
        "expected_attendance": 40,
    }).execute().data[0]

    def booking(where, start, end, status, **extra):
        admin.schema("bookings").table("bookings").insert({
            "event_id": event["id"], "venue_id": where["id"], "venue_name": where["name"],
            "coordinator_id": coordinator["id"], "coordinator_name": "E2E Tester",
            "coordinator_email": coordinator["email"], "booking_date": day,
            "start_time": start, "end_time": end, "event_name": event["name"],
            "event_purpose": event["purpose"], "expected_attendance": 40, "status": status, **extra,
        }).execute()

    booking(buffer, "10:00", "12:00", "confirmed", decided_by=staff["id"],
            decided_at="2026-10-01T00:00:00+00:00")
    booking(held, "12:00", "13:00", "held", held_by=staff["id"],
            held_at="2026-10-01T00:00:00+00:00", hold_expires_at="2099-01-01T04:00:00+00:00")
    admin.schema("bookings").table("blocks").insert({
        "venue_id": blocked["id"], "venue_name": blocked["name"], "start_date": day,
        "start_time": "11:00", "end_date": day, "end_time": "14:00",
        "reason": "maintenance", "created_by": staff["id"],
    }).execute()

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.get_by_role("tab", name="Venues").click()
    panel = page.locator("#panel-venues")
    panel.get_by_role("button", name=re.compile(r"^Filters")).click()

    def row(label):
        return panel.get_by_role("list", name="Venues").get_by_role("listitem").filter(has_text=names[label])

    def shows(*present):
        for label in names:
            expect(row(label)).to_have_count(1 if label in present else 0, timeout=20000)

    # 1. 12:10-12:50: inside Buffer's turnaround, Held's hold and Blocked's period.
    panel.get_by_label("Search by name or location").fill("S34 ")
    panel.get_by_label("Open on").fill(day)
    panel.get_by_label("Open from").fill("12:10")
    panel.get_by_label("Open until").fill("12:50")
    shows("Free")

    # 2. 13:00-14:00: back-to-back with Buffer and Held; Blocked runs to 14:00.
    panel.get_by_label("Open from").fill("13:00")
    panel.get_by_label("Open until").fill("14:00")
    shows("Buffer", "Held", "Free")

    # 3. Clear filters brings every venue back.
    panel.get_by_role("button", name="Clear filters").click()
    shows("Buffer", "Held", "Blocked", "Free")
    # The event is this Coordinator's own, so it is on their Events tab; the
    # Venues list must still never show it.
    expect(panel.get_by_text(event["name"])).to_have_count(0)
