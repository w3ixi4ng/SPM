import logging
from datetime import date, datetime, time, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from supabase import Client

from authorization import require_permission
from database import get_db
from schemas import (
    CoordinatorLoad,
    CoordinatorLoadRequest,
    DecisionCreate,
    DecisionValue,
    ACCESSIBILITY_FEATURES,
    FACILITIES,
    ROOM_LAYOUTS,
    EventDraftCreate,
    EventDraftUpdate,
    EventOptions,
    EventRead,
    EventSubmittedCreate,
    InternalEventCreate,
    InternalEventSubmit,
    InternalTechnicalSupportAssignment,
    InternalEventUpdate,
    OverlappingEvent,
    OverlappingEventsRequest,
    TechnicalSupportLoad,
    TechnicalSupportLoadRequest,
)
from security import clear_session_cookies

app = FastAPI(title="Events Service")
logger = logging.getLogger(__name__)

SCHEMA = "events"
TABLE = "events"


@app.exception_handler(StarletteHTTPException)
async def clear_dead_session(request: Request, exc: StarletteHTTPException):
    response = await http_exception_handler(request, exc)
    if getattr(request.state, "clear_session", False):
        clear_session_cookies(response)
    return response


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
    logger.exception("Unhandled events service error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


def _execute(operation):
    try:
        return operation.execute()
    except Exception as exc:
        logger.exception("Event storage operation failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event storage unavailable",
        ) from exc


def _submitted_now() -> str:
    """The submission timestamp, as the record of when it happened.

    Set by the service, never taken from the payload -- the same rule as
    organiser_id and status. A client that could choose its own submission
    time could backdate one.
    """
    return datetime.now(timezone.utc).isoformat()


def _insert_event(payload, event_status: str, organiser_id: str, db: Client):
    values = payload.model_dump(mode="json")
    values.update({"organiser_id": organiser_id, "status": event_status})
    # Null on a draft, so the column means "submitted at this time" and never
    # "last touched". The table's check constraint enforces the same pairing.
    values["submitted_at"] = (
        _submitted_now() if event_status == "submitted" else None
    )
    result = _execute(db.schema(SCHEMA).table(TABLE).insert(values))
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create event",
        )
    return result.data[0]


def _get_owned_event(event_id: UUID, organiser_id: str, db: Client):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("id", str(event_id))
        .eq("organiser_id", organiser_id)
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")
    return result.data[0]


def _get_assigned_event(event_id: UUID, coordinator_id: str, db: Client):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("id", str(event_id))
        .eq("assigned_coordinator_id", coordinator_id)
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")
    return result.data[0]


def _get_support_assigned_event(event_id: UUID, staff_id: str, db: Client):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("id", str(event_id))
        .eq("assigned_technical_support_id", staff_id)
        .in_("status", ["planning", "confirmed"])
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")
    return result.data[0]


def _decided_now() -> str:
    """The decision timestamp -- same reasoning as _submitted_now: set by
    the service so a client cannot backdate its own decision.
    """
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
@app.get("/events/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.post(
    "/events/drafts",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_draft(
    payload: EventDraftCreate,
    user=Depends(require_permission("events:save_draft")),
    db: Client = Depends(get_db),
):
    return _insert_event(payload, "draft", str(user.id), db)


@app.post(
    "/events",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_submitted_event(
    payload: EventSubmittedCreate,
    user=Depends(require_permission("events:create")),
    db: Client = Depends(get_db),
):
    return _insert_event(payload, "submitted", str(user.id), db)


@app.get("/events", response_model=list[EventRead])
def list_events(
    user=Depends(require_permission("events:view_own")),
    db: Client = Depends(get_db),
):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("organiser_id", str(user.id))
        .order("updated_at", desc=True)
    )
    return _execute(operation).data


# S-36: the venue requirement option sets for the organiser's form --
# organisers cannot view venues, so they cannot use GET /venues/options.
# Registered before /events/{event_id}, which would otherwise read "options"
# as an event id.
@app.get("/events/options", response_model=EventOptions)
def event_options(user=Depends(require_permission("events:create"))):
    return EventOptions(
        room_layouts=list(ROOM_LAYOUTS),
        facilities=list(FACILITIES),
        accessibility=list(ACCESSIBILITY_FEATURES),
    )


# Registered before /events/{event_id}: "assigned" would otherwise match that
# route's {event_id} path parameter and fail as an invalid UUID instead of
# reaching this one. Route order is match order.
@app.get("/events/assigned", response_model=list[EventRead])
def list_assigned_events(
    user=Depends(require_permission("events:view_assigned")),
    db: Client = Depends(get_db),
):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("assigned_coordinator_id", str(user.id))
        .order("updated_at", desc=True)
    )
    return _execute(operation).data


