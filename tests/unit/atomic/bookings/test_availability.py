"""S-30: exclusive holds, venue blocks and the calendar's lookups."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import BOOKING, app, booking_row, database_module, lookups, table

STAFF = 'abababab-abab-4bab-8bab-abababababab'
STUDIO_B = BOOKING['venue_id']
BLOCK_ID = '77777777-7777-4777-8777-777777777777'
COOKIE = {'sb_access_token': 'verified-token'}

BLOCK = {
    'venue_id': STUDIO_B,
    'venue_name': 'Studio B',
    'start_date': '2026-11-13',
    'end_date': '2026-11-16',
    'reason': 'maintenance',
    'note': '  Ceiling repair  ',
}


def block_row(**changes):
    row = {
        **BLOCK,
        'note': 'Ceiling repair',
        'id': BLOCK_ID,
        'created_by': STAFF,
        'created_at': '2026-11-10T01:00:00+00:00',
    }
    row.update(changes)
    return row


def existing(status, start='10:00:00', end='12:00:00', **changes):
    return booking_row(
        id='55555555-5555-4555-8555-555555555555',
        status=status, booking_date='2026-11-12', start_time=start, end_time=end, **changes,
    )


@pytest.fixture
def auth():
    fake = MagicMock()
    fake.auth.get_user.return_value.user = SimpleNamespace(id=STAFF, app_metadata={'role': 'venue_staff'})
    app.dependency_overrides[database_module.get_auth] = lambda: fake
    yield fake
    app.dependency_overrides.pop(database_module.get_auth, None)


def echo_insert(db):
    insert = table(db).insert
    insert.return_value.execute.side_effect = lambda: MagicMock(
        data=[{'id': BLOCK_ID, **insert.call_args.args[0]}]
    )


OVERLAPS = [('10:30', '11:30'), ('09:00', '11:00'), ('11:00', '13:00'), ('09:00', '13:00')]


# --- TC-BOOKINGS-025 ------------------------------------------------------
@pytest.mark.parametrize('start, end', OVERLAPS)
def test_a_request_overlapping_a_confirmed_booking_is_refused(client, db, start, end):
    lookups(db, [existing('confirmed')], [])

    response = client.post('/bookings', json={**BOOKING, 'start_time': start, 'end_time': end})

    assert response.status_code == 409
    assert response.json() == {'detail': 'Studio B is already confirmed on 12 Nov 2026 from 10:00 to 12:00.'}
    table(db).insert.assert_not_called()


# --- TC-BOOKINGS-026 ------------------------------------------------------
@pytest.mark.parametrize('start, end', OVERLAPS)
def test_a_request_overlapping_a_tentative_hold_is_refused(client, db, start, end):
    query = lookups(db, [existing('pending')], [])

    response = client.post('/bookings', json={**BOOKING, 'start_time': start, 'end_time': end})

    assert response.status_code == 409
    assert response.json() == {
        'detail': 'Studio B is already tentatively held on 12 Nov 2026 from 10:00 to 12:00.'
    }
    table(db).insert.assert_not_called()
    eq_calls = [call.args for call in query.eq.call_args_list]
    assert ('venue_id', STUDIO_B) in eq_calls
    assert ('booking_date', '2026-11-12') in eq_calls
    query.in_.assert_called_once_with('status', ['pending', 'confirmed'])
    query.lt.assert_called_once_with('start_time', f'{end}:00')
    query.gt.assert_called_once_with('end_time', f'{start}:00')


# --- TC-BOOKINGS-027 ------------------------------------------------------
@pytest.mark.parametrize('changes', [
    {'start_time': '08:00', 'end_time': '10:00'},
    {'start_time': '12:00', 'end_time': '14:00'},
    {'booking_date': '2026-11-13', 'start_time': '10:30', 'end_time': '11:30'},
    {'venue_id': 'cccccccc-0000-4ccc-8ccc-cccccccccccc', 'start_time': '10:30', 'end_time': '11:30'},
])
def test_slots_that_do_not_overlap_a_live_booking_are_accepted(client, db, changes):
    # The database answers the half-open, pending/confirmed-only lookup: none
    # of these rows overlaps a live booking, so it finds nothing.
    lookups(db, [], [])
    table(db).insert.return_value.execute.return_value = MagicMock(data=[booking_row(**changes)])

    response = client.post('/bookings', json={**BOOKING, **changes})

    assert response.status_code == 201
    assert response.json()['status'] == 'pending'


def test_a_simultaneous_request_that_loses_the_race_is_told_why(client, db):
    class ExclusionViolation(Exception):
        code = '23P01'

    lookups(db, [], [], [existing('pending', '09:00:00', '12:00:00')])
    table(db).insert.return_value.execute.side_effect = ExclusionViolation('private detail')

    response = client.post('/bookings', json=BOOKING)

    assert response.status_code == 409
    assert response.json()['detail'] == 'Studio B is already tentatively held on 12 Nov 2026 from 09:00 to 12:00.'


# --- TC-BOOKINGS-028 ------------------------------------------------------
@pytest.mark.parametrize('day', ['2026-11-13', '2026-11-16'])
def test_a_request_on_a_blocked_day_is_refused(client, db, day):
    query = lookups(db, [], [block_row()])

    response = client.post('/bookings', json={**BOOKING, 'booking_date': day})

    assert response.status_code == 409
    assert response.json() == {'detail': 'Studio B is unavailable from 13 Nov 2026 to 16 Nov 2026.'}
    table(db).insert.assert_not_called()
    query.lte.assert_called_once_with('start_date', day)
    query.gte.assert_called_once_with('end_date', day)


def test_the_day_after_a_block_can_be_requested(client, db):
    lookups(db, [], [])
    table(db).insert.return_value.execute.return_value = MagicMock(data=[booking_row(booking_date='2026-11-17')])

    response = client.post('/bookings', json={**BOOKING, 'booking_date': '2026-11-17'})

    assert response.status_code == 201


# --- TC-BOOKINGS-029 ------------------------------------------------------
def test_a_pending_request_on_a_blocked_day_cannot_be_confirmed(client, db, auth):
    booking = booking_row(booking_date='2026-11-13')
    lookups(db, [booking], [], [block_row(reason='safety')])

    response = client.post(f'/bookings/{booking["id"]}/decision', json={'decision': 'approved'}, cookies=COOKIE)

    assert response.status_code == 409
    assert response.json() == {'detail': 'Studio B is unavailable from 13 Nov 2026 to 16 Nov 2026.'}
    table(db).update.assert_not_called()


def test_a_pending_request_on_a_blocked_day_can_still_be_rejected(client, db, auth):
    booking = booking_row(booking_date='2026-11-13')
    lookups(db, [booking])
    update = table(db).update.return_value
    update.eq.return_value = update
    update.execute.side_effect = lambda: SimpleNamespace(
        data=[booking_row(booking_date='2026-11-13', **table(db).update.call_args.args[0])]
    )

    response = client.post(
        f'/bookings/{booking["id"]}/decision',
        json={'decision': 'rejected', 'reason': 'Venue under maintenance'}, cookies=COOKIE,
    )

    assert response.status_code == 200
    assert response.json()['status'] == 'rejected'


# --- TC-BOOKINGS-030 ------------------------------------------------------
def test_venue_staff_add_a_block(client, db, auth):
    echo_insert(db)

    response = client.post('/blocks', json=BLOCK, cookies=COOKIE)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body['id'] == BLOCK_ID
    assert body['note'] == 'Ceiling repair'
    assert body['created_by'] == STAFF
    assert body['created_at']
    db.schema.return_value.table.assert_called_with('blocks')
    sent = table(db).insert.call_args.args[0]
    assert sent['created_by'] == STAFF
    assert {key: sent[key] for key in ('venue_id', 'start_date', 'end_date', 'reason')} == {
        key: BLOCK[key] for key in ('venue_id', 'start_date', 'end_date', 'reason')
    }


@pytest.mark.parametrize('changes, note', [
    ({'end_date': '2026-11-13'}, 'Ceiling repair'),
    ({'note': '   '}, None),
])
def test_one_day_blocks_and_blank_notes(client, db, auth, changes, note):
    echo_insert(db)

    response = client.post('/blocks', json={**BLOCK, **changes}, cookies=COOKIE)

    assert response.status_code == 201
    assert response.json()['note'] == note


# --- TC-BOOKINGS-031 ------------------------------------------------------
def test_a_block_may_cover_existing_bookings_without_changing_them(client, db, auth):
    echo_insert(db)

    response = client.post('/blocks', json=BLOCK, cookies=COOKIE)

    assert response.status_code == 201
    table(db).update.assert_not_called()
    table(db).select.assert_not_called()


# --- TC-BOOKINGS-032 ------------------------------------------------------
@pytest.mark.parametrize('changes, field, message', [
    ({'end_date': '2026-11-12'}, 'body', 'end_date must be on or after start_date'),
    ({'reason': 'flood'}, 'reason', None),
    ({'reason': 'other', 'note': '  '}, 'body', 'Add a note when the reason is other'),
    ({'created_by': STAFF}, 'created_by', None),
])
def test_invalid_blocks_are_refused_with_a_field_error(client, db, auth, changes, field, message):
    response = client.post('/blocks', json={**BLOCK, **changes}, cookies=COOKIE)

    assert response.status_code == 422
    errors = response.json()['errors']
    assert field in errors
    if message:
        assert message in errors[field]
    table(db).insert.assert_not_called()


def test_a_block_needs_a_venue(client, db, auth):
    body = {key: value for key, value in BLOCK.items() if key != 'venue_id'}
    response = client.post('/blocks', json=body, cookies=COOKIE)

    assert response.status_code == 422
    assert 'venue_id' in response.json()['errors']


def test_only_venue_staff_add_blocks(client, db, auth):
    assert client.post('/blocks', json=BLOCK).status_code == 401

    auth.auth.get_user.return_value.user.app_metadata = {'role': 'event_coordinator'}
    response = client.post('/blocks', json=BLOCK, cookies=COOKIE)

    assert response.status_code == 403
    assert response.json() == {'detail': 'Permission denied'}
    table(db).insert.assert_not_called()


# --- TC-BOOKINGS-033 ------------------------------------------------------
def test_bookings_are_listed_for_one_venue_and_range(client, db):
    rows = [existing('confirmed', '09:00:00', '12:00:00'), existing('pending', '14:00:00', '16:00:00'),
            existing('rejected', '16:00:00', '17:00:00')]
    query = lookups(db, rows)

    response = client.get('/bookings', params={'venue_id': STUDIO_B, 'from': '2026-11-11', 'to': '2026-12-08'})

    assert response.status_code == 200
    assert [row['status'] for row in response.json()] == ['confirmed', 'pending', 'rejected']
    query.eq.assert_called_once_with('venue_id', STUDIO_B)
    query.gte.assert_called_once_with('booking_date', '2026-11-11')
    query.lte.assert_called_once_with('booking_date', '2026-12-08')
    assert [call.args for call in query.order.call_args_list] == [('booking_date',), ('start_time',)]


@pytest.mark.parametrize('params', [
    {'venue_id': STUDIO_B, 'from': '2026-11-11'},
    {'venue_id': STUDIO_B, 'to': '2026-12-08'},
    {'from': '2026-11-11', 'to': '2026-12-08'},
])
def test_a_venue_filter_always_needs_a_range(client, db, params):
    response = client.get('/bookings', params=params)

    assert response.status_code == 422
    assert response.json()['detail'] == 'Filter by venue_id with from and to'
    db.schema.assert_not_called()


# --- TC-BOOKINGS-034 ------------------------------------------------------
def test_blocks_are_listed_for_one_venue_and_range(client, db):
    rows = [block_row(start_date='2026-11-09', end_date='2026-11-11'), block_row()]
    query = lookups(db, rows)

    response = client.get('/blocks', params={'venue_id': STUDIO_B, 'from': '2026-11-11', 'to': '2026-12-08'})

    assert response.status_code == 200
    assert [row['start_date'] for row in response.json()] == ['2026-11-09', '2026-11-13']
    db.schema.return_value.table.assert_called_with('blocks')
    query.eq.assert_called_once_with('venue_id', STUDIO_B)
    # Overlaps the range: starts by its end, ends on or after its start.
    query.lte.assert_called_once_with('start_date', '2026-12-08')
    query.gte.assert_called_once_with('end_date', '2026-11-11')
    query.order.assert_called_once_with('start_date')


def test_blocks_need_a_filter(client, db):
    response = client.get('/blocks')

    assert response.status_code == 422
    assert response.json() == {'detail': 'Filter by venue_id with from and to'}
    db.schema.assert_not_called()


# --- TC-BOOKINGS-035 ------------------------------------------------------
def test_venue_staff_remove_a_block(client, db, auth):
    delete = table(db).delete.return_value.eq.return_value
    delete.execute.side_effect = [MagicMock(data=[block_row()]), MagicMock(data=[])]

    first = client.delete(f'/blocks/{BLOCK_ID}', cookies=COOKIE)
    second = client.delete(f'/blocks/{BLOCK_ID}', cookies=COOKIE)

    assert first.status_code == 204
    assert second.status_code == 404
    assert second.json() == {'detail': 'Block not found'}
    table(db).delete.return_value.eq.assert_called_with('id', BLOCK_ID)


def test_only_venue_staff_remove_blocks(client, db, auth):
    assert client.delete(f'/blocks/{BLOCK_ID}').status_code == 401

    auth.auth.get_user.return_value.user.app_metadata = {'role': 'event_coordinator'}
    assert client.delete(f'/blocks/{BLOCK_ID}', cookies=COOKIE).status_code == 403
    table(db).delete.assert_not_called()
