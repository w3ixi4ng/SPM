"""Fixtures for the registrations service's isolated unit tests."""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

SERVICE = (
    Path(__file__).resolve().parents[4] / "backend" / "services" / "atomic" / "registrations"
)

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

# Services use flat imports because each Docker image runs from its own folder.
# Load this service while preserving any same-named modules another service's
# conftest already loaded, so `pytest tests/unit` remains collectable.
_MODULE_NAMES = ("app", "authorization", "clients", "database", "schemas", "security")
_saved_modules = {name: sys.modules.get(name) for name in _MODULE_NAMES}
for _name in _MODULE_NAMES:
    sys.modules.pop(_name, None)
sys.path.insert(0, str(SERVICE))
try:
    app_module = importlib.import_module("app")
    database_module = importlib.import_module("database")
finally:
    sys.path.remove(str(SERVICE))
    for _name in _MODULE_NAMES:
        sys.modules.pop(_name, None)
        if _saved_modules[_name] is not None:
            sys.modules[_name] = _saved_modules[_name]

app = app_module.app
get_db = database_module.get_db

EVENT_ID = "22222222-2222-4222-8222-222222222222"
ATTENDEE_A = "33333333-3333-4333-8333-333333333333"
ATTENDEE_B = "44444444-4444-4444-8444-444444444444"
REGISTRATION_ID = "55555555-5555-4555-8555-555555555555"


def registration_row(**changes):
    row = {
        "id": REGISTRATION_ID,
        "event_id": EVENT_ID,
        "attendee_id": ATTENDEE_A,
        "created_at": "2026-11-05T04:00:00Z",
    }
    row.update(changes)
    return row


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
