"""TC-E2E-236 -- a Coordinator changes one venue booking and cancels another;
the event's other booking is untouched (S-80).

The rules (who, which statuses, conflicts, suitability) are
TC-BOOKINGS-057..051 and TC-VENUEBOOKINGS-093..072/110's job and are not
restaged here. This proves the change screen and the cancel panel through
Kong, and that the rows on the event page reflect exactly one booking each.
"""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env

DAY = "2026-11-12"


# --- TC-E2E-236 -----------------------------------------------------------
def test_a_coordinator_changes_one_booking_and_cancels_another(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    organiser = make_user("event_organiser")
    staff = make_user("venue_staff")
    tag = uuid.uuid4().hex[:6]

    def venue(name):
        # Attributed to the staff member, so make_user's teardown deletes it.
        return admin.schema("venues").table("venues").insert({
            "name": f"spm-e2e {name} {tag}", "location": "10 Anson Road", "capacity": 300,
            "room_layouts": ["theatre"], "facilities": [],
            "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
            "created_by": staff["id"],
        }).execute().data[0]

    hall, studio = venue("Hall"), venue("Studio")
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"], "assigned_coordinator_id": coordinator["id"],
        "status": "planning", "name": f"spm-e2e Change {tag}", "purpose": "Change or cancel",
        "start_date": DAY, "start_time": "08:00", "end_date": DAY, "end_time": "18:00",
        "expected_attendance": 120, "decision": "approved",
        "decided_at": "2026-10-01T00:00:00+00:00", "submitted_at": "2026-09-30T00:00:00+00:00",
    }).execute().data[0]

    def book(where, start, end):
        return admin.schema("bookings").table("bookings").insert({
            "event_id": event["id"], "venue_id": where["id"], "coordinator_id": coordinator["id"],
            "coordinator_name": "E2E Tester", "coordinator_email": coordinator["email"],
            "booking_date": DAY, "start_time": start, "end_time": end,
            "event_name": event["name"], "event_purpose": "Change or cancel",
            "expected_attendance": 120, "venue_name": where["name"], "status": "confirmed",
            "decided_by": staff["id"], "decided_at": "2026-10-02T00:00:00+00:00",
        }).execute().data[0]

    hall_booking = book(hall, "09:00", "12:00")
    book(studio, "13:00", "15:00")

    def rows():
        return page.get_by_role("list", name="Venue requests sent").get_by_role("listitem")

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")

    # 1-2. Change the Studio booking's time.
    page.get_by_role("link", name=f"Change {studio['name']} booking").click()
    page.get_by_role("heading", name="Change venue booking").wait_for(timeout=20000)
    expect(page.get_by_label("From", exact=True)).to_have_value("13:00")
    page.get_by_label("From", exact=True).fill("15:00")
    page.get_by_label("To", exact=True).fill("17:00")
    page.get_by_role("button", name="Save changes").click()
    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}$"), timeout=20000)
    expect(page.get_by_text("Venue booking changed. It's pending until Venue Staff review it again.")).to_be_visible(timeout=20000)
    studio_row = rows().filter(has_text=studio["name"])
    expect(studio_row).to_contain_text("15:00–17:00", timeout=20000)
    expect(studio_row).to_contain_text("Pending")
    hall_row = rows().filter(has_text=hall["name"])
    expect(hall_row).to_contain_text("09:00–12:00")
    expect(hall_row).to_contain_text("Confirmed")

    # 3. Keep booking changes nothing.
    page.get_by_role("button", name=f"Cancel {hall['name']} booking").click()
    panel = page.get_by_role("dialog")
    expect(panel).to_contain_text(f"Cancel {hall['name']} on 12 Nov 2026, 09:00–12:00?", timeout=20000)
    panel.get_by_role("button", name="Keep booking").click()
    expect(panel).to_have_count(0)
    assert admin.schema("bookings").table("bookings").select("id").eq("id", hall_booking["id"]).execute().data

    # 4. Cancel booking removes the Hall booking only.
    page.get_by_role("button", name=f"Cancel {hall['name']} booking").click()
    panel.get_by_role("button", name="Cancel booking").click()
    expect(page.get_by_text("Venue booking cancelled. Its time is free for other events.")).to_be_visible(timeout=20000)

    # 5. After a reload, only the Studio booking remains.
    page.reload()
    expect(rows()).to_have_count(1, timeout=20000)
    expect(rows().first).to_contain_text(studio["name"])
    expect(rows().first).to_contain_text("15:00–17:00")
    expect(rows().first).to_contain_text("Pending")
