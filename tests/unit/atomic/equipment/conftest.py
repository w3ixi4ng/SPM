"""Fixtures for the equipment service's isolated unit tests."""

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

SERVICE = Path(__file__).resolve().parents[4] / "backend" / "services" / "atomic" / "equipment"

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

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
EquipmentCreate = schemas_module.EquipmentCreate
EquipmentRequirementWrite = schemas_module.EquipmentRequirementWrite

STAFF_ID = "11111111-1111-4111-8111-111111111111"
ITEM_ID = "22222222-2222-4222-8222-222222222222"
EVENT_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
REQUIREMENT_ID = "33333333-3333-4333-8333-333333333333"

VALID_ITEM = {
    "type": "Wireless Microphone",
    "description": "Handheld wireless microphone with receiver",
    "total_quantity": 12,
}


def fake_user(user_id=STAFF_ID, role="technical_support"):
    metadata = {} if role is None else {"role": role}
    return SimpleNamespace(id=user_id, app_metadata=metadata)


def authenticate(client, auth, user=None):
    client.cookies.set("sb_access_token", "access-token")
    auth.auth.get_user.return_value = SimpleNamespace(user=user or fake_user())


def equipment_row(**changes):
    row = {
        **VALID_ITEM,
        "id": ITEM_ID,
        "operational_status": "available",
        "lifecycle_status": "active",
        "created_by": STAFF_ID,
        "created_at": "2026-09-27T08:00:00Z",
        "updated_at": "2026-09-27T08:00:00Z",
    }
    row.update(changes)
    return row


def requirement_row(**changes):
    row = {
        "id": REQUIREMENT_ID,
        "event_id": EVENT_ID,
        "equipment_item_id": ITEM_ID,
        "required_quantity": 6,
        "recorded_by_coordinator_id": STAFF_ID,
        "created_at": "2026-09-27T09:00:00Z",
        "updated_at": "2026-09-27T09:00:00Z",
    }
    row.update(changes)
    return row


def requirement_detail(**changes):
    return {
        **requirement_row(),
        "equipment": {
            key: value
            for key, value in equipment_row().items()
            if key not in {"created_by", "created_at", "updated_at"}
        },
        **changes,
    }


def table(db):
    return db.schema.return_value.table.return_value


def insert_operation(db):
    return table(db).insert.return_value


def catalogue_operation(db):
    return table(db).select.return_value.order.return_value


def selection_operation(db):
    return (
        table(db)
        .select.return_value.eq.return_value.eq.return_value.order.return_value
    )


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
