"""How much of each equipment pool is free for a window (S-44).

Pure functions over the catalogue, the events overlapping the window and
their requirements, exactly as the services return them, so the counting is
testable without HTTP and the route stays thin.

- Reserved: requirements on the overlapping events. The events service only
  returns planning, pending safety check and confirmed events, so rejected,
  returned, draft and submitted events already hold nothing by the time they
  get here.
- Unavailable: the pool-wide operational status. A pool that is
  "unavailable" or "maintenance" has none free for any window.
- Retired items are not part of the check at all.
"""


def _matches(item: dict, type_search: str | None) -> bool:
    if not type_search:
        return True
    return type_search.casefold() in item["type"].casefold()


def _reservation(requirement: dict, event: dict) -> dict:
    return {
        "event_id": event["id"],
        "event_name": event.get("name"),
        "status": event["status"],
        "start_date": event["start_date"],
        "start_time": event["start_time"],
        "end_date": event["end_date"],
        "end_time": event["end_time"],
        "required_quantity": requirement["required_quantity"],
    }


def _item(item: dict, reservations: list[dict], quantity: int | None) -> dict:
    total = item["total_quantity"]
    reserved = sum(reservation["required_quantity"] for reservation in reservations)
    usable = item["operational_status"] == "available"
    unavailable = 0 if usable else total
    # Never below zero: Coordinators can record more than a pool holds.
    available = max(0, total - reserved) if usable else 0
    return {
        "id": item["id"],
        "type": item["type"],
        "operational_status": item["operational_status"],
        "total": total,
        "reserved": reserved,
        "unavailable": unavailable,
        "available": available,
        "over_reserved": reserved > total,
        "sufficient": None if quantity is None else available >= quantity,
        "reservations": reservations,
    }


def items(
    catalogue: list[dict],
    events: list[dict],
    requirements: list[dict],
    *,
    type_search: str | None,
    quantity: int | None,
) -> list[dict]:
    """Every active item matching the search, in catalogue (type) order,
    with its counts for the window and the events holding it in the order
    the events service gave them (start order)."""
    order = {event["id"]: index for index, event in enumerate(events)}
    by_event = {event["id"]: event for event in events}
    held: dict[str, list[tuple[int, dict]]] = {}
    for requirement in requirements:
        event = by_event.get(requirement["event_id"])
        if event is None:
            continue
        held.setdefault(requirement["equipment_item_id"], []).append(
            (order[event["id"]], _reservation(requirement, event))
        )

    return [
        _item(item, [reservation for _, reservation in sorted(held.get(item["id"], []), key=lambda pair: pair[0])], quantity)
        for item in catalogue
        if item.get("lifecycle_status") == "active" and _matches(item, type_search)
    ]


def shortages(event: dict, catalogue: list[dict], events: list[dict], requirements: list[dict]) -> list[dict]:
    """S-17: the event's own requirements that cannot be met in its window --
    what is left once every other overlapping event has taken its share."""
    counted = {
        row["id"]: row
        for row in items(catalogue, events, requirements, type_search=None, quantity=None)
    }
    short = []
    for requirement in requirements:
        if requirement["event_id"] != event["id"]:
            continue
        item = counted.get(requirement["equipment_item_id"])
        if item is None:
            # Retired since it was recorded: nothing of it can be provided.
            available = 0
            name = (requirement.get("equipment") or {}).get("type", "Unknown equipment")
        else:
            others = sum(
                reservation["required_quantity"]
                for reservation in item["reservations"]
                if reservation["event_id"] != event["id"]
            )
            usable = item["operational_status"] == "available"
            available = max(0, item["total"] - others) if usable else 0
            name = item["type"]
        if requirement["required_quantity"] > available:
            short.append({
                "equipment_item_id": requirement["equipment_item_id"],
                "name": name,
                "required": requirement["required_quantity"],
                "available": available,
            })
    return short
