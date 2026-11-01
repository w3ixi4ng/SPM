"""S-60 Equipment batch journal and write lock against a real TEST schema."""

import os
import uuid

import httpx

from .conftest import BASE_URL, requires_env


pytestmark = requires_env


def test_versioned_batch_is_idempotent_and_blocks_competing_requirement_writes(admin):
    secret = os.environ["ASSIGNMENT_SERVICE_SECRET"]
    actor = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    operation_id = str(uuid.uuid4())
    items = []
    try:
        for name in ("Projector", "Microphone"):
            item = admin.schema("equipment").table("equipment").insert({
                "type": f"S60 {name} {uuid.uuid4().hex[:8]}",
                "total_quantity": 10, "created_by": actor,
            }).execute().data[0]
            items.append(item["id"])
        admin.schema("equipment").table("requirements").insert([
            {"event_id": event_id, "equipment_item_id": items[0],
             "required_quantity": 2, "recorded_by_coordinator_id": actor},
            {"event_id": event_id, "equipment_item_id": items[1],
             "required_quantity": 1, "recorded_by_coordinator_id": actor},
        ]).execute()
        baseline = [{"equipment_item_id": items[0], "required_quantity": 2},
                    {"equipment_item_id": items[1], "required_quantity": 1}]
        proposed = [{"equipment_item_id": items[0], "required_quantity": 3}]
        body = {"operation_id": operation_id, "event_id": event_id,
                "actor_id": actor, "baseline": baseline, "proposed": proposed}
        with httpx.Client(base_url=BASE_URL, timeout=20.0,
                          headers={"X-Assignment-Service-Token": secret}) as api:
            first = api.post("/internal/equipment-requirements/change-batches", json=body)
            assert first.status_code == 200, first.text
            assert first.json()["status"] == "applied"
            retry = api.post("/internal/equipment-requirements/change-batches", json=body)
            assert retry.status_code == 200, retry.text
            assert retry.json()["id"] == operation_id
            rows = admin.schema("equipment").table("requirements").select(
                "equipment_item_id,required_quantity"
            ).eq("event_id", event_id).execute().data
            assert rows == proposed
            changes = admin.schema("equipment").table("requirement_changes").select(
                "action,before_quantity,after_quantity"
            ).eq("event_id", event_id).execute().data
            assert sorted(row["action"] for row in changes) == ["removed", "updated"]
            competing = api.put(f"/internal/equipment-requirements/{event_id}/{items[0]}",
                json={"required_quantity": 4, "recorded_by_coordinator_id": actor})
            assert competing.status_code == 409, competing.text
            assert admin.schema("equipment").table("requirements").select("required_quantity").eq(
                "event_id", event_id).single().execute().data["required_quantity"] == 3
            aborted = api.post(f"/internal/equipment-requirements/change-batches/{operation_id}/abort")
            assert aborted.status_code == 200, aborted.text
            assert aborted.json()["status"] == "aborted"
            restored = admin.schema("equipment").table("requirements").select(
                "equipment_item_id,required_quantity"
            ).eq("event_id", event_id).execute().data
            assert sorted(restored, key=lambda row: row["equipment_item_id"]) == sorted(
                baseline, key=lambda row: row["equipment_item_id"])
            assert api.post("/internal/equipment-requirements/change-batches", json=body).status_code == 409
            next_operation = str(uuid.uuid4())
            next_body = {**body, "operation_id": next_operation}
            assert api.post("/internal/equipment-requirements/change-batches", json=next_body).status_code == 200
            finished = api.post(f"/internal/equipment-requirements/change-batches/{next_operation}/finish")
            assert finished.status_code == 200 and finished.json()["status"] == "finalized"
            newer = api.put(f"/internal/equipment-requirements/{event_id}/{items[0]}",
                json={"required_quantity": 4, "recorded_by_coordinator_id": actor})
            assert newer.status_code == 200, newer.text
            assert api.post(f"/internal/equipment-requirements/change-batches/{next_operation}/abort").status_code == 409
            assert admin.schema("equipment").table("requirements").select("required_quantity").eq(
                "event_id", event_id).single().execute().data["required_quantity"] == 4
    finally:
        admin.schema("equipment").table("change_operations").delete().eq("event_id", event_id).execute()
        admin.schema("equipment").table("requirement_changes").delete().eq("event_id", event_id).execute()
        admin.schema("equipment").table("requirements").delete().eq("event_id", event_id).execute()
        for item_id in items:
            admin.schema("equipment").table("equipment").delete().eq("id", item_id).execute()
