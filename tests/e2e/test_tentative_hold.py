"""TC-E2E-223/224 -- explicit tentative holds and automatic release (S-33).

S-79: a second request for the same event no longer replaces the first, so
TC-E2E-223 now checks the hold survives it.
"""

import re
import uuid

import pytest
from playwright.sync_api import expect

from .conftest import open_request, requires_env
from .test_venue_availability import add_event, add_venue, d, day_cell, day_detail, open_calendar, show_month

pytestmark = requires_env


def add_booking(admin, event, venue, coordinator, *, start="09:00", end="12:00", status="pending", staff=None):
    row = {
        "event_id": event["id"], "venue_id": venue["id"],
        "coordinator_id": coordinator["id"], "coordinator_name": "E2E Tester",
        "coordinator_email": coordinator["email"], "booking_date": d(5).isoformat(),
        "start_time": start, "end_time": end, "event_name": event["name"],
        "event_purpose": event["purpose"], "expected_attendance": 40,
        "venue_name": venue["name"], "status": status,
    }
    if status == "held":
        row.update(held_by=staff["id"], held_at="2026-10-01T00:00:00+00:00")
    return admin.schema("bookings").table("bookings").insert(row).execute().data[0]


def booking_row(page, event_name):
    return page.get_by_role("list", name="Pending booking requests").get_by_role(
        "listitem"
    ).filter(has_text=event_name)


def test_tentative_hold_is_distinct_and_a_second_request_keeps_it(
    admin, page, make_user, sign_in
):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    venue = add_venue(admin, staff, uuid.uuid4().hex[:6])
    event = add_event(admin, organiser, coordinator, "S33", d(5))
    original = add_booking(admin, event, venue, coordinator)

    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    # S-75: the hold is placed on the request's own page.
    open_request(page, event["name"])
    page.get_by_role("button", name="Place hold").click()
    expect(page.get_by_role("button", name="Release hold")).to_be_visible(timeout=20000)
    expect(page.get_by_text("Tentatively held").first).to_be_visible()

    open_calendar(page, venue["name"], "/dashboard/venue-staff")
    show_month(page, d(5))
    day_cell(page, d(5)).click()
    expect(day_detail(page, d(5))).to_contain_text("Tentatively held 09:00–12:00", timeout=20000)

    page.get_by_role("link", name="Back to dashboard").click()
    page.get_by_role("button", name="Sign out").click()
    # The logout request clears server-side cookies before redirecting. CI is
    # slower than a local browser, so do not start the next login while that
    # request is still in flight.
    page.wait_for_url(re.compile(r"/login$"), timeout=30000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=30000)
    page.goto(f"/coordinator/events/{event['id']}/request-venue")
    venue_row = page.get_by_role("list", name="Venues").get_by_role("listitem").filter(
        has_text=venue["name"]
    )
    venue_row.get_by_role("radio").check()
    page.get_by_label("Date", exact=True).fill(d(5).isoformat())
    page.get_by_label("From", exact=True).fill("13:00")
    page.get_by_label("To", exact=True).fill("16:00")
    page.get_by_role("button", name="Send request").click()
    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}$"), timeout=20000)

    stored = admin.schema("bookings").table("bookings").select(
        "id,status,hold_release_reason"
    ).eq("id", original["id"]).execute().data[0]
    assert stored == {"id": original["id"], "status": "held", "hold_release_reason": None}


@pytest.mark.parametrize("terminal_status", ["rejected", "cancelled"])
def test_terminal_event_releases_hold_when_staff_refreshes(
    admin, page, make_user, sign_in, terminal_status
):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    venue = add_venue(admin, staff, uuid.uuid4().hex[:6])
    event = add_event(admin, organiser, coordinator, f"S33 {terminal_status}", d(5))
    held = add_booking(admin, event, venue, coordinator, status="held", staff=staff)

    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    expect(booking_row(page, event["name"])).to_contain_text("Tentatively held", timeout=20000)

    admin.schema("events").table("events").update({"status": terminal_status}).eq(
        "id", event["id"]
    ).execute()
    with page.expect_response(
        lambda response: "/api/venue-bookings/pending" in response.url
        and response.request.method == "GET",
        timeout=20000,
    ):
        page.reload()
    expect(booking_row(page, event["name"])).to_have_count(0, timeout=20000)

    stored = admin.schema("bookings").table("bookings").select(
        "status,hold_release_reason,hold_released_at"
    ).eq("id", held["id"]).execute().data[0]
    assert stored["status"] == "pending"
    assert stored["hold_release_reason"] == f"event_{terminal_status}"
    assert stored["hold_released_at"] is not None

    open_calendar(page, venue["name"], "/dashboard/venue-staff")
    show_month(page, d(5))
    day_cell(page, d(5)).click()
    expect(day_detail(page, d(5))).to_contain_text("Available", timeout=20000)
