"""TC-BOOKINGS-102/103. Run only after S-37 SQL is confirmed on .env.test."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest
from supabase import create_client

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


def create_booking(booking_ids):
    response = httpx.post(f'{BASE_URL}/bookings', json={
        'event_id': str(uuid.uuid4()), 'venue_id': str(uuid.uuid4()),
        'coordinator_id': str(uuid.uuid4()), 'coordinator_name': 'Test Coordinator',
        'coordinator_email': 'coordinator@example.com', 'booking_date': '2026-11-12',
        'start_time': '09:00', 'end_time': '12:00', 'event_name': 'spm-test S-37',
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
    audit = {'status', 'decision_reason', 'decision_alternative', 'decided_by', 'decided_at'}
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
