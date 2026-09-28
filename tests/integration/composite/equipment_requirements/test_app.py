"""Integration tests for S-40 -- see TEST_CASES.md."""

import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env


# --- TC-EQUIPMENTREQUIREMENTS-101 -----------------------------------------
def test_coordinator_records_edits_and_deletes_requirement_visible_to_support(admin, auth_client, world):
    coordinator = cookie_for(auth_client, world["coordinator"])
    support = cookie_for(auth_client, world["support"])
    path = f"{GATEWAY_BASE_URL}/equipment-requirements/{world['event_id']}/{world['equipment_id']}"

    created = httpx.put(path, headers=coordinator, json={"required_quantity": 2}, timeout=15.0)
    assert created.status_code == 200, created.text
    assert created.json()["required_quantity"] == 2

    edited = httpx.put(path, headers=coordinator, json={"required_quantity": 4}, timeout=15.0)
    assert edited.status_code == 200, edited.text
    assert edited.json()["required_quantity"] == 4

    visible = httpx.get(f"{GATEWAY_BASE_URL}/equipment-requirements", headers=support, timeout=15.0)
    assert visible.status_code == 200, visible.text
    matching = [row for row in visible.json() if row["event_id"] == world["event_id"]]
    assert len(matching) == 1
    assert matching[0]["equipment"]["id"] == world["equipment_id"]
    assert matching[0]["required_quantity"] == 4

    removed = httpx.delete(path, headers=coordinator, timeout=15.0)
    assert removed.status_code == 204, removed.text
    rows = admin.schema("equipment").table("requirements").select("id").eq("event_id", world["event_id"]).execute()
    assert rows.data == []


# --- TC-EQUIPMENTREQUIREMENTS-102 -----------------------------------------
def test_reassignment_uses_current_assignment_not_recorded_by_audit(admin, auth_client, world):
    old_headers = cookie_for(auth_client, world["coordinator"])
    new_headers = cookie_for(auth_client, world["new_coordinator"])
    path = f"{GATEWAY_BASE_URL}/equipment-requirements/{world['event_id']}/{world['equipment_id']}"

    first = httpx.put(path, headers=old_headers, json={"required_quantity": 2}, timeout=15.0)
    assert first.status_code == 200, first.text
    assert first.json()["recorded_by_coordinator_id"] == world["coordinator"]["id"]

    admin.schema("events").table("events").update({
        "assigned_coordinator_id": world["new_coordinator"]["id"]
    }).eq("id", world["event_id"]).execute()

    refused = httpx.put(path, headers=old_headers, json={"required_quantity": 3}, timeout=15.0)
    assert refused.status_code == 404, refused.text

    accepted = httpx.put(path, headers=new_headers, json={"required_quantity": 5}, timeout=15.0)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["required_quantity"] == 5
    assert accepted.json()["recorded_by_coordinator_id"] == world["new_coordinator"]["id"]
    stored = admin.schema("equipment").table("requirements").select("*").eq(
        "event_id", world["event_id"]
    ).eq("equipment_item_id", world["equipment_id"]).execute().data
    assert len(stored) == 1
    assert stored[0]["required_quantity"] == 5
    assert stored[0]["recorded_by_coordinator_id"] == world["new_coordinator"]["id"]
