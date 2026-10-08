"""TC-E2E-229 -- manual Lead assignment and persistent notifications."""

import re
import uuid

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


# --- TC-E2E-229 -----------------------------------------------------------
def test_lead_assigns_request_and_both_recipients_are_notified(
    page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    lead = make_user("event_coordinator_lead")
    coordinator = make_user("event_coordinator")
    unrelated = make_user("attendee")
    event_name = f"Autumn Forum {uuid.uuid4().hex[:6]}"

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    page.get_by_role("link", name="Create event request").click()
    page.get_by_label("Event name").fill(event_name)
    page.get_by_label("Purpose").fill("Bring the community together")
    _choose_date(page, "Start date", 2026, 10, 18)
    _choose_time(page, "Start time", "9:00 AM")
    _choose_date(page, "End date", 2026, 10, 18)
    _choose_time(page, "End time", "12:00 PM")
    page.get_by_label("Expected attendance").fill("120")
    page.get_by_role("button", name="Submit request").click()
    page.get_by_text("Request submitted.").wait_for(timeout=30000)

    page.goto("/dashboard/event-organiser")
    request_link = page.get_by_role("link").filter(has_text=event_name)
    request_link.get_by_text("Under review").wait_for(timeout=20000)
    page.get_by_role("button", name="Sign out").click()

    sign_in(lead)
    page.wait_for_url(
        re.compile(r"/dashboard/event-coordinator-lead$"), timeout=20000
    )
    card = page.get_by_role("listitem").filter(has_text=event_name)
    card.get_by_text("Expected attendance: 120").wait_for(timeout=20000)
    card.get_by_label(f"Event Coordinator for {event_name}").select_option(
        coordinator["id"]
    )
    card.get_by_role("button", name="Assign request").click()
    page.get_by_text(re.compile(rf"{re.escape(event_name)} was assigned")).wait_for(
        timeout=30000
    )
    assert card.count() == 0
    page.get_by_role("button", name="Sign out").click()

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    coordinator_message = f"You have been assigned to {event_name}."
    page.get_by_text(coordinator_message, exact=True).wait_for(timeout=20000)
    page.get_by_role("tab", name="Events").click()
    page.get_by_text(event_name, exact=True).wait_for(timeout=20000)
    page.reload()
    page.get_by_text(coordinator_message, exact=True).wait_for(timeout=20000)
    page.get_by_role("button", name="Sign out").click()

    sign_in(organiser)
    organiser_message = f"E2E Tester has been assigned to {event_name}."
    page.get_by_text(organiser_message, exact=True).wait_for(timeout=20000)
    page.reload()
    page.get_by_text(organiser_message, exact=True).wait_for(timeout=20000)
    page.get_by_role("button", name="Sign out").click()

    sign_in(unrelated)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    inbox = page.context.request.get("/api/notifications")
    assert inbox.status == 200
    assert all(row["event_name"] != event_name for row in inbox.json())
