"""Cookie authentication and role checks for the events service."""

import os

from fastapi import Depends, HTTPException, Request, Response, status
from supabase import Client

from database import get_auth

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


def get_current_user(
    request: Request,
    response: Response,
    auth: Client = Depends(get_auth),
):
    """Return the verified Supabase user represented by the session cookies."""
    access_token = request.cookies.get(ACCESS_COOKIE)
    if access_token:
        try:
            user = auth.auth.get_user(access_token).user
        except Exception:
            user = None
        if user is not None:
            return user

    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if refresh_token:
        try:
            renewed = auth.auth.refresh_session(refresh_token)
        except Exception:
            renewed = None
        if (
            renewed is not None
            and renewed.session is not None
            and renewed.user is not None
        ):
            set_session_cookies(response, renewed.session)
            return renewed.user

    request.state.clear_session = True
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
