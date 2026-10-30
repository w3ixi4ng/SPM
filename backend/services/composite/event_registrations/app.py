"""S-51: confirmed events' public pages, and Attendees registering for them.
S-48: each registration read back by its Attendee and by the event's Organiser.
S-49: a recorded registration sends the Attendee an in-app confirmation.
S-50: registration capped at the event's expected attendance -- the figure the
S-35 venue check uses -- with a waiting list once it is full, and the
Organiser's own decision to close registration early.
S-53: an Attendee withdraws until the event starts.
S-55: a freed place is offered to whoever has waited longest -- held for them,
never given -- and they take it or pass it on themselves.

Anyone may read a confirmed event's public details. Registering needs a
signed-in Attendee, an event that asks for registration, and a moment inside
its registration period. The period is Singapore wall-clock time, so "now"
is read in Singapore whatever the server's own clock says.
"""

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from clients import (
    get_bookings_client,
    get_events_client,
    get_notifications_client,
    get_now,
    get_registrations_client,
    get_users_client,
    get_venues_client,
)
from schemas import (
    EventAttendees,
    MyRegistration,
    PublicEvent,
    RegistrationStatus,
    WaitingListStatus,
)

app = FastAPI(title="Event Registrations Service")
logger = logging.getLogger(__name__)

ATTENDEE_ROLE = "attendee"
SINGAPORE = timezone(timedelta(hours=8))
SIGN_IN_TO_REGISTER = "Sign in to register for this event."
ATTENDEES_ONLY = "Only attendee accounts can register for events."
NOT_REQUIRED = "This event doesn't need registration."
SIGN_IN_TO_SEE_ATTENDEES = "Sign in to see who has registered."
# S-50
FULL = "This event is full. You can join the waiting list."
CLOSED_BY_ORGANISER = "The organiser has closed registration for this event."
STILL_HAS_PLACES = "This event still has places. Register instead."
ALREADY_REGISTERED = "You're already registered for this event."
# The registrations service's own word for a full event.
REGISTRATIONS_FULL = "This event is full."
# S-53
SIGN_IN_TO_WITHDRAW = "Sign in to withdraw your registration."
ALREADY_STARTED = "This event has already started. You can no longer withdraw."
NOT_REGISTERED = "You're not registered for this event."
# S-55
SIGN_IN_TO_RESPOND = "Sign in to respond to this offer."
OFFER_STARTED = "This event has already started. The place can no longer be taken."
NO_OFFER = "You don't have a place on offer for this event."


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


async def _attendee(
    request: Request, users: httpx.AsyncClient, *, signed_out: str = SIGN_IN_TO_REGISTER
) -> dict:
    response = await _call("Users", users.get("/users/me", cookies=request.cookies))
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail=signed_out)
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
    # S-91: public/Attendee projections expose only the deliberate primary,
    # never secondary operational venues.
    confirmed = [
        row for row in rows
        if row.get("status") == "confirmed" and row.get("is_primary") is True
    ]
    found = await asyncio.gather(
        *(
            _json("Venues", venues.get(f'/internal/venues/{row["venue_id"]}'))
            for row in confirmed
        )
    )
    return list(dict.fromkeys(venue["name"] for venue in found))


async def _places_taken(event_id: str, registrations: httpx.AsyncClient) -> int:
    """Places held plus, S-55, places held open for an invited Attendee: an
    offered place is no more free to others than a taken one."""
    rows, waiting = await asyncio.gather(
        _json("Registrations", registrations.get(f"/registrations/events/{event_id}")),
        _json("Registrations", registrations.get(f"/registrations/waiting-list/events/{event_id}")),
    )
    return len(rows) + sum(1 for row in waiting if row.get("offered_at"))


def _is_full(event: dict, taken: int) -> bool:
    capacity = event.get("expected_attendance")
    return bool(capacity) and taken >= capacity


async def _public(event: dict, bookings, venues, registrations) -> dict:
    event_id = str(event["id"])
    full = False
    if event.get("registration_required"):
        full = _is_full(event, await _places_taken(event_id, registrations))
    return {
        **event,
        "venues": await _venue_names(event_id, bookings, venues),
        "registration_closed_by_organiser": bool(event.get("registration_closed_at")),
        "is_full": full,
    }


