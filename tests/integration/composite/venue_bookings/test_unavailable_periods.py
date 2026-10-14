"""TC-VENUEBOOKINGS-110..111. Run after the S-77 SQL on .env.test."""
import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env


@pytest.fixture
def cleanup(admin, world):
    """Periods and notifications this case creates, removed pass or fail. The
    world fixture removes the bookings, event, venue and accounts."""
    try:
        yield
    finally:
        admin.schema('bookings').table('blocks').delete().eq('venue_id', world['venue_id']).execute()
        admin.schema('notifications').table('notifications').delete().eq('event_id', world['event_id']).execute()


def snapshot(admin, schema, table, row_id):
    return admin.schema(schema).table(table).select('*').eq('id', row_id).execute().data[0]


# --- TC-VENUEBOOKINGS-110 --------------------------------------------------
def test_marking_a_period_through_kong_flags_and_notifies_and_changes_nothing_else(
    admin, auth_client, world, cleanup,
):
    coordinator = cookie_for(auth_client, world['coordinator'])
    staff = cookie_for(auth_client, world['staff'])
    venue_id, event_id = world['venue_id'], world['event_id']

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        sent = api.post('/venue-bookings', headers=coordinator, json={
            'event_id': event_id, 'venue_id': venue_id, 'booking_date': '2026-11-12',
            'start_time': '10:00', 'end_time': '12:00',
        })
        assert sent.status_code == 201, sent.text
        k = sent.json()['id']
        approved = api.post(f'/venue-bookings/{k}/decision', headers=staff, json={'decision': 'approved'})
        assert approved.status_code == 200, approved.text
        booking_before = snapshot(admin, 'bookings', 'bookings', k)
        event_before = snapshot(admin, 'events', 'events', event_id)

        marked = api.post('/venue-bookings/blocks', headers=staff, json={
            'venue_id': venue_id, 'start_date': '2026-11-12', 'start_time': '09:00',
            'end_date': '2026-11-12', 'end_time': '13:00', 'reason': 'safety',
        })
        assert marked.status_code == 201, marked.text
        assert [row['id'] for row in marked.json()['affected_bookings']] == [k]
        assert marked.json()['coordinators_notified'] is True, (
            'the notification was not stored -- check the S-77 notifications SQL ran'
        )

        inbox = api.get('/notifications', headers=coordinator)
        assert inbox.status_code == 200, inbox.text
        mine = [row for row in inbox.json() if row['event_id'] == event_id]
        assert len(mine) == 1
        assert mine[0]['kind'] == 'venue_unavailable'
        assert 'from 12 Nov 2026 09:00 to 12 Nov 2026 13:00' in mine[0]['message']
        assert mine[0]['message'].endswith('12 Nov 2026 from 10:00 to 12:00 needs alternative arrangements.')

        listed = api.get('/venue-bookings', headers=coordinator, params={'event_id': event_id})
        assert listed.status_code == 200, listed.text
        [row] = [row for row in listed.json() if row['id'] == k]
        assert row['requires_alternative_arrangements'] is True
        assert [(p['start_time'], p['end_time'], p['reason']) for p in row['unavailable_periods']] == [
            ('09:00:00', '13:00:00', 'safety'),
        ]

    assert snapshot(admin, 'bookings', 'bookings', k) == booking_before
    assert booking_before['status'] == 'confirmed'
    assert snapshot(admin, 'events', 'events', event_id) == event_before
    assert event_before['status'] == 'planning'


# --- TC-VENUEBOOKINGS-111 --------------------------------------------------
def test_through_kong_a_request_and_a_hold_inside_the_period_are_refused(admin, auth_client, world, cleanup):
    coordinator = cookie_for(auth_client, world['coordinator'])
    staff = cookie_for(auth_client, world['staff'])
    venue_id, event_id = world['venue_id'], world['event_id']
    admin.schema('venues').table('venues').update({'setup_minutes': 30}).eq('id', venue_id).execute()
    venue_name = admin.schema('venues').table('venues').select('name').eq('id', venue_id).execute().data[0]['name']

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        def request(start, end):
            return api.post('/venue-bookings', headers=coordinator, json={
                'event_id': event_id, 'venue_id': venue_id, 'booking_date': '2026-11-12',
                'start_time': start, 'end_time': end,
            })

        def mark(start, end):
            response = api.post('/venue-bookings/blocks', headers=staff, json={
                'venue_id': venue_id, 'start_date': '2026-11-12', 'start_time': start,
                'end_date': '2026-11-12', 'end_time': end, 'reason': 'maintenance',
            })
            assert response.status_code == 201, response.text
            return response.json()['id']

        q = request('10:00', '12:00')
        assert q.status_code == 201, q.text
        first = mark('13:00', '15:00')

        refused = request('15:00', '16:00')
        assert refused.status_code == 409, refused.text
        assert refused.json()['detail'] == (
            f'{venue_name} is unavailable from 12 Nov 2026 13:00 to 12 Nov 2026 15:00.'
        )
        stored = admin.schema('bookings').table('bookings').select('id').eq('event_id', event_id).execute().data
        assert [row['id'] for row in stored] == [q.json()['id']]

        allowed = request('15:30', '16:30')
        assert allowed.status_code == 201, allowed.text

        assert api.delete(f'/venue-bookings/blocks/{first}', headers=staff).status_code == 204
        mark('11:00', '13:00')
        held = api.post(f"/venue-bookings/{q.json()['id']}/hold", headers=staff,
                        json={"expires_at": "2099-01-01T12:00:00+08:00"})
        assert held.status_code == 409, held.text
        assert held.json()['detail'] == f'{venue_name} is unavailable from 12 Nov 2026 11:00 to 12 Nov 2026 13:00.'

    assert snapshot(admin, 'bookings', 'bookings', q.json()['id'])['status'] == 'pending'
