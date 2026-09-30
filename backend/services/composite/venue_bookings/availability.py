"""A venue's availability calendar (S-30).

Pure functions over the bookings and blocks exactly as the bookings service
returns them, so the rules are testable without HTTP and the route stays thin.

What each role may see is decided here. A Coordinator sees another event's
confirmed booking as just "confirmed" and a hold as just "held" -- no event,
no coordinator, no ids. Venue Staff additionally see a block's id and note,
which they need to remove it. Rejected requests are not on the calendar.
"""

# The booking status each calendar state comes from. Anything else -- a
# rejected request -- is left off.
STATES = {"held": "held", "confirmed": "confirmed"}


def _booking_entry(booking: dict) -> dict:
    return {
        "state": STATES[booking["status"]],
        "start_date": booking["booking_date"],
        "end_date": booking["booking_date"],
        "start_time": booking["start_time"],
        "end_time": booking["end_time"],
    }


def _block_entry(block: dict, staff: bool) -> dict:
    entry = {
        "state": "blocked",
        "start_date": block["start_date"],
        "end_date": block["end_date"],
        "start_time": None,
        "end_time": None,
        "reason": block["reason"],
    }
    if staff:
        entry["id"] = block["id"]
        entry["note"] = block.get("note")
    return entry


def entries(bookings: list[dict], blocks: list[dict], *, staff: bool) -> list[dict]:
    """The calendar's entries, in date order and then by start time. A
    whole-day block sorts ahead of that day's bookings."""
    found = [_booking_entry(booking) for booking in bookings if booking["status"] in STATES]
    found += [_block_entry(block, staff) for block in blocks]
    return sorted(found, key=lambda entry: (entry["start_date"], entry["start_time"] or ""))
