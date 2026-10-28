"""TC-E2E-257 -- S-53: a registered Attendee withdraws from the event page,
and the Attendee first on the waiting list takes the place and is told so.

What only a browser proves: the inline confirmation, the page switching from
registered to the waiting list as the freed place goes to someone else, and
both Attendees' dashboards agreeing through Kong."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env
from .test_cap_registration import _confirmed_event, _sign_out

pytestmark = requires_env

REGISTERED = "You're registered for this event."
WITHDRAWN = "You've withdrawn from this event."


# --- TC-E2E-257 -----------------------------------------------------------
def test_an_attendee_withdraws_and_the_next_in_line_gets_the_place(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    first = make_user("attendee")
    second = make_user("attendee")
    third = make_user("attendee")
    admin.schema("users").table("users").update({"name": "S-53 E2E Attendee B"}).eq(
        "id", second["id"]
    ).execute()
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
    expect(page.get_by_text(
        f"Withdraw from {name}? Your place goes to the next person on the waiting list."
    )).to_be_visible(timeout=20000)
    page.get_by_role("button", name="Keep my place").click()
    expect(page.get_by_text(REGISTERED)).to_be_visible()
    expect(page.get_by_role("button", name="Withdraw", exact=True)).to_have_count(0)

    page.get_by_role("button", name="Withdraw registration").click()
    page.get_by_role("button", name="Withdraw", exact=True).click()
    expect(page.get_by_text(WITHDRAWN)).to_be_visible(timeout=20000)
    expect(page.get_by_text(REGISTERED)).to_have_count(0)
    expect(page.get_by_role("button", name="Join the waiting list")).to_be_visible(timeout=20000)

    page.reload()
    expect(page.get_by_role("button", name="Join the waiting list")).to_be_visible(timeout=20000)
    expect(page.get_by_text(WITHDRAWN)).to_have_count(0)
    expect(page.get_by_text(REGISTERED)).to_have_count(0)
    expect(page.get_by_role("button", name="Withdraw registration")).to_have_count(0)

    page.goto("/dashboard/attendee")
    mine = page.get_by_role("region", name="Your registrations")
    expect(mine).to_be_visible(timeout=20000)
    expect(mine.get_by_role("listitem").filter(has_text=name)).to_have_count(0)
    _sign_out(page)

    sign_in(second)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    row = page.get_by_role("region", name="Your registrations").get_by_role(
        "listitem"
    ).filter(has_text=name)
    expect(row.get_by_text("Confirmed", exact=True)).to_be_visible(timeout=20000)
    inbox = page.get_by_role("region", name="Notifications")
    expect(inbox.get_by_text(
        f"A place opened up: you're now registered for {name}, "
    )).to_be_visible(timeout=20000)
    _sign_out(page)

    sign_in(third)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    page.goto(public)
    expect(page.get_by_text("You're on the waiting list. You're next in line.")).to_be_visible(
        timeout=20000
    )