def _day(moment: date) -> str:
    return f"{moment.day} {moment:%b %Y}"


def _clock(moment: time) -> str:
    hour = moment.hour % 12 or 12
    meridiem = "am" if moment.hour < 12 else "pm"
    return f"{hour}:{moment:%M} {meridiem}"


def _when(moment: datetime) -> str:
    """1 Nov 2026, 9:00 am -- the same wording the event page uses."""
    return f"{_day(moment)}, {_clock(moment)}"


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
    # S-50: inside the period, the Organiser's own close comes next.
    if event.get("registration_closed_at"):
        raise HTTPException(status_code=409, detail=CLOSED_BY_ORGANISER)


def _event_summary(event: dict, venues: list[str]) -> str:
    """The event, its date and time, and its venue, in the S-49 wording."""
    start_date = date.fromisoformat(event["start_date"])
    end_date = date.fromisoformat(event["end_date"])
    starts = f"{_day(start_date)}, {_clock(time.fromisoformat(event['start_time']))}"
    ends = _clock(time.fromisoformat(event["end_time"]))
    if end_date != start_date:
        ends = f"{_day(end_date)}, {ends}"
    where = f"at {', '.join(venues)}" if venues else "venue to be confirmed"
    return f"{event['name']}, {starts} – {ends}, {where}"


def _confirmation(event: dict, venues: list[str], user: dict) -> str:
    """S-49: the event and the Attendee's entry details, name and email."""
    return (
        f"Registration confirmed: {_event_summary(event, venues)}. "
        f"Name: {user['name']}. Email: {user['email']}."
    )


def _offer(event: dict, venues: list[str], user: dict) -> str:
    """S-55: an invitation, not a registration -- the place is only held."""
    return (
        f"A place opened up at {_event_summary(event, venues)}. "
        "It's held for you: accept it on the event page to register."
    )


# Each notification an Attendee is sent about a place: its kind and wording.
CONFIRMATION = ("registration_confirmation", _confirmation)
# S-55: a freed place is held for this Attendee. Keyed by their waiting-list
# entry, which is only ever offered a place once.
OFFER = ("waiting_list_offer", _offer)


async def _send_notice(
    notice, event: dict, user: dict, row: dict, bookings, venues, notifications,
) -> None:
    """Best effort: the place is already recorded, so a notice that can't be
    built or stored is logged rather than failing the request that made it."""
    kind, wording = notice
    try:
        names = await _venue_names(str(event["id"]), bookings, venues)
        notification = {
            "recipient_id": user["id"],
            "event_id": str(event["id"]),
            "event_name": event["name"],
            "kind": kind,
            "message": wording(event, names, user),
            "deduplication_key": f"{kind}:{row['id']}",
        }
        response = await notifications.post(
            "/internal/notifications", json={"notifications": [notification]}
        )
        if response.status_code != 201:
            logger.error("%s not stored for %s: %s", kind, row["id"], response.status_code)
    except Exception as exc:
        logger.exception("%s not sent for %s", kind, row["id"], exc_info=exc)


@app.get("/event-registrations/events", response_model=list[PublicEvent])
async def list_public_events(
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
):
    rows = await _json("Events", events.get("/internal/events/published"))
    return await asyncio.gather(
        *(_public(row, bookings, venues, registrations) for row in rows)
    )


@app.get("/event-registrations/events/{event_id}", response_model=PublicEvent)
async def get_public_event(
    event_id: UUID,
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
):
    event = await _published_event(event_id, events)
    return await _public(event, bookings, venues, registrations)


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
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
    now: datetime = Depends(get_now),
):
    user = await _attendee(request, users)
    event = await _published_event(event_id, events)
    _check_period(event, now)

    # The attendee is whoever the session says, never the request. S-50: the
    # cap is the event's expected attendance; the registrations service
    # counts and inserts in one step so the last place goes to one person.
    response = await _call(
        "Registrations",
        registrations.post(
            "/registrations",
            json={
                "event_id": str(event_id),
                "attendee_id": user["id"],
                "capacity": event["expected_attendance"],
            },
        ),
    )
    if response.status_code == 409:
        detail = response.json()["detail"]
        raise HTTPException(
            status_code=409, detail=FULL if detail == REGISTRATIONS_FULL else detail
        )
    if response.status_code != 201:
        raise _unavailable("Registrations")
    row = response.json()
    # S-49: only reached once the place is recorded, so a refused or failed
    # registration never sends a confirmation.
    await _send_notice(CONFIRMATION, event, user, row, bookings, venues, notifications)
    return {"event_id": event_id, "registered": True, "registered_at": row["created_at"]}


