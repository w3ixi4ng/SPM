"""Fixtures for the events service's isolated unit tests."""

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

SERVICE = Path(__file__).resolve().parents[4] / "backend" / "services" / "atomic" / "events"

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
    authorization_module = importlib.import_module("authorization")
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
EventDraftCreate = schemas_module.EventDraftCreate
EventDraftUpdate = schemas_module.EventDraftUpdate
EventSubmittedCreate = schemas_module.EventSubmittedCreate
EVENT_ORGANISER_PERMISSIONS = authorization_module.EVENT_ORGANISER_PERMISSIONS
ROLE_PERMISSIONS = authorization_module.ROLE_PERMISSIONS

ORGANISER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"
EVENT_ID = "33333333-3333-4333-8333-333333333333"


def fake_user(user_id=ORGANISER_ID, role="event_organiser"):
    metadata = {} if role is None else {"role": role}
    return SimpleNamespace(id=user_id, app_metadata=metadata)


def authenticate(client, auth, user=None):
    client.cookies.set("sb_access_token", "access-token")
    auth.auth.get_user.return_value = SimpleNamespace(user=user or fake_user())


def event_row(**changes):
    row = {
        "id": EVENT_ID,
        "organiser_id": ORGANISER_ID,
        "status": "draft",
        "name": None,
        "purpose": None,
        "start_date": None,
        "start_time": None,
        "end_date": None,
        "end_time": None,
        "expected_attendance": None,
        "venue": None,
        "equipment_requests": {},
        "accessibility_requirements": None,
        "created_at": "2026-09-14T00:00:00Z",
        "updated_at": "2026-09-14T00:00:00Z",
    }
    row.update(changes)
    return row


def on_insert(db, rows=None, error=None):
    operation = db.schema.return_value.table.return_value.insert.return_value
    if error is not None:
        operation.execute.side_effect = error
    else:
        operation.execute.return_value = SimpleNamespace(data=rows)


def on_owned_select(db, rows):
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)


def on_owned_list(db, rows=None, error=None):
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value.order.return_value
    )
    if error is not None:
        operation.execute.side_effect = error
    else:
        operation.execute.return_value = SimpleNamespace(data=rows)


def on_update(db, rows):
    # Three .eq() calls: id, organiser_id, and status='draft' -- this is the
    # draft-to-submitted transition (POST /events/{id}/submit), which is
    # still only allowed from a draft.
    operation = (
        db.schema.return_value.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)


def on_update_owned(db, rows):
    # Two .eq() calls: id and organiser_id only -- PATCH /events/{id} edits
    # an owned event regardless of its status, so there is no status filter
    # to chain a third .eq() onto.
    operation = (
        db.schema.return_value.table.return_value.update.return_value.eq.return_value.eq.return_value
    )
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
