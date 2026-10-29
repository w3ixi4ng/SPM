"""Bookings a venue's unavailable periods affect (S-77).

A period runs from start_date + start_time up to, but not including,
end_date + end_time. A held or confirmed booking at the same venue is
affected when the window it occupies the venue -- start - setup to
end + turnaround, from occupancy.py -- overlaps the period. Pending and
rejected requests are never affected: a pending one cannot be held or
confirmed inside a period anyway.

Like S-75's clashes, being affected is worked out from current data each
time it is viewed. Nothing here changes a booking or an event: the period
does not cancel anything, and removing it removes the flag.

Pure functions over bookings, blocks and venues exactly as their services
return them, so the rules are testable without HTTP.
"""

from datetime import date, datetime, time

import occupancy

# Repeated from the frontend's BLOCK_REASONS labels, for notification text.
REASON_LABELS = {
    "maintenance": "Maintenance",
    "equipment_failure": "Equipment failure",
    "renovation": "Renovation",
    "safety": "Safety concern",
    "other": "Other operational reason",
}

KIND = "venue_unavailable"
# The notifications service takes at most this many rows in one batch.
BATCH_SIZE = 20


def _moment(day, clock) -> datetime:
    return datetime.combine(date.fromisoformat(str(day)), time.fromisoformat(str(clock)))


def bounds(block: dict) -> tuple[datetime, datetime]:
    return _moment(block["start_date"], block["start_time"]), _moment(block["end_date"], block["end_time"])


def affects(booking: dict, block: dict, venue: dict) -> bool:
    if booking.get("status") not in occupancy.LIVE:
        return False
    if str(booking["venue_id"]) != str(block["venue_id"]):
        return False
    occupied_start, occupied_end = occupancy.occupied(booking, venue)
    start, end = bounds(block)
    return start < occupied_end and occupied_start < end


def affected_bookings(bookings: list[dict], block: dict, venue: dict) -> list[dict]:
    """The bookings `block` affects, in date then start order, as Venue
    Staff see them -- with the event, the Coordinator and the occupied window."""
    found = sorted(
        (row for row in bookings if affects(row, block, venue)),
        key=lambda row: (str(row["booking_date"]), str(row["start_time"])),
    )
    return [occupancy.staff_view(row, venue) for row in found]


def period(block: dict) -> dict:
    return {
        "start_date": str(block["start_date"]),
        "start_time": str(block["start_time"]),
        "end_date": str(block["end_date"]),
        "end_time": str(block["end_time"]),
        "reason": block["reason"],
        "note": block.get("note"),
    }


def _after_resolution(booking: dict, block: dict) -> bool:
    """S-78: once a Coordinator resolves the flag, the periods they dealt with
    -- every one created up to then -- stop flagging the booking. A period
    created later flags it again."""
    resolved_at = booking.get("alternative_resolved_at")
    if not resolved_at or not block.get("created_at"):
        return True
    return datetime.fromisoformat(str(block["created_at"])) > datetime.fromisoformat(str(resolved_at))


def flag(booking: dict, blocks: list[dict], venue: dict | None) -> dict:
    """The fields every booking read carries: whether it needs alternative
    arrangements, and the periods that say so, in start order."""
    found = []
    if venue is not None:
        found = sorted(
            (
                block for block in blocks
                if affects(booking, block, venue) and _after_resolution(booking, block)
            ),
            key=lambda block: bounds(block)[0],
        )
    return {
        "requires_alternative_arrangements": bool(found),
        "unavailable_periods": [period(block) for block in found],
    }


def _date_label(value) -> str:
    # "1 Nov 2026", never "01 Nov 2026", as in the bookings service.
    day = date.fromisoformat(str(value)[:10])
    return f"{day.day} {day:%b %Y}"


def message(block: dict, booking: dict) -> str:
    start, end = bounds(block)
    return (
        f'{block["venue_name"]} is unavailable from {_date_label(start)} {start:%H:%M} to {_date_label(end)} {end:%H:%M} '
        f'({REASON_LABELS[block["reason"]]}). Your booking on {_date_label(booking["booking_date"])} '
        f'from {str(booking["start_time"])[:5]} to {str(booking["end_time"])[:5]} '
        "needs alternative arrangements."
    )


def notifications(block: dict, affected: list[dict], events: dict[str, dict]) -> list[dict]:
    """One row per affected booking, to its event's current Coordinator --
    `events` is the events service's active assignments by event id. A
    booking whose event has no current Coordinator is still affected, but
    there is nobody to tell. The key makes a retry create only what is
    missing."""
    rows = []
    for booking in affected:
        event = events.get(str(booking["event_id"]))
        recipient = (event or {}).get("assigned_coordinator_id")
        if not recipient:
            continue
        rows.append({
            "recipient_id": str(recipient),
            "event_id": str(booking["event_id"]),
            "event_name": event.get("name") or booking["event_name"],
            "kind": KIND,
            "message": message(block, booking),
            "deduplication_key": f'{KIND}:{block["id"]}:{booking["id"]}:{recipient}',
        })
    return rows


def batches(rows: list[dict]) -> list[list[dict]]:
    return [rows[index:index + BATCH_SIZE] for index in range(0, len(rows), BATCH_SIZE)]
