"""Atomic service: venue booking requests.

Stores what the venue_bookings composite has already checked, and lists it
back. It never calls another service and never judges whether a request is
suitable -- that needs the event and the venue, which makes it composite
work. No Kong route reaches this service. S-37 decisions verify staff
credentials independently, including calls to the published service port.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal, NamedTuple
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from supabase import Client

from database import get_db
from schemas import BlockCreate, BlockRead, BookingCreate, BookingRead, BookingDecision, HoldRelease
from security import require_user, require_venue_staff

app = FastAPI(title="Bookings Service")
logger = logging.getLogger(__name__)

SCHEMA = "bookings"
TABLE = "bookings"
BLOCKS = "blocks"

# S-30: a pending request is a tentative hold, and holds are exclusive, so a
# new request must not overlap either of these.
LIVE_STATUSES = ["held", "confirmed"]


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


def _booking(db: Client, booking_id: UUID):
    result = _execute(
        db.schema(SCHEMA).table(TABLE).select("*").eq("id", str(booking_id))
    )
    return result.data[0] if result.data else None


def _overlap(db: Client, booking: dict):
    operation = (
        db.schema(SCHEMA).table(TABLE)
        .select("id,status,venue_name,booking_date,start_time,end_time")
        .eq("venue_id", booking["venue_id"])
        .eq("booking_date", booking["booking_date"])
        .eq("status", "confirmed")
        .neq("id", booking["id"])
        .lt("start_time", booking["end_time"])
        .gt("end_time", booking["start_time"])
        .order("start_time")
        .limit(1)
    )
    result = _execute(operation)
    return result.data[0] if result.data else None


class Gap(NamedTuple):
    """S-75: the venue's current setup and turnaround minutes. A booking
    occupies its venue from start - setup to end + turnaround, so two
    bookings at one venue need setup + turnaround minutes between them."""

    setup: int = 0
    turnaround: int = 0

    @property
    def minutes(self) -> int:
        return self.setup + self.turnaround


def venue_gap(
    setup_minutes: int = Query(default=0, ge=0),
    turnaround_minutes: int = Query(default=0, ge=0),
) -> Gap:
    """The venue_bookings composite passes the venue's times as it reads them
    now. A caller passing none gets the pre-S-75 rule: no gap."""
    return Gap(setup_minutes, turnaround_minutes)


def _shift(value, minutes: int) -> str:
    """A booking time moved by `minutes`, kept within its day: bookings never
    cross midnight, and neither does their occupied window (S-75 keeps it
    inside opening hours), so the day's edges are bounds enough."""
    day = date(2000, 1, 2)
    moved = datetime.combine(day, time.fromisoformat(str(value))) + timedelta(minutes=minutes)
    if moved.date() < day:
        return "00:00:00"
    if moved.date() > day:
        return "24:00:00"
    return moved.time().isoformat()


def _live_overlap(db: Client, booking: dict, gap: Gap = Gap()):
    """S-30: a new request against every hold and confirmed booking -- holds
    are exclusive. Half-open, so back-to-back is allowed. S-75: widened by the
    venue's setup + turnaround, so a booking is checked by the time its venue
    is occupied, not just its own start and end."""
    operation = (
        db.schema(SCHEMA).table(TABLE)
        .select("id,status,venue_name,booking_date,start_time,end_time")
        .eq("venue_id", booking["venue_id"])
        .eq("booking_date", booking["booking_date"])
        .in_("status", LIVE_STATUSES)
    )
    # A held booking being confirmed is itself live; it never clashes with itself.
    if booking.get("id"):
        operation = operation.neq("id", str(booking["id"]))
    operation = (
        operation
        .lt("start_time", _shift(booking["end_time"], gap.minutes))
        .gt("end_time", _shift(booking["start_time"], -gap.minutes))
        .order("start_time")
        .limit(1)
    )
    result = _execute(operation)
    return result.data[0] if result.data else None


def _block_on(db: Client, venue_id: str, day: str):
    """S-30: the block covering `day` at this venue, if any. Blocks are whole
    days, inclusive at both ends."""
    operation = (
        db.schema(SCHEMA).table(BLOCKS)
        .select("id,venue_name,start_date,end_date")
        .eq("venue_id", str(venue_id))
        .lte("start_date", str(day))
        .gte("end_date", str(day))
        .order("start_date")
        .limit(1)
    )
    result = _execute(operation)
    return result.data[0] if result.data else None


def _date_label(value) -> str:
    return datetime.fromisoformat(str(value)).strftime("%d %b %Y")


def _conflict_detail(conflict: dict, gap: Gap = Gap()) -> str:
    booking_date = _date_label(conflict["booking_date"])
    start = str(conflict["start_time"])[:5]
    end = str(conflict["end_time"])[:5]
    taken = "tentatively held" if conflict.get("status") == "held" else "confirmed"
    detail = (
        f'{conflict["venue_name"]} is already {taken} on {booking_date} '
        f"from {start} to {end}."
    )
    if gap.minutes:
        # S-75: say why a time that looks free is not.
        in_use_until = _shift(conflict["end_time"], gap.turnaround)[:5]
        detail += (
            f" With {gap.setup} min setup and {gap.turnaround} min turnaround "
            f"it is in use until {in_use_until}."
        )
    return detail


