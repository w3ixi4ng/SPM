"""TC-E2E-215 -- retired equipment remains managed but not selectable."""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


# --- TC-E2E-215 -----------------------------------------------------------
def test_retired_equipment_remains_managed_but_disappears_from_selection(
    admin, page, make_user, sign_in
):
    support = make_user("technical_support")
    coordinator = make_user("event_coordinator")
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    item_type = f"spm-e2e S42 Microphone {suffix}"
    item = (
        admin.schema("equipment")
        .table("equipment")
        .insert(
            {
                "type": item_type,
                "description": "Retire through the browser",
                "total_quantity": 12,
                "operational_status": "available",
                "lifecycle_status": "active",
                "created_by": support["id"],
            }
        )
        .execute()
        .data[0]
    )
    event = (
        admin.schema("events")
        .table("events")
        .insert(
            {
                "organiser_id": organiser["id"],
                "status": "planning",
                "assigned_coordinator_id": coordinator["id"],
                "name": f"spm-e2e S42 Event {suffix}",
                "purpose": "Prove retired equipment is not selectable",
                "start_date": "2026-11-13",
                "start_time": "09:00",
                "end_date": "2026-11-13",
                "end_time": "12:00",
                "expected_attendance": 40,
                "decision": "approved",
                "decided_at": "2026-10-01T00:00:00+00:00",
                "submitted_at": "2026-09-30T00:00:00+00:00",
            }
        )
        .execute()
        .data[0]
    )

    sign_in(support)
    page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name=f"Retire {item_type}").click()
    page.get_by_text(f"{item_type} was retired from new equipment requests.").wait_for(
        timeout=20000
    )

    catalogue = page.get_by_role("list", name="Equipment catalogue")
    row = catalogue.get_by_role("listitem").filter(has_text=item_type)
    row.wait_for(timeout=20000)
    row.get_by_text("Available · Retired", exact=True).wait_for()
    assert row.get_by_role("button", name=f"Retire {item_type}").count() == 0

    stored = (
        admin.schema("equipment")
        .table("equipment")
        .select("*")
        .eq("id", item["id"])
        .execute()
        .data[0]
    )
    assert stored["lifecycle_status"] == "retired"

    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    page.get_by_role("heading", name="Required equipment").wait_for(timeout=20000)
    assert page.get_by_label(f"{item_type} quantity").count() == 0
