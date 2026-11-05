"""S-81 reopened: the Event Coordinator confirms a hold, which tells the Venue
Staff who placed it; an unconfirmed hold can't be approved.
TC-VENUEBOOKINGS-480 to 484."""
import logging
from unittest.mock import AsyncMock

import pytest

from .conftest import BOOKING_ID, COORDINATOR_ID, EVENT_ID, STAFF_ID, VENUE_ID, fake_response, me

CONFIRM = f"/venue-bookings/{BOOKING_ID}/hold-confirmation"
HELD_AT = "2026-11-05T01:00:00+00:00"
HELD = {
    "id": BOOKING_ID, "venue_id": VENUE_ID, "event_id": EVENT_ID, "status": "held",
    "booking_date": "2026-11-12", "start_time": "09:00:00", "end_time": "12:00:00",
    "venue_name": "Studio B", "event_name": "Alumni Night", "coordinator_id": COORDINATOR_ID,
    "held_by": STAFF_ID, "held_at": HELD_AT, "hold_expires_at": "2099-01-01T04:00:00+00:00",
    "hold_confirmed_by": None, "hold_confirmed_at": None,
}
CONFIRMED = {**HELD, "hold_confirmed_by": COORDINATOR_ID, "hold_confirmed_at": "2026-11-05T02:00:00+00:00"}
NOT_CONFIRMED = "This hold can't be approved until the Event Coordinator confirms it."


@pytest.fixture
def held(services):
    services.booking = fake_response(200, dict(HELD))
    services.bookings.post = AsyncMock(return_value=fake_response(200, dict(CONFIRMED)))
    services.notifications.post = AsyncMock(
        side_effect=lambda path, **kwargs: fake_response(201, kwargs["json"]["notifications"]))
    return services


def confirmation_calls(services):
    return [c for c in services.bookings.post.call_args_list
            if c.args[0] == f"/bookings/{BOOKING_ID}/hold-confirmation"]


# --- TC-VENUEBOOKINGS-480 --------------------------------------------------
def test_confirming_a_hold_informs_the_venue_staff_who_placed_it(client, held):
    response = client.post(CONFIRM, cookies={"sb_access_token": "k"})

    assert response.status_code == 200, response.text
    assert response.json() == CONFIRMED
    [call] = confirmation_calls(held)
    assert call.kwargs["cookies"] == {"sb_access_token": "k"}
    held.notifications.post.assert_called_once()
    path, kwargs = held.notifications.post.call_args.args[0], held.notifications.post.call_args.kwargs
    assert path == "/internal/notifications"
    assert kwargs["json"] == {"notifications": [{
        "recipient_id": STAFF_ID,
        "event_id": EVENT_ID,
        "event_name": "Alumni Night",
        "kind": "venue_hold_confirmed",
        "message": "Grace Hopper confirmed the tentative hold for Studio B on 12 Nov 2026, 09:00–12:00 "
                   "(Alumni Night). You can now approve it before the hold expires.",
        "deduplication_key": f"venue_hold_confirmed:{BOOKING_ID}:{HELD_AT}",
    }]}


# --- TC-VENUEBOOKINGS-481 --------------------------------------------------
def test_not_their_event_is_not_found(client, held):
    held.event = fake_response(404, {"detail": "Event not found"})

    response = client.post(CONFIRM)

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    assert confirmation_calls(held) == []
    held.notifications.post.assert_not_called()


def test_an_event_out_of_planning_is_refused(client, held):
    held.set_event(status="confirmed")

    response = client.post(CONFIRM)

    assert response.status_code == 409
    assert response.json()["detail"] == "A venue can only be requested for an event in planning"
    assert confirmation_calls(held) == []
    held.notifications.post.assert_not_called()


@pytest.mark.parametrize("role", ["venue_staff", "event_organiser"])
def test_only_a_coordinator_confirms(client, held, role):
    held.user = me(role)

    assert client.post(CONFIRM).status_code == 403
    assert confirmation_calls(held) == []
    held.notifications.post.assert_not_called()


def test_confirming_needs_a_session(client, held):
    held.user = fake_response(401, {"detail": "Not authenticated"})

    assert client.post(CONFIRM).status_code == 401
    assert confirmation_calls(held) == []


# --- TC-VENUEBOOKINGS-482 --------------------------------------------------
def test_a_refusal_from_bookings_is_passed_on(client, held):
    held.bookings.post = AsyncMock(return_value=fake_response(409, {"detail": "Only a tentative hold can be confirmed"}))

    response = client.post(CONFIRM)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only a tentative hold can be confirmed"
    held.notifications.post.assert_not_called()


# --- TC-VENUEBOOKINGS-483 --------------------------------------------------
def test_a_failed_notice_doesnt_undo_the_confirmation(client, held, caplog):
    held.notifications.post = AsyncMock(return_value=fake_response(500, {}))

    with caplog.at_level(logging.WARNING):
        response = client.post(CONFIRM)

    assert response.status_code == 200, response.text
    assert response.json() == CONFIRMED
    assert "could not be notified" in caplog.text


# --- TC-VENUEBOOKINGS-484 --------------------------------------------------
def test_approving_an_unconfirmed_hold_is_refused_with_the_reason(client, held):
    held.user = me("venue_staff")
    held.bookings.post = AsyncMock(return_value=fake_response(409, {"detail": NOT_CONFIRMED}))

    response = client.post(f"/venue-bookings/{BOOKING_ID}/decision", json={"decision": "approved"})

    assert response.status_code == 409
    assert response.json()["detail"] == NOT_CONFIRMED
    held.notifications.post.assert_not_called()
