"""Composite service: venue booking requests (S-36).

A Coordinator's request spans four entities -- the Coordinator (users), the
event (events), the venue (venues) and the request itself (bookings) -- which
is why it lives here and not in any one atomic service. Owns no table; every
write ends up in ``bookings.bookings`` by way of the bookings service.
"""

import asyncio
import logging
from datetime import date
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import availability
import occupancy
import suitability
from clients import (
    INTERNAL_READ_TIMEOUT,
    get_bookings_client,
    get_events_client,
    get_users_client,
    get_venues_client,
)
from schemas import BlockRequest, VenueBookingRequest, BookingDecision

app = FastAPI(title="Venue Bookings Service")
logger = logging.getLogger(__name__)

COORDINATOR_ROLE = "event_coordinator"
VENUE_STAFF_ROLE = "venue_staff"
NOT_IN_PLANNING = "A venue can only be requested for an event in planning"
UNSUITABLE = "This venue can't take this booking"

# The bookings service's identified 409s: a slot taken by a confirmed booking
# (S-38) or a hold, or a day blocked by Venue Staff (S-30). These name only the
# venue, date and times, so they are safe to pass to the caller. S-76's refused
# approvals and holds also name the event in the way; only Venue Staff reach
# those routes. Any other 409 detail is not passed on.
CONFLICT_PHRASES = (
    " is already confirmed on ", " is already tentatively held on ", " is unavailable from ",
    "Can't confirm this booking: it overlaps ", "Can't hold this booking: it overlaps ",
)
INTERNAL_GET_ATTEMPTS = 3
INTERNAL_GET_BACKOFF = (0.5, 1.0)