@app.get("/events/assigned/{event_id}", response_model=EventRead)
def get_assigned_event(
    event_id: UUID,
    user=Depends(require_permission("events:view_assigned")),
    db: Client = Depends(get_db),
):
    return _get_assigned_event(event_id, str(user.id), db)


# Registered before /events/{event_id}, as for the Coordinator assignment
# routes above. Technical Support sees only active work currently assigned to
# its verified user id; historical cancelled/completed assignments stay hidden.
@app.get("/events/support-assigned", response_model=list[EventRead])
def list_support_assigned_events(
    user=Depends(require_permission("events:view_support_assigned")),
    db: Client = Depends(get_db),
):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("assigned_technical_support_id", str(user.id))
        .in_("status", ["planning", "confirmed"])
        .order("updated_at", desc=True)
    )
    return _execute(operation).data


@app.get("/events/support-assigned/{event_id}", response_model=EventRead)
def get_support_assigned_event(
    event_id: UUID,
    user=Depends(require_permission("events:view_support_assigned")),
    db: Client = Depends(get_db),
):
    return _get_support_assigned_event(event_id, str(user.id), db)


@app.get("/events/booking-status/{event_id}")
def get_booking_status(
    event_id: UUID,
    user=Depends(require_permission("events:view_booking_status")),
    db: Client = Depends(get_db),
):
    """Minimal event state for Venue Staff hold synchronisation. No event
    details are exposed across the role boundary."""
    result = _execute(
        db.schema(SCHEMA).table(TABLE).select("id,status").eq("id", str(event_id))
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")
    return result.data[0]


@app.get("/events/{event_id}", response_model=EventRead)
def get_event(
    event_id: UUID,
    user=Depends(require_permission("events:view_own")),
    db: Client = Depends(get_db),
):
    return _get_owned_event(event_id, str(user.id), db)


@app.patch("/events/{event_id}", response_model=EventRead)
def update_event(
    event_id: UUID,
    payload: EventDraftUpdate,
    user=Depends(require_permission("events:update_own_draft")),
    db: Client = Depends(get_db),
):
    organiser_id = str(user.id)
    existing = _get_owned_event(event_id, organiser_id, db)

    # S-14: a rejection is permanent -- the story is explicit that a
    # rejected request is closed and cannot be resubmitted, and that starts
    # with it no longer being editable.
    if existing["status"] == "rejected":
        raise HTTPException(status_code=409, detail="This request has been rejected and is closed")

    changes = payload.model_dump(exclude_unset=True, mode="json")
    if not changes:
        return existing

    # A PATCH may supply only one time while the other already exists on the
    # record. Validate the resulting record, not only the partial request, so
    # a cross-field conflict is still a 422 instead of reaching the SQL CHECK.
    #
    # Everything past a draft -- submitted, planning, returned -- still has
    # to satisfy every submitted-required rule after the edit; the draft
    # schema would happily accept a PATCH that nulls out a required field,
    # which the database's own constraint would then reject as an opaque
    # storage failure instead of a readable 422.
    validator = EventDraftCreate if existing["status"] == "draft" else EventSubmittedCreate
    candidate = {
        field: existing.get(field) for field in EventDraftCreate.model_fields
    }
    candidate.update(changes)
    try:
        validator.model_validate(candidate)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .update(changes)
        .eq("id", str(event_id))
        .eq("organiser_id", organiser_id)
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")
    return result.data[0]


# A draft is submitted for the first time, or a returned request is
# resubmitted after the organiser amends it -- both land here, since both
# are "this record has no pending submission yet and now does."
_SUBMITTABLE_STATUSES = ("draft", "returned")

# The status-guarded submit write matched nothing: the record left draft or
# returned between the read and the write -- resubmitted from another tab,
# say. S-13: says what happened and what to do, since for a returned request
# "editable draft" was simply wrong.
_NO_LONGER_AWAITING_CHANGES = "This request is no longer awaiting changes. Reload to see its current status."


@app.post("/events/{event_id}/submit", response_model=EventRead)
def submit_draft(
    event_id: UUID,
    payload: EventSubmittedCreate,
    user=Depends(require_permission("events:submit_own")),
    db: Client = Depends(get_db),
):
    organiser_id = str(user.id)
    existing = _get_owned_event(event_id, organiser_id, db)
    if existing["status"] not in _SUBMITTABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Event has already been submitted")

    changes = payload.model_dump(mode="json")
    changes["status"] = "submitted"
    changes["submitted_at"] = _submitted_now()
    # A resubmission is a clean slate for the decision that sent it back --
    # the previous reason/comment described a version of the request that no
    # longer exists once the organiser has amended it.
    changes["decision"] = None
    changes["decision_reason"] = None
    changes["decision_comment"] = None
    changes["decided_at"] = None
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .update(changes)
        .eq("id", str(event_id))
        .eq("organiser_id", organiser_id)
        .in_("status", _SUBMITTABLE_STATUSES)
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=409, detail=_NO_LONGER_AWAITING_CHANGES)
    return result.data[0]


