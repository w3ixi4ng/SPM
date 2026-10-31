"""S-77: marking a venue temporarily unavailable, TC-VENUEBOOKINGS-067..078."""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from .conftest import app_module, fake_response, me

TODAY = date(2026, 11, 10)
STUDIO_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
HALL_C = 'aaaaaaaa-0000-4aaa-8aaa-aaaaaaaaaaaa'
BLOCK_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
COOKIE = {'sb_access_token': 'token'}
C1, C2, C3 = (f'{n}{n}{n}{n}{n}{n}{n}{n}-0000-4000-8000-00000000000{n}' for n in (1, 2, 3))
O1, O2, O4 = (f'{n}{n}{n}{n}{n}{n}{n}{n}-1111-4111-8111-11111111111{n}' for n in (1, 2, 4))

REQUEST = {'venue_id': STUDIO_B, 'start_date': '2026-11-13', 'start_time': '09:00',
           'end_date': '2026-11-14', 'end_time': '17:00', 'reason': 'equipment_failure',
           'note': 'Air handling unit down'}
P = {**REQUEST, 'id': BLOCK_ID, 'venue_name': 'Studio B', 'start_time': '09:00:00', 'end_time': '17:00:00',
     'created_by': 'abababab-abab-4bab-8bab-abababababab', 'created_at': '2026-11-10T01:00:00+00:00'}
P_PERIOD = {'start_date': '2026-11-13', 'start_time': '09:00:00', 'end_date': '2026-11-14',
            'end_time': '17:00:00', 'reason': 'equipment_failure', 'note': 'Air handling unit down'}


def booking(number, event_id, event_name, status, day, start, end, coordinator=C3, venue_id=STUDIO_B):
    return {
        'id': f'b0000000-0000-4000-8000-{number:012d}',
        'event_id': event_id, 'event_name': event_name, 'venue_id': venue_id,
        'venue_name': 'Studio B' if venue_id == STUDIO_B else 'Hall C',
        'coordinator_id': coordinator, 'coordinator_name': f'Coordinator {coordinator[:1]}',
        'status': status, 'booking_date': day, 'start_time': f'{start}:00', 'end_time': f'{end}:00',
    }


E1, E2, E4, E5, E6 = (f'eeeeeee{n}-0000-4000-8000-000000000000' for n in (1, 2, 4, 5, 6))
A = booking(1, E1, 'Alumni talk', 'confirmed', '2026-11-13', '10:00', '12:00', coordinator=C1)
B = booking(2, E2, 'Board lunch', 'held', '2026-11-14', '15:00', '16:30')
D = booking(4, E4, 'Evening recital', 'confirmed', '2026-11-14', '17:15', '19:00')
F = booking(5, E5, 'Breakfast briefing', 'confirmed', '2026-11-13', '07:00', '08:30')
G = booking(6, E6, 'Late workshop', 'confirmed', '2026-11-15', '10:00', '12:00')
LIVE = [F, A, B, D, G]

ACTIVE = [
    {'id': E1, 'name': 'Alumni talk', 'assigned_coordinator_id': C2, 'organiser_id': O1},
    {'id': E2, 'name': 'Board lunch', 'assigned_coordinator_id': C3, 'organiser_id': O2},
    {'id': E4, 'name': 'Evening recital', 'assigned_coordinator_id': C3, 'organiser_id': O4},
    {'id': E5, 'name': 'Breakfast briefing', 'assigned_coordinator_id': C3, 'organiser_id': O1},
    {'id': E6, 'name': 'Late workshop', 'assigned_coordinator_id': C3, 'organiser_id': O2},
]


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(app_module, '_today', lambda: TODAY)


