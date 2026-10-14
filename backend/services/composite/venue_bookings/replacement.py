"""Replacing a booking an unavailable period affects (S-78).

The replacement is for the affected booking's own date and times, and the
event's current requirements -- the Coordinator only picks the venue. A
venue is offered when it is suitable (S-36's checks, suitability.py) and
available: no held or confirmed booking there within the setup + turnaround
gap (the bookings service's own rule for a new request, S-75) and no
unavailable period over the window it would occupy (S-77). A pending request
reserves nothing, so it never makes a venue unavailable.

Pure functions over bookings, blocks, events and venues exactly as their
services return them, so the rules are testable without HTTP.
"""

from datetime import date, time, timedelta
from types import SimpleNamespace

import occupancy
import suitability
import unavailability

# An event whose venue bookings may still change. A confirmed event is the
# one most likely to lose a confirmed venue.
OPEN_EVENT_STATUSES = ("planning", "confirmed", "preparation", "safety_changes_requested")
ACTIVE = ("pending", "held")


def slot(booking: dict) -> SimpleNamespace:
    """The affected booking's date and times, shaped as suitability.py reads a
    request."""
    return SimpleNamespace(
        booking_date=date.fromisoformat(str(booking["booking_date"])),
        start_time=time.fromisoformat(str(booking["start_time"])),
        end_time=time.fromisoformat(str(booking["end_time"])),
    )


def summary(booking: dict) -> dict:
    return {
        "id": booking["id"],
        "venue_name": booking["venue_name"],
        "booking_date": str(booking["booking_date"]),
        "start_time": str(booking["start_time"]),
        "end_time": str(booking["end_time"]),
    }


def suitable(booking: dict, event: dict, venue: dict) -> bool:
    return not suitability.problems(slot(booking), event, venue)


def _taken(booking: dict, venue: dict, same_day: list[dict]) -> bool:
    """As the bookings service checks a new request: another held or
    confirmed booking within setup + turnaround minutes either side."""
    minutes = timedelta(minutes=sum(occupancy.gap(venue)))
    start, end = occupancy.occupied(booking, {})
    for other in same_day:
        if other.get("status") not in occupancy.LIVE:
            continue
        other_start, other_end = occupancy.occupied(other, {})
        if other_start < end + minutes and other_end > start - minutes:
            return True
    return False


def _blocked(booking: dict, venue: dict, blocks: list[dict]) -> bool:
    occupied_start, occupied_end = occupancy.occupied(booking, venue)
    for block in blocks:
        start, end = unavailability.bounds(block)
        if start < occupied_end and occupied_start < end:
            return True
    return False


def available(booking: dict, venue: dict, same_day: list[dict], blocks: list[dict]) -> bool:
    """Whether `venue` is free for the affected booking's date and times."""
    at_venue = {**booking, "venue_id": venue["id"]}
    return not _taken(at_venue, venue, same_day) and not _blocked(at_venue, venue, blocks)


def active_replacement(original: dict, event_bookings: list[dict]) -> dict | None:
    """The pending or held replacement request for `original`, if any. One at
    a time: once that one is rejected, another may be sent."""
    return next(
        (
            row for row in event_bookings
            if str(row.get("replaces_booking_id")) == str(original["id"]) and row.get("status") in ACTIVE
        ),
        None,
    )
