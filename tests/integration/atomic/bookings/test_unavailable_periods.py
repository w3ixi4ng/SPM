"""TC-BOOKINGS-110..111. Run after the S-77 SQL on .env.test."""
import uuid

import httpx
import pytest
from postgrest.exceptions import APIError

from .conftest import BASE_URL, requires_env
from .test_availability import block_ids, booking_body  # noqa: F401 -- block_ids is a fixture
from .test_decision import actors  # noqa: F401 -- actors is a fixture

pytestmark = requires_env


def period_row(venue_id, **changes):
    row = {
        'venue_id': venue_id, 'venue_name': 'spm-test Studio', 'start_date': '2026-11-13',
        'start_time': '09:00', 'end_date': '2026-11-13', 'end_time': '12:00',
        'reason': 'equipment_failure', 'note': 'spm-test projector fault',
        'created_by': str(uuid.uuid4()),
    }
    row.update(changes)
    return row


# --- TC-BOOKINGS-110 ------------------------------------------------------
def test_a_timed_period_refuses_an_overlapping_request_and_allows_a_back_to_back_one(
    admin, block_ids, booking_ids, actors,
):
    staff_id, staff = actors('venue_staff')
    venue_id = str(uuid.uuid4())

    created = httpx.post(f'{BASE_URL}/blocks', headers=staff, json={
        'venue_id': venue_id, 'venue_name': 'Studio B', 'start_date': '2026-11-13', 'start_time': '09:00',
        'end_date': '2026-11-13', 'end_time': '12:00', 'reason': 'equipment_failure',
        'note': 'spm-test projector fault',
    }, timeout=15)
    assert created.status_code == 201, created.text
    block = created.json()
    block_ids.append(block['id'])
    assert (block['start_time'], block['end_time']) == ('09:00:00', '12:00:00')

    listed = httpx.get(f'{BASE_URL}/blocks', params={'venue_id': venue_id, 'from': '2026-11-13', 'to': '2026-11-13'},
                       timeout=15)
    assert listed.status_code == 200, listed.text
    assert [(row['id'], row['start_time']) for row in listed.json()] == [(block['id'], '09:00:00')]

    def request(start, end):
        return httpx.post(f'{BASE_URL}/bookings', timeout=20,
                          json={**booking_body(venue_id, start, end), 'booking_date': '2026-11-13'})

    inside = request('11:00', '13:00')
    assert inside.status_code == 409, inside.text
    assert inside.json()['detail'] == 'Studio B is unavailable from 13 Nov 2026 09:00 to 13 Nov 2026 12:00.'
    stored = admin.schema('bookings').table('bookings').select('id').eq('venue_id', venue_id).execute().data
    assert stored == [], 'a request inside the period was stored'

    after = request('12:00', '14:00')
    assert after.status_code == 201, after.text
    booking_ids.append(after.json()['id'])

    rows = admin.schema('bookings').table('blocks').select('*').eq('id', block['id']).execute().data
    assert len(rows) == 1, 'no row in bookings.blocks -- check the S-77 SQL ran'
    assert rows[0]['reason'] == 'equipment_failure'
    assert rows[0]['created_by'] == staff_id


# --- TC-BOOKINGS-111 ------------------------------------------------------
@pytest.mark.parametrize('changes', [
    {'reason': 'internal_activity'},
    {'reason': 'other', 'note': None},
    {'start_time': '12:00', 'end_time': '09:00'},
])
def test_the_database_accepts_only_the_storys_periods(admin, block_ids, changes):
    venue_id = str(uuid.uuid4())
    accepted = admin.schema('bookings').table('blocks').insert(period_row(venue_id)).execute().data
    block_ids.extend(row['id'] for row in accepted)
    assert len(accepted) == 1

    with pytest.raises(APIError) as refused:
        result = admin.schema('bookings').table('blocks').insert(period_row(venue_id, **changes)).execute()
        block_ids.extend(row['id'] for row in result.data)
    assert refused.value.code == '23514', refused.value
