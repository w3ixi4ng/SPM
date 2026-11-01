"""S-60 Events boundary: coordinator scope and direct safety guards."""

from types import SimpleNamespace

from .conftest import COORDINATOR_A, COORDINATOR_B, EVENT_ID, authenticate, event_row, fake_user, app_module
from .test_s18 import editable_event, assigned_select, edit_update


REQUEST_ID = "44444444-4444-4444-8444-444444444444"
TRUSTED = {"X-Assignment-Service-Token": "unit-assignment-secret"}


def test_internal_impact_read_requires_trusted_service(client, db):
    path = f"/internal/events/{EVENT_ID}/unresolved-change-impacts"
    client.headers.pop("X-Assignment-Service-Token", None)
    assert client.get(path).status_code == 403
    db.schema.assert_not_called()


def test_change_decision_requires_current_coordinator_and_trusted_service(client, db, auth):
    authenticate(client, auth, fake_user(COORDINATOR_A, "event_coordinator"))
    path = f"/events/assigned/{EVENT_ID}/change-requests/{REQUEST_ID}/reject"
    client.headers.pop("X-Assignment-Service-Token")
    assert client.post(path, json={"reason": "Venue unavailable"}).status_code == 403
    db.schema.assert_not_called()

    operation = db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value
    operation.execute.return_value = SimpleNamespace(data=[])
    assert client.post(path, headers=TRUSTED, json={"reason": "Venue unavailable"}).status_code == 404
    db.schema.return_value.rpc.assert_not_called()

    db.reset_mock()
    authenticate(client, auth, fake_user(COORDINATOR_B, "event_coordinator"))
    operation.execute.return_value = SimpleNamespace(data=[])
    assert client.post(path, headers=TRUSTED, json={"reason": "Venue unavailable"}).status_code == 404
    db.schema.return_value.rpc.assert_not_called()


def test_direct_safety_submission_rejects_unresolved_accepted_impact(client, db, monkeypatch):
    operation = db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value
    operation.execute.return_value = SimpleNamespace(data=[event_row(
        status="planning", assigned_coordinator_id=COORDINATOR_A,
        safety_decision=None,
    )])
    monkeypatch.setattr(app_module, "_unresolved_change_impacts", lambda event_id, store: [{
        "id": "venue_booking:b1:capacity", "status": "outstanding", "reason": "Capacity too low",
    }])

    response = client.post(f"/internal/events/{EVENT_ID}/safety-submission",
                           json={"coordinator_id": COORDINATOR_A})

    assert response.status_code == 409
    assert "Resolve change impacts" in response.json()["detail"]
    db.schema.return_value.table.return_value.update.assert_not_called()


def test_significant_direct_s18_edit_cannot_skip_trusted_impact_review(client, db, auth):
    authenticate(client, auth, fake_user(COORDINATOR_A, "event_coordinator"))
    assigned_select(db, [editable_event()])
    client.headers.pop("X-Assignment-Service-Token")

    response = client.patch(f"/events/assigned/{EVENT_ID}", json={
        "expected_version": 0, "expected_attendance": 150,
        "impact_accepted": True, "impact_items": [],
    })

    assert response.status_code == 403
    db.schema.return_value.table.return_value.update.assert_not_called()


def test_routine_s18_edit_stays_available_without_service_token(client, db, auth):
    authenticate(client, auth, fake_user(COORDINATOR_A, "event_coordinator"))
    current = editable_event()
    assigned_select(db, [current])
    edit_update(db, [editable_event(contact_phone="+65 6123 4567", edit_version=1)])
    client.headers.pop("X-Assignment-Service-Token")

    response = client.patch(f"/events/assigned/{EVENT_ID}", json={
        "expected_version": 0, "contact_phone": "+65 6123 4567",
    })

    assert response.status_code == 200, response.text
    values = db.schema.return_value.table.return_value.update.call_args.args[0]
    assert "s60_edit_impacts" not in values
    assert "safety_decision" not in values


def test_direct_safety_transition_reports_applying_operation_as_conflict(client, db, monkeypatch):
    operation = db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value
    operation.execute.return_value = SimpleNamespace(data=[event_row(
        status="planning", assigned_coordinator_id=COORDINATOR_A, safety_decision=None,
    )])
    monkeypatch.setattr(app_module, "_unresolved_change_impacts", lambda event_id, store: [])
    conflict = RuntimeError("Event change acceptance is in progress")
    conflict.code = "23514"
    db.schema.return_value.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.is_.return_value.execute.side_effect = conflict

    response = client.post(f"/internal/events/{EVENT_ID}/safety-submission",
                           json={"coordinator_id": COORDINATOR_A})

    assert response.status_code == 409
    assert response.json()["detail"] == "Event change acceptance is in progress"
