"""Composite service for submitting and assigning event requests.

Spans two entities -- events and users -- which is why this lives here and
not in either atomic service (see AGENTS.md: "Atomic services never call
other services. ... Anything spanning two entities is a composite service").
Owns no table of its own; every write ends up in ``events.events`` by way of
the events service's internal routes.
"""

import asyncio
import logging
from datetime import date, datetime, time
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from clients import assignment_service_headers, get_bookings_client, get_equipment_client, get_events_client, get_notifications_client, get_registrations_client, get_users_client, get_venues_client
import impact
from schemas import (
    CancellationDecision,
    CoordinatorAssignmentCreate,
    CoordinatorReassignmentCreate,
    ReassignmentRequestSubmit,
    EventRequestSubmit,
    EventRequestUpdate,
    EventChangeSubmit,
    EventChangeValues,
    EventDecision,
    EventInformationUpdate,
    EventChangeAccept,
    EventChangeReject,
    EventImpactResolve,
    CoordinatorSignificantEdit,
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
_NOTIFICATIONS_DOWN = "The event was saved, but the Organiser notification could not be delivered."


async def _notify_organiser(notifications: httpx.AsyncClient, row: dict) -> None:
    """Persist one outcome after its owning service accepted the action."""
    try:
        response = await notifications.post(
            "/internal/notifications", json={"notifications": [row]}
        )
    except httpx.HTTPError as exc:
        logger.exception("Notifications service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail=_NOTIFICATIONS_DOWN) from exc
    if response.status_code != status.HTTP_201_CREATED:
        raise HTTPException(status_code=502, detail=_NOTIFICATIONS_DOWN)


def _decision_message(event: dict) -> str:
    decision = event["decision"]
    name = event["name"]
    if decision == "approved":
        return f"Event request approved: {name}. Planning can now begin."
    reason = event.get("decision_reason") or "No reason was provided."
    if decision == "rejected":
        return f"Event request rejected: {name}. Reason: {reason}"
    guidance = (
        f" Guidance: {event['decision_comment']}" if event.get("decision_comment") else ""
    )
    return (
        f"Event request returned for amendment: {name}. Reason: {reason}.{guidance} "
        "Update the request and resubmit it."
    )


def _window(event: dict) -> tuple[datetime, datetime]:
    return (
        datetime.combine(
            date.fromisoformat(str(event["start_date"])),
            time.fromisoformat(str(event["start_time"])),
        ),
        datetime.combine(
            date.fromisoformat(str(event["end_date"])),
            time.fromisoformat(str(event["end_time"])),
        ),
    )


def _window_label(event: dict) -> str:
    start, end = _window(event)
    start_label = f"{start.day} {start:%b %Y} {start:%H:%M}"
    if start.date() == end.date():
        return f"{start_label}–{end:%H:%M}"
    return f"{start_label}–{end.day} {end:%b %Y} {end:%H:%M}"


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


async def _s60_json(service: str, awaitable, *, allowed: set[int] = frozenset()) -> object:
    try:
        response = await awaitable
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"{service} service unavailable") from exc
    if response.status_code in allowed:
        raise HTTPException(status_code=response.status_code, detail=response.json().get("detail", "Request changed"))
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"{service} service unavailable")
    return response.json()


