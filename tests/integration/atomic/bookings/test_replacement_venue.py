"""TC-BOOKINGS-112..113. Run after the S-78 SQL on .env.test."""
import uuid

import httpx

from .conftest import BASE_URL, requires_env
from .test_availability import booking_body
from .test_decision import actors  # noqa: F401 -- actors is a fixture

pytestmark = requires_env


def create(booking_ids, body):
    response = httpx.post(f'{BASE_URL}/bookings', json=body, timeout=20)
    assert response.status_code == 201, response.text
    booking_ids.append(response.json()['id'])
    return response.json()


def approve(booking_id, staff):
    response = httpx.post(f'{BASE_URL}/bookings/{booking_id}/decision', headers=staff,
                          json={'decision': 'approved'}, timeout=20)
    assert response.status_code == 200, response.text
    return response.json()


def read(admin, booking_id):
    rows = admin.schema('bookings').table('bookings').select('*').eq('id', booking_id).execute().data
    assert len(rows) == 1, 'no row in bookings.bookings -- check the S-78 SQL ran'
    return rows[0]


def confirmed_original(admin, booking_ids, staff):
    v1 = str(uuid.uuid4())
    original = create(booking_ids, booking_body(v1, '10:00', '12:00'))
    approve(original['id'], staff)
    return v1, original


# --- TC-BOOKINGS-112 ------------------------------------------------------
def test_approving_a_real_replacement_replaces_the_original_and_frees_its_slot(admin, booking_ids, actors):
    _, staff = actors('venue_staff')
    v1, original = confirmed_original(admin, booking_ids, staff)
    before = read(admin, original['id'])

    v2 = str(uuid.uuid4())
    replacement = create(booking_ids, {
        **booking_body(v2, '10:00', '12:00'), 'event_id': original['event_id'], 'replaces_booking_id': original['id'],
    })
    assert replacement['replaces_booking_id'] == original['id']

    assert approve(replacement['id'], staff)['status'] == 'confirmed'

    after = read(admin, original['id'])
    assert after['status'] == 'replaced'
    assert after['replaced_by_booking_id'] == replacement['id']
    assert after['replaced_at'] is not None
    unchanged = {key for key in before if key not in ('status', 'replaced_by_booking_id', 'replaced_at')}
    assert {key: after[key] for key in unchanged} == {key: before[key] for key in unchanged}

    # The original no longer holds V1.
    create(booking_ids, booking_body(v1, '10:00', '12:00'))


# --- TC-BOOKINGS-113 ------------------------------------------------------
def test_a_resolution_note_is_saved_and_read_back(admin, booking_ids, actors):
    _, staff = actors('venue_staff')
    coordinator_id, coordinator = actors('event_coordinator')
    _, original = confirmed_original(admin, booking_ids, staff)

    resolved = httpx.post(f"{BASE_URL}/bookings/{original['id']}/alternative-resolution", headers=coordinator,
                          json={'note': 'Moved online'}, timeout=20)
    assert resolved.status_code == 200, resolved.text

    read_back = httpx.get(f"{BASE_URL}/bookings/{original['id']}", timeout=15)
    assert read_back.status_code == 200, read_back.text
    for body in (resolved.json(), read_back.json()):
        assert body['alternative_resolution_note'] == 'Moved online'
        assert body['alternative_resolved_by'] == coordinator_id
        assert body['alternative_resolved_at'] is not None
        assert body['status'] == 'confirmed'