def _raise_overlap(conflict: dict, gap: Gap = Gap()):
    raise HTTPException(status_code=409, detail=_conflict_detail(conflict, gap))


def _raise_blocked(block: dict):
    raise HTTPException(
        status_code=409,
        detail=(
            f'{block["venue_name"]} is unavailable from {_date_label(block["start_date"])} '
            f'to {_date_label(block["end_date"])}.'
        ),
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/bookings/{booking_id}/decision", response_model=BookingRead)
def decide_booking(
    booking_id: UUID,
    payload: BookingDecision,
    staff=Depends(require_venue_staff),
    gap: Gap = Depends(venue_gap),
    db: Client = Depends(get_db),
):
    booking = _booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["status"] not in ("pending", "held"):
        raise HTTPException(status_code=409, detail="This booking request has already been decided")

    if payload.decision == "approved":
        conflict = _live_overlap(db, {**booking, "id": str(booking_id)}, gap)
        if conflict:
            _raise_overlap(conflict, gap)
        # S-30: a block added after the request was sent stops it being
        # confirmed. Rejecting it stays possible.
        block = _block_on(db, booking["venue_id"], booking["booking_date"])
        if block:
            _raise_blocked(block)

    values = {
        "status": "confirmed" if payload.decision == "approved" else "rejected",
        "decision_reason": payload.reason,
        "decision_alternative": payload.alternative,
        "decided_by": str(staff.id),
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    # The conditional update protects this request from two decisions. The
    # database exclusion constraint protects different requests for the same
    # venue/slot, including simultaneous confirmations after the check above.
    try:
        result = db.schema(SCHEMA).table(TABLE).update(values).eq(
            "id", str(booking_id)
    ).in_("status", ["pending", "held"]).execute()
    except Exception as exc:
        if payload.decision == "approved" and getattr(exc, "code", None) == "23P01":
            conflict = _overlap(db, booking)
            if conflict:
                _raise_overlap(conflict, gap)
        logger.exception("Booking storage operation failed", exc_info=exc)
        raise HTTPException(status_code=500, detail="Booking storage unavailable") from exc
    if result.data:
        return result.data[0]
    raise HTTPException(status_code=409, detail="This booking request has already been decided")


@app.post("/bookings/{booking_id}/hold", response_model=BookingRead)
def place_hold(
    booking_id: UUID,
    staff=Depends(require_venue_staff),
    gap: Gap = Depends(venue_gap),
    db: Client = Depends(get_db),
):
    booking = _booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["status"] == "held":
        return booking
    if booking["status"] != "pending":
        raise HTTPException(status_code=409, detail="Only a pending booking request can be held")

    conflict = _live_overlap(db, {**booking, "id": str(booking_id)}, gap)
    if conflict:
        _raise_overlap(conflict, gap)
    block = _block_on(db, booking["venue_id"], booking["booking_date"])
    if block:
        _raise_blocked(block)

    values = {
        "status": "held",
        "held_by": str(staff.id),
        "held_at": datetime.now(timezone.utc).isoformat(),
        "hold_released_at": None,
        "hold_release_reason": None,
    }
    try:
        result = db.schema(SCHEMA).table(TABLE).update(values).eq(
            "id", str(booking_id)
        ).eq("status", "pending").execute()
    except Exception as exc:
        if getattr(exc, "code", None) == "23P01":
            conflict = _live_overlap(db, {**booking, "id": str(booking_id)}, gap)
            if conflict:
                _raise_overlap(conflict, gap)
        logger.exception("Booking storage operation failed", exc_info=exc)
        raise HTTPException(status_code=500, detail="Booking storage unavailable") from exc
    if result.data:
        return result.data[0]
    raise HTTPException(status_code=409, detail="Only a pending booking request can be held")


@app.post("/bookings/{booking_id}/release", response_model=BookingRead)
def release_hold(
    booking_id: UUID,
    payload: HoldRelease,
    user=Depends(require_user),
    db: Client = Depends(get_db),
):
    booking = _booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    role = (getattr(user, "app_metadata", None) or {}).get("role")
    if role == "event_coordinator":
        if payload.reason != "booking_replaced" or str(user.id) != str(booking["coordinator_id"]):
            raise HTTPException(status_code=403, detail="Permission denied")
    elif role == "venue_staff":
        pass
    else:
        raise HTTPException(status_code=403, detail="Permission denied")
    if booking["status"] == "pending" and booking.get("hold_release_reason") == payload.reason:
        return booking
    if booking["status"] != "held":
        raise HTTPException(status_code=409, detail="Only a tentative hold can be released")

    values = {
        "status": "pending",
        "hold_released_at": datetime.now(timezone.utc).isoformat(),
        "hold_release_reason": payload.reason,
    }
    result = _execute(
        db.schema(SCHEMA).table(TABLE).update(values)
        .eq("id", str(booking_id)).eq("status", "held")
    )
    if result.data:
        return result.data[0]
    raise HTTPException(status_code=409, detail="Only a tentative hold can be released")


@app.post("/bookings", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate,
    gap: Gap = Depends(venue_gap),
    db: Client = Depends(get_db),
):
    values = payload.model_dump(mode="json")
    values["status"] = "pending"
    # Set here, never taken from the payload, so a request cannot be
    # backdated ahead of others in Venue Staff's queue.
    values["submitted_at"] = datetime.now(timezone.utc).isoformat()

    # A new request is pending and does not itself reserve the slot, but it
    # may not be submitted into a slot already held, confirmed or blocked.
    conflict = _live_overlap(db, values, gap)
    if conflict:
        _raise_overlap(conflict, gap)
    block = _block_on(db, values["venue_id"], values["booking_date"])
    if block:
        _raise_blocked(block)
    try:
        result = db.schema(SCHEMA).table(TABLE).insert(values).execute()
    except Exception as exc:
        if getattr(exc, "code", None) == "23P01":
            conflict = _live_overlap(db, values, gap)
            if conflict:
                _raise_overlap(conflict, gap)
        logger.exception("Booking storage operation failed", exc_info=exc)
        raise HTTPException(status_code=500, detail="Booking storage unavailable") from exc
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create booking",
        )
    return result.data[0]


def _date_range(venue_id, from_date, to_date):
    """A venue filter always comes with a range, so nothing lists a venue's
    whole history at once."""
    if venue_id is None or from_date is None or to_date is None:
        raise HTTPException(status_code=422, detail="Filter by venue_id with from and to")
    if to_date < from_date:
        raise HTTPException(status_code=422, detail="The end date must be on or after the start date")


@app.get("/bookings", response_model=list[BookingRead])
def list_bookings(
    booking_status: Literal["pending", "held", "actionable"] | None = Query(default=None, alias="status"),
    event_id: UUID | None = None,
    venue_id: UUID | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Client = Depends(get_db),
):
    # Always filtered: Venue Staff ask by status, a Coordinator by event, and
    # S-30's calendar by venue and date range. Nothing hands out every
    # booking at once.
    if venue_id is not None or from_date is not None or to_date is not None:
        _date_range(venue_id, from_date, to_date)
        operation = (
            db.schema(SCHEMA).table(TABLE).select("*")
            .eq("venue_id", str(venue_id))
            .gte("booking_date", from_date.isoformat())
            .lte("booking_date", to_date.isoformat())
        )
        return _execute(operation.order("booking_date").order("start_time")).data

    if booking_status is None and event_id is None:
        raise HTTPException(status_code=422, detail="Filter by status or event_id")

    operation = db.schema(SCHEMA).table(TABLE).select("*")
    if booking_status == "actionable":
        operation = operation.in_("status", ["pending", "held"])
    elif booking_status is not None:
        operation = operation.eq("status", booking_status)
    if event_id is not None:
        operation = operation.eq("event_id", str(event_id))
    # Oldest first: the order requests came in.
    return _execute(operation.order("submitted_at")).data


@app.get("/bookings/{booking_id}", response_model=BookingRead)
def get_booking(booking_id: UUID, db: Client = Depends(get_db)):
    """S-75: one request, for the venue_bookings composite -- it needs the
    booking's venue to pass that venue's setup and turnaround times to a
    hold or decision, and Venue Staff open each request on its own page.
    Internal, like the other reads: the composite checks the caller's role."""
    booking = _booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


@app.post("/blocks", response_model=BlockRead, status_code=status.HTTP_201_CREATED)
def create_block(
    payload: BlockCreate,
    staff=Depends(require_venue_staff),
    db: Client = Depends(get_db),
):
    # S-30. A block may cover existing holds and bookings -- an emergency
    # does not wait for them -- and none of them is changed here. Staff
    # reassign affected events offline.
    values = payload.model_dump(mode="json")
    values["created_by"] = str(staff.id)
    values["created_at"] = datetime.now(timezone.utc).isoformat()
    result = _execute(db.schema(SCHEMA).table(BLOCKS).insert(values))
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create block",
        )
    return result.data[0]


@app.get("/blocks", response_model=list[BlockRead])
def list_blocks(
    venue_id: UUID | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Client = Depends(get_db),
):
    # Every block touching the range, including one that only partly does.
    _date_range(venue_id, from_date, to_date)
    operation = (
        db.schema(SCHEMA).table(BLOCKS).select("*")
        .eq("venue_id", str(venue_id))
        .lte("start_date", to_date.isoformat())
        .gte("end_date", from_date.isoformat())
    )
    return _execute(operation.order("start_date")).data


@app.delete("/blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_block(
    block_id: UUID,
    staff=Depends(require_venue_staff),
    db: Client = Depends(get_db),
):
    result = _execute(db.schema(SCHEMA).table(BLOCKS).delete().eq("id", str(block_id)))
    if not result.data:
        raise HTTPException(status_code=404, detail="Block not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