def _identified_conflict(response) -> str | None:
    if response.status_code != status.HTTP_409_CONFLICT:
        return None
    detail = (response.json() or {}).get("detail", "")
    if isinstance(detail, str) and any(phrase in detail for phrase in CONFLICT_PHRASES):
        return detail
    return None


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
    logger.exception("Unhandled venue_bookings service error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@app.get("/health")
@app.get("/venue-bookings/health", include_in_schema=False)
def health():
    return {"status": "ok"}


def _unavailable(service: str) -> HTTPException:
    return HTTPException(status_code=502, detail=f"{service} service unavailable")


async def _call(service: str, send):
    """Awaits one downstream call, turning a connection failure into a 502
    that names the service rather than a 500 that names nothing."""
    try:
        return await send
    except httpx.HTTPError as exc:
        logger.exception("%s service unavailable", service, exc_info=exc)
        raise _unavailable(service) from exc


async def _get(service: str, client: httpx.AsyncClient, path: str, **kwargs):
    """Retry idempotent dependency reads on transport failures only.

    HTTP responses are returned unchanged so each caller retains its existing
    401/404/validation mapping. Writes continue through ``_call`` once and are
    never retried, avoiding duplicate bookings, decisions, holds, or blocks.
    """
    last_error: httpx.HTTPError | None = None
    for attempt in range(INTERNAL_GET_ATTEMPTS):
        try:
            return await client.get(
                path,
                timeout=INTERNAL_READ_TIMEOUT,
                **kwargs,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
            if attempt < INTERNAL_GET_ATTEMPTS - 1:
                logger.warning(
                    "%s GET %s failed on attempt %s/%s; retrying",
                    service,
                    path,
                    attempt + 1,
                    INTERNAL_GET_ATTEMPTS,
                )
                await asyncio.sleep(INTERNAL_GET_BACKOFF[attempt])

    logger.error(
        "%s service unavailable after %s GET attempts: %s",
        service,
        INTERNAL_GET_ATTEMPTS,
        last_error,
    )
    raise _unavailable(service) from last_error


async def _authenticate(request: Request, users: httpx.AsyncClient, *roles: str) -> dict:
    response = await _get("Users", users, "/users/me", cookies=request.cookies)
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Users")

    user = response.json()
    if user.get("role") not in roles:
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


async def _fetch(service: str, client: httpx.AsyncClient, path: str, cookies, not_found: str) -> dict:
    """GET one record with the caller's own session, so the owning service's
    access rules still apply -- the events service only returns an event
    assigned to this Coordinator."""
    response = await _get(service, client, path, cookies=cookies)
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail=not_found)
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable(service)
    return response.json()


def _booking_body(payload: VenueBookingRequest, user: dict, event: dict, venue: dict) -> dict:
    # A snapshot: Venue Staff assess what was asked at submission, even if
    # the event changes afterwards.
    return {
        **payload.model_dump(mode="json"),
        "coordinator_id": user["id"],
        "coordinator_name": user["name"],
        "coordinator_email": user["email"],
        "event_name": event["name"],
        "event_purpose": event["purpose"],
        "expected_attendance": event["expected_attendance"],
        "special_requirements": event.get("special_requirements"),
        "room_layout": event.get("room_layout"),
        "required_facilities": event.get("required_facilities") or [],
        "required_accessibility": event.get("required_accessibility") or [],
        "venue_name": venue["name"],
    }


def _today() -> date:
    """The composite's server date: S-75 clashes are checked from today on."""
    return date.today()


async def _booking_by_id(bookings: httpx.AsyncClient, booking_id) -> dict:
    response = await _get("Bookings", bookings, f"/bookings/{booking_id}")
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Booking not found")
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")
    return response.json()


async def _with_clashes(rows: list[dict], venues, bookings, cookies) -> list[dict]:
    """S-75: each row with the live clash warning for it -- `clashes: []` when
    there is none. Only held and confirmed bookings from today on are
    checked, against the other held/confirmed bookings at their venue that
    day, using the venue's current setup and turnaround. Read-only: nothing
    is ever changed because of a clash."""
    today = _today()
    checked = [
        row for row in rows
        if row.get("status") in occupancy.LIVE and date.fromisoformat(str(row["booking_date"])) >= today
    ]
    venues_by_id: dict[str, dict] = {}
    days: dict[tuple[str, str], list[dict]] = {}
    for row in checked:
        venue_id, day = str(row["venue_id"]), str(row["booking_date"])
        if venue_id not in venues_by_id:
            try:
                venues_by_id[venue_id] = await _fetch(
                    "Venues", venues, f"/venues/{venue_id}", cookies, "Venue not found"
                )
            except HTTPException as exc:
                # A request whose venue no longer exists is still listed, just
                # without a warning -- one bad row must not hide the others.
                # Any other failure still fails the list rather than hide a clash.
                if exc.status_code != status.HTTP_404_NOT_FOUND:
                    raise
                logger.warning("Booking %s refers to missing venue %s", row["id"], venue_id)
                venues_by_id[venue_id] = None
        if venues_by_id[venue_id] is not None and (venue_id, day) not in days:
            days[(venue_id, day)] = await _list(bookings, "/bookings", {"venue_id": venue_id, "from": day, "to": day})

    result = []
    for row in rows:
        venue = venues_by_id.get(str(row.get("venue_id")))
        if row not in checked or venue is None:
            result.append({**row, "clashes": []})
            continue
        same_day = days[(str(row["venue_id"]), str(row["booking_date"]))]
        result.append({
            **row,
            **occupancy.gap_params(venue),
            "clashes": occupancy.clashes_for(row, same_day, venue, today),
        })
    return result


@app.post("/venue-bookings", status_code=status.HTTP_201_CREATED)
async def submit_venue_booking(
    payload: VenueBookingRequest,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    user = await _authenticate(request, users, COORDINATOR_ROLE)

    event = await _fetch(
        "Events", events, f"/events/assigned/{payload.event_id}", request.cookies, "Event not found"
    )
    if event.get("status") != "planning":
        raise HTTPException(status_code=409, detail=NOT_IN_PLANNING)

    venue = await _fetch(
        "Venues", venues, f"/venues/{payload.venue_id}", request.cookies, "Venue not found"
    )

    problems = suitability.problems(payload, event, venue)
    if problems:
        return JSONResponse(status_code=422, content={"detail": UNSUITABLE, "errors": problems})

    # Read existing requests before writing so an identical retry is
    # idempotent and a successful replacement can release the old hold.
    previous_response = await _get(
        "Bookings", bookings, "/bookings", params={"event_id": str(payload.event_id)}
    )
    if previous_response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")
    previous_holds = [row for row in previous_response.json() if row.get("status") == "held"]

    def slot(row):
        return (
            str(row["venue_id"]),
            str(row["booking_date"]),
            str(row["start_time"])[:5],
            str(row["end_time"])[:5],
        )

    replacement_slot = slot(payload.model_dump(mode="json"))
    existing = next(
        (
            row for row in previous_response.json()
            if row.get("status") in ("pending", "held") and slot(row) == replacement_slot
        ),
        None,
    )
    if existing:
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=existing)

    body = _booking_body(payload, user, event, venue)
    # S-75: checked by the venue's current setup and turnaround.
    response = await _call("Bookings", bookings.post(
        "/bookings", json=body, params=occupancy.gap_params(venue),
    ))
    # S-30: the slot is held, booked or blocked -- say which, as the bookings
    # service worded it.
    conflict = _identified_conflict(response)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    if response.status_code != status.HTTP_201_CREATED:
        raise _unavailable("Bookings")
    created = response.json()
    for old in previous_holds:
        if slot(old) == replacement_slot:
            continue
        released = await _call("Bookings", bookings.post(
            f'/bookings/{old["id"]}/release',
            json={"reason": "booking_replaced"}, cookies=request.cookies,
        ))
        if released.status_code != status.HTTP_200_OK:
            raise _unavailable("Bookings")
    return created


@app.get("/venue-bookings")
async def list_venue_bookings_for_event(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """The requests sent for one event, every status, oldest first. The
    events lookup is what limits this to the Coordinator the event is
    assigned to -- the same check as submitting one."""
    await _authenticate(request, users, COORDINATOR_ROLE)
    await _fetch("Events", events, f"/events/assigned/{event_id}", request.cookies, "Event not found")

    response = await _get(
        "Bookings", bookings, "/bookings", params={"event_id": str(event_id)}
    )
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")
    # S-75: flagged for the assigned Coordinator.
    return await _with_clashes(response.json(), venues, bookings, request.cookies)


@app.get("/venue-bookings/pending")
async def list_pending_venue_bookings(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    # Every Venue Staff member sees every pending request -- no filter by
    # who added the venue.
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    response = await _get(
        "Bookings", bookings, "/bookings", params={"status": "actionable"}
    )
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")
    current = await _release_terminal_holds(response.json(), events, bookings, request.cookies)
    return await _with_clashes(current, venues, bookings, request.cookies)


@app.post("/venue-bookings/{booking_id}/hold")
async def hold_venue_booking(
    booking_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    gap = await _venue_gap(booking_id, venues, bookings, request.cookies)
    response = await _call(
        "Bookings", bookings.post(f"/bookings/{booking_id}/hold", params=gap, cookies=request.cookies)
    )
    if response.status_code == 200:
        return response.json()
    conflict = _identified_conflict(response)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    if response.status_code in (401, 403, 404, 409):
        raise HTTPException(status_code=response.status_code, detail=(response.json() or {}).get("detail"))
    raise _unavailable("Bookings")


@app.post("/venue-bookings/{booking_id}/release")
async def release_venue_booking(
    booking_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    response = await _call("Bookings", bookings.post(
        f"/bookings/{booking_id}/release",
        json={"reason": "staff_released"}, cookies=request.cookies,
    ))
    if response.status_code == 200:
        return response.json()
    if response.status_code in (401, 403, 404, 409):
        raise HTTPException(status_code=response.status_code, detail=(response.json() or {}).get("detail"))
    raise _unavailable("Bookings")


@app.post("/venue-bookings/{booking_id}/decision")
async def decide_venue_booking(
    booking_id: UUID,
    payload: BookingDecision,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    # Only a confirmation reserves time, so only it needs the venue's setup
    # and turnaround; a rejection never depends on reading the venue.
    gap = (
        await _venue_gap(booking_id, venues, bookings, request.cookies)
        if payload.decision == "approved" else {"setup_minutes": 0, "turnaround_minutes": 0}
    )
    response = await _call("Bookings", bookings.post(
        f"/bookings/{booking_id}/decision",
        json=payload.model_dump(mode="json"), params=gap, cookies=request.cookies,
    ))
    if response.status_code == 200:
        return response.json()
    conflict = _identified_conflict(response)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    messages = {
        401: "Not authenticated", 403: "Permission denied",
        404: "Booking not found",
        409: "This booking request has already been decided",
        422: "Please check the decision and provide a reason or alternative when rejecting",
    }
    if response.status_code in messages:
        raise HTTPException(status_code=response.status_code, detail=messages[response.status_code])
    raise _unavailable("Bookings")


async def _venue_gap(booking_id, venues, bookings, cookies) -> dict:
    """S-75: the setup and turnaround of the booking's venue, read now, so a
    hold or confirmation is checked by the saved values."""
    booking = await _booking_by_id(bookings, booking_id)
    venue = await _fetch("Venues", venues, f'/venues/{booking["venue_id"]}', cookies, "Venue not found")
    return occupancy.gap_params(venue)


async def _list(bookings: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
    response = await _get("Bookings", bookings, path, params=params)
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")
    return response.json()


async def _release_terminal_holds(rows, events, bookings, cookies):
    """Release a hold once Venue Staff observe that its authoritative event
    is rejected or cancelled. A dependency failure is conservative: the
    calendar/request list fails rather than claiming the slot is available."""
    current = []
    for row in rows:
        if row.get("status") != "held":
            current.append(row)
            continue
        event = await _get(
            "Events",
            events,
            f'/events/booking-status/{row["event_id"]}',
            cookies=cookies,
        )
        if event.status_code == 404:
            current.append(row)
            continue
        if event.status_code != 200:
            raise _unavailable("Events")
        event_status = event.json().get("status")
        if event_status not in ("rejected", "cancelled"):
            current.append(row)
            continue
        released = await _call("Bookings", bookings.post(
            f'/bookings/{row["id"]}/release',
            json={"reason": f"event_{event_status}"}, cookies=cookies,
        ))
        if released.status_code != 200:
            raise _unavailable("Bookings")
        # A terminal event must disappear from the actionable list as soon as
        # its hold is released; returning it as pending would allow re-holding
        # a rejected or cancelled event.
    return current


@app.get("/venue-bookings/availability")
async def venue_availability(
    venue_id: UUID,
    request: Request,
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-30: a venue's holds, confirmed bookings and blocks across a range.
    Failures are never an empty calendar, which would read as "available"."""
    user = await _authenticate(request, users, COORDINATOR_ROLE, VENUE_STAFF_ROLE)
    if to_date < from_date:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Please check the details you entered",
                "errors": {"to": "The end date must be on or after the start date"},
            },
        )

    venue = await _fetch("Venues", venues, f"/venues/{venue_id}", request.cookies, "Venue not found")
    params = {"venue_id": str(venue_id), "from": from_date.isoformat(), "to": to_date.isoformat()}
    booked = await _list(bookings, "/bookings", params)
    if user["role"] == VENUE_STAFF_ROLE:
        booked = await _release_terminal_holds(booked, events, bookings, request.cookies)
    blocked = await _list(bookings, "/blocks", params)

    return {
        "venue_id": venue["id"],
        "venue_name": venue["name"],
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "operating_hours": venue["operating_hours"],
        # S-75: so the calendar can show when the venue is in use.
        **occupancy.gap_params(venue),
        "entries": availability.entries(booked, blocked, staff=user["role"] == VENUE_STAFF_ROLE),
    }


BLOCK_MESSAGES = {401: "Not authenticated", 403: "Permission denied", 404: "Block not found"}


def _block_failure(response):
    """Maps the bookings service's answer for a block write. A 422 keeps its
    field errors; anything unexpected is a 502, never a false success."""
    if response.status_code == 422:
        return JSONResponse(status_code=422, content=response.json())
    if response.status_code in BLOCK_MESSAGES:
        raise HTTPException(status_code=response.status_code, detail=BLOCK_MESSAGES[response.status_code])
    raise _unavailable("Bookings")


@app.post("/venue-bookings/blocks", status_code=status.HTTP_201_CREATED)
async def add_venue_block(
    payload: BlockRequest,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-30: Venue Staff mark a venue unavailable. The bookings service checks
    the session again, so the cookies go with it."""
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    venue = await _fetch("Venues", venues, f"/venues/{payload.venue_id}", request.cookies, "Venue not found")

    body = {**payload.model_dump(mode="json"), "venue_name": venue["name"]}
    response = await _call("Bookings", bookings.post("/blocks", json=body, cookies=request.cookies))
    if response.status_code == status.HTTP_201_CREATED:
        return response.json()
    return _block_failure(response)


@app.delete(
    "/venue-bookings/blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_venue_block(
    block_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    response = await _call("Bookings", bookings.delete(f"/blocks/{block_id}", cookies=request.cookies))
    if response.status_code == status.HTTP_204_NO_CONTENT:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return _block_failure(response)


# --- S-75: clashes, and one request by id ------------------------------------
# Registered last: /venue-bookings/{booking_id} would otherwise read
# "pending", "availability" or "clashes" as an id.

# A booking date no request reaches: "from today on" with no end.
_FAR_FUTURE = "9999-12-31"


@app.get("/venue-bookings/clashes")
async def list_venue_clashes(
    request: Request,
    venue_id: UUID | None = None,
    users: httpx.AsyncClient = Depends(get_users_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-75: every pair of held/confirmed bookings at a venue, today on, that
    clash under its current setup and turnaround. Venue Staff see this right
    after changing the times. Read-only.

    S-76: with no venue, every venue's clashes -- the standing list Venue
    Staff review on their dashboard."""
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    if venue_id is None:
        return await _clashes_to_review(venues, bookings, request.cookies)
    venue = await _fetch("Venues", venues, f"/venues/{venue_id}", request.cookies, "Venue not found")
    rows = await _list(bookings, "/bookings", {
        "venue_id": str(venue_id), "from": _today().isoformat(), "to": _FAR_FUTURE,
    })
    return {
        "venue_id": venue["id"],
        "venue_name": venue["name"],
        **occupancy.gap_params(venue),
        "pairs": occupancy.clash_pairs(rows, venue, _today()),
    }


async def _clashes_to_review(venues, bookings, cookies) -> dict:
    """S-76: the venues with at least one clashing pair, by venue name, each
    with its current setup and turnaround. Worked out live like S-75's
    warnings: nothing is stored or changed. A booking whose venue no longer
    exists is skipped; a failing service fails the list rather than read as
    "no clashes"."""
    today = _today()
    listed = await _get("Venues", venues, "/venues", cookies=cookies)
    if listed.status_code != status.HTTP_200_OK:
        raise _unavailable("Venues")
    rows = await _list(bookings, "/bookings", {"status": "live", "from": today.isoformat()})

    by_venue: dict[str, list[dict]] = {}
    for row in rows:
        by_venue.setdefault(str(row["venue_id"]), []).append(row)
    flagged = []
    for venue in sorted(listed.json(), key=lambda venue: venue["name"]):
        pairs = occupancy.clash_pairs(by_venue.get(str(venue["id"]), []), venue, today)
        if pairs:
            flagged.append({
                "venue_id": venue["id"],
                "venue_name": venue["name"],
                **occupancy.gap_params(venue),
                "pairs": pairs,
            })
    return {"venues": flagged}


@app.get("/venue-bookings/{booking_id}")
async def get_venue_booking(
    booking_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-75: one request for its own page in the Venue Staff workspace, with
    its clash warning. Decided requests are returned too, so the page can say
    so."""
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    booking = await _booking_by_id(bookings, booking_id)
    [row] = await _with_clashes([booking], venues, bookings, request.cookies)
    return row

