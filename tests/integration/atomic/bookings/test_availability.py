"""TC-BOOKINGS-105..107. Run after the S-30 SQL on .env.test."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest

from .conftest import BASE_URL, requires_env
from .test_decision import actors, create_booking  # noqa: F401 -- actors is a fixture

pytestmark = requires_env


@pytest.fixture
def block_ids(admin):
    created: list[str] = []
    try:
        yield created
    finally:
        for block_id in created:
            admin.schema('bookings').table('blocks').delete().eq('id', block_id).execute()


def booking_body(venue_id, start_time, end_time):
    return {
        'event_id': str(uuid.uuid4()), 'venue_id': venue_id,
        'coordinator_id': str(uuid.uuid4()), 'coordinator_name': 'Test Coordinator',
        'coordinator_email': 'coordinator@example.com', 'booking_date': '2026-11-12',
        'start_time': start_time, 'end_time': end_time, 'event_name': 'spm-test availability',
        'event_purpose': 'Availability testing', 'expected_attendance': 100, 'venue_name': 'Studio B',
    }


# --- TC-BOOKINGS-105 ------------------------------------------------------
def test_a_block_can_be_saved_read_back_and_removed(admin, block_ids, actors):
    staff_id, staff = actors('venue_staff')
    venue_id = str(uuid.uuid4())

    created = httpx.post(f'{BASE_URL}/blocks', headers=staff, json={
        'venue_id': venue_id, 'venue_name': 'Studio B', 'start_date': '2026-11-13',
        'end_date': '2026-11-16', 'reason': 'renovation', 'note': 'spm-test block',
    }, timeout=15)
    assert created.status_code == 201, created.text
    block = created.json()
    block_ids.append(block['id'])
    assert block['created_by'] == staff_id

    params = {'venue_id': venue_id, 'from': '2026-11-11', 'to': '2026-11-30'}
    listed = httpx.get(f'{BASE_URL}/blocks', params=params, timeout=15)
    assert listed.status_code == 200, listed.text
    assert [row['id'] for row in listed.json()] == [block['id']]

    removed = httpx.delete(f"{BASE_URL}/blocks/{block['id']}", headers=staff, timeout=15)
    assert removed.status_code == 204
    rows = admin.schema('bookings').table('blocks').select('id').eq('id', block['id']).execute().data
    assert rows == [], 'the block is still in bookings.blocks'


# --- TC-BOOKINGS-106 ------------------------------------------------------
def test_two_simultaneous_overlapping_requests_produce_exactly_one_hold(admin, booking_ids, actors):
    venue_id = str(uuid.uuid4())
    barrier = Barrier(2)
    _, staff = actors('venue_staff')

    pending = [
        httpx.post(f'{BASE_URL}/bookings', json=booking_body(venue_id, '09:00', '12:00'), timeout=20),
        httpx.post(f'{BASE_URL}/bookings', json=booking_body(venue_id, '11:00', '13:00'), timeout=20),
    ]
    assert all(response.status_code == 201 for response in pending)
    booking_ids.extend(response.json()['id'] for response in pending)

    def hold(booking_id):
        barrier.wait(timeout=10)
        return httpx.post(f'{BASE_URL}/bookings/{booking_id}/hold', headers=staff, timeout=20)

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(hold, pending[0].json()['id'])
        two = pool.submit(hold, pending[1].json()['id'])
        responses = [one.result(), two.result()]

    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert 'Studio B is already tentatively held on 12 Nov 2026 from ' in conflict.json()['detail']
    rows = admin.schema('bookings').table('bookings').select('status').eq('venue_id', venue_id).execute().data
    assert sorted(row['status'] for row in rows) == ['held', 'pending']


# --- TC-BOOKINGS-107 ------------------------------------------------------
def test_rejecting_a_hold_releases_the_slot(booking_ids, actors):
    _, staff = actors('venue_staff')
    venue_id = str(uuid.uuid4())
    held = create_booking(booking_ids, venue_id=venue_id, start_time='09:00', end_time='12:00')

    rejected = httpx.post(f"{BASE_URL}/bookings/{held['id']}/decision", headers=staff,
                          json={'decision': 'rejected', 'reason': 'spm-test release'}, timeout=15)
    assert rejected.status_code == 200, rejected.text

    again = httpx.post(f'{BASE_URL}/bookings', json=booking_body(venue_id, '09:00', '12:00'), timeout=15)
    assert again.status_code == 201, again.text
    booking_ids.append(again.json()['id'])
    assert again.json()['status'] == 'pending'
