"""Trusted role-to-permission policy for the equipment service."""

from fastapi import Depends, HTTPException, status

from security import get_current_user

CREATE_PERMISSION = "equipment:create"
MANAGE_VIEW_PERMISSION = "equipment:view_catalogue"
SELECTION_PERMISSION = "equipment:view_selection"

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "technical_support": frozenset(
        {CREATE_PERMISSION, MANAGE_VIEW_PERMISSION, SELECTION_PERMISSION}
    ),
    # S-40 moves requirement editing to the assigned Coordinator. The existing
    # organiser event form still consumes selection data until that story.
    "event_coordinator": frozenset({SELECTION_PERMISSION}),
    "event_organiser": frozenset({SELECTION_PERMISSION}),
    "venue_staff": frozenset(),
    "attendee": frozenset(),
}


def require_permission(permission: str):
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
