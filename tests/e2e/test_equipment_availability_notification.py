"""TC-E2E-267: equipment becomes unavailable and its Coordinator is told."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def test_support_makes_equipment_unavailable_and_the_coordinator_is_told(
    admin, page, make_user, sign_in
):
    coordinator = make_user("event_coordinator")
    support = make_user("technical_support")
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    event_name = f"S-71 Confirmed Forum {suffix}"
    equipment_name = f"S-71 Projector {suffix}"
    equipment = admin.schema("equipment").table("equipment").insert(
        {
            "type": equipment_name,
            "description": "Needed by the confirmed event",
            "total_quantity": 3,
            "operational_status": "available",
            "lifecycle_status": "active",
            "created_by": support["id"],
        }
    ).execute().data[0]
    event = admin.schema("events").table("events").insert(
        {
            "organiser_id": organiser["id"],
            "assigned_coordinator_id": coordinator["id"],
            "status": "confirmed",
            "name": event_name,
            "purpose": "Prove the S-71 browser journey",
            "start_date": "2026-12-12",
            "start_time": "09:00",
            "end_date": "2026-12-12",
            "end_time": "12:00",
            "expected_attendance": 50,
            "decision": "approved",
            "decided_at": "2026-10-01T00:00:00Z",
            "submitted_at": "2026-09-30T00:00:00Z",
            "safety_decision": "approved",
            "safety_officer_id": str(uuid.uuid4()),
            "safety_decided_at": "2026-10-02T00:00:00Z",
        }
    ).execute().data[0]
    admin.schema("equipment").table("requirements").insert(
        {
            "event_id": event["id"],
            "equipment_item_id": equipment["id"],
            "required_quantity": 2,
            "recorded_by_coordinator_id": coordinator["id"],
        }
    ).execute()

    sign_in(support)
    page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
    page.get_by_role("link", name=f"Edit {equipment_name}").click()
    page.wait_for_url(re.compile(rf"/equipment/{equipment['id']}/edit$"), timeout=20000)
    page.get_by_label("Operational status (required)").select_option("unavailable")
    page.get_by_role("button", name="Save changes").click()
    page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
    expect(page.get_by_text(f"{equipment_name} was updated in the equipment catalogue.")).to_be_visible()

    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    inbox = page.get_by_role("region", name="Notifications")
    expect(inbox).to_contain_text(equipment_name, timeout=20000)
    expect(inbox).to_contain_text(event_name)
    expect(inbox).to_contain_text("Arrange replacement equipment before the event.")
