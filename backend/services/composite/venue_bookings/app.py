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
import replacement
import suitability
import unavailability
from clients import (
    INTERNAL_READ_TIMEOUT,
    get_bookings_client,
    get_events_client,
    get_notifications_client,
    get_users_client,
    get_venues_client,
)
from schemas import (
    BlockRequest,
    BookingDecision,
    HoldRequest,
    ReplacementRequest,
    ResolutionRequest,
    RestoreDecision,
    VenueBookingChange,
    VenueBookingRequest,
    VenuePreparationRequest,
)

app = FastAPI(title="Venue Bookings Service")
logger = logging.getLogger(__name__)

COORDINATOR_ROLE = "event_coordinator"
ORGANISER_ROLE = "event_organiser"
VENUE_STAFF_ROLE = "venue_staff"
NOT_IN_PLANNING = "A venue can only be requested for an event in planning"
UNSUITABLE = "This venue can't take this booking"
# S-78
REPLACEMENT_NOT_NEEDED = "This booking doesn't need a replacement venue"
RESOLUTION_NOT_NEEDED = "This booking doesn't need alternative arrangements"
EVENT_CLOSED = "This event's venue bookings can no longer be changed"
REPLACEMENT_WAITING = "A replacement request for this booking is already with Venue Staff"
# S-90
RESTORE_NOT_OFFERED = "Restore is only possible while a replacement is waiting for Venue Staff."
# Venues checked at once by the S-78 replacement search.
SEARCH_CONCURRENCY = 6
CANNOT_REPLACE = "This booking can no longer be replaced"

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


def _slot_time(booking: dict, field: str) -> str:
    clock = str(booking[field])
    return f'{booking["booking_date"]}T{clock if len(clock) > 5 else clock + ":00"}'


def _venue_details(booking: dict, **extra) -> dict:
    return {"booking_id": str(booking["id"]), "venue_name": booking.get("venue_name"), **extra}


async def _record(events: httpx.AsyncClient, booking: dict, user: dict, action: str, details: dict) -> None:
    """S-82: add a venue action to its event's change history.

    Called only after the bookings service accepted the action. Best effort,
    by the developer's decision: the booking has already changed, so a failed
    entry is logged rather than reported as a failed action."""
    event_id = booking.get("event_id")
    entry = {"actor_id": user.get("id"), "actor_role": user.get("role"), "action": action, "details": details}
    try:
        response = await events.post(f"/internal/events/{event_id}/history", json=entry)
        if response.status_code != status.HTTP_201_CREATED:
            raise RuntimeError(f"Events answered {response.status_code}")
    except Exception as exc:
        logger.error("Could not record %s in the history of event %s", action, event_id, exc_info=exc)


async def _event_notification_scope(events: httpx.AsyncClient, event_id) -> dict:
    response = await _get(
        "Events", events, f"/internal/events/{event_id}/notification-scope"
    )
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Events")
    return response.json()


