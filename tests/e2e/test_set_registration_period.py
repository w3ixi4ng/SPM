"""TC-E2E-246 -- S-51: the Organiser turns registration on and sets its
period while writing the request, and it is fixed once submitted.

What only a browser proves: the toggle and the period pickers send what
the events service expects, the page refuses a period that closes after the
event starts, and a submitted request shows the period with no control to
change it."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def _choose_date(page, label, year, month_index, day):
    page.get_by_label(label).click()
    picker = page.get_by_role("dialog", name="Choose a date")
    picker.get_by_label("Month", exact=True).select_option(str(month_index))
    picker.get_by_label("Year", exact=True).select_option(str(year))
    picker.get_by_role("button", name=str(day), exact=True).click()


def _choose_time(page, label, displayed_time):
    page.get_by_label(label).click()
    page.get_by_role("option", name=displayed_time, exact=True).click()


# --- TC-E2E-246 -----------------------------------------------------------
def test_organiser_sets_a_registration_period_fixed_once_submitted(page, make_user, sign_in):
    organiser = make_user("event_organiser")
    make_user("event_coordinator")
    event_name = f"Registration Evening {uuid.uuid4().hex[:6]}"

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    page.get_by_role("link", name="Create event request").click()
    page.get_by_label("Event name").fill(event_name)
    page.get_by_label("Purpose").fill("Bring alumni and students together")
    _choose_date(page, "Start date", 2026, 11, 10)
    _choose_time(page, "Start time", "6:00 PM")
    _choose_date(page, "End date", 2026, 11, 10)
    _choose_time(page, "End time", "9:00 PM")
    page.get_by_label("Expected attendance").fill("120")

    page.get_by_label("Attendees register for this event").check()
    _choose_date(page, "Registration opening date", 2026, 10, 1)
    _choose_time(page, "Registration opening time", "9:00 AM")
    _choose_date(page, "Registration closing date", 2026, 11, 10)
    _choose_time(page, "Registration closing time", "7:00 PM")
    page.get_by_role("button", name="Submit request").click()
    expect(page.get_by_text("Registration must close before the event starts.")).to_be_visible(
        timeout=20000
    )
    expect(page).to_have_url(re.compile(r"/events/new$"))

    _choose_date(page, "Registration closing date", 2026, 11, 5)
    _choose_time(page, "Registration closing time", "6:00 PM")
    page.get_by_role("button", name="Submit request").click()
    page.get_by_text("Request submitted.").wait_for(timeout=30000)

    page.reload()
    expect(
        page.get_by_text("Registration opens 1 Nov 2026, 9:00 am and closes 5 Dec 2026, 6:00 pm.")
    ).to_be_visible(timeout=20000)
    expect(page.get_by_label("Attendees register for this event")).to_have_count(0)
    expect(page.get_by_label("Registration closing date")).to_have_count(0)
