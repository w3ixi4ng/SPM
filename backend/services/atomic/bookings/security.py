"""Verify the session at the atomic decision boundary, including direct calls."""

from fastapi import Depends, HTTPException, Request
from supabase import Client

from database import get_auth


def require_venue_staff(request: Request, auth: Client = Depends(get_auth)):
    token = request.cookies.get("sb_access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user = auth.auth.get_user(token).user
    except Exception:
        user = None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if (getattr(user, "app_metadata", None) or {}).get("role") != "venue_staff":
        raise HTTPException(status_code=403, detail="Permission denied")
    return user
