from types import SimpleNamespace

import pytest

from .conftest import COORDINATOR_A, COORDINATOR_B, EVENT_ID, authenticate, event_row, fake_user


ACTIVE = ["submitted", "planning", "pending_safety_check", "confirmed", "returned"]
LEAD_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


@pytest.fixture(autouse=True)
def lead_auth(client, auth):
    authenticate(client, auth, fake_user(LEAD_ID, "event_coordinator_lead"))


def assigned_row(owner=COORDINATOR_A, version=0, previous=None, **changes):
    row = event_row(
        status="submitted",
        name="Autumn Forum",
        purpose="Community planning",
        start_date="2026-11-18",
        start_time="09:00:00",
        end_date="2026-11-18",
        end_time="12:00:00",
        expected_attendance=120,
        assigned_coordinator_id=owner,
        previous_coordinator_id=previous,
        coordinator_assignment_version=version,
        assigning_lead_id=LEAD_ID,
        submitted_at="2026-10-08T12:00:00Z",
    )
    row.update(changes)
    return row


def current_read(db, rows):
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=rows)
    )


def reassignment_write(db, rows):
    operation = db.schema.return_value.table.return_value.update.return_value
    operation.eq.return_value.eq.return_value.eq.return_value.eq.return_value.in_.return_value.select.return_value.execute.return_value = (
        SimpleNamespace(data=rows)
    )


def payload(target=COORDINATOR_B, expected=COORDINATOR_A, version=0):
    return {
        "coordinator_id": target,
        "expected_coordinator_id": expected,
        "expected_assignment_version": version,
    }


def test_internal_active_assignments_filter_status_owner_and_order(client, db):
    operation = (
        db.schema.return_value.table.return_value.select.return_value.in_.return_value.not_.is_.return_value.eq.return_value.order.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=[assigned_row()])

    response = client.get("/internal/events/lead-assigned-active")

    assert response.status_code == 200
    table = db.schema.return_value.table.return_value
    table.select.return_value.in_.assert_called_once_with("status", ACTIVE)
    table.select.return_value.in_.return_value.not_.is_.assert_called_once_with(
        "assigned_coordinator_id", "null"
    )
    table.select.return_value.in_.return_value.not_.is_.return_value.eq.assert_called_once_with(
        "assigning_lead_id", LEAD_ID
    )
    table.select.return_value.in_.return_value.not_.is_.return_value.eq.return_value.order.assert_called_once_with(
        "updated_at", desc=True
    )


def test_notification_assignment_read_does_not_require_a_lead_session(client, db, auth):
    client.cookies.clear()
    operation = (
        db.schema.return_value.table.return_value.select.return_value.in_
        .return_value.not_.is_.return_value.order.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=[assigned_row()])

    response = client.get("/internal/events/assigned-active")

    assert response.status_code == 200
    assert response.json()[0]["assigned_coordinator_id"] == COORDINATOR_A
    assert not auth.auth.get_user.called
    db.schema.return_value.table.return_value.select.return_value.in_.return_value.not_.is_.return_value.order.assert_called_once_with(
        "updated_at", desc=True
    )


def test_internal_reassignment_uses_versioned_compare_and_set(client, db):
    current_read(db, [assigned_row()])
    changed = assigned_row(owner=COORDINATOR_B, previous=COORDINATOR_A, version=1)
    reassignment_write(db, [changed])

    response = client.post(
        f"/internal/events/{EVENT_ID}/reassignment", json=payload()
    )

    assert response.status_code == 200
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_B
    assert response.json()["previous_coordinator_id"] == COORDINATOR_A
    assert response.json()["coordinator_assignment_version"] == 1
    assert response.json()["reassignment_created"] is True
    update = db.schema.return_value.table.return_value.update
    assert update.call_args.args[0] == {
        "assigned_coordinator_id": COORDINATOR_B,
        "previous_coordinator_id": COORDINATOR_A,
        "coordinator_assignment_version": 1,
    }
    update.return_value.eq.assert_called_once_with("id", EVENT_ID)
    update.return_value.eq.return_value.eq.assert_called_once_with(
        "assigned_coordinator_id", COORDINATOR_A
    )
    update.return_value.eq.return_value.eq.return_value.eq.assert_called_once_with(
        "coordinator_assignment_version", 0
    )
    update.return_value.eq.return_value.eq.return_value.eq.return_value.eq.assert_called_once_with(
        "assigning_lead_id", LEAD_ID
    )
    update.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.in_.assert_called_once_with(
        "status", ACTIVE
    )


def test_internal_reassignment_retry_is_idempotent(client, db):
    current_read(
        db,
        [assigned_row(owner=COORDINATOR_B, previous=COORDINATOR_A, version=1)],
    )

    response = client.post(
        f"/internal/events/{EVENT_ID}/reassignment", json=payload()
    )

    assert response.status_code == 200
    assert response.json()["reassignment_created"] is False
    assert response.json()["coordinator_assignment_version"] == 1
    db.schema.return_value.table.return_value.update.assert_not_called()


@pytest.mark.parametrize(
    "row,request_data",
    [
        (
            assigned_row(
                owner=COORDINATOR_A,
                previous=COORDINATOR_B,
                version=2,
            ),
            payload(target=COORDINATOR_B, expected=COORDINATOR_A, version=0),
        ),
        (
            assigned_row(owner=COORDINATOR_A, version=0),
            payload(target=COORDINATOR_A, expected=COORDINATOR_A, version=0),
        ),
    ],
)
def test_internal_reassignment_rejects_stale_or_same_owner_requests(
    client, db, row, request_data
):
    current_read(db, [row])

    response = client.post(
        f"/internal/events/{EVENT_ID}/reassignment", json=request_data
    )

    assert response.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()


def test_internal_reassignment_rejects_unrelated_lead_and_legacy_event(client, db):
    current_read(db, [assigned_row(assigning_lead_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")])
    unrelated = client.post(f"/internal/events/{EVENT_ID}/reassignment", json=payload())
    assert unrelated.status_code == 404
    current_read(db, [assigned_row(assigning_lead_id=None)])
    legacy = client.post(f"/internal/events/{EVENT_ID}/reassignment", json=payload())
    assert legacy.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()


@pytest.mark.parametrize(
    "rows,expected_status",
    [
        ([], 404),
        ([assigned_row(owner=None)], 409),
        ([assigned_row(status="draft", submitted_at=None)], 409),
        ([assigned_row(status="rejected", decision="rejected", decision_reason="No", decided_at="2026-10-08T13:00:00Z")], 409),
        ([assigned_row(status="cancelled", decision="approved", decided_at="2026-10-08T13:00:00Z")], 409),
    ],
)
def test_internal_reassignment_rejects_missing_ineligible_and_unassigned_events(
    client, db, rows, expected_status
):
    current_read(db, rows)

    response = client.post(
        f"/internal/events/{EVENT_ID}/reassignment", json=payload()
    )

    assert response.status_code == expected_status
    db.schema.return_value.table.return_value.update.assert_not_called()
