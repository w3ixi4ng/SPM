"""Regression coverage for transient venue-bookings dependency failures."""

from unittest.mock import AsyncMock

import httpx

from .conftest import EVENT, REQUEST, fake_response


# --- TC-VENUEBOOKINGS-047 ------------------------------------------------
def test_transient_event_timeout_retries_then_returns_validation(client, services):
    unsuitable = {**EVENT, "expected_attendance": 151}
    services.events.get = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("temporary Events delay"),
            fake_response(200, unsuitable),
        ]
    )

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 422
    assert "expected_attendance" in response.json()["errors"]
    assert services.events.get.await_count == 2
    for call in services.events.get.await_args_list:
        timeout = call.kwargs["timeout"]
        assert timeout.read == 10.0
    services.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-048 ------------------------------------------------
def test_exhausted_event_get_retries_return_safe_502(client, services, no_retry_delay):
    services.events.get = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("slow"),
            httpx.ConnectError("reset"),
            httpx.ReadTimeout("still slow"),
        ]
    )

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 502
    assert response.json() == {"detail": "Events service unavailable"}
    assert services.events.get.await_count == 3
    assert no_retry_delay.await_count == 2
    services.venues.get.assert_not_called()
    services.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-049 ------------------------------------------------
def test_booking_write_timeout_is_not_retried(client, services):
    services.bookings.post = AsyncMock(
        side_effect=httpx.ReadTimeout("write response was lost")
    )

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 502
    assert response.json() == {"detail": "Bookings service unavailable"}
    assert services.bookings.post.await_count == 1
