"""S-78: replacing a booking an unavailable period affects, TC-VENUEBOOKINGS-079..092."""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from .conftest import app_module, fake_response, me

TODAY = date(2026, 10, 13)
COOKIE = {'sb_access_token': 'token'}
C2 = '22222222-0000-4000-8000-000000000002'
E1 = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
A_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
R1_ID = '11111111-1111-4111-8111-111111111111'
STUDIO_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'


def venue_id(letter):
    return f'{letter * 8}-0000-4000-8000-000000000000'


HALL_C, ROOM_D, HALL_E, HALL_F, HALL_G, HALL_H, HALL_J, HALL_K = (
    venue_id(letter) for letter in 'cdef0123'
)

EVENT = {
    'id': E1, 'status': 'planning', 'assigned_coordinator_id': C2,
    'name': 'Alumni talk', 'purpose': 'Annual alumni lecture',
    'start_date': '2026-11-13', 'start_time': '09:00:00',
    'end_date': '2026-11-13', 'end_time': '18:00:00',
    'expected_attendance': 120, 'special_requirements': 'Lectern on stage',
    'room_layout': 'theatre', 'required_facilities': ['projector', 'microphones'],
    'required_accessibility': ['wheelchair_access'],
}

FRIDAY = [{'day': 'fri', 'open': '08:00:00', 'close': '20:00:00'}]


def venue(id_, name, **changes):
    return {
        'id': id_, 'name': name, 'location': '1 Campus Way', 'capacity': 200,
        'room_layouts': ['theatre'], 'facilities': ['projector', 'microphones'],
        'accessibility': ['wheelchair_access'], 'operating_hours': FRIDAY,
        'setup_minutes': 0, 'turnaround_minutes': 0, **changes,
    }


VENUES = [
    venue(STUDIO_B, 'Studio B'),
    venue(HALL_C, 'Hall C'),
    venue(ROOM_D, 'Room D', capacity=100),
    venue(HALL_E, 'Hall E', facilities=['projector']),
    venue(HALL_F, 'Hall F'),
    venue(HALL_G, 'Hall G', setup_minutes=30, turnaround_minutes=30),
    venue(HALL_H, 'Hall H'),
    venue(HALL_J, 'Hall J', operating_hours=[{'day': 'thu', 'open': '08:00:00', 'close': '20:00:00'}]),
    venue(HALL_K, 'Hall K'),
]
BY_ID = {row['id']: row for row in VENUES}


def booking(id_, venue_, status, start='10:00', end='12:00', day='2026-11-13', **changes):
    return {
        'id': id_, 'event_id': E1, 'venue_id': venue_, 'venue_name': BY_ID[venue_]['name'],
        'coordinator_id': C2, 'coordinator_name': 'Ben Tan', 'event_name': 'Alumni talk',
        'status': status, 'booking_date': day, 'start_time': f'{start}:00', 'end_time': f'{end}:00',
        'replaces_booking_id': None, **changes,
    }


A = booking(A_ID, STUDIO_B, 'confirmed')
P = {
    'id': 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'venue_id': STUDIO_B, 'venue_name': 'Studio B',
    'start_date': '2026-11-13', 'start_time': '09:00:00', 'end_date': '2026-11-14', 'end_time': '17:00:00',
    'reason': 'equipment_failure', 'note': 'Air handling unit down', 'created_at': '2026-10-12T08:00:00Z',
}
P_PERIOD = {key: P[key] for key in ('start_date', 'start_time', 'end_date', 'end_time', 'reason', 'note')}
P2 = {**P, 'id': 'cccccccc-0000-4ccc-8ccc-000000000002', 'start_time': '11:00:00',
      'end_date': '2026-11-13', 'end_time': '13:00:00', 'created_at': '2026-10-14T08:00:00Z'}
HALL_H_PERIOD = {**P, 'id': 'cccccccc-0000-4ccc-8ccc-000000000003', 'venue_id': HALL_H, 'venue_name': 'Hall H',
                 'end_date': '2026-11-13', 'start_time': '12:00:00', 'end_time': '14:00:00'}

SAME_DAY = {
    HALL_F: [booking('f0000000-0000-4000-8000-000000000001', HALL_F, 'confirmed', '11:00', '13:00')],
    HALL_G: [booking('f0000000-0000-4000-8000-000000000002', HALL_G, 'held', '08:00', '09:30')],
    HALL_K: [booking('f0000000-0000-4000-8000-000000000003', HALL_K, 'pending')],
}


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(app_module, '_today', lambda: TODAY)


