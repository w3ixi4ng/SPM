"""S-25 venue preparation orchestration."""
from unittest.mock import AsyncMock

import pytest

from .conftest import BOOKING_ID, EVENT_ID, fake_response, me

PATH = f"/venue-bookings/{BOOKING_ID}/preparation"


def confirmed(**changes):
    return {
        "id": BOOKING_ID, "event_id": EVENT_ID, "status": "confirmed",
        "venue_name": "Studio B", "event_name": "Alumni evening",
        "venue_preparation_status": "not_started", "venue_preparation_version": 0,
        **changes,
    }


def test_staff_updates_confirmed_booking_during_preparation(client, services):
    services.user = me("venue_staff")
    services.booking = fake_response(200, confirmed())
    services.booking_event_status = "preparation"
    services.bookings.put = AsyncMock(return_value=fake_response(200, confirmed(
        venue_preparation_status="ready", venue_preparation_version=1,
    )))
    response = client.put(PATH, json={"status": "ready", "expected_version": 0},
                          cookies={"sb_access_token": "token"})
    assert response.status_code == 200
    services.bookings.put.assert_awaited_once_with(
        f"/bookings/{BOOKING_ID}/venue-preparation",
        json={"status": "ready", "expected_version": 0},
        cookies={"sb_access_token": "token"},
    )


@pytest.mark.parametrize("event_status", ["planning", "confirmed", "cancelled"])
def test_update_is_limited_to_event_preparation(client, services, event_status):
    services.user = me("venue_staff")
    services.booking = fake_response(200, confirmed())
    services.booking_event_status = event_status
    assert client.put(PATH, json={"status": "ready", "expected_version": 0}).status_code == 409
    services.bookings.put.assert_not_called()


@pytest.mark.parametrize("role", ["event_coordinator", "technical_support", "event_organiser", "attendee"])
def test_only_venue_staff_can_update(client, services, role):
    services.user = me(role)
    assert client.put(PATH, json={"status": "ready", "expected_version": 0}).status_code == 403
    services.bookings.put.assert_not_called()


@pytest.mark.parametrize("booking_status", ["pending", "held", "rejected", "replaced"])
def test_nonconfirmed_bookings_are_refused(client, services, booking_status):
    services.user = me("venue_staff")
    services.booking = fake_response(200, confirmed(status=booking_status))
    assert client.put(PATH, json={"status": "ready", "expected_version": 0}).status_code == 409
    services.events.get.assert_not_called()
    services.bookings.put.assert_not_called()


def test_preparation_list_contains_only_preparation_events(client, services):
    services.user = me("venue_staff")
    services.pending = fake_response(200, [confirmed()])
    services.booking_event_status = "preparation"
    response = client.get("/venue-bookings/preparation")
    assert response.status_code == 200
    assert response.json()[0]["event_status"] == "preparation"
