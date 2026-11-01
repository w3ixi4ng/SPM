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

from clients import assignment_service_headers, get_bookings_client, get_equipment_client, get_events_client, get_notifications_client, get_registrations_client, get_users_client, get_venue_bookings_client
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
    TechnicalSupportRequest,
    VenueCancellationSubmit,
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
    return event


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
    failure: str = _ATTENDEES_NOT_NOTIFIED,
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
        raise HTTPException(status_code=502, detail=failure) from exc
    if places.status_code != status.HTTP_200_OK or waiting.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail=failure)

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
            raise HTTPException(status_code=502, detail=failure) from exc
        if sent.status_code != status.HTTP_201_CREATED:
            raise HTTPException(status_code=502, detail=failure)
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


# S-89: the assigned Coordinator cancels an event venue unavailability
# affects once no alternative venue could be found.
_NOT_AFFECTED = (
    "None of this event's venue bookings is affected by an unavailable venue, "
    "so it can't be cancelled here."
)
_ALREADY_CANCELLED = "This event is already cancelled."
_NOT_CANCELLED = "The event could not be cancelled. Nothing was changed. Try again."
_STILL_LOCKED = (
    "The event was not cancelled, but its venue bookings could not be unlocked. Try again."
)
_OUTCOME_UNKNOWN = (
    "We couldn't confirm whether the event was cancelled, so its venue bookings stay "
    "locked for now. Reload the event in a few minutes: if it shows as cancelled, "
    "cancel again to finish; if not, you can try again."
)
_HISTORY_NOT_RECORDED = (
    "The event is cancelled, but the cancellation was not recorded in its history. "
    "Cancel again to finish."
)
_VENUE_BOOKINGS_NOT_RELEASED = (
    "The event is cancelled, but its venue bookings were not released. Cancel again to finish."
)
_VENUE_ORGANISER_NOT_NOTIFIED = (
    "The event is cancelled and its venue bookings released, but the Organiser "
    "was not notified. Cancel again to finish."
)
_VENUE_ATTENDEES_NOT_NOTIFIED = (
    "The event is cancelled, but its attendees were not notified. Cancel again to notify them."
)
_VENUE_NOT_COMPLETED = (
    "Everyone was notified, but the cancellation could not be marked complete. "
    "Cancel again to finish."
)
_ACTIVE_BOOKING_STATUSES = frozenset({"pending", "held", "confirmed"})
_VENUE_BOOKINGS_DOWN = "Venue bookings service unavailable"


async def _affected_booking_ids(
    event_id: UUID, request: Request, venue_bookings: httpx.AsyncClient
) -> list[str]:
    """S-77's flag, as the venue_bookings composite that owns the rule
    reports it for this Coordinator's event. A failed read is a 502 -- never
    "affected" and never "not affected"."""
    try:
        response = await venue_bookings.get(
            "/venue-bookings", params={"event_id": str(event_id)}, cookies=request.cookies,
        )
    except httpx.HTTPError as exc:
        logger.exception("Venue bookings service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail=_VENUE_BOOKINGS_DOWN) from exc
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Event not found or not assigned to you")
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail=_VENUE_BOOKINGS_DOWN)
    return [
        str(row["id"]) for row in response.json()
        if row.get("requires_alternative_arrangements") is True
    ]


async def _bookings_post(bookings: httpx.AsyncClient, path: str, request: Request, body: dict):
    """One bookings write; None if the service could not be reached."""
    try:
        return await bookings.post(path, json=body, cookies=request.cookies)
    except httpx.HTTPError as exc:
        logger.exception("Bookings service unavailable", exc_info=exc)
        return None


async def _reopen(event_id: UUID, operation_id: str, request: Request, bookings) -> bool:
    """Withdraw this operation's closure intent (or an abandoned one).
    True once the bookings service has answered; it reopens nothing that a
    release has already closed."""
    response = await _bookings_post(
        bookings, f"/internal/events/{event_id}/bookings/closure/reopen", request,
        {"operation_id": operation_id},
    )
    return response is not None and response.status_code == status.HTTP_200_OK


async def _events_write(events: httpx.AsyncClient, path: str, request: Request, **kwargs):
    try:
        return await events.post(
            path, headers=assignment_service_headers(), cookies=request.cookies, **kwargs
        )
    except httpx.HTTPError as exc:
        logger.exception("Events service unavailable", exc_info=exc)
        return None


async def _event_bookings(event_id: UUID, bookings: httpx.AsyncClient) -> list[dict]:
    try:
        response = await bookings.get("/bookings", params={"event_id": str(event_id)})
    except httpx.HTTPError as exc:
        logger.exception("Bookings service unavailable", exc_info=exc)
        raise HTTPException(status_code=502, detail="Bookings service unavailable") from exc
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail="Bookings service unavailable")
    return response.json()


