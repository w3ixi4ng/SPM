"""Fixtures for the venue_bookings composite service's isolated unit tests.

All four outbound HTTP clients are replaced with fakes that record every call
and answer from the shared test data -- there is no network, no Supabase, and
no other service running.
"""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

SERVICE = (
    Path(__file__).resolve().parents[4]
    / "backend"
    / "services"
    / "composite"
    / "venue_bookings"
)

os.environ.setdefault("USERS_SERVICE_URL", "http://users:8001")
os.environ.setdefault("EVENTS_SERVICE_URL", "http://events:8002")
os.environ.setdefault("VENUES_SERVICE_URL", "http://venues:8003")
os.environ.setdefault("BOOKINGS_SERVICE_URL", "http://bookings:8004")

# Services use flat imports because each Docker image runs from its own
# folder. Load this service while preserving any same-named modules another
# service's conftest already loaded, so `pytest tests/unit` remains
# collectable.
_MODULE_NAMES = ("app", "availability", "clients", "database", "schemas", "suitability")
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

app = app_module.app
get_users_client = clients_module.get_users_client
get_events_client = clients_module.get_events_client
get_venues_client = clients_module.get_venues_client
get_bookings_client = clients_module.get_bookings_client

COORDINATOR_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
STAFF_ID = "abababab-abab-4bab-8bab-abababababab"
EVENT_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
VENUE_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
BOOKING_ID = "44444444-4444-4444-8444-444444444444"

COORDINATOR = {
    "id": COORDINATOR_ID,
    "name": "Grace Hopper",
    "email": "grace@example.com",
    "role": "event_coordinator",
}

# As the events service returns it: times with seconds.
EVENT = {
    "id": EVENT_ID,
    "status": "planning",
    "assigned_coordinator_id": COORDINATOR_ID,
    "name": "Alumni networking evening",
    "purpose": "Reconnect graduates with faculty",
    "start_date": "2026-11-12",
    "start_time": "09:00:00",
    "end_date": "2026-11-12",
    "end_time": "18:00:00",
    "expected_attendance": 120,
    "special_requirements": "Vegetarian catering for 40",
    # S-36: the venue requirements are the event's.
    "room_layout": "theatre",
    "required_facilities": ["projector"],
    "required_accessibility": ["wheelchair_access"],
}

# As the venues service returns it.
VENUE = {
    "id": VENUE_ID,
    "name": "Studio B",
    "location": "10 Anson Road",
    "capacity": 150,
    "facilities": ["projector", "sound_system", "wifi"],
    "accessibility": ["wheelchair_access", "lift"],
    "room_layouts": ["theatre", "classroom"],
    "operating_hours": [
        {"day": "thu", "open": "08:00:00", "close": "20:00:00"},
        {"day": "fri", "open": "08:00:00", "close": "20:00:00"},
    ],
}

REQUEST = {
    "event_id": EVENT_ID,
    "venue_id": VENUE_ID,
    "booking_date": "2026-11-12",
    "start_time": "09:00",
    "end_time": "12:00",
    "notes": "Access from 08:30 for setup",
}


def fake_response(status_code, json_body=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body
    return response


def me(role="event_coordinator", **overrides):
    return fake_response(200, {**COORDINATOR, "role": role, **overrides})


def created_booking(body):
    return fake_response(
        201, {**body, "id": BOOKING_ID, "status": "pending", "submitted_at": "2026-10-01T09:00:00+00:00"}
    )


def requested(**changes):
    return {**REQUEST, **changes}


class Services:
    """The four fakes, each answering from what a case sets on it."""

    def __init__(self):
        self.user = me()
        self.event = fake_response(200, dict(EVENT))
        self.venue = fake_response(200, dict(VENUE))
        self.pending = fake_response(200, [])

        self.users = MagicMock()
        self.users.get = AsyncMock(side_effect=self._users_get)

        self.events = MagicMock()
        self.events.get = AsyncMock(side_effect=self._events_get)
        self.events.post = AsyncMock()
        self.events.patch = AsyncMock()
        self.events.put = AsyncMock()

        self.venues = MagicMock()
        self.venues.get = AsyncMock(side_effect=self._venues_get)

        self.bookings = MagicMock()
        self.bookings.post = AsyncMock(side_effect=self._bookings_post)
        self.bookings.get = AsyncMock(side_effect=lambda path, **kwargs: self.pending)

    def set_event(self, **changes):
        self.event = fake_response(200, {**EVENT, **changes})

    def set_venue(self, **changes):
        self.venue = fake_response(200, {**VENUE, **changes})

    async def _users_get(self, path, **kwargs):
        assert path == "/users/me", f"unexpected users.get({path!r})"
        return self.user

    async def _events_get(self, path, **kwargs):
        if path.startswith("/events/booking-status/"):
            return fake_response(200, {"id": path.rsplit("/", 1)[-1], "status": "planning"})
        assert path == f"/events/assigned/{EVENT_ID}", f"unexpected events.get({path!r})"
        return self.event

    async def _venues_get(self, path, **kwargs):
        return self.venue

    async def _bookings_post(self, path, **kwargs):
        assert path == "/bookings", f"unexpected bookings.post({path!r})"
        return created_booking(kwargs["json"])

    def sent_booking(self):
        self.bookings.post.assert_called_once()
        return self.bookings.post.call_args.kwargs["json"]


@pytest.fixture
def services():
    return Services()


@pytest.fixture
def client(services):
    app.dependency_overrides[get_users_client] = lambda: services.users
    app.dependency_overrides[get_events_client] = lambda: services.events
    app.dependency_overrides[get_venues_client] = lambda: services.venues
    app.dependency_overrides[get_bookings_client] = lambda: services.bookings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
