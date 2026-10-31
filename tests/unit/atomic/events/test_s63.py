"""S-63 internal event identity used by notification composites."""

from types import SimpleNamespace

from .conftest import COORDINATOR_A, EVENT_ID, ORGANISER_ID


def _scope_select(db, rows):
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)


def test_notification_scope_returns_only_the_owned_event_identity(client, db):
    row = {
        "id": EVENT_ID,
        "organiser_id": ORGANISER_ID,
        "name": "Autumn Forum",
        "status": "confirmed",
        "assigned_coordinator_id": COORDINATOR_A,
    }
    _scope_select(db, [row])

    response = client.get(f"/internal/events/{EVENT_ID}/notification-scope")

    assert response.status_code == 200
    assert response.json() == row
    db.schema.return_value.table.return_value.select.assert_called_once_with(
        "id,organiser_id,name,status,assigned_coordinator_id"
    )


def test_notification_scope_returns_404_for_an_unknown_event(client, db):
    _scope_select(db, [])

    response = client.get(f"/internal/events/{EVENT_ID}/notification-scope")

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}
