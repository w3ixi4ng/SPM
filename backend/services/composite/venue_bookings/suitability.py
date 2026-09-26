"""Whether a venue can take a Coordinator's booking request.

Pure functions over the event and venue exactly as their services return
them, so the rules are testable without HTTP and the route stays thin. Every
failed check is collected, not just the first -- a Coordinator fixes them all
in one pass (TC-VENUEBOOKINGS-016).

This is validation at submission, not a booking decision: a request that
fails here is never saved and never reaches Venue Staff.
"""

from datetime import date, datetime, time

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = ("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays")


def _time(value: str | time) -> time:
    # The services serialise times as "HH:MM:SS"; fromisoformat takes that and "HH:MM".
    return value if isinstance(value, time) else time.fromisoformat(value)


def _date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _window_problem(booking, event) -> str | None:
    event_start = datetime.combine(_date(event["start_date"]), _time(event["start_time"]))
    event_end = datetime.combine(_date(event["end_date"]), _time(event["end_time"]))
    booking_start = datetime.combine(booking.booking_date, booking.start_time)
    booking_end = datetime.combine(booking.booking_date, booking.end_time)
    # Inclusive: a booking may use the event's full window, never more.
    if booking_start < event_start or booking_end > event_end:
        return "The booking must fall within the event's date and time"
    return None


def _hours_problem(booking, venue) -> str | None:
    weekday = booking.booking_date.weekday()
    hours = next(
        (entry for entry in venue["operating_hours"] if entry["day"] == DAYS[weekday]),
        None,
    )
    if hours is None:
        return f"{venue['name']} is closed on {DAY_NAMES[weekday]}"

    opens, closes = _time(hours["open"]), _time(hours["close"])
    # Inclusive at both ends: open-to-close exactly is allowed.
    if booking.start_time < opens or booking.end_time > closes:
        return f"{venue['name']} is open {opens:%H:%M}–{closes:%H:%M} on {DAY_NAMES[weekday]}"
    return None


def _missing(required: list[str], offered: list[str]) -> list[str]:
    return [item for item in required if item not in offered]


def problems(booking, event: dict, venue: dict) -> dict[str, str]:
    """Every reason `venue` can't take `booking` for `event`, keyed by the
    field a Coordinator would change. Empty when it can."""
    found: dict[str, str] = {}
    name = venue["name"]

    window = _window_problem(booking, event)
    if window:
        found["booking_date"] = window

    hours = _hours_problem(booking, venue)
    if hours:
        found["operating_hours"] = hours

    attendance = event["expected_attendance"]
    if attendance > venue["capacity"]:
        found["expected_attendance"] = (
            f"{name} holds {venue['capacity']} people; this event expects {attendance}"
        )

    # The requirements are the event's (S-36), not the request's.
    missing_facilities = _missing(event.get("required_facilities") or [], venue["facilities"])
    if missing_facilities:
        found["required_facilities"] = f"{name} does not have: {', '.join(missing_facilities)}"

    missing_accessibility = _missing(event.get("required_accessibility") or [], venue["accessibility"])
    if missing_accessibility:
        found["required_accessibility"] = f"{name} does not have: {', '.join(missing_accessibility)}"

    layout = event.get("room_layout")
    if layout is not None and layout not in venue["room_layouts"]:
        found["room_layout"] = f"{name} does not offer the {layout} layout"

    return found
