"""S-40 orchestration for event equipment requirements.

The equipment atomic service owns the relationship. This composite owns the
cross-service decision: who the currently assigned Coordinator is and whether
the event is still in planning.
"""

import logging
from datetime import date, datetime, time, timezone
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import availability
from clients import get_equipment_client, get_events_client, get_users_client
from schemas import RequirementQuantity, SignoffDecision, SignoffRequest

app = FastAPI(title="Equipment Requirements Service")
logger = logging.getLogger(__name__)

COORDINATOR_ROLE = "event_coordinator"
TECHNICAL_SUPPORT_ROLE = "technical_support"
NOT_IN_PLANNING = "Equipment requirements can only be edited while the event is in planning"
INTERNAL_PATH = "/internal/equipment-requirements"


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
    logger.exception("Unhandled equipment_requirements error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
@app.get("/equipment-requirements/health", include_in_schema=False)
def health():
    return {"status": "ok"}


def _unavailable(service: str) -> HTTPException:
    return HTTPException(status_code=502, detail=f"{service} service unavailable")


async def _call(service: str, send):
    try:
        return await send
    except httpx.HTTPError as exc:
        logger.exception("%s service unavailable", service, exc_info=exc)
        raise _unavailable(service) from exc


async def _current_user(request: Request, users: httpx.AsyncClient) -> dict:
    response = await _call("Users", users.get("/users/me", cookies=request.cookies))
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != 200:
        raise _unavailable("Users")
    user = response.json()
    if user.get("role") not in {COORDINATOR_ROLE, TECHNICAL_SUPPORT_ROLE}:
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


async def _assigned_event(
    event_id: UUID,
    request: Request,
    events: httpx.AsyncClient,
) -> dict:
    response = await _call(
        "Events",
        events.get(f"/events/assigned/{event_id}", cookies=request.cookies),
    )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Event not found or not assigned to you")
    if response.status_code != 200:
        raise _unavailable("Events")
    return response.json()


async def _support_assigned_event(
    event_id: UUID,
    request: Request,
    events: httpx.AsyncClient,
) -> dict:
    response = await _call(
        "Events",
        events.get(
            f"/events/support-assigned/{event_id}", cookies=request.cookies
        ),
    )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Event not found or not assigned to you")
    if response.status_code != 200:
        raise _unavailable("Events")
    return response.json()


async def _support_assigned_events(
    request: Request,
    events: httpx.AsyncClient,
) -> list[dict]:
    response = await _call(
        "Events",
        events.get("/events/support-assigned", cookies=request.cookies),
    )
    if response.status_code != 200:
        raise _unavailable("Events")
    return response.json()


def _require_planning(event: dict) -> None:
    if event.get("status") != "planning":
        raise HTTPException(status_code=409, detail=NOT_IN_PLANNING)


async def _clear_signoff(event_id: UUID, events: httpx.AsyncClient) -> None:
    """S-17: any change to the requirements voids Technical Support's
    sign-off. Cleared before the change, so a requirement is never changed
    under an approval that no longer applies."""
    response = await _call(
        "Events", events.post(f"/internal/events/{event_id}/technical-signoff/clear"),
    )
    if response.status_code != 200:
        raise _unavailable("Events")


async def _equipment_response(service_call):
    response = await _call("Equipment", service_call)
    if response.status_code in {404, 409, 422}:
        detail = response.json().get("detail", "Equipment request was rejected")
        raise HTTPException(status_code=response.status_code, detail=detail)
    if response.status_code not in {200, 204}:
        raise _unavailable("Equipment")
    if response.status_code == 204:
        return Response(status_code=204)
    return response.json()


async def _requirement(event_id: UUID, equipment_item_id: UUID, equipment: httpx.AsyncClient) -> dict | None:
    rows = await _json_list("Equipment", equipment.get(INTERNAL_PATH, params={"event_id": str(event_id)}))
    return next((row for row in rows if str(row["equipment_item_id"]) == str(equipment_item_id)), None)


async def _record(
    event_id: UUID, equipment_item_id: UUID, user: dict, action: str,
    before: dict | None, to_quantity: int | None,
    events: httpx.AsyncClient, equipment: httpx.AsyncClient,
) -> None:
    """S-82: add a requirement change to its event's change history.

    Called only after the equipment service accepted the change. Best effort,
    by the developer's decision: the requirement has already changed, so a
    failed entry is logged rather than reported as a failed change."""
    try:
        named = before or await _requirement(event_id, equipment_item_id, equipment)
        entry = {
            "actor_id": user["id"],
            "actor_role": user["role"],
            "action": action,
            "details": {
                "equipment_item_id": str(equipment_item_id),
                "item_name": ((named or {}).get("equipment") or {}).get("type"),
                "from_quantity": before["required_quantity"] if before else None,
                "to_quantity": to_quantity,
            },
        }
        response = await events.post(f"/internal/events/{event_id}/history", json=entry)
        if response.status_code != status.HTTP_201_CREATED:
            raise RuntimeError(f"Events answered {response.status_code}")
    except Exception as exc:
        logger.error("Could not record %s in the history of event %s", action, event_id, exc_info=exc)


@app.put("/equipment-requirements/{event_id}/{equipment_item_id}")
async def save_requirement(
    event_id: UUID,
    equipment_item_id: UUID,
    payload: RequirementQuantity,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
):
    user = await _current_user(request, users)
    if user["role"] != COORDINATOR_ROLE:
        raise HTTPException(status_code=403, detail="Permission denied")
    event = await _assigned_event(event_id, request, events)
    _require_planning(event)
    if not payload.impact_accepted:
        raise HTTPException(
            status_code=409,
            detail="Review and accept the equipment impact before saving",
        )
    before = await _requirement(event_id, equipment_item_id, equipment)
    await _clear_signoff(event_id, events)
    saved = await _equipment_response(
        equipment.put(
            f"{INTERNAL_PATH}/{event_id}/{equipment_item_id}/audited",
            json={
                "required_quantity": payload.required_quantity,
                "recorded_by_coordinator_id": user["id"],
            },
        ),
    )
    if not before or before["required_quantity"] != payload.required_quantity:
        await _record(
            event_id, equipment_item_id, user, "equipment_requirement_set",
            before, payload.required_quantity, events, equipment,
        )
    return saved


@app.delete(
    "/equipment-requirements/{event_id}/{equipment_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_requirement(
    event_id: UUID,
    equipment_item_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
    impact_accepted: bool = Query(default=False),
):
    user = await _current_user(request, users)
    if user["role"] != COORDINATOR_ROLE:
        raise HTTPException(status_code=403, detail="Permission denied")
    event = await _assigned_event(event_id, request, events)
    _require_planning(event)
    if not impact_accepted:
        raise HTTPException(
            status_code=409,
            detail="Review and accept the equipment impact before removing it",
        )
    before = await _requirement(event_id, equipment_item_id, equipment)
    await _clear_signoff(event_id, events)
    removed = await _equipment_response(
        equipment.post(
            f"{INTERNAL_PATH}/{event_id}/{equipment_item_id}/remove-audited",
            json={"recorded_by_coordinator_id": user["id"]},
        ),
    )
    await _record(
        event_id, equipment_item_id, user, "equipment_requirement_removed",
        before, None, events, equipment,
    )
    return removed


def _window_error() -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Please check the details you entered",
            "errors": {"end_time": "The end must be after the start"},
        },
    )


