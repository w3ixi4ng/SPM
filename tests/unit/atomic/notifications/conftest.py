import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

SERVICE = Path(__file__).resolve().parents[4] / "backend" / "services" / "atomic" / "notifications"

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

_MODULE_NAMES = ("app", "database", "schemas", "security")
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
get_auth = database_module.get_auth

RECIPIENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ORGANISER = "11111111-1111-4111-8111-111111111111"
EVENT_ID = "33333333-3333-4333-8333-333333333333"


def notification_row(recipient_id=RECIPIENT, row_id=1, **changes):
    row = {
        "id": row_id,
        "recipient_id": recipient_id,
        "event_id": EVENT_ID,
        "event_name": "Autumn Forum",
        "kind": "event_assignment",
        "message": "You have been assigned to Autumn Forum.",
        "deduplication_key": f"event_assignment:{EVENT_ID}:{recipient_id}",
        "created_at": "2026-10-08T12:00:00Z",
    }
    row.update(changes)
    return row


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


def authenticate(client, auth, user_id=RECIPIENT):
    client.cookies.set("sb_access_token", "access-token")
    auth.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id=user_id, app_metadata={"role": "event_coordinator"})
    )
