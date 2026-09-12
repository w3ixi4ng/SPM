"""Session cookies, and working out who is calling from them.

The browser never handles a token. Login writes the Supabase access and
refresh tokens into httpOnly cookies, and every later request is identified
from those, so a cross-site script has nothing to steal.
"""

import os

from fastapi import Depends, HTTPException, Request, Response, status
from supabase import Client

from database import get_auth

ACCESS_COOKIE = "sb_access_token"
REFRESH_COOKIE = "sb_refresh_token"

# Secure is on by default and only worth turning off for plain-http testing.
# Browsers count localhost as a secure origin, so dev over http still works
# with this left alone.
COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "true").lower() != "false"

# Lax, not None: the frontend reaches these routes same-origin through the
# Vite proxy and later through Kong. Going cross-origin would mean SameSite
# None plus CORS with credentials -- see this service's README.
COOKIE_SAMESITE = "lax"

# The refresh cookie outlives the access token, so this is how long a session
# survives without anyone logging in again.
REFRESH_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def set_session_cookies(response: Response, session) -> None:
    """Write a Supabase session to the pair of httpOnly cookies."""
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
    """Expire both cookies. The attributes have to match the ones they were
    set with, or the browser keeps the originals and ignores this."""
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
    """The signed-in Supabase user, or a 401.

    An expired access token is not a logout. The access token lasts an hour
    and a route guard calls this on every page load, so when it has expired
    the refresh cookie is tried, and a renewed session is written back to the
    browser on this same response.
    """
    access_token = request.cookies.get(ACCESS_COOKIE)
    if access_token:
        try:
            user = auth.auth.get_user(access_token).user
        except Exception:
            # Expired, revoked, or malformed -- all of which mean the same
            # thing here. Fall through and try the refresh token.
            user = None
        if user is not None:
            return user

    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if refresh_token:
        try:
            renewed = auth.auth.refresh_session(refresh_token)
        except Exception:
            renewed = None
        if renewed is not None and renewed.session is not None:
            set_session_cookies(response, renewed.session)
            return renewed.user

    # Nothing usable left, so take the dead cookies with us rather than
    # letting the browser send them on every subsequent request. Raising
    # throws this response away, so the flag is what survives into the
    # handler in app.py that does the clearing.
    request.state.clear_session = True
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