def _has_started(event: dict, now: datetime) -> bool:
    """S-53: the event's start, Singapore wall-clock time. An event without a
    start yet hasn't started."""
    if not event.get("start_date") or not event.get("start_time"):
        return False
    starts = datetime.combine(
        date.fromisoformat(event["start_date"]), time.fromisoformat(event["start_time"])
    )
    return now.astimezone(SINGAPORE).replace(tzinfo=None) >= starts


async def _profile(user_id: str, users: httpx.AsyncClient) -> dict:
    found = await _json("Users", users.post("/internal/users/profiles", json={"ids": [user_id]}))
    return found[0]


async def _invite(
    offered: dict | None, event: dict, users, bookings, venues, notifications
) -> None:
    """S-55: tell the Attendee a freed place is held for them. Best effort, as
    the offer is already recorded."""
    if not offered:
        return
    try:
        profile = await _profile(offered["attendee_id"], users)
    except Exception as exc:
        logger.exception("waiting_list_offer not sent for %s", offered["id"], exc_info=exc)
        return
    await _send_notice(OFFER, event, profile, offered, bookings, venues, notifications)


@app.delete(
    "/event-registrations/events/{event_id}/registration",
    response_model=RegistrationStatus,
)
async def withdraw(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
    now: datetime = Depends(get_now),
):
    """S-53: open until the event starts, whether or not registration still
    is. S-55: the registrations service offers the freed place to the next
    Attendee waiting in the same step, capped at the event's expected
    attendance; they are invited, not registered."""
    user = await _attendee(request, users, signed_out=SIGN_IN_TO_WITHDRAW)
    event = await _published_event(event_id, events)
    if _has_started(event, now):
        raise HTTPException(status_code=409, detail=ALREADY_STARTED)

    response = await _call(
        "Registrations",
        registrations.post(
            "/registrations/withdrawals",
            json={
                "event_id": str(event_id),
                "attendee_id": user["id"],
                "capacity": event.get("expected_attendance") or 0,
            },
        ),
    )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=NOT_REGISTERED)
    if response.status_code != 200:
        raise _unavailable("Registrations")
    await _invite(response.json().get("offered"), event, users, bookings, venues, notifications)
    return {"event_id": event_id, "registered": False, "registered_at": None}


async def _offer_response(request: Request, event_id: UUID, users, events, now) -> tuple[dict, dict]:
    """S-55: who may answer an offer, and until when -- the event's start,
    whatever the registration period or an Organiser close says."""
    user = await _attendee(request, users, signed_out=SIGN_IN_TO_RESPOND)
    event = await _published_event(event_id, events)
    if _has_started(event, now):
        raise HTTPException(status_code=409, detail=OFFER_STARTED)
    return user, event


@app.post(
    "/event-registrations/events/{event_id}/waiting-list/offer",
    response_model=RegistrationStatus,
    status_code=201,
)
async def accept_offer(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
    now: datetime = Depends(get_now),
):
    """S-55: the invited Attendee takes the place held for them. This is the
    only way off the waiting list into a place."""
    user, event = await _offer_response(request, event_id, users, events, now)
    response = await _call(
        "Registrations",
        registrations.post(
            "/registrations/offers/acceptances",
            json={"event_id": str(event_id), "attendee_id": user["id"]},
        ),
    )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=NO_OFFER)
    if response.status_code == 409:
        raise HTTPException(status_code=409, detail=response.json()["detail"])
    if response.status_code != 201:
        raise _unavailable("Registrations")
    row = response.json()
    await _send_notice(CONFIRMATION, event, user, row, bookings, venues, notifications)
    return {"event_id": event_id, "registered": True, "registered_at": row["created_at"]}


