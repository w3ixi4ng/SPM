"""S-76: TC-BOOKINGS-042 and 043, booking conflicts incl. setup and turnaround.

Venue Staff are told which booking blocks an approval or hold and when it
occupies the venue, and the composite can read every live booking from a
date for the clashes to review.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import BOOKING_ID, app, booking_row, database_module, lookups, table

STAFF = 'abababab-abab-4bab-8bab-abababababab'
COOKIE = {'sb_access_token': 'verified-token'}
GAP = {'setup_minutes': 30, 'turnaround_minutes': 45}
A = booking_row(id='aaaaaaaa-0000-4000-8000-00000000000a', status='confirmed', event_name='Alumni talk',
                booking_date='2026-11-12', start_time='10:00:00', end_time='12:00:00')
B = booking_row(event_name='Board lunch', booking_date='2026-11-12', start_time='12:30:00', end_time='14:00:00')
OCCUPIED = ('it overlaps Alumni talk (confirmed), which occupies Studio B on 12 Nov 2026 '
            'from 09:30 to 12:45 (event 10:00–12:00, 30 min setup, 45 min turnaround).')


@pytest.fixture
def auth():
    fake = MagicMock()
    fake.auth.get_user.return_value.user = SimpleNamespace(id=STAFF, app_metadata={'role': 'venue_staff'})
    app.dependency_overrides[database_module.get_auth] = lambda: fake
    yield fake
    app.dependency_overrides.pop(database_module.get_auth, None)


def approve(client, params=GAP):
    return client.post(f'/bookings/{BOOKING_ID}/decision', params=params,
                       json={'decision': 'approved'}, cookies=COOKIE)


# --- TC-BOOKINGS-042 -------------------------------------------------------
def test_a_refused_approval_names_the_booking_and_its_occupied_period(client, db, auth):
    lookups(db, [B], [A], [])

    response = approve(client)

    assert response.status_code == 409
    assert response.json() == {'detail': f"Can't confirm this booking: {OCCUPIED}"}
    table(db).update.assert_not_called()


def test_a_refused_hold_says_the_same(client, db, auth):
    lookups(db, [B], [A], [])

    response = client.post(f'/bookings/{BOOKING_ID}/hold', params=GAP, json={'expires_at': '2099-11-12T10:00:00+08:00'}, cookies=COOKIE)

    assert response.status_code == 409
    assert response.json() == {'detail': f"Can't hold this booking: {OCCUPIED}"}
    table(db).update.assert_not_called()


def test_a_held_booking_in_the_way_is_named_as_tentatively_held(client, db, auth):
    lookups(db, [B], [{**A, 'status': 'held'}], [])

    response = approve(client)

    assert response.json()['detail'] == (
        "Can't confirm this booking: it overlaps Alumni talk (tentatively held), which occupies "
        'Studio B on 12 Nov 2026 from 09:30 to 12:45 (event 10:00–12:00, 30 min setup, 45 min turnaround).'
    )


def test_with_no_setup_or_turnaround_the_occupied_period_is_the_event(client, db, auth):
    lookups(db, [B], [{**A, 'start_time': '12:00:00', 'end_time': '13:00:00'}], [])

    response = approve(client, params={'setup_minutes': 0, 'turnaround_minutes': 0})

    assert response.status_code == 409
    assert response.json()['detail'] == (
        "Can't confirm this booking: it overlaps Alumni talk (confirmed), "
        'which occupies Studio B on 12 Nov 2026 from 12:00 to 13:00.'
    )


def test_a_race_lost_at_the_database_gives_the_same_message(client, db, auth):
    class ExclusionViolation(Exception):
        code = '23P01'

    # The booking, no overlap yet, no block, then the overlap re-read after
    # the exclusion constraint refuses the update.
    lookups(db, [B], [], [], [A])
    update = table(db).update.return_value
    update.eq.return_value = update
    update.in_.return_value = update
    update.execute.side_effect = ExclusionViolation('private constraint detail')

    response = approve(client)

    assert response.status_code == 409
    assert response.json() == {'detail': f"Can't confirm this booking: {OCCUPIED}"}
    assert 'private' not in response.text


# --- TC-BOOKINGS-043 -------------------------------------------------------
def test_every_live_booking_from_a_date_is_listed_at_once(client, db):
    query = lookups(db, [A, B])

    response = client.get('/bookings', params={'status': 'live', 'from': '2026-11-10'})

    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()] == [A['id'], B['id']]
    query.in_.assert_called_once_with('status', ['held', 'confirmed'])
    query.gte.assert_called_once_with('booking_date', '2026-11-10')
    query.eq.assert_not_called()
    assert [call.args[0] for call in query.order.call_args_list] == ['venue_id', 'booking_date', 'start_time']


def test_a_live_list_needs_a_start_date(client, db):
    lookups(db)

    response = client.get('/bookings', params={'status': 'live'})

    assert response.status_code == 422
    table(db).select.assert_not_called()


def test_a_live_list_can_be_narrowed_to_one_venue(client, db):
    query = lookups(db, [A])

    response = client.get('/bookings', params={'status': 'live', 'from': '2026-11-10', 'venue_id': A['venue_id']})

    assert response.status_code == 200
    query.eq.assert_called_once_with('venue_id', A['venue_id'])
    query.gte.assert_called_once_with('booking_date', '2026-11-10')