class Studio:
    """The bookings, events and venues fakes for Studio B and period P."""

    def __init__(self, services):
        self.services = services
        self.live = list(LIVE)
        self.active = list(ACTIVE)
        self.blocks = {STUDIO_B: [P], HALL_C: []}
        self.by_event = []
        self.one = {}
        services.user = me('venue_staff')
        services.venues.get = AsyncMock(side_effect=self.venues_get)
        services.events.get = AsyncMock(side_effect=self.events_get)
        services.bookings.get = AsyncMock(side_effect=self.bookings_get)
        services.bookings.post = AsyncMock(return_value=fake_response(201, dict(P)))
        services.bookings.delete = AsyncMock(return_value=fake_response(204))

    async def venues_get(self, path, **kwargs):
        venue_id = path.rsplit('/', 1)[-1]
        name = 'Studio B' if venue_id == STUDIO_B else 'Hall C'
        return fake_response(200, {'id': venue_id, 'name': name, 'setup_minutes': 30, 'turnaround_minutes': 30})

    async def events_get(self, path, **kwargs):
        if path == '/internal/events/assigned-active':
            return fake_response(200, self.active)
        if path.startswith('/events/assigned/'):
            return fake_response(200, {'id': path.rsplit('/', 1)[-1], 'status': 'planning'})
        if path.startswith('/events/booking-status/'):
            return fake_response(200, {'id': path.rsplit('/', 1)[-1], 'status': 'planning'})
        raise AssertionError(f'unexpected events.get({path!r})')

    async def bookings_get(self, path, **kwargs):
        params = kwargs.get('params') or {}
        if path == f'/blocks/{BLOCK_ID}':
            return fake_response(200, dict(P))
        if path.startswith('/blocks/'):
            return fake_response(404, {'detail': 'Block not found'})
        if path == '/blocks':
            return fake_response(200, self.blocks.get(params['venue_id'], []))
        if path.startswith('/bookings/'):
            return fake_response(200, self.one[path.rsplit('/', 1)[-1]])
        if params.get('status') == 'live':
            return fake_response(200, self.live)
        if 'event_id' in params:
            return fake_response(200, self.by_event)
        if params.get('status') == 'actionable':
            return fake_response(200, self.by_event)
        if 'venue_id' in params:
            day = params['from']
            return fake_response(200, [row for row in self.live if row['booking_date'] == day])
        raise AssertionError(f'unexpected bookings.get({path!r}, {params!r})')

    def sent_notifications(self):
        return [row for call in self.services.notifications.post.await_args_list
                for row in call.kwargs['json']['notifications']]


@pytest.fixture
def studio(services):
    return Studio(services)


def mark(client):
    return client.post('/venue-bookings/blocks', json=REQUEST, cookies=COOKIE)


# --- TC-VENUEBOOKINGS-067 --------------------------------------------------
def test_marking_a_period_identifies_the_bookings_it_affects(client, studio):
    response = mark(client)

    assert response.status_code == 201, response.text
    body = response.json()
    assert {key: body[key] for key in P} == P
    assert body['coordinators_notified'] is True
    affected = body['affected_bookings']
    assert [row['id'] for row in affected] == [A['id'], B['id'], D['id']]
    assert set(affected[0]) == {
        'id', 'event_id', 'event_name', 'coordinator_name', 'status', 'booking_date',
        'start_time', 'end_time', 'occupied_start', 'occupied_end',
    }
    assert affected[2]['occupied_start'] == '16:45'
    studio.services.bookings.post.assert_awaited_once_with(
        '/blocks', json={**REQUEST, 'start_time': '09:00:00', 'end_time': '17:00:00', 'venue_name': 'Studio B'},
        cookies=COOKIE,
    )
    live_read = [call for call in studio.services.bookings.get.await_args_list
                 if (call.kwargs.get('params') or {}).get('status') == 'live']
    assert live_read[0].kwargs['params'] == {'status': 'live', 'from': '2026-11-13', 'venue_id': STUDIO_B}


@pytest.mark.parametrize('refusal', [
    fake_response(422, {'detail': 'Please check the details you entered', 'errors': {'reason': 'Input should be ...'}}),
    fake_response(409, {'detail': 'Block not found'}),
])
def test_a_refused_period_goes_no_further(client, studio, refusal):
    studio.services.bookings.post = AsyncMock(return_value=refusal)

    response = mark(client)

    assert response.status_code in (422, 502)
    studio.services.notifications.post.assert_not_called()
    studio.services.events.get.assert_not_called()