async def _cancel_event(
    event_id: UUID, payload: VenueCancellationSubmit, affected: list[str],
    operation_id: str, request: Request, events, bookings,
) -> dict | JSONResponse:
    """Close the event's bookings, then cancel the event. If the event is not
    cancelled, the closure intent is withdrawn again before answering, so a
    refused or failed cancellation never leaves the bookings locked."""
    closure = await _bookings_post(
        bookings, f"/internal/events/{event_id}/bookings/closure", request,
        {"reason": "event_cancelled", "operation_id": operation_id},
    )
    if closure is None or closure.status_code != status.HTTP_200_OK:
        # Unknown whether it was recorded; withdrawing ours is always safe.
        await _reopen(event_id, operation_id, request, bookings)
        raise HTTPException(status_code=502, detail=_NOT_CANCELLED)

    recorded = await _events_write(
        events, f"/internal/events/{event_id}/venue-cancellation", request,
        json={**payload.model_dump(), "affected_booking_ids": affected},
    )
    if recorded is None:
        # No answer: the write may still land. Keep the bookings closed
        # until the outcome is known -- a cancelled event with open bookings
        # is the one state this must never leave behind.
        try:
            current = await _assigned_event(event_id, request, events)
        except HTTPException as exc:
            raise HTTPException(status_code=502, detail=_OUTCOME_UNKNOWN) from exc
        if current.get("venue_cancelled_at"):
            return current
        raise HTTPException(status_code=502, detail=_OUTCOME_UNKNOWN)
    if recorded.status_code == status.HTTP_200_OK:
        return recorded.json()

    # Any other answer is definite: the events service did not cancel it.
    if not await _reopen(event_id, operation_id, request, bookings):
        raise HTTPException(status_code=502, detail=_STILL_LOCKED)
    if recorded.status_code in _DECISION_PASSTHROUGH:
        return JSONResponse(status_code=recorded.status_code, content=recorded.json())
    raise HTTPException(status_code=502, detail=_NOT_CANCELLED)


async def _release_event_bookings(
    event_id: UUID, operation_id: str, request: Request, bookings: httpx.AsyncClient
) -> int:
    """Release, then re-read: anything still active is released by a second
    call, and still active after that is a failure. Returns how many of the
    event's bookings are released in all, so a resumed cancellation reports
    the same number as an uninterrupted one."""
    for _attempt in range(2):
        response = await _bookings_post(
            bookings, f"/internal/events/{event_id}/bookings/release", request,
            {"reason": "event_cancelled", "operation_id": operation_id},
        )
        if response is None or response.status_code != status.HTTP_200_OK:
            raise HTTPException(status_code=502, detail=_VENUE_BOOKINGS_NOT_RELEASED)
        try:
            rows = await _event_bookings(event_id, bookings)
        except HTTPException as exc:
            raise HTTPException(status_code=502, detail=_VENUE_BOOKINGS_NOT_RELEASED) from exc
        if not any(row.get("status") in _ACTIVE_BOOKING_STATUSES for row in rows):
            return sum(1 for row in rows if row.get("status") == "released")
    raise HTTPException(status_code=502, detail=_VENUE_BOOKINGS_NOT_RELEASED)


def _venue_cancelled_organiser_message(event: dict) -> str:
    announced = _cancelled_message(event).removesuffix(" It will not take place.")
    return (
        f"{announced} Your Event Coordinator cancelled it because no alternative venue "
        f"could be found. Reason: {event['venue_cancellation_reason']}"
    )


@app.post("/event-requests/{event_id}/venue-cancellation")
async def cancel_for_venue_unavailability(
    event_id: UUID,
    payload: VenueCancellationSubmit,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venue_bookings: httpx.AsyncClient = Depends(get_venue_bookings_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
):
    """S-89: the assigned Coordinator cancels an event venue unavailability
    affects, after working through the alternatives with its Organiser.

    In order: S-77's flag (from venue_bookings) must be on one of the event's
    bookings; the bookings are closed to new active bookings; the event is
    cancelled (or the closure withdrawn again); the S-82 history entry is
    recorded; every booking is released; the Organiser and Attendees are told
    (S-63/S-69); the events service marks the operation complete. Any failure
    after the event changed is a 502 saying what is left; calling again
    resumes an existing S-89 cancellation without re-checking the flag (the
    released bookings no longer carry it) and repeats nothing already done.
    Equipment needs no call: requirements reserve stock only while the
    event's status is committed, so `cancelled` releases them."""
    await _authenticate_coordinator(request, users)
    event = await _assigned_event(event_id, request, events)
    operation_id = str(uuid4())

    if not event.get("venue_cancelled_at"):
        if event.get("status") == "cancelled":
            raise HTTPException(status_code=409, detail=_ALREADY_CANCELLED)
        affected = await _affected_booking_ids(event_id, request, venue_bookings)
        if not affected:
            # Withdraw any closure an abandoned attempt left behind.
            await _reopen(event_id, operation_id, request, bookings)
            raise HTTPException(status_code=409, detail=_NOT_AFFECTED)
        cancelled = await _cancel_event(
            event_id, payload, affected, operation_id, request, events, bookings,
        )
        if isinstance(cancelled, JSONResponse):
            return cancelled
        event = cancelled

    history = await _events_write(
        events, f"/internal/events/{event_id}/venue-cancellation/history", request,
    )
    if history is None or history.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail=_HISTORY_NOT_RECORDED)

    released = await _release_event_bookings(event_id, operation_id, request, bookings)
    try:
        await _notify_organiser(notifications, {
            "recipient_id": event["organiser_id"],
            "event_id": event["id"],
            "event_name": event["name"],
            "kind": "event_cancelled",
            "message": _venue_cancelled_organiser_message(event),
            "deduplication_key": f"event_cancelled:{event['id']}:{event['organiser_id']}",
        })
    except HTTPException as exc:
        raise HTTPException(status_code=502, detail=_VENUE_ORGANISER_NOT_NOTIFIED) from exc
    notified = await _notify_cancelled(
        event, registrations, notifications, _VENUE_ATTENDEES_NOT_NOTIFIED
    )

    completed = await _events_write(
        events, f"/internal/events/{event_id}/venue-cancellation/complete", request
    )
    if completed is None or completed.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=502, detail=_VENUE_NOT_COMPLETED)
    return {
        **completed.json(),
        "released_bookings": released,
        "organiser_notified": True,
        "notified_attendees": notified,
        "cancellation_completed": True,
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
