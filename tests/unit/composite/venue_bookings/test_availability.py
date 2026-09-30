"""S-30: the availability calendar and venue blocks, TC-VENUEBOOKINGS-035..044."""
from unittest.mock import AsyncMock

import httpx
import pytest

from .conftest import VENUE, VENUE_ID, fake_response, me, requested

BLOCK_ID = '77777777-7777-4777-8777-777777777777'
RANGE = {'venue_id': VENUE_ID, 'from': '2026-11-11', 'to': '2026-12-08'}
COOKIE = {'sb_access_token': 'token'}

BOOKINGS = [
    {'id': 'b1', 'status': 'confirmed', 'booking_date': '2026-11-12', 'start_time': '09:00:00',
     'end_time': '12:00:00', 'event_id': 'e1', 'event_name': 'Alumni night',
     'coordinator_name': 'Grace Hopper', 'coordinator_email': 'grace@example.com'},
    {'id': 'b2', 'status': 'pending', 'booking_date': '2026-11-12', 'start_time': '14:00:00',
     'end_time': '16:00:00', 'event_id': 'e2', 'event_name': 'Board dinner',
     'coordinator_name': 'Ada Lovelace', 'coordinator_email': 'ada@example.com'},
    {'id': 'b3', 'status': 'rejected', 'booking_date': '2026-11-12', 'start_time': '16:00:00',
     'end_time': '17:00:00', 'event_id': 'e3', 'event_name': 'Rejected talk',
     'coordinator_name': 'Alan Turing', 'coordinator_email': 'alan@example.com'},
]
BLOCKS = [{'id': BLOCK_ID, 'venue_id': VENUE_ID, 'venue_name': 'Studio B', 'start_date': '2026-11-13',
           'end_date': '2026-11-16', 'reason': 'maintenance', 'note': 'Ceiling repair',
           'created_by': 'abababab-abab-4bab-8bab-abababababab', 'created_at': '2026-11-10T01:00:00+00:00'}]

BLOCK_REQUEST = {'venue_id': VENUE_ID, 'start_date': '2026-11-13', 'end_date': '2026-11-16',
                 'reason': 'maintenance', 'note': 'Ceiling repair'}


def lists(services, bookings=None, blocks=None):
    answers = {
        '/bookings': bookings or fake_response(200, BOOKINGS),
        '/blocks': blocks or fake_response(200, BLOCKS),
    }

    async def get(path, **kwargs):
        return answers[path]

    services.bookings.get = AsyncMock(side_effect=get)


EXPECTED_ENTRIES = [
    {'state': 'confirmed', 'start_date': '2026-11-12', 'end_date': '2026-11-12',
     'start_time': '09:00:00', 'end_time': '12:00:00'},
    {'state': 'held', 'start_date': '2026-11-12', 'end_date': '2026-11-12',
     'start_time': '14:00:00', 'end_time': '16:00:00'},
    {'state': 'blocked', 'start_date': '2026-11-13', 'end_date': '2026-11-16',
     'start_time': None, 'end_time': None, 'reason': 'maintenance'},
]


# --- TC-VENUEBOOKINGS-035 -------------------------------------------------
def test_a_coordinator_gets_a_venues_availability_for_a_range(client, services):
    lists(services)

    response = client.get('/venue-bookings/availability', params=RANGE, cookies=COOKIE)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        'venue_id': VENUE_ID,
        'venue_name': 'Studio B',
        'from': '2026-11-11',
        'to': '2026-12-08',
        'operating_hours': VENUE['operating_hours'],
        'entries': EXPECTED_ENTRIES,
    }
    for private in ('Alumni night', 'Grace Hopper', 'grace@example.com', 'Ceiling repair', BLOCK_ID, '"b1"', '"e1"'):
        assert private not in response.text
    params = {'venue_id': VENUE_ID, 'from': '2026-11-11', 'to': '2026-12-08'}
    assert [call.args[0] for call in services.bookings.get.call_args_list] == ['/bookings', '/blocks']
    assert all(call.kwargs['params'] == params for call in services.bookings.get.call_args_list)
    assert services.venues.get.call_args.args == (f'/venues/{VENUE_ID}',)
    assert services.venues.get.call_args.kwargs['cookies'] == COOKIE