# --- TC-VENUEBOOKINGS-068 --------------------------------------------------
def test_a_period_over_no_bookings_affects_none_and_notifies_nobody(client, studio):
    studio.live = [F, G]

    response = mark(client)

    assert response.status_code == 201
    assert response.json()['affected_bookings'] == []
    assert response.json()['coordinators_notified'] is True
    studio.services.notifications.post.assert_not_called()


# --- TC-VENUEBOOKINGS-069 --------------------------------------------------
def test_affected_events_are_not_cancelled_and_their_records_are_untouched(client, studio):
    mark(client)

    events = studio.services.events
    assert [call.args[0] for call in events.get.await_args_list] == ['/internal/events/assigned-active']
    events.post.assert_not_called()
    events.patch.assert_not_called()
    events.put.assert_not_called()
    bookings = studio.services.bookings
    assert [call.args[0] for call in bookings.post.await_args_list] == ['/blocks']
    bookings.delete.assert_not_called()
    assert not bookings.patch.called and not bookings.put.called
    assert not studio.services.venues.post.called


# --- TC-VENUEBOOKINGS-070 --------------------------------------------------
def test_each_affected_events_coordinator_and_organiser_are_notified_once(client, studio):
    mark(client)

    studio.services.notifications.post.assert_awaited_once()
    assert studio.services.notifications.post.await_args.args == ('/internal/notifications',)
    rows = studio.sent_notifications()
    assert [row['recipient_id'] for row in rows] == [C2, O1, C3, O2, C3, O4]
    assert [row['event_id'] for row in rows] == [E1, E1, E2, E2, E4, E4]
    assert [row['event_name'] for row in rows] == [
        'Alumni talk', 'Alumni talk', 'Board lunch', 'Board lunch',
        'Evening recital', 'Evening recital',
    ]
    assert all(row['kind'] == 'venue_unavailable' for row in rows)
    assert rows[0]['message'] == (
        'Studio B is unavailable from 13 Nov 2026 09:00 to 14 Nov 2026 17:00 (Equipment failure). '
        'Your booking on 13 Nov 2026 from 10:00 to 12:00 needs alternative arrangements.'
    )
    assert rows[1]['message'].endswith(
        'Review the event and work with your Event Coordinator to arrange a replacement.'
    )
    assert [row['deduplication_key'] for row in rows] == [
        f'venue_unavailable:{BLOCK_ID}:{A["id"]}:{C2}',
        f'venue_unavailable:{BLOCK_ID}:{A["id"]}:{O1}',
        f'venue_unavailable:{BLOCK_ID}:{B["id"]}:{C3}',
        f'venue_unavailable:{BLOCK_ID}:{B["id"]}:{O2}',
        f'venue_unavailable:{BLOCK_ID}:{D["id"]}:{C3}',
        f'venue_unavailable:{BLOCK_ID}:{D["id"]}:{O4}',
    ]


# --- TC-VENUEBOOKINGS-071 --------------------------------------------------
def test_an_affected_booking_whose_event_has_no_current_coordinator_is_still_flagged(client, studio):
    studio.active = [
        {**event, 'assigned_coordinator_id': None} if event['id'] == E2 else event
        for event in ACTIVE
    ]

    response = mark(client)

    assert response.status_code == 201
    assert [row['id'] for row in response.json()['affected_bookings']] == [A['id'], B['id'], D['id']]
    assert [(row['event_id'], row['recipient_id']) for row in studio.sent_notifications()] == [
        (E1, C2), (E1, O1), (E2, O2), (E4, C3), (E4, O4),
    ]
    assert response.json()['coordinators_notified'] is True


