"""TC-VENUEBOOKINGS-106. Run after the S-30 SQL on .env.test."""
import uuid

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env

RANGE = {'from': '2026-11-11', 'to': '2026-11-30'}


@pytest.fixture
def more_events(admin, world):
    """Two more planning events for the same Coordinator, so three requests
    come from three events. Their bookings, and any block on the world's
    venue, are deleted afterwards."""
    created = []
    try:
        for label in ('B', 'C'):
            created.append(
                admin.schema('events').table('events').insert({
                    'organiser_id': world['coordinator']['id'],
                    'status': 'planning',
                    'assigned_coordinator_id': world['coordinator']['id'],
                    'name': f'spm-test Event {label} {uuid.uuid4().hex[:6]}',
                    'purpose': 'Availability testing',
                    'start_date': '2026-11-12', 'start_time': '09:00',
                    'end_date': '2026-11-12', 'end_time': '18:00',
                    'expected_attendance': 120,
                    'room_layout': 'theatre',
                    'required_facilities': ['projector'],
                    'required_accessibility': ['wheelchair_access'],
                    'decision': 'approved',
                    'decided_at': '2026-10-01T00:00:00Z',
                    'submitted_at': '2026-09-30T00:00:00Z',
                }).execute().data[0]['id']
            )
        yield created
    finally:
        for event_id in created:
            admin.schema('bookings').table('bookings').delete().eq('event_id', event_id).execute()
            admin.schema('events').table('events').delete().eq('id', event_id).execute()
        admin.schema('bookings').table('blocks').delete().eq('venue_id', world['venue_id']).execute()


def test_the_calendar_reflects_a_hold_a_confirmed_booking_and_a_block_through_kong(admin, auth_client, world, more_events):
    coordinator = cookie_for(auth_client, world['coordinator'])
    staff = cookie_for(auth_client, world['staff'])
    venue_id = world['venue_id']
    event_a, (event_b, event_c) = world['event_id'], more_events

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        def calendar():
            response = api.get('/venue-bookings/availability', headers=coordinator, params={'venue_id': venue_id, **RANGE})
            assert response.status_code == 200, response.text
            assert 'spm-test Event' not in response.text, 'an event name reached the Coordinator'
            return [(entry['state'], entry['start_date'], (entry['start_time'] or '')[:5]) for entry in response.json()['entries']]

        def request(event_id, start, end):
            return api.post('/venue-bookings', headers=coordinator, json={
                'event_id': event_id, 'venue_id': venue_id, 'booking_date': '2026-11-12',
                'start_time': start, 'end_time': end,
            })

        # 1. Nothing on the venue yet.
        assert calendar() == []

        # 2. A is confirmed, B is held.
        a = request(event_a, '09:00', '12:00')
        b = request(event_b, '14:00', '16:00')
        assert a.status_code == b.status_code == 201, (a.text, b.text)
        confirmed = api.post(f"/venue-bookings/{a.json()['id']}/decision", headers=staff, json={'decision': 'approved'})
        assert confirmed.status_code == 200, confirmed.text
        held = api.post(f"/venue-bookings/{b.json()['id']}/hold", headers=staff)
        assert held.status_code == 200, held.text
        assert calendar() == [('confirmed', '2026-11-12', '09:00'), ('held', '2026-11-12', '14:00')]

        # 3. C overlaps B's hold; once B is rejected the slot is released.
        refused = request(event_c, '15:00', '17:00')
        assert refused.status_code == 409, refused.text
        assert refused.json()['detail'] == (
            f"{admin.schema('venues').table('venues').select('name').eq('id', venue_id).execute().data[0]['name']}"
            ' is already tentatively held on 12 Nov 2026 from 14:00 to 16:00.'
        )
        rejected = api.post(f"/venue-bookings/{b.json()['id']}/decision", headers=staff,
                            json={'decision': 'rejected', 'reason': 'spm-test release'})
        assert rejected.status_code == 200, rejected.text
        c = request(event_c, '15:00', '17:00')
        assert c.status_code == 201, c.text
        held = api.post(f"/venue-bookings/{c.json()['id']}/hold", headers=staff)
        assert held.status_code == 200, held.text
        assert calendar() == [('confirmed', '2026-11-12', '09:00'), ('held', '2026-11-12', '15:00')]

        # 4. Staff block the following days.
        blocked = api.post('/venue-bookings/blocks', headers=staff, json={
            'venue_id': venue_id, 'start_date': '2026-11-13', 'end_date': '2026-11-16', 'reason': 'safety',
        })
        assert blocked.status_code == 201, blocked.text
        assert calendar() == [
            ('confirmed', '2026-11-12', '09:00'), ('held', '2026-11-12', '15:00'), ('blocked', '2026-11-13', ''),
        ]
        entry = api.get('/venue-bookings/availability', headers=coordinator,
                        params={'venue_id': venue_id, **RANGE}).json()['entries'][-1]
        assert entry['reason'] == 'safety' and 'id' not in entry and 'note' not in entry