async def _notify_venue_decision(
    booking: dict,
    payload: BookingDecision,
    events: httpx.AsyncClient,
    notifications: httpx.AsyncClient,
) -> None:
    event = await _event_notification_scope(events, booking["event_id"])
    organiser_id = event["organiser_id"]
    venue_name = booking.get("venue_name") or "the requested venue"
    if payload.decision == "approved":
        message = (
            f"Venue booking confirmed for {event['name']}: {venue_name}. "
            "No action is required."
        )
    else:
        details = []
        if payload.reason:
            details.append(f"Reason: {payload.reason}.")
        if payload.alternative:
            details.append(f"Suggested alternative: {payload.alternative}.")
        message = (
            f"Venue booking rejected for {event['name']}: {venue_name}. "
            f"{' '.join(details)} Review the decision and work with your Event Coordinator "
            "to arrange another venue."
        )
    response = await _call("Notifications", notifications.post(
        "/internal/notifications", json={"notifications": [{
            "recipient_id": organiser_id,
            "event_id": str(booking["event_id"]),
            "event_name": event["name"],
            "kind": "venue_booking_decision",
            "message": message,
            "deduplication_key": (
                f"venue_booking_decision:{booking['id']}:{booking['status']}:"
                f"{booking.get('decided_at') or 'saved'}:{organiser_id}"
            ),
        }]}
    ))
    if response.status_code != status.HTTP_201_CREATED:
        raise _unavailable("Notifications")


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
    is ever changed because of a clash.

    S-77: each row also says whether an unavailable period at its venue
    affects it -- `requires_alternative_arrangements` and the
    `unavailable_periods` that do. Worked out the same live way, for the same
    rows; a period lookup that fails fails the read, never reads as "fine"."""
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

    blocks_by_venue: dict[str, list[dict]] = {}
    for venue_id in {str(row["venue_id"]) for row in checked}:
        if venues_by_id[venue_id] is None:
            continue
        dates = [str(row["booking_date"]) for row in checked if str(row["venue_id"]) == venue_id]
        blocks_by_venue[venue_id] = await _list(
            bookings, "/blocks", {"venue_id": venue_id, "from": min(dates), "to": max(dates)}
        )

    result = []
    for row in rows:
        venue = venues_by_id.get(str(row.get("venue_id")))
        if row not in checked or venue is None:
            result.append({**row, "clashes": [], **unavailability.flag(row, [], None)})
            continue
        same_day = days[(str(row["venue_id"]), str(row["booking_date"]))]
        result.append({
            **row,
            **occupancy.gap_params(venue),
            "clashes": occupancy.clashes_for(row, same_day, venue, today),
            **unavailability.flag(row, blocks_by_venue[str(row["venue_id"])], venue),
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
    # idempotent. S-79: an event may book several venues, so a new request
    # never replaces or releases the event's other bookings.
    previous_response = await _get(
        "Bookings", bookings, "/bookings", params={"event_id": str(payload.event_id)}
    )
    if previous_response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")

    def slot(row):
        return (
            str(row["venue_id"]),
            str(row["booking_date"]),
            str(row["start_time"])[:5],
            str(row["end_time"])[:5],
        )

    requested_slot = slot(payload.model_dump(mode="json"))
    existing = next(
        (
            row for row in previous_response.json()
            if row.get("status") in ("pending", "held") and slot(row) == requested_slot
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
    booking = response.json()
    await _record(events, booking, user, "venue_requested", _venue_details(
        booking, start=_slot_time(booking, "start_time"), end=_slot_time(booking, "end_time"),
    ))
    return booking


# S-80: what a Coordinator may change or cancel; a rejected request is closed.
CHANGEABLE_STATUSES = ("pending", "held", "confirmed")


async def _changeable_booking(booking_id, action, request, events, bookings) -> tuple[dict, dict]:
    """S-80: the booking, and its event -- read with the Coordinator's own
    session, so the events service only returns it if they are assigned.
    Refused unless the event is in planning and the booking is still open."""
    booking = await _booking_by_id(bookings, booking_id)
    event = await _fetch(
        "Events", events, f'/events/assigned/{booking["event_id"]}', request.cookies, "Event not found"
    )
    if event.get("status") != "planning":
        raise HTTPException(status_code=409, detail=NOT_IN_PLANNING)
    if booking["status"] not in CHANGEABLE_STATUSES:
        raise HTTPException(
            status_code=409, detail=f"Only a pending, held or confirmed booking can be {action}"
        )
    return booking, event


@app.patch("/venue-bookings/{booking_id}")
async def change_venue_booking(
    booking_id: UUID,
    payload: VenueBookingChange,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-80: move one booking of an event; its other bookings are untouched.
    Checked exactly like a new request, and back to pending for Venue Staff."""
    user = await _authenticate(request, users, COORDINATOR_ROLE)
    before, event = await _changeable_booking(booking_id, "changed", request, events, bookings)
    venue = await _fetch(
        "Venues", venues, f"/venues/{payload.venue_id}", request.cookies, "Venue not found"
    )
    problems = suitability.problems(payload, event, venue)
    if problems:
        return JSONResponse(status_code=422, content={"detail": UNSUITABLE, "errors": problems})

    response = await _call("Bookings", bookings.patch(
        f"/bookings/{booking_id}",
        json={**payload.model_dump(mode="json"), "venue_name": venue["name"]},
        params=occupancy.gap_params(venue),
        cookies=request.cookies,
    ))
    conflict = _identified_conflict(response)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")
    after = response.json()
    await _record(events, after, user, "venue_request_changed", _venue_details(
        after,
        **{"from": {"start": _slot_time(before, "start_time"), "end": _slot_time(before, "end_time"),
                    "venue_name": before.get("venue_name")},
           "to": {"start": _slot_time(after, "start_time"), "end": _slot_time(after, "end_time"),
                  "venue_name": after.get("venue_name")}},
    ))
    return after


