"""Verify the session at the atomic decision boundary, including direct calls."""

import hmac
import logging
import os
import time
from threading import Lock

from fastapi import Depends, HTTPException, Request, status
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


# supabase-py's synchronous auth client carries mutable session state and is
# not safe for simultaneous calls from FastAPI's worker threads. Serialise
# token verification while retaining the one reusable client required by the
# service; the booking write itself remains concurrent and database-atomic.
_auth_lock = Lock()


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


def _ask_auth(auth: Client, token: str):
    """The verified answer for `token`, or None if Supabase rejected it.

    A call that got no verdict is retried; if it never gets one, that is a
    503, never a 401. The lock is held per attempt, not across the pauses,
    so one slow verification doesn't hold up every other request.
    """
    for delay in (*AUTH_RETRY_DELAYS, None):
        try:
            with _auth_lock:
                return auth.auth.get_user(token)
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


def require_user(request: Request, auth: Client = Depends(get_auth)):
    token = request.cookies.get("sb_access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    answer = _ask_auth(auth, token)
    user = answer.user if answer is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_venue_staff(user=Depends(require_user)):
    if (getattr(user, "app_metadata", None) or {}).get("role") != "venue_staff":
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


def require_coordinator(user=Depends(require_user)):
    """S-78: a Coordinator resolving a booking's flag. Which events are theirs
    is the events service's to say; the venue_bookings composite asks it."""
    if (getattr(user, "app_metadata", None) or {}).get("role") != "event_coordinator":
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


def require_assignment_service(request: Request):
    secret = os.environ.get("ASSIGNMENT_SERVICE_SECRET")
    supplied = request.headers.get("X-Assignment-Service-Token", "")
    if not secret or not hmac.compare_digest(supplied, secret):
        raise HTTPException(status_code=403, detail="Permission denied")