# S-36: the decision and the status it leads to are separate things. An
# approval is recorded as decision=approved and moves the event on to
# planning; reject and return are both a decision and a status of the same
# name.
_STATUS_AFTER_DECISION = {
    DecisionValue.APPROVED: "planning",
    DecisionValue.REJECTED: "rejected",
    DecisionValue.RETURNED: "returned",
}


@app.post("/events/{event_id}/decision", response_model=EventRead)
def decide_event(
    event_id: UUID,
    payload: DecisionCreate,
    user=Depends(require_permission("events:decide")),
    db: Client = Depends(get_db),
):
    """The assigned coordinator's approve/reject/return decision on a
    submitted request -- S-14. Only the coordinator this request was routed
    to may decide it (same ownership principle as an organiser's own
    routes), and only while it is `submitted`: a decision already made, or
    a draft nothing has submitted yet, cannot be decided on again.
    """
    coordinator_id = str(user.id)
    existing = _get_assigned_event(event_id, coordinator_id, db)
    if existing["status"] != "submitted":
        raise HTTPException(status_code=409, detail="This request is not awaiting a decision")

    changes = {
        "status": _STATUS_AFTER_DECISION[payload.decision],
        "decision": payload.decision.value,
        "decision_reason": payload.reason,
        "decision_comment": payload.comment,
        "decided_at": _decided_now(),
    }
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .update(changes)
        .eq("id", str(event_id))
        .eq("assigned_coordinator_id", coordinator_id)
        .eq("status", "submitted")
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=409, detail="This request is not awaiting a decision")
    return result.data[0]


# --- Internal, composite-only routes ----------------------------------------
#
# No Kong route exists for any of these -- see schemas.py's note on the
# models they use. They are reachable only from inside the Docker network,
# by the event_requests composite service.


def _window_bounds(start_date: date, start_time: time, end_date: date, end_time: time):
    return datetime.combine(start_date, start_time), datetime.combine(end_date, end_time)


def _windows_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    # Strict inequalities: a request that starts exactly when another ends
    # (or vice versa) is back-to-back, not overlapping.
    return a_start < b_end and b_start < a_end


