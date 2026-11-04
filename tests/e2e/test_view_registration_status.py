"""TC-E2E-268 -- S-58: an Attendee sees their registration status, kept current.

What only a browser proves: the dashboard's row for one event follows the
Attendee from Confirmed to Withdrawn and back, staying a single row. The
waiting-list and offered rows are proven by TC-E2E-255 and TC-E2E-264."""

import re
import uuid
from datetime import datetime, timedelta, timezone

from playwright.sync_api import expect

from .conftest import requires_env
from .test_cap_registration import _confirmed_event

pytestmark = requires_env

SGT = timezone(timedelta(hours=8))
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def sgt_today() -> str:
    """Today in Singapore, as the dashboard writes it: "30 Oct 2026"."""
    today = datetime.now(SGT)
    return f"{today.day} {MONTHS[today.month - 1]} {today.year}"


# --- TC-E2E-268 -----------------------------------------------------------
def test_the_dashboard_shows_a_withdrawal_then_the_place_again(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    attendee = make_user("attendee")
    name = f"Status Workshop {uuid.uuid4().hex[:6]}"
    event = _confirmed_event(admin, organiser, name, expected_attendance=5)
    admin.schema("registrations").table("registrations").insert(
        {"event_id": event["id"], "attendee_id": attendee["id"]}
    ).execute()
    public = f"/public/events/{event['id']}"

    def row():
        page.goto("/dashboard/attendee")
        mine = page.get_by_role("region", name="Your registrations")
        expect(mine).to_be_visible(timeout=20000)
        found = mine.get_by_role("listitem").filter(has_text=name)
        expect(found).to_have_count(1, timeout=20000)
        return found

    sign_in(attendee)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    expect(row()).to_contain_text("Confirmed")

    page.goto(public)
    page.get_by_role("button", name="Withdraw registration").click()
    page.get_by_role("button", name="Withdraw", exact=True).click()
    expect(page.get_by_text("You've withdrawn from this event.")).to_be_visible(timeout=20000)

    withdrawn = row()
    expect(withdrawn).to_contain_text(f"Withdrawn on {sgt_today()}")
    expect(withdrawn).not_to_contain_text("Confirmed")
    expect(withdrawn.get_by_role("link", name=name)).to_have_attribute("href", public)

    page.goto(public)
    page.get_by_role("button", name="Register").click()
    expect(page.get_by_text("You're registered for this event.")).to_be_visible(timeout=20000)

    again = row()
    expect(again).to_contain_text("Confirmed")
    expect(again).not_to_contain_text("Withdrawn")
