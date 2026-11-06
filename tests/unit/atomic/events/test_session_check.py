"""Session check: a rejected token vs Supabase Auth not answering.

TC-EVENTS-458..461. Ported from the users service (TC-USERS-035..038): only a 4xx other
than 429 is a verdict on the token; anything else is retried, then a 503.
"""
from types import SimpleNamespace

import httpx
import pytest
from supabase import AuthApiError

from .conftest import app, authenticate, fake_user, on_owned_list

PATH = "/events"


def auth_error(message, status):
    return AuthApiError(message, status, None)


def send(client):
    return client.get(PATH)


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

    route = next(r for r in app.routes if getattr(r, "path", None) == "/events")
    for check in checks(route.dependant):
        monkeypatch.setitem(check.__globals__, "AUTH_RETRY_DELAYS", (0, 0))


def caller():
    return fake_user()


def succeed(db):
    on_owned_list(db, [])


# --- TC-EVENTS-458 ---------------------------------------------------------
def test_a_rejected_token_is_401_without_retrying(client, auth, no_retry_pause):
    client.cookies.set("sb_access_token", "revoked-token")
    auth.auth.get_user.side_effect = auth_error("invalid JWT", 403)

    response = send(client)

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    assert auth.auth.get_user.call_count == 1


# --- TC-EVENTS-459 ---------------------------------------------------------
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

    assert response.status_code == 200, response.text
    assert response.json() == []
    assert auth.auth.get_user.call_count == 2


# --- TC-EVENTS-460 ---------------------------------------------------------
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
    client.cookies.set("sb_refresh_token", "refresh-token")
    auth.auth.get_user.side_effect = failure

    response = send(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication service unavailable"
    assert auth.auth.get_user.call_count == 3
    # No verdict on the token is not a logout.
    auth.auth.refresh_session.assert_not_called()
    assert set_cookies(response) == {}


# --- TC-EVENTS-461 ---------------------------------------------------------
def test_a_refresh_that_got_no_answer_is_retried(client, db, auth, no_retry_pause):
    client.cookies.set("sb_access_token", "expired-token")
    client.cookies.set("sb_refresh_token", "refresh-token")
    auth.auth.get_user.side_effect = auth_error("token is expired", 401)
    session = SimpleNamespace(
        access_token="new-access", refresh_token="new-refresh", expires_in=3600,
    )
    auth.auth.refresh_session.side_effect = [
        httpx.RemoteProtocolError("Server disconnected"),
        SimpleNamespace(user=caller(), session=session),
    ]
    succeed(db)

    response = send(client)

    assert response.status_code == 200, response.text
    assert auth.auth.refresh_session.call_count == 2
    assert "new-access" in set_cookies(response)["sb_access_token"]
