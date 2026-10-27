"""S-85 coordinator oversight read-source tests."""

from types import SimpleNamespace
import pytest

from .conftest import COORDINATOR_A, authenticate, event_row, fake_user

LEAD_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


@pytest.fixture(autouse=True)
def lead_auth(client, auth):
    authenticate(client, auth, fake_user(LEAD_ID, "event_coordinator_lead"))


OVERSIGHT_ACTIVE = [
    "submitted",
    "under_review",
    "returned",
    "planning",
    "pending_safety_check",
    "confirmed",
    "preparation",
    "safety_rejected",
    "safety_changes_requested",
]


def _active_row(status: str):
    return event_row(
        status=status,
        name=f"{status} event",
        purpose="Coordinator oversight",
        start_date="2026-11-18",
        start_time="09:00:00",
        end_date="2026-11-18",
        end_time="12:00:00",
        expected_attendance=50,
        assigned_coordinator_id=COORDINATOR_A,
        submitted_at="2026-10-09T00:00:00Z",
    )


def test_internal_oversight_uses_all_open_active_statuses(client, db):
    operation = (
        db.schema.return_value.table.return_value.select.return_value.in_.return_value.not_.is_.return_value.order.return_value.eq.return_value
    )
    operation.execute.return_value = SimpleNamespace(
        data=[_active_row(status) for status in OVERSIGHT_ACTIVE]
    )

    response = client.get("/internal/events/coordinator-overview")

    assert response.status_code == 200
    assert [row["status"] for row in response.json()] == OVERSIGHT_ACTIVE
    table = db.schema.return_value.table.return_value
    table.select.return_value.in_.assert_called_once_with(
        "status", OVERSIGHT_ACTIVE
    )
    table.select.return_value.in_.return_value.not_.is_.assert_called_once_with(
        "assigned_coordinator_id", "null"
    )
    table.select.return_value.in_.return_value.not_.is_.return_value.order.assert_called_once_with(
        "updated_at", desc=True
    )
    table.select.return_value.in_.return_value.not_.is_.return_value.order.return_value.eq.assert_called_once_with(
        "assigning_lead_id", LEAD_ID
    )


def test_internal_oversight_excludes_unassigned_and_inactive_events(client, db):
    operation = (
        db.schema.return_value.table.return_value.select.return_value.in_.return_value.not_.is_.return_value.order.return_value.eq.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=[])

    response = client.get("/internal/events/coordinator-overview")

    assert response.status_code == 200
    assert response.json() == []
    assert set(
        db.schema.return_value.table.return_value.select.return_value.in_.call_args.args[1]
    ) == set(OVERSIGHT_ACTIVE)
    assert set(OVERSIGHT_ACTIVE).isdisjoint(
        {"draft", "rejected", "cancelled", "completed"}
    )
    db.schema.return_value.table.return_value.insert.assert_not_called()
    db.schema.return_value.table.return_value.update.assert_not_called()
    db.schema.return_value.table.return_value.delete.assert_not_called()
