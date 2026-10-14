"""TC-VENUEBOOKINGS-112 -- S-81 expiry notification and release through Kong."""

from datetime import datetime, timedelta, timezone

import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env


def test_hold_expiry_is_notified_and_released_through_kong(
    admin, auth_client, world,
):
    coordinator = cookie_for(auth_client, world['coordinator'])
    staff = cookie_for(auth_client, world['staff'])
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20) as api:
        created = api.post('/venue-bookings', headers=coordinator, json={
            'event_id': world['event_id'], 'venue_id': world['venue_id'],
            'booking_date': '2026-11-12', 'start_time': '09:00', 'end_time': '12:00',
        })
        assert created.status_code == 201, created.text
        booking_id = created.json()['id']

        held = api.post(
            f'/venue-bookings/{booking_id}/hold', headers=staff,
            json={'expires_at': expiry},
        )
        assert held.status_code == 200, held.text
        assert held.json()['status'] == 'held'
        assert held.json()['hold_expires_at'] is not None

        inbox = api.get('/notifications', headers=coordinator)
        assert inbox.status_code == 200, inbox.text
        notices = [
            row for row in inbox.json()
            if row['event_id'] == world['event_id'] and row['kind'] == 'venue_hold_expiry'
        ]
        assert len(notices) == 1
        assert 'tentative hold' in notices[0]['message'].lower()

        admin.schema('bookings').table('bookings').update({
            'hold_expires_at': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        }).eq('id', booking_id).execute()
        calendar = api.get('/venue-bookings/availability', headers=staff, params={
            'venue_id': world['venue_id'], 'from': '2026-11-12', 'to': '2026-11-12',
        })
        assert calendar.status_code == 200, calendar.text
        assert calendar.json()['entries'] == []

    stored = admin.schema('bookings').table('bookings').select(
        'status,hold_release_reason,hold_released_at'
    ).eq('id', booking_id).execute().data[0]
    assert stored['status'] == 'pending'
    assert stored['hold_release_reason'] == 'expired'
    assert stored['hold_released_at'] is not None