@app.post("/events/coordinator-load", response_model=list[CoordinatorLoad])
def coordinator_load(payload: CoordinatorLoadRequest, db: Client = Depends(get_db)):
    if not payload.coordinator_ids:
        return []

    ids = [str(coordinator_id) for coordinator_id in payload.coordinator_ids]
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("id,assigned_coordinator_id,start_date,start_time,end_date,end_time")
        .in_("assigned_coordinator_id", ids)
        # Submitted (awaiting decision) and planning (accepted, arrangements
        # underway) both occupy the coordinator's time. Returned and rejected
        # do not -- neither is a live commitment.
        .in_("status", ["submitted", "planning"])
    )
    rows = _execute(operation).data

    # Excluded here, in Python, rather than added to the query: this keeps
    # the query's shape identical whether or not a caller is rechecking an
    # existing event, which is what every other case (a fresh submission)
    # still is.
    exclude_event_id = (
        str(payload.exclude_event_id) if payload.exclude_event_id is not None else None
    )

    by_coordinator: dict[str, list[dict]] = {coordinator_id: [] for coordinator_id in ids}
    for row in rows:
        if row["id"] == exclude_event_id:
            continue
        by_coordinator[row["assigned_coordinator_id"]].append(row)

    requested_start, requested_end = _window_bounds(
        payload.start_date, payload.start_time, payload.end_date, payload.end_time
    )

    results = []
    for coordinator_id in ids:
        assigned = by_coordinator[coordinator_id]
        conflict = any(
            _windows_overlap(
                requested_start,
                requested_end,
                *_window_bounds(
                    date.fromisoformat(row["start_date"]),
                    time.fromisoformat(row["start_time"]),
                    date.fromisoformat(row["end_date"]),
                    time.fromisoformat(row["end_time"]),
                ),
            )
            for row in assigned
        )
        results.append(
            {
                "coordinator_id": coordinator_id,
                "conflict": conflict,
                "assigned_count": len(assigned),
            }
        )
    return results


@app.post("/events/overlapping", response_model=list[OverlappingEvent])
def overlapping_events(payload: OverlappingEventsRequest, db: Client = Depends(get_db)):
    """S-44: the live events whose time overlaps a window -- the ones whose
    equipment requirements reserve equipment then. Planning and confirmed
    events are committed; draft, submitted, returned and rejected are not."""
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("id,name,status,start_date,start_time,end_date,end_time")
        .in_("status", ["planning", "confirmed"])
        # Coarse date filter in the query; the exact time overlap below.
        .lte("start_date", payload.end_date.isoformat())
        .gte("end_date", payload.start_date.isoformat())
    )
    rows = _execute(operation).data

    requested_start, requested_end = _window_bounds(
        payload.start_date, payload.start_time, payload.end_date, payload.end_time
    )

    def bounds(row):
        return _window_bounds(
            date.fromisoformat(row["start_date"]),
            time.fromisoformat(row["start_time"]),
            date.fromisoformat(row["end_date"]),
            time.fromisoformat(row["end_time"]),
        )

    overlapping = [row for row in rows if _windows_overlap(requested_start, requested_end, *bounds(row))]
    return sorted(overlapping, key=bounds)


@app.post(
    "/events/technical-support-load",
    response_model=list[TechnicalSupportLoad],
)
def technical_support_load(
    payload: TechnicalSupportLoadRequest,
    db: Client = Depends(get_db),
):
    if not payload.staff_ids:
        return []

    ids = [str(staff_id) for staff_id in payload.staff_ids]
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select(
            "id,assigned_technical_support_id,start_date,start_time,end_date,end_time"
        )
        .in_("assigned_technical_support_id", ids)
        .in_("status", ["planning", "confirmed"])
    )
    rows = _execute(operation).data
    by_staff: dict[str, list[dict]] = {staff_id: [] for staff_id in ids}
    for row in rows:
        staff_id = row.get("assigned_technical_support_id")
        if staff_id in by_staff:
            by_staff[staff_id].append(row)

    requested_start, requested_end = _window_bounds(
        payload.start_date, payload.start_time, payload.end_date, payload.end_time
    )
    return [
        {
            "staff_id": staff_id,
            "conflict": any(
                _windows_overlap(
                    requested_start,
                    requested_end,
                    *_window_bounds(
                        date.fromisoformat(row["start_date"]),
                        time.fromisoformat(row["start_time"]),
                        date.fromisoformat(row["end_date"]),
                        time.fromisoformat(row["end_time"]),
                    ),
                )
                for row in by_staff[staff_id]
            ),
            "assigned_count": len(by_staff[staff_id]),
        }
        for staff_id in ids
    ]


