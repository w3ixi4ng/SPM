"""S-33 hold routing and event-state release orchestration."""

from unittest.mock import AsyncMock

import pytest

from .conftest import (
    BOOKING_ID,
    EVENT_ID,
    REQUEST,
    STAFF_ID,
    VENUE_ID,
    fake_response,
    me,
)


@pytest.mark.parametrize("action", ["hold", "release"])
def test_staff_hold_actions_are_authenticated_and_forwarded(client, services, action):
    services.user = me("venue_staff", id=STAFF_ID)
    saved = {"id": BOOKING_ID, "status": "held" if action == "hold" else "pending"}
    services.bookings.post = AsyncMock(return_value=fake_response(200, saved))

    response = client.post(f"/venue-bookings/{BOOKING_ID}/{action}")

    assert response.status_code == 200
    assert response.json() == saved
    # S-75: a hold is checked by the venue's current setup and turnaround.
    expected = {"params": {'setup_minutes': 0, 'turnaround_minutes': 0}, "cookies": {}} if action == "hold" else {
        "json": {"reason": "staff_released"}, "cookies": {}
    }
    services.bookings.post.assert_awaited_once_with(
        f"/bookings/{BOOKING_ID}/{action}", **expected
    )


@pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "technical_support", "attendee"])
def test_nonstaff_cannot_manage_holds(client, services, role):
    services.user = me(role)

    assert client.post(f"/venue-bookings/{BOOKING_ID}/hold").status_code == 403
    assert client.post(f"/venue-bookings/{BOOKING_ID}/release").status_code == 403
    services.bookings.post.assert_not_called()


# S-79 removed replacement: a new request never releases the event's other
# holds. That is TC-VENUEBOOKINGS-061/062 in test_multiple_venues.py.


def test_failed_creation_keeps_the_existing_hold(client, services):
    services.pending = fake_response(200, [{
        "id": BOOKING_ID, "event_id": EVENT_ID,
        "venue_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "booking_date": "2026-11-11", "start_time": "09:00:00",
        "end_time": "12:00:00", "status": "held",
    }])
    services.bookings.post = AsyncMock(return_value=fake_response(500, {"detail": "down"}))

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 502
    assert services.bookings.post.await_count == 1


@pytest.mark.parametrize("event_status", ["rejected", "cancelled"])
def test_observed_terminal_event_releases_its_hold(client, services, event_status):
    services.user = me("venue_staff", id=STAFF_ID)
    held = {
        "id": BOOKING_ID, "event_id": EVENT_ID, "venue_id": VENUE_ID,
        "booking_date": "2026-11-12", "start_time": "09:00:00",
        "end_time": "12:00:00", "status": "held",
    }
    services.pending = fake_response(200, [held])
    services.events.get = AsyncMock(return_value=fake_response(
        200, {"id": EVENT_ID, "status": event_status}
    ))
    services.bookings.post = AsyncMock(return_value=fake_response(
        200, {**held, "status": "pending", "hold_release_reason": f"event_{event_status}"}
    ))

    response = client.get("/venue-bookings/pending")

    assert response.status_code == 200
    assert response.json() == []
    services.bookings.post.assert_awaited_once_with(
        f"/bookings/{BOOKING_ID}/release",
        json={"reason": f"event_{event_status}"}, cookies={},
    )
