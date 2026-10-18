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
from schemas import (
    AlternativeResolution,
    BlockCreate,
    BlockRead,
    BookingChange,
    BookingCreate,
    BookingDecision,
    BookingRead,
    HoldRelease,
)
from security import require_coordinator, require_user, require_venue_staff

app = FastAPI(title="Bookings Service")
logger = logging.getLogger(__name__)

SCHEMA = "bookings"
TABLE = "bookings"
BLOCKS = "blocks"

# S-30: a pending request is a tentative hold, and holds are exclusive, so a
# new request must not overlap either of these.
LIVE_STATUSES = ["held", "confirmed"]
CANNOT_RESOLVE = "Only a held or confirmed booking can be resolved"


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
        .select("id,status,event_name,venue_name,booking_date,start_time,end_time")
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


def _block_start(block: dict) -> datetime:
    return datetime.combine(
        date.fromisoformat(str(block["start_date"])), time.fromisoformat(str(block["start_time"]))
    )


def _block_end(block: dict) -> datetime:
    return datetime.combine(
        date.fromisoformat(str(block["end_date"])), time.fromisoformat(str(block["end_time"]))
    )


def _occupied(booking: dict, gap: Gap) -> tuple[datetime, datetime]:
    """S-75: the window a booking occupies its venue, as datetimes. "24:00"
    from _shift is midnight at the end of the day."""
    day = date.fromisoformat(str(booking["booking_date"]))

    def at(value: str) -> datetime:
        if value.startswith("24:"):
            return datetime.combine(day + timedelta(days=1), time())
        return datetime.combine(day, time.fromisoformat(value))

    return (
        at(_shift(booking["start_time"], -gap.setup)),
        at(_shift(booking["end_time"], gap.turnaround)),
    )


def _block_over(db: Client, booking: dict, gap: Gap = Gap()):
    """S-77: the unavailable period at this venue that the booking's occupied
    window overlaps, if any. Periods are half-open, [start, end), so a
    booking may end exactly when one starts or start exactly when it ends.
    The query narrows to periods touching the booking's day; the exact
    overlap is checked here, since it compares a date and a time together."""
    day = str(booking["booking_date"])
    operation = (
        db.schema(SCHEMA).table(BLOCKS)
        .select("id,venue_name,start_date,start_time,end_date,end_time")
        .eq("venue_id", str(booking["venue_id"]))
        .lte("start_date", day)
        .gte("end_date", day)
        .order("start_date")
    )
    occupied_start, occupied_end = _occupied(booking, gap)
    for block in _execute(operation).data or []:
        if _block_start(block) < occupied_end and _block_end(block) > occupied_start:
            return block
    return None


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


def _staff_conflict_detail(action: str, conflict: dict, gap: Gap) -> str:
    """S-76: for Venue Staff only, who may see whose booking it is -- the
    booking in the way and the whole window it occupies the venue."""
    taken = "tentatively held" if conflict.get("status") == "held" else "confirmed"
    start = str(conflict["start_time"])[:5]
    end = str(conflict["end_time"])[:5]
    detail = (
        f"Can't {action} this booking: it overlaps {conflict['event_name']} ({taken}), "
        f"which occupies {conflict['venue_name']} on {_date_label(conflict['booking_date'])} "
        f"from {_shift(conflict['start_time'], -gap.setup)[:5]} "
        f"to {_shift(conflict['end_time'], gap.turnaround)[:5]}"
    )
    if gap.minutes:
        detail += f" (event {start}–{end}, {gap.setup} min setup, {gap.turnaround} min turnaround)"
    return detail + "."


def _raise_staff_overlap(action: str, conflict: dict, gap: Gap):
    raise HTTPException(status_code=409, detail=_staff_conflict_detail(action, conflict, gap))


