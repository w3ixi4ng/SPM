"""S-93: a Lead sees an inactive Coordinator's work across Lead scopes."""

import re
import uuid

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .conftest import requires_env

pytestmark = requires_env


def test_leads_clear_only_their_inactive_coordinator_assignments(page, make_user, sign_in, admin):
    organiser = make_user("event_organiser")
    first_lead = make_user("event_coordinator_lead")
    second_lead = make_user("event_coordinator_lead")
    former = make_user("event_coordinator")
    replacement = make_user("event_coordinator")
    officer = make_user("safety_officer")
    for user, name in ((former, "S93 Former"), (replacement, "S93 Replacement")):
        admin.schema("users").table("users").update({"name": name}).eq("id", user["id"]).execute()
    admin.auth.admin.update_user_by_id(former["id"], {
        "app_metadata": {"role": "event_coordinator", "coordinator_active": False},
    })
    suffix = uuid.uuid4().hex[:8]
    first_name, second_name = f"S93 Safety Pending {suffix}", f"S93 Preparation {suffix}"

    def seed(name, lead_id, status, day):
        values = {
            "organiser_id": organiser["id"], "assigned_coordinator_id": former["id"],
            "assigning_lead_id": lead_id, "status": status, "name": name,
            "purpose": "S-93 cross-Lead inventory journey", "start_date": day,
            "start_time": "09:00", "end_date": day, "end_time": "12:00",
            "expected_attendance": 40, "submitted_at": "2026-10-01T00:00:00Z",
            "decision": "approved", "decided_at": "2026-10-02T00:00:00Z",
        }
        if status == "preparation":
            values.update({
                "safety_decision": "approved", "safety_officer_id": officer["id"],
                "safety_decided_at": "2026-10-03T00:00:00Z",
            })
        return admin.schema("events").table("events").insert(values).execute().data[0]

    seed(first_name, first_lead["id"], "pending_safety_check", "2026-11-18")
    seed(second_name, second_lead["id"], "preparation", "2026-11-20")

    def select_former():
        selector = page.get_by_label("Event Coordinator", exact=True)
        for attempt in range(3):
            try:
                selector.select_option(former["id"], timeout=7000)
                break
            except PlaywrightTimeoutError:
                retry = page.get_by_role("alert").filter(
                    has_text="Coordinator oversight is temporarily unavailable"
                ).get_by_role("button", name="Try again")
                if attempt == 2 or retry.count() == 0:
                    raise
                retry.click()
        return page.get_by_role("list", name="Selected Coordinator active events")

    sign_in(first_lead)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator-lead$"), timeout=20000)
    inventory = select_former()
    page.get_by_text("2 active events", exact=True).wait_for(timeout=20000)
    page.get_by_role("alert").filter(has_text="Inactive Coordinator has 2 active events").wait_for()
    own = inventory.get_by_role("listitem").filter(has_text=first_name)
    other = inventory.get_by_role("listitem").filter(has_text=second_name)
    other.get_by_text("Read-only", exact=False).wait_for()
    assert other.get_by_role("button", name="Reassign event").count() == 0
    own.get_by_label(f"New Event Coordinator for {first_name}").select_option(replacement["id"])
    own.get_by_role("button", name="Reassign event").click()
    page.get_by_text("1 active event", exact=True).wait_for(timeout=30000)
    inventory.get_by_text(second_name, exact=True).wait_for()

    sign_in(second_lead)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator-lead$"), timeout=20000)
    inventory = select_former()
    page.get_by_text("1 active event", exact=True).wait_for(timeout=20000)
    remaining = inventory.get_by_role("listitem").filter(has_text=second_name)
    remaining.get_by_label(f"New Event Coordinator for {second_name}").select_option(replacement["id"])
    remaining.get_by_role("button", name="Reassign event").click()
    page.get_by_text("0 active events", exact=True).wait_for(timeout=30000)
    assert page.get_by_role("alert").filter(has_text="Inactive Coordinator has").count() == 0
