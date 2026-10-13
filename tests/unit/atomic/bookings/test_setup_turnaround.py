"""S-75: TC-BOOKINGS-039 to 041, the venue's setup/turnaround gap.

The fake database answers whatever it is told, so each case checks the
widened bounds the query asks for and answers as the real table would for
those bounds.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import BOOKING, BOOKING_ID, app, booking_row, database_module, lookups, table

STAFF = 'abababab-abab-4bab-8bab-abababababab'
COOKIE = {'sb_access_token': 'verified-token'}
GAP = {'setup_minutes': 30, 'turnaround_minutes': 45}
A = booking_row(id='aaaaaaaa-0000-4000-8000-00000000000a', status='confirmed',
                booking_date='2026-11-12', start_time='10:00:00', end_time='12:00:00')
IN_USE = ('Studio B is already confirmed on 12 Nov 2026 from 10:00 to 12:00. '
          'With 30 min setup and 45 min turnaround it is in use until 12:45.')


@pytest.fixture
def auth():
    fake = MagicMock()
    fake.auth.get_user.return_value.user = SimpleNamespace(id=STAFF, app_metadata={'role': 'venue_staff'})
    app.dependency_overrides[database_module.get_auth] = lambda: fake
    yield fake
    app.dependency_overrides.pop(database_module.get_auth, None)


def clashes(start, end, gap_minutes):
    """Whether A clashes with start-end, by the rule the query encodes."""
    return '10:00:00' < _add(end, gap_minutes) and '12:00:00' > _add(start, -gap_minutes)


def _add(value, minutes):
    hours, mins = map(int, value[:5].split(':'))
    total = max(0, min(24 * 60, hours * 60 + mins + minutes))
    return f'{total // 60:02d}:{total % 60:02d}:00'


# --- TC-BOOKINGS-039 -------------------------------------------------------
@pytest.mark.parametrize('start, end', [('12:30', '13:00'), ('13:15', '14:00'), ('08:00', '08:45'), ('07:30', '08:45')])
def test_a_request_inside_the_gap_is_refused_and_says_why(client, db, start, end):
    expected_clash = clashes(f'{start}:00', f'{end}:00', 75)
    query = lookups(db, [A] if expected_clash else [], [])
    table(db).insert.return_value.execute.return_value = MagicMock(data=[booking_row(start_time=start, end_time=end)])

    response = client.post('/bookings', params=GAP, json={**BOOKING, 'booking_date': '2026-11-12',
                                                          'start_time': start, 'end_time': end})

    query.lt.assert_called_once_with('start_time', _add(f'{end}:00', 75))
    query.gt.assert_called_once_with('end_time', _add(f'{start}:00', -75))
    if start == '12:30':
        assert response.status_code == 409
        assert response.json() == {'detail': IN_USE}
        table(db).insert.assert_not_called()
    else:
        assert response.status_code == 201, response.text


def test_without_the_venue_times_the_rule_is_as_before(client, db):
    query = lookups(db, [], [])
    table(db).insert.return_value.execute.return_value = MagicMock(data=[booking_row()])

    response = client.post('/bookings', json={**BOOKING, 'start_time': '12:30', 'end_time': '13:00'})

    assert response.status_code == 201
    query.lt.assert_called_once_with('start_time', '13:00:00')
    query.gt.assert_called_once_with('end_time', '12:30:00')


def test_a_held_neighbour_is_named_as_held(client, db):
    lookups(db, [{**A, 'status': 'held'}], [])

    response = client.post('/bookings', params=GAP, json={**BOOKING, 'start_time': '12:30', 'end_time': '13:00'})

    assert response.status_code == 409
    assert response.json()['detail'].startswith('Studio B is already tentatively held on 12 Nov 2026 from 10:00 to 12:00.')


@pytest.mark.parametrize('params', [{'setup_minutes': -1}, {'turnaround_minutes': 'x'}])
def test_bad_venue_times_are_refused(client, db, params):
    assert client.post('/bookings', params=params, json=BOOKING).status_code == 422
    table(db).insert.assert_not_called()


def test_the_gap_is_clamped_to_the_day(client, db):
    query = lookups(db, [], [])
    table(db).insert.return_value.execute.return_value = MagicMock(data=[booking_row()])

    client.post('/bookings', params={'setup_minutes': 600, 'turnaround_minutes': 600},
                json={**BOOKING, 'start_time': '09:00', 'end_time': '12:00'})

    query.lt.assert_called_once_with('start_time', '24:00:00')
    query.gt.assert_called_once_with('end_time', '00:00:00')


# --- TC-BOOKINGS-040 -------------------------------------------------------
B = booking_row(booking_date='2026-11-12', start_time='12:30:00', end_time='14:00:00')


@pytest.mark.parametrize('action, body', [('hold', None), ('decision', {'decision': 'approved'})])
def test_holds_and_confirmations_use_the_same_gap(client, db, auth, action, body):
    query = lookups(db, [B], [A], [])

    request_body = {'expires_at': '2099-11-12T10:00:00+08:00'} if action == 'hold' else body
    response = client.post(f'/bookings/{BOOKING_ID}/{action}', params=GAP, json=request_body, cookies=COOKIE)

    # S-76 (TC-BOOKINGS-042): Venue Staff get the booking in the way and its
    # whole occupied period instead of IN_USE.
    verb = 'hold' if action == 'hold' else 'confirm'
    assert response.status_code == 409
    assert response.json() == {'detail': (
        f"Can't {verb} this booking: it overlaps Alumni networking evening (confirmed), "
        'which occupies Studio B on 12 Nov 2026 from 09:30 to 12:45 '
        '(event 10:00–12:00, 30 min setup, 45 min turnaround).'
    )}
    query.neq.assert_called_once_with('id', BOOKING_ID)
    query.lt.assert_called_once_with('start_time', '15:15:00')
    query.gt.assert_called_once_with('end_time', '11:15:00')
    table(db).update.assert_not_called()


@pytest.mark.parametrize('action, body, status', [
    ('hold', None, 'held'), ('decision', {'decision': 'approved'}, 'confirmed'),
])
def test_without_the_venue_times_holds_and_confirmations_succeed(client, db, auth, action, body, status):
    query = lookups(db, [B], [], [])
    update = table(db).update.return_value
    update.eq.return_value = update
    update.in_.return_value = update
    update.execute.return_value = SimpleNamespace(data=[{**B, 'status': status}])

    request_body = {'expires_at': '2099-11-12T10:00:00+08:00'} if action == 'hold' else body
    response = client.post(f'/bookings/{BOOKING_ID}/{action}', json=request_body, cookies=COOKIE)

    assert response.status_code == 200, response.text
    query.lt.assert_called_once_with('start_time', '14:00:00')


def test_confirming_a_held_booking_never_clashes_with_itself(client, db, auth):
    held = {**B, 'status': 'held'}
    query = lookups(db, [held], [], [])
    update = table(db).update.return_value
    update.eq.return_value = update
    update.in_.return_value = update
    update.execute.return_value = SimpleNamespace(data=[{**held, 'status': 'confirmed'}])

    response = client.post(f'/bookings/{BOOKING_ID}/decision', params=GAP,
                           json={'decision': 'approved'}, cookies=COOKIE)

    assert response.status_code == 200, response.text
    query.neq.assert_called_once_with('id', BOOKING_ID)


# --- TC-BOOKINGS-041 -------------------------------------------------------
def test_a_booking_is_readable_by_id(client, db):
    lookups(db, [A], [])

    found = client.get(f'/bookings/{A["id"]}')
    missing = client.get('/bookings/99999999-0000-4000-8000-000000000009')

    assert found.status_code == 200
    assert found.json()['id'] == A['id']
    assert missing.status_code == 404
    assert missing.json() == {'detail': 'Booking not found'}
