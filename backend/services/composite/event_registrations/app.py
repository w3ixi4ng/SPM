"""S-51: confirmed events' public pages, and Attendees registering for them.
S-48: each registration read back by its Attendee and by the event's Organiser.

Anyone may read a confirmed event's public details. Registering needs a
signed-in Attendee, an event that asks for registration, and a moment inside
its registration period. The period is Singapore wall-clock time, so "now"
is read in Singapore whatever the server's own clock says.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from clients import (
    get_bookings_client,
    get_events_client,
    get_now,
    get_registrations_client,
    get_users_client,
    get_venues_client,
)
from schemas import EventAttendees, MyRegistration, PublicEvent, RegistrationStatus

app = FastAPI(title="Event Registrations Service")
logger = logging.getLogger(__name__)

ATTENDEE_ROLE = "attendee"
SINGAPORE = timezone(timedelta(hours=8))
SIGN_IN_TO_REGISTER = "Sign in to register for this event."
ATTENDEES_ONLY = "Only attendee accounts can register for events."
NOT_REQUIRED = "This event doesn't need registration."
SIGN_IN_TO_SEE_ATTENDEES = "Sign in to see who has registered."


@app.exception_handler(RequestValidationError)
async def readable_validation_error(request: Request, exc: RequestValidationError):
    errors: dict[str, str] = {}
    for error in exc.errors():
        path = [str(part) for part in error["loc"] if part != "body"]
        errors.setdefault(".".join(path) or "body", error["msg"])
    return JSONResponse(
        status_code=422,
        content={"detail": "Please check the request", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    logger.exception("Unhandled event_registrations error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
@app.get("/event-registrations/health", include_in_schema=False)
def health():
    return {"status": "ok"}


def _unavailable(service: str) -> HTTPException:
    return HTTPException(status_code=502, detail=f"{service} service unavailable")


async def _call(service: str, send):
    try:
        return await send
    except httpx.HTTPError as exc:
        logger.exception("%s service unavailable", service, exc_info=exc)
        raise _unavailable(service) from exc


async def _json(service: str, send, *, identified: frozenset[int] = frozenset()):
    """The downstream body on 200; its own detail for the statuses the
    caller names; otherwise the service is treated as down."""
    response = await _call(service, send)
    if response.status_code in identified:
        detail = (response.json() or {}).get("detail", f"{service} request rejected")
        raise HTTPException(status_code=response.status_code, detail=detail)
    if response.status_code != 200:
        raise _unavailable(service)
    return response.json()


async def _attendee(request: Request, users: httpx.AsyncClient) -> dict:
    response = await _call("Users", users.get("/users/me", cookies=request.cookies))
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail=SIGN_IN_TO_REGISTER)
    if response.status_code != 200:
        raise _unavailable("Users")
    user = response.json()
    if user.get("role") != ATTENDEE_ROLE:
        raise HTTPException(status_code=403, detail=ATTENDEES_ONLY)
    return user


async def _published_event(event_id: UUID, events: httpx.AsyncClient) -> dict:
    return await _json(
        "Events",
        events.get(f"/internal/events/published/{event_id}"),
        identified=frozenset({404}),
    )


async def _venue_names(
    event_id: str, bookings: httpx.AsyncClient, venues: httpx.AsyncClient
) -> list[str]:
    rows = await _json("Bookings", bookings.get("/bookings", params={"event_id": event_id}))
    confirmed = [row for row in rows if row.get("status") == "confirmed"]
    found = await asyncio.gather(
        *(
            _json("Venues", venues.get(f'/internal/venues/{row["venue_id"]}'))
            for row in confirmed
        )
    )
    return list(dict.fromkeys(venue["name"] for venue in found))


async def _public(event: dict, bookings, venues) -> dict:
    return {**event, "venues": await _venue_names(str(event["id"]), bookings, venues)}


def _when(moment: datetime) -> str:
    """1 Nov 2026, 9:00 am -- the same wording the event page uses."""
    hour = moment.hour % 12 or 12
    meridiem = "am" if moment.hour < 12 else "pm"
    return f"{moment.day} {moment:%b %Y}, {hour}:{moment:%M} {meridiem}"


def _check_period(event: dict, now: datetime) -> None:
    """Refuse a registration outside the period. Opening is inclusive and
    closing exclusive: at the closing time itself registration is closed."""
    if not event.get("registration_required"):
        raise HTTPException(status_code=409, detail=NOT_REQUIRED)
    local_now = now.astimezone(SINGAPORE).replace(tzinfo=None)
    opens = datetime.fromisoformat(event["registration_opens_at"])
    closes = datetime.fromisoformat(event["registration_closes_at"])
    # S-48: a blocked attempt states the whole window, not only one end.
    window = f"from {_when(opens)} to {_when(closes)}"
    if local_now < opens:
        raise HTTPException(
            status_code=409, detail=f"Registration hasn't opened yet. It's open {window}."
        )
    if local_now >= closes:
        raise HTTPException(
            status_code=409, detail=f"Registration has closed. It was open {window}."
        )


@app.get("/event-registrations/events", response_model=list[PublicEvent])
async def list_public_events(
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
):
    rows = await _json("Events", events.get("/internal/events/published"))
    return await asyncio.gather(*(_public(row, bookings, venues) for row in rows))


@app.get("/event-registrations/events/{event_id}", response_model=PublicEvent)
async def get_public_event(
    event_id: UUID,
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
):
    event = await _published_event(event_id, events)
    return await _public(event, bookings, venues)


@app.post(
    "/event-registrations/events/{event_id}/registration",
    response_model=RegistrationStatus,
    status_code=201,
)
async def register(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
    now: datetime = Depends(get_now),
):
    user = await _attendee(request, users)
    event = await _published_event(event_id, events)
    _check_period(event, now)

    # The attendee is whoever the session says, never the request.
    response = await _call(
        "Registrations",
        registrations.post(
            "/registrations", json={"event_id": str(event_id), "attendee_id": user["id"]}
        ),
    )
    if response.status_code == 409:
        raise HTTPException(status_code=409, detail=response.json()["detail"])
    if response.status_code != 201:
        raise _unavailable("Registrations")
    row = response.json()
    return {"event_id": event_id, "registered": True, "registered_at": row["created_at"]}


@app.get(
    "/event-registrations/events/{event_id}/registration",
    response_model=RegistrationStatus,
)
async def get_my_registration(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
):
    user = await _attendee(request, users)
    response = await _call(
        "Registrations",
        registrations.get(f'/registrations/events/{event_id}/attendees/{user["id"]}'),
    )
    if response.status_code == 404:
        return {"event_id": event_id, "registered": False, "registered_at": None}
    if response.status_code != 200:
        raise _unavailable("Registrations")
    return {
        "event_id": event_id,
        "registered": True,
        "registered_at": response.json()["created_at"],
    }


async def _owned_event(event_id: UUID, request: Request, events: httpx.AsyncClient) -> None:
    """The events service decides ownership: it answers 404 for another
    Organiser's event and 403 for any other role."""
    response = await _call(
        "Events", events.get(f"/events/{event_id}", cookies=request.cookies)
    )
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail=SIGN_IN_TO_SEE_ATTENDEES)
    if response.status_code in (403, 404):
        detail = (response.json() or {}).get("detail", "Event not found")
        raise HTTPException(status_code=response.status_code, detail=detail)
    if response.status_code != 200:
        raise _unavailable("Events")


