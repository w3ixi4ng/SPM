"""S-60 impact descriptions over snapshots returned by owning services.

This module never reads a database. The composite obtains each snapshot over
HTTP and fails closed when a required owner is unavailable.
"""

from datetime import date, datetime, time, timedelta


WINDOW = ("start_date", "start_time", "end_date", "end_time")
VENUE = ("venue", "room_layout", "required_facilities", "required_accessibility", "special_requirements")


def _item(kind: str, identity: str, code: str, reason: str, action: str) -> dict:
    return {
        "id": f"{kind}:{identity}:{code}", "kind": kind,
        "arrangement_id": identity, "code": code, "reason": reason,
        "required_action": action, "status": "outstanding",
    }


def _window(values: dict) -> tuple[datetime, datetime]:
    return (
        datetime.combine(date.fromisoformat(str(values["start_date"])), time.fromisoformat(str(values["start_time"]))),
        datetime.combine(date.fromisoformat(str(values["end_date"])), time.fromisoformat(str(values["end_time"]))),
    )


def _booking_conflict(booking: dict, venue: dict, others: list[dict], proposed: dict) -> bool:
    start, end = _window(proposed)
    setup = timedelta(minutes=int(venue.get("setup_minutes") or 0))
    turnaround = timedelta(minutes=int(venue.get("turnaround_minutes") or 0))
    start -= setup
    end += turnaround
    for other in others:
        if other.get("status") not in {"held", "confirmed"} or str(other.get("event_id")) == str(booking.get("event_id")):
            continue
        other_start = datetime.combine(date.fromisoformat(str(other["booking_date"])), time.fromisoformat(str(other["start_time"]))) - setup
        other_end = datetime.combine(date.fromisoformat(str(other["booking_date"])), time.fromisoformat(str(other["end_time"]))) + turnaround
        if start < other_end and other_start < end:
            return True
    return False


def assess(
    event: dict, request: dict, bookings: list[dict], venues: dict[str, dict],
    nearby_bookings: dict[str, list[dict]], current_equipment: list[dict],
    catalogue: list[dict], overlapping_events: list[dict], overlapping_requirements: list[dict],
    technical_conflict: bool,
) -> list[dict]:
    accepted = request["accepted_values"]
    proposed = request["proposed_values"]
    window_changed = any(accepted.get(key) != proposed.get(key) for key in WINDOW)
    attendance_changed = accepted.get("expected_attendance") != proposed.get("expected_attendance")
    venue_changed = any(accepted.get(key) != proposed.get(key) for key in VENUE)
    old_equipment = {row["equipment_item_id"]: row["required_quantity"] for row in request["accepted_equipment"]}
    new_equipment = {row["equipment_item_id"]: row["required_quantity"] for row in request["proposed_equipment"]}
    equipment_changed = old_equipment != new_equipment
    items: list[dict] = []

    for booking in bookings:
        if booking.get("status") not in {"pending", "held", "confirmed"}:
            continue
        booking_id = str(booking["id"])
        venue = venues[str(booking["venue_id"])]
        if window_changed:
            items.append(_item("venue_booking", booking_id, "window",
                "The existing booking is for the previous date or time; confirm a suitable new slot or replacement.",
                "Confirm changed booking or arrange a replacement"))
            if _booking_conflict(booking, venue, nearby_bookings.get(str(booking["venue_id"]), []), proposed):
                items.append(_item("venue_booking", booking_id, "clash",
                    "The proposed window overlaps another booking, including setup or turnaround.",
                    "Resolve the venue clash with Venue Staff"))
        if attendance_changed and int(proposed["expected_attendance"]) > int(venue["capacity"]):
            items.append(_item("venue_booking", booking_id, "capacity",
                f"{venue.get('name', 'Venue')} holds {venue['capacity']} people; the proposal expects {proposed['expected_attendance']}.",
                "Choose a suitable venue or revise the plan"))
        if venue_changed:
            for field, venue_field in (("required_facilities", "facilities"), ("required_accessibility", "accessibility")):
                missing = sorted(set(proposed.get(field) or []) - set(venue.get(venue_field) or []))
                if missing:
                    items.append(_item("venue_booking", booking_id, field,
                        f"The venue lacks {field.replace('_', ' ')}: {', '.join(missing)}.",
                        "Confirm a suitable venue or replacement"))
            layout = proposed.get("room_layout")
            if layout and layout not in (venue.get("room_layouts") or []):
                items.append(_item("venue_booking", booking_id, "layout",
                    f"The venue does not offer the proposed {layout} layout.",
                    "Confirm a suitable layout or replacement"))
            if accepted.get("special_requirements") != proposed.get("special_requirements"):
                items.append(_item("venue_booking", booking_id, "special_requirements",
                    "Special venue requirements changed and need Venue Staff review.",
                    "Confirm the new requirements with Venue Staff"))

    if attendance_changed:
        safety = _item("safety", str(event["id"]), "attendance",
            "Attendance changed; the previous safety review does not cover the new number.",
            "Complete a fresh Operational Safety Check")
        safety["status"] = "informational"
        items.append(safety)

    catalogue_by_id = {str(row["id"]): row for row in catalogue}
    live_current = {str(row["equipment_item_id"]): row for row in current_equipment}
    overlapping_ids = {str(row["id"]) for row in overlapping_events if str(row["id"]) != str(event["id"])}
    reserved: dict[str, int] = {}
    for row in overlapping_requirements:
        if str(row["event_id"]) in overlapping_ids:
            identity = str(row["equipment_item_id"])
            reserved[identity] = reserved.get(identity, 0) + int(row["required_quantity"])
    for identity in sorted(set(old_equipment) | set(new_equipment)):
        changed = old_equipment.get(identity) != new_equipment.get(identity)
        if not changed and not window_changed:
            continue
        item = catalogue_by_id.get(str(identity)) or (live_current.get(str(identity), {}).get("equipment") or {})
        reason = "The required quantity or item changed; revalidate its preparation and reservation."
        if window_changed and not changed:
            reason = "The event window changed; revalidate this item's availability and preparation."
        if changed and identity not in catalogue_by_id:
            reason = "The changed item is not active and available in the live catalogue."
        elif item and new_equipment.get(identity, 0) + reserved.get(str(identity), 0) > int(item.get("total_quantity") or 0):
            reason = "The proposed requirement exceeds the live available quantity for the new window."
        items.append(_item("equipment", str(identity), "requirement", reason,
            "Revalidate live quantity and obtain any required Technical Support decision"))

    if event.get("assigned_technical_support_id") and (window_changed or equipment_changed):
        technical_id = str(event["assigned_technical_support_id"])
        reason = "Technical Support's prior assignment or sign-off covers the old arrangement."
        if technical_conflict:
            reason = "Technical Support has another assignment in the proposed window."
        items.append(_item("technical_support", technical_id, "assignment", reason,
            "Review schedule and obtain a fresh authoritative sign-off where needed"))
    return items
