"""S-51: who holds a place at which event.

Only composites call this service; it has no Kong route. Event ids and
attendee ids are opaque here -- the events and users services own them.
"""

import logging
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError
from supabase import Client

from database import get_db
from schemas import RegistrationCreate, RegistrationRead

app = FastAPI(title="Registrations Service")
logger = logging.getLogger(__name__)

SCHEMA = "registrations"
TABLE = "registrations"
UNIQUE_VIOLATION = "23505"
ALREADY_REGISTERED = "You're already registered for this event."
NOT_REGISTERED = "You're not registered for this event."


@app.exception_handler(RequestValidationError)
async def readable_validation_error(request: Request, exc: RequestValidationError):
    errors: dict[str, str] = {}
    for error in exc.errors():
        path = [str(part) for part in error["loc"] if part != "body"]
        errors.setdefault(".".join(path) or "body", error["msg"])
    return JSONResponse(
        status_code=422,
        content={"detail": "Please check the registration", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    logger.exception("Unhandled registrations service error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _execute(operation):
    try:
        return operation.execute()
    except APIError as exc:
        # One place per account per event: the table's unique constraint is
        # what makes a second registration, even a simultaneous one, fail.
        if exc.code == UNIQUE_VIOLATION:
            raise HTTPException(status_code=409, detail=ALREADY_REGISTERED) from exc
        logger.exception("Registration storage operation failed", exc_info=exc)
        raise _storage_unavailable() from exc
    except Exception as exc:
        logger.exception("Registration storage operation failed", exc_info=exc)
        raise _storage_unavailable() from exc


def _storage_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Registration storage unavailable",
    )


@app.get("/health")
@app.get("/registrations/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.post("/registrations", response_model=RegistrationRead, status_code=201)
def create_registration(payload: RegistrationCreate, db: Client = Depends(get_db)):
    result = _execute(
        db.schema(SCHEMA).table(TABLE).insert(payload.model_dump(mode="json"))
    )
    if not result.data:
        raise _storage_unavailable()
    return result.data[0]


@app.get(
    "/registrations/events/{event_id}/attendees/{attendee_id}",
    response_model=RegistrationRead,
)
def get_registration(event_id: UUID, attendee_id: UUID, db: Client = Depends(get_db)):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("event_id", str(event_id))
        .eq("attendee_id", str(attendee_id))
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=404, detail=NOT_REGISTERED)
    return result.data[0]


# S-48: a place is recorded against both the event and the Attendee, so it
# can be read back from either side. An empty list is an answer, not a 404.
@app.get("/registrations/events/{event_id}", response_model=list[RegistrationRead])
def list_event_registrations(event_id: UUID, db: Client = Depends(get_db)):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("event_id", str(event_id))
        .order("created_at")
    )
    return _execute(operation).data


@app.get("/registrations/attendees/{attendee_id}", response_model=list[RegistrationRead])
def list_attendee_registrations(attendee_id: UUID, db: Client = Depends(get_db)):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("attendee_id", str(attendee_id))
        .order("created_at")
    )
    return _execute(operation).data
