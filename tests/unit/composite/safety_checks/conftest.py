"""Fixtures for the S-86 safety_checks composite."""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

SERVICE = Path(__file__).resolve().parents[4] / "backend" / "services" / "composite" / "safety_checks"

os.environ.setdefault("USERS_SERVICE_URL", "http://users:8001")
os.environ.setdefault("EVENTS_SERVICE_URL", "http://events:8002")
os.environ.setdefault("VENUES_SERVICE_URL", "http://venues:8003")
os.environ.setdefault("BOOKINGS_SERVICE_URL", "http://bookings:8004")
os.environ.setdefault("EQUIPMENT_SERVICE_URL", "http://equipment:8005")
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


@pytest.fixture
def services():
    clients = {
        "users": AsyncMock(),
        "events": AsyncMock(),
        "venues": AsyncMock(),
        "bookings": AsyncMock(),
        "equipment": AsyncMock(),
        "notifications": AsyncMock(),
    }
    clients["notifications"].post.return_value.status_code = 201
    return clients


@pytest.fixture
def client(services):
    app_module.app.dependency_overrides[clients_module.get_users_client] = lambda: services["users"]
    app_module.app.dependency_overrides[clients_module.get_events_client] = lambda: services["events"]
    app_module.app.dependency_overrides[clients_module.get_venues_client] = lambda: services["venues"]
    app_module.app.dependency_overrides[clients_module.get_bookings_client] = lambda: services["bookings"]
    app_module.app.dependency_overrides[clients_module.get_equipment_client] = lambda: services["equipment"]
    app_module.app.dependency_overrides[clients_module.get_notifications_client] = lambda: services["notifications"]
    with TestClient(app_module.app) as test_client:
        yield test_client
    app_module.app.dependency_overrides.clear()