@app.put(
    "/events/{event_id}/technical-support/internal",
    response_model=EventRead,
)
def record_technical_support_assignment(
    event_id: UUID,
    payload: InternalTechnicalSupportAssignment,
    db: Client = Depends(get_db),
):
    coordinator_id = str(payload.coordinator_id)
    current = _execute(
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("id", str(event_id))
        .eq("assigned_coordinator_id", coordinator_id)
        .eq("status", "planning")
    )
    if not current.data:
        raise HTTPException(
            status_code=409,
            detail="Technical Support can only be requested for your planning event",
        )

    event = current.data[0]
    existing_staff_id = event.get("assigned_technical_support_id")
    selected_staff_id = existing_staff_id or (
        str(payload.assigned_technical_support_id)
        if payload.assigned_technical_support_id is not None
        else None
    )
    assigned_at = event.get("technical_support_assigned_at")
    if selected_staff_id is not None and assigned_at is None:
        assigned_at = datetime.now(timezone.utc).isoformat()

    values = {
        "technical_support_required": True,
        "technical_support_details": payload.technical_support_details,
        "assigned_technical_support_id": selected_staff_id,
        "technical_support_assigned_at": assigned_at,
    }
    if all(event.get(field) == value for field, value in values.items()):
        return event

    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .update(values)
        .eq("id", str(event_id))
        .eq("assigned_coordinator_id", coordinator_id)
        .eq("status", "planning")
    )
    if existing_staff_id is None:
        operation = operation.is_("assigned_technical_support_id", "null")
    else:
        operation = operation.eq(
            "assigned_technical_support_id", existing_staff_id
        )
    result = _execute(operation.select("*"))
    if not result.data:
        raise HTTPException(
            status_code=409,
            detail="The event changed before Technical Support could be saved",
        )
    return result.data[0]


@app.post(
    "/events/internal",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_submitted_event_internal(
    payload: InternalEventCreate,
    db: Client = Depends(get_db),
):
    values = payload.model_dump(mode="json")
    values["status"] = "submitted"
    values["submitted_at"] = _submitted_now()
    result = _execute(db.schema(SCHEMA).table(TABLE).insert(values))
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create event",
        )
    return result.data[0]


@app.post("/events/{event_id}/submit/internal", response_model=EventRead)
def submit_draft_internal(
    event_id: UUID,
    payload: InternalEventSubmit,
    db: Client = Depends(get_db),
):
    organiser_id = str(payload.organiser_id)
    existing = _get_owned_event(event_id, organiser_id, db)
    if existing["status"] not in _SUBMITTABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Event has already been submitted")

    changes = payload.model_dump(mode="json", exclude={"organiser_id"})
    changes["status"] = "submitted"
    changes["submitted_at"] = _submitted_now()
    changes["decision"] = None
    changes["decision_reason"] = None
    changes["decision_comment"] = None
    changes["decided_at"] = None
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .update(changes)
        .eq("id", str(event_id))
        .eq("organiser_id", organiser_id)
        .in_("status", _SUBMITTABLE_STATUSES)
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=409, detail=_NO_LONGER_AWAITING_CHANGES)
    return result.data[0]


@app.patch("/events/{event_id}/internal", response_model=EventRead)
def update_event_internal(
    event_id: UUID,
    payload: InternalEventUpdate,
    db: Client = Depends(get_db),
):
    """Mirrors the public PATCH /events/{event_id}, plus an optional
    reassignment -- for the composite's edit-recheck flow, which only calls
    this when the currently assigned coordinator no longer fits the edited
    window and a different one has to be written in the same update.
    """
    organiser_id = str(payload.organiser_id)
    existing = _get_owned_event(event_id, organiser_id, db)

    if existing["status"] == "rejected":
        raise HTTPException(status_code=409, detail="This request has been rejected and is closed")

    changes = payload.model_dump(exclude_unset=True, mode="json", exclude={"organiser_id"})
    if not changes:
        return existing

    validator = EventDraftCreate if existing["status"] == "draft" else EventSubmittedCreate
    candidate = {field: existing.get(field) for field in EventDraftCreate.model_fields}
    candidate.update(
        {key: value for key, value in changes.items() if key in EventDraftCreate.model_fields}
    )
    try:
        validator.model_validate(candidate)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .update(changes)
        .eq("id", str(event_id))
        .eq("organiser_id", organiser_id)
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")
    return result.data[0]