class World:
    """The four fakes for E1, its affected booking A, and the candidate venues."""

    def __init__(self, services):
        self.services = services
        self.event = dict(EVENT)
        self.event_status = 200
        self.one = {A_ID: dict(A)}
        self.by_event = [dict(A)]
        self.venues = [dict(row) for row in VENUES]
        self.venues_status = 200
        self.same_day = {key: list(rows) for key, rows in SAME_DAY.items()}
        self.blocks = {STUDIO_B: [P], HALL_H: [HALL_H_PERIOD]}
        self.blocks_status = 200
        self.post_answers = {}
        services.user = me(id=C2, name='Ben Tan', email='ben@example.com')
        services.events.get = AsyncMock(side_effect=self.events_get)
        services.venues.get = AsyncMock(side_effect=self.venues_get)
        services.bookings.get = AsyncMock(side_effect=self.bookings_get)
        services.bookings.post = AsyncMock(side_effect=self.bookings_post)

    async def events_get(self, path, **kwargs):
        if path.startswith('/events/booking-status/'):
            return fake_response(200, {'id': path.rsplit('/', 1)[-1], 'status': 'planning'})
        assert path == f'/events/assigned/{E1}', path
        if self.event_status != 200:
            return fake_response(self.event_status, {'detail': 'Event not found'})
        return fake_response(200, self.event)

    async def venues_get(self, path, **kwargs):
        if path == '/venues':
            return fake_response(self.venues_status, self.venues if self.venues_status == 200 else None)
        found = next((row for row in self.venues if row['id'] == path.rsplit('/', 1)[-1]), None)
        return fake_response(200, found) if found else fake_response(404, {'detail': 'Venue not found'})

    async def bookings_get(self, path, **kwargs):
        params = kwargs.get('params') or {}
        if path == '/blocks':
            if self.blocks_status != 200:
                return fake_response(self.blocks_status)
            return fake_response(200, self.blocks.get(params['venue_id'], []))
        if path.startswith('/bookings/'):
            found = self.one.get(path.rsplit('/', 1)[-1])
            return fake_response(200, found) if found else fake_response(404, {'detail': 'Booking not found'})
        if 'event_id' in params:
            return fake_response(200, self.by_event)
        if 'venue_id' in params:
            return fake_response(200, self.same_day.get(params['venue_id'], []))
        if params.get('status') == 'actionable':
            return fake_response(200, [row for row in self.by_event if row['status'] in ('pending', 'held')])
        raise AssertionError(f'unexpected bookings.get({path!r}, {params!r})')

    async def bookings_post(self, path, **kwargs):
        if path in self.post_answers:
            return self.post_answers[path]
        if path == '/bookings':
            body = kwargs['json']
            return fake_response(201, {**body, 'id': R1_ID, 'status': 'pending'})
        raise AssertionError(f'unexpected bookings.post({path!r})')

    def posts(self, path):
        return [call for call in self.services.bookings.post.await_args_list if call.args[0] == path]

    def venue_list_reads(self):
        return [call for call in self.services.venues.get.await_args_list if call.args[0] == '/venues']


@pytest.fixture
def world(services):
    return World(services)


def search(client, booking_id=A_ID):
    return client.get(f'/venue-bookings/{booking_id}/replacement-venues', cookies=COOKIE)


def replace(client, body, booking_id=A_ID):
    return client.post(f'/venue-bookings/{booking_id}/replacement', json=body, cookies=COOKIE)


def resolve(client, body, booking_id=A_ID):
    return client.post(f'/venue-bookings/{booking_id}/resolution', json=body, cookies=COOKIE)


def listed(client):
    response = client.get(f'/venue-bookings?event_id={E1}', cookies=COOKIE)
    assert response.status_code == 200, response.text
    return {row['id']: row for row in response.json()}


