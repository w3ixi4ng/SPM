"""TC-E2E-218: a confirmed venue slot blocks an overlapping confirmation."""
import re
import uuid

from playwright.sync_api import expect

from .conftest import open_request, requires_env

pytestmark = requires_env


def test_confirmed_venue_time_becomes_unavailable_to_another_event(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    venue_name = f"spm-e2e S38 Venue {suffix}"
    # A real venue: since S-75 a confirmation reads the venue's setup and
    # turnaround. Attributed to the staff member, so make_user's teardown
    # deletes it.
    venue_id = admin.schema("venues").table("venues").insert({
        "name": venue_name, "location": "10 Anson Road", "capacity": 150,
        "room_layouts": ["theatre"], "facilities": [], "accessibility": [],
        "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
        "created_by": staff["id"],
    }).execute().data[0]["id"]

    events = []
    bookings = []
    for label, start, end in (("A", "09:00", "12:00"), ("B", "11:00", "13:00")):
        event = admin.schema("events").table("events").insert({
            "organiser_id": organiser["id"],
            "assigned_coordinator_id": coordinator["id"],
            "status": "planning",
            "decision": "approved",
            "decided_at": "2026-10-01T00:00:00+00:00",
            "submitted_at": "2026-09-30T00:00:00+00:00",
            "name": f"spm-e2e S38 Event {label} {suffix}",
            "purpose": "Overlap confirmation testing",
            "start_date": "2026-11-12",
            "start_time": "08:00",
            "end_date": "2026-11-12",
            "end_time": "18:00",
            "expected_attendance": 40,
        }).execute().data[0]
        events.append(event)
        bookings.append(admin.schema("bookings").table("bookings").insert({
            "event_id": event["id"],
            "venue_id": venue_id,
            "coordinator_id": coordinator["id"],
            "coordinator_name": "E2E Tester",
            "coordinator_email": coordinator["email"],
            "booking_date": "2026-11-12",
            "start_time": start,
            "end_time": end,
            "event_name": event["name"],
            "event_purpose": event["purpose"],
            "expected_attendance": 40,
            "venue_name": venue_name,
        }).execute().data[0])

    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    pending = page.get_by_role("list", name="Pending booking requests")

    # S-75: each request is decided on its own page, opened from its row.
    open_request(page, events[0]["name"])
    page.get_by_role("radio", name="Approve", exact=True).check()
    page.get_by_role("button", name="Save decision").click()
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    expect(pending.get_by_role("link").filter(has_text=events[0]["name"])).to_have_count(0, timeout=20000)

    open_request(page, events[1]["name"])
    page.get_by_role("radio", name="Approve", exact=True).check()
    page.get_by_role("button", name="Save decision").click()
    # S-76's wording, which replaced S-38's: the booking in the way and when
    # it occupies the venue (setup and turnaround are 0 here).
    expect(page.get_by_role("alert").filter(has_text="Can't confirm this booking")).to_contain_text(
        f"it overlaps {events[0]['name']} (confirmed), which occupies {venue_name} "
        "on 12 Nov 2026 from 09:00 to 12:00",
        timeout=20000,
    )
    page.reload()
    page.get_by_role("link", name="Back to dashboard").click()
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    expect(pending.get_by_role("link").filter(has_text=events[1]["name"])).to_be_visible(timeout=20000)

    page.get_by_role("button", name="Sign out").click()
    # Sign out clears the cookie asynchronously. Finish that transition
    # before signing in as another user and doing a hard page navigation.
    page.wait_for_url(re.compile(r"/login$"), timeout=20000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{events[0]['id']}")
    page.wait_for_url(re.compile(rf"/coordinator/events/{events[0]['id']}$"), timeout=20000)
    expect(page.get_by_role("list", name="Venue requests sent")).to_contain_text("Confirmed", timeout=20000)
    page.goto(f"/coordinator/events/{events[1]['id']}")
    page.wait_for_url(re.compile(rf"/coordinator/events/{events[1]['id']}$"), timeout=20000)
    expect(page.get_by_role("list", name="Venue requests sent")).to_contain_text("Pending", timeout=20000)

    rows = admin.schema("bookings").table("bookings").select("id,status").in_(
        "id", [booking["id"] for booking in bookings]
    ).execute().data
    assert sorted(row["status"] for row in rows) == ["confirmed", "pending"]
