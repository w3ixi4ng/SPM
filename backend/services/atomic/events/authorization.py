"""Trusted role-to-permission policy and FastAPI authorization dependencies."""

from fastapi import Depends, HTTPException, status

from security import get_current_user

DASHBOARD_PERMISSION = "dashboard:view"

EVENT_ORGANISER_EVENT_PERMISSIONS = frozenset(
    {
        "events:create",
        "events:save_draft",
        "events:view_own",
        "events:update_own_draft",
        "events:submit_own",
        # S-62
        "events:request_cancellation",
    }
)

# S-14: a coordinator can now also decide (approve/reject/return) a request
# routed to them, on top of viewing it.
# S-61: and decide on an Organiser's cancellation request.
EVENT_COORDINATOR_EVENT_PERMISSIONS = frozenset({
    "events:view_assigned",
    "events:request_reassignment",
    "events:decide",
    "events:update_assigned",
    "events:decide_cancellation",
})

# Every recognized role may enter its own role dashboard. Add internal-role
# permissions here when the corresponding stories exist, even if their
# endpoint lands in another task.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "event_organiser": frozenset(
        {DASHBOARD_PERMISSION, *EVENT_ORGANISER_EVENT_PERMISSIONS}
    ),
    "event_coordinator": frozenset(
        {DASHBOARD_PERMISSION, *EVENT_COORDINATOR_EVENT_PERMISSIONS}
    ),
    "event_coordinator_lead": frozenset({DASHBOARD_PERMISSION, "events:lead_assignments"}),
    "venue_staff": frozenset({DASHBOARD_PERMISSION, "events:view_booking_status"}),
    "technical_support": frozenset(
        {
            DASHBOARD_PERMISSION,
            "events:view_support_assigned",
            "events:update_equipment_preparation",
        }
    ),
    "attendee": frozenset({DASHBOARD_PERMISSION}),
}

EVENT_ORGANISER_PERMISSIONS = ROLE_PERMISSIONS["event_organiser"]


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
