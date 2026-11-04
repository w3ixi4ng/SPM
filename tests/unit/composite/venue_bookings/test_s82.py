"""S-82: each venue action that takes effect adds one entry to its event's
change history. TC-VENUEBOOKINGS-122 to -125."""

import logging
from unittest.mock import AsyncMock

import httpx
import pytest

from .conftest import BOOKING_ID, COORDINATOR_ID, EVENT_ID, REQUEST, STAFF_ID, VENUE_ID, app_module, fake_response, me
from .test_replacement_venue import A, A_ID, C2, E1, HALL_C, R1_ID, TODAY, World

HISTORY = f"/internal/events/{EVENT_ID}/history"
COOKIE = {"sb_access_token": "token"}


def booking(**changes):
    return {
        "id": BOOKING_ID, "event_id": EVENT_ID, "venue_id": VENUE_ID, "venue_name": "Studio B",
        "coordinator_id": COORDINATOR_ID, "event_name": "Alumni networking evening",
        "status": "pending", "booking_date": "2026-11-12", "start_time": "09:00:00", "end_time": "12:00:00",
        "hold_expires_at": "2099-11-12T02:00:00+00:00", **changes,
    }


@pytest.fixture
def history(services):
    services.events.post = AsyncMock(return_value=fake_response(201, {"id": 1}))
    return services


def sent(services):
    return [(call.args[0], call.kwargs["json"]) for call in services.events.post.await_args_list]


def entry(actor_id, role, action, details):
    return {"actor_id": actor_id, "actor_role": role, "action": action, "details": details}


# --- TC-VENUEBOOKINGS-122 ----------------------------------------------------
def test_coordinator_venue_requests_are_recorded(client, history):
    assert client.post("/venue-bookings", json=REQUEST).status_code == 201

    history.booking = fake_response(200, booking(status="held"))
    history.bookings.patch = AsyncMock(return_value=fake_response(200, booking(
        start_time="10:00:00", end_time="13:00:00",
    )))
    change = {**REQUEST, "start_time": "10:00", "end_time": "13:00"}
    change.pop("event_id")
    assert client.patch(f"/venue-bookings/{BOOKING_ID}", json=change).status_code == 200

    history.bookings.delete = AsyncMock(return_value=fake_response(204))
    assert client.delete(f"/venue-bookings/{BOOKING_ID}").status_code == 204

    assert sent(history) == [
        (HISTORY, entry(COORDINATOR_ID, "event_coordinator", "venue_requested", {
            "booking_id": BOOKING_ID, "venue_name": "Studio B",
            "start": "2026-11-12T09:00:00", "end": "2026-11-12T12:00:00",
        })),
        (HISTORY, entry(COORDINATOR_ID, "event_coordinator", "venue_request_changed", {
            "booking_id": BOOKING_ID, "venue_name": "Studio B",
            "from": {"start": "2026-11-12T09:00:00", "end": "2026-11-12T12:00:00", "venue_name": "Studio B"},
            "to": {"start": "2026-11-12T10:00:00", "end": "2026-11-12T13:00:00", "venue_name": "Studio B"},
        })),
        (HISTORY, entry(COORDINATOR_ID, "event_coordinator", "venue_request_withdrawn", {
            "booking_id": BOOKING_ID, "venue_name": "Studio B",
        })),
    ]


@pytest.fixture
def world(services, monkeypatch):
    monkeypatch.setattr(app_module, "_today", lambda: TODAY)
    services.events.post = AsyncMock(return_value=fake_response(201, {"id": 1}))
    return World(services)