@app.delete(
    "/event-registrations/events/{event_id}/waiting-list/offer",
    response_model=RegistrationStatus,
)
async def decline_offer(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    notifications: httpx.AsyncClient = Depends(get_notifications_client),
    now: datetime = Depends(get_now),
):
    """S-55: the invited Attendee passes. They leave the waiting list, and the
    place is offered to the next in line in the same step."""
    user, event = await _offer_response(request, event_id, users, events, now)
    response = await _call(
        "Registrations",
        registrations.post(
            "/registrations/offers/declines",
            json={
                "event_id": str(event_id),
                "attendee_id": user["id"],
                "capacity": event.get("expected_attendance") or 0,
            },
        ),
    )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=NO_OFFER)
    if response.status_code != 200:
        raise _unavailable("Registrations")
    await _invite(response.json().get("offered"), event, users, bookings, venues, notifications)
    return {"event_id": event_id, "registered": False, "registered_at": None}


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
    place = await _entry(registrations, f'/registrations/events/{event_id}/attendees/{user["id"]}')
    if place is not None:
        return {
            "event_id": event_id,
            "registered": True,
            "registered_at": place["created_at"],
        }
    waiting = await _entry(
        registrations, f'/registrations/waiting-list/events/{event_id}/attendees/{user["id"]}'
    )
    return {
        "event_id": event_id,
        "registered": False,
        "registered_at": None,
        "waitlisted": waiting is not None,
        "joined_at": waiting["created_at"] if waiting else None,
        "position": await _place_in_line(event_id, user["id"], registrations) if waiting else None,
        "offered": bool(waiting and waiting.get("offered_at")),
    }


async def _place_in_line(event_id, attendee_id: str, registrations: httpx.AsyncClient) -> int | None:
    """S-52: 1-based, in the first-come, first-served order the
    registrations service keeps the waiting list in."""
    rows = await _json(
        "Registrations", registrations.get(f"/registrations/waiting-list/events/{event_id}")
    )
    ids = [row["attendee_id"] for row in rows]
    return ids.index(attendee_id) + 1 if attendee_id in ids else None


async def _entry(registrations: httpx.AsyncClient, path: str) -> dict | None:
    """One row the registrations service holds, or None on its 404."""
    response = await _call("Registrations", registrations.get(path))
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise _unavailable("Registrations")
    return response.json()


@app.post(
    "/event-registrations/events/{event_id}/waiting-list",
    response_model=WaitingListStatus,
    status_code=201,
)
async def join_waiting_list(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
    now: datetime = Depends(get_now),
):
    """S-50: offered once the event is full, and only while registration
    would otherwise be open."""
    user = await _attendee(request, users)
    event = await _published_event(event_id, events)
    _check_period(event, now)
    if await _entry(registrations, f'/registrations/events/{event_id}/attendees/{user["id"]}'):
        raise HTTPException(status_code=409, detail=ALREADY_REGISTERED)
    if not _is_full(event, await _places_taken(str(event_id), registrations)):
        raise HTTPException(status_code=409, detail=STILL_HAS_PLACES)

    response = await _call(
        "Registrations",
        registrations.post(
            "/registrations/waiting-list",
            json={"event_id": str(event_id), "attendee_id": user["id"]},
        ),
    )
    if response.status_code == 409:
        raise HTTPException(status_code=409, detail=response.json()["detail"])
    if response.status_code != 201:
        raise _unavailable("Registrations")
    return {
        "event_id": event_id,
        "waitlisted": True,
        "joined_at": response.json()["created_at"],
        "position": await _place_in_line(event_id, user["id"], registrations),
    }