# --- TC-VENUEBOOKINGS-072 --------------------------------------------------
def test_more_than_twenty_affected_bookings_are_notified_in_batches(client, studio):
    many = [booking(100 + n, f'eeeeeeee-0000-4000-8000-{n:012d}', f'Event {n}', 'confirmed',
                    '2026-11-13', '10:00', '11:00')
            for n in range(25)]
    studio.live = many
    studio.active = [
        {'id': row['event_id'], 'name': row['event_name'], 'assigned_coordinator_id': C3,
         'organiser_id': f'99999999-0000-4000-8000-{n:012d}'}
        for n, row in enumerate(many)
    ]

    response = mark(client)

    assert response.status_code == 201
    assert len(response.json()['affected_bookings']) == 25
    sizes = [len(call.kwargs['json']['notifications'])
             for call in studio.services.notifications.post.await_args_list]
    assert sizes == [20, 20, 10]
    keys = [row['deduplication_key'] for row in studio.sent_notifications()]
    assert len(set(keys)) == 50


# --- TC-VENUEBOOKINGS-073 --------------------------------------------------
def test_a_notification_failure_keeps_the_period(client, studio):
    studio.services.notifications.post = AsyncMock(return_value=fake_response(500, {'detail': 'down'}))

    response = mark(client)

    assert response.status_code == 201
    assert [row['id'] for row in response.json()['affected_bookings']] == [A['id'], B['id'], D['id']]
    assert response.json()['coordinators_notified'] is False
    studio.services.bookings.delete.assert_not_called()


def test_an_events_failure_keeps_the_period_too(client, studio):
    async def events_get(path, **kwargs):
        return fake_response(500, {'detail': 'down'})

    studio.services.events.get = AsyncMock(side_effect=events_get)

    response = mark(client)

    assert response.status_code == 201
    assert response.json()['coordinators_notified'] is False
    studio.services.notifications.post.assert_not_called()
    studio.services.bookings.delete.assert_not_called()


def test_retrying_notifies_again_with_the_same_keys(client, studio):
    mark(client)
    first_keys = [row['deduplication_key'] for row in studio.sent_notifications()]
    studio.services.notifications.post.reset_mock()

    response = client.post(f'/venue-bookings/blocks/{BLOCK_ID}/notify', cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()['affected_bookings']] == [A['id'], B['id'], D['id']]
    assert response.json()['coordinators_notified'] is True
    assert [row['deduplication_key'] for row in studio.sent_notifications()] == first_keys


def test_retrying_an_unknown_period_is_a_404(client, studio):
    response = client.post('/venue-bookings/blocks/eeeeeeee-0000-4000-8000-999999999999/notify', cookies=COOKIE)

    assert response.status_code == 404
    assert response.json() == {'detail': 'Block not found'}
    studio.services.notifications.post.assert_not_called()


# --- TC-VENUEBOOKINGS-074 --------------------------------------------------
@pytest.mark.parametrize('user, status_code, detail', [
    (fake_response(401, {'detail': 'Not authenticated'}), 401, 'Not authenticated'),
    (me('event_coordinator'), 403, 'Permission denied'),
])
def test_only_venue_staff_mark_periods_or_retry(client, studio, user, status_code, detail):
    studio.services.user = user

    added = mark(client)
    retried = client.post(f'/venue-bookings/blocks/{BLOCK_ID}/notify')

    assert added.status_code == retried.status_code == status_code
    assert added.json() == retried.json() == {'detail': detail}
    studio.services.bookings.post.assert_not_called()
    studio.services.notifications.post.assert_not_called()


@pytest.mark.parametrize('body, field', [
    ({k: v for k, v in REQUEST.items() if k != 'end_time'}, 'end_time'),
    ({**REQUEST, 'venue_name': 'Forged'}, 'venue_name'),
    ({**REQUEST, 'created_by': 'forged'}, 'created_by'),
])
def test_bad_period_input_is_refused(client, studio, body, field):
    response = client.post('/venue-bookings/blocks', json=body)

    assert response.status_code == 422
    assert field in response.json()['errors']
    studio.services.bookings.post.assert_not_called()


def test_a_period_on_an_unknown_venue_is_a_404(client, studio):
    studio.services.venues.get = AsyncMock(return_value=fake_response(404, {'detail': 'Venue not found'}))

    response = mark(client)

    assert response.status_code == 404
    assert response.json() == {'detail': 'Venue not found'}
    studio.services.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-075 --------------------------------------------------
