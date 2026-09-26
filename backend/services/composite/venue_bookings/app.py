"""Composite service: venue booking requests (S-36).

A Coordinator's request spans four entities -- the Coordinator (users), the
event (events), the venue (venues) and the request itself (bookings) -- which
is why it lives here and not in any one atomic service. Owns no table; every
write ends up in ``bookings.bookings`` by way of the bookings service.
"""

import logging

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import suitability
from clients import get_bookings_client, get_events_client, get_users_client, get_venues_client
from schemas import VenueBookingRequest

app = FastAPI(title="Venue Bookings Service")
logger = logging.getLogger(__name__)

COORDINATOR_ROLE = "event_coordinator"
VENUE_STAFF_ROLE = "venue_staff"
NOT_IN_PLANNING = "A venue can only be requested for an event in planning"
UNSUITABLE = "This venue can't take this booking"


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


async def _authenticate(request: Request, users: httpx.AsyncClient, role: str) -> dict:
    response = await _call("Users", users.get("/users/me", cookies=request.cookies))
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Users")

    user = response.json()
    if user.get("role") != role:
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


async def _fetch(service: str, client: httpx.AsyncClient, path: str, cookies, not_found: str) -> dict:
    """GET one record with the caller's own session, so the owning service's
    access rules still apply -- the events service only returns an event
    assigned to this Coordinator."""
    response = await _call(service, client.get(path, cookies=cookies))
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
        "accessibility_requirements": event.get("accessibility_requirements"),
        "venue_name": venue["name"],
    }


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

    body = _booking_body(payload, user, event, venue)
    response = await _call("Bookings", bookings.post("/bookings", json=body))
    if response.status_code != status.HTTP_201_CREATED:
        raise _unavailable("Bookings")
    return response.json()


@app.get("/venue-bookings/pending")
async def list_pending_venue_bookings(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
):
    # Every Venue Staff member sees every pending request -- no filter by
    # who added the venue.
    await _authenticate(request, users, VENUE_STAFF_ROLE)
    response = await _call("Bookings", bookings.get("/bookings", params={"status": "pending"}))
    if response.status_code != status.HTTP_200_OK:
        raise _unavailable("Bookings")
    return response.json()
