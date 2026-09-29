"""S-37/S-38 booking decisions, isolated storage and authentication."""
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


def prepare(db, *, booking=None, conflicts=None):
    booking = booking_row() if booking is None else booking
    query = table(db).select.return_value
    query.eq.return_value = query
    query.neq.return_value = query
    query.lt.return_value = query
    query.gt.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.side_effect = [
        SimpleNamespace(data=[] if booking is False else [booking]),
        SimpleNamespace(data=conflicts or []),
    ]
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
    booking = booking_row(status='confirmed') if exists else False
    update = prepare(db, booking=booking)
    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})
    assert response.status_code == code
    table(db).update.assert_not_called()


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


@pytest.mark.parametrize('start_time,end_time', [
    ('10:30:00', '11:30:00'),
    ('09:00:00', '11:00:00'),
    ('11:00:00', '13:00:00'),
    ('09:00:00', '13:00:00'),
])
def test_confirmation_reports_existing_overlap(client, db, auth, start_time, end_time):
    conflict = booking_row(
        id='55555555-5555-4555-8555-555555555555',
        status='confirmed',
        start_time='10:00:00',
        end_time='12:00:00',
    )
    prepare(db, booking=booking_row(start_time=start_time, end_time=end_time), conflicts=[conflict])

    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})

    assert response.status_code == 409
    assert response.json()['detail'] == 'Studio B is already confirmed on 12 Nov 2026 from 10:00 to 12:00.'
    table(db).update.assert_not_called()


def test_overlap_lookup_uses_half_open_same_venue_and_date_window(client, db, auth):
    prepare(db, conflicts=[])

    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})

    assert response.status_code == 200
    query = table(db).select.return_value
    assert ('venue_id', booking_row()['venue_id']) in [call.args for call in query.eq.call_args_list]
    assert ('booking_date', booking_row()['booking_date']) in [call.args for call in query.eq.call_args_list]
    assert ('status', 'confirmed') in [call.args for call in query.eq.call_args_list]
    query.lt.assert_called_once_with('start_time', booking_row()['end_time'])
    query.gt.assert_called_once_with('end_time', booking_row()['start_time'])


def test_database_overlap_race_returns_identified_conflict(client, db, auth):
    class ExclusionViolation(Exception):
        code = '23P01'

    conflict = booking_row(
        id='55555555-5555-4555-8555-555555555555',
        status='confirmed',
        start_time='10:00:00',
        end_time='12:00:00',
    )
    update = prepare(db)
    table(db).select.return_value.execute.side_effect = [
        SimpleNamespace(data=[booking_row()]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[conflict]),
    ]
    update.execute.side_effect = ExclusionViolation('private constraint detail')

    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})

    assert response.status_code == 409
    assert response.json()['detail'] == 'Studio B is already confirmed on 12 Nov 2026 from 10:00 to 12:00.'
