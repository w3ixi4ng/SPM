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

from clients import assignment_service_headers, get_bookings_client, get_equipment_client, get_events_client, get_notifications_client, get_users_client
from schemas import (
    CancellationDecision,
    CoordinatorAssignmentCreate,
    CoordinatorReassignmentCreate,
    ReassignmentRequestSubmit,
    EventRequestSubmit,
    EventRequestUpdate,
    EventChangeSubmit,
    EventChangeValues,
    TechnicalSupportRequest,
)

app = FastAPI(title="Event Requests Service")
logger = logging.getLogger(__name__)

ORGANISER_ROLE = "event_organiser"
COORDINATOR_ROLE = "event_coordinator"
LEAD_ROLE = "event_coordinator_lead"
CHANGE_REQUEST_STATUSES = frozenset({
    "submitted", "under_review", "returned", "planning",
    "pending_safety_check", "confirmed", "preparation",
})
ASSIGNMENT_SUMMARY_FIELDS = (
    "id", "name", "status", "start_date", "start_time", "end_date", "end_time",
    "assigned_coordinator_id", "assigning_lead_id", "coordinator_assignment_version",
)
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


def _is_active_coordinator(coordinator: dict) -> bool:
    return coordinator.get("coordinator_active", True) is True


def _assignment_headers() -> dict[str, str]:
    try:
        return assignment_service_headers()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def _profiles_by_id(users: httpx.AsyncClient, ids: list[str]) -> dict[str, dict]:
    unique_ids = list(dict.fromkeys(ids))
    if not unique_ids:
        return {}
    try:
        response = await users.post("/internal/users/profiles", json={"ids": unique_ids})
    except httpx.HTTPError as exc:
        logger.exception("Users service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Users service unavailable") from exc
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Users service unavailable")
    return {profile["id"]: profile for profile in response.json()}


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
    # 409: the event is closed (rejected, or cancelled since S-61) -- the
    # events service says which, and the Organiser should read that, not a
    # claim that the service is down.
    if response.status_code in (
        status.HTTP_200_OK, status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT, 422,
    ):
        return JSONResponse(status_code=response.status_code, content=response.json())
    raise HTTPException(status_code=502, detail="Events service unavailable")


# S-59 keeps proposed configuration separate from accepted Events and
# Equipment records. These reads cross service boundaries only through HTTP.
async def _change_viewer(request: Request, users: httpx.AsyncClient) -> dict:
    try:
        response = await users.get("/users/me", cookies=request.cookies)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Users service unavailable") from exc
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Users service unavailable")
    user = response.json()
    if user.get("role") not in {ORGANISER_ROLE, COORDINATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


async def _change_event(event_id: UUID, role: str, cookies, events: httpx.AsyncClient) -> dict:
    path = f"/events/{event_id}" if role == ORGANISER_ROLE else f"/events/assigned/{event_id}"
    try:
        response = await events.get(path, cookies=cookies)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code in {401, 403, 404}:
        raise HTTPException(status_code=response.status_code, detail="Event not found" if response.status_code == 404 else "Permission denied")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    return response.json()


async def _change_equipment(event_id: UUID, equipment: httpx.AsyncClient) -> list[dict]:
    try:
        response = await equipment.get("/internal/equipment-requirements", params={"event_id": str(event_id)})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Equipment service unavailable") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Equipment service unavailable")
    return response.json()


def _equipment_snapshot(rows: list[dict]) -> list[dict]:
    return sorted(
        [{"equipment_item_id": row["equipment_item_id"], "required_quantity": row["required_quantity"]} for row in rows],
        key=lambda item: item["equipment_item_id"],
    )


@app.get("/event-requests/{event_id}/change-requests")
async def get_event_change_requests(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
):
    user = await _change_viewer(request, users)
    event = await _change_event(event_id, user["role"], request.cookies, events)
    try:
        requests_response = await events.get(f"/events/{event_id}/change-requests", cookies=request.cookies)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if requests_response.status_code != 200:
        if requests_response.status_code in {401, 403, 404}:
            raise HTTPException(status_code=requests_response.status_code, detail="Event not found")
        raise HTTPException(status_code=502, detail="Events service unavailable")
    current_equipment = await _change_equipment(event_id, equipment)
    options = []
    if user["role"] == ORGANISER_ROLE:
        try:
            options_response = await equipment.get("/equipment/selection", cookies=request.cookies)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Equipment service unavailable") from exc
        if options_response.status_code != 200:
            raise HTTPException(status_code=502, detail="Equipment service unavailable")
        options = options_response.json()
    return {
        "event": event,
        "requests": requests_response.json(),
        "equipment": current_equipment,
        "equipment_options": options,
    }