# --- TC-VENUEBOOKINGS-036 -------------------------------------------------
def test_venue_staff_also_get_what_they_need_to_remove_a_block(client, services):
    services.user = me('venue_staff')
    lists(services)

    entries = client.get('/venue-bookings/availability', params=RANGE).json()['entries']

    assert entries[:2] == EXPECTED_ENTRIES[:2]
    assert entries[2] == {**EXPECTED_ENTRIES[2], 'id': BLOCK_ID, 'note': 'Ceiling repair'}
    assert 'Alumni night' not in str(entries)


# --- TC-VENUEBOOKINGS-037 -------------------------------------------------
@pytest.mark.parametrize('role', ['event_organiser', 'technical_support', 'admin'])
def test_other_roles_cannot_view_the_calendar(client, services, role):
    services.user = me(role)
    lists(services)

    response = client.get('/venue-bookings/availability', params=RANGE)

    assert response.status_code == 403
    assert response.json() == {'detail': 'Permission denied'}
    services.venues.get.assert_not_called()
    services.bookings.get.assert_not_called()


def test_no_session_cannot_view_the_calendar(client, services):
    services.user = fake_response(401, {'detail': 'Not authenticated'})
    lists(services)

    response = client.get('/venue-bookings/availability', params=RANGE)

    assert response.status_code == 401
    assert response.json() == {'detail': 'Not authenticated'}
    services.bookings.get.assert_not_called()


@pytest.mark.parametrize('changes, field', [
    ({'from': None}, 'from'),
    ({'to': None}, 'to'),
    ({'from': '12-11-2026'}, 'from'),
    ({'venue_id': 'not-a-uuid'}, 'venue_id'),
])
def test_a_malformed_range_is_refused(client, services, changes, field):
    lists(services)
    params = {key: value for key, value in {**RANGE, **changes}.items() if value is not None}

    response = client.get('/venue-bookings/availability', params=params)

    assert response.status_code == 422
    body = response.json()
    assert body['detail'] == 'Please check the details you entered'
    assert any(field in key for key in body['errors'])
    services.bookings.get.assert_not_called()


def test_the_end_date_must_not_be_before_the_start_date(client, services):
    lists(services)

    response = client.get('/venue-bookings/availability', params={**RANGE, 'from': '2026-11-20', 'to': '2026-11-12'})

    assert response.status_code == 422
    assert response.json()['errors'] == {'to': 'The end date must be on or after the start date'}
    services.bookings.get.assert_not_called()


# --- TC-VENUEBOOKINGS-038 -------------------------------------------------
def test_an_unknown_venue_is_a_404(client, services):
    services.venue = fake_response(404, {'detail': 'Venue not found'})
    lists(services)

    response = client.get('/venue-bookings/availability', params=RANGE)

    assert response.status_code == 404
    assert response.json() == {'detail': 'Venue not found'}
    services.bookings.get.assert_not_called()


@pytest.mark.parametrize('which', ['bookings', 'blocks'])
def test_a_bookings_failure_is_a_502_never_an_empty_calendar(client, services, which):
    failed = fake_response(500, {'detail': 'Booking storage unavailable'})
    lists(services, **{which: failed})

    response = client.get('/venue-bookings/availability', params=RANGE)

    assert response.status_code == 502
    assert response.json() == {'detail': 'Bookings service unavailable'}


def test_an_unreachable_venues_service_is_named(client, services):
    services.venues.get = AsyncMock(side_effect=httpx.ConnectError('refused'))
    lists(services)

    response = client.get('/venue-bookings/availability', params=RANGE)

    assert response.status_code == 502
    assert response.json() == {'detail': 'Venues service unavailable'}


# --- TC-VENUEBOOKINGS-039 -------------------------------------------------
def test_a_venue_with_nothing_on_it_returns_no_entries(client, services):
    lists(services, fake_response(200, []), fake_response(200, []))

    body = client.get('/venue-bookings/availability', params=RANGE).json()

    assert body['entries'] == []
    assert body['operating_hours'] == VENUE['operating_hours']


# --- TC-VENUEBOOKINGS-040 -------------------------------------------------
@pytest.mark.parametrize('detail', [
    'Studio B is already confirmed on 12 Nov 2026 from 10:00 to 12:00.',
    'Studio B is already tentatively held on 12 Nov 2026 from 10:00 to 12:00.',
    'Studio B is unavailable from 13 Nov 2026 to 16 Nov 2026.',
])
def test_a_conflicting_requests_409_reaches_the_coordinator_unchanged(client, services, detail):
    services.bookings.post = AsyncMock(return_value=fake_response(409, {'detail': detail}))

    response = client.post('/venue-bookings', json=requested())

    assert response.status_code == 409
    assert response.json() == {'detail': detail}


