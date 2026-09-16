import logging
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
from schemas import EventDraftCreate, EventDraftUpdate, EventRead, EventSubmittedCreate
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


def _insert_event(payload, event_status: str, organiser_id: str, db: Client):
    values = payload.model_dump(mode="json")
    values.update({"organiser_id": organiser_id, "status": event_status})
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

    changes = payload.model_dump(exclude_unset=True, mode="json")
    if not changes:
        return existing

    # A PATCH may supply only one time while the other already exists on the
    # record. Validate the resulting record, not only the partial request, so
    # a cross-field conflict is still a 422 instead of reaching the SQL CHECK.
    #
    # A submitted event still has to satisfy every submitted-required rule
    # after the edit -- the draft schema would happily accept a PATCH that
    # nulls out a required field, which the database's own constraint would
    # then reject as an opaque storage failure instead of a readable 422.
    validator = EventSubmittedCreate if existing["status"] == "submitted" else EventDraftCreate
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


@app.post("/events/{event_id}/submit", response_model=EventRead)
def submit_draft(
    event_id: UUID,
    payload: EventSubmittedCreate,
    user=Depends(require_permission("events:submit_own")),
    db: Client = Depends(get_db),
):
    organiser_id = str(user.id)
    existing = _get_owned_event(event_id, organiser_id, db)
    if existing["status"] != "draft":
        raise HTTPException(status_code=409, detail="Event has already been submitted")

    changes = payload.model_dump(mode="json")
    changes["status"] = "submitted"
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .update(changes)
        .eq("id", str(event_id))
        .eq("organiser_id", organiser_id)
        .eq("status", "draft")
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=409, detail="Event is no longer an editable draft")
    return result.data[0]
