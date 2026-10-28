"""TC-E2E-260 and TC-E2E-261 -- S-82: the change history in a real browser,
through Kong, for the Coordinator, a Lead and the Safety Officer."""

import re
import uuid
from datetime import datetime, timedelta, timezone

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env

SGT = timezone(timedelta(hours=8))
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def today_sgt() -> str:
    now = datetime.now(SGT)
    return f"{now.day} {MONTHS[now.month - 1]} {now.year}"


def name(admin, user, display):
    admin.schema("users").table("users").update({"name": display}).eq("id", user["id"]).execute()


def planning_event(admin, organiser, coordinator, **changes):
    return admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "assigned_coordinator_id": coordinator["id"],
        "status": "planning",
        "name": f"History Forum {uuid.uuid4().hex[:6]}",
        "purpose": "Exercise the S-82 browser journey",
        "start_date": "2026-11-18", "start_time": "09:00",
        "end_date": "2026-11-18", "end_time": "12:00",
        "expected_attendance": 120,
        "decision": "approved", "decided_at": "2026-10-01T00:00:00Z",
        "submitted_at": "2026-09-30T00:00:00Z",
        **changes,
    }).execute().data[0]


def sign_out(page):
    page.goto("/dashboard")
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=20000)


def select_inventory_coordinator(page, coordinator):
    """As in the S-93 journey: on a busy shared test project the Lead's
    overview can answer "temporarily unavailable", leaving no options to
    choose. The page offers "Try again"; use it, as a Lead would."""
    selector = page.get_by_label("Event Coordinator", exact=True)
    for attempt in range(3):
        try:
            selector.select_option(coordinator["id"], timeout=7000)
            return
        except PlaywrightTimeoutError:
            retry = page.get_by_role("alert").filter(
                has_text="Coordinator oversight is temporarily unavailable"
            ).get_by_role("button", name="Try again")
            if attempt == 2 or retry.count() == 0:
                raise
            retry.click()


def history_list(page):
    history = page.get_by_role("list", name="Change history")
    expect(history).to_be_visible(timeout=20000)
    return history


# --- TC-E2E-260 -------------------------------------------------------------
def test_coordinator_and_lead_see_an_edit_in_the_history(admin, page, make_user, sign_in):
    organiser = make_user("event_organiser")
    other_lead = make_user("event_coordinator_lead")
    lead = make_user("event_coordinator_lead")
    coordinator = make_user("event_coordinator")
    name(admin, organiser, "Ada Organiser")
    name(admin, coordinator, "Alex Coordinator")
    event = planning_event(admin, organiser, coordinator, assigning_lead_id=other_lead["id"])

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    expect(page.get_by_role("heading", name=event["name"])).to_be_visible(timeout=20000)
    page.get_by_role("button", name="Edit event information").click()
    page.get_by_label("Expected attendance").fill("150")
    page.get_by_role("button", name="Review changes").click()
    page.get_by_role("alertdialog").get_by_role("button", name="Accept and save").click()
    expect(page.get_by_text("Event information saved.", exact=True)).to_be_visible(timeout=20000)

    page.get_by_role("link", name="View change history").click()
    page.wait_for_url(re.compile(rf"/events/{event['id']}/history$"), timeout=20000)
    newest = history_list(page).locator(":scope > li").first
    expect(newest).to_contain_text("Edited the event")
    expect(newest).to_contain_text("Expected attendance: 120 → 150")
    expect(newest).to_contain_text("Alex Coordinator, Event Coordinator")
    expect(newest).to_contain_text(today_sgt())
    expect(page.get_by_role("link", name="Back to event")).to_be_visible()
    expect(page.get_by_role("button")).to_have_count(0)
    expect(page.get_by_role("textbox")).to_have_count(0)

    sign_out(page)
    sign_in(lead)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator-lead$"), timeout=20000)
    select_inventory_coordinator(page, coordinator)
    inventory = page.get_by_role("list", name="Selected Coordinator active events")
    inventory.get_by_role("link", name=f"Change history for {event['name']}").click(timeout=20000)
    page.wait_for_url(re.compile(rf"/events/{event['id']}/history$"), timeout=20000)
    newest = history_list(page).locator(":scope > li").first
    expect(newest).to_contain_text("Edited the event")
    expect(newest).to_contain_text("Expected attendance: 120 → 150")
    expect(newest).to_contain_text("Alex Coordinator, Event Coordinator")

    sign_out(page)
    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    page.goto(f"/events/{event['id']}/history")
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    expect(page.get_by_role("list", name="Change history")).to_have_count(0)


# --- TC-E2E-261 -------------------------------------------------------------
def test_safety_officer_sees_only_the_safety_history(admin, page, make_user, sign_in):
    organiser = make_user("event_organiser")
    lead = make_user("event_coordinator_lead")
    coordinator = make_user("event_coordinator")
    officer = make_user("safety_officer")
    name(admin, coordinator, "Alex Coordinator")
    name(admin, officer, "Sam Safety")
    event = planning_event(admin, organiser, coordinator, status="pending_safety_check")
    admin.schema("events").table("event_history").insert([
        {"event_id": event["id"], "actor_id": lead["id"], "actor_role": "event_coordinator_lead",
         "category": "assignment", "action": "coordinator_assigned",
         "details": {"coordinator_id": coordinator["id"]}, "occurred_at": "2026-10-01T01:00:00Z"},
        {"event_id": event["id"], "actor_id": coordinator["id"], "actor_role": "event_coordinator",
         "category": "edit", "action": "edited", "occurred_at": "2026-10-02T01:00:00Z",
         "details": {"changes": {"contact_phone": {"before": None, "after": "91234567"}}, "significant": False}},
        {"event_id": event["id"], "actor_id": coordinator["id"], "actor_role": "event_coordinator",
         "category": "edit", "action": "edited", "occurred_at": "2026-10-03T01:00:00Z",
         "details": {"changes": {"expected_attendance": {"before": 120, "after": 150}}, "significant": True}},
    ]).execute()

    sign_in(officer)
    page.wait_for_url(re.compile(r"/dashboard/safety-officer$"), timeout=20000)
    page.goto(f"/safety-checks/{event['id']}")
    expect(page.get_by_role("heading", name=event["name"])).to_be_visible(timeout=20000)
    page.get_by_role("radio", name="Request changes").check()
    page.get_by_label("Reason (required)").fill("Fire exit blocked")
    page.get_by_role("button", name="Record safety decision").click()
    expect(page.get_by_role("status")).to_contain_text("Operational safety decision recorded", timeout=20000)

    page.get_by_role("link", name="View change history").click()
    page.wait_for_url(re.compile(rf"/events/{event['id']}/history$"), timeout=20000)
    rows = history_list(page).locator(":scope > li")
    expect(rows).to_have_count(2, timeout=20000)
    expect(rows.nth(0)).to_contain_text("Requested safety changes: Fire exit blocked")
    expect(rows.nth(0)).to_contain_text("Sam Safety, Safety Officer")
    expect(rows.nth(1)).to_contain_text("Expected attendance: 120 → 150")
    expect(page.get_by_text("Contact phone", exact=False)).to_have_count(0)
    expect(page.get_by_text("Assigned", exact=False)).to_have_count(0)
    expect(page.get_by_role("link", name="Back to safety checks")).to_be_visible()
