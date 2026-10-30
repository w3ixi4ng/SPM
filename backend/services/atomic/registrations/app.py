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
from schemas import (
    OfferAcceptanceCreate,
    OfferDeclineCreate,
    OfferDeclineRead,
    RegistrationCreate,
    RegistrationRead,
    WaitingListCreate,
    WaitingListRead,
    WithdrawalCreate,
    WithdrawalRead,
)

app = FastAPI(title="Registrations Service")
logger = logging.getLogger(__name__)

SCHEMA = "registrations"
TABLE = "registrations"
WAITING_LIST = "waiting_list"
UNIQUE_VIOLATION = "23505"
# Raised by registrations.register when the event has no place left.
EVENT_FULL = "SP050"
# Raised by registrations.withdraw when the Attendee holds no place.
NOT_HELD = "SP053"
# Raised by registrations.accept_offer / decline_offer without an open offer.
NO_OFFER_HELD = "SP055"
ALREADY_REGISTERED = "You're already registered for this event."
NOT_REGISTERED = "You're not registered for this event."
FULL = "This event is full."
ALREADY_WAITING = "You're already on the waiting list for this event."
NOT_WAITING = "You're not on the waiting list for this event."
NO_OFFER = "You don't have a place on offer for this event."


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


def _execute(operation, *, duplicate: str = ALREADY_REGISTERED):
    try:
        return operation.execute()
    except APIError as exc:
        # One place per account per event: the table's unique constraint is
        # what makes a second registration, even a simultaneous one, fail.
        if exc.code == UNIQUE_VIOLATION:
            raise HTTPException(status_code=409, detail=duplicate) from exc
        if exc.code == EVENT_FULL:
            raise HTTPException(status_code=409, detail=FULL) from exc
        if exc.code == NOT_HELD:
            raise HTTPException(status_code=404, detail=NOT_REGISTERED) from exc
        if exc.code == NO_OFFER_HELD:
            raise HTTPException(status_code=404, detail=NO_OFFER) from exc
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
    # S-50: counted and inserted in one locked step in Postgres, so the last
    # place can't go to two people registering at the same moment.
    params = payload.model_dump(mode="json")
    result = _execute(
        db.schema(SCHEMA).rpc(
            "register",
            {
                "p_event_id": params["event_id"],
                "p_attendee_id": params["attendee_id"],
                "p_capacity": params["capacity"],
            },
        )
    )
    if not result.data:
        raise _storage_unavailable()
    return result.data[0]


# S-53: the place is given up and, in the same locked step, S-55: offered to
# the Attendee who has waited longest -- held for them, not given.
@app.post("/registrations/withdrawals", response_model=WithdrawalRead)
def withdraw(payload: WithdrawalCreate, db: Client = Depends(get_db)):
    params = payload.model_dump(mode="json")
    result = _execute(
        db.schema(SCHEMA).rpc(
            "withdraw",
            {
                "p_event_id": params["event_id"],
                "p_attendee_id": params["attendee_id"],
                "p_capacity": params["capacity"],
            },
        )
    )
    if not result.data:
        raise _storage_unavailable()
    return result.data


# S-55: only the invited Attendee's own acceptance registers them.
@app.post("/registrations/offers/acceptances", response_model=RegistrationRead, status_code=201)
def accept_offer(payload: OfferAcceptanceCreate, db: Client = Depends(get_db)):
    params = payload.model_dump(mode="json")
    result = _execute(
        db.schema(SCHEMA).rpc(
            "accept_offer",
            {"p_event_id": params["event_id"], "p_attendee_id": params["attendee_id"]},
        )
    )
    if not result.data:
        raise _storage_unavailable()
    return result.data[0]


# S-55: declining leaves the waiting list and, in the same locked step, offers
# the place to the next in line.
@app.post("/registrations/offers/declines", response_model=OfferDeclineRead)
def decline_offer(payload: OfferDeclineCreate, db: Client = Depends(get_db)):
    params = payload.model_dump(mode="json")
    result = _execute(
        db.schema(SCHEMA).rpc(
            "decline_offer",
            {
                "p_event_id": params["event_id"],
                "p_attendee_id": params["attendee_id"],
                "p_capacity": params["capacity"],
            },
        )
    )
    if not result.data:
        raise _storage_unavailable()
    return result.data


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


# S-50: Attendees waiting for a place at a full event, in the order they joined.
@app.post("/registrations/waiting-list", response_model=WaitingListRead, status_code=201)
def join_waiting_list(payload: WaitingListCreate, db: Client = Depends(get_db)):
    result = _execute(
        db.schema(SCHEMA).table(WAITING_LIST).insert(payload.model_dump(mode="json")),
        duplicate=ALREADY_WAITING,
    )
    if not result.data:
        raise _storage_unavailable()
    return result.data[0]


@app.get(
    "/registrations/waiting-list/events/{event_id}", response_model=list[WaitingListRead]
)
def list_waiting_list(event_id: UUID, db: Client = Depends(get_db)):
    operation = (
        db.schema(SCHEMA)
        .table(WAITING_LIST)
        .select("*")
        .eq("event_id", str(event_id))
        # S-52: first come, first served; id breaks a tie so no two entries
        # ever share a place in line.
        .order("created_at")
        .order("id")
    )
    return _execute(operation).data


# S-52: every event an Attendee is waiting for, for their dashboard.
@app.get(
    "/registrations/waiting-list/attendees/{attendee_id}", response_model=list[WaitingListRead]
)
def list_attendee_waiting_list(attendee_id: UUID, db: Client = Depends(get_db)):
    operation = (
        db.schema(SCHEMA)
        .table(WAITING_LIST)
        .select("*")
        .eq("attendee_id", str(attendee_id))
        .order("created_at")
    )
    return _execute(operation).data


@app.get(
    "/registrations/waiting-list/events/{event_id}/attendees/{attendee_id}",
    response_model=WaitingListRead,
)
def get_waiting_list_entry(event_id: UUID, attendee_id: UUID, db: Client = Depends(get_db)):
    operation = (
        db.schema(SCHEMA)
        .table(WAITING_LIST)
        .select("*")
        .eq("event_id", str(event_id))
        .eq("attendee_id", str(attendee_id))
    )
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=404, detail=NOT_WAITING)
    return result.data[0]
