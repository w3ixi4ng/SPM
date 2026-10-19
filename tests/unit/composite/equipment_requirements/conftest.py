"""Isolated outbound-service fakes for S-40 orchestration tests."""

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
    / "equipment_requirements"
)

os.environ.setdefault("USERS_SERVICE_URL", "http://users:8001")
os.environ.setdefault("EVENTS_SERVICE_URL", "http://events:8002")
os.environ.setdefault("EQUIPMENT_SERVICE_URL", "http://equipment:8005")

_MODULE_NAMES = ("app", "availability", "clients", "schemas")
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
get_equipment_client = clients_module.get_equipment_client

COORDINATOR_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
NEW_COORDINATOR_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
SUPPORT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
EVENT_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
SECOND_EVENT_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff"
ITEM_ID = "22222222-2222-4222-8222-222222222222"
REQUIREMENT_ID = "33333333-3333-4333-8333-333333333333"


def fake_response(status_code, body=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = body
    return response


def user(role="event_coordinator", user_id=COORDINATOR_ID):
    return {
        "id": user_id,
        "name": "Grace Hopper",
        "email": "grace@example.com",
        "role": role,
    }


def event(
    status="planning",
    coordinator_id=COORDINATOR_ID,
    event_id=EVENT_ID,
    support_id=SUPPORT_ID,
):
    return {
        "id": event_id,
        "status": status,
        "assigned_coordinator_id": coordinator_id,
        "assigned_technical_support_id": support_id,
        "name": "Alumni evening",
    }


def requirement(quantity=6, recorded_by=COORDINATOR_ID):
    return {
        "id": REQUIREMENT_ID,
        "event_id": EVENT_ID,
        "equipment_item_id": ITEM_ID,
        "required_quantity": quantity,
        "recorded_by_coordinator_id": recorded_by,
        "created_at": "2026-09-27T09:00:00Z",
        "updated_at": "2026-09-27T09:00:00Z",
        "equipment": {
            "id": ITEM_ID,
            "type": "Wireless Microphone",
            "description": None,
            "total_quantity": 12,
            "operational_status": "available",
            "lifecycle_status": "active",
        },
    }


class Services:
    def __init__(self):
        self.me = fake_response(200, user())
        self.assigned_event = fake_response(200, event())
        self.support_events = fake_response(200, [event()])
        self.support_event = fake_response(200, event())
        self.saved = fake_response(200, requirement())
        self.listed = fake_response(200, [requirement()])
        self.deleted = fake_response(204)

        self.users = MagicMock()
        self.users.get = AsyncMock(side_effect=lambda *args, **kwargs: self.me)
        self.events = MagicMock()
        self.events.get = AsyncMock(side_effect=self._event_response)
        # S-17: a requirement change clears the sign-off first; sign-off
        # itself is a PUT. Tests that need other answers replace these.
        self.cleared = fake_response(200, event())
        self.signed = fake_response(200, event())
        self.events.post = AsyncMock(side_effect=lambda *args, **kwargs: self.cleared)
        self.events.put = AsyncMock(side_effect=lambda *args, **kwargs: self.signed)
        self.equipment = MagicMock()
        self.equipment.put = AsyncMock(side_effect=lambda *args, **kwargs: self.saved)
        self.equipment.get = AsyncMock(side_effect=lambda *args, **kwargs: self.listed)
        self.equipment.delete = AsyncMock(side_effect=lambda *args, **kwargs: self.deleted)

    def _event_response(self, path, *args, **kwargs):
        if path == "/events/support-assigned":
            return self.support_events
        if path.startswith("/events/support-assigned/"):
            return self.support_event
        return self.assigned_event


@pytest.fixture
def services():
    return Services()


@pytest.fixture
def client(services):
    app.dependency_overrides[get_users_client] = lambda: services.users
    app.dependency_overrides[get_events_client] = lambda: services.events
    app.dependency_overrides[get_equipment_client] = lambda: services.equipment
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
