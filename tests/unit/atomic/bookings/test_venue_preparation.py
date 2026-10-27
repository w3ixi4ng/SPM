"""S-25 per-booking venue preparation, isolated from Supabase."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import app, database_module, BOOKING_ID, booking_row, table

STAFF_ID = "abababab-abab-4bab-8bab-abababababab"
PATH = f"/bookings/{BOOKING_ID}/venue-preparation"


@pytest.fixture
def auth():
    fake = MagicMock()
    fake.auth.get_user.return_value.user = SimpleNamespace(
        id=STAFF_ID, app_metadata={"role": "venue_staff"}
    )
    app.dependency_overrides[database_module.get_auth] = lambda: fake
    yield fake
    app.dependency_overrides.pop(database_module.get_auth, None)


def prepare(db, booking=None, saved=True):
    booking = booking or booking_row(
        status="confirmed", venue_preparation_status="not_started",
        venue_preparation_updated_by=None, venue_preparation_updated_at=None,
        venue_preparation_version=0,
    )
    query = table(db).select.return_value
    query.eq.return_value = query
    query.execute.return_value = SimpleNamespace(data=[booking])
    update = table(db).update.return_value
    update.eq.return_value = update
    values = lambda: table(db).update.call_args.args[0]
    update.execute.side_effect = lambda: SimpleNamespace(
        data=[{**booking, **values()}] if saved else []
    )
    return update


@pytest.mark.parametrize("state", ["not_started", "in_progress", "ready"])
def test_staff_saves_each_state_with_server_audit(client, db, auth, state):
    update = prepare(db)
    before = datetime.now(timezone.utc)
    response = client.put(PATH, json={"status": state, "expected_version": 0},
                          cookies={"sb_access_token": "token"})
    assert response.status_code == 200, response.text
    assert response.json()["venue_preparation_status"] == state
    assert response.json()["venue_preparation_updated_by"] == STAFF_ID
    assert datetime.fromisoformat(response.json()["venue_preparation_updated_at"]) >= before
    assert response.json()["venue_preparation_version"] == 1
    assert ("status", "confirmed") in [call.args for call in update.eq.call_args_list]
    assert ("venue_preparation_version", 0) in [call.args for call in update.eq.call_args_list]


@pytest.mark.parametrize("payload", [
    {"status": "done", "expected_version": 0},
    {"status": "ready", "expected_version": 0, "venue_preparation_updated_by": STAFF_ID},
])
def test_invalid_or_forged_input_never_writes(client, db, auth, payload):
    response = client.put(PATH, json=payload, cookies={"sb_access_token": "token"})
    assert response.status_code == 422
    table(db).update.assert_not_called()


def test_stale_version_is_a_conflict(client, db, auth):
    prepare(db, saved=False)
    response = client.put(PATH, json={"status": "ready", "expected_version": 0},
                          cookies={"sb_access_token": "token"})
    assert response.status_code == 409
    assert "Reload" in response.json()["detail"]


@pytest.mark.parametrize("status", ["pending", "held", "rejected", "replaced"])
def test_only_confirmed_bookings_can_be_prepared(client, db, auth, status):
    prepare(db, booking=booking_row(status=status))
    response = client.put(PATH, json={"status": "ready", "expected_version": 0},
                          cookies={"sb_access_token": "token"})
    assert response.status_code == 409
    table(db).update.assert_not_called()


@pytest.mark.parametrize("role", ["event_coordinator", "technical_support", "event_organiser", "attendee"])
def test_non_staff_cannot_update(client, db, auth, role):
    auth.auth.get_user.return_value.user.app_metadata = {"role": role}
    response = client.put(PATH, json={"status": "ready", "expected_version": 0},
                          cookies={"sb_access_token": "token"})
    assert response.status_code == 403
    table(db).update.assert_not_called()
