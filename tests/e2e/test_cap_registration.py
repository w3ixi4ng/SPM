"""TC-E2E-254, TC-E2E-255 -- S-50: registration capped at the event's
expected attendance, with a waiting list once it is full, and the
Organiser's own decision to close registration early.

What only a browser proves: the public page swaps Register for the waiting
list, the place survives a reload, and the Organiser's close reaches the
Attendee's page through Kong."""

import re
import uuid
from datetime import datetime, timedelta, timezone

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env

SGT = timezone(timedelta(hours=8))
FULL = "This event is full. You can join the waiting list."
CLOSED_BY_ORGANISER = "The organiser has closed registration for this event."


def _now():
    return datetime.now(SGT).replace(tzinfo=None, second=0, microsecond=0)


def _confirmed_event(admin, organiser, name, *, expected_attendance):
    now = _now()
    start = now + timedelta(days=14)
    return admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "status": "confirmed",
        "name": name,
        "purpose": "Reconnect alumni with current students",
        "start_date": start.date().isoformat(),
        "start_time": "18:00",
        "end_date": start.date().isoformat(),
        "end_time": "21:00",
        "expected_attendance": expected_attendance,
        "submitted_at": "2026-10-01T00:00:00Z",
        "decision": "approved",
        "decided_at": "2026-10-02T00:00:00Z",
        "safety_decision": "approved",
        "safety_officer_id": organiser["id"],
        "safety_decided_at": "2026-10-03T00:00:00Z",
        "registration_required": True,
        "registration_opens_at": (now - timedelta(days=1)).isoformat(),
        "registration_closes_at": (now + timedelta(days=7)).isoformat(),
    }).execute().data[0]


def _sign_out(page):
    page.goto("/dashboard")
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=20000)


# --- TC-E2E-254 -----------------------------------------------------------
def test_a_full_event_turns_the_next_attendee_to_the_waiting_list(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    first = make_user("attendee")
    second = make_user("attendee")
    users = admin.schema("users").table("users")
    users.update({"name": "S-50 First Attendee"}).eq("id", first["id"]).execute()
    users.update({"name": "S-50 Second Attendee"}).eq("id", second["id"]).execute()
    event = _confirmed_event(
        admin, organiser, f"Small Workshop {uuid.uuid4().hex[:6]}", expected_attendance=1
    )
    public = f"/public/events/{event['id']}"

    sign_in(first)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    page.goto(public)
    page.get_by_role("button", name="Register").click()
    expect(page.get_by_text("You're registered for this event.")).to_be_visible(timeout=20000)
    _sign_out(page)

    sign_in(second)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    page.goto(public)
    expect(page.get_by_text(FULL)).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Register")).to_have_count(0)
    page.get_by_role("button", name="Join the waiting list").click()
    expect(page.get_by_text("You're on the waiting list.")).to_be_visible(timeout=20000)
    page.reload()
    expect(page.get_by_text("You're on the waiting list.")).to_be_visible(timeout=20000)
    _sign_out(page)

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/"), timeout=20000)
    page.goto(f"/events/{event['id']}")
    attendees = page.get_by_role("region", name="Registered attendees")
    expect(attendees.get_by_text("1 attendee registered")).to_be_visible(timeout=20000)
    expect(attendees.get_by_text("S-50 First Attendee")).to_be_visible()
    waiting = page.get_by_role("region", name="Waiting list")
    expect(waiting.get_by_text("1 person on the waiting list")).to_be_visible()
    expect(waiting.get_by_text("S-50 Second Attendee")).to_be_visible()


# --- TC-E2E-255 -----------------------------------------------------------
def test_the_organiser_closes_registration_early_and_reopens_it(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    attendee = make_user("attendee")
    event = _confirmed_event(
        admin, organiser, f"Open Day {uuid.uuid4().hex[:6]}", expected_attendance=50
    )
    public = f"/public/events/{event['id']}"

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/"), timeout=20000)
    page.goto(f"/events/{event['id']}")
    attendees = page.get_by_role("region", name="Registered attendees")
    attendees.get_by_role("button", name="Close registration").click()
    attendees.get_by_role("group", name="Confirm closing registration").get_by_role(
        "button", name="Close registration"
    ).click()
    expect(attendees.get_by_text(re.compile(
        r"^You closed registration on .+\. Attendees can't register until you reopen it\.$"
    ))).to_be_visible(timeout=20000)
    reopen = attendees.get_by_role("button", name="Reopen registration")
    expect(reopen).to_be_visible()
    _sign_out(page)

    sign_in(attendee)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    page.goto(public)
    expect(page.get_by_text(CLOSED_BY_ORGANISER)).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Register")).to_have_count(0)
    expect(page.get_by_role("button", name="Join the waiting list")).to_have_count(0)
    _sign_out(page)

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/"), timeout=20000)
    page.goto(f"/events/{event['id']}")
    page.get_by_role("region", name="Registered attendees").get_by_role(
        "button", name="Reopen registration"
    ).click()
    expect(page.get_by_role("button", name="Close registration")).to_be_visible(timeout=20000)
    _sign_out(page)

    sign_in(attendee)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    page.goto(public)
    expect(page.get_by_role("button", name="Register")).to_be_visible(timeout=20000)
