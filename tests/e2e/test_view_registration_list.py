"""TC-E2E-265, 266 -- S-57: the Organiser, and the event's assigned
Coordinator, see who is currently registered.

What only a browser proves: Refresh list re-reads the list without a page
load, and the Coordinator's page shows the list -- without the Organiser's
close control -- because frontend and composite agree on who may see it.
Access rules and withdrawals themselves are TC-EVENTREGISTRATIONS-062..065
and -109."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env
from .test_cap_registration import _confirmed_event

pytestmark = requires_env


def _withdraw_elsewhere(browser, base_url, account, event_id):
    """The Attendee withdraws in their own browser session while the
    viewer's page stays open."""
    context = browser.new_context(base_url=base_url)
    try:
        other = context.new_page()
        other.goto("/login")
        other.fill("input[name=email]", account["email"])
        other.fill("input[name=password]", account["password"])
        other.click("button[type=submit]")
        other.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
        withdrawn = context.request.delete(
            f"/api/event-registrations/events/{event_id}/registration"
        )
        assert withdrawn.status == 200, withdrawn.text()
    finally:
        context.close()


def _attendee(admin, make_user, name):
    account = make_user("attendee")
    admin.schema("users").table("users").update({"name": name}).eq(
        "id", account["id"]
    ).execute()
    return account


# --- TC-E2E-265 -----------------------------------------------------------
def test_the_organiser_refreshes_the_list_after_withdrawals(
    admin, page, browser, base_url, make_user, sign_in
):
    organiser = make_user("event_organiser")
    first = _attendee(admin, make_user, "S-57 E2E Attendee A")
    second = _attendee(admin, make_user, "S-57 E2E Attendee B")
    event = _confirmed_event(
        admin, organiser, f"Alumni evening {uuid.uuid4().hex[:6]}", expected_attendance=5
    )
    for account in (first, second):
        admin.schema("registrations").table("registrations").insert(
            {"event_id": event["id"], "attendee_id": account["id"]}
        ).execute()
    event_page = f"/events/{event['id']}"

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/"), timeout=20000)
    page.goto(event_page)
    attendees = page.get_by_role("region", name="Registered attendees")
    expect(attendees.get_by_text("2 attendees registered")).to_be_visible(timeout=20000)
    expect(attendees.get_by_text("S-57 E2E Attendee A")).to_be_visible()
    expect(attendees.get_by_text(first["email"])).to_be_visible()
    expect(attendees.get_by_text("S-57 E2E Attendee B")).to_be_visible()
    expect(attendees.get_by_text(second["email"])).to_be_visible()

    # Marks this page load: a navigation would discard it.
    page.evaluate("window.__s57_same_page = true")

    _withdraw_elsewhere(browser, base_url, first, event["id"])
    attendees.get_by_role("button", name="Refresh list").click()
    expect(attendees.get_by_text("1 attendee registered")).to_be_visible(timeout=20000)
    expect(attendees.get_by_text("S-57 E2E Attendee B")).to_be_visible()
    expect(page.get_by_text("S-57 E2E Attendee A")).to_have_count(0)

    _withdraw_elsewhere(browser, base_url, second, event["id"])
    attendees.get_by_role("button", name="Refresh list").click()
    expect(attendees.get_by_text("No one is currently registered for this event.")).to_be_visible(
        timeout=20000
    )
    expect(page.get_by_text("S-57 E2E Attendee B")).to_have_count(0)

    assert page.url.endswith(event_page)
    assert page.evaluate("window.__s57_same_page") is True


# --- TC-E2E-266 -----------------------------------------------------------
def test_the_assigned_coordinator_sees_the_registration_list(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    first = _attendee(admin, make_user, "S-57 E2E Attendee A")
    event = _confirmed_event(
        admin, organiser, f"Alumni evening {uuid.uuid4().hex[:6]}", expected_attendance=5
    )
    admin.schema("events").table("events").update(
        {"assigned_coordinator_id": coordinator["id"]}
    ).eq("id", event["id"]).execute()
    admin.schema("registrations").table("registrations").insert(
        {"event_id": event["id"], "attendee_id": first["id"]}
    ).execute()

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    attendees = page.get_by_role("region", name="Registered attendees")
    expect(attendees.get_by_text("1 attendee registered")).to_be_visible(timeout=20000)
    expect(attendees.get_by_text("S-57 E2E Attendee A")).to_be_visible()
    expect(attendees.get_by_text(first["email"])).to_be_visible()
    expect(attendees.get_by_role("button", name="Refresh list")).to_be_visible()
    expect(page.get_by_role("button", name="Close registration")).to_have_count(0)