@app.delete(
    "/venue-bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def cancel_venue_booking(
    booking_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-80: cancel one booking of an event. It is deleted, so its time is
    free; the event's other bookings are untouched."""
    user = await _authenticate(request, users, COORDINATOR_ROLE)
    booking, _ = await _changeable_booking(booking_id, "cancelled", request, events, bookings)
    response = await _call("Bookings", bookings.delete(
        f"/bookings/{booking_id}", cookies=request.cookies,
    ))
    if response.status_code != status.HTTP_204_NO_CONTENT:
        raise _unavailable("Bookings")
    await _record(events, booking, user, "venue_request_withdrawn", _venue_details(booking))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/venue-bookings/{booking_id}/primary")
async def select_primary_venue_booking(
    booking_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-91: only the Coordinator assigned to this booking's event chooses
    which confirmed venue Attendees see."""
    await _authenticate(request, users, COORDINATOR_ROLE)
    booking = await _booking_by_id(bookings, booking_id)
    await _fetch(
        "Events", events, f'/events/assigned/{booking["event_id"]}',
        request.cookies, "Event not found",
    )
    response = await _call("Bookings", bookings.put(
        f"/bookings/{booking_id}/primary", cookies=request.cookies,
    ))
    if response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT):
        raise HTTPException(
            status_code=response.status_code,
            detail=(response.json() or {}).get("detail", "Primary venue could not be selected"),
        )
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")
    return response.json()


@app.get("/venue-bookings")
async def list_venue_bookings_for_event(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """Every venue for one event. Its assigned Coordinator and owning
    Organiser see the complete set; attendee routes use their own filtered
    projection in event_registrations."""
    user = await _authenticate(request, users, COORDINATOR_ROLE, ORGANISER_ROLE)
    event_path = (
        f"/events/assigned/{event_id}"
        if user["role"] == COORDINATOR_ROLE
        else f"/events/{event_id}"
    )
    await _fetch("Events", events, event_path, request.cookies, "Event not found")

    response = await _get(
        "Bookings", bookings, "/bookings", params={"event_id": str(event_id)}
    )
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")
    # S-75 warnings are Coordinator work. The Organiser gets the same venue
    # rows and primary marker without internal clash controls.
    if user["role"] == ORGANISER_ROLE:
        return response.json()
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


@app.get("/venue-bookings/preparation")
async def list_venue_preparation_bookings(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-25: confirmed bookings whose event is currently in Preparation."""
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    response = await _get("Bookings", bookings, "/bookings", params={"status": "confirmed"})
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")

    async def in_preparation(row):
        event = await _get(
            "Events", events, f'/events/booking-status/{row["event_id"]}',
            cookies=request.cookies,
        )
        if event.status_code == status.HTTP_404_NOT_FOUND:
            return None
        if event.status_code != status.HTTP_200_OK:
            raise _unavailable("Events")
        return {**row, "event_status": event.json().get("status")} if event.json().get("status") == "preparation" else None

    rows = await asyncio.gather(*(in_preparation(row) for row in response.json()))
    return [row for row in rows if row is not None]


@app.put("/venue-bookings/{booking_id}/preparation")
async def update_venue_preparation(
    booking_id: UUID,
    payload: VenuePreparationRequest,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    booking = await _booking_by_id(bookings, booking_id)
    if booking.get("status") != "confirmed":
        raise HTTPException(status_code=409, detail="Only a confirmed venue booking can be prepared")

    event = await _get(
        "Events", events, f'/events/booking-status/{booking["event_id"]}',
        cookies=request.cookies,
    )
    if event.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status_code != status.HTTP_200_OK:
        raise _unavailable("Events")
    if event.json().get("status") != "preparation":
        raise HTTPException(
            status_code=409,
            detail="Venue preparation can only be updated while the event is in preparation",
        )

    response = await _call("Bookings", bookings.put(
        f"/bookings/{booking_id}/venue-preparation",
        json=payload.model_dump(mode="json"), cookies=request.cookies,
    ))
    if response.status_code == status.HTTP_200_OK:
        return response.json()
    if response.status_code in (401, 403, 404, 409, 422):
        raise HTTPException(
            status_code=response.status_code,
            detail=(response.json() or {}).get("detail", "Venue preparation was not updated"),
        )
    raise _unavailable("Bookings")


@app.post("/venue-bookings/{booking_id}/hold")
async def hold_venue_booking(
    booking_id: UUID,
    request: Request,
    payload: HoldRequest | None = None,
    users: httpx.AsyncClient = Depends(get_users_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    staff = await _authenticate(request, users, VENUE_STAFF_ROLE)
    gap = await _venue_gap(booking_id, venues, bookings, request.cookies)
    if payload is None:
        return JSONResponse(
            status_code=422,
            content={"detail": "Please check the details you entered", "errors": {"expires_at": "Field required"}},
        )
    response = await _call(
        "Bookings", bookings.post(
            f"/bookings/{booking_id}/hold", params=gap,
            json=payload.model_dump(mode="json"), cookies=request.cookies,
        )
    )
    if response.status_code == 200:
        held = response.json()
        notice = {
            "recipient_id": held["coordinator_id"],
            "event_id": held["event_id"],
            "event_name": held["event_name"],
            "kind": "venue_hold_expiry",
            "message": (
                f'The tentative hold for {held["venue_name"]} on '
                f'{held["booking_date"]} from {str(held["start_time"])[:5]} '
                f'to {str(held["end_time"])[:5]} will expire at '
                f'{held["hold_expires_at"]} if it is not confirmed.'
            ),
            "deduplication_key": (
                f'venue_hold_expiry:{held["id"]}:{held["hold_expires_at"]}'
            ),
        }
        notified = await _call("Notifications", notifications.post(
            "/internal/notifications", json={"notifications": [notice]},
        ))
        if notified.status_code != status.HTTP_201_CREATED:
            logger.warning("Hold %s saved but its expiry notice could not be sent", held["id"])
        await _record(events, held, staff, "venue_held", _venue_details(held))
        return held
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
    events: httpx.AsyncClient = Depends(get_events_client),
):
    staff = await _authenticate(request, users, VENUE_STAFF_ROLE)
    response = await _call("Bookings", bookings.post(
        f"/bookings/{booking_id}/release",
        json={"reason": "staff_released"}, cookies=request.cookies,
    ))
    if response.status_code == 200:
        released = response.json()
        await _record(events, released, staff, "venue_released", _venue_details(released))
        return released
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
    events: httpx.AsyncClient = Depends(get_events_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
):
    staff = await _authenticate(request, users, VENUE_STAFF_ROLE)
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
        decided = response.json()
        action = "venue_confirmed" if payload.decision == "approved" else "venue_rejected"
        await _record(events, decided, staff, action, _venue_details(
            decided, reason=payload.reason, alternative=payload.alternative,
        ))
        await _notify_venue_decision(decided, payload, events, notifications)
        return decided
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


async def _affected(block: dict, venue: dict, bookings) -> list[dict]:
    """S-77: the held and confirmed bookings the period affects, read now."""
    rows = await _list(bookings, "/bookings", {
        "status": "live", "from": str(block["start_date"]), "venue_id": str(block["venue_id"]),
    })
    return unavailability.affected_bookings(rows, block, venue)


async def _notify(block: dict, affected: list[dict], events, notifications) -> bool:
    """S-77: tell each affected event's current Coordinator. The period is
    already saved, so a failure here is reported as `False`, never undone:
    Venue Staff retry, and the deduplication keys mean nobody is told twice."""
    if not affected:
        return True
    try:
        response = await _get("Events", events, "/internal/events/assigned-active")
        if response.status_code != status.HTTP_200_OK:
            return False
        current = {str(event["id"]): event for event in response.json()}
        rows = unavailability.notifications(block, affected, current)
        for batch in unavailability.batches(rows):
            sent = await _call("Notifications", notifications.post(
                "/internal/notifications", json={"notifications": batch},
            ))
            if sent.status_code != status.HTTP_201_CREATED:
                return False
    except HTTPException:
        return False
    return True


async def _identify_and_notify(block: dict, venue: dict, bookings, events, notifications) -> dict:
    affected = await _affected(block, venue, bookings)
    return {
        "affected_bookings": affected,
        "coordinators_notified": await _notify(block, affected, events, notifications),
    }


@app.post("/venue-bookings/blocks", status_code=status.HTTP_201_CREATED)
async def add_venue_block(
    payload: BlockRequest,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
):
    """S-30: Venue Staff mark a venue unavailable. The bookings service checks
    the session again, so the cookies go with it.

    S-77: the response also names the bookings the period affects, and says
    whether their Coordinators were told. Nothing about those bookings or
    their events is changed."""
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    venue = await _fetch("Venues", venues, f"/venues/{payload.venue_id}", request.cookies, "Venue not found")

    body = {**payload.model_dump(mode="json"), "venue_name": venue["name"]}
    response = await _call("Bookings", bookings.post("/blocks", json=body, cookies=request.cookies))
    if response.status_code != status.HTTP_201_CREATED:
        return _block_failure(response)
    block = response.json()
    try:
        outcome = await _identify_and_notify(block, venue, bookings, events, notifications)
    except HTTPException:
        # The period is saved, so this is still a 201. Which bookings it
        # affects is unknown rather than "none"; the retry works it out.
        logger.warning("Could not identify the bookings block %s affects", block["id"])
        outcome = {"affected_bookings": None, "coordinators_notified": False}
    return {**block, **outcome}


@app.post("/venue-bookings/blocks/{block_id}/notify")
async def notify_venue_block(
    block_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
):
    """S-77: Venue Staff retry telling the Coordinators of the bookings a
    period affects, worked out again from current data."""
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    response = await _get("Bookings", bookings, f"/blocks/{block_id}")
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Block not found")
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")
    block = response.json()
    venue = await _fetch("Venues", venues, f'/venues/{block["venue_id"]}', request.cookies, "Venue not found")
    return await _identify_and_notify(block, venue, bookings, events, notifications)


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


# --- S-78: replacing an affected booking ---------------------------------------


async def _affected_booking(
    booking_id, request: Request, users, events, venues, bookings, not_needed: str,
    *, rejected_too: bool = False,
):
    """The caller, the booking and its event, once the caller is the event's
    current Coordinator and the booking carries S-77's flag -- or, with
    `rejected_too` (S-17), was rejected by Venue Staff. A booking whose event
    isn't the caller's is the same 404 as one that doesn't exist."""
    user = await _authenticate(request, users, COORDINATOR_ROLE)
    booking = await _booking_by_id(bookings, booking_id)
    event = await _fetch(
        "Events", events, f'/events/assigned/{booking["event_id"]}', request.cookies, "Booking not found"
    )
    if event.get("status") not in replacement.OPEN_EVENT_STATUSES:
        raise HTTPException(status_code=409, detail=EVENT_CLOSED)
    if rejected_too and booking.get("status") == "rejected":
        return user, booking, event
    [flagged] = await _with_clashes([booking], venues, bookings, request.cookies)
    if not flagged["requires_alternative_arrangements"]:
        raise HTTPException(status_code=409, detail=not_needed)
    return user, booking, event


@app.get("/venue-bookings/{booking_id}/replacement-venues")
async def search_replacement_venues(
    booking_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-78: the venues that could take the affected booking's event at its
    date and times, by name. A failed read is a 502, never "no venues"."""
    _, booking, event = await _affected_booking(
        booking_id, request, users, events, venues, bookings, REPLACEMENT_NOT_NEEDED,
        rejected_too=True,
    )
    listed = await _get("Venues", venues, "/venues", cookies=request.cookies)
    if listed.status_code != status.HTTP_200_OK:
        raise _unavailable("Venues")

    day = str(booking["booking_date"])
    candidates = [
        venue for venue in sorted(listed.json(), key=lambda venue: venue["name"])
        if str(venue["id"]) != str(booking["venue_id"]) and replacement.suitable(booking, event, venue)
    ]
    # Each venue costs two Bookings reads, so they are checked a few at a time
    # rather than one after another -- in sequence, a dozen suitable venues
    # kept the Coordinator waiting over 20 seconds.
    gate = asyncio.Semaphore(SEARCH_CONCURRENCY)

    async def free(venue):
        params = {"venue_id": str(venue["id"]), "from": day, "to": day}
        async with gate:
            same_day, blocks = await asyncio.gather(
                _list(bookings, "/bookings", params), _list(bookings, "/blocks", params),
            )
        return replacement.available(booking, venue, same_day, blocks)

    checked = await asyncio.gather(*(free(venue) for venue in candidates))
    offered = [venue for venue, ok in zip(candidates, checked) if ok]
    return {"booking": replacement.summary(booking), "venues": offered}


@app.post("/venue-bookings/{booking_id}/replacement", status_code=status.HTTP_201_CREATED)
async def request_replacement_venue(
    booking_id: UUID,
    payload: ReplacementRequest,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-78: a request for another venue, linked to the affected booking and
    for its event, date and times. The event's details are copied in as for
    any request (S-36), so nothing is typed in again. The original keeps its
    flag until Venue Staff approve this."""
    user, original, event = await _affected_booking(
        booking_id, request, users, events, venues, bookings, REPLACEMENT_NOT_NEEDED,
        rejected_too=True,
    )
    event_bookings = await _list(bookings, "/bookings", {"event_id": str(original["event_id"])})
    waiting = replacement.active_replacement(original, event_bookings)
    if waiting:
        # The same venue again is a retry, not a second request.
        if str(waiting["venue_id"]) == str(payload.venue_id):
            return JSONResponse(status_code=status.HTTP_201_CREATED, content=waiting)
        raise HTTPException(status_code=409, detail=REPLACEMENT_WAITING)

    venue = await _fetch("Venues", venues, f"/venues/{payload.venue_id}", request.cookies, "Venue not found")
    asked = VenueBookingRequest(
        event_id=original["event_id"],
        venue_id=payload.venue_id,
        booking_date=original["booking_date"],
        start_time=original["start_time"],
        end_time=original["end_time"],
        notes=payload.notes,
    )
    problems = suitability.problems(asked, event, venue)
    if problems:
        return JSONResponse(status_code=422, content={"detail": UNSUITABLE, "errors": problems})

    body = {**_booking_body(asked, user, event, venue), "replaces_booking_id": str(original["id"])}
    response = await _call("Bookings", bookings.post(
        "/bookings", json=body, params=occupancy.gap_params(venue),
    ))
    conflict = _identified_conflict(response)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    if response.status_code == status.HTTP_409_CONFLICT and (response.json() or {}).get("detail") == CANNOT_REPLACE:
        raise HTTPException(status_code=409, detail=CANNOT_REPLACE)
    if response.status_code != status.HTTP_201_CREATED:
        raise _unavailable("Bookings")
    created = response.json()
    await _record(events, created, user, "venue_replacement_requested", _venue_details(
        created, replaces_booking_id=str(original["id"]), replaced_venue_name=original.get("venue_name"),
    ))
    return created


@app.post("/venue-bookings/{booking_id}/resolution")
async def resolve_alternative_arrangements(
    booking_id: UUID,
    payload: ResolutionRequest,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-78: the Coordinator says what they arranged instead. The booking is
    not changed, and a replacement already sent stays with Venue Staff; the
    flag ignores the periods this resolves."""
    user, _, _ = await _affected_booking(
        booking_id, request, users, events, venues, bookings, RESOLUTION_NOT_NEEDED,
    )
    response = await _call("Bookings", bookings.post(
        f"/bookings/{booking_id}/alternative-resolution",
        json=payload.model_dump(), cookies=request.cookies,
    ))
    if response.status_code == status.HTTP_200_OK:
        resolved = response.json()
        await _record(events, resolved, user, "venue_alternative_resolved", _venue_details(resolved))
        return resolved
    if response.status_code in (401, 403, 404, 409):
        raise HTTPException(status_code=response.status_code, detail=(response.json() or {}).get("detail"))
    raise _unavailable("Bookings")


async def _replaces(booking: dict, bookings) -> dict | None:
    """S-78: for Venue Staff, which booking a replacement request replaces."""
    if not booking.get("replaces_booking_id"):
        return None
    try:
        original = await _booking_by_id(bookings, booking["replaces_booking_id"])
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise
        return None
    return {**replacement.summary(original), "status": original["status"]}


# --- S-90: restoring the original booking ------------------------------------


def _passed_on(response: httpx.Response) -> HTTPException | None:
    """The bookings service's own refusal -- the venue isn't free, or there is
    nothing to restore -- in its own words."""
    if response.status_code in (401, 403, 404, 409):
        return HTTPException(
            status_code=response.status_code, detail=(response.json() or {}).get("detail")
        )
    return None


@app.post("/venue-bookings/{booking_id}/restore")
async def request_restore(
    booking_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-90: the event's Coordinator asks to keep the original booking. Only
    while its replacement (S-78) still waits for Venue Staff; the bookings
    service then checks the original venue is free for the whole window it
    occupies, by its current setup and turnaround. Nothing changes until
    Venue Staff confirm."""
    user = await _authenticate(request, users, COORDINATOR_ROLE)
    original = await _booking_by_id(bookings, booking_id)
    event = await _fetch(
        "Events", events, f'/events/assigned/{original["event_id"]}', request.cookies, "Booking not found"
    )
    if event.get("status") not in replacement.OPEN_EVENT_STATUSES:
        raise HTTPException(status_code=409, detail=EVENT_CLOSED)
    event_bookings = await _list(bookings, "/bookings", {"event_id": str(original["event_id"])})
    waiting = replacement.active_replacement(original, event_bookings)
    if original.get("status") not in occupancy.LIVE or waiting is None:
        raise HTTPException(status_code=409, detail=RESTORE_NOT_OFFERED)

    venue = await _fetch("Venues", venues, f'/venues/{original["venue_id"]}', request.cookies, "Venue not found")
    response = await _call("Bookings", bookings.post(
        f"/bookings/{booking_id}/restore-request",
        params=occupancy.gap_params(venue), cookies=request.cookies,
    ))
    if response.status_code == status.HTTP_200_OK:
        requested = response.json()
        await _record(events, requested, user, "venue_restore_requested", _venue_details(
            requested, replacement_venue_name=waiting.get("venue_name"),
        ))
        return requested
    refused = _passed_on(response)
    if refused:
        raise refused
    raise _unavailable("Bookings")


@app.get("/venue-bookings/restores")
async def list_restore_requests(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-90: for Venue Staff, each open restore request with the replacement
    confirming it would withdraw."""
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    requested = await _list(bookings, "/bookings", {"restore_requested": "true"})

    async def with_replacement(original: dict) -> dict:
        event_bookings = await _list(bookings, "/bookings", {"event_id": str(original["event_id"])})
        waiting = replacement.active_replacement(original, event_bookings)
        summary = {**replacement.summary(waiting), "status": waiting["status"]} if waiting else None
        return {**original, "replacement": summary}

    return await asyncio.gather(*(with_replacement(row) for row in requested))


@app.post("/venue-bookings/{booking_id}/restore-decision")
async def decide_restore(
    booking_id: UUID,
    payload: RestoreDecision,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    """S-90: Venue Staff confirm or decline. Confirming is checked again by
    the venue's current setup and turnaround; the bookings service then
    withdraws the replacement and resolves the original's flag."""
    staff = await _authenticate(request, users, VENUE_STAFF_ROLE)
    gap = (
        await _venue_gap(booking_id, venues, bookings, request.cookies)
        if payload.decision == "approved" else {"setup_minutes": 0, "turnaround_minutes": 0}
    )
    response = await _call("Bookings", bookings.post(
        f"/bookings/{booking_id}/restore-decision",
        json=payload.model_dump(), params=gap, cookies=request.cookies,
    ))
    if response.status_code == status.HTTP_200_OK:
        outcome = response.json()
        withdrawn = outcome.get("withdrawn") or []
        action = "venue_restore_confirmed" if payload.decision == "approved" else "venue_restore_declined"
        await _record(events, outcome["booking"], staff, action, _venue_details(
            outcome["booking"],
            replacement_venue_name=withdrawn[0].get("venue_name") if withdrawn else None,
        ))
        return outcome
    refused = _passed_on(response)
    if refused:
        raise refused
    raise _unavailable("Bookings")


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
    return {**row, "replaces": await _replaces(booking, bookings)}

