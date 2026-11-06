"""Session check: a rejected token vs Supabase Auth not answering.

TC-BOOKINGS-475..477. Ported from the users service (TC-USERS-035..038): only a 4xx other
than 429 is a verdict on the token; anything else is retried, then a 503.
"""
from types import SimpleNamespace

import httpx
import pytest
from supabase import AuthApiError

from .conftest import BOOKING_ID, app, database_module, table
from unittest.mock import MagicMock

STAFF = "abababab-abab-4bab-8bab-abababababab"


@pytest.fixture
def auth():
    fake = MagicMock()
    app.dependency_overrides[database_module.get_auth] = lambda: fake
    yield fake
    app.dependency_overrides.pop(database_module.get_auth, None)


PATH = f"/bookings/{BOOKING_ID}/decision"


def auth_error(message, status):
    return AuthApiError(message, status, None)


def send(client):
    return client.post(PATH, json={"decision": "approved"})


def set_cookies(response):
    return {
        header.split("=", 1)[0]: header
        for header in response.headers.get_list("set-cookie")
    }


@pytest.fixture
def no_retry_pause(monkeypatch):
    """Retries without the real pauses, patched on the module the route's
    session check actually lives in (every service has a `security`)."""
    def checks(dependant):
        for dep in dependant.dependencies:
            if dep.call.__name__ in ("get_current_user", "require_user"):
                yield dep.call
            yield from checks(dep)

    route = next(r for r in app.routes if getattr(r, "path", None) == "/bookings/{booking_id}/decision")
    for check in checks(route.dependant):
        monkeypatch.setitem(check.__globals__, "AUTH_RETRY_DELAYS", (0, 0))


def caller():
    return SimpleNamespace(id=STAFF, app_metadata={"role": "venue_staff"})


def succeed(db):
    # No booking row: the decision route answers 404 once the session check passes.
    query = table(db).select.return_value
    for method in ("eq", "neq", "in_", "lt", "gt", "lte", "gte", "order", "limit"):
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    update = table(db).update.return_value
    for method in ("eq", "in_", "or_", "lt", "lte"):
        getattr(update, method).return_value = update
    update.execute.return_value = SimpleNamespace(data=[])


# --- TC-BOOKINGS-475 ---------------------------------------------------------
def test_a_rejected_token_is_401_without_retrying(client, auth, no_retry_pause):
    client.cookies.set("sb_access_token", "revoked-token")
    auth.auth.get_user.side_effect = auth_error("invalid JWT", 403)

    response = send(client)

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    assert auth.auth.get_user.call_count == 1


# --- TC-BOOKINGS-476 ---------------------------------------------------------
@pytest.mark.parametrize(
    "blip",
    [httpx.RemoteProtocolError("Server disconnected"), httpx.ReadTimeout("timed out")],
    ids=["dropped", "timeout"],
)
def test_a_session_check_that_got_no_answer_is_retried(client, db, auth, no_retry_pause, blip):
    client.cookies.set("sb_access_token", "access-token")
    auth.auth.get_user.side_effect = [blip, SimpleNamespace(user=caller())]
    succeed(db)

    response = send(client)

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Booking not found"
    assert auth.auth.get_user.call_count == 2


# --- TC-BOOKINGS-477 ---------------------------------------------------------
@pytest.mark.parametrize(
    "failure",
    [
        httpx.RemoteProtocolError("Server disconnected"),
        auth_error("upstream error", 500),
        auth_error("rate limit", 429),
    ],
    ids=["dropped", "500", "429"],
)
def test_no_answer_is_503_and_keeps_the_cookies(client, auth, no_retry_pause, failure):
    client.cookies.set("sb_access_token", "access-token")
    auth.auth.get_user.side_effect = failure

    response = send(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication service unavailable"
    assert auth.auth.get_user.call_count == 3
