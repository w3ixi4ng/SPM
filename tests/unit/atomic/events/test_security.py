"""Auth failures on the events service must not masquerade as dead sessions."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException, Request, Response
from supabase_auth.errors import AuthApiError

from .conftest import app_module, fake_user


def request_with_cookies(value="sb_access_token=access-token"):
    return Request({"type": "http", "method": "GET", "path": "/events/example",
                    "headers": [(b"cookie", value.encode())]})


@pytest.fixture(autouse=True)
def no_auth_retry_pause(monkeypatch):
    monkeypatch.setitem(app_module.get_current_user.__globals__, "AUTH_RETRY_DELAYS", (0, 0))


def test_dropped_auth_check_retries_the_same_access_token():
    auth = MagicMock()
    user = fake_user()
    auth.auth.get_user.side_effect = [httpx.RemoteProtocolError("Server disconnected"),
                                      SimpleNamespace(user=user)]
    request, response = request_with_cookies(), Response()

    assert app_module.get_current_user(request, response, auth) is user
    assert auth.auth.get_user.call_count == 2
    auth.auth.get_user.assert_called_with("access-token")
    auth.auth.refresh_session.assert_not_called()


@pytest.mark.parametrize("failure", [
    httpx.RemoteProtocolError("Server disconnected"),
    AuthApiError("Auth unavailable", 500, None),
    AuthApiError("rate limited", 429, None),
])
def test_auth_without_a_verdict_returns_503_and_keeps_cookies(failure):
    auth = MagicMock()
    auth.auth.get_user.side_effect = failure
    request, response = request_with_cookies("sb_access_token=access-token; sb_refresh_token=refresh-token"), Response()

    with pytest.raises(HTTPException) as caught:
        app_module.get_current_user(request, response, auth)

    assert caught.value.status_code == 503
    assert caught.value.detail == "Authentication service unavailable"
    assert auth.auth.get_user.call_count == 3
    auth.auth.refresh_session.assert_not_called()
    assert not getattr(request.state, "clear_session", False)
    assert "set-cookie" not in response.headers


def test_rejected_access_token_is_401_without_retry():
    auth = MagicMock()
    auth.auth.get_user.side_effect = AuthApiError("invalid JWT", 401, None)
    request, response = request_with_cookies(), Response()

    with pytest.raises(HTTPException) as caught:
        app_module.get_current_user(request, response, auth)

    assert caught.value.status_code == 401
    auth.auth.get_user.assert_called_once_with("access-token")
    assert request.state.clear_session is True


def test_refresh_retries_after_a_dropped_connection():
    auth = MagicMock()
    auth.auth.get_user.side_effect = AuthApiError("expired", 401, None)
    user = fake_user()
    auth.auth.refresh_session.side_effect = [
        httpx.RemoteProtocolError("Server disconnected"),
        SimpleNamespace(user=user, session=SimpleNamespace(
            access_token="new-access", refresh_token="new-refresh", expires_in=3600)),
    ]
    request, response = request_with_cookies("sb_access_token=old; sb_refresh_token=refresh-token"), Response()

    assert app_module.get_current_user(request, response, auth) is user
    assert auth.auth.refresh_session.call_count == 2
    assert "new-access" in response.headers["set-cookie"]
