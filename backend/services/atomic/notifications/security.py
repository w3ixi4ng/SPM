"""Cookie authentication for the notifications service."""

import logging
import os
import time

from fastapi import Depends, HTTPException, Request, Response, status
from supabase import Client

from database import get_auth

try:  # supabase-py re-exports the auth errors
    from supabase import AuthApiError
except ImportError:  # pragma: no cover - older releases keep them here
    try:
        from supabase_auth.errors import AuthApiError
    except ImportError:
        from gotrue.errors import AuthApiError

logger = logging.getLogger(__name__)

ACCESS_COOKIE = "sb_access_token"
REFRESH_COOKIE = "sb_refresh_token"
COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "true").lower() != "false"
COOKIE_SAMESITE = "lax"
REFRESH_MAX_AGE = 60 * 60 * 24 * 30


def set_session_cookies(response: Response, session) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        session.access_token,
        max_age=getattr(session, "expires_in", None) or 3600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=REFRESH_MAX_AGE,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(
            name,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            path="/",
        )


# Pauses before each retry of an Auth call that never got a verdict. Ported
# from the users service (TC-USERS-035..038).
AUTH_RETRY_DELAYS = (0.2, 0.5)
AUTH_UNAVAILABLE = "Authentication service unavailable"


def _rejected(exc: Exception) -> bool:
    """Supabase looked at the token and said no: expired, revoked, malformed
    or already used. Anything else -- a dropped connection, a timeout, a 5xx
    or a 429 -- says nothing about the token."""
    status_code = getattr(exc, "status", None)
    return (
        isinstance(exc, AuthApiError)
        and isinstance(status_code, int)
        and 400 <= status_code < 500
        and status_code != 429
    )


def _ask_auth(call):
    """The answer to `call`, or None if Supabase rejected the token.

    A call that got no verdict is retried; if it never gets one, that is a
    503, never a 401 -- treating a network blip as a dead session signs a
    working user out, and fails a composite's call on their behalf.
    """
    for delay in (*AUTH_RETRY_DELAYS, None):
        try:
            return call()
        except Exception as exc:
            if _rejected(exc):
                return None
            if delay is None:
                logger.warning("Supabase Auth gave no verdict: %r", exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=AUTH_UNAVAILABLE,
                ) from exc
            time.sleep(delay)


def get_current_user(
    request: Request,
    response: Response,
    auth: Client = Depends(get_auth),
):
    access_token = request.cookies.get(ACCESS_COOKIE)
    if access_token:
        # Expired, revoked, or malformed all mean the same thing here: fall
        # through and try the refresh token. No answer at all is a 503.
        answer = _ask_auth(lambda: auth.auth.get_user(access_token))
        user = answer.user if answer is not None else None
        if user is not None:
            return user

    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if refresh_token:
        renewed = _ask_auth(lambda: auth.auth.refresh_session(refresh_token))
        if renewed is not None and renewed.session is not None and renewed.user is not None:
            set_session_cookies(response, renewed.session)
            return renewed.user

    request.state.clear_session = True
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