def test_an_unidentified_409_from_bookings_is_still_a_502(client, services):
    services.bookings.post = AsyncMock(return_value=fake_response(409, {'detail': 'private diagnostic'}))

    response = client.post('/venue-bookings', json=requested())

    assert response.status_code == 502
    assert response.json() == {'detail': 'Bookings service unavailable'}


# --- TC-VENUEBOOKINGS-041 -------------------------------------------------
def test_a_decision_refused_by_a_block_reaches_venue_staff_unchanged(client, services):
    services.user = me('venue_staff')
    detail = 'Studio B is unavailable from 13 Nov 2026 to 16 Nov 2026.'
    services.bookings.post = AsyncMock(return_value=fake_response(409, {'detail': detail}))

    response = client.post('/venue-bookings/44444444-4444-4444-8444-444444444444/decision',
                           json={'decision': 'approved'})

    assert response.status_code == 409
    assert response.json() == {'detail': detail}


# --- TC-VENUEBOOKINGS-042 -------------------------------------------------
def test_venue_staff_add_a_block(client, services):
    services.user = me('venue_staff')
    stored = {**BLOCKS[0]}
    services.bookings.post = AsyncMock(return_value=fake_response(201, stored))

    response = client.post('/venue-bookings/blocks', json=BLOCK_REQUEST, cookies=COOKIE)

    assert response.status_code == 201
    assert response.json() == stored
    services.bookings.post.assert_awaited_once_with(
        '/blocks', json={**BLOCK_REQUEST, 'venue_name': 'Studio B'}, cookies=COOKIE,
    )


@pytest.mark.parametrize('extra', [{'created_by': 'forged'}, {'venue_name': 'Forged'}])
def test_a_block_cannot_carry_server_owned_fields(client, services, extra):
    services.user = me('venue_staff')

    response = client.post('/venue-bookings/blocks', json={**BLOCK_REQUEST, **extra})

    assert response.status_code == 422
    services.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-043 -------------------------------------------------
@pytest.mark.parametrize('role', ['event_coordinator', 'event_organiser', 'technical_support'])
def test_only_venue_staff_manage_blocks(client, services, role):
    services.user = me(role)
    services.bookings.delete = AsyncMock()

    added = client.post('/venue-bookings/blocks', json=BLOCK_REQUEST)
    removed = client.delete(f'/venue-bookings/blocks/{BLOCK_ID}')

    assert added.status_code == removed.status_code == 403
    services.bookings.post.assert_not_called()
    services.bookings.delete.assert_not_called()


def test_no_session_cannot_manage_blocks(client, services):
    services.user = fake_response(401, {'detail': 'Not authenticated'})
    services.bookings.delete = AsyncMock()

    assert client.post('/venue-bookings/blocks', json=BLOCK_REQUEST).status_code == 401
    assert client.delete(f'/venue-bookings/blocks/{BLOCK_ID}').status_code == 401
    services.bookings.delete.assert_not_called()


def test_a_block_on_an_unknown_venue_is_a_404(client, services):
    services.user = me('venue_staff')
    services.venue = fake_response(404, {'detail': 'Venue not found'})

    response = client.post('/venue-bookings/blocks', json=BLOCK_REQUEST)

    assert response.status_code == 404
    assert response.json() == {'detail': 'Venue not found'}
    services.bookings.post.assert_not_called()


def test_the_bookings_field_errors_are_passed_through(client, services):
    services.user = me('venue_staff')
    refused = {'detail': 'Please check the details you entered', 'errors': {'reason': 'Input should be ...'}}
    services.bookings.post = AsyncMock(return_value=fake_response(422, refused))

    response = client.post('/venue-bookings/blocks', json=BLOCK_REQUEST)

    assert response.status_code == 422
    assert response.json() == refused


# --- TC-VENUEBOOKINGS-044 -------------------------------------------------
def test_venue_staff_remove_a_block(client, services):
    services.user = me('venue_staff')
    services.bookings.delete = AsyncMock(side_effect=[fake_response(204), fake_response(404, {'detail': 'Block not found'})])

    first = client.delete(f'/venue-bookings/blocks/{BLOCK_ID}', cookies=COOKIE)
    second = client.delete(f'/venue-bookings/blocks/{BLOCK_ID}', cookies=COOKIE)

    assert first.status_code == 204
    assert second.status_code == 404
    assert second.json() == {'detail': 'Block not found'}
    services.bookings.delete.assert_awaited_with(f'/blocks/{BLOCK_ID}', cookies=COOKIE)
