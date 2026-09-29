"""S-37: TC-BOOKINGS-017..022, isolated storage and authentication."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import app, database_module, BOOKING_ID, booking_row, table

STAFF = 'abababab-abab-4bab-8bab-abababababab'
PATH = f'/bookings/{BOOKING_ID}/decision'


@pytest.fixture
def auth():
    fake = MagicMock()
    fake.auth.get_user.return_value.user = SimpleNamespace(id=STAFF, app_metadata={'role': 'venue_staff'})
    app.dependency_overrides[database_module.get_auth] = lambda: fake
    yield fake
    app.dependency_overrides.pop(database_module.get_auth, None)


def prepare(db):
    update = table(db).update.return_value
    update.eq.return_value = update
    update.execute.side_effect = lambda: SimpleNamespace(data=[booking_row(**table(db).update.call_args.args[0])])
    return update


@pytest.mark.parametrize('payload, expected', [
    ({'decision': 'approved'}, 'confirmed'),
    ({'decision': 'approved', 'reason': '  Checked  ', 'alternative': ' \t '}, 'confirmed'),
    ({'decision': 'rejected', 'reason': ' Repairs '}, 'rejected'),
    ({'decision': 'rejected', 'alternative': ' Try Studio C at 14:00 '}, 'rejected'),
    ({'decision': 'rejected', 'reason': 'Repairs', 'alternative': 'Try Friday'}, 'rejected'),
])
def test_decision_preserves_request(client, db, auth, payload, expected):
    update = prepare(db)
    before = datetime.now(timezone.utc)
    response = client.post(PATH, json=payload, cookies={'sb_access_token': 'verified-token'})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['status'] == expected
    assert saved['decided_by'] == STAFF
    assert datetime.fromisoformat(saved['decided_at'].replace('Z', '+00:00')) >= before
    values = table(db).update.call_args.args[0]
    assert set(values) == {'status', 'decision_reason', 'decision_alternative', 'decided_by', 'decided_at'}
    assert values['decision_reason'] == (payload.get('reason', '').strip() or None)
    assert values['decision_alternative'] == (payload.get('alternative', '').strip() or None)
    assert update.eq.call_args_list[0].args == ('id', BOOKING_ID)
    assert update.eq.call_args_list[1].args == ('status', 'pending')
    for key, value in booking_row().items():
        if key not in ('status', 'submitted_at'):
            assert saved[key] == value
    assert datetime.fromisoformat(saved['submitted_at'].replace('Z', '+00:00')) == datetime.fromisoformat(booking_row()['submitted_at'])
    table(db).insert.assert_not_called()


@pytest.mark.parametrize('payload', [
    {'decision': 'rejected'}, {'decision': 'rejected', 'reason': ' ', 'alternative': '\t'},
    {'decision': 'pending'}, {'decision': 'cancelled'},
    {'decision': 'approved', 'reason': 42}, {'decision': 'approved', 'alternative': []},
    *[{'decision': 'approved', key: 'forged'} for key in
      ('status', 'decided_by', 'decided_at', 'venue_id', 'booking_date')],
])
def test_invalid_decision_never_writes(client, db, auth, payload):
    assert client.post(PATH, json=payload, cookies={'sb_access_token': 'token'}).status_code == 422
    table(db).update.assert_not_called()


@pytest.mark.parametrize('exists, code', [(True, 409), (False, 404)])
def test_no_conditional_match_is_conflict_or_missing(client, db, auth, exists, code):
    update = prepare(db)
    update.execute.side_effect = None
    update.execute.return_value = SimpleNamespace(data=[])
    table(db).select.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[{'id': BOOKING_ID}] if exists else [])
    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})
    assert response.status_code == code
    table(db).update.assert_called_once()


@pytest.mark.parametrize('role', ['event_coordinator', 'event_organiser', 'technical_support', 'attendee', 'unknown', None])
def test_direct_nonstaff_call_forbidden(client, db, auth, role):
    auth.auth.get_user.return_value.user.app_metadata = {'role': role}
    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})
    assert response.status_code == 403
    table(db).update.assert_not_called()


def test_missing_and_invalid_session(client, db, auth):
    assert client.post(PATH, json={'decision': 'approved'}).status_code == 401
    auth.auth.get_user.side_effect = RuntimeError('private auth detail')
    assert client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'bad'}).status_code == 401
    table(db).update.assert_not_called()


def test_storage_failure_safe(client, db, auth):
    prepare(db).execute.side_effect = RuntimeError('private database diagnostic')
    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})
    assert response.status_code == 500
    assert 'private' not in response.text
