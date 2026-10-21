"""S-26 equipment preparation status."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import EVENT_ID, authenticate, event_row, fake_user

SUPPORT_A = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
SUPPORT_B = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


def prepared_event(status="planning", preparation="not_started", **changes):
    values = dict(
        status=status,
        assigned_technical_support_id=SUPPORT_A,
        equipment_preparation_status=preparation,
        equipment_preparation_updated_by=None,
        equipment_preparation_updated_at=None,
    )
    values.update(changes)
    return event_row(**values)


def arrange_read(db, rows):
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value
        .eq.return_value.in_.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)


def arrange_update(db, rows):
    operation = (
        db.schema.return_value.table.return_value.update.return_value.eq.return_value
        .eq.return_value.in_.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)


# TC-EVENTS-123
@pytest.mark.parametrize("lifecycle", ["planning", "confirmed", "preparation"])
@pytest.mark.parametrize("value", ["in_progress", "ready", "not_started"])
def test_assigned_support_can_record_each_status_and_move_backwards(
    client, db, auth, lifecycle, value
):
    authenticate(client, auth, fake_user(user_id=SUPPORT_A, role="technical_support"))
    arrange_read(db, [prepared_event(status=lifecycle)])
    stored = prepared_event(
        status=lifecycle,
        preparation=value,
        equipment_preparation_updated_by=SUPPORT_A,
        equipment_preparation_updated_at="2026-10-11T03:00:00Z",
    )
    arrange_update(db, [stored])

    response = client.put(
        f"/events/support-assigned/{EVENT_ID}/equipment-preparation",
        json={"status": value},
    )

    assert response.status_code == 200
    assert response.json()["equipment_preparation_status"] == value
    values = db.schema.return_value.table.return_value.update.call_args.args[0]
    assert values["equipment_preparation_status"] == value
    assert values["equipment_preparation_updated_by"] == SUPPORT_A
    assert values["equipment_preparation_updated_at"]


# TC-EVENTS-124
@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("event_coordinator", 403),
        ("event_organiser", 403),
        ("venue_staff", 403),
        ("attendee", 403),
        ("unknown", 403),
    ],
)
def test_only_assigned_support_can_update_preparation(client, db, auth, role, expected):
    authenticate(client, auth, fake_user(role=role))
    response = client.put(
        f"/events/support-assigned/{EVENT_ID}/equipment-preparation",
        json={"status": "ready"},
    )
    assert response.status_code == expected
    db.schema.assert_not_called()


def test_unassigned_support_cannot_update_preparation(client, db, auth):
    authenticate(client, auth, fake_user(user_id=SUPPORT_B, role="technical_support"))
    arrange_read(db, [])
    response = client.put(
        f"/events/support-assigned/{EVENT_ID}/equipment-preparation",
        json={"status": "ready"},
    )
    assert response.status_code == 404
    db.schema.return_value.table.return_value.update.assert_not_called()


# TC-EVENTS-125
@pytest.mark.parametrize(
    "payload",
    [
        {"status": "done"},
        {"status": "ready", "equipment_preparation_updated_by": SUPPORT_B},
    ],
)
def test_invalid_and_stale_updates_never_report_success(client, db, auth, payload):
    authenticate(client, auth, fake_user(user_id=SUPPORT_A, role="technical_support"))
    response = client.put(
        f"/events/support-assigned/{EVENT_ID}/equipment-preparation", json=payload
    )
    assert response.status_code == 422
    db.schema.assert_not_called()


def test_concurrent_preparation_change_returns_conflict(client, db, auth):
    authenticate(client, auth, fake_user(user_id=SUPPORT_A, role="technical_support"))
    arrange_read(db, [prepared_event()])
    arrange_update(db, [])
    response = client.put(
        f"/events/support-assigned/{EVENT_ID}/equipment-preparation",
        json={"status": "ready"},
    )
    assert response.status_code == 409
    assert "Reload" in response.json()["detail"]


def test_storage_failure_is_safe(client, db, auth):
    authenticate(client, auth, fake_user(user_id=SUPPORT_A, role="technical_support"))
    arrange_read(db, [prepared_event()])
    operation = (
        db.schema.return_value.table.return_value.update.return_value.eq.return_value
        .eq.return_value.in_.return_value
    )
    operation.execute.side_effect = RuntimeError("database details")
    response = client.put(
        f"/events/support-assigned/{EVENT_ID}/equipment-preparation",
        json={"status": "ready"},
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Event storage unavailable"}
