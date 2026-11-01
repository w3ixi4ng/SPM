"""S-60 trusted Equipment batch API boundary tests."""

from types import SimpleNamespace

from .conftest import EVENT_ID, ITEM_ID, STAFF_ID


OPERATION_ID = "44444444-4444-4444-8444-444444444444"
PATH = "/internal/equipment-requirements/change-batches"
BODY = {
    "operation_id": OPERATION_ID,
    "event_id": EVENT_ID,
    "actor_id": STAFF_ID,
    "baseline": [{"equipment_item_id": ITEM_ID, "required_quantity": 2}],
    "proposed": [{"equipment_item_id": ITEM_ID, "required_quantity": 3}],
}


def test_batch_requires_trusted_service_and_canonical_snapshots(client, db, monkeypatch):
    monkeypatch.setenv("ASSIGNMENT_SERVICE_SECRET", "trusted-s60")
    denied = client.post(PATH, json=BODY)
    assert denied.status_code == 403
    db.schema.assert_not_called()

    duplicate = client.post(PATH, headers={"X-Assignment-Service-Token": "trusted-s60"},
                            json={**BODY, "proposed": BODY["proposed"] * 2})
    assert duplicate.status_code == 422
    db.schema.assert_not_called()

    operation = db.schema.return_value.rpc.return_value
    operation.execute.return_value = SimpleNamespace(data=[{"id": OPERATION_ID, "status": "applied"}])
    result = client.post(PATH, headers={"X-Assignment-Service-Token": "trusted-s60"}, json=BODY)
    assert result.status_code == 200, result.text
    db.schema.return_value.rpc.assert_called_once_with("apply_change_batch", {
        "p_operation_id": OPERATION_ID, "p_event_id": EVENT_ID, "p_actor_id": STAFF_ID,
        "p_baseline": BODY["baseline"], "p_proposed": BODY["proposed"],
    })


def test_batch_conflict_and_recovery_routes_preserve_controlled_state(client, db, monkeypatch):
    monkeypatch.setenv("ASSIGNMENT_SERVICE_SECRET", "trusted-s60")
    headers = {"X-Assignment-Service-Token": "trusted-s60"}
    operation = db.schema.return_value.rpc.return_value.execute
    conflict = RuntimeError("Requirement change is in progress")
    conflict.code = "23514"
    operation.side_effect = conflict
    result = client.post(PATH, headers=headers, json=BODY)
    assert result.status_code == 409

    operation.side_effect = None
    operation.return_value = SimpleNamespace(data=[{"id": OPERATION_ID, "status": "finalized"}])
    finished = client.post(f"{PATH}/{OPERATION_ID}/finish", headers=headers)
    assert finished.status_code == 200
    assert finished.json()["status"] == "finalized"
    assert db.schema.return_value.rpc.call_args.args[0] == "finish_change_batch"
