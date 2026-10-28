"""TC-VENUEBOOKINGS-126: a real venue request and confirmation reach the
event's change history in the events service (S-82 AC1)."""

import os

import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env

EVENTS_BASE_URL = f"http://localhost:{os.environ.get('EVENTS_SERVICE_PORT', '8002')}"


def test_venue_actions_reach_the_event_history(auth_client, world):
    coordinator = cookie_for(auth_client, world["coordinator"])
    staff = cookie_for(auth_client, world["staff"])
    event_id = world["event_id"]

    with httpx.Client(timeout=20.0) as api:
        created = api.post(f"{GATEWAY_BASE_URL}/venue-bookings", headers=coordinator, json={
            "event_id": event_id, "venue_id": world["venue_id"], "booking_date": "2026-11-12",
            "start_time": "09:00", "end_time": "12:00",
        })
        assert created.status_code == 201, created.text
        booking = created.json()
        confirmed = api.post(
            f"{GATEWAY_BASE_URL}/venue-bookings/{booking['id']}/decision",
            headers=staff, json={"decision": "approved"},
        )
        assert confirmed.status_code == 200, confirmed.text

        history = api.get(f"{EVENTS_BASE_URL}/internal/events/{event_id}/history")

    assert history.status_code == 200, history.text
    assert [
        (entry["action"], entry["actor_id"], entry["category"], entry["details"]["booking_id"],
         entry["details"]["venue_name"])
        for entry in history.json()
    ] == [
        ("venue_confirmed", world["staff"]["id"], "venue", booking["id"], booking["venue_name"]),
        ("venue_requested", world["coordinator"]["id"], "venue", booking["id"], booking["venue_name"]),
    ]
