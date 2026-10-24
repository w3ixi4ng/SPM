"""TC-VENUEBOOKINGS-112..113. Run after the S-78 SQL on .env.test."""
import uuid

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env


@pytest.fixture
def more(admin, world):
    """V2 and V3 beside the world's venue (V1), and another event's booking,
    removed pass or fail with the periods this case creates. The world
    fixture removes the event's own bookings, the event, V1 and the accounts."""
    venue = admin.schema('venues').table('venues').select('*').eq('id', world['venue_id']).execute().data[0]
    created = {'venues': [], 'bookings': []}

    def add_venue(label):
        row = {key: venue[key] for key in (
            'location', 'capacity', 'facilities', 'accessibility', 'room_layouts', 'operating_hours', 'created_by',
        )}
        row['name'] = f"{venue['name']} {label}"
        venue_id = admin.schema('venues').table('venues').insert(row).execute().data[0]['id']
        created['venues'].append(venue_id)
        return venue_id

    def add_confirmed_booking(venue_id, start, end):
        row = admin.schema('bookings').table('bookings').insert({
            'event_id': str(uuid.uuid4()), 'venue_id': venue_id, 'coordinator_id': str(uuid.uuid4()),
            'coordinator_name': 'spm-test Other', 'coordinator_email': 'other@example.com',
            'status': 'confirmed', 'booking_date': '2026-11-12', 'start_time': start, 'end_time': end,
            'event_name': 'spm-test other event', 'event_purpose': 'Taking V3', 'expected_attendance': 10,
            'venue_name': 'V3', 'decided_by': world['staff']['id'], 'decided_at': '2026-10-01T00:00:00Z',
        }).execute().data[0]
        created['bookings'].append(row['id'])

    try:
        yield add_venue, add_confirmed_booking
    finally:
        for booking_id in created['bookings']:
            admin.schema('bookings').table('bookings').delete().eq('id', booking_id).execute()
        admin.schema('bookings').table('blocks').delete().eq('venue_id', world['venue_id']).execute()
        # The replacement at V2 belongs to the event, so the world removes it
        # first only if it runs first; remove it here before its venue.
        for venue_id in created['venues']:
            admin.schema('bookings').table('bookings').delete().eq('venue_id', venue_id).execute()
            admin.schema('venues').table('venues').delete().eq('id', venue_id).execute()
        admin.schema('notifications').table('notifications').delete().eq('event_id', world['event_id']).execute()


def flagged_booking(api, world, coordinator, staff):
    """K: a confirmed booking at V1, 12 Nov 10:00-12:00, under a period."""
    sent = api.post('/venue-bookings', headers=coordinator, json={
        'event_id': world['event_id'], 'venue_id': world['venue_id'], 'booking_date': '2026-11-12',
        'start_time': '10:00', 'end_time': '12:00',
    })
    assert sent.status_code == 201, sent.text
    k = sent.json()['id']
    assert api.post(f'/venue-bookings/{k}/decision', headers=staff, json={'decision': 'approved'}).status_code == 200
    marked = api.post('/venue-bookings/blocks', headers=staff, json={
        'venue_id': world['venue_id'], 'start_date': '2026-11-12', 'start_time': '09:00',
        'end_date': '2026-11-12', 'end_time': '13:00', 'reason': 'safety',
    })
    assert marked.status_code == 201, marked.text
    return k


def row_for(api, coordinator, world, booking_id):
    listed = api.get('/venue-bookings', headers=coordinator, params={'event_id': world['event_id']})
    assert listed.status_code == 200, listed.text
    return next(row for row in listed.json() if row['id'] == booking_id)


# --- TC-VENUEBOOKINGS-112 --------------------------------------------------
def test_through_kong_a_coordinator_finds_a_free_venue_requests_it_and_approval_ends_the_flag(
    admin, auth_client, world, more,
):
    add_venue, add_confirmed_booking = more
    v2, v3 = add_venue('V2'), add_venue('V3')
    add_confirmed_booking(v3, '11:00', '12:00')
    coordinator = cookie_for(auth_client, world['coordinator'])
    staff = cookie_for(auth_client, world['staff'])

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=30.0) as api:
        k = flagged_booking(api, world, coordinator, staff)

        found = api.get(f'/venue-bookings/{k}/replacement-venues', headers=coordinator)
        assert found.status_code == 200, found.text
        offered = {venue['id'] for venue in found.json()['venues']}
        assert v2 in offered
        assert world['venue_id'] not in offered and v3 not in offered

        sent = api.post(f'/venue-bookings/{k}/replacement', headers=coordinator, json={'venue_id': v2})
        assert sent.status_code == 201, sent.text
        r = sent.json()['id']
        stored = admin.schema('bookings').table('bookings').select('*').eq('id', r).execute().data
        assert len(stored) == 1, 'no replacement row -- check the S-78 SQL ran'
        assert stored[0]['replaces_booking_id'] == k
        assert stored[0]['event_id'] == world['event_id']
        assert (stored[0]['booking_date'], stored[0]['start_time'], stored[0]['end_time']) == (
            '2026-11-12', '10:00:00', '12:00:00'
        )
        assert stored[0]['event_name'].startswith('spm-test Event')
        assert stored[0]['expected_attendance'] == 120

        original = row_for(api, coordinator, world, k)
        assert original['status'] == 'confirmed'
        assert original['requires_alternative_arrangements'] is True
        assert row_for(api, coordinator, world, r)['status'] == 'pending'

        approved = api.post(f'/venue-bookings/{r}/decision', headers=staff, json={'decision': 'approved'})
        assert approved.status_code == 200, approved.text
        assert approved.json()['status'] == 'confirmed'

        original = row_for(api, coordinator, world, k)
        assert original['status'] == 'replaced', 'the original was not replaced -- check the S-78 trigger ran'
        assert original['replaced_by_booking_id'] == r
        assert original['requires_alternative_arrangements'] is False
        assert row_for(api, coordinator, world, r)['status'] == 'confirmed'


# --- TC-VENUEBOOKINGS-113 --------------------------------------------------
def test_through_kong_resolving_the_flag_with_a_note_clears_it(admin, auth_client, world, more):
    coordinator = cookie_for(auth_client, world['coordinator'])
    staff = cookie_for(auth_client, world['staff'])

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=30.0) as api:
        k = flagged_booking(api, world, coordinator, staff)

        resolved = api.post(f'/venue-bookings/{k}/resolution', headers=coordinator, json={'note': 'Moved online'})
        assert resolved.status_code == 200, resolved.text

        row = row_for(api, coordinator, world, k)
        assert row['status'] == 'confirmed'
        assert row['requires_alternative_arrangements'] is False
        assert row['alternative_resolution_note'] == 'Moved online'