def _raise_blocked(block: dict):
    start = _block_start(block)
    end = _block_end(block)
    raise HTTPException(
        status_code=409,
        detail=(
            f'{block["venue_name"]} is unavailable from {start:%d %b %Y %H:%M} '
            f'to {end:%d %b %Y %H:%M}.'
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
            _raise_staff_overlap("confirm", conflict, gap)
        # S-30: a block added after the request was sent stops it being
        # confirmed. Rejecting it stays possible.
        block = _block_over(db, booking, gap)
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
    # S-78: confirming a replacement also marks its original `replaced` -- a
    # trigger does that in the same transaction (backend/sql/bookings.sql).
    try:
        result = db.schema(SCHEMA).table(TABLE).update(values).eq(
            "id", str(booking_id)
    ).in_("status", ["pending", "held"]).execute()
    except Exception as exc:
        if payload.decision == "approved" and getattr(exc, "code", None) == "23P01":
            conflict = _live_overlap(db, {**booking, "id": str(booking_id)}, gap)
            if conflict:
                _raise_staff_overlap("confirm", conflict, gap)
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
        _raise_staff_overlap("hold", conflict, gap)
    block = _block_over(db, booking, gap)
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
                _raise_staff_overlap("hold", conflict, gap)
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


# S-80: what a Coordinator may change or cancel. A rejected request is a
# closed decision; it is left as it is.
CHANGEABLE_STATUSES = ["pending", "held", "confirmed"]
# Everything a hold or a decision recorded. A changed booking is a new
# request for Venue Staff, so none of it applies any more.
_REVIEW_CLEARED = {
    "held_by": None, "held_at": None, "hold_released_at": None, "hold_release_reason": None,
    "decided_by": None, "decided_at": None, "decision_reason": None, "decision_alternative": None,
    # S-78: a resolved unavailability flag was about the old time and venue.
    "alternative_resolved_at": None, "alternative_resolved_by": None, "alternative_resolution_note": None,
}


@app.patch("/bookings/{booking_id}", response_model=BookingRead)
def change_booking(
    booking_id: UUID,
    payload: BookingChange,
    gap: Gap = Depends(venue_gap),
    _coordinator=Depends(require_coordinator),
    db: Client = Depends(get_db),
):
    """S-80: move one booking. It goes back to pending, so its old slot is
    free at once and Venue Staff review it again. Checked like a new request,
    except that it never clashes with itself. The composite has already
    checked the Coordinator is assigned to the event."""
    booking = _booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["status"] not in CHANGEABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Only a pending, held or confirmed booking can be changed")

    values = payload.model_dump(mode="json")
    candidate = {**values, "id": str(booking_id)}
    conflict = _live_overlap(db, candidate, gap)
    if conflict:
        _raise_overlap(conflict, gap)
    block = _block_over(db, candidate, gap)
    if block:
        _raise_blocked(block)

    result = _execute(
        db.schema(SCHEMA).table(TABLE)
        .update({**values, "status": "pending", **_REVIEW_CLEARED})
        .eq("id", str(booking_id))
        .in_("status", CHANGEABLE_STATUSES)
    )
    if not result.data:
        raise HTTPException(status_code=409, detail="Only a pending, held or confirmed booking can be changed")
    return result.data[0]


@app.delete("/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def cancel_booking(
    booking_id: UUID,
    _coordinator=Depends(require_coordinator),
    db: Client = Depends(get_db),
):
    """S-80: cancel one booking. It is deleted, so its time shows as
    available; the event's other bookings are not touched."""
    booking = _booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["status"] not in CHANGEABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Only a pending, held or confirmed booking can be cancelled")
    result = _execute(
        db.schema(SCHEMA).table(TABLE).delete()
        .eq("id", str(booking_id))
        .in_("status", CHANGEABLE_STATUSES)
    )
    if not result.data:
        raise HTTPException(status_code=409, detail="Only a pending, held or confirmed booking can be cancelled")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _replacement_problem(db: Client, values: dict):
    """S-78: a replacement must point at a booking of the same event that
    still stands. A JSONResponse to return when it doesn't, else None."""
    original = _booking(db, values["replaces_booking_id"])
    if original is None or str(original["event_id"]) != str(values["event_id"]):
        message = (
            "The booking being replaced doesn't exist" if original is None
            else "A replacement must be for the same event"
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Please check the details you entered",
                "errors": {"replaces_booking_id": message},
            },
        )
    if original["status"] in ("rejected", "replaced"):
        raise HTTPException(status_code=409, detail="This booking can no longer be replaced")
    return None


@app.post("/bookings", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate,
    gap: Gap = Depends(venue_gap),
    db: Client = Depends(get_db),
):
    values = payload.model_dump(mode="json")
    if values["replaces_booking_id"] is not None:
        problem = _replacement_problem(db, values)
        if problem is not None:
            return problem
    values["status"] = "pending"
    # Set here, never taken from the payload, so a request cannot be
    # backdated ahead of others in Venue Staff's queue.
    values["submitted_at"] = datetime.now(timezone.utc).isoformat()

    # A new request is pending and does not itself reserve the slot, but it
    # may not be submitted into a slot already held, confirmed or blocked.
    conflict = _live_overlap(db, values, gap)
    if conflict:
        _raise_overlap(conflict, gap)
    block = _block_over(db, values, gap)
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


@app.post("/bookings/{booking_id}/alternative-resolution", response_model=BookingRead)
def resolve_alternative_arrangements(
    booking_id: UUID,
    payload: AlternativeResolution,
    user=Depends(require_coordinator),
    db: Client = Depends(get_db),
):
    """S-78: a Coordinator records what they arranged instead of the venue an
    unavailable period took away. The booking itself is not changed. Whether
    the event is theirs and the booking is flagged is the venue_bookings
    composite's check; this one keeps the write to live bookings."""
    booking = _booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["status"] not in LIVE_STATUSES:
        raise HTTPException(status_code=409, detail=CANNOT_RESOLVE)
    values = {
        "alternative_resolved_at": datetime.now(timezone.utc).isoformat(),
        "alternative_resolved_by": str(user.id),
        "alternative_resolution_note": payload.note,
    }
    result = _execute(
        db.schema(SCHEMA).table(TABLE).update(values)
        .eq("id", str(booking_id)).in_("status", LIVE_STATUSES)
    )
    if result.data:
        return result.data[0]
    raise HTTPException(status_code=409, detail=CANNOT_RESOLVE)


def _date_range(venue_id, from_date, to_date):
    """A venue filter always comes with a range, so nothing lists a venue's
    whole history at once."""
    if venue_id is None or from_date is None or to_date is None:
        raise HTTPException(status_code=422, detail="Filter by venue_id with from and to")
    if to_date < from_date:
        raise HTTPException(status_code=422, detail="The end date must be on or after the start date")


@app.get("/bookings", response_model=list[BookingRead])
def list_bookings(
    booking_status: Literal["pending", "held", "actionable", "live"] | None = Query(default=None, alias="status"),
    event_id: UUID | None = None,
    venue_id: UUID | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Client = Depends(get_db),
):
    # Always filtered: Venue Staff ask by status, a Coordinator by event, and
    # S-30's calendar by venue and date range. Nothing hands out every
    # booking at once.
    if booking_status == "live":
        # S-76: every held and confirmed booking from a date on, for Venue
        # Staff's clashes to review. Always bounded by a start date.
        if from_date is None:
            raise HTTPException(status_code=422, detail="Filter live bookings by from")
        operation = (
            db.schema(SCHEMA).table(TABLE).select("*")
            .in_("status", LIVE_STATUSES)
            .gte("booking_date", from_date.isoformat())
        )
        if venue_id is not None:
            operation = operation.eq("venue_id", str(venue_id))
        return _execute(
            operation.order("venue_id").order("booking_date").order("start_time")
        ).data

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
    # does not wait for them -- and none of them is changed here. S-77: the
    # venue_bookings composite identifies them and tells their Coordinators.
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
    # S-77: a period's end is exclusive, so one ending at 00:00 on `from`
    # stopped the day before and is left out.
    _date_range(venue_id, from_date, to_date)
    operation = (
        db.schema(SCHEMA).table(BLOCKS).select("*")
        .eq("venue_id", str(venue_id))
        .lte("start_date", to_date.isoformat())
        .gte("end_date", from_date.isoformat())
    )
    range_start = datetime.combine(from_date, time())
    return [
        block for block in _execute(operation.order("start_date")).data
        if _block_end(block) > range_start
    ]


@app.get("/blocks/{block_id}", response_model=BlockRead)
def get_block(block_id: UUID, db: Client = Depends(get_db)):
    """S-77: one period, for the composite to work out its affected bookings
    again when Venue Staff retry the Coordinators' notifications. Internal,
    like the other reads: the composite checks the caller's role."""
    result = _execute(db.schema(SCHEMA).table(BLOCKS).select("*").eq("id", str(block_id)))
    if not result.data:
        raise HTTPException(status_code=404, detail="Block not found")
    return result.data[0]


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
