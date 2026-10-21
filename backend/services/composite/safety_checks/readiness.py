"""What still stands between a planning event and its Operational Safety
Check (S-17).

Venue approved: at least one confirmed booking, and no booking still pending
or held, no rejected booking that has not been replaced (a rejected
replacement request does not count again), and no confirmed
booking an unavailable period affects (S-77) that has not been resolved
(S-78). Replaced bookings no longer count.

Equipment and technical support arranged -- only when the event has an
equipment requirement or asked for technical support: Technical Support is
assigned, has approved the arrangements, and has marked preparation ready
(S-26).

There is no override. The Coordinator sees every outstanding item at once.

Pure functions over rows exactly as their services return them, so the rules
are testable without HTTP.
"""

from datetime import date, datetime, time, timedelta

PREPARATION_LABELS = {"not_started": "Not Started", "in_progress": "In Progress"}


def _date_label(value) -> str:
    day = date.fromisoformat(str(value))
    return f"{day.day} {day.strftime('%b %Y')}"


def _where(booking: dict) -> str:
    return f"{booking['venue_name']} on {_date_label(booking['booking_date'])}"


def _item(code: str, label: str, booking: dict | None = None) -> dict:
    item = {"code": code, "label": label}
    if booking is not None:
        item["booking_id"] = str(booking["id"])
    return item


def _in_order(bookings: list[dict]) -> list[dict]:
    return sorted(bookings, key=lambda row: (str(row["booking_date"]), str(row["start_time"])))


# Repeated from venue_bookings' occupancy.py and unavailability.py -- each
# Docker image holds only its own service's code. Change both.
def _moment(day, clock) -> datetime:
    return datetime.combine(date.fromisoformat(str(day)), time.fromisoformat(str(clock)))


def _occupied(booking: dict, venue: dict) -> tuple[datetime, datetime]:
    setup = int(venue.get("setup_minutes") or 0)
    turnaround = int(venue.get("turnaround_minutes") or 0)
    return (
        _moment(booking["booking_date"], booking["start_time"]) - timedelta(minutes=setup),
        _moment(booking["booking_date"], booking["end_time"]) + timedelta(minutes=turnaround),
    )


def _after_resolution(booking: dict, block: dict) -> bool:
    resolved_at = booking.get("alternative_resolved_at")
    if not resolved_at or not block.get("created_at"):
        return True
    return datetime.fromisoformat(str(block["created_at"])) > datetime.fromisoformat(str(resolved_at))


def flagged(booking: dict, blocks: list[dict], venue: dict) -> bool:
    """Whether an unavailable period affects this booking and has not been
    resolved with alternative arrangements."""
    occupied_start, occupied_end = _occupied(booking, venue)
    for block in blocks:
        if str(block["venue_id"]) != str(booking["venue_id"]):
            continue
        start = _moment(block["start_date"], block["start_time"])
        end = _moment(block["end_date"], block["end_time"])
        if start < occupied_end and occupied_start < end and _after_resolution(booking, block):
            return True
    return False


def signoff_needed(event: dict, requirements: list[dict]) -> bool:
    return bool(requirements) or bool(event.get("technical_support_required"))


def venue_items(bookings: list[dict], flagged_ids: set[str]) -> list[dict]:
    confirmed = [row for row in bookings if row.get("status") == "confirmed"]
    awaiting = [row for row in bookings if row.get("status") in ("pending", "held")]
    # A rejected replacement request is not counted again: the booking it
    # was meant to replace is still here and still outstanding on its own.
    rejected = [
        row for row in bookings
        if row.get("status") == "rejected" and not row.get("replaces_booking_id")
    ]
    items = []
    if not confirmed:
        items.append(_item("venue_missing", "No venue booking has been confirmed yet"))
    items += [
        _item("venue_awaiting", f"{_where(row)} is waiting for Venue Staff", row)
        for row in _in_order(awaiting)
    ]
    items += [
        _item(
            "venue_rejected",
            f"{_where(row)} was rejected — request a replacement venue",
            row,
        )
        for row in _in_order(rejected)
    ]
    items += [
        _item(
            "venue_unavailable",
            f"{_where(row)} is affected by an unavailable period — "
            "replace it or record alternative arrangements",
            row,
        )
        for row in _in_order(confirmed)
        if str(row["id"]) in flagged_ids
    ]
    return items


def technical_items(event: dict, requirements: list[dict]) -> list[dict]:
    if not signoff_needed(event, requirements):
        return []
    items = []
    if not event.get("assigned_technical_support_id"):
        items.append(_item(
            "technical_support_unassigned", "Technical Support has not been assigned",
        ))
    decision = event.get("technical_signoff_decision")
    if decision == "declined":
        items.append(_item(
            "technical_signoff_declined",
            f"Technical Support declined: {event.get('technical_signoff_reason')}",
        ))
    elif decision != "approved":
        items.append(_item(
            "technical_signoff_awaiting",
            "Technical Support has not approved the equipment arrangements",
        ))
    preparation = event.get("equipment_preparation_status") or "not_started"
    if preparation != "ready":
        items.append(_item(
            "equipment_preparation",
            f"Equipment preparation is {PREPARATION_LABELS.get(preparation, preparation)}",
        ))
    return items


def outstanding(
    event: dict,
    bookings: list[dict],
    flagged_ids: set[str],
    requirements: list[dict],
) -> list[dict]:
    """Every outstanding item, venue first. Empty means ready to submit."""
    return venue_items(bookings, flagged_ids) + technical_items(event, requirements)
