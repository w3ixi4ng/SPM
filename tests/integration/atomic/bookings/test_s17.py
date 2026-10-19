"""TC-BOOKINGS-115. Run after the S-17 change to the S-78 trigger on .env.test."""
import uuid

import httpx

from .conftest import BASE_URL, requires_env
from .test_availability import booking_body
from .test_decision import actors  # noqa: F401 -- actors is a fixture
from .test_replacement_venue import approve, create, read

pytestmark = requires_env


# --- TC-BOOKINGS-115 ------------------------------------------------------
def test_confirmed_replacement_retires_rejected_original(admin, booking_ids, actors):
    _, staff = actors('venue_staff')
    original = create(booking_ids, booking_body(str(uuid.uuid4()), '10:00', '12:00'))
    rejected = httpx.post(f'{BASE_URL}/bookings/{original["id"]}/decision', headers=staff,
                          json={'decision': 'rejected', 'reason': 'Double-booked'}, timeout=20)
    assert rejected.status_code == 200, rejected.text

    replacement = create(booking_ids, {
        **booking_body(str(uuid.uuid4()), '10:00', '12:00'),
        'event_id': original['event_id'], 'replaces_booking_id': original['id'],
    })
    assert approve(replacement['id'], staff)['status'] == 'confirmed'

    after = read(admin, original['id'])
    assert after['status'] == 'replaced', 'still rejected -- check the S-17 trigger change ran'
    assert after['replaced_by_booking_id'] == replacement['id']
    assert after['replaced_at'] is not None
    assert after['decision_reason'] == 'Double-booked'
