"""Fixtures for the S-51 event_registrations composite."""

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import DEFAULT, AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

SERVICE = (
    Path(__file__).resolve().parents[4]
    / "backend" / "services" / "composite" / "event_registrations"
)

os.environ.setdefault("USERS_SERVICE_URL", "http://users:8001")
os.environ.setdefault("EVENTS_SERVICE_URL", "http://events:8002")
os.environ.setdefault("VENUES_SERVICE_URL", "http://venues:8003")
os.environ.setdefault("BOOKINGS_SERVICE_URL", "http://bookings:8004")
os.environ.setdefault("REGISTRATIONS_SERVICE_URL", "http://registrations:8007")
os.environ.setdefault("NOTIFICATIONS_SERVICE_URL", "http://notifications:8006")

_MODULE_NAMES = ("app", "clients", "schemas")
_saved_modules = {name: sys.modules.get(name) for name in _MODULE_NAMES}
for _name in _MODULE_NAMES:
    sys.modules.pop(_name, None)
sys.path.insert(0, str(SERVICE))
try:
    app_module = importlib.import_module("app")
    clients_module = importlib.import_module("clients")
finally:
    sys.path.remove(str(SERVICE))
    for _name in _MODULE_NAMES:
        sys.modules.pop(_name, None)
        if _saved_modules[_name] is not None:
            sys.modules[_name] = _saved_modules[_name]

SGT = timezone(timedelta(hours=8))
EVENT_E = "22222222-2222-4222-8222-222222222222"
EVENT_F = "66666666-6666-4666-8666-666666666666"
ATTENDEE_A = "33333333-3333-4333-8333-333333333333"
VENUE_ID = "77777777-7777-4777-8777-777777777777"
REGISTERED_AT = "2026-11-05T04:00:00Z"


def response(status, json=None):
    return httpx.Response(status, json=json)


def sgt(text: str) -> datetime:
    """A Singapore wall-clock moment, as an aware instant."""
    return datetime.fromisoformat(text).replace(tzinfo=SGT)


def published(event_id=EVENT_E, **changes):
    row = {
        "id": event_id,
        "name": "Alumni networking evening",
        "purpose": "Reconnect alumni with current students",
        "start_date": "2026-11-20",
        "start_time": "18:00:00",
        "end_date": "2026-11-20",
        "end_time": "21:00:00",
        "registration_required": True,
        "registration_opens_at": "2026-11-01T09:00:00",
        "registration_closes_at": "2026-11-15T18:00:00",
        # S-50: the cap, and the Organiser's close decision.
        "expected_attendance": 2,
        "registration_closed_at": None,
    }
    row.update(changes)
    return row


EVENT_F_ROW = published(
    EVENT_F,
    name="Open lecture",
    registration_required=False,
    registration_opens_at=None,
    registration_closes_at=None,
)


def me(role="attendee", user_id=ATTENDEE_A):
    return {"id": user_id, "name": "Ada Lovelace", "email": "ada@example.com", "role": role}


class Clock:
    def __init__(self):
        self.now = sgt("2026-11-05T12:00")


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def services():
    users = AsyncMock()
    users.get.return_value = response(200, me())

    events = AsyncMock()

    async def events_get(path, **kwargs):
        if path == "/internal/events/published":
            return response(200, [published(), EVENT_F_ROW])
        if path == f"/internal/events/published/{EVENT_E}":
            return response(200, published())
        if path == f"/internal/events/published/{EVENT_F}":
            return response(200, EVENT_F_ROW)
        # S-56: the Attendee's own list reads the event with its status.
        if path == f"/internal/events/attendee-view/{EVENT_E}":
            return response(200, {**published(), "status": "confirmed"})
        if path == f"/internal/events/attendee-view/{EVENT_F}":
            return response(200, {**EVENT_F_ROW, "status": "confirmed"})
        return response(404, {"detail": "Event not found."})

    events.get.side_effect = events_get

    bookings = AsyncMock()

    async def bookings_get(path, params=None, **kwargs):
        if params and params.get("event_id") == EVENT_E:
            return response(
                200,
                [
                    {"id": "b1", "venue_id": VENUE_ID, "status": "confirmed",
                     "venue_name": "Seminar Room 2-1", "submitted_at": "2026-10-01T02:00:00Z"},
                    {"id": "b2", "venue_id": "rejected-venue", "status": "rejected",
                     "venue_name": "Rejected Room", "submitted_at": "2026-09-01T02:00:00Z"},
                ],
            )
        return response(200, [])

    bookings.get.side_effect = bookings_get

    venues = AsyncMock()
    venues.get.return_value = response(200, {"id": VENUE_ID, "name": "Seminar Room 2-1"})

    registrations = AsyncMock()
    registrations.post.return_value = response(
        201,
        {"id": "r1", "event_id": EVENT_E, "attendee_id": ATTENDEE_A, "created_at": REGISTERED_AT},
    )
    # S-50: places and waiting lists by event, so a route can read both. A
    # test that sets `registrations.get.return_value` to a response still
    # gets it for every read except the waiting list's.
    registrations.places = {}
    registrations.waiting = {}

    async def registrations_get(path, **kwargs):
        parts = path.strip("/").split("/")
        if parts[1] == "waiting-list" and parts[2] == "attendees":
            # S-52: one Attendee's entries across every event.
            return response(200, [
                row for rows in registrations.waiting.values()
                for row in rows if row["attendee_id"] == parts[3]
            ])
        if parts[1] == "waiting-list":
            rows = registrations.waiting.get(parts[3], [])
            if len(parts) == 4:
                return response(200, rows)
            found = [row for row in rows if row["attendee_id"] == parts[5]]
            return response(200, found[0]) if found else response(404, {"detail": "not waiting"})
        if isinstance(registrations.get.return_value, httpx.Response):
            return DEFAULT
        if parts[1] == "events":
            rows = registrations.places.get(parts[2], [])
            if len(parts) == 3:
                return response(200, rows)
            found = [row for row in rows if row["attendee_id"] == parts[4]]
            return response(200, found[0]) if found else response(404, {"detail": "not registered"})
        return response(200, [])

    registrations.get.side_effect = registrations_get

    notifications = AsyncMock()
    notifications.post.return_value = response(201, [])
    return {
        "users": users,
        "events": events,
        "bookings": bookings,
        "venues": venues,
        "registrations": registrations,
        "notifications": notifications,
    }


@pytest.fixture
def client(services, clock):
    overrides = app_module.app.dependency_overrides
    overrides[clients_module.get_users_client] = lambda: services["users"]
    overrides[clients_module.get_events_client] = lambda: services["events"]
    overrides[clients_module.get_bookings_client] = lambda: services["bookings"]
    overrides[clients_module.get_venues_client] = lambda: services["venues"]
    overrides[clients_module.get_registrations_client] = lambda: services["registrations"]
    overrides[clients_module.get_notifications_client] = lambda: services["notifications"]
    overrides[clients_module.get_now] = lambda: clock.now
    with TestClient(app_module.app) as test_client:
        yield test_client
    overrides.clear()
