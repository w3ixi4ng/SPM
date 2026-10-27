"""S-88 Events owned request endpoints; SQL trigger behavior needs integration."""

from types import SimpleNamespace
import pytest

from .conftest import COORDINATOR_A, EVENT_ID, authenticate, event_row, fake_user

LEAD_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
ROW = {
    "id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
    "event_id": EVENT_ID,
    "event_name": "November Forum",
    "requester_id": COORDINATOR_A,
    "assigning_lead_id": LEAD_ID,
    "assignment_version": 2,
    "reason": "Cannot cover the November event",
    "status": "pending",
    "created_at": "2026-10-25T00:00:00Z",
    "actioned_at": None,
}


def payload():
    return {"reason": "  Cannot cover the November event  "}


@pytest.fixture(autouse=True)
def coordinator_auth(client, auth):
    authenticate(client, auth, fake_user(COORDINATOR_A, "event_coordinator"))


def assigned_read(db):
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[event_row(assigned_coordinator_id=COORDINATOR_A, assigning_lead_id=LEAD_ID,
                        coordinator_assignment_version=2)]
    )


def test_request_insert_passes_only_validated_fields_to_events_schema(client, db):
    assigned_read(db)
    db.schema.return_value.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(data=[ROW])
    response = client.post(f"/events/{EVENT_ID}/reassignment-request", json=payload())
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    db.schema.assert_called_with("events")
    assert db.schema.return_value.table.call_args.args[0] == "reassignment_requests"
    inserted = db.schema.return_value.table.return_value.insert.call_args.args[0]
    assert inserted == {
        "event_id": EVENT_ID, "requester_id": COORDINATOR_A,
        "assigning_lead_id": LEAD_ID, "assignment_version": 2,
        "reason": ROW["reason"],
    }


def test_request_rejects_blank_reason_and_client_status(client, db):
    for body in ({**payload(), "reason": "  "}, {**payload(), "status": "actioned"}):
        assert client.post(f"/events/{EVENT_ID}/reassignment-request", json=body).status_code == 422
    db.schema.return_value.table.return_value.insert.assert_not_called()


def test_unique_pending_conflict_is_reported(client, db):
    assigned_read(db)
    error = RuntimeError("duplicate")
    error.code = "23505"
    db.schema.return_value.table.return_value.insert.return_value.execute.side_effect = error
    response = client.post(f"/events/{EVENT_ID}/reassignment-request", json=payload())
    assert response.status_code == 409
    assert "pending" in response.json()["detail"]


def test_request_history_filters_by_trusted_composite_identity(client, db):
    query = db.schema.return_value.table.return_value.select.return_value.eq.return_value.order.return_value
    query.execute.return_value = SimpleNamespace(data=[ROW])
    response = client.get("/events/reassignment-requests/mine")
    assert response.status_code == 200
    assert response.json()[0]["requester_id"] == COORDINATOR_A
    db.schema.return_value.table.return_value.select.return_value.eq.assert_called_with("requester_id", COORDINATOR_A)


def test_lead_history_filters_by_recorded_provenance(client, db, auth):
    authenticate(client, auth, fake_user(LEAD_ID, "event_coordinator_lead"))
    query = db.schema.return_value.table.return_value.select.return_value.eq.return_value.order.return_value
    query.execute.return_value = SimpleNamespace(data=[ROW])
    response = client.get("/internal/reassignment-requests/lead")
    assert response.status_code == 200
    db.schema.return_value.table.return_value.select.return_value.eq.assert_called_with("assigning_lead_id", LEAD_ID)


def test_direct_request_requires_real_coordinator_session_and_ownership(client, db, auth):
    client.cookies.clear()
    assert client.post(f"/events/{EVENT_ID}/reassignment-request", json=payload()).status_code == 401
    authenticate(client, auth, fake_user(LEAD_ID, "event_coordinator_lead"))
    assert client.post(f"/events/{EVENT_ID}/reassignment-request", json=payload()).status_code == 403
    authenticate(client, auth, fake_user(COORDINATOR_A, "event_coordinator"))
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[])
    assert client.post(f"/events/{EVENT_ID}/reassignment-request", json=payload()).status_code == 404
    db.schema.return_value.table.return_value.insert.assert_not_called()


def test_legacy_and_unrelated_lead_scope_fails_closed(client, db, auth):
    authenticate(client, auth, fake_user(LEAD_ID, "event_coordinator_lead"))
    query = db.schema.return_value.table.return_value.select.return_value.eq.return_value
    query.execute.return_value = SimpleNamespace(data=[event_row(assigning_lead_id=None)])
    legacy = client.get(f"/internal/events/{EVENT_ID}/assignment-scope")
    assert legacy.status_code == 409
    other_lead = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    query.execute.return_value = SimpleNamespace(data=[event_row(assigning_lead_id=other_lead)])
    unrelated = client.get(f"/internal/events/{EVENT_ID}/assignment-scope")
    assert unrelated.status_code == 404
