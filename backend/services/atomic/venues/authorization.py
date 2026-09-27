"""Trusted role-to-permission policy for the venues service."""

from fastapi import Depends, HTTPException, status

from security import get_current_user

CREATE_PERMISSION = "venues:create"
UPDATE_PERMISSION = "venues:update"
VIEW_PERMISSION = "venues:view"

# Every recognized role is listed so an unknown role is told apart from a
# known one without venue access. Mirrored for presentation only by
# frontend/src/lib/access.js; this file is the one that is enforced.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "venue_staff": frozenset({CREATE_PERMISSION, VIEW_PERMISSION, UPDATE_PERMISSION}),
    "event_coordinator": frozenset({VIEW_PERMISSION}),
    "event_organiser": frozenset(),
    "technical_support": frozenset(),
    "attendee": frozenset(),
}


def require_permission(permission: str):
    """Return a dependency that authorizes a verified user's trusted role."""

    def authorize(user=Depends(get_current_user)):
        app_metadata = getattr(user, "app_metadata", None) or {}
        role = app_metadata.get("role")

        if role not in ROLE_PERMISSIONS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Recognized role required",
            )

        if permission not in ROLE_PERMISSIONS[role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )

        return user

    return authorize
