"""When a venue is occupied by a booking, and which bookings clash (S-75).

A booking occupies its venue from start - setup to end + turnaround, using
the venue's current times, so two bookings at one venue clash when those
windows overlap. Touching windows -- one ending exactly as the other starts
-- do not clash. Only held and confirmed bookings reserve time.

A clash is a warning worked out from current data each time it is viewed.
Nothing here changes a booking: a clash is resolved by people, and the
warning goes once it no longer applies.

Pure functions over bookings and venues exactly as their services return
them, so the rules are testable without HTTP.
"""

from datetime import date, datetime, time, timedelta

LIVE = ("held", "confirmed")


def gap(venue: dict) -> tuple[int, int]:
    """The venue's (setup, turnaround) minutes; 0 for a venue saved before S-75."""
    return int(venue.get("setup_minutes") or 0), int(venue.get("turnaround_minutes") or 0)


def gap_params(venue: dict) -> dict:
    setup, turnaround = gap(venue)
    return {"setup_minutes": setup, "turnaround_minutes": turnaround}


def _moment(booking_date, value) -> datetime:
    return datetime.combine(date.fromisoformat(str(booking_date)), time.fromisoformat(str(value)))


def occupied(booking: dict, venue: dict) -> tuple[datetime, datetime]:
    setup, turnaround = gap(venue)
    return (
        _moment(booking["booking_date"], booking["start_time"]) - timedelta(minutes=setup),
        _moment(booking["booking_date"], booking["end_time"]) + timedelta(minutes=turnaround),
    )


def _clock(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def _is_current_live(booking: dict, today: date) -> bool:
    return booking.get("status") in LIVE and date.fromisoformat(str(booking["booking_date"])) >= today


def _overlaps(a: dict, b: dict, venue: dict) -> bool:
    a_start, a_end = occupied(a, venue)
    b_start, b_end = occupied(b, venue)
    return a_start < b_end and b_start < a_end


def clashes_for(booking: dict, others: list[dict], venue: dict, today: date) -> list[dict]:
    """The other held/confirmed bookings at this venue that `booking` clashes
    with, for its Coordinator: each other booking's time and state only --
    never another event's name, coordinator or id."""
    if not _is_current_live(booking, today):
        return []
    found = []
    for other in sorted(others, key=lambda row: (str(row["booking_date"]), str(row["start_time"]))):
        if str(other["id"]) == str(booking["id"]) or not _is_current_live(other, today):
            continue
        if str(other["venue_id"]) != str(booking["venue_id"]) or not _overlaps(booking, other, venue):
            continue
        start, end = occupied(other, venue)
        found.append({
            "booking_date": str(other["booking_date"]),
            "start_time": str(other["start_time"]),
            "end_time": str(other["end_time"]),
            "occupied_start": _clock(start),
            "occupied_end": _clock(end),
            "status": other["status"],
        })
    return found


def _staff_view(booking: dict, venue: dict) -> dict:
    start, end = occupied(booking, venue)
    return {
        "id": booking["id"],
        "event_id": booking["event_id"],
        "event_name": booking["event_name"],
        "coordinator_name": booking["coordinator_name"],
        "status": booking["status"],
        "booking_date": str(booking["booking_date"]),
        "start_time": str(booking["start_time"]),
        "end_time": str(booking["end_time"]),
        "occupied_start": _clock(start),
        "occupied_end": _clock(end),
    }


def clash_pairs(bookings: list[dict], venue: dict, today: date) -> list[dict]:
    """Every pair of held/confirmed bookings at the venue, today onwards,
    whose occupied windows overlap -- each pair once, in date then start
    order -- for Venue Staff, who may see whose they are."""
    live = sorted(
        (row for row in bookings if _is_current_live(row, today)),
        key=lambda row: (str(row["booking_date"]), str(row["start_time"])),
    )
    pairs = []
    for index, first in enumerate(live):
        for second in live[index + 1:]:
            if _overlaps(first, second, venue):
                pairs.append({"first": _staff_view(first, venue), "second": _staff_view(second, venue)})
    return pairs
