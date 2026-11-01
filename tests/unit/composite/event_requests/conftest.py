"""Fixtures for the event_requests composite service's isolated unit tests.

Both outbound HTTP clients (`get_users_client`, `get_events_client`) are
replaced with fakes that record every call and return a queued response --
there is no network, no Supabase, and no other service running.
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
    / "event_requests"
)

os.environ.setdefault("USERS_SERVICE_URL", "http://users:8001")
os.environ.setdefault("EVENTS_SERVICE_URL", "http://events:8002")
os.environ.setdefault("EQUIPMENT_SERVICE_URL", "http://equipment:8005")
os.environ.setdefault("NOTIFICATIONS_SERVICE_URL", "http://notifications:8006")
os.environ.setdefault("BOOKINGS_SERVICE_URL", "http://bookings:8004")
os.environ.setdefault("REGISTRATIONS_SERVICE_URL", "http://registrations:8007")
os.environ.setdefault("ASSIGNMENT_SERVICE_SECRET", "unit-assignment-secret")

# Services use flat imports because each Docker image runs from its own
# folder. Load this service while preserving any same-named modules another
# service's conftest already loaded, so `pytest tests/unit` remains
# collectable -- "app", "schemas", and "clients" all exist in more than one
# service.
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

app = app_module.app
get_users_client = clients_module.get_users_client
get_events_client = clients_module.get_events_client
get_notifications_client = clients_module.get_notifications_client
get_bookings_client = clients_module.get_bookings_client
get_equipment_client = clients_module.get_equipment_client
get_registrations_client = clients_module.get_registrations_client

ORGANISER_ID = "11111111-1111-4111-8111-111111111111"
COORDINATOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
COORDINATOR_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
EVENT_ID = "33333333-3333-4333-8333-333333333333"

SUBMITTED = {
    "name": "Alumni networking evening",
    "purpose": "Connect alumni with graduating students",
    "start_date": "2026-10-20",
    "start_time": "18:00",
    "end_date": "2026-10-20",
    "end_time": "21:00",
    "expected_attendance": 120,
    "venue": "Main auditorium",
}


def fake_response(status_code, json_body=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body
    return response


def organiser_me_response(user_id=ORGANISER_ID, role="event_organiser"):
    return fake_response(200, {"id": user_id, "name": "Ada Lovelace", "email": "ada@example.com", "role": role})


def coordinators_response(coordinators):
    return fake_response(200, coordinators)


def coordinator(coordinator_id, name="Coordinator"):
    return {"id": coordinator_id, "name": name, "email": f"{coordinator_id}@example.com"}


def load_row(coordinator_id, conflict=False, assigned_count=0):
    return {"coordinator_id": coordinator_id, "conflict": conflict, "assigned_count": assigned_count}


def load_response(rows):
    return fake_response(200, rows)


def event_response(status_code=201, **overrides):
    body = {
        "id": EVENT_ID,
        "organiser_id": ORGANISER_ID,
        "status": "submitted",
        "assigned_coordinator_id": COORDINATOR_A,
        **SUBMITTED,
        # The events service always includes seconds on the way out, unlike
        # SUBMITTED above (an organiser-style "HH:MM" request body) -- this
        # represents what a real GET/PATCH response actually looks like.
        "start_time": "18:00:00",
        "end_time": "21:00:00",
        "submitted_at": "2026-09-17T10:00:00Z",
        "created_at": "2026-09-17T10:00:00Z",
        "updated_at": "2026-09-17T10:00:00Z",
    }
    body.update(overrides)
    return fake_response(status_code, body)


def users_get_side_effect(coordinators=None, role="event_organiser", coordinators_status=200):
    """A `.get(path, **kwargs)` side effect for Auth and Coordinator lookup."""

    async def _get(path, **kwargs):
        if path == "/users/me":
            return organiser_me_response(role=role)
        if path == "/internal/users/coordinators":
            if coordinators_status != 200:
                return fake_response(coordinators_status, None)
            return coordinators_response(coordinators or [])
        raise AssertionError(f"unexpected users.get({path!r})")

    return _get


def users_get_raises_on_coordinators(exc):
    async def _get(path, **kwargs):
        if path == "/users/me":
            return organiser_me_response()
        if path == "/internal/users/coordinators":
            raise exc
        raise AssertionError(f"unexpected users.get({path!r})")

    return _get


def events_post_side_effect(loads, create_path, create_status, create_body):
    """A `.post(path, **kwargs)` side_effect covering coordinator-load and a create/submit call."""

    async def _post(path, **kwargs):
        if path == "/events/coordinator-load":
            return load_response(loads)
        if path == create_path:
            return fake_response(create_status, create_body)
        raise AssertionError(f"unexpected events.post({path!r})")

    return _post


def events_post_raises_on_load(exc):
    async def _post(path, **kwargs):
        if path == "/events/coordinator-load":
            raise exc
        raise AssertionError(f"unexpected events.post({path!r})")

    return _post


def events_post_coordinator_load_side_effect(all_loads: dict):
    """`all_loads`: {coordinator_id: {"conflict": bool, "assigned_count": int}}.

    Responds to /events/coordinator-load with rows for exactly the ids in the
    request body, the same way the real endpoint would for any subset --
    covers both a single-coordinator recheck and a full-pool pick with one
    fake, regardless of how many times it is called in one request.
    """

    async def _post(path, **kwargs):
        assert path == "/events/coordinator-load", f"unexpected events.post({path!r})"
        requested = kwargs["json"]["coordinator_ids"]
        rows = [{"coordinator_id": cid, **all_loads[cid]} for cid in requested]
        return load_response(rows)

    return _post


def events_post_side_effect_with_loads(all_loads: dict, extra_path: str, extra_response):
    """Like `events_post_coordinator_load_side_effect`, plus one more exact
    path (e.g. a resubmit's `/events/{id}/submit/internal`) that returns a
    fixed response -- covers a resubmit's recheck-then-create in one fake.
    """

    async def _post(path, **kwargs):
        if path == "/events/coordinator-load":
            requested = kwargs["json"]["coordinator_ids"]
            rows = [{"coordinator_id": cid, **all_loads[cid]} for cid in requested]
            return load_response(rows)
        if path == extra_path:
            return extra_response
        raise AssertionError(f"unexpected events.post({path!r})")

    return _post


def events_patch_side_effect(plain_response=None, internal_response=None):
    """A `.patch(path, **kwargs)` side_effect covering the plain forward-patch
    path and the reassignment-carrying internal one."""

    async def _patch(path, **kwargs):
        if path.endswith("/internal"):
            assert internal_response is not None, f"unexpected events.patch({path!r})"
            return internal_response
        assert plain_response is not None, f"unexpected events.patch({path!r})"
        return plain_response

    return _patch


@pytest.fixture
def users():
    """Fakes the users-service AsyncClient: .get() is an AsyncMock."""
    client = MagicMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    return client


@pytest.fixture
def events():
    """Fakes the events-service AsyncClient methods with AsyncMocks."""
    client = MagicMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.patch = AsyncMock()
    client.put = AsyncMock()
    return client


@pytest.fixture
def notifications():
    return MagicMock(post=AsyncMock(return_value=fake_response(201, [])))


@pytest.fixture
def bookings():
    """S-61: fakes the bookings-service AsyncClient."""
    return MagicMock(delete=AsyncMock())


@pytest.fixture
def equipment():
    return MagicMock(get=AsyncMock())


@pytest.fixture
def registrations():
    """S-69: fakes the registrations-service AsyncClient. No one holds a place
    or waits unless a test says so."""
    return MagicMock(get=AsyncMock(return_value=fake_response(200, [])))


@pytest.fixture
def client(users, events, notifications, bookings, equipment, registrations):
    app.dependency_overrides[get_users_client] = lambda: users
    app.dependency_overrides[get_events_client] = lambda: events
    app.dependency_overrides[get_notifications_client] = lambda: notifications
    app.dependency_overrides[get_bookings_client] = lambda: bookings
    app.dependency_overrides[get_equipment_client] = lambda: equipment
    app.dependency_overrides[get_registrations_client] = lambda: registrations
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
