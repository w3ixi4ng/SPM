"""S-77: timed unavailable periods, TC-BOOKINGS-044..050."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import BOOKING, app, booking_row, database_module, lookups, table

STAFF = '55555555-5555-4555-8555-555555555555'
STUDIO_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
BLOCK_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
COOKIE = {'sb_access_token': 'verified-token'}
GAP = {'setup_minutes': 30, 'turnaround_minutes': 30}
UNAVAILABLE = 'Studio B is unavailable from 13 Nov 2026 09:00 to 14 Nov 2026 17:00.'

PERIOD = {
    'venue_id': STUDIO_B,
    'venue_name': 'Studio B',
    'start_date': '2026-11-13',
    'start_time': '09:00',
    'end_date': '2026-11-14',
    'end_time': '17:00',
    'reason': 'equipment_failure',
    'note': '  Air handling unit down  ',
}

# Period P as the database returns it.
P = {
    **PERIOD,
    'id': BLOCK_ID,
    'start_time': '09:00:00',
    'end_time': '17:00:00',
    'note': 'Air handling unit down',
    'created_by': STAFF,
    'created_at': '2026-11-10T01:00:00+00:00',
}


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


def at_studio_b(**changes):
    return {**BOOKING, 'venue_id': STUDIO_B, **changes}


# --- TC-BOOKINGS-044 ------------------------------------------------------
def test_venue_staff_mark_a_venue_unavailable_for_a_timed_period(client, db, auth):
    echo_insert(db)

    response = client.post('/blocks', json=PERIOD, cookies=COOKIE)

    assert response.status_code == 201, response.text
    body = response.json()
    assert {key: body[key] for key in ('venue_id', 'venue_name', 'start_date', 'end_date', 'reason')} == {
        key: PERIOD[key] for key in ('venue_id', 'venue_name', 'start_date', 'end_date', 'reason')
    }
    assert (body['start_time'], body['end_time']) == ('09:00:00', '17:00:00')
    assert body['note'] == 'Air handling unit down'
    assert body['id'] == BLOCK_ID
    assert body['created_by'] == STAFF
    assert body['created_at']
    table(db).insert.assert_called_once()
    db.schema.return_value.table.assert_called_with('blocks')


def test_a_period_may_fall_within_one_day(client, db, auth):
    echo_insert(db)
    one_day = {**PERIOD, 'start_date': '2026-11-20', 'start_time': '13:00',
               'end_date': '2026-11-20', 'end_time': '15:00', 'reason': 'maintenance'}
    del one_day['note']

    response = client.post('/blocks', json=one_day, cookies=COOKIE)

    assert response.status_code == 201, response.text
    assert response.json()['note'] is None


# --- TC-BOOKINGS-045 ------------------------------------------------------
@pytest.mark.parametrize('changes', [
    {'reason': 'maintenance', 'note': None},
    {'reason': 'equipment_failure', 'note': None},
    {'reason': 'renovation', 'note': None},
    {'reason': 'safety', 'note': None},
    {'reason': 'other', 'note': 'Fire alarm testing'},
])
def test_every_story_reason_is_accepted(client, db, auth, changes):
    echo_insert(db)

    response = client.post('/blocks', json={**PERIOD, **changes}, cookies=COOKIE)

    assert response.status_code == 201, response.text
    assert response.json()['reason'] == changes['reason']


@pytest.mark.parametrize('note', [None, '   '])
def test_other_needs_a_description(client, db, auth, note):
    response = client.post('/blocks', json={**PERIOD, 'reason': 'other', 'note': note}, cookies=COOKIE)

    assert response.status_code == 422
    assert response.json()['errors']['body'] == 'Value error, Add a description when the reason is other'
    table(db).insert.assert_not_called()


@pytest.mark.parametrize('reason', ['internal_activity', 'flood'])
def test_a_reason_outside_the_story_is_refused(client, db, auth, reason):
    response = client.post('/blocks', json={**PERIOD, 'reason': reason}, cookies=COOKIE)

    assert response.status_code == 422
    assert 'reason' in response.json()['errors']
    table(db).insert.assert_not_called()


# --- TC-BOOKINGS-046 ------------------------------------------------------
@pytest.mark.parametrize('missing', ['start_time', 'end_time'])
def test_a_period_needs_both_times(client, db, auth, missing):
    body = {key: value for key, value in PERIOD.items() if key != missing}

    response = client.post('/blocks', json=body, cookies=COOKIE)

    assert response.status_code == 422
    assert missing in response.json()['errors']
    table(db).insert.assert_not_called()


@pytest.mark.parametrize('changes', [
    {'end_date': '2026-11-13', 'end_time': '08:00'},
    {'end_date': '2026-11-13', 'end_time': '09:00'},
    {'end_date': '2026-11-12'},
])
def test_a_period_must_end_after_it_starts(client, db, auth, changes):
    response = client.post('/blocks', json={**PERIOD, **changes}, cookies=COOKIE)

    assert response.status_code == 422
    assert response.json()['errors']['body'] == 'Value error, The period must end after it starts'
    table(db).insert.assert_not_called()


def test_a_period_cannot_carry_who_created_it(client, db, auth):
    response = client.post('/blocks', json={**PERIOD, 'created_by': STAFF}, cookies=COOKIE)

    assert response.status_code == 422
    table(db).insert.assert_not_called()


def test_only_venue_staff_mark_periods(client, db, auth):
    assert client.post('/blocks', json=PERIOD).json() == {'detail': 'Not authenticated'}

    auth.auth.get_user.return_value.user.app_metadata = {'role': 'event_coordinator'}
    response = client.post('/blocks', json=PERIOD, cookies=COOKIE)

    assert response.status_code == 403
    assert response.json() == {'detail': 'Permission denied'}
    table(db).insert.assert_not_called()


# --- TC-BOOKINGS-047 ------------------------------------------------------
@pytest.mark.parametrize('day, start, end', [
    ('2026-11-13', '14:00', '16:00'),
    ('2026-11-13', '07:00', '08:45'),
    ('2026-11-14', '17:15', '19:00'),
])
def test_a_request_overlapping_the_period_is_refused(client, db, day, start, end):
    query = lookups(db, [], [P])

    response = client.post('/bookings', params=GAP,
                           json=at_studio_b(booking_date=day, start_time=start, end_time=end))

    assert response.status_code == 409
    assert response.json() == {'detail': UNAVAILABLE}
    table(db).insert.assert_not_called()
    query.lte.assert_called_once_with('start_date', day)
    query.gte.assert_called_once_with('end_date', day)


@pytest.mark.parametrize('day, start, end', [
    ('2026-11-13', '07:00', '08:30'),
    ('2026-11-14', '17:30', '19:00'),
    ('2026-11-12', '10:00', '12:00'),
])
def test_a_request_clear_of_the_period_is_accepted(client, db, day, start, end):
    # The day before has no period touching it; the others touch P's days
    # but their occupied windows only meet it.
    lookups(db, [], [] if day == '2026-11-12' else [P])
    table(db).insert.return_value.execute.return_value = MagicMock(
        data=[booking_row(venue_id=STUDIO_B, booking_date=day, start_time=f'{start}:00', end_time=f'{end}:00')]
    )

    response = client.post('/bookings', params=GAP,
                           json=at_studio_b(booking_date=day, start_time=start, end_time=end))

    assert response.status_code == 201, response.text


# --- TC-BOOKINGS-048 ------------------------------------------------------
def test_a_hold_overlapping_the_period_is_refused(client, db, auth):
    r1 = booking_row(venue_id=STUDIO_B, booking_date='2026-11-13', start_time='14:00:00', end_time='16:00:00')
    lookups(db, [r1], [], [P])

    response = client.post(f'/bookings/{r1["id"]}/hold', params=GAP, json={'expires_at': '2099-11-12T10:00:00+08:00'}, cookies=COOKIE)

    assert response.status_code == 409
    assert response.json() == {'detail': UNAVAILABLE}
    table(db).update.assert_not_called()


def test_a_hold_that_ends_as_the_period_starts_is_placed(client, db, auth):
    r2 = booking_row(venue_id=STUDIO_B, booking_date='2026-11-13', start_time='07:00:00', end_time='08:30:00')
    lookups(db, [r2], [], [P])
    update = table(db).update.return_value
    update.eq.return_value = update
    update.execute.side_effect = lambda: SimpleNamespace(
        data=[{**r2, **table(db).update.call_args.args[0]}]
    )

    response = client.post(f'/bookings/{r2["id"]}/hold', params=GAP, json={'expires_at': '2099-11-12T10:00:00+08:00'}, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'held'


# --- TC-BOOKINGS-049 ------------------------------------------------------
def test_a_confirmation_overlapping_the_period_is_refused(client, db, auth):
    held = booking_row(venue_id=STUDIO_B, booking_date='2026-11-13', start_time='14:00:00',
                       end_time='16:00:00', status='held', held_by=STAFF, held_at='2026-11-10T00:00:00+00:00')
    lookups(db, [held], [], [P])

    response = client.post(f'/bookings/{held["id"]}/decision', json={'decision': 'approved'}, cookies=COOKIE)

    assert response.status_code == 409
    assert response.json() == {'detail': UNAVAILABLE}
    table(db).update.assert_not_called()


def test_a_held_request_in_the_period_can_still_be_rejected(client, db, auth):
    held = booking_row(venue_id=STUDIO_B, booking_date='2026-11-13', start_time='14:00:00',
                       end_time='16:00:00', status='held', held_by=STAFF, held_at='2026-11-10T00:00:00+00:00')
    lookups(db, [held])
    update = table(db).update.return_value
    update.eq.return_value = update
    update.in_.return_value = update
    update.execute.side_effect = lambda: SimpleNamespace(
        data=[{**held, **table(db).update.call_args.args[0]}]
    )

    response = client.post(
        f'/bookings/{held["id"]}/decision',
        json={'decision': 'rejected', 'reason': 'Air handling unit down'}, cookies=COOKIE,
    )

    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'rejected'


# --- TC-BOOKINGS-050 ------------------------------------------------------
def test_one_period_is_read_by_id(client, db):
    query = lookups(db, [P])

    response = client.get(f'/blocks/{BLOCK_ID}')

    assert response.status_code == 200
    assert (response.json()['start_time'], response.json()['end_time']) == ('09:00:00', '17:00:00')
    query.eq.assert_called_once_with('id', BLOCK_ID)


def test_an_unknown_period_is_a_404(client, db):
    lookups(db, [])

    response = client.get('/blocks/dddddddd-dddd-4ddd-8ddd-000000000000')

    assert response.status_code == 404
    assert response.json() == {'detail': 'Block not found'}


def test_a_period_is_listed_for_a_range_it_touches(client, db):
    # A period that ended exactly at 00:00 on `from` stopped the day before.
    ended_before = {**P, 'id': 'eeeeeeee-0000-4eee-8eee-eeeeeeeeeeee', 'start_date': '2026-11-12',
                    'start_time': '09:00:00', 'end_date': '2026-11-14', 'end_time': '00:00:00'}
    lookups(db, [ended_before, P])

    response = client.get('/blocks', params={'venue_id': STUDIO_B, 'from': '2026-11-14', 'to': '2026-11-30'})

    assert response.status_code == 200
    assert [row['id'] for row in response.json()] == [BLOCK_ID]
    assert response.json()[0]['start_time'] == '09:00:00'
