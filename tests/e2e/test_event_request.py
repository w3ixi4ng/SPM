"""TC-E2E-203 -- an organiser files an event request and sees it listed.

The product's actual path: browser -> Kong -> events service -> the `events`
schema, gated by the `events:create` permission, and back out through the
dashboard's list. Nothing else in the suite crosses all of that.

Since S-12, submission also crosses the event_requests composite and the
users service, to assign a coordinator -- hence the seeded coordinator
account below. Without at least one, submission now 409s.
"""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


def _pick_date(page, trigger: str, day: str = "15") -> None:
    """Choose a day from the custom calendar popover.

    Next month rather than this one: the picker disables days before today, so
    a fixed day number is only always selectable a month ahead.
    """
    page.click(trigger)
    dialog = page.get_by_role("dialog", name="Choose a date")
    dialog.get_by_role("button", name="Next month").click()
    dialog.get_by_role("button", name=day, exact=True).click()


def _pick_time(page, trigger: str, label: str) -> None:
    """Choose a time from the custom listbox popover, by its displayed label."""
    page.click(trigger)
    page.get_by_role("listbox", name="Choose a time").get_by_role(
        "option", name=label, exact=True
    ).click()


# --- TC-E2E-203 -----------------------------------------------------------
def test_organiser_submits_an_event_request_and_sees_it_listed(
    page, make_user, sign_in
):
    # A free event coordinator has to exist, or submission below 409s -- see
    # S-12: it is a routing precondition, not something the organiser's own
    # session can satisfy.
    make_user("event_coordinator")

    user = make_user("event_organiser")
    sign_in(user)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)

    name = f"E2E Launch {uuid.uuid4().hex[:6]}"

    page.goto("/events/new")
    page.fill("#event-name", name)
    page.fill("#event-purpose", "Proving the path from browser to database.")

    # Same day, so the form's "end after start" rule applies to the times.
    _pick_date(page, "#event-start-date")
    _pick_time(page, "#event-start-time", "9:00 AM")
    _pick_date(page, "#event-end-date")
    _pick_time(page, "#event-end-time", "11:00 AM")

    page.fill("#event-attendance", "40")
    page.fill("#event-venue", "Hall A")

    page.get_by_role("button", name="Submit request").click()

    # The organiser is told it worked. The acceptance criterion asks for a
    # clear indication, and a silent redirect is not one.
    page.get_by_text("Request submitted.").wait_for(timeout=30000)

    # A submitted request redirects to its own page, which is the first proof
    # the events service accepted it and gave it an id.
    page.wait_for_url(re.compile(r"/events/[0-9a-f-]{36}$"), timeout=30000)

    # And it is really stored, not just echoed back: a fresh load of the
    # dashboard reads it from the events service.
    page.goto("/dashboard/event-organiser")
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    page.get_by_text(name, exact=True).wait_for(timeout=20000)

    # And it reads as submitted rather than draft -- the list is where the two
    # are meant to be told apart at a glance.
    page.get_by_text("submitted", exact=False).first.wait_for(timeout=20000)
