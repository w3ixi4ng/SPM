"""TC-BOOKINGS-102..104. Run after the S-37, S-38 and S-30 SQL on .env.test."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest
from tests.supabase_client import create_client

from .conftest import BASE_URL, requires_env

pytestmark = requires_env


@pytest.fixture
def actors(admin):
    created = []
    def make(role):
        email = f'spm-test-decision-{uuid.uuid4().hex[:12]}@example.com'
        password = 'correct-horse-battery-staple'
        user = admin.auth.admin.create_user({'email': email, 'password': password,
            'email_confirm': True, 'app_metadata': {'role': role}}).user
        created.append(user.id)
        auth = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_ANON_KEY'])
        session = auth.auth.sign_in_with_password({'email': email, 'password': password}).session
        return str(user.id), {'Cookie': f'sb_access_token={session.access_token}'}
    try:
        yield make
    finally:
        for user_id in created:
            admin.auth.admin.delete_user(user_id)


def create_booking(booking_ids, *, event_id=None, venue_id=None, start_time='09:00', end_time='12:00'):
    response = httpx.post(f'{BASE_URL}/bookings', json={
        'event_id': event_id or str(uuid.uuid4()), 'venue_id': venue_id or str(uuid.uuid4()),
        'coordinator_id': str(uuid.uuid4()), 'coordinator_name': 'Test Coordinator',
        'coordinator_email': 'coordinator@example.com', 'booking_date': '2026-11-12',
        'start_time': start_time, 'end_time': end_time, 'event_name': 'spm-test booking decision',
        'event_purpose': 'Decision testing', 'expected_attendance': 100, 'venue_name': 'Studio B',
    }, timeout=15)
    assert response.status_code == 201, response.text
    row = response.json()
    booking_ids.append(row['id'])
    return row


@pytest.mark.parametrize('payload, status', [
    ({'decision': 'approved'}, 'confirmed'),
    ({'decision': 'rejected', 'alternative': 'Try Studio C at 14:00'}, 'rejected'),
])
def test_decisions_persist_without_rewriting_requests(admin, booking_ids, actors, payload, status):
    staff_id, staff = actors('venue_staff')
    _, coordinator = actors('event_coordinator')
    booking = create_booking(booking_ids)
    path = f"{BASE_URL}/bookings/{booking['id']}/decision"
    before = admin.schema('bookings').table('bookings').select('*').eq('id', booking['id']).execute().data[0]
    assert httpx.post(path, json=payload, timeout=15).status_code == 401
    assert httpx.post(path, headers=coordinator, json=payload, timeout=15).status_code == 403
    saved = httpx.post(path, headers=staff, json=payload, timeout=15)
    assert saved.status_code == 200, saved.text
    after = admin.schema('bookings').table('bookings').select('*').eq('id', booking['id']).execute().data[0]
    assert after['status'] == status and after['decided_by'] == staff_id and after['decided_at']
    assert after['decision_alternative'] == payload.get('alternative')
    primary = {'is_primary', 'primary_selected_by', 'primary_selected_at'}
    if status == 'confirmed':
        assert after['is_primary'] is True
        assert after['primary_selected_by'] == staff_id
        assert after['primary_selected_at']
    else:
        assert after['is_primary'] is False
        assert after['primary_selected_by'] is None
        assert after['primary_selected_at'] is None
    audit = {
        'status', 'decision_reason', 'decision_alternative', 'decided_by',
        'decided_at', *primary,
    }
    assert {k: v for k, v in before.items() if k not in audit} == {k: v for k, v in after.items() if k not in audit}
    assert httpx.post(path, headers=staff, json=payload, timeout=15).status_code == 409
    assert admin.schema('bookings').table('bookings').select('*').eq('id', booking['id']).execute().data[0] == after
    pending = httpx.get(f'{BASE_URL}/bookings', params={'status': 'pending'}, timeout=15)
    assert pending.status_code == 200
    assert booking['id'] not in [row['id'] for row in pending.json()]
    rows = httpx.get(f'{BASE_URL}/bookings', params={'event_id': booking['event_id']}, timeout=15).json()
    assert len(rows) == 1 and rows[0]['status'] == status


def test_concurrent_decisions_have_one_winner(admin, booking_ids, actors):
    first_id, first = actors('venue_staff')
    second_id, second = actors('venue_staff')
    booking = create_booking(booking_ids)
    barrier = Barrier(2)
    def decide(headers, payload):
        barrier.wait(timeout=10)
        return httpx.post(f"{BASE_URL}/bookings/{booking['id']}/decision", headers=headers, json=payload, timeout=20)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(decide, first, {'decision': 'approved'})
        two = pool.submit(decide, second, {'decision': 'rejected', 'reason': 'Repairs'})
        results = [one.result(), two.result()]
    assert sorted(r.status_code for r in results) == [200, 409]
    row = admin.schema('bookings').table('bookings').select('*').eq('id', booking['id']).execute().data[0]
    if row['status'] == 'confirmed':
        assert row['decided_by'] == first_id and row['decision_reason'] is None
    else:
        assert row['status'] == 'rejected' and row['decided_by'] == second_id and row['decision_reason'] == 'Repairs'
    assert httpx.post(f"{BASE_URL}/bookings/{booking['id']}/decision", headers=first,
                      json={'decision': 'approved'}, timeout=15).status_code == 409


def _direct_row(booking, **changes):
    """A bookings.bookings row written with the admin client, going around
    the API and every check it makes."""
    row = {key: booking[key] for key in (
        'event_id', 'venue_id', 'coordinator_id', 'coordinator_name', 'coordinator_email',
        'booking_date', 'event_name', 'event_purpose', 'expected_attendance', 'venue_name',
    )}
    row['event_id'] = str(uuid.uuid4())
    row.update(changes)
    return row


# TC-BOOKINGS-104 (rewritten for S-30): S-38's rule, that the database never
# holds two overlapping confirmed bookings, checked at the database itself.
def test_the_database_refuses_a_second_overlapping_confirmed_booking(admin, booking_ids, actors):
    staff_id, staff = actors('venue_staff')
    venue_id = str(uuid.uuid4())
    first = create_booking(booking_ids, venue_id=venue_id, start_time='09:00', end_time='12:00')
    approved = httpx.post(f"{BASE_URL}/bookings/{first['id']}/decision", headers=staff,
                          json={'decision': 'approved'}, timeout=15)
    assert approved.status_code == 200, approved.text
    confirmed = {'status': 'confirmed', 'decided_by': staff_id, 'decided_at': '2026-10-01T00:00:00+00:00'}
    table = admin.schema('bookings').table('bookings')

    with pytest.raises(Exception) as refused:
        table.insert(_direct_row(first, start_time='11:00', end_time='13:00', **confirmed)).execute()
    assert getattr(refused.value, 'code', None) == '23P01', f'expected an exclusion violation, got {refused.value!r}'

    # [start, end): a booking starting exactly when the first ends is not an overlap.
    back_to_back = table.insert(_direct_row(first, start_time='12:00', end_time='14:00', **confirmed)).execute()
    booking_ids.append(back_to_back.data[0]['id'])

    rows = table.select('status,start_time,end_time').eq('venue_id', venue_id).order('start_time').execute().data
    assert [(row['status'], row['start_time'][:5], row['end_time'][:5]) for row in rows] == [
        ('confirmed', '09:00', '12:00'), ('confirmed', '12:00', '14:00'),
    ]


# TC-BOOKINGS-116
def test_primary_selection_moves_atomically_and_removal_leaves_a_choice(
    admin, booking_ids, actors
):
    _, staff = actors('venue_staff')
    coordinator_id, coordinator = actors('event_coordinator')
    event_id = str(uuid.uuid4())
    first = create_booking(booking_ids, event_id=event_id, start_time='09:00', end_time='10:00')
    second = create_booking(booking_ids, event_id=event_id, start_time='10:00', end_time='11:00')
    for row in (first, second):
        decided = httpx.post(
            f"{BASE_URL}/bookings/{row['id']}/decision", headers=staff,
            json={'decision': 'approved'}, timeout=15,
        )
        assert decided.status_code == 200, decided.text

    table = admin.schema('bookings').table('bookings')
    initial = table.select('id,is_primary').eq('event_id', event_id).execute().data
    assert {row['id']: row['is_primary'] for row in initial} == {
        first['id']: True, second['id']: False,
    }

    selected = httpx.put(
        f"{BASE_URL}/bookings/{second['id']}/primary", headers=coordinator, timeout=15,
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()['is_primary'] is True
    assert selected.json()['primary_selected_by'] == coordinator_id
    moved = table.select('id,is_primary').eq('event_id', event_id).execute().data
    assert {row['id']: row['is_primary'] for row in moved} == {
        first['id']: False, second['id']: True,
    }

    removed = httpx.delete(
        f"{BASE_URL}/bookings/{second['id']}", headers=coordinator, timeout=15,
    )
    assert removed.status_code == 204, removed.text
    booking_ids.remove(second['id'])
    remaining = table.select('id,is_primary').eq('event_id', event_id).execute().data
    assert remaining == [{'id': first['id'], 'is_primary': False}]
