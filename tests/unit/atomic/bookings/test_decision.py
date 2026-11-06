"""S-37/S-38 booking decisions, isolated storage and authentication."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from supabase import AuthApiError

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


def prepare(db, *, booking=None, conflicts=None, blocks=None):
    booking = booking_row() if booking is None else booking
    query = table(db).select.return_value
    for method in ('eq', 'neq', 'in_', 'lt', 'gt', 'lte', 'gte', 'order', 'limit'):
        getattr(query, method).return_value = query
    # The booking, the confirmed-overlap check, then S-30's block check.
    query.execute.side_effect = [
        SimpleNamespace(data=[] if booking is False else [booking]),
        SimpleNamespace(data=conflicts or []),
        SimpleNamespace(data=blocks or []),
    ]
    update = table(db).update.return_value
    update.eq.return_value = update
    update.in_.return_value = update
    update.or_.return_value = update
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
    expected_fields = {'status', 'decision_reason', 'decision_alternative', 'decided_by', 'decided_at'}
    if payload['decision'] == 'approved':
        expected_fields |= {'approval_setup_minutes', 'approval_turnaround_minutes'}
        assert (values['approval_setup_minutes'], values['approval_turnaround_minutes']) == (0, 0)
    assert set(values) == expected_fields
    assert values['decision_reason'] == (payload.get('reason', '').strip() or None)
    assert values['decision_alternative'] == (payload.get('alternative', '').strip() or None)
    assert update.eq.call_args_list[0].args == ('id', BOOKING_ID)
    update.in_.assert_called_once_with('status', ['pending', 'held'])
    for key, value in booking_row().items():
        if key not in ('status', 'submitted_at'):
            assert saved[key] == value
    assert datetime.fromisoformat(saved['submitted_at'].replace('Z', '+00:00')) == datetime.fromisoformat(booking_row()['submitted_at'])
    table(db).insert.assert_not_called()


def test_held_booking_needs_coordinator_confirmation_before_staff_approval(client, db, auth):
    """TC-BOOKINGS-017: ordinary pending approval remains available."""
    prepare(db, booking=booking_row(status='held', hold_confirmed_at=None))
    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})
    assert response.status_code == 409
    assert 'Event Coordinator confirms it' in response.json()['detail']
    table(db).update.assert_not_called()


def test_expired_hold_cannot_be_approved_as_an_ordinary_pending_request(client, db, auth):
    prepare(db, booking=booking_row(status='pending', hold_release_reason='expired'))
    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})
    assert response.status_code == 409
    table(db).update.assert_not_called()


def test_confirmed_hold_can_be_approved_by_staff(client, db, auth):
    prepare(db, booking=booking_row(status='held',
        hold_confirmed_by='cccccccc-cccc-4ccc-8ccc-cccccccccccc',
        hold_confirmed_at='2026-11-10T00:00:00+00:00'))
    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'confirmed'


def test_only_the_trusted_composite_can_record_a_confirmed_hold(client, db, monkeypatch):
    assigned = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
    monkeypatch.setenv('ASSIGNMENT_SERVICE_SECRET', 'test-service-token')
    held = booking_row(status='held', hold_expires_at='2099-01-01T00:00:00+00:00')
    prepare(db, booking=held)
    path = f'/internal/bookings/{BOOKING_ID}/confirm-hold'
    body = {'coordinator_id': assigned}
    forbidden = client.post(path, json=body)
    assert forbidden.status_code == 403
    table(db).update.assert_not_called()

    prepare(db, booking=held)
    update = table(db).update.return_value
    update.is_.return_value = update
    update.gt.return_value = update
    update.execute.return_value = SimpleNamespace(data=[{
        **held, 'hold_confirmed_by': assigned,
        'hold_confirmed_at': '2026-11-10T00:00:00+00:00',
    }])
    allowed = client.post(path, json=body, headers={'X-Assignment-Service-Token': 'test-service-token'})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()['hold_confirmed_by'] == assigned


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
    # Invalid means Supabase rejected it. An error with no verdict is a 503
    # (TC-BOOKINGS-477), not a dead session.
    auth.auth.get_user.side_effect = AuthApiError('invalid JWT', 403, None)
    refused = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'bad'})
    assert refused.status_code == 401
    assert refused.json() == {'detail': 'Not authenticated'}
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
    # S-76: Venue Staff are told whose booking it is and when it occupies the venue.
    assert response.json()['detail'] == (
        "Can't confirm this booking: it overlaps Alumni networking evening (confirmed), "
        'which occupies Studio B on 12 Nov 2026 from 10:00 to 12:00.'
    )
    table(db).update.assert_not_called()


def test_overlap_lookup_uses_half_open_same_venue_and_date_window(client, db, auth):
    prepare(db, conflicts=[])

    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})

    assert response.status_code == 200
    query = table(db).select.return_value
    assert ('venue_id', booking_row()['venue_id']) in [call.args for call in query.eq.call_args_list]
    assert ('booking_date', booking_row()['booking_date']) in [call.args for call in query.eq.call_args_list]
    query.in_.assert_called_once_with('status', ['held', 'confirmed'])
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
        SimpleNamespace(data=[]),  # S-30: no block that day
        SimpleNamespace(data=[conflict]),
    ]
    update.execute.side_effect = ExclusionViolation('private constraint detail')

    response = client.post(PATH, json={'decision': 'approved'}, cookies={'sb_access_token': 'token'})

    assert response.status_code == 409
    # S-76: Venue Staff are told whose booking it is and when it occupies the venue.
    assert response.json()['detail'] == (
        "Can't confirm this booking: it overlaps Alumni networking evening (confirmed), "
        'which occupies Studio B on 12 Nov 2026 from 10:00 to 12:00.'
    )