@app.get("/event-registrations/events/{event_id}/attendees", response_model=EventAttendees)
async def list_event_attendees(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
):
    await _owned_event(event_id, request, events)
    rows = await _json("Registrations", registrations.get(f"/registrations/events/{event_id}"))
    profiles = {}
    if rows:
        found = await _json(
            "Users",
            users.post(
                "/internal/users/profiles", json={"ids": [row["attendee_id"] for row in rows]}
            ),
        )
        profiles = {profile["id"]: profile for profile in found}
    attendees = [
        {
            "attendee_id": row["attendee_id"],
            "name": profiles.get(row["attendee_id"], {}).get("name"),
            "email": profiles.get(row["attendee_id"], {}).get("email"),
            "registered_at": row["created_at"],
        }
        for row in rows
    ]
    return {"event_id": event_id, "count": len(attendees), "attendees": attendees}


async def _still_public(event_id: str, events: httpx.AsyncClient) -> dict | None:
    """An event that is no longer confirmed drops out of the Attendee's list."""
    response = await _call("Events", events.get(f"/internal/events/published/{event_id}"))
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise _unavailable("Events")
    return response.json()


@app.get("/event-registrations/me/registrations", response_model=list[MyRegistration])
async def list_my_registrations(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
):
    user = await _attendee(request, users)
    rows = await _json("Registrations", registrations.get(f'/registrations/attendees/{user["id"]}'))
    found = await asyncio.gather(*(_still_public(row["event_id"], events) for row in rows))
    listed = [
        {**event, "event_id": event["id"], "registered_at": row["created_at"]}
        for row, event in zip(rows, found)
        if event is not None
    ]
    # Soonest event first; an event without dates yet sorts last.
    return sorted(
        listed,
        key=lambda item: (item["start_date"] or "9999-12-31", item["start_time"] or ""),
    )