def test_replacement_and_resolution_are_recorded(client, world):
    response = client.post(f"/venue-bookings/{A_ID}/replacement", json={"venue_id": HALL_C}, cookies=COOKIE)
    assert response.status_code == 201, response.text

    resolution = f"/bookings/{A_ID}/alternative-resolution"
    world.post_answers[resolution] = fake_response(200, {**A, "alternative_resolution_note": "Moved online"})
    response = client.post(f"/venue-bookings/{A_ID}/resolution", json={"note": "Moved online"}, cookies=COOKIE)
    assert response.status_code == 200, response.text

    path = f"/internal/events/{E1}/history"
    assert sent(world.services) == [
        (path, entry(C2, "event_coordinator", "venue_replacement_requested", {
            "booking_id": R1_ID, "venue_name": "Hall C",
            "replaces_booking_id": A_ID, "replaced_venue_name": "Studio B",
        })),
        (path, entry(C2, "event_coordinator", "venue_alternative_resolved", {
            "booking_id": A_ID, "venue_name": "Studio B",
        })),
    ]


# --- TC-VENUEBOOKINGS-123 ----------------------------------------------------
def test_venue_staff_decisions_are_recorded(client, history):
    history.user = me("venue_staff", id=STAFF_ID)
    history.bookings.post = AsyncMock(return_value=fake_response(200, booking(status="held")))
    hold = {"expires_at": "2099-11-12T10:00:00+08:00"}
    assert client.post(f"/venue-bookings/{BOOKING_ID}/hold", json=hold).status_code == 200
    assert client.post(f"/venue-bookings/{BOOKING_ID}/release").status_code == 200
    assert client.post(f"/venue-bookings/{BOOKING_ID}/decision", json={"decision": "approved"}).status_code == 200
    rejected = {"decision": "rejected", "reason": "Under renovation", "alternative": "Studio C"}
    assert client.post(f"/venue-bookings/{BOOKING_ID}/decision", json=rejected).status_code == 200

    named = {"booking_id": BOOKING_ID, "venue_name": "Studio B"}
    assert sent(history) == [
        (HISTORY, entry(STAFF_ID, "venue_staff", "venue_held", named)),
        (HISTORY, entry(STAFF_ID, "venue_staff", "venue_released", named)),
        (HISTORY, entry(STAFF_ID, "venue_staff", "venue_confirmed",
                        {**named, "reason": None, "alternative": None})),
        (HISTORY, entry(STAFF_ID, "venue_staff", "venue_rejected",
                        {**named, "reason": "Under renovation", "alternative": "Studio C"})),
    ]


# --- TC-VENUEBOOKINGS-124 ----------------------------------------------------
def test_refused_venue_actions_record_nothing(client, history):
    history.bookings.post = AsyncMock(return_value=fake_response(
        409, {"detail": "Studio B is already confirmed on 2026-11-12 from 09:00 to 12:00"},
    ))
    assert client.post("/venue-bookings", json=REQUEST).status_code == 409

    history.set_venue(capacity=10)
    assert client.post("/venue-bookings", json=REQUEST).status_code == 422

    assert client.post(f"/venue-bookings/{BOOKING_ID}/decision", json={"decision": "approved"}).status_code == 403

    history.user = me("venue_staff", id=STAFF_ID)
    history.set_venue()
    history.bookings.post = AsyncMock(return_value=fake_response(409, {"detail": "Already held"}))
    hold = {"expires_at": "2099-11-12T10:00:00+08:00"}
    assert client.post(f"/venue-bookings/{BOOKING_ID}/hold", json=hold).status_code == 409

    history.events.post.assert_not_awaited()


# --- TC-VENUEBOOKINGS-125 ----------------------------------------------------
@pytest.mark.parametrize("failure", ["500", "timeout"])
def test_a_failed_history_write_does_not_undo_the_venue_action(client, history, caplog, failure):
    history.user = me("venue_staff", id=STAFF_ID)
    confirmed = booking(status="confirmed")
    history.bookings.post = AsyncMock(return_value=fake_response(200, confirmed))
    history.events.post = AsyncMock(
        side_effect=httpx.ReadTimeout("slow") if failure == "timeout" else None,
        return_value=fake_response(500, {"detail": "boom"}),
    )

    with caplog.at_level(logging.ERROR):
        response = client.post(f"/venue-bookings/{BOOKING_ID}/decision", json={"decision": "approved"})

    assert response.status_code == 200
    assert response.json() == confirmed
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert EVENT_ID in errors[0] and "venue_confirmed" in errors[0]
