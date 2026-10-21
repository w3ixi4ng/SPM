"""S-61: an approved cancellation removes every booking for the event.

TC-BOOKINGS-064..066.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import app, booking_row, database_module, table

EVENT_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
COORDINATOR = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
COOKIE = {"sb_access_token": "verified-token"}
URL = f"/internal/events/{EVENT_ID}/bookings"


@pytest.fixture
def signed_in():
    """Signs the request in as `role`."""
    fake = MagicMock()
    app.dependency_overrides[database_module.get_auth] = lambda: fake

    def as_role(role):
        fake.auth.get_user.return_value.user = SimpleNamespace(id=COORDINATOR, app_metadata={"role": role})

    as_role("event_coordinator")
    yield as_role
    app.dependency_overrides.pop(database_module.get_auth, None)


def on_delete(db, rows=None, error=None):
    operation = table(db).delete.return_value.eq.return_value
    if error is not None:
        operation.execute.side_effect = error
    else:
        operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


# --- TC-BOOKINGS-064 -------------------------------------------------------
def test_an_approved_cancellation_removes_every_booking_for_the_event(client, db, signed_in):
    on_delete(db, [booking_row(status=status) for status in ("pending", "held", "confirmed")])

    response = client.delete(URL, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": 3}
    table(db).delete.assert_called_once_with()
    assert table(db).delete.return_value.eq.call_args.args == ("event_id", EVENT_ID)
    # Every status: no further filter after event_id.
    table(db).delete.return_value.eq.return_value.in_.assert_not_called()
    assert [call.args[0] for call in db.schema.return_value.table.call_args_list] == ["bookings"]


# --- TC-BOOKINGS-065 -------------------------------------------------------
def test_removing_an_events_bookings_twice_is_safe(client, db, signed_in):
    on_delete(db, [])

    response = client.delete(URL, cookies=COOKIE)

    assert response.status_code == 200
    assert response.json() == {"deleted": 0}


# --- TC-BOOKINGS-066 -------------------------------------------------------
def test_without_a_session_nothing_is_removed(client, db):
    response = client.delete(URL)

    assert response.status_code == 401
    db.schema.assert_not_called()


@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "technical_support", "attendee"])
def test_other_roles_cannot_remove_an_events_bookings(client, db, signed_in, role):
    signed_in(role)

    response = client.delete(URL, cookies=COOKIE)

    assert response.status_code == 403
    db.schema.assert_not_called()


def test_a_storage_failure_is_a_500(client, db, signed_in):
    on_delete(db, error=RuntimeError("connection reset"))

    response = client.delete(URL, cookies=COOKIE)

    assert response.status_code == 500
    assert response.json() == {"detail": "Booking storage unavailable"}
