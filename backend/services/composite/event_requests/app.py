"""Composite service for submitting and assigning event requests.

Spans two entities -- events and users -- which is why this lives here and
not in either atomic service (see AGENTS.md: "Atomic services never call
other services. ... Anything spanning two entities is a composite service").
Owns no table of its own; every write ends up in ``events.events`` by way of
the events service's internal routes.
"""

import logging
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from clients import get_events_client, get_notifications_client, get_users_client
from schemas import (
    CoordinatorAssignmentCreate,
    EventRequestSubmit,
    EventRequestUpdate,
    TechnicalSupportRequest,
)

app = FastAPI(title="Event Requests Service")
logger = logging.getLogger(__name__)

ORGANISER_ROLE = "event_organiser"
COORDINATOR_ROLE = "event_coordinator"
LEAD_ROLE = "event_coordinator_lead"
NO_SUPPORT_AVAILABLE = "Technical Support is required but no staff member is currently available"
# The events service's status-guarded submit write matched nothing -- the
# request stopped being a draft or returned one underneath this call. Same
# wording as the events service, which cannot be imported across services.
NO_LONGER_AWAITING_CHANGES = "This request is no longer awaiting changes. Reload to see its current status."


@app.exception_handler(RequestValidationError)
async def readable_validation_error(request: Request, exc: RequestValidationError):
    errors: dict[str, str] = {}
    for error in exc.errors():
        path = [str(part) for part in error["loc"] if part != "body"]
        errors.setdefault(".".join(path) or "body", error["msg"])

    return JSONResponse(
        status_code=422,
        content={"detail": "Please check the details you entered", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    logger.exception("Unhandled event_requests service error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@app.get("/health")
@app.get("/event-requests/health", include_in_schema=False)
def health():
    return {"status": "ok"}


async def _authenticate_organiser(request: Request, users: httpx.AsyncClient) -> dict:
    try:
        response = await users.get("/users/me", cookies=request.cookies)
    except httpx.HTTPError as exc:
        logger.exception("Users service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Users service unavailable") from exc

    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Users service unavailable")

    user = response.json()
    if user.get("role") != ORGANISER_ROLE:
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


async def _authenticate_coordinator(request: Request, users: httpx.AsyncClient) -> dict:
    try:
        response = await users.get("/users/me", cookies=request.cookies)
    except httpx.HTTPError as exc:
        logger.exception("Users service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Users service unavailable") from exc
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Users service unavailable")
    user = response.json()
    if user.get("role") != COORDINATOR_ROLE:
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


async def _authenticate_lead(request: Request, users: httpx.AsyncClient) -> dict:
    try:
        response = await users.get("/users/me", cookies=request.cookies)
    except httpx.HTTPError as exc:
        logger.exception("Users service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Users service unavailable") from exc
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Users service unavailable")
    user = response.json()
    if user.get("role") != LEAD_ROLE:
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


async def _coordinator_pool(users: httpx.AsyncClient) -> list[dict]:
    try:
        response = await users.get("/internal/users/coordinators")
    except httpx.HTTPError as exc:
        logger.exception("Users service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Users service unavailable") from exc
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Users service unavailable")
    return response.json()


async def _assigned_event(
    event_id: UUID,
    request: Request,
    events: httpx.AsyncClient,
) -> dict:
    try:
        response = await events.get(
            f"/events/assigned/{event_id}", cookies=request.cookies
        )
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Event not found or not assigned to you")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    return response.json()


async def _technical_support_pool(users: httpx.AsyncClient) -> list[dict]:
    try:
        response = await users.get("/users/technical-support")
    except httpx.HTTPError as exc:
        logger.exception("Users service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Users service unavailable") from exc
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Users service unavailable")
    return response.json()


def _select_technical_support(candidates: list[dict], loads: list[dict]) -> dict | None:
    """Least live workload, then ascending user id; kept replaceable by design."""
    by_id = {row["staff_id"]: row for row in loads}
    available = [
        candidate
        for candidate in candidates
        if candidate["id"] in by_id and not by_id[candidate["id"]]["conflict"]
    ]
    if not available:
        return None
    return min(
        available,
        key=lambda candidate: (
            by_id[candidate["id"]]["assigned_count"],
            candidate["id"],
        ),
    )


def _support_response(event: dict, candidates: list[dict]) -> dict:
    staff_id = event.get("assigned_technical_support_id")
    staff = next((row for row in candidates if row["id"] == staff_id), None)
    if staff_id is not None and staff is None:
        staff = {"id": staff_id, "name": None, "email": None}
    required = bool(event.get("technical_support_required"))
    if staff_id is not None:
        assignment_state = "assigned"
        message = "Technical Support Staff assigned"
    elif required:
        assignment_state = "unassigned"
        message = NO_SUPPORT_AVAILABLE
    else:
        assignment_state = "not_required"
        message = "Technical Support has not been requested"
    return {
        "technical_support_required": required,
        "support_details": event.get("technical_support_details"),
        "assigned_technical_support_id": staff_id,
        "technical_support_assigned_at": event.get("technical_support_assigned_at"),
        "assignment_state": assignment_state,
        "assigned_staff": staff,
        "message": message,
    }


async def _forward_patch(
    events: httpx.AsyncClient,
    event_id: UUID,
    changes: dict,
    cookies,
):
    """Passes an edit straight through to the public PATCH /events/{id},
    forwarding the organiser's own session -- used whenever no assignment
    recheck is needed, so this composite adds a hop but no new behaviour.
    """
    try:
        response = await events.patch(f"/events/{event_id}", json=changes, cookies=cookies)
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code in (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND, 422):
        return JSONResponse(status_code=response.status_code, content=response.json())
    raise HTTPException(status_code=502, detail="Events service unavailable")


@app.post("/event-requests", status_code=status.HTTP_201_CREATED)
async def submit_new_request(
    payload: EventRequestSubmit,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    user = await _authenticate_organiser(request, users)

    body = payload.model_dump(mode="json")
    body["organiser_id"] = user["id"]
    body["assigned_coordinator_id"] = None
    try:
        response = await events.post("/events/internal", json=body)
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code != status.HTTP_201_CREATED:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    return response.json()


@app.post("/event-requests/{event_id}/submit")
async def submit_existing_draft(
    event_id: UUID,
    payload: EventRequestSubmit,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    """Submit a draft unassigned, or resubmit a returned request without
    changing its existing assignment. S-83 makes assignment a Lead action.
    """
    user = await _authenticate_organiser(request, users)
    try:
        current_response = await events.get(f"/events/{event_id}", cookies=request.cookies)
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if current_response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Event not found")
    if current_response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    current = current_response.json()

    coordinator_id = (
        current.get("assigned_coordinator_id")
        if current.get("status") == "returned"
        else None
    )

    body = payload.model_dump(mode="json")
    body["organiser_id"] = user["id"]
    body["assigned_coordinator_id"] = coordinator_id
    try:
        response = await events.post(f"/events/{event_id}/submit/internal", json=body)
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Event not found")
    if response.status_code == status.HTTP_409_CONFLICT:
        raise HTTPException(status_code=409, detail=NO_LONGER_AWAITING_CHANGES)
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    return response.json()


@app.patch("/event-requests/{event_id}")
async def update_event_request(
    event_id: UUID,
    payload: EventRequestUpdate,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    """Edit an organiser-owned request without automatic reassignment.

    S-83 makes assignment a Lead decision. Date/time edits therefore never
    invoke the superseded conflict-based auto-assignment path.
    """
    await _authenticate_organiser(request, users)
    changes = payload.model_dump(exclude_unset=True, mode="json")
    return await _forward_patch(events, event_id, changes, request.cookies)


@app.get("/event-requests/unassigned")
async def list_unassigned_requests(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    await _authenticate_lead(request, users)
    try:
        response = await events.get("/internal/events/unassigned")
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")

    rows = response.json()
    organiser_ids = list(dict.fromkeys(row["organiser_id"] for row in rows))
    profiles: dict[str, dict] = {}
    if organiser_ids:
        try:
            profile_response = await users.post("/internal/users/profiles", json={"ids": organiser_ids})
        except httpx.HTTPError as exc:
            logger.exception("Users service unavailable", exc_info=exc)
            raise HTTPException(status_code=502, detail="Users service unavailable") from exc
        if profile_response.status_code != status.HTTP_200_OK:
            raise HTTPException(status_code=502, detail="Users service unavailable")
        profiles = {profile["id"]: profile for profile in profile_response.json()}

    return [
        {
            **row,
            "organiser": profiles.get(
                row["organiser_id"],
                {"id": row["organiser_id"], "name": "Unknown organiser", "email": None},
            ),
        }
        for row in rows
    ]


@app.get("/event-requests/coordinators")
async def list_assignment_coordinators(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
):
    await _authenticate_lead(request, users)
    return await _coordinator_pool(users)


@app.post("/event-requests/{event_id}/assignment")
async def assign_event_request(
    event_id: UUID,
    payload: CoordinatorAssignmentCreate,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
):
    await _authenticate_lead(request, users)
    coordinators = await _coordinator_pool(users)
    coordinator_id = str(payload.coordinator_id)
    coordinator = next((item for item in coordinators if item["id"] == coordinator_id), None)
    if coordinator is None:
        raise HTTPException(
            status_code=422,
            detail="Selected user is not an Event Coordinator",
        )

    try:
        event_response = await events.post(
            f"/internal/events/{event_id}/assignment",
            json={"coordinator_id": coordinator_id},
        )
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if event_response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT):
        raise HTTPException(
            status_code=event_response.status_code,
            detail=event_response.json().get("detail"),
        )
    if event_response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")

    event = event_response.json()
    event_name = event["name"]
    organiser_id = event["organiser_id"]
    key_prefix = f"event_assignment:{event_id}"
    batch = {
        "notifications": [
            {
                "recipient_id": coordinator_id,
                "event_id": str(event_id),
                "event_name": event_name,
                "kind": "event_assignment",
                "message": f"You have been assigned to {event_name}.",
                "deduplication_key": f"{key_prefix}:{coordinator_id}",
            },
            {
                "recipient_id": organiser_id,
                "event_id": str(event_id),
                "event_name": event_name,
                "kind": "event_assignment",
                "message": f"{coordinator['name']} has been assigned to {event_name}.",
                "deduplication_key": f"{key_prefix}:{organiser_id}",
            },
        ]
    }
    try:
        notification_response = await notifications.post(
            "/internal/notifications", json=batch
        )
    except httpx.HTTPError as exc:
        logger.exception("Notifications service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Notifications service unavailable") from exc
    if notification_response.status_code != status.HTTP_201_CREATED:
        raise HTTPException(status_code=502, detail="Notifications service unavailable")
    return event


@app.get("/event-requests/{event_id}/technical-support-assignment")
async def get_technical_support_assignment(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    await _authenticate_coordinator(request, users)
    event = await _assigned_event(event_id, request, events)
    candidates = (
        await _technical_support_pool(users)
        if event.get("assigned_technical_support_id") is not None
        else []
    )
    return _support_response(event, candidates)


@app.post("/event-requests/{event_id}/technical-support-assignment")
async def request_technical_support_assignment(
    event_id: UUID,
    payload: TechnicalSupportRequest,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    user = await _authenticate_coordinator(request, users)
    event = await _assigned_event(event_id, request, events)
    if event.get("status") != "planning":
        raise HTTPException(
            status_code=409,
            detail="Technical Support can only be requested while the event is in planning",
        )

    existing_staff_id = event.get("assigned_technical_support_id")
    candidates: list[dict]
    selected: dict | None = None
    if existing_staff_id is not None:
        candidates = await _technical_support_pool(users)
        selected = next(
            (row for row in candidates if row["id"] == existing_staff_id), None
        )
        if event.get("technical_support_details") == payload.support_details:
            return _support_response(event, candidates)
    else:
        candidates = await _technical_support_pool(users)
        if candidates:
            body = {
                "staff_ids": [candidate["id"] for candidate in candidates],
                "start_date": event["start_date"],
                "start_time": event["start_time"],
                "end_date": event["end_date"],
                "end_time": event["end_time"],
            }
            try:
                load_response = await events.post(
                    "/events/technical-support-load", json=body
                )
            except httpx.HTTPError as exc:
                logger.exception("Events service unavailable", exc_info=exc)
                raise HTTPException(
                    status_code=502, detail="Events service unavailable"
                ) from exc
            if load_response.status_code != status.HTTP_200_OK:
                raise HTTPException(status_code=502, detail="Events service unavailable")
            selected = _select_technical_support(
                candidates, load_response.json()
            )

    write_body = {
        "coordinator_id": user["id"],
        "technical_support_details": payload.support_details,
        "assigned_technical_support_id": (
            existing_staff_id
            if existing_staff_id is not None
            else selected["id"] if selected is not None else None
        ),
    }
    try:
        response = await events.put(
            f"/events/{event_id}/technical-support/internal", json=write_body
        )
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code == status.HTTP_409_CONFLICT:
        raise HTTPException(status_code=409, detail=response.json().get("detail"))
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    return _support_response(response.json(), candidates)