def test_the_coordinators_list_flags_bookings_needing_alternative_arrangements(client, studio):
    studio.services.user = me('event_coordinator', id=C2)
    a2 = booking(12, E1, 'Alumni talk', 'pending', '2026-11-13', '13:00', '14:00', coordinator=C2)
    a3 = booking(13, E1, 'Alumni talk', 'rejected', '2026-11-13', '15:00', '16:00', coordinator=C2)
    a4 = booking(14, E1, 'Alumni talk', 'confirmed', '2026-11-13', '10:00', '12:00',
                 coordinator=C2, venue_id=HALL_C)
    studio.by_event = [A, a2, a3, a4]

    response = client.get('/venue-bookings', params={'event_id': E1})

    assert response.status_code == 200, response.text
    rows = {row['id']: row for row in response.json()}
    assert rows[A['id']]['requires_alternative_arrangements'] is True
    assert rows[A['id']]['unavailable_periods'] == [P_PERIOD]
    for other in (a2, a3, a4):
        assert rows[other['id']]['requires_alternative_arrangements'] is False
        assert rows[other['id']]['unavailable_periods'] == []
    assert rows[A['id']]['clashes'] == []
    block_reads = [call.kwargs['params'] for call in studio.services.bookings.get.await_args_list
                   if call.args[0] == '/blocks']
    assert sorted(read['venue_id'] for read in block_reads) == sorted([STUDIO_B, HALL_C])
    assert all(read['from'] == read['to'] == '2026-11-13' for read in block_reads)


# --- TC-VENUEBOOKINGS-076 --------------------------------------------------
def test_venue_staffs_pending_list_and_request_page_carry_the_same_flag(client, studio):
    pending = booking(15, E5, 'Breakfast briefing', 'pending', '2026-11-13', '13:00', '14:00')
    studio.by_event = [B, pending]
    studio.one = {B['id']: B, A['id']: A}

    listed = {row['id']: row for row in client.get('/venue-bookings/pending').json()}
    b_page = client.get(f'/venue-bookings/{B["id"]}').json()
    a_page = client.get(f'/venue-bookings/{A["id"]}').json()

    for row in (listed[B['id']], b_page, a_page):
        assert row['requires_alternative_arrangements'] is True
        assert row['unavailable_periods'] == [P_PERIOD]
    assert listed[pending['id']]['requires_alternative_arrangements'] is False
    assert listed[pending['id']]['unavailable_periods'] == []


# --- TC-VENUEBOOKINGS-077 --------------------------------------------------
def test_removing_the_period_removes_the_flag(client, studio):
    studio.by_event = [A]

    removed = client.delete(f'/venue-bookings/blocks/{BLOCK_ID}', cookies=COOKIE)
    studio.blocks = {STUDIO_B: []}
    studio.services.user = me('event_coordinator', id=C2)
    row = client.get('/venue-bookings', params={'event_id': E1}).json()[0]

    assert removed.status_code == 204
    assert row['requires_alternative_arrangements'] is False
    assert row['unavailable_periods'] == []
    assert [call.args[0] for call in studio.services.bookings.post.await_args_list] == []


# --- TC-VENUEBOOKINGS-078 --------------------------------------------------
def test_a_failed_period_lookup_is_an_error_never_a_missing_flag(client, studio):
    studio.by_event = [A]
    studio.one = {A['id']: A}
    lookup = studio.bookings_get

    async def blocks_fail(path, **kwargs):
        if path == '/blocks':
            return fake_response(500, {'detail': 'down'})
        return await lookup(path, **kwargs)

    studio.services.bookings.get = AsyncMock(side_effect=blocks_fail)

    studio.services.user = me('event_coordinator', id=C2)
    by_event = client.get('/venue-bookings', params={'event_id': E1})
    studio.services.user = me('venue_staff')
    pending = client.get('/venue-bookings/pending')
    page = client.get(f'/venue-bookings/{A["id"]}')

    for response in (by_event, pending, page):
        assert response.status_code == 502
        assert response.json() == {'detail': 'Bookings service unavailable'}
