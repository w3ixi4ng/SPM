"""Fixtures for the users service's unit tests.

Nothing here touches a network. Supabase is a MagicMock in both of its roles --
the table client and the auth client -- swapped in through
``app.dependency_overrides``, which is the seam ``get_db`` and ``get_auth``
exist to provide.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

SERVICE = Path(__file__).resolve().parents[4] / "backend" / "services" / "atomic" / "users"
sys.path.insert(0, str(SERVICE))

# database.py reads these at import and builds both clients, so they have to
# exist before `app` can be imported. The values are never used: every client
# is replaced below.
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

USER_ID = "11111111-1111-4111-8111-111111111111"
EMAIL = "ada@example.com"
NAME = "Ada Lovelace"
PROFILE = {"id": USER_ID, "name": NAME, "email": EMAIL, "created_at": "2026-09-12T00:00:00Z"}


def fake_session(access="access-token", refresh="refresh-token", expires_in=3600):
    return SimpleNamespace(
        access_token=access, refresh_token=refresh, expires_in=expires_in
    )


def fake_user(uid=USER_ID, email=EMAIL, role="event_organiser"):
    app_metadata = {} if role is None else {"role": role}
    return SimpleNamespace(id=uid, email=email, app_metadata=app_metadata)


def on_select(db, rows):
    """Point .schema().table().select().eq().execute() at one result."""
    chain = db.schema.return_value.table.return_value.select.return_value.eq.return_value
    chain.execute.return_value = SimpleNamespace(data=rows)


def on_insert(db, rows=None, error=None):
    """Point .schema().table().insert().execute() at a result, or make it raise."""
    chain = db.schema.return_value.table.return_value.insert.return_value
    if error is not None:
        chain.execute.side_effect = error
    else:
        chain.execute.return_value = SimpleNamespace(data=rows)


def on_in(db, rows):
    """Point .schema().table().select().in_().execute() at a result."""
    chain = db.schema.return_value.table.return_value.select.return_value.in_.return_value
    chain.execute.return_value = SimpleNamespace(data=rows)


def auth_admin_user(uid, role, email=None, user_metadata=None):
    """A Supabase Auth admin-listing user -- only the fields the route reads."""
    return SimpleNamespace(
        id=uid,
        email=email,
        user_metadata=user_metadata or {},
        app_metadata={} if role is None else {"role": role},
    )


@pytest.fixture
def db():
    """Stands in for the service_role client -- the profile table."""
    return MagicMock()


@pytest.fixture
def auth():
    """Stands in for the anon client -- Supabase Auth."""
    return MagicMock()


@pytest.fixture
def client(db, auth):
    from app import app
    from database import get_auth, get_db

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_auth] = lambda: auth
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# Imported through the service so the tests raise the same exception class the
# routes catch, whichever supabase-py release is installed.
from app import AuthApiError  # noqa: E402  -- env above has to be set first


def auth_error(message, status=400, code=None):
    """A Supabase Auth failure, built against either constructor signature."""
    try:
        return AuthApiError(message, status, code)
    except TypeError:  # pragma: no cover - older releases take two arguments
        return AuthApiError(message, status)