async def _json_list(service: str, service_call) -> list[dict]:
    response = await _call(service, service_call)
    if response.status_code != 200:
        raise _unavailable(service)
    return response.json()


SIGNOFF_ONLY_IN_PLANNING = (
    "Technical Support sign-off can only change while the event is in planning"
)
SHORT = "Some equipment is short for this event"


async def _event_shortages(
    event: dict,
    request: Request,
    events: httpx.AsyncClient,
    equipment: httpx.AsyncClient,
) -> list[dict]:
    window = {
        "start_date": str(event["start_date"]),
        "start_time": str(event["start_time"])[:5],
        "end_date": str(event["end_date"]),
        "end_time": str(event["end_time"])[:5],
    }
    overlapping = await _json_list("Events", events.post("/events/overlapping", json=window))
    if not any(row["id"] == event["id"] for row in overlapping):
        overlapping = [*overlapping, event]
    catalogue = await _json_list("Equipment", equipment.get("/equipment", cookies=request.cookies))
    params = [("event_ids", row["id"]) for row in overlapping]
    requirements = await _json_list("Equipment", equipment.get(INTERNAL_PATH, params=params))
    return availability.shortages(event, catalogue, overlapping, requirements)


@app.post("/equipment-requirements/{event_id}/sign-off")
async def sign_off(
    event_id: UUID,
    payload: SignoffRequest,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
):
    """S-17: the assigned Technical Support approves or declines the event's
    equipment arrangements. A shortage blocks approval unless Technical
    Support explains how it will be covered."""
    user = await _current_user(request, users)
    if user["role"] != TECHNICAL_SUPPORT_ROLE:
        raise HTTPException(status_code=403, detail="Permission denied")
    event = await _support_assigned_event(event_id, request, events)
    if event.get("status") != "planning":
        raise HTTPException(status_code=409, detail=SIGNOFF_ONLY_IN_PLANNING)
    if payload.decision is SignoffDecision.APPROVED and payload.override_comment is None:
        short = await _event_shortages(event, request, events, equipment)
        if short:
            return JSONResponse(status_code=409, content={"detail": SHORT, "short": short})

    body = {"technical_support_id": user["id"], **payload.model_dump(mode="json", exclude_none=True)}
    response = await _call(
        "Events", events.put(f"/internal/events/{event_id}/technical-signoff", json=body),
    )
    if response.status_code in {404, 409, 422}:
        detail = (response.json() or {}).get("detail", "Sign-off was rejected")
        raise HTTPException(status_code=response.status_code, detail=detail)
    if response.status_code != 200:
        raise _unavailable("Events")
    return response.json()