# --- TC-VENUEBOOKINGS-079 --------------------------------------------------
def test_the_search_offers_only_suitable_available_venues(client, world):
    response = search(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body['booking'] == {
        'id': A_ID, 'venue_name': 'Studio B', 'booking_date': '2026-11-13',
        'start_time': '10:00:00', 'end_time': '12:00:00',
    }
    assert [row['name'] for row in body['venues']] == ['Hall C', 'Hall H', 'Hall K']
    assert body['venues'][0] == BY_ID[HALL_C]
    world.services.bookings.post.assert_not_awaited()
    world.services.events.post.assert_not_awaited()


# --- TC-VENUEBOOKINGS-080 --------------------------------------------------
def test_the_search_uses_the_events_current_requirements(client, world):
    world.event['expected_attendance'] = 250

    response = search(client)

    assert response.status_code == 200, response.text
    assert response.json()['venues'] == []
    events_call = world.services.events.get.await_args
    assert events_call.args[0] == f'/events/assigned/{E1}'
    assert events_call.kwargs['cookies'] == COOKIE


# --- TC-VENUEBOOKINGS-081 / 086 / 091 --------------------------------------
UNFLAGGED = {
    'pending': booking(A_ID, STUDIO_B, 'pending'),
    'replaced': booking(A_ID, STUDIO_B, 'replaced'),
    'no period': booking(A_ID, HALL_C, 'confirmed'),
    'in the past': booking(A_ID, STUDIO_B, 'confirmed', day='2026-10-01'),
    'resolved': booking(A_ID, STUDIO_B, 'confirmed', alternative_resolved_at='2026-10-12T09:00:00Z'),
}

ROUTES = {
    'search': (lambda client: search(client), "This booking doesn't need a replacement venue", '/bookings'),
    'replace': (lambda client: replace(client, {'venue_id': HALL_C}),
                "This booking doesn't need a replacement venue", '/bookings'),
    'resolve': (lambda client: resolve(client, {'note': 'Moved online'}),
                "This booking doesn't need alternative arrangements", f'/bookings/{A_ID}/alternative-resolution'),
}


@pytest.mark.parametrize('route', ROUTES)
def test_no_session_or_the_wrong_role_is_refused(client, world, route):
    send, _, write = ROUTES[route]
    world.services.user = fake_response(401, {'detail': 'Not authenticated'})
    assert send(client).json() == {'detail': 'Not authenticated'}
    world.services.user = me('venue_staff')
    response = send(client)
    assert (response.status_code, response.json()) == (403, {'detail': 'Permission denied'})
    assert not world.posts(write)
    assert not world.venue_list_reads()


@pytest.mark.parametrize('route', ROUTES)
def test_an_unknown_booking_or_another_coordinators_event_is_not_found(client, world, route):
    send, _, write = ROUTES[route]
    world.one = {}
    response = send(client)
    assert (response.status_code, response.json()) == (404, {'detail': 'Booking not found'})

    world.one = {A_ID: dict(A)}
    world.event_status = 404
    response = send(client)
    assert (response.status_code, response.json()) == (404, {'detail': 'Booking not found'})
    assert not world.posts(write)
    assert not world.venue_list_reads()


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('case', UNFLAGGED)
def test_a_booking_without_the_flag_is_refused(client, world, route, case):
    send, detail, write = ROUTES[route]
    world.one = {A_ID: UNFLAGGED[case]}
    world.by_event = [UNFLAGGED[case]]

    response = send(client)

    assert (response.status_code, response.json()) == (409, {'detail': detail})
    assert not world.posts(write)
    assert not world.venue_list_reads()


# S-17: a rejected booking can be replaced (test_s17.py), but it was never
# affected by a period, so there are no alternative arrangements to record.
def test_a_rejected_booking_has_no_alternative_arrangements(client, world):
    send, detail, write = ROUTES['resolve']
    rejected = booking(A_ID, STUDIO_B, 'rejected')
    world.one = {A_ID: rejected}
    world.by_event = [rejected]

    response = send(client)

    assert (response.status_code, response.json()) == (409, {'detail': detail})
    assert not world.posts(write)


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('event_status', ['cancelled', 'rejected'])
def test_a_closed_event_is_refused(client, world, route, event_status):
    send, _, write = ROUTES[route]
    world.event['status'] = event_status

    response = send(client)

    assert (response.status_code, response.json()) == (
        409, {'detail': "This event's venue bookings can no longer be changed"}
    )
    assert not world.posts(write)


@pytest.mark.parametrize('event_status', ['confirmed', 'preparation', 'safety_changes_requested'])
def test_an_open_event_past_planning_may_still_search(client, world, event_status):
    world.event['status'] = event_status
    response = search(client)
    assert response.status_code == 200, response.text
    assert [row['name'] for row in response.json()['venues']] == ['Hall C', 'Hall H', 'Hall K']


def test_a_failed_read_is_an_error_never_no_venues(client, world):
    world.venues_status = 500
    assert search(client).json() == {'detail': 'Venues service unavailable'}

    world.venues_status = 200
    world.blocks = {STUDIO_B: [P]}
    original = world.bookings_get

    async def failing(path, **kwargs):
        params = kwargs.get('params') or {}
        if path == '/blocks' and params.get('venue_id') == HALL_C:
            return fake_response(500)
        return await original(path, **kwargs)

    world.services.bookings.get = AsyncMock(side_effect=failing)
    response = search(client)
    assert (response.status_code, response.json()) == (502, {'detail': 'Bookings service unavailable'})


# --- TC-VENUEBOOKINGS-082 --------------------------------------------------
def test_a_replacement_is_stored_linked_with_the_events_details(client, world):
    response = replace(client, {'venue_id': HALL_C, 'notes': '  Same setup as Studio B  '})

    assert response.status_code == 201, response.text
    assert response.json()['status'] == 'pending'
    assert response.json()['replaces_booking_id'] == A_ID
    [call] = world.posts('/bookings')
    assert call.kwargs['params'] == {'setup_minutes': 0, 'turnaround_minutes': 0}
    assert call.kwargs['json'] == {
        'event_id': E1, 'venue_id': HALL_C, 'replaces_booking_id': A_ID,
        'booking_date': '2026-11-13', 'start_time': '10:00:00', 'end_time': '12:00:00',
        'notes': 'Same setup as Studio B',
        'coordinator_id': C2, 'coordinator_name': 'Ben Tan', 'coordinator_email': 'ben@example.com',
        'event_name': 'Alumni talk', 'event_purpose': 'Annual alumni lecture', 'expected_attendance': 120,
        'special_requirements': 'Lectern on stage', 'room_layout': 'theatre',
        'required_facilities': ['projector', 'microphones'], 'required_accessibility': ['wheelchair_access'],
        'venue_name': 'Hall C',
    }
    assert len(world.services.bookings.post.await_args_list) == 1
    # S-82: the one write to Events is the history entry, never the event.
    posted = [call.args[0] for call in world.services.events.post.await_args_list]
    assert [path.endswith('/history') for path in posted] == [True]
    world.services.events.patch.assert_not_awaited()


# --- TC-VENUEBOOKINGS-083 --------------------------------------------------
@pytest.mark.parametrize('body, field', [
    ({}, 'venue_id'),
    ({'venue_id': 'not-a-uuid'}, 'venue_id'),
    *[({'venue_id': HALL_C, name: value}, name) for name, value in [
        ('booking_date', '2026-11-20'), ('event_id', E1), ('start_time', '09:00'), ('end_time', '13:00'),
        ('expected_attendance', 50), ('room_layout', 'banquet'), ('required_facilities', []),
        ('replaces_booking_id', A_ID),
    ]],
])
def test_the_replacement_body_takes_only_a_venue_and_notes(client, world, body, field):
    response = replace(client, body)

    assert response.status_code == 422, response.text
    assert field in response.json()['errors']
    assert not world.posts('/bookings')


def test_blank_notes_are_stored_as_none(client, world):
    response = replace(client, {'venue_id': HALL_C, 'notes': '   '})
    assert response.status_code == 201, response.text
    assert world.posts('/bookings')[0].kwargs['json']['notes'] is None


# --- TC-VENUEBOOKINGS-084 --------------------------------------------------
def test_an_unsuitable_venue_is_refused_and_nothing_is_stored(client, world):
    response = replace(client, {'venue_id': ROOM_D})
    assert response.status_code == 422
    assert response.json() == {
        'detail': "This venue can't take this booking",
        'errors': {'expected_attendance': 'Room D holds 100 people; this event expects 120'},
    }

    response = replace(client, {'venue_id': HALL_J})
    assert response.status_code == 422
    assert response.json()['errors']['operating_hours'] == 'Hall J is closed on Fridays'
    assert not world.posts('/bookings')


@pytest.mark.parametrize('venue_, detail', [
    (HALL_F, 'Hall F is already confirmed on 13 Nov 2026 from 11:00 to 13:00.'),
    (STUDIO_B, 'Studio B is unavailable from 13 Nov 2026 09:00 to 14 Nov 2026 17:00.'),
])
def test_a_taken_or_unavailable_venue_passes_the_refusal_through(client, world, venue_, detail):
    world.post_answers['/bookings'] = fake_response(409, {'detail': detail})
    response = replace(client, {'venue_id': venue_})
    assert (response.status_code, response.json()) == (409, {'detail': detail})


def test_an_unknown_venue_is_not_found(client, world):
    response = replace(client, {'venue_id': 'abcdabcd-0000-4000-8000-000000000000'})
    assert (response.status_code, response.json()) == (404, {'detail': 'Venue not found'})
    assert not world.posts('/bookings')


# --- TC-VENUEBOOKINGS-085 --------------------------------------------------
@pytest.mark.parametrize('waiting', ['pending', 'held'])
def test_the_same_venue_again_returns_the_waiting_request(client, world, waiting):
    r1 = booking(R1_ID, HALL_C, waiting, replaces_booking_id=A_ID)
    world.by_event = [dict(A), r1]

    response = replace(client, {'venue_id': HALL_C})

    assert response.status_code == 201
    assert response.json() == r1
    assert not world.posts('/bookings')


def test_another_venue_while_one_is_waiting_is_refused(client, world):
    world.by_event = [dict(A), booking(R1_ID, HALL_C, 'pending', replaces_booking_id=A_ID)]

    response = replace(client, {'venue_id': HALL_H})

    assert (response.status_code, response.json()) == (
        409, {'detail': 'A replacement request for this booking is already with Venue Staff'}
    )
    assert not world.posts('/bookings')


def test_another_request_may_follow_a_rejection_or_another_bookings_replacement(client, world):
    world.by_event = [
        dict(A),
        booking(R1_ID, HALL_C, 'rejected', replaces_booking_id=A_ID),
        booking('99999999-0000-4000-8000-000000000009', HALL_C, 'pending',
                replaces_booking_id='98989898-0000-4000-8000-000000000000'),
    ]

    response = replace(client, {'venue_id': HALL_H})

    assert response.status_code == 201, response.text
    assert world.posts('/bookings')[0].kwargs['json']['replaces_booking_id'] == A_ID


# --- TC-VENUEBOOKINGS-087 / 089 --------------------------------------------
@pytest.mark.parametrize('r1_status', ['pending', 'rejected'])
def test_the_original_stays_flagged_until_the_replacement_is_approved(client, world, r1_status):
    r1 = booking(R1_ID, HALL_C, r1_status, replaces_booking_id=A_ID,
                 decision_reason='Hall C is being repainted' if r1_status == 'rejected' else None)
    world.by_event = [dict(A), r1]
    world.blocks = {STUDIO_B: [P]}

    rows = listed(client)

    assert rows[A_ID]['status'] == 'confirmed'
    assert rows[A_ID]['requires_alternative_arrangements'] is True
    assert rows[A_ID]['unavailable_periods'] == [P_PERIOD]
    assert rows[R1_ID]['replaces_booking_id'] == A_ID
    assert rows[R1_ID]['requires_alternative_arrangements'] is False
    assert rows[R1_ID]['unavailable_periods'] == []
    if r1_status == 'rejected':
        assert rows[R1_ID]['decision_reason'] == 'Hall C is being repainted'


# --- TC-VENUEBOOKINGS-088 --------------------------------------------------
def test_once_approved_the_original_reads_replaced_and_unflagged(client, world):
    r1 = booking(R1_ID, HALL_C, 'confirmed', replaces_booking_id=A_ID)
    world.one[R1_ID] = booking(R1_ID, HALL_C, 'pending', replaces_booking_id=A_ID)
    world.post_answers[f'/bookings/{R1_ID}/decision'] = fake_response(200, r1)
    world.services.user = me('venue_staff')

    decided = client.post(f'/venue-bookings/{R1_ID}/decision', json={'decision': 'approved'}, cookies=COOKIE)

    assert decided.status_code == 200, decided.text
    assert decided.json() == r1
    assert [call.args[0] for call in world.services.bookings.post.await_args_list] == [
        f'/bookings/{R1_ID}/decision'
    ]

    world.services.user = me(id=C2, name='Ben Tan', email='ben@example.com')
    world.by_event = [
        booking(A_ID, STUDIO_B, 'replaced', replaced_by_booking_id=R1_ID, replaced_at='2026-10-13T10:00:00Z'),
        r1,
    ]
    rows = listed(client)
    assert rows[A_ID]['status'] == 'replaced'
    assert rows[A_ID]['replaced_by_booking_id'] == R1_ID
    assert rows[A_ID]['requires_alternative_arrangements'] is False
    assert rows[A_ID]['unavailable_periods'] == []
    assert rows[R1_ID]['status'] == 'confirmed'


# --- TC-VENUEBOOKINGS-090 --------------------------------------------------
RESOLVED = {
    'alternative_resolved_at': '2026-10-13T10:00:00Z',
    'alternative_resolved_by': C2,
    'alternative_resolution_note': 'Moved online for this session',
}


def test_resolving_clears_the_flag_until_a_later_period(client, world):
    path = f'/bookings/{A_ID}/alternative-resolution'
    world.post_answers[path] = fake_response(200, {**A, **RESOLVED})

    response = resolve(client, {'note': '  Moved online for this session  '})

    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'confirmed'
    [call] = world.posts(path)
    assert call.kwargs['json'] == {'note': 'Moved online for this session'}
    assert call.kwargs['cookies'] == COOKIE

    world.by_event = [{**A, **RESOLVED}]
    rows = listed(client)
    assert rows[A_ID]['requires_alternative_arrangements'] is False
    assert rows[A_ID]['unavailable_periods'] == []
    assert rows[A_ID]['alternative_resolution_note'] == 'Moved online for this session'

    world.blocks = {STUDIO_B: [P, P2]}
    rows = listed(client)
    assert rows[A_ID]['requires_alternative_arrangements'] is True
    assert [period['start_time'] for period in rows[A_ID]['unavailable_periods']] == ['11:00:00']


# --- TC-VENUEBOOKINGS-091 --------------------------------------------------
@pytest.mark.parametrize('body', [{}, {'note': '   '}, {'note': 'x' * 501},
                                  {'note': 'Fine', 'alternative_resolved_by': C2}])
def test_a_bad_note_is_refused(client, world, body):
    response = resolve(client, body)
    assert response.status_code == 422, response.text
    if 'alternative_resolved_by' not in body:
        assert 'note' in response.json()['errors']
    assert not world.posts(f'/bookings/{A_ID}/alternative-resolution')


def test_a_500_character_note_is_accepted(client, world):
    world.post_answers[f'/bookings/{A_ID}/alternative-resolution'] = fake_response(200, {**A, **RESOLVED})
    assert resolve(client, {'note': 'x' * 500}).status_code == 200


def test_a_failed_resolution_write_is_a_502(client, world):
    world.post_answers[f'/bookings/{A_ID}/alternative-resolution'] = fake_response(500)
    response = resolve(client, {'note': 'Moved online'})
    assert (response.status_code, response.json()) == (502, {'detail': 'Bookings service unavailable'})


# --- TC-VENUEBOOKINGS-092 --------------------------------------------------
def test_resolving_leaves_a_pending_replacement_with_venue_staff(client, world):
    r1 = booking(R1_ID, HALL_C, 'pending', replaces_booking_id=A_ID)
    world.by_event = [dict(A), r1]
    world.post_answers[f'/bookings/{A_ID}/alternative-resolution'] = fake_response(200, {**A, **RESOLVED})

    assert resolve(client, {'note': 'Moved online for this session'}).status_code == 200
    assert [call.args[0] for call in world.services.bookings.post.await_args_list] == [
        f'/bookings/{A_ID}/alternative-resolution'
    ]

    world.services.user = me('venue_staff')
    pending = client.get('/venue-bookings/pending', cookies=COOKIE)
    assert pending.status_code == 200, pending.text
    assert R1_ID in [row['id'] for row in pending.json()]


# --- Venue Staff's request page names the booking being replaced -----------
def test_venue_staffs_request_page_names_the_booking_being_replaced(client, world):
    world.one[R1_ID] = booking(R1_ID, HALL_C, 'pending', replaces_booking_id=A_ID)
    world.services.user = me('venue_staff')

    response = client.get(f'/venue-bookings/{R1_ID}', cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json()['replaces'] == {
        'id': A_ID, 'venue_name': 'Studio B', 'booking_date': '2026-11-13',
        'start_time': '10:00:00', 'end_time': '12:00:00', 'status': 'confirmed',
    }
    assert client.get(f'/venue-bookings/{A_ID}', cookies=COOKIE).json()['replaces'] is None