async def _s60_request(event_id: UUID, request_id: UUID, cookies, events: httpx.AsyncClient) -> dict:
    rows = await _s60_json("Events", events.get(f"/events/{event_id}/change-requests", cookies=cookies), allowed={401, 403, 404})
    row = next((item for item in rows if item["id"] == str(request_id)), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    return row


async def _s60_assessment(
    event: dict, change: dict, cookies,
    events: httpx.AsyncClient, equipment: httpx.AsyncClient,
    bookings: httpx.AsyncClient, venues: httpx.AsyncClient,
) -> tuple[list[dict], list[dict]]:
    event_id = UUID(event["id"])
    requirement_rows = await _change_equipment(event_id, equipment)
    booking_rows = await _s60_json("Bookings", bookings.get("/bookings", params={"event_id": str(event_id)}))
    venue_rows: dict[str, dict] = {}
    nearby: dict[str, list[dict]] = {}
    proposed = change["proposed_values"]
    for booking in booking_rows:
        venue_id = str(booking["venue_id"])
        if venue_id in venue_rows:
            continue
        venue_rows[venue_id] = await _s60_json("Venues", venues.get(f"/internal/venues/{venue_id}"))
        nearby[venue_id] = await _s60_json("Bookings", bookings.get("/bookings", params={
            "venue_id": venue_id, "from": proposed["start_date"], "to": proposed["end_date"],
        }))
    catalogue = await _s60_json("Equipment", equipment.get("/equipment/selection", cookies=cookies), allowed={401, 403})
    window = {key: proposed[key] for key in ("start_date", "start_time", "end_date", "end_time")}
    overlapping = await _s60_json("Events", events.post("/events/overlapping", json=window))
    overlapping_requirements = []
    if overlapping:
        overlapping_requirements = await _s60_json("Equipment", equipment.get(
            "/internal/equipment-requirements",
            params=[("event_ids", row["id"]) for row in overlapping],
        ))
    technical_conflict = False
    if event.get("assigned_technical_support_id"):
        load = await _s60_json("Events", events.post("/events/technical-support-load", json={
            "staff_ids": [event["assigned_technical_support_id"]],
            "exclude_event_id": event["id"], **window,
        }))
        technical_conflict = any(row["conflict"] for row in load)
    return impact.assess(
        event, change, booking_rows, venue_rows, nearby, requirement_rows,
        catalogue, overlapping, overlapping_requirements, technical_conflict,
    ), requirement_rows


async def _s60_equipment_available(
    event: dict, item_id: str, quantity: int, cookies,
    events: httpx.AsyncClient, equipment: httpx.AsyncClient,
) -> bool:
    catalogue = await _s60_json("Equipment", equipment.get("/equipment/selection", cookies=cookies))
    item = next((row for row in catalogue if str(row["id"]) == item_id), None)
    if item is None:
        return False
    window = {key: event[key] for key in ("start_date", "start_time", "end_date", "end_time")}
    overlapping = await _s60_json("Events", events.post("/events/overlapping", json=window))
    other_ids = [row["id"] for row in overlapping if str(row["id"]) != str(event["id"])]
    other_requirements = []
    if other_ids:
        other_requirements = await _s60_json("Equipment", equipment.get(
            "/internal/equipment-requirements", params=[("event_ids", identity) for identity in other_ids],
        ))
    reserved = sum(int(row["required_quantity"]) for row in other_requirements
                   if str(row["equipment_item_id"]) == item_id)
    return quantity + reserved <= int(item["total_quantity"])


@app.get("/event-requests/{event_id}/change-requests/{request_id}/review")
async def review_event_change_request(
    event_id: UUID, request_id: UUID, request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
):
    await _authenticate_coordinator(request, users)
    event = await _change_event(event_id, COORDINATOR_ROLE, request.cookies, events)
    change = await _s60_request(event_id, request_id, request.cookies, events)
    if change["status"] == "pending":
        impacts, equipment_rows = await _s60_assessment(event, change, request.cookies, events, equipment, bookings, venues)
    else:
        impacts = change.get("impacts") or []
        equipment_rows = await _change_equipment(event_id, equipment)
    booking_rows = await _s60_json("Bookings", bookings.get("/bookings", params={"event_id": str(event_id)}))
    return {"event": event, "request": change, "impacts": impacts,
            "equipment": equipment_rows, "bookings": booking_rows}


async def _s60_write(service: str, response, success: set[int] = frozenset({200})) -> dict:
    try:
        received = await response
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"{service} operation incomplete; reload and retry") from exc
    if received.status_code in success:
        return received.json()
    if received.status_code in {401, 403, 404, 409, 422}:
        raise HTTPException(status_code=received.status_code, detail=received.json().get("detail", "Operation rejected"))
    raise HTTPException(status_code=502, detail=f"{service} operation incomplete; reload and retry")


