from types import SimpleNamespace

import pytest

from .conftest import COORDINATOR_A, COORDINATOR_B, EVENT_ID, ORGANISER_ID, event_row, on_insert


SUBMITTED = {
    "name": "Autumn Forum",
    "purpose": "Community planning",
    "start_date": "2026-11-18",
    "start_time": "09:00",
    "end_date": "2026-11-18",
    "end_time": "12:00",
    "expected_attendance": 120,
}


def submitted_row(**changes):
    return event_row(
        status="submitted",
        name="Autumn Forum",
        purpose="Community planning",
        start_date="2026-11-18",
        start_time="09:00:00",
        end_date="2026-11-18",
        end_time="12:00:00",
        expected_attendance=120,
        submitted_at="2026-10-08T12:00:00Z",
        **changes,
    )


def test_internal_submission_can_start_unassigned(client, db):
    row = submitted_row(assigned_coordinator_id=None)
    on_insert(db, [row])

    response = client.post(
        "/events/internal",
        json={**SUBMITTED, "organiser_id": ORGANISER_ID},
    )

    assert response.status_code == 201
    assert response.json()["assigned_coordinator_id"] is None
    inserted = db.schema.return_value.table.return_value.insert.call_args.args[0]
    assert inserted["status"] == "submitted"
    assert inserted["assigned_coordinator_id"] is None
    assert inserted["submitted_at"] is not None


def test_internal_unassigned_queue_filters_and_orders_in_storage(client, db):
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value.is_.return_value.order.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=[submitted_row()])

    response = client.get("/internal/events/unassigned")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [EVENT_ID]
    table = db.schema.return_value.table.return_value
    table.select.return_value.eq.assert_called_once_with("status", "submitted")
    table.select.return_value.eq.return_value.is_.assert_called_once_with(
        "assigned_coordinator_id", "null"
    )
    table.select.return_value.eq.return_value.is_.return_value.order.assert_called_once_with(
        "submitted_at"
    )


def test_internal_assignment_is_conditional_and_same_target_idempotent(client, db):
    assigned = submitted_row(assigned_coordinator_id=COORDINATOR_A)
    update_operation = (
        db.schema.return_value.table.return_value.update.return_value.eq.return_value.eq.return_value.is_.return_value.select.return_value
    )
    update_operation.execute.side_effect = [
        SimpleNamespace(data=[assigned]),
        SimpleNamespace(data=[]),
    ]
    select_operation = db.schema.return_value.table.return_value.select.return_value.eq.return_value
    select_operation.execute.return_value = SimpleNamespace(data=[assigned])

    first = client.post(
        f"/internal/events/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )
    second = client.post(
        f"/internal/events/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["assignment_created"] is True
    assert second.json()["assignment_created"] is False
    chain = db.schema.return_value.table.return_value.update.return_value
    chain.eq.assert_any_call("id", EVENT_ID)
    chain.eq.return_value.eq.assert_any_call("status", "submitted")
    chain.eq.return_value.eq.return_value.is_.assert_any_call(
        "assigned_coordinator_id", "null"
    )


def test_internal_assignment_rejects_a_different_existing_owner(client, db):
    update_operation = (
        db.schema.return_value.table.return_value.update.return_value.eq.return_value.eq.return_value.is_.return_value.select.return_value
    )
    update_operation.execute.return_value = SimpleNamespace(data=[])
    current = submitted_row(assigned_coordinator_id=COORDINATOR_B)
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[current])
    )

    response = client.post(
        f"/internal/events/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 409


@pytest.mark.parametrize("event_status", ["draft", "returned", "planning"])
def test_internal_assignment_rejects_wrong_state_targets(client, db, event_status):
    operation = db.schema.return_value.table.return_value
    operation.update.return_value.eq.return_value.eq.return_value.is_.return_value.select.return_value.execute.return_value.data = []
    operation.select.return_value.eq.return_value.execute.return_value.data = [
        event_row(status=event_status, assigned_coordinator_id=None)
    ]

    response = client.post(
        f"/internal/events/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "This event request is no longer available for assignment"


def test_internal_assignment_returns_404_for_a_missing_event(client, db):
    update_operation = (
        db.schema.return_value.table.return_value.update.return_value.eq.return_value.eq.return_value.is_.return_value.select.return_value
    )
    update_operation.execute.return_value = SimpleNamespace(data=[])
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[])
    )

    response = client.post(
        f"/internal/events/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 404
