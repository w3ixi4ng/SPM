"""TC-E2E-255 -- S-52: an Attendee on a full event's waiting list sees their
place in line, and their dashboard marks the event as waiting, not confirmed.

What only a browser proves: the place survives a reload through Kong, and the
dashboard row and the event page agree on it."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env
from .test_cap_registration import _confirmed_event, _sign_out

pytestmark = requires_env

PLACE = "You're on the waiting list. You're 2nd in line."


def _dashboard_row(page, name):
    registrations = page.get_by_role("region", name="Your registrations")
    return registrations.get_by_role("listitem").filter(has_text=name)


# --- TC-E2E-255 -----------------------------------------------------------
def test_a_waitlisted_attendee_sees_their_place_in_line(admin, page, make_user, sign_in):
    organiser = make_user("event_organiser")
    first = make_user("attendee")
    second = make_user("attendee")
    third = make_user("attendee")
    name = f"Small Workshop {uuid.uuid4().hex[:6]}"
    event = _confirmed_event(admin, organiser, name, expected_attendance=1)
    registrations = admin.schema("registrations")
    registrations.table("registrations").insert(
        {"event_id": event["id"], "attendee_id": first["id"]}
    ).execute()
    registrations.table("waiting_list").insert(
        {"event_id": event["id"], "attendee_id": second["id"]}
    ).execute()
    public = f"/public/events/{event['id']}"

    sign_in(third)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    page.goto(public)
    page.get_by_role("button", name="Join the waiting list").click()
    expect(page.get_by_text(PLACE)).to_be_visible(timeout=20000)
    page.reload()
    expect(page.get_by_text(PLACE)).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Register")).to_have_count(0)
    expect(page.get_by_text("You're registered for this event.")).to_have_count(0)

    page.goto("/dashboard/attendee")
    row = _dashboard_row(page, name)
    expect(row.get_by_text("Waiting list · 2nd in line")).to_be_visible(timeout=20000)
    expect(row.get_by_text("Confirmed")).to_have_count(0)
    _sign_out(page)

    sign_in(first)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    expect(_dashboard_row(page, name).get_by_text("Confirmed")).to_be_visible(timeout=20000)