@app.post("/event-requests/{event_id}/change-requests/{request_id}/accept")
async def accept_event_change_request(
    event_id: UUID, request_id: UUID, payload: EventChangeAccept, request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
):
    coordinator = await _authenticate_coordinator(request, users)
    event = await _change_event(event_id, COORDINATOR_ROLE, request.cookies, events)
    change = await _s60_request(event_id, request_id, request.cookies, events)
    if change["status"] not in {"pending", "applying", "accepted"}:
        raise HTTPException(status_code=409, detail="Change request is no longer pending")
    if change["status"] == "pending":
        impacts, requirements = await _s60_assessment(event, change, request.cookies, events, equipment, bookings, venues)
        if change["accepted_equipment"] != change["proposed_equipment"]:
            live_items = await _s60_json("Equipment", equipment.get(
                "/equipment/selection", cookies=request.cookies,
            ))
            active_ids = {str(item["id"]) for item in live_items}
            before = {str(item["equipment_item_id"]): item["required_quantity"]
                      for item in change["accepted_equipment"]}
            for item in change["proposed_equipment"]:
                identity = str(item["equipment_item_id"])
                if before.get(identity) != item["required_quantity"] and identity not in active_ids:
                    raise HTTPException(status_code=409, detail=f"Equipment item {identity} is no longer available")
        if set(payload.impact_ids) != {item["id"] for item in impacts} or len(payload.impact_ids) != len(impacts):
            raise HTTPException(status_code=409, detail="Impact assessment changed; review it again")
        if event["updated_at"] != payload.expected_event_updated_at.isoformat().replace("+00:00", "Z"):
            # ISO formatting differs across PostgREST versions; the Events
            # owner performs the authoritative timestamp comparison below.
            from datetime import datetime
            if datetime.fromisoformat(event["updated_at"].replace("Z", "+00:00")) != payload.expected_event_updated_at:
                raise HTTPException(status_code=409, detail="Event changed; reload the review")
        if _equipment_snapshot(requirements) != change["accepted_equipment"]:
            raise HTTPException(status_code=409, detail="Equipment requirements changed; reload the review")
        operation_id = payload.operation_id or uuid4()
        change = await _s60_write("Events", events.post(
            f"/events/assigned/{event_id}/change-requests/{request_id}/prepare",
            cookies=request.cookies, headers=_assignment_headers(), json={
                "operation_id": str(operation_id),
                "expected_event_updated_at": event["updated_at"], "impacts": impacts,
            },
        ))
    else:
        operation_id = UUID(change["operation_id"])
        if payload.operation_id and payload.operation_id != operation_id:
            raise HTTPException(status_code=409, detail="A different acceptance operation is in progress")
        if set(payload.impact_ids) != {item["id"] for item in change.get("impacts") or []}:
            raise HTTPException(status_code=409, detail="Impact assessment changed; reload it")
    equipment_changed = change["accepted_equipment"] != change["proposed_equipment"]
    if equipment_changed and change["status"] != "accepted":
        await _s60_write("Equipment", equipment.post(
            "/internal/equipment-requirements/change-batches",
            headers=_assignment_headers(), json={
                "operation_id": str(operation_id), "event_id": str(event_id),
                "actor_id": change.get("reviewed_by") or coordinator["id"], "baseline": change["accepted_equipment"],
                "proposed": change["proposed_equipment"],
            },
        ))
    if change["status"] != "accepted":
        change = await _s60_write("Events", events.post(
            f"/events/assigned/{event_id}/change-requests/{request_id}/complete",
            cookies=request.cookies, headers=_assignment_headers(),
            json={"operation_id": str(operation_id)},
        ))
    if equipment_changed:
        await _s60_write("Equipment", equipment.post(
            f"/internal/equipment-requirements/change-batches/{operation_id}/finish",
            headers=_assignment_headers(),
        ))
    return change


