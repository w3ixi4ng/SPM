"""Atomic service: venue booking requests.

Stores what the venue_bookings composite has already checked, and lists it
back. It never calls another service and never judges whether a request is
suitable -- that needs the event and the venue, which makes it composite
work. No Kong route reaches this service. S-37 decisions verify staff
credentials independently, including calls to the published service port.
"""

import logging
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from supabase import Client

from database import get_db
from schemas import BookingCreate, BookingRead, BookingDecision
from security import require_venue_staff

app = FastAPI(title="Bookings Service")
logger = logging.getLogger(__name__)

SCHEMA = "bookings"
TABLE = "bookings"


@app.exception_handler(RequestValidationError)
async def readable_validation_error(request: Request, exc: RequestValidationError):
    errors: dict[str, str] = {}
    for error in exc.errors():
        path = [str(part) for part in error["loc"] if part not in ("body", "query")]
        errors.setdefault(".".join(path) or "body", error["msg"])

    return JSONResponse(
        status_code=422,
        content={"detail": "Please check the details you entered", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    logger.exception("Unhandled bookings service error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


def _execute(operation):
    try:
        return operation.execute()
    except Exception as exc:
        logger.exception("Booking storage operation failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Booking storage unavailable",
        ) from exc


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/bookings/{booking_id}/decision", response_model=BookingRead)
def decide_booking(
    booking_id: UUID,
    payload: BookingDecision,
    staff=Depends(require_venue_staff),
    db: Client = Depends(get_db),
):
    values = {
        "status": "confirmed" if payload.decision == "approved" else "rejected",
        "decision_reason": payload.reason,
        "decision_alternative": payload.alternative,
        "decided_by": str(staff.id),
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    # One conditional write: concurrent decisions cannot overwrite the winner.
    # S-38 must protect this pending -> confirmed write against OTHER bookings
    # for the same venue/slot. This condition alone does not prevent overlaps.
    result = _execute(db.schema(SCHEMA).table(TABLE).update(values)
                      .eq("id", str(booking_id)).eq("status", "pending"))
    if result.data:
        return result.data[0]
    existing = _execute(db.schema(SCHEMA).table(TABLE).select("id")
                        .eq("id", str(booking_id)))
    if not existing.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    raise HTTPException(status_code=409, detail="This booking request has already been decided")


@app.post("/bookings", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingCreate, db: Client = Depends(get_db)):
    values = payload.model_dump(mode="json")
    values["status"] = "pending"
    # Set here, never taken from the payload, so a request cannot be
    # backdated ahead of others in Venue Staff's queue.
    values["submitted_at"] = datetime.now(timezone.utc).isoformat()
    result = _execute(db.schema(SCHEMA).table(TABLE).insert(values))
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create booking",
        )
    return result.data[0]


@app.get("/bookings", response_model=list[BookingRead])
def list_bookings(
    booking_status: Literal["pending"] | None = Query(default=None, alias="status"),
    event_id: UUID | None = None,
    db: Client = Depends(get_db),
):
    # Always filtered: Venue Staff ask by status, a Coordinator by event.
    # Nothing hands out every booking at once.
    if booking_status is None and event_id is None:
        raise HTTPException(status_code=422, detail="Filter by status or event_id")

    operation = db.schema(SCHEMA).table(TABLE).select("*")
    if booking_status is not None:
        operation = operation.eq("status", booking_status)
    if event_id is not None:
        operation = operation.eq("event_id", str(event_id))
    # Oldest first: the order requests came in.
    return _execute(operation.order("submitted_at")).data
