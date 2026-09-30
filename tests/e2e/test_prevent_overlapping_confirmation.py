"""TC-E2E-218: a confirmed venue slot blocks an overlapping confirmation."""
import re
import uuid

import pytest
from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


@pytest.mark.skip(reason="TC-E2E-218 is superseded by S-30: two overlapping pending requests can no "
                         "longer exist. TC-E2E-221 covers the refusal at submission.")
def test_confirmed_venue_time_becomes_unavailable_to_another_event(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    venue_name = f"spm-e2e S38 Venue {suffix}"
    venue_id = str(uuid.uuid4())

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

    first = pending.get_by_role("listitem").filter(has_text=events[0]["name"])
    first.get_by_role("radio", name="Approve", exact=True).check()
    first.get_by_role("button", name="Save decision").click()
    expect(first).to_have_count(0, timeout=20000)

    second = pending.get_by_role("listitem").filter(has_text=events[1]["name"])
    second.get_by_role("radio", name="Approve", exact=True).check()
    second.get_by_role("button", name="Save decision").click()
    expect(second.get_by_role("alert")).to_contain_text(
        f"{venue_name} is already confirmed on 12 Nov 2026 from 09:00 to 12:00",
        timeout=20000,
    )
    page.reload()
    expect(pending.get_by_role("listitem").filter(has_text=events[1]["name"])).to_be_visible(timeout=20000)

    page.get_by_role("button", name="Sign out").click()
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{events[0]['id']}")
    expect(page.get_by_role("list", name="Venue requests sent")).to_contain_text("Confirmed", timeout=20000)
    page.goto(f"/coordinator/events/{events[1]['id']}")
    expect(page.get_by_role("list", name="Venue requests sent")).to_contain_text("Pending", timeout=20000)

    rows = admin.schema("bookings").table("bookings").select("id,status").in_(
        "id", [booking["id"] for booking in bookings]
    ).execute().data
    assert sorted(row["status"] for row in rows) == ["confirmed", "pending"]