async def _viewable_event(event_id: UUID, request: Request, events: httpx.AsyncClient) -> None:
    """The events service decides who may see the list: it answers 404 for
    another Organiser's event and 403 for any other role. S-57: a 403 may
    still be the event's assigned Coordinator, so ask again as one -- 404 for
    a Coordinator not assigned to it, 403 again for every other role."""
    response = await _call(
        "Events", events.get(f"/events/{event_id}", cookies=request.cookies)
    )
    if response.status_code == 403:
        response = await _call(
            "Events", events.get(f"/events/assigned/{event_id}", cookies=request.cookies)
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
    await _viewable_event(event_id, request, events)
    rows, waiting = await asyncio.gather(
        _json("Registrations", registrations.get(f"/registrations/events/{event_id}")),
        _json("Registrations", registrations.get(f"/registrations/waiting-list/events/{event_id}")),
    )
    profiles = {}
    ids = list(dict.fromkeys(row["attendee_id"] for row in [*rows, *waiting]))
    if ids:
        found = await _json("Users", users.post("/internal/users/profiles", json={"ids": ids}))
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
    waiting_list = [
        {
            "attendee_id": row["attendee_id"],
            "name": profiles.get(row["attendee_id"], {}).get("name"),
            "email": profiles.get(row["attendee_id"], {}).get("email"),
            "joined_at": row["created_at"],
        }
        for row in waiting
    ]
    return {
        "event_id": event_id,
        "count": len(attendees),
        "attendees": attendees,
        "waiting_list": waiting_list,
    }


# S-56: confirmed details are shown; an event sent back for re-checking stays
# listed with them hidden until it is confirmed again.
DETAILS_CONFIRMED = "confirmed"
_DETAIL_FIELDS = ("start_date", "start_time", "end_date", "end_time")


async def _attendee_view(event_id: str, events: httpx.AsyncClient) -> dict | None:
    """An event that is over or cancelled drops out of the Attendee's list."""
    response = await _call("Events", events.get(f"/internal/events/attendee-view/{event_id}"))
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise _unavailable("Events")
    return response.json()


async def _primary_venue(event_id: str, bookings: httpx.AsyncClient) -> str | None:
    """S-91: the one confirmed booking the Coordinator designated. When a
    primary is cancelled or replaced, none is guessed in its place."""
    rows = await _json("Bookings", bookings.get("/bookings", params={"event_id": event_id}))
    primary = next((
        row for row in rows
        if row.get("status") == "confirmed" and row.get("is_primary") is True
    ), None)
    return primary.get("venue_name") if primary else None


async def _with_details(entry: dict, event: dict, bookings: httpx.AsyncClient) -> dict:
    row = {**event, "event_id": event["id"], **entry}
    row["details_confirmed"] = event["status"] == DETAILS_CONFIRMED
    row["venue"] = None
    if not row["details_confirmed"]:
        row.update(dict.fromkeys(_DETAIL_FIELDS))
    elif entry["status"] == "confirmed":
        # Only an Attendee holding a place sees where to go.
        row["venue"] = await _primary_venue(str(event["id"]), bookings)
    return row


@app.get("/event-registrations/me/registrations", response_model=list[MyRegistration])
async def list_my_registrations(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    registrations: httpx.AsyncClient = Depends(get_registrations_client),
):
    user = await _attendee(request, users)
    places, waiting = await asyncio.gather(
        _json("Registrations", registrations.get(f'/registrations/attendees/{user["id"]}')),
        _json("Registrations", registrations.get(f'/registrations/waiting-list/attendees/{user["id"]}')),
    )
    held = {row["event_id"] for row in places}
    # S-52: a confirmed place wins should both ever exist for one event.
    waiting = [row for row in waiting if row["event_id"] not in held]
    found, positions = await asyncio.gather(
        asyncio.gather(*(_attendee_view(row["event_id"], events) for row in [*places, *waiting])),
        asyncio.gather(
            *(_place_in_line(row["event_id"], user["id"], registrations) for row in waiting)
        ),
    )
    entries = [
        *({"status": "confirmed", "registered_at": row["created_at"], "joined_at": None,
           "position": None} for row in places),
        # S-55: an entry a freed place is held for reads "offered".
        *({"status": "offered" if row.get("offered_at") else "waitlisted",
           "registered_at": None, "joined_at": row["created_at"],
           "position": position} for row, position in zip(waiting, positions)),
    ]
    shown = [
        (entry, event)
        for entry, event in zip(entries, found)
        # A waiting-list entry is listed only while the event is confirmed (S-52).
        if event is not None
        and (entry["status"] == "confirmed" or event["status"] == DETAILS_CONFIRMED)
    ]
    listed = await asyncio.gather(*(_with_details(entry, event, bookings) for entry, event in shown))
    # Soonest event first; an event without dates, or whose details are being
    # re-checked, sorts last.
    return sorted(
        listed,
        key=lambda item: (item["start_date"] or "9999-12-31", item["start_time"] or ""),
    )
