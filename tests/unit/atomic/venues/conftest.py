"""Fixtures for the venues service's isolated unit tests."""

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

SERVICE = Path(__file__).resolve().parents[4] / "backend" / "services" / "atomic" / "venues"

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

# Services use flat imports because each Docker image runs from its own folder.
# Load this service while preserving any same-named modules another service's
# conftest already loaded, so `pytest tests/unit` remains collectable.
_MODULE_NAMES = ("app", "authorization", "database", "schemas", "security")
_saved_modules = {name: sys.modules.get(name) for name in _MODULE_NAMES}
for _name in _MODULE_NAMES:
    sys.modules.pop(_name, None)
sys.path.insert(0, str(SERVICE))
try:
    app_module = importlib.import_module("app")
    database_module = importlib.import_module("database")
    schemas_module = importlib.import_module("schemas")
finally:
    sys.path.remove(str(SERVICE))
    for _name in _MODULE_NAMES:
        sys.modules.pop(_name, None)
        if _saved_modules[_name] is not None:
            sys.modules[_name] = _saved_modules[_name]

app = app_module.app
get_auth = database_module.get_auth
get_db = database_module.get_db
VenueCreate = schemas_module.VenueCreate

STAFF_ID = "11111111-1111-1111-1111-111111111111"
VENUE_ID = "22222222-2222-2222-2222-222222222222"
MISSING_ID = "33333333-3333-3333-3333-333333333333"

VALID_VENUE = {
    "name": "Harbourfront Hall",
    "location": "1 Harbourfront Walk, Singapore 098585",
    "capacity": 250,
    "facilities": ["projector", "wifi", "stage"],
    "accessibility": ["wheelchair_access", "accessible_toilets"],
    "room_layouts": ["theatre", "banquet"],
    "operating_hours": [
        {"day": "mon", "open": "09:00", "close": "18:00"},
        {"day": "sat", "open": "10:00", "close": "22:00"},
    ],
    "description": "Waterfront hall with a raised stage.",
}

MINIMAL_VENUE = {
    "name": "Studio B",
    "location": "10 Anson Road, Singapore 079903",
    "capacity": 30,
    "room_layouts": ["boardroom"],
    "operating_hours": [{"day": "tue", "open": "08:00", "close": "17:00"}],
}

# VALID_VENUE as the service sends it to Supabase: times serialised in full,
# and S-75's setup and turnaround defaulting to 0.
VALID_VENUE_STORED = {
    **VALID_VENUE,
    "setup_minutes": 0,
    "turnaround_minutes": 0,
    "operating_hours": [
        {"day": "mon", "open": "09:00:00", "close": "18:00:00"},
        {"day": "sat", "open": "10:00:00", "close": "22:00:00"},
    ],
}


def fake_user(user_id=STAFF_ID, role="venue_staff"):
    metadata = {} if role is None else {"role": role}
    return SimpleNamespace(id=user_id, app_metadata=metadata)


def authenticate(client, auth, user=None):
    client.cookies.set("sb_access_token", "access-token")
    auth.auth.get_user.return_value = SimpleNamespace(user=user or fake_user())


def venue_row(**changes):
    row = {
        **VALID_VENUE_STORED,
        "id": VENUE_ID,
        "created_by": STAFF_ID,
        "created_at": "2026-09-26T08:00:00+00:00",
    }
    row.update(changes)
    return row


def insert_operation(db):
    return db.schema.return_value.table.return_value.insert.return_value


def list_operation(db):
    return db.schema.return_value.table.return_value.select.return_value.order.return_value


def get_operation(db):
    return db.schema.return_value.table.return_value.select.return_value.eq.return_value


def returns(operation, rows):
    operation.execute.return_value = SimpleNamespace(data=rows)


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def auth():
    return MagicMock()


@pytest.fixture
def client(db, auth):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_auth] = lambda: auth
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
