"""S-34 reopened: every venue's occupied times on a date, for the venue
filter. TC-VENUEBOOKINGS-450..453."""
from unittest.mock import AsyncMock

import httpx
import pytest

from .conftest import fake_response, me

V1 = '11111111-1111-4111-8111-000000000001'
V2 = '11111111-1111-4111-8111-000000000002'
V3 = '11111111-1111-4111-8111-000000000003'
COOKIE = {'sb_access_token': 'token'}
DAY = {'date': '2026-11-12'}

BOOKINGS = [
    {'id': 'a', 'venue_id': V1, 'status': 'confirmed', 'booking_date': '2026-11-12',
     'start_time': '10:00:00', 'end_time': '12:00:00', 'event_id': 'e1', 'event_name': 'Gala',
     'coordinator_name': 'Grace Hopper', 'coordinator_email': 'grace@example.com'},
    {'id': 'b', 'venue_id': V2, 'status': 'held', 'booking_date': '2026-11-12',
     'start_time': '12:00:00', 'end_time': '13:00:00', 'event_id': 'e2', 'event_name': 'Board dinner',
     'hold_expires_at': '2099-01-01T04:00:00+00:00',
     'coordinator_name': 'Ada Lovelace', 'coordinator_email': 'ada@example.com'},
]
BLOCKS = [{'id': 'c', 'venue_id': V3, 'venue_name': 'Studio B', 'start_date': '2026-11-11',
           'start_time': '18:00:00', 'end_date': '2026-11-12', 'end_time': '14:00:00',
           'reason': 'maintenance', 'note': 'private'}]


def lists(services, bookings=None, blocks=None):
    answers = {
        '/bookings': bookings or fake_response(200, BOOKINGS),
        '/blocks': blocks or fake_response(200, BLOCKS),
    }

    async def get(path, **kwargs):
        answer = answers[path]
        if isinstance(answer, Exception):
            raise answer
        return answer

    services.bookings.get = AsyncMock(side_effect=get)


EXPECTED = [
    {'venue_id': V1, 'state': 'confirmed', 'start_date': '2026-11-12', 'end_date': '2026-11-12',
     'start_time': '10:00:00', 'end_time': '12:00:00'},
    {'venue_id': V2, 'state': 'held', 'start_date': '2026-11-12', 'end_date': '2026-11-12',
     'start_time': '12:00:00', 'end_time': '13:00:00'},
    {'venue_id': V3, 'state': 'blocked', 'start_date': '2026-11-11', 'end_date': '2026-11-12',
     'start_time': '18:00:00', 'end_time': '14:00:00'},
]


# --- TC-VENUEBOOKINGS-450 -------------------------------------------------
def test_a_coordinator_gets_every_venues_occupied_times_for_a_date(client, services):
    lists(services)

    response = client.get('/venue-bookings/occupied', params=DAY, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json() == {'date': '2026-11-12', 'entries': EXPECTED}
    for private in ('Gala', 'Grace Hopper', 'grace@example.com', 'private', 'maintenance',
                    '"e1"', 'expires_at'):
        assert private not in response.text
    calls = [(call.args[0], call.kwargs['params']) for call in services.bookings.get.call_args_list]
    assert calls == [
        ('/bookings', {'status': 'live', 'from': '2026-11-12', 'to': '2026-11-12'}),
        ('/blocks', {'from': '2026-11-12', 'to': '2026-11-12'}),
    ]


# --- TC-VENUEBOOKINGS-451 -------------------------------------------------
def test_venue_staff_may_ask_too(client, services):
    lists(services)
    services.user = me('venue_staff')

    response = client.get('/venue-bookings/occupied', params=DAY, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json()['entries'] == EXPECTED


@pytest.mark.parametrize('role', ['event_organiser', 'attendee'])
def test_other_roles_are_refused(client, services, role):
    lists(services)
    services.user = me(role)

    response = client.get('/venue-bookings/occupied', params=DAY, cookies=COOKIE)

    assert response.status_code == 403
    services.bookings.get.assert_not_called()


def test_no_session_is_refused(client, services):
    lists(services)
    services.user = fake_response(401, {'detail': 'Not authenticated'})

    response = client.get('/venue-bookings/occupied', params=DAY)

    assert response.status_code == 401
    services.bookings.get.assert_not_called()


# --- TC-VENUEBOOKINGS-452 -------------------------------------------------
@pytest.mark.parametrize('params', [{}, {'date': '12-11-2026'}, {'date': '2026-02-30'}])
def test_the_date_is_required_and_must_be_a_date(client, services, params):
    lists(services)

    response = client.get('/venue-bookings/occupied', params=params, cookies=COOKIE)

    assert response.status_code == 422
    services.bookings.get.assert_not_called()


# --- TC-VENUEBOOKINGS-453 -------------------------------------------------
@pytest.mark.parametrize('bookings, blocks', [
    (fake_response(500, {'detail': 'boom'}), None),
    (None, fake_response(500, {'detail': 'boom'})),
    (httpx.ReadTimeout('slow'), None),
])
def test_a_failure_is_never_an_empty_list(client, services, bookings, blocks):
    lists(services, bookings=bookings, blocks=blocks)

    response = client.get('/venue-bookings/occupied', params=DAY, cookies=COOKIE)

    assert response.status_code == 502
    assert 'Bookings' in response.json()['detail']
