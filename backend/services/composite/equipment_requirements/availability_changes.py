"""Equipment availability changes that newly affect committed events (S-71).

Pure functions over the item, current event assignments and requirements keep
the cross-service rule testable without HTTP.  Venue availability remains in
the venue_bookings composite; this module is deliberately equipment-only.
"""

from datetime import date, datetime, time

KIND = "equipment_unavailable"
COMMITTED_STATUSES = {"confirmed", "preparation"}
BATCH_SIZE = 20


def availability_signature(item: dict) -> tuple:
    """Only fields capable of changing supply participate in S-71."""
    return (
        item.get("operational_status"),
        item.get("lifecycle_status"),
        item.get("total_quantity"),
    )


def _moment(day, clock) -> datetime:
    return datetime.combine(
        date.fromisoformat(str(day)[:10]),
        time.fromisoformat(str(clock).replace("Z", "+00:00")),
    )


def overlaps(left: dict, right: dict) -> bool:
    left_start = _moment(left["start_date"], left["start_time"])
    left_end = _moment(left["end_date"], left["end_time"])
    right_start = _moment(right["start_date"], right["start_time"])
    right_end = _moment(right["end_date"], right["end_time"])
    return left_start < right_end and right_start < left_end


def _usable(item: dict) -> bool:
    return (
        item.get("lifecycle_status") == "active"
        and item.get("operational_status") == "available"
    )


def _short(
    item: dict,
    event: dict,
    required: int,
    committed: list[dict],
    quantities: dict[str, int],
) -> bool:
    if not _usable(item):
        return True
    reserved_by_others = sum(
        quantities.get(str(other["id"]), 0)
        for other in committed
        if str(other["id"]) != str(event["id"]) and overlaps(event, other)
    )
    available = max(0, int(item["total_quantity"]) - reserved_by_others)
    return required > available


def newly_affected(
    before: dict,
    after: dict,
    events: list[dict],
    requirements: list[dict],
) -> list[dict]:
    """Committed events that were supplied before and are short afterwards."""
    committed = [
        event
        for event in events
        if event.get("status") in COMMITTED_STATUSES
        and event.get("assigned_coordinator_id")
    ]
    target = str(after["id"])
    quantities: dict[str, int] = {}
    for requirement in requirements:
        if str(requirement.get("equipment_item_id")) != target:
            continue
        event_id = str(requirement["event_id"])
        quantities[event_id] = quantities.get(event_id, 0) + int(
            requirement["required_quantity"]
        )

    affected = []
    for event in committed:
        required = quantities.get(str(event["id"]), 0)
        if required <= 0:
            continue
        if not _short(before, event, required, committed, quantities) and _short(
            after, event, required, committed, quantities
        ):
            affected.append(event)
    return affected


def _detail(item: dict) -> str:
    if item.get("lifecycle_status") == "retired":
        return "the item was retired"
    if item.get("operational_status") == "maintenance":
        return "the item is under maintenance"
    if item.get("operational_status") == "unavailable":
        return "the item is unavailable"
    return f'available stock was reduced to {item["total_quantity"]}'


def notifications(item: dict, affected: list[dict]) -> list[dict]:
    """One idempotent notice for each event's current Coordinator."""
    change = str(item["updated_at"])
    rows = []
    for event in affected:
        recipient = str(event["assigned_coordinator_id"])
        event_id = str(event["id"])
        event_name = event.get("name") or "your confirmed event"
        item_name = item.get("type") or "Equipment"
        rows.append(
            {
                "recipient_id": recipient,
                "event_id": event_id,
                "event_name": event_name,
                "kind": KIND,
                "message": (
                    f"Equipment availability changed for {item_name}: {_detail(item)}. "
                    f"This affects {event_name}. Arrange replacement equipment "
                    "before the event."
                ),
                "deduplication_key": (
                    f"{KIND}:{item['id']}:{change}:{event_id}:{recipient}"
                ),
            }
        )
    return rows


def batches(rows: list[dict]) -> list[list[dict]]:
    return [
        rows[index : index + BATCH_SIZE]
        for index in range(0, len(rows), BATCH_SIZE)
    ]
