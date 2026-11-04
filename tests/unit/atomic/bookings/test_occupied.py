"""S-34 reopened: one date's live bookings and blocks across every venue,
for the venue filter. TC-BOOKINGS-460 and 461."""
import pytest

from .conftest import booking_row, lookups, table

STAFF = '55555555-5555-4555-8555-555555555555'
V1 = '11111111-1111-4111-8111-000000000001'
V2 = '11111111-1111-4111-8111-000000000002'
V3 = '11111111-1111-4111-8111-000000000003'


def block(block_id, venue_id, start_date, start_time, end_date, end_time):
    return {
        'id': block_id, 'venue_id': venue_id, 'venue_name': 'Studio B',
        'start_date': start_date, 'start_time': start_time, 'end_date': end_date, 'end_time': end_time,
        'reason': 'maintenance', 'note': None, 'created_by': STAFF,
        'created_at': '2026-11-01T00:00:00+00:00',
    }


P = block('aaaaaaaa-0000-4000-8000-00000000000c', V1, '2026-11-11', '18:00:00', '2026-11-12', '14:00:00')
Q = block('aaaaaaaa-0000-4000-8000-00000000000a', V2, '2026-11-12', '09:00:00', '2026-11-12', '10:00:00')
R = block('aaaaaaaa-0000-4000-8000-00000000000b', V3, '2026-11-11', '08:00:00', '2026-11-12', '00:00:00')
DAY = {'from': '2026-11-12', 'to': '2026-11-12'}


# --- TC-BOOKINGS-460 -------------------------------------------------------
def test_live_bookings_can_be_bounded_by_to_as_well_as_from(client, db):
    held = booking_row(status='held', booking_date='2026-11-12')
    query = lookups(db, [held])

    response = client.get('/bookings', params={'status': 'live', **DAY})

    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()] == [held['id']]
    query.in_.assert_called_once_with('status', ['held', 'confirmed'])
    query.gte.assert_called_once_with('booking_date', '2026-11-12')
    query.lte.assert_called_once_with('booking_date', '2026-11-12')
    query.eq.assert_not_called()


def test_a_live_list_without_to_is_unchanged(client, db):
    query = lookups(db, [])

    response = client.get('/bookings', params={'status': 'live', 'from': '2026-11-12'})

    assert response.status_code == 200
    query.lte.assert_not_called()


def test_a_live_list_ending_before_it_starts_is_refused(client, db):
    lookups(db)

    response = client.get('/bookings', params={'status': 'live', 'from': '2026-11-12', 'to': '2026-11-11'})

    assert response.status_code == 422
    table(db).select.assert_not_called()


# --- TC-BOOKINGS-461 -------------------------------------------------------
def test_blocks_can_be_listed_for_a_range_across_venues(client, db):
    query = lookups(db, [P, Q, R])

    response = client.get('/blocks', params=DAY)

    assert response.status_code == 200, response.text
    # R ends at 00:00 that morning: it stopped the day before.
    assert [row['id'] for row in response.json()] == [P['id'], Q['id']]
    query.lte.assert_called_once_with('start_date', '2026-11-12')
    query.gte.assert_called_once_with('end_date', '2026-11-12')
    query.eq.assert_not_called()


def test_one_venues_blocks_are_unchanged(client, db):
    query = lookups(db, [P])

    response = client.get('/blocks', params={'venue_id': V1, **DAY})

    assert response.status_code == 200
    query.eq.assert_called_once_with('venue_id', V1)


@pytest.mark.parametrize('params', [{}, {'from': '2026-11-12'}, {'to': '2026-11-12'},
                                    {'from': '2026-11-12', 'to': '2026-11-11'}])
def test_blocks_always_need_a_range(client, db, params):
    lookups(db)

    response = client.get('/blocks', params=params)

    assert response.status_code == 422
    table(db).select.assert_not_called()