@app.post("/event-requests/{event_id}/change-requests/{request_id}/reject")
async def reject_event_change_request(
    event_id: UUID, request_id: UUID, payload: EventChangeReject, request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    await _authenticate_coordinator(request, users)
    await _change_event(event_id, COORDINATOR_ROLE, request.cookies, events)
    return await _s60_write("Events", events.post(
        f"/events/assigned/{event_id}/change-requests/{request_id}/reject",
        cookies=request.cookies, headers=_assignment_headers(), json=payload.model_dump(),
    ))


@app.post("/event-requests/{event_id}/change-requests/{request_id}/impacts/{impact_id}/resolve")
async def resolve_event_change_impact(
    event_id: UUID, request_id: UUID, impact_id: str, payload: EventImpactResolve, request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
):
    await _authenticate_coordinator(request, users)
    event = await _change_event(event_id, COORDINATOR_ROLE, request.cookies, events)
    change = await _s60_request(event_id, request_id, request.cookies, events)
    if change["status"] != "accepted":
        raise HTTPException(status_code=409, detail="Accept the change before resolving impacts")
    item = next((row for row in change.get("impacts") or [] if row["id"] == impact_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Impact not found")
    if item["status"] != "outstanding":
        raise HTTPException(status_code=409, detail="Impact is no longer outstanding")
    accepted_at = change["resolved_at"]
    kind = item["kind"]
    evidence = {}
    if kind == "venue_booking":
        booking_id = payload.evidence.get("booking_id")
        if not booking_id:
            raise HTTPException(status_code=422, detail="A confirmed booking is required as evidence")
        booking = await _s60_json("Bookings", bookings.get(f"/bookings/{booking_id}"), allowed={404})
        if booking.get("event_id") != str(event_id) or booking.get("status") != "confirmed":
            raise HTTPException(status_code=409, detail="Booking is not confirmed for this event")
        if not booking.get("decided_by") or not booking.get("decided_at") or datetime.fromisoformat(booking["decided_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(accepted_at.replace("Z", "+00:00")):
            raise HTTPException(status_code=409, detail="Venue Staff must confirm the changed arrangement")
        if (str(booking["booking_date"]) != str(event["start_date"])
            or str(booking["start_time"])[:5] != str(event["start_time"])[:5]
            or str(booking["end_time"])[:5] != str(event["end_time"])[:5]):
            raise HTTPException(status_code=409, detail="Booking does not cover the accepted event window")
        venue = await _s60_json("Venues", venues.get(f"/internal/venues/{booking['venue_id']}"))
        if int(event["expected_attendance"]) > int(venue["capacity"]):
            raise HTTPException(status_code=409, detail="Venue capacity is still insufficient")
        for field, venue_field in (("required_facilities", "facilities"), ("required_accessibility", "accessibility")):
            if set(event.get(field) or []) - set(venue.get(venue_field) or []):
                raise HTTPException(status_code=409, detail="Venue requirements are still unmet")
        if event.get("room_layout") and event["room_layout"] not in (venue.get("room_layouts") or []):
            raise HTTPException(status_code=409, detail="Venue layout is still unsuitable")
        nearby = await _s60_json("Bookings", bookings.get("/bookings", params={
            "venue_id": booking["venue_id"], "from": booking["booking_date"], "to": booking["booking_date"],
        }))
        if impact._booking_conflict(booking, venue, nearby, event):
            raise HTTPException(status_code=409, detail="Venue booking still clashes")
        evidence.update({
            "booking_id": str(booking_id), "venue_id": str(booking["venue_id"]),
            "venue_decided_by": booking.get("decided_by"), "venue_decided_at": booking["decided_at"],
        })
    elif kind in {"equipment", "technical_support"}:
        signed_at = event.get("technical_signoff_at")
        if (event.get("technical_signoff_decision") != "approved" or not signed_at
            or datetime.fromisoformat(signed_at.replace("Z", "+00:00")) <= datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
            or event.get("technical_signoff_by") != event.get("assigned_technical_support_id")):
            raise HTTPException(status_code=409, detail="Fresh Technical Support sign-off is required")
        if kind == "equipment":
            prepared_at = event.get("equipment_preparation_updated_at")
            if (event.get("equipment_preparation_status") != "ready" or not prepared_at
                or datetime.fromisoformat(prepared_at.replace("Z", "+00:00")) <= datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))):
                raise HTTPException(status_code=409, detail="Fresh Technical Support preparation is required")
            requirements = _equipment_snapshot(await _change_equipment(event_id, equipment))
            if requirements != change["proposed_equipment"]:
                raise HTTPException(status_code=409, detail="Equipment requirements changed again")
            quantity = next((row["required_quantity"] for row in requirements
                             if str(row["equipment_item_id"]) == item["arrangement_id"]), 0)
            if quantity and not await _s60_equipment_available(event, item["arrangement_id"], quantity, request.cookies, events, equipment):
                raise HTTPException(status_code=409, detail="Equipment is unavailable for the accepted window")
            evidence.update({
                "equipment_item_id": item["arrangement_id"], "required_quantity": quantity,
                "equipment_preparation_updated_by": event.get("equipment_preparation_updated_by"),
                "equipment_preparation_updated_at": event.get("equipment_preparation_updated_at"),
            })
        evidence.update({"technical_signoff_by": event.get("technical_signoff_by"),
                         "technical_signoff_at": signed_at})
    else:
        raise HTTPException(status_code=422, detail="This impact cannot be resolved here")
    return await _s60_write("Events", events.post(
        f"/events/assigned/{event_id}/change-requests/{request_id}/impacts/{impact_id}/resolve",
        cookies=request.cookies, headers=_assignment_headers(),
        json={**payload.model_dump(), "evidence": evidence},
    ))


async def _s60_edit_review(
    event_id: UUID, edit: dict, request: Request, events: httpx.AsyncClient,
    equipment: httpx.AsyncClient, bookings: httpx.AsyncClient, venues: httpx.AsyncClient,
) -> tuple[dict, dict, list[dict]]:
    event = await _change_event(event_id, COORDINATOR_ROLE, request.cookies, events)
    preview = await _s60_write("Events", events.post(
        f"/events/assigned/{event_id}/edit-impact", json=edit, cookies=request.cookies,
    ))
    impacts = []
    if preview["requires_impact_acceptance"]:
        original = EventChangeValues.model_validate({field: event.get(field) for field in EventChangeValues.model_fields}).model_dump(mode="json")
        proposed = EventChangeValues.model_validate({**original, **{
            field: value for field, value in edit.items() if field in EventChangeValues.model_fields
        }}).model_dump(mode="json")
        equipment_rows = await _change_equipment(event_id, equipment)
        snapshot = _equipment_snapshot(equipment_rows)
        synthetic = {"accepted_values": original, "proposed_values": proposed,
                     "accepted_equipment": snapshot, "proposed_equipment": snapshot}
        impacts, _ = await _s60_assessment(event, synthetic, request.cookies, events, equipment, bookings, venues)
        for item in impacts:
            item["id"] = f"edit:{event['edit_version'] + 1}:{item['id']}"
    return event, preview, impacts


@app.post("/event-requests/{event_id}/information/impact")
async def preview_coordinator_edit_impacts(
    event_id: UUID, edit: dict, request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
):
    await _authenticate_coordinator(request, users)
    _, preview, impacts = await _s60_edit_review(event_id, edit, request, events, equipment, bookings, venues)
    return {**preview, "impacts": impacts}


@app.patch("/event-requests/{event_id}/information/significant")
async def save_coordinator_significant_edit(
    event_id: UUID, payload: CoordinatorSignificantEdit, request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
):
    await _authenticate_coordinator(request, users)
    before, preview, impacts = await _s60_edit_review(event_id, payload.edit, request, events, equipment, bookings, venues)
    if not preview["requires_impact_acceptance"]:
        raise HTTPException(status_code=409, detail="This edit does not require significant impact acceptance")
    if len(payload.impact_ids) != len(impacts) or set(payload.impact_ids) != {item["id"] for item in impacts}:
        raise HTTPException(status_code=409, detail="Impact assessment changed; review it again")
    event = await _s60_write("Events", events.patch(
        f"/events/assigned/{event_id}", cookies=request.cookies, headers=_assignment_headers(),
        json={**payload.edit, "impact_accepted": True, "impact_items": impacts},
    ))
    await _notify_schedule_change(event_id, before, event, notifications)
    return event


@app.post("/event-requests/{event_id}/information/impacts/{impact_id}/resolve")
async def resolve_coordinator_edit_impact(
    event_id: UUID, impact_id: str, payload: EventImpactResolve, request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
):
    await _authenticate_coordinator(request, users)
    event = await _change_event(event_id, COORDINATOR_ROLE, request.cookies, events)
    item = next((row for row in event.get("s60_edit_impacts") or [] if row["id"] == impact_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Impact not found")
    if item["status"] != "outstanding":
        raise HTTPException(status_code=409, detail="Impact is no longer outstanding")
    evidence = {}
    if item["kind"] == "venue_booking":
        booking_id = payload.evidence.get("booking_id")
        if not booking_id:
            raise HTTPException(status_code=422, detail="A confirmed booking is required as evidence")
        booking = await _s60_json("Bookings", bookings.get(f"/bookings/{booking_id}"), allowed={404})
        if booking.get("event_id") != str(event_id) or booking.get("status") != "confirmed":
            raise HTTPException(status_code=409, detail="Booking is not confirmed for this event")
        if not booking.get("decided_by") or not booking.get("decided_at") or datetime.fromisoformat(booking["decided_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(item["flagged_at"].replace("Z", "+00:00")):
            raise HTTPException(status_code=409, detail="Venue Staff must confirm the changed arrangement")
        if (str(booking["booking_date"]) != str(event["start_date"])
            or str(booking["start_time"])[:5] != str(event["start_time"])[:5]
            or str(booking["end_time"])[:5] != str(event["end_time"])[:5]):
            raise HTTPException(status_code=409, detail="Booking does not cover the accepted event window")
        venue = await _s60_json("Venues", venues.get(f"/internal/venues/{booking['venue_id']}"))
        if (int(event["expected_attendance"]) > int(venue["capacity"])
            or set(event.get("required_facilities") or []) - set(venue.get("facilities") or [])
            or set(event.get("required_accessibility") or []) - set(venue.get("accessibility") or [])
            or (event.get("room_layout") and event["room_layout"] not in (venue.get("room_layouts") or []))):
            raise HTTPException(status_code=409, detail="Venue remains unsuitable")
        nearby = await _s60_json("Bookings", bookings.get("/bookings", params={
            "venue_id": booking["venue_id"], "from": booking["booking_date"], "to": booking["booking_date"],
        }))
        if impact._booking_conflict(booking, venue, nearby, event):
            raise HTTPException(status_code=409, detail="Venue booking still clashes")
        evidence.update({
            "booking_id": str(booking_id), "venue_id": str(booking["venue_id"]),
            "venue_decided_by": booking.get("decided_by"), "venue_decided_at": booking["decided_at"],
        })
    elif item["kind"] in {"equipment", "technical_support"}:
        if (event.get("technical_signoff_decision") != "approved"
            or not event.get("technical_signoff_at")
            or datetime.fromisoformat(event["technical_signoff_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(item["flagged_at"].replace("Z", "+00:00"))
            or event.get("technical_signoff_by") != event.get("assigned_technical_support_id")):
            raise HTTPException(status_code=409, detail="Fresh Technical Support sign-off is required")
        if item["kind"] == "equipment":
            prepared_at = event.get("equipment_preparation_updated_at")
            if (event.get("equipment_preparation_status") != "ready" or not prepared_at
                or datetime.fromisoformat(prepared_at.replace("Z", "+00:00")) <= datetime.fromisoformat(item["flagged_at"].replace("Z", "+00:00"))):
                raise HTTPException(status_code=409, detail="Fresh Technical Support preparation is required")
            current = await _change_equipment(event_id, equipment)
            quantity = next((row["required_quantity"] for row in current
                             if str(row["equipment_item_id"]) == item["arrangement_id"]), 0)
            if not quantity:
                raise HTTPException(status_code=409, detail="Equipment requirement no longer exists")
            if not await _s60_equipment_available(event, item["arrangement_id"], quantity, request.cookies, events, equipment):
                raise HTTPException(status_code=409, detail="Equipment is unavailable for the accepted window")
            evidence.update({
                "equipment_item_id": item["arrangement_id"], "required_quantity": quantity,
                "equipment_preparation_updated_by": event.get("equipment_preparation_updated_by"),
                "equipment_preparation_updated_at": event.get("equipment_preparation_updated_at"),
            })
        evidence.update({"technical_signoff_by": event.get("technical_signoff_by"),
                         "technical_signoff_at": event.get("technical_signoff_at")})
    else:
        raise HTTPException(status_code=422, detail="This impact cannot be resolved here")
    return await _s60_write("Events", events.post(
        f"/events/assigned/{event_id}/edit-impacts/{impact_id}/resolve",
        cookies=request.cookies, headers=_assignment_headers(),
        json={**payload.model_dump(), "evidence": evidence},
    ))


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


@app.post("/event-requests/{event_id}/decision")
async def decide_event_request(
    event_id: UUID,
    payload: EventDecision,
    request: Request,
    events: httpx.AsyncClient = Depends(get_events_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
):
    """S-63: save the S-14 decision, then tell the event's Organiser."""
    try:
        response = await events.post(
            f"/events/{event_id}/decision",
            json=payload.model_dump(mode="json", exclude_none=True),
            cookies=request.cookies,
        )
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code in {401, 403, 404, 409, 422}:
        return JSONResponse(status_code=response.status_code, content=response.json())
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")

    event = response.json()
    organiser_id = event["organiser_id"]
    await _notify_organiser(notifications, {
        "recipient_id": organiser_id,
        "event_id": str(event_id),
        "event_name": event["name"],
        "kind": "event_request_decision",
        "message": _decision_message(event),
        "deduplication_key": (
            f"event_request_decision:{event_id}:{event['decision']}:"
            f"{event.get('decided_at') or 'saved'}:{organiser_id}"
        ),
    })
    return event


@app.patch("/event-requests/{event_id}/information")
async def update_event_information(
    event_id: UUID,
    payload: EventInformationUpdate,
    request: Request,
    events: httpx.AsyncClient = Depends(get_events_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
):
    """S-63: keep S-18's atomic update and notify only schedule changes."""
    before = await _assigned_event(event_id, request, events)
    try:
        response = await events.patch(
            f"/events/assigned/{event_id}",
            json=payload.model_dump(mode="json", exclude_unset=True),
            cookies=request.cookies,
        )
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Events service unavailable") from exc
    if response.status_code in {401, 403, 404, 409, 422}:
        return JSONResponse(status_code=response.status_code, content=response.json())
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Events service unavailable")

    event = response.json()
    await _notify_schedule_change(event_id, before, event, notifications)
    return event


async def _notify_schedule_change(
    event_id: UUID, before: dict, event: dict, notifications: httpx.AsyncClient,
) -> None:
    schedule_fields = ("start_date", "start_time", "end_date", "end_time")
    if any(str(before.get(field)) != str(event.get(field)) for field in schedule_fields):
        postponed = _window(event)[0] > _window(before)[0]
        change = "postponed" if postponed else "rescheduled"
        organiser_id = event["organiser_id"]
        await _notify_organiser(notifications, {
            "recipient_id": organiser_id,
            "event_id": str(event_id),
            "event_name": event["name"],
            "kind": "event_schedule_changed",
            "message": (
                f"Event {change}: {event['name']} moved from {_window_label(before)} "
                f"to {_window_label(event)}. Review the updated event details and contact "
                "your Event Coordinator if anything needs attention."
            ),
            "deduplication_key": (
                f"event_schedule_changed:{event_id}:{event.get('edit_version', 'saved')}:"
                f"{organiser_id}"
            ),
        })


# S-61: what the events service may answer on a decision and is passed on as
# it is. Anything else, or no answer, means nothing was changed.
_DECISION_PASSTHROUGH = (200, 401, 403, 404, 409, 422)
_EVENTS_DOWN = "The events service is unavailable. Nothing was changed."
_BOOKINGS_NOT_RELEASED = (
    "The event is cancelled, but its venue bookings were not released. "
    "Approve again to release them."
)


# S-69: approving a cancellation tells everyone holding a place or waiting.
_ATTENDEES_NOT_NOTIFIED = (
    "The event is cancelled, but its attendees were not notified. "
    "Approve again to notify them."
)
# The notifications service accepts at most this many rows per request.
_NOTIFICATION_BATCH = 20


def _day(moment: date) -> str:
    return f"{moment.day} {moment:%b %Y}"


def _clock(moment: time) -> str:
    hour = moment.hour % 12 or 12
    meridiem = "am" if moment.hour < 12 else "pm"
    return f"{hour}:{moment:%M} {meridiem}"


def _cancelled_message(event: dict) -> str:
    """The event and when it was to happen, in the S-49 confirmation's
    wording. No reason: approval records none, and the Organiser's request
    reason was written for the Coordinator."""
    if not (event.get("start_date") and event.get("start_time")
            and event.get("end_date") and event.get("end_time")):
        return f"Event cancelled: {event['name']}. It will not take place."
    start_date = date.fromisoformat(event["start_date"])
    end_date = date.fromisoformat(event["end_date"])
    starts = f"{_day(start_date)}, {_clock(time.fromisoformat(event['start_time']))}"
    ends = _clock(time.fromisoformat(event["end_time"]))
    if end_date != start_date:
        ends = f"{_day(end_date)}, {ends}"
    return f"Event cancelled: {event['name']}, {starts} – {ends}. It will not take place."


async def _notify_cancelled(
    event: dict,
    registrations: httpx.AsyncClient,
    notifications: httpx.AsyncClient,
) -> int:
    """One notification per Attendee holding a place or on the waiting list
    (an offered place included). Deduplicated per Attendee, so approving
    again to retry never notifies anyone twice. Returns how many."""
    event_id = event["id"]
    try:
        places, waiting = await asyncio.gather(
            registrations.get(f"/registrations/events/{event_id}"),
            registrations.get(f"/registrations/waiting-list/events/{event_id}"),
        )
    except httpx.HTTPError as exc:
        logger.exception("Registrations service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail=_ATTENDEES_NOT_NOTIFIED) from exc
    if places.status_code != status.HTTP_200_OK or waiting.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail=_ATTENDEES_NOT_NOTIFIED)

    attendee_ids = list(dict.fromkeys(
        row["attendee_id"] for row in [*places.json(), *waiting.json()]
    ))
    message = _cancelled_message(event)
    rows = [
        {
            "recipient_id": attendee_id,
            "event_id": event_id,
            "event_name": event["name"],
            "kind": "event_cancelled",
            "message": message,
            "deduplication_key": f"event_cancelled:{event_id}:{attendee_id}",
        }
        for attendee_id in attendee_ids
    ]
    for start in range(0, len(rows), _NOTIFICATION_BATCH):
        batch = {"notifications": rows[start:start + _NOTIFICATION_BATCH]}
        try:
            sent = await notifications.post("/internal/notifications", json=batch)
        except httpx.HTTPError as exc:
            logger.exception("Notifications service unavailable", exc_info=exc)
            raise HTTPException(status_code=502, detail=_ATTENDEES_NOT_NOTIFIED) from exc
        if sent.status_code != status.HTTP_201_CREATED:
            raise HTTPException(status_code=502, detail=_ATTENDEES_NOT_NOTIFIED)
    return len(rows)


async def _notify_cancelled_organiser(event: dict, notifications: httpx.AsyncClient) -> None:
    organiser_id = event["organiser_id"]
    await _notify_organiser(notifications, {
        "recipient_id": organiser_id,
        "event_id": event["id"],
        "event_name": event["name"],
        "kind": "event_cancelled",
        "message": _cancelled_message(event),
        "deduplication_key": f"event_cancelled:{event['id']}:{organiser_id}",
    })


@app.post("/event-requests/{event_id}/cancellation-decision")
async def decide_cancellation(
    event_id: UUID,
    payload: CancellationDecision,
    request: Request,
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
):
    """S-61: the assigned Coordinator approves or declines a cancellation
    request. The events service checks the session, the assignment and the
    request, and records the decision. On approval the event's venue
    bookings are then removed so their times are free. Equipment needs no
    call: only planning and confirmed events reserve it.

    The event changes first. If the bookings can't be removed, approving
    again is a no-op on the event and retries the removal. S-69: then every
    Attendee holding a place or waiting is notified, retried the same way."""
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
    await _notify_cancelled_organiser(event, notifications)
    notified = await _notify_cancelled(event, registrations, notifications)
    return {
        **event,
        "released_bookings": released.json()["deleted"],
        "notified_attendees": notified,
        "organiser_notified": True,
    }


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
