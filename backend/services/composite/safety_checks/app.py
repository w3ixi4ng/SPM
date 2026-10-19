"""S-86 cross-service Operational Safety Check workflow."""

import logging
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from clients import (
    get_bookings_client,
    get_equipment_client,
    get_events_client,
    get_users_client,
    get_venues_client,
)
import readiness
from schemas import SafetyDecisionRequest

app = FastAPI(title="Safety Checks Service")
logger = logging.getLogger(__name__)

SAFETY_OFFICER_ROLE = "safety_officer"
EVENT_COORDINATOR_ROLE = "event_coordinator"


@app.exception_handler(RequestValidationError)
async def readable_validation_error(request: Request, exc: RequestValidationError):
    errors: dict[str, str] = {}
    for error in exc.errors():
        path = [str(part) for part in error["loc"] if part != "body"]
        errors.setdefault(".".join(path) or "body", error["msg"])
    return JSONResponse(
        status_code=422,
        content={"detail": "Please check the safety decision", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    logger.exception("Unhandled safety_checks error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
@app.get("/safety-checks/health", include_in_schema=False)
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


async def _safety_officer(request: Request, users: httpx.AsyncClient) -> dict:
    response = await _call("Users", users.get("/users/me", cookies=request.cookies))
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != 200:
        raise _unavailable("Users")
    user = response.json()
    if user.get("role") != SAFETY_OFFICER_ROLE:
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


async def _event_coordinator(request: Request, users: httpx.AsyncClient) -> dict:
    response = await _call("Users", users.get("/users/me", cookies=request.cookies))
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != 200:
        raise _unavailable("Users")
    user = response.json()
    if user.get("role") != EVENT_COORDINATOR_ROLE:
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


async def _json(service: str, send, *, identified: set[int] = frozenset()) -> object:
    response = await _call(service, send)
    if response.status_code in identified:
        detail = (response.json() or {}).get("detail", f"{service} request rejected")
        raise HTTPException(status_code=response.status_code, detail=detail)
    if response.status_code != 200:
        raise _unavailable(service)
    return response.json()


async def _profiles(users: httpx.AsyncClient, ids: list[str]) -> dict[str, dict]:
    unique = list(dict.fromkeys(value for value in ids if value))
    if not unique:
        return {}
    rows = await _json(
        "Users", users.post("/internal/users/profiles", json={"ids": unique})
    )
    return {row["id"]: row for row in rows}


def _unknown_profile(user_id: str | None, label: str) -> dict | None:
    if user_id is None:
        return None
    return {"id": user_id, "name": label, "email": None}


@app.get("/safety-checks")
async def list_safety_checks(
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    await _safety_officer(request, users)
    rows = await _json("Events", events.get("/internal/events/safety-review"))
    if not rows:
        return []
    profiles = await _profiles(users, [row["organiser_id"] for row in rows])
    return [
        {
            **row,
            "organiser": profiles.get(row["organiser_id"])
            or _unknown_profile(row["organiser_id"], "Unknown organiser"),
        }
        for row in rows
    ]


async def _confirmed_venues(
    event_id: UUID,
    bookings: httpx.AsyncClient,
    venues: httpx.AsyncClient,
) -> list[dict]:
    booking_rows = await _json(
        "Bookings", bookings.get("/bookings", params={"event_id": str(event_id)})
    )
    confirmed = [row for row in booking_rows if row.get("status") == "confirmed"]
    enriched = []
    for booking in confirmed:
        venue = await _json(
            "Venues",
            venues.get(f'/internal/venues/{booking["venue_id"]}'),
        )
        enriched.append(
            {
                "booking_id": booking["id"],
                "venue_id": booking["venue_id"],
                "name": venue["name"],
                "location": venue["location"],
                "capacity": venue["capacity"],
                "layout": booking.get("room_layout"),
                "accessibility": venue.get("accessibility", []),
                "facilities": venue.get("facilities", []),
                # Venue description is the existing catalogue field in which
                # staff record restrictions; S-86 presents it explicitly.
                "restrictions": venue.get("description"),
                "booking_date": booking["booking_date"],
                "start_time": booking["start_time"],
                "end_time": booking["end_time"],
                "booking_special_requirements": booking.get("special_requirements"),
                "booking_notes": booking.get("notes"),
            }
        )
    return enriched


@app.get("/safety-checks/coordinator/events/{event_id}")
async def get_returned_safety_review(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    """Show S-87 feedback only to the currently assigned Coordinator."""

    coordinator = await _event_coordinator(request, users)
    event = await _json(
        "Events",
        events.get(
            f"/internal/events/{event_id}/safety-return",
            params={"coordinator_id": coordinator["id"]},
        ),
        identified={404, 409},
    )
    history = event.get("safety_review_history") or []
    profiles = await _profiles(
        users,
        [row.get("safety_officer_id") for row in history],
    )
    enriched = [
        {
            **row,
            "safety_officer": profiles.get(row.get("safety_officer_id"))
            or _unknown_profile(row.get("safety_officer_id"), "Unknown Safety Officer"),
        }
        for row in history
    ]
    current = next(
        (
            row
            for row in reversed(enriched)
            if row["decision"] == "changes_requested"
            and row["decided_at"] == event.get("safety_decided_at")
        ),
        enriched[-1] if enriched else None,
    )
    return {
        "event": event,
        "current_return": current,
        "safety_review_history": enriched,
    }


NOT_IN_PLANNING = "This event is not in planning"
NOT_RETURNED = "This event is not awaiting revision after a safety change request"
OUTSTANDING = "This event has outstanding arrangements"


async def _assigned_event(event_id: UUID, request: Request, events: httpx.AsyncClient) -> dict:
    """The event, read as the signed-in Coordinator. Another Coordinator's
    event is the same 404 as one that doesn't exist."""
    return await _json(
        "Events",
        events.get(f"/events/assigned/{event_id}", cookies=request.cookies),
        identified={401, 403, 404, 409},
    )


async def _flagged_ids(
    bookings_rows: list[dict],
    bookings: httpx.AsyncClient,
    venues: httpx.AsyncClient,
) -> set[str]:
    flagged = set()
    for booking in bookings_rows:
        if booking.get("status") != "confirmed":
            continue
        venue = await _json("Venues", venues.get(f'/internal/venues/{booking["venue_id"]}'))
        day = str(booking["booking_date"])
        blocks = await _json(
            "Bookings",
            bookings.get(
                "/blocks",
                params={"venue_id": str(booking["venue_id"]), "from": day, "to": day},
            ),
        )
        if readiness.flagged(booking, blocks, venue):
            flagged.add(str(booking["id"]))
    return flagged


async def _outstanding(
    event: dict,
    bookings: httpx.AsyncClient,
    venues: httpx.AsyncClient,
    equipment: httpx.AsyncClient,
) -> list[dict]:
    event_id = str(event["id"])
    booking_rows = await _json("Bookings", bookings.get("/bookings", params={"event_id": event_id}))
    requirements = await _json(
        "Equipment",
        equipment.get("/internal/equipment-requirements", params={"event_id": event_id}),
    )
    flagged = await _flagged_ids(booking_rows, bookings, venues)
    return readiness.outstanding(event, booking_rows, flagged, requirements)


def _refuse_outstanding(items: list[dict]) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": OUTSTANDING, "outstanding": items})


async def _no_body(request: Request):
    """S-17 has no override: the submission takes no input at all, so nothing
    a client sends can change its outcome."""
    if (await request.body()).strip():
        raise HTTPException(status_code=422, detail="This request takes no body")


@app.get("/safety-checks/coordinator/events/{event_id}/readiness")
async def get_readiness(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
):
    """S-17: what submission would refuse, without submitting."""
    await _event_coordinator(request, users)
    event = await _assigned_event(event_id, request, events)
    items = await _outstanding(event, bookings, venues, equipment)
    return {"ready": not items, "outstanding": items}


@app.post("/safety-checks/coordinator/events/{event_id}/submit")
async def submit_for_safety_check(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
):
    """S-17: planning -> pending_safety_check, only once nothing is outstanding."""
    await _no_body(request)
    coordinator = await _event_coordinator(request, users)
    event = await _assigned_event(event_id, request, events)
    if event.get("status") != "planning":
        raise HTTPException(status_code=409, detail=NOT_IN_PLANNING)
    items = await _outstanding(event, bookings, venues, equipment)
    if items:
        return _refuse_outstanding(items)
    return await _json(
        "Events",
        events.post(
            f"/internal/events/{event_id}/safety-submission",
            json={"coordinator_id": coordinator["id"]},
        ),
        identified={404, 409},
    )


@app.post("/safety-checks/coordinator/events/{event_id}/resubmit")
async def resubmit_returned_safety_review(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
):
    """S-87 resubmission, held to the same S-17 check as a first submission."""
    await _no_body(request)
    coordinator = await _event_coordinator(request, users)
    event = await _assigned_event(event_id, request, events)
    if event.get("status") != "planning" or event.get("safety_decision") != "changes_requested":
        raise HTTPException(status_code=409, detail=NOT_RETURNED)
    items = await _outstanding(event, bookings, venues, equipment)
    if items:
        return _refuse_outstanding(items)
    return await _json(
        "Events",
        events.post(
            f"/internal/events/{event_id}/safety-resubmit",
            json={"coordinator_id": coordinator["id"]},
        ),
        identified={404, 409},
    )


@app.get("/safety-checks/{event_id}")
async def get_safety_check(
    event_id: UUID,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
    venues: httpx.AsyncClient = Depends(get_venues_client),
    bookings: httpx.AsyncClient = Depends(get_bookings_client),
    equipment: httpx.AsyncClient = Depends(get_equipment_client),
):
    await _safety_officer(request, users)
    event = await _json(
        "Events",
        events.get(f"/internal/events/safety-review/{event_id}"),
        identified={404, 409},
    )
    profile_ids = [event["organiser_id"]]
    if event.get("assigned_technical_support_id"):
        profile_ids.append(event["assigned_technical_support_id"])
    profiles = await _profiles(users, profile_ids)
    confirmed_venues = await _confirmed_venues(event_id, bookings, venues)
    requirements = await _json(
        "Equipment",
        equipment.get(
            "/internal/equipment-requirements",
            params={"event_id": str(event_id)},
        ),
    )
    support_id = event.get("assigned_technical_support_id")
    return {
        "event": event,
        "organiser": profiles.get(event["organiser_id"])
        or _unknown_profile(event["organiser_id"], "Unknown organiser"),
        "technical_support": profiles.get(support_id)
        or _unknown_profile(support_id, "Unknown Technical Support"),
        "technical_support_notes": event.get("technical_support_details"),
        "confirmed_venues": confirmed_venues,
        "equipment_requirements": requirements,
    }


@app.post("/safety-checks/{event_id}/decision")
async def decide_safety_check(
    event_id: UUID,
    payload: SafetyDecisionRequest,
    request: Request,
    users: httpx.AsyncClient = Depends(get_users_client),
    events: httpx.AsyncClient = Depends(get_events_client),
):
    officer = await _safety_officer(request, users)
    return await _json(
        "Events",
        events.post(
            f"/internal/events/safety-review/{event_id}/decision",
            json={
                **payload.model_dump(mode="json"),
                "safety_officer_id": officer["id"],
            },
        ),
        identified={404, 409, 422},
    )
