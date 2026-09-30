"""Fixtures for the bookings service's isolated unit tests."""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

SERVICE = Path(__file__).resolve().parents[4] / "backend" / "services" / "atomic" / "bookings"

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")

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

BOOKING_ID = "44444444-4444-4444-8444-444444444444"

BOOKING = {
    "event_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
    "venue_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    "coordinator_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    "coordinator_name": "Grace Hopper",
    "coordinator_email": "grace@example.com",
    "booking_date": "2026-11-12",
    "start_time": "09:00",
    "end_time": "12:00",
    "event_name": "Alumni networking evening",
    "event_purpose": "Reconnect graduates with faculty",
    "expected_attendance": 120,
    "special_requirements": "Vegetarian catering for 40",
    "required_accessibility": ["wheelchair_access", "lift"],
    "required_facilities": ["projector", "sound_system"],
    "room_layout": "theatre",
    "notes": "Access from 08:30 for setup",
    "venue_name": "Studio B",
}

# BOOKING as the service sends it to Supabase: times serialised in full.
BOOKING_STORED = {**BOOKING, "start_time": "09:00:00", "end_time": "12:00:00"}


def booking_row(**changes):
    row = {
        **BOOKING_STORED,
        "id": BOOKING_ID,
        "status": "pending",
        "submitted_at": "2026-10-01T09:00:00+00:00",
    }
    row.update(changes)
    return row


def table(db):
    return db.schema.return_value.table.return_value


def lookups(db, *results):
    """S-30: every filtered select returns the same query object, and each
    execute returns the next result in turn -- the overlap check, then the
    block check. With no results, every lookup finds nothing."""
    query = table(db).select.return_value
    for method in ("eq", "neq", "in_", "lt", "gt", "lte", "gte", "order", "limit"):
        getattr(query, method).return_value = query
    if results:
        query.execute.side_effect = [MagicMock(data=rows) for rows in results]
    else:
        query.execute.return_value = MagicMock(data=[])
    return query


def on_insert(db, rows):
    lookups(db)
    table(db).insert.return_value.execute.return_value = MagicMock(data=rows)


def on_pending_list(db, rows):
    (
        table(db).select.return_value.eq.return_value.order.return_value.execute.return_value
    ) = MagicMock(data=rows)


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