@app.post("/event-requests/{event_id}/change-requests", status_code=201)
async def submit_event_change_request(
    event_id: UUID,
    payload: EventChangeSubmit,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
):
    await _authenticate_organiser(request, users)
    event = await _change_event(event_id, ORGANISER_ROLE, request.cookies, events)
    if event["status"] not in CHANGE_REQUEST_STATUSES:
        raise HTTPException(status_code=409, detail="This event cannot receive a change request")
    accepted = EventChangeValues.model_validate({
        field: event.get(field) for field in EventChangeValues.model_fields
    }).model_dump(mode="json")
    proposed = payload.values.model_dump(mode="json")
    current_equipment = await _change_equipment(event_id, equipment)
    accepted_equipment = _equipment_snapshot(current_equipment)
    proposed_equipment = sorted(
        [item.model_dump(mode="json") for item in payload.equipment],
        key=lambda item: item["equipment_item_id"],
    )
    if accepted == proposed and accepted_equipment == proposed_equipment:
        raise HTTPException(status_code=422, detail="Change request has no changed values")

    # A retired accepted requirement may stay untouched in the snapshot. New
    # or changed requirements must be selectable from the live catalogue.
    if accepted_equipment != proposed_equipment:
        try:
            options_response = await equipment.get("/equipment/selection", cookies=request.cookies)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Equipment service unavailable") from exc
        if options_response.status_code != 200:
            raise HTTPException(status_code=502, detail="Equipment service unavailable")
        available = {item["id"] for item in options_response.json()}
        prior = {item["equipment_item_id"]: item["required_quantity"] for item in accepted_equipment}
        for item in proposed_equipment:
            if prior.get(item["equipment_item_id"]) != item["required_quantity"] and item["equipment_item_id"] not in available:
                raise HTTPException(status_code=422, detail="Choose active, available equipment items")

    # Catch equipment edits observed during form validation. A later
    # cross-service race remains for S-60 to revalidate at review time.
    latest_equipment = _equipment_snapshot(await _change_equipment(event_id, equipment))
    if latest_equipment != accepted_equipment:
        raise HTTPException(status_code=409, detail="Equipment requirements changed; reload before requesting changes")

    body = {
        "expected_event_updated_at": event["updated_at"],
        "proposed_values": proposed,
        "accepted_equipment": accepted_equipment,
        "proposed_equipment": proposed_equipment,
    }
    try:
        response = await events.post(
            f"/events/{event_id}/change-request/internal",
            json=body, cookies=request.cookies, headers=_assignment_headers(),
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Events service unavailable. Nothing was changed.") from exc
    if response.status_code in {201, 401, 403, 404, 409, 422}:
        return JSONResponse(status_code=response.status_code, content=response.json())
    raise HTTPException(status_code=502, detail="Events service unavailable. Nothing was changed.")


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


# S-61: what the events service may answer on a decision and is passed on as
# it is. Anything else, or no answer, means nothing was changed.
_DECISION_PASSTHROUGH = (200, 401, 403, 404, 409, 422)
_EVENTS_DOWN = "The events service is unavailable. Nothing was changed."
_BOOKINGS_NOT_RELEASED = (
    "The event is cancelled, but its venue bookings were not released. "
    "Approve again to release them."
)


@app.post("/event-requests/{event_id}/cancellation-decision")
async def decide_cancellation(
    event_id: UUID,
    payload: CancellationDecision,
    request: Request,
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-61: the assigned Coordinator approves or declines a cancellation
    request. The events service checks the session, the assignment and the
    request, and records the decision. On approval the event's venue
    bookings are then removed so their times are free. Equipment needs no
    call: only planning and confirmed events reserve it.

    The event changes first. If the bookings can't be removed, approving
    again is a no-op on the event and retries the removal."""
    try:
        decided = await events.post(
            f"/events/{event_id}/cancellation-decision",
            json=payload.model_dump(exclude_none=True),
            cookies=request.cookies,
        )
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail=_EVENTS_DOWN) from exc
    if decided.status_code not in _DECISION_PASSTHROUGH:
        raise HTTPException(status_code=502, detail=_EVENTS_DOWN)
    if decided.status_code != status.HTTP_200_OK:
        return JSONResponse(status_code=decided.status_code, content=decided.json())

    event = decided.json()
    if event.get("cancellation_decision") != "approved":
        return event

    try:
        released = await bookings.delete(
            f"/internal/events/{event_id}/bookings", cookies=request.cookies
        )
    except httpx.HTTPError as exc:
        logger.exception("Bookings service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail=_BOOKINGS_NOT_RELEASED) from exc
    if released.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail=_BOOKINGS_NOT_RELEASED)
    return {**event, "released_bookings": released.json()["deleted"]}


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
    profiles = await _profiles_by_id(users, organiser_ids)

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
    return [item for item in await _coordinator_pool(users) if _is_active_coordinator(item)]


@app.get("/event-requests/coordinators/{coordinator_id}/active-events")
async def coordinator_active_events(
    coordinator_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    """S-93 inventory for a selected Coordinator; cross-Lead rows are summaries."""
    lead = await _authenticate_lead(request, users)
    coordinator = next(
        (item for item in await _coordinator_pool(users) if item["id"] == str(coordinator_id)),
        None,
    )
    if coordinator is None:
        raise HTTPException(status_code=404, detail="Coordinator not found")
    try:
        response = await events.get(
            f"/internal/events/coordinators/{coordinator_id}/active-summary",
            cookies=request.cookies,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    rows = []
    for row in response.json():
        responsible = row.get("assigning_lead_id")
        scope = "mine" if responsible == lead["id"] else ("other_lead" if responsible else "legacy")
        rows.append({
            **{field: row.get(field) for field in ASSIGNMENT_SUMMARY_FIELDS},
            "scope": scope,
            "actionable": scope == "mine",
            "inactive_owner": not _is_active_coordinator(coordinator),
        })
    return {
        "coordinator": coordinator,
        "active_assignment_count": len(rows),
        "events": rows,
    }


@app.get("/event-requests/assigned-active")
async def list_active_assignments(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    await _authenticate_lead(request, users)
    try:
        response = await events.get("/internal/events/lead-assigned-active", cookies=request.cookies)
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")

    rows = response.json()
    profile_ids = [
        profile_id
        for row in rows
        for profile_id in (row["organiser_id"], row["assigned_coordinator_id"])
    ]
    profiles = await _profiles_by_id(users, profile_ids)
    return [
        {
            **row,
            "organiser": profiles.get(
                row["organiser_id"],
                {"id": row["organiser_id"], "name": "Unknown organiser", "email": None},
            ),
            "coordinator": profiles.get(
                row["assigned_coordinator_id"],
                {
                    "id": row["assigned_coordinator_id"],
                    "name": "Unknown coordinator",
                    "email": None,
                },
            ),
        }
        for row in rows
    ]


@app.get("/event-requests/coordinator-overview")
async def coordinator_overview(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    """Group active assigned events under every trusted Coordinator.

    S-85 owns no persistence. Events supplies lifecycle-filtered rows and
    Users supplies the trusted Coordinator pool plus organiser profiles.
    Keeping empty groups is deliberate: a Lead needs to see idle
    Coordinators as well as current work.
    """
    await _authenticate_lead(request, users)
    coordinators = await _coordinator_pool(users)

    try:
        response = await events.get("/internal/events/coordinator-overview", cookies=request.cookies)
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")

    rows = response.json()
    profiles = await _profiles_by_id(users, [row["organiser_id"] for row in rows])

    groups = {
        item["id"]: {
            "coordinator": item,
            "active_assignment_count": 0,
            "events": [],
        }
        for item in coordinators
    }
    invalid_assignments = []

    for row in rows:
        owner_id = row["assigned_coordinator_id"]
        if owner_id not in groups:
            invalid_assignments.append(
                {
                    "event_id": row["id"],
                    "name": row["name"],
                    "status": row["status"],
                    "assigned_coordinator_id": owner_id,
                    "reason": "identity_missing",
                }
            )
            continue

        owner = groups[owner_id]["coordinator"]
        organiser = profiles.get(
            row["organiser_id"],
            {"id": row["organiser_id"], "name": "Unknown organiser", "email": None},
        )
        groups[owner_id]["events"].append(
            {**row, "organiser": organiser, "coordinator": owner}
        )

    for group in groups.values():
        group["active_assignment_count"] = len(group["events"])

    ordered = sorted(
        groups.values(),
        key=lambda group: (
            (group["coordinator"].get("name") or "").casefold(),
            group["coordinator"]["id"],
        ),
    )
    return {"coordinators": ordered, "invalid_assignments": invalid_assignments}


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
    if coordinator is None or not _is_active_coordinator(coordinator):
        raise HTTPException(
            status_code=422,
            detail="Selected Event Coordinator is not active or eligible",
        )

    try:
        event_response = await events.post(
            f"/internal/events/{event_id}/assignment",
            json={"coordinator_id": coordinator_id}, cookies=request.cookies,
            headers=_assignment_headers(),
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


@app.get("/event-requests/reassignment-requests/mine")
async def my_reassignment_requests(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    await _authenticate_coordinator(request, users)
    try:
        response = await events.get("/events/reassignment-requests/mine", cookies=request.cookies)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    return response.json()


@app.get("/event-requests/reassignment-requests/lead")
async def lead_reassignment_requests(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    await _authenticate_lead(request, users)
    try:
        response = await events.get("/internal/reassignment-requests/lead", cookies=request.cookies)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    rows = response.json()
    profiles = await _profiles_by_id(users, [row["requester_id"] for row in rows])
    return [{**row, "requester": profiles.get(row["requester_id"], {
        "id": row["requester_id"], "name": "Unknown coordinator", "email": None,
    })} for row in rows]


@app.post("/event-requests/{event_id}/reassignment-request", status_code=201)
async def request_event_reassignment(
    event_id: UUID,
    payload: ReassignmentRequestSubmit,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    await _authenticate_coordinator(request, users)
    event = await _assigned_event(event_id, request, events)
    if not event.get("assigning_lead_id"):
        raise HTTPException(status_code=409, detail="This event has no recorded responsible Lead")
    try:
        response = await events.post(
            f"/events/{event_id}/reassignment-request",
            json={"reason": payload.reason}, cookies=request.cookies,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code in (404, 409, 422):
        raise HTTPException(status_code=response.status_code, detail=response.json().get("detail"))
    if response.status_code != 201:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    return response.json()


@app.post("/event-requests/{event_id}/reassignment")
async def reassign_event_request(
    event_id: UUID,
    payload: CoordinatorReassignmentCreate,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
):
    lead = await _authenticate_lead(request, users)
    target_id = str(payload.coordinator_id)
    expected_id = str(payload.expected_coordinator_id)
    if target_id == expected_id:
        raise HTTPException(
            status_code=422,
            detail="Choose a different valid Event Coordinator",
        )

    coordinators = await _coordinator_pool(users)
    by_id = {item["id"]: item for item in coordinators}
    target = by_id.get(target_id)
    if target is None or not _is_active_coordinator(target):
        raise HTTPException(
            status_code=422,
            detail="Selected Event Coordinator is not active or eligible",
        )

    try:
        scope_response = await events.get(
            f"/internal/events/{event_id}/assignment-scope", cookies=request.cookies,
        )
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if scope_response.status_code in (404, 409):
        raise HTTPException(status_code=scope_response.status_code, detail=scope_response.json().get("detail"))
    if scope_response.status_code != 200:
        # The 502 hides whether events refused the session (401/403) or failed
        # (5xx); the log keeps the real answer.
        logger.error(
            "Events assignment-scope answered %s: %s",
            scope_response.status_code, scope_response.text,
        )
        raise HTTPException(status_code=502, detail="Events service unavailable")
    scope = scope_response.json()
    if not scope.get("assigning_lead_id"):
        raise HTTPException(status_code=409, detail="This event has no recorded responsible Lead")
    if scope["assigning_lead_id"] != lead["id"]:
        raise HTTPException(status_code=404, detail="Event not found in your scope")

    try:
        event_response = await events.post(
            f"/internal/events/{event_id}/reassignment",
            json=payload.model_dump(mode="json"), cookies=request.cookies,
            headers=_assignment_headers(),
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
        logger.error(
            "Events reassignment answered %s: %s",
            event_response.status_code, event_response.text,
        )
        raise HTTPException(status_code=502, detail="Events service unavailable")

    event = event_response.json()
    event_name = event["name"]
    organiser_id = event["organiser_id"]
    previous_id = event["previous_coordinator_id"]
    version = event["coordinator_assignment_version"]
    previous = by_id.get(
        previous_id,
        {"id": previous_id, "name": "the previous Event Coordinator"},
    )
    key_prefix = f"event_reassignment:{event_id}:{version}"
    batch = {
        "notifications": [
            {
                "recipient_id": target_id,
                "event_id": str(event_id),
                "event_name": event_name,
                "kind": "event_reassignment",
                "message": f"You have been assigned to {event_name}.",
                "deduplication_key": f"{key_prefix}:{target_id}",
            },
            {
                "recipient_id": previous_id,
                "event_id": str(event_id),
                "event_name": event_name,
                "kind": "event_reassignment",
                "message": f"{event_name} has been reassigned to {target['name']}. You are no longer the assigned Event Coordinator.",
                "deduplication_key": f"{key_prefix}:{previous_id}",
            },
            {
                "recipient_id": organiser_id,
                "event_id": str(event_id),
                "event_name": event_name,
                "kind": "event_reassignment",
                "message": f"{event_name} has been reassigned from {previous['name']} to {target['name']}.",
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


# --- S-82: an event's change history -----------------------------------------

# Every user id an entry's details can name, so the page can show a name.
HISTORY_PEOPLE_KEYS = (
    "coordinator_id", "from_coordinator_id", "to_coordinator_id",
    "technical_support_id", "previous_technical_support_id",
)


async def _events_read(events: httpx.AsyncClient, path: str, **params) -> dict | list:
    try:
        response = await events.get(path, params=params or None)
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Event not found")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")
    return response.json()


def _people_in(entry: dict) -> list[str]:
    details = entry.get("details") or {}
    ids = [details.get(key) for key in HISTORY_PEOPLE_KEYS]
    # The Organiser's edit-recheck can move the event to another Coordinator.
    moved = (details.get("changes") or {}).get("assigned_coordinator_id") or {}
    ids += [moved.get("before"), moved.get("after")]
    return [user_id for user_id in ids if user_id]


async def _named_history(scope: dict, entries: list[dict], users: httpx.AsyncClient) -> dict:
    """The entries with each actor's name, and a name for everyone their
    details mention. A name no longer on file is null, never a guess."""
    people_ids = [user_id for entry in entries for user_id in _people_in(entry)]
    actor_ids = [entry["actor_id"] for entry in entries if entry.get("actor_id")]
    profiles = await _profiles_by_id(users, actor_ids + people_ids)

    def name(user_id):
        return (profiles.get(user_id) or {}).get("name")

    return {
        "event_id": scope["id"],
        "event_name": scope.get("name"),
        "entries": [
            {
                "id": entry["id"],
                "occurred_at": entry["occurred_at"],
                "category": entry["category"],
                "action": entry["action"],
                "details": entry.get("details") or {},
                "actor": None if not entry.get("actor_id") else {
                    "id": entry["actor_id"],
                    "name": name(entry["actor_id"]),
                    "role": entry.get("actor_role"),
                },
            }
            for entry in entries
        ],
        "people": {user_id: name(user_id) for user_id in dict.fromkeys(people_ids)},
    }


@app.get("/event-requests/{event_id}/history")
async def event_history(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    """S-82: the assigned Coordinator's or any Lead's view of who changed or
    decided what, and when. A Coordinator no longer assigned is told the
    event does not exist, as on every other assigned-event route."""
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
    if user.get("role") not in (COORDINATOR_ROLE, LEAD_ROLE):
        raise HTTPException(status_code=403, detail="Permission denied")

    scope = await _events_read(events, f"/internal/events/{event_id}/history-scope")
    if user["role"] == COORDINATOR_ROLE and scope.get("assigned_coordinator_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Event not found")
    entries = await _events_read(events, f"/internal/events/{event_id}/history")
    return await _named_history(scope, entries, users)