# Registered before any /equipment-requirements/{...} GET could read
# "availability" as an id.
@app.get("/equipment-requirements/availability")
async def check_availability(
    request: Request,
    start_date: date,
    start_time: time,
    end_date: date,
    end_time: time,
    type: str | None = Query(default=None, max_length=200),
    quantity: int | None = Query(default=None, ge=1),
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
):
    """S-44: how much of each active equipment pool is free for a window.
    Every call reads live data -- nothing is cached -- and says when it was
    checked. A failing dependency is a 502, never an empty or full result."""
    user = await _current_user(request, users)
    if user["role"] != TECHNICAL_SUPPORT_ROLE:
        raise HTTPException(status_code=403, detail="Permission denied")
    if datetime.combine(end_date, end_time) <= datetime.combine(start_date, start_time):
        return _window_error()

    window = {
        "start_date": start_date.isoformat(),
        "start_time": start_time.isoformat(timespec="minutes"),
        "end_date": end_date.isoformat(),
        "end_time": end_time.isoformat(timespec="minutes"),
    }
    overlapping = await _json_list("Events", events.post("/events/overlapping", json=window))
    catalogue = await _json_list("Equipment", equipment.get("/equipment", cookies=request.cookies))
    requirements = []
    if overlapping:
        params = [("event_ids", event["id"]) for event in overlapping]
        requirements = await _json_list("Equipment", equipment.get(INTERNAL_PATH, params=params))

    type_search = type.strip() if type else None
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        **window,
        "type": type_search or None,
        "quantity": quantity,
        "items": availability.items(
            catalogue, overlapping, requirements, type_search=type_search, quantity=quantity,
        ),
    }


@app.get("/equipment-requirements")
async def list_requirements(
    request: Request,
    event_id: UUID | None = Query(default=None),
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
):
    user = await _current_user(request, users)
    if user["role"] == COORDINATOR_ROLE:
        if event_id is None:
            raise HTTPException(status_code=422, detail="event_id is required for a Coordinator")
        await _assigned_event(event_id, request, events)
        params = {"event_id": str(event_id)}
    elif event_id is not None:
        await _support_assigned_event(event_id, request, events)
        params = {"event_id": str(event_id)}
    else:
        assigned = await _support_assigned_events(request, events)
        if not assigned:
            return []
        params = [("event_ids", row["id"]) for row in assigned]

    return await _equipment_response(
        equipment.get(INTERNAL_PATH, params=params),
    )
