"""TC-E2E-264 -- S-55: a freed place is offered to the first Attendee on the
waiting list, who must accept it; declining passes it to the next in line.

What only a browser proves: the invitation reaching the right dashboard with a
link that leads to the event page, the held-place panel and its inline decline
confirmation, and each Attendee's dashboard agreeing through Kong."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env
from .test_cap_registration import _confirmed_event, _sign_out

pytestmark = requires_env

HELD = "A place is being held for you. Accept it to register, or decline to pass it to the next person."
REGISTERED = "You're registered for this event."


def _invitation(page, name):
    inbox = page.get_by_role("region", name="Notifications")
    return inbox.get_by_role("listitem").filter(has_text=f"A place opened up at {name}, ")


def _row(page, name):
    return page.get_by_role("region", name="Your registrations").get_by_role(
        "listitem"
    ).filter(has_text=name)


# --- TC-E2E-264 -----------------------------------------------------------
def test_a_freed_place_is_offered_to_the_first_in_line_who_must_accept_it(
    admin, page, make_user, sign_in
):
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
    for account in (second, third):
        registrations.table("waiting_list").insert(
            {"event_id": event["id"], "attendee_id": account["id"]}
        ).execute()
    public = f"/public/events/{event['id']}"

    sign_in(first)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    page.goto(public)
    page.get_by_role("button", name="Withdraw registration").click()
    page.get_by_role("button", name="Withdraw", exact=True).click()
    expect(page.get_by_text("You've withdrawn from this event.")).to_be_visible(timeout=20000)
    _sign_out(page)

    # B, first in line, is invited -- not registered.
    sign_in(second)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    expect(_row(page, name).get_by_text("Place offered", exact=True)).to_be_visible(timeout=20000)
    expect(_row(page, name).get_by_text("Confirmed", exact=True)).to_have_count(0)
    invitation = _invitation(page, name)
    expect(invitation.get_by_text(
        "It's held for you: accept it on the event page to register."
    )).to_be_visible(timeout=20000)
    invitation.get_by_role("link", name="View event").click()

    page.wait_for_url(re.compile(re.escape(public) + "$"), timeout=20000)
    expect(page.get_by_text(HELD)).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Accept place")).to_be_visible()
    expect(page.get_by_text(REGISTERED)).to_have_count(0)

    page.get_by_role("button", name="Decline", exact=True).click()
    expect(page.get_by_text("Decline this place? You'll leave the waiting list.")).to_be_visible()
    page.get_by_role("button", name="Keep my offer").click()
    expect(page.get_by_text(HELD)).to_be_visible()

    page.get_by_role("button", name="Decline", exact=True).click()
    page.get_by_role("button", name="Decline", exact=True).click()
    expect(page.get_by_text(
        "You've declined the place and left the waiting list."
    )).to_be_visible(timeout=20000)
    # The place is now held for C, so the event is still full to B.
    expect(page.get_by_role("button", name="Join the waiting list")).to_be_visible(timeout=20000)
    _sign_out(page)

    # C, next in line, is invited and takes the place.
    sign_in(third)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    expect(_row(page, name).get_by_text("Place offered", exact=True)).to_be_visible(timeout=20000)
    expect(_invitation(page, name)).to_be_visible(timeout=20000)
    page.goto(public)
    expect(page.get_by_text(HELD)).to_be_visible(timeout=20000)
    page.get_by_role("button", name="Accept place").click()
    expect(page.get_by_text(REGISTERED)).to_be_visible(timeout=20000)

    page.goto("/dashboard/attendee")
    expect(_row(page, name).get_by_text("Confirmed", exact=True)).to_be_visible(timeout=20000)
    expect(page.get_by_role("region", name="Notifications").get_by_text(
        f"Registration confirmed: {name}, "
    )).to_be_visible(timeout=20000)
