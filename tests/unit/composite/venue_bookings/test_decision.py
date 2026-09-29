"""S-37: TC-VENUEBOOKINGS-032..034; existing assignment policy retained."""
from unittest.mock import AsyncMock

import httpx
import pytest

from .conftest import BOOKING_ID, EVENT_ID, fake_response, me

PATH = f'/venue-bookings/{BOOKING_ID}/decision'


@pytest.mark.parametrize('decision', ['approved', 'rejected'])
def test_staff_decision_forwarded_with_credentials(client, services, decision):
    services.user = me('venue_staff')
    saved = {'id': BOOKING_ID, 'status': 'confirmed' if decision == 'approved' else 'rejected'}
    services.bookings.post = AsyncMock(return_value=fake_response(200, saved))
    payload = {'decision': decision, 'reason': ' Repairs ', 'alternative': None}
    result = client.post(PATH, json=payload, cookies={'sb_access_token': 'token'})
    assert result.status_code == 200 and result.json() == saved
    services.bookings.post.assert_awaited_once_with(f'/bookings/{BOOKING_ID}/decision',
        json={**payload, 'reason': 'Repairs'}, cookies={'sb_access_token': 'token'})
    services.events.get.assert_not_called()
    services.venues.get.assert_not_called()


@pytest.mark.parametrize('role', ['event_coordinator', 'event_organiser', 'technical_support', 'attendee'])
def test_nonstaff_cannot_decide(client, services, role):
    services.user = me(role)
    assert client.post(PATH, json={'decision': 'approved'}).status_code == 403
    services.bookings.post.assert_not_called()


def test_missing_session_denied(client, services):
    services.user = fake_response(401, {'detail': 'Not authenticated'})
    assert client.post(PATH, json={'decision': 'approved'}).status_code == 401
    services.bookings.post.assert_not_called()


@pytest.mark.parametrize('code', [401, 403, 404, 409, 422, 500])
def test_safe_downstream_errors(client, services, code):
    services.user = me('venue_staff')
    services.bookings.post = AsyncMock(return_value=fake_response(code, {'detail': 'private diagnostic'}))
    result = client.post(PATH, json={'decision': 'approved'})
    assert result.status_code == (502 if code == 500 else code)
    assert 'private diagnostic' not in result.text


def test_timeout_is_safe(client, services):
    services.user = me('venue_staff')
    services.bookings.post = AsyncMock(side_effect=httpx.ReadTimeout('private diagnostic'))
    assert client.post(PATH, json={'decision': 'approved'}).status_code == 502


@pytest.mark.parametrize('payload', [{'decision': 'pending'}, {'decision': 'rejected'}, {'decision': 'approved', 'decided_by': 'forged'}])
def test_invalid_body_never_forwarded(client, services, payload):
    services.user = me('venue_staff')
    assert client.post(PATH, json=payload).status_code == 422
    services.bookings.post.assert_not_called()


def test_reassigned_requester_still_denied(client, services):
    services.event = fake_response(404, {'detail': 'Event not found'})
    assert client.get('/venue-bookings', params={'event_id': EVENT_ID}).status_code == 404
    services.bookings.get.assert_not_called()


def test_assigned_coordinator_sees_saved_decision(client, services):
    rows = [{'id': BOOKING_ID, 'status': 'rejected', 'decision_reason': 'Repairs', 'decision_alternative': 'Try Friday'}]
    services.pending = fake_response(200, rows)
    result = client.get('/venue-bookings', params={'event_id': EVENT_ID})
    assert result.status_code == 200 and result.json() == rows
