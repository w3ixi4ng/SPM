"""Verify the session at the atomic decision boundary, including direct calls."""

from threading import Lock

from fastapi import Depends, HTTPException, Request
from supabase import Client

from database import get_auth


# supabase-py's synchronous auth client carries mutable session state and is
# not safe for simultaneous calls from FastAPI's worker threads. Serialise
# token verification while retaining the one reusable client required by the
# service; the booking write itself remains concurrent and database-atomic.
_auth_lock = Lock()


def require_user(request: Request, auth: Client = Depends(get_auth)):
    token = request.cookies.get("sb_access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        with _auth_lock:
            user = auth.auth.get_user(token).user
    except Exception:
        user = None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_venue_staff(user=Depends(require_user)):
    if (getattr(user, "app_metadata", None) or {}).get("role") != "venue_staff":
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


def require_event_coordinator(user=Depends(require_user)):
    if (getattr(user, "app_metadata", None) or {}).get("role") != "event_coordinator":
        raise HTTPException(status_code=403, detail="Permission denied")
    return user
