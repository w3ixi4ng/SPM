"""TC-EQUIPMENTREQUIREMENTS-103 (S-44): the availability check through Kong."""

import uuid

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, _make_user, cookie_for, requires_env

pytestmark = requires_env

DAY = "2026-11-12"
CHECK = {"start_date": DAY, "start_time": "09:00", "end_date": DAY, "end_time": "12:00"}


@pytest.fixture
def stock(admin):
    """A support account, an organiser, a fresh 10-unit item, and helpers to
    seed events holding it. Everything is deleted afterwards."""
    support = _make_user(admin, "technical_support")
    organiser = _make_user(admin, "event_organiser")
    item_type = f"spm-test S44 Mic {uuid.uuid4().hex[:8]}"
    item_id = admin.schema("equipment").table("equipment").insert({
        "type": item_type, "total_quantity": 10, "created_by": support["id"],
    }).execute().data[0]["id"]
    event_ids: list[str] = []

    def hold(status, start, end, quantity):
        decided = {"decision": "rejected", "decision_reason": "spm-test"} if status == "rejected" else {"decision": "approved"}
        event_id = admin.schema("events").table("events").insert({
            "organiser_id": organiser["id"], "assigned_coordinator_id": organiser["id"],
            "status": status, "name": f"spm-test S44 {status} {start}",
            "purpose": "Availability check", "start_date": DAY, "start_time": start,
            "end_date": DAY, "end_time": end, "expected_attendance": 10,
            "submitted_at": "2026-09-30T00:00:00Z", "decided_at": "2026-10-01T00:00:00Z", **decided,
        }).execute().data[0]["id"]
        event_ids.append(event_id)
        admin.schema("equipment").table("requirements").insert({
            "event_id": event_id, "equipment_item_id": item_id,
            "required_quantity": quantity, "recorded_by_coordinator_id": organiser["id"],
        }).execute()
        return event_id

    try:
        yield {"support": support, "item_type": item_type, "hold": hold}
    finally:
        for event_id in event_ids:
            admin.schema("equipment").table("requirements").delete().eq("event_id", event_id).execute()
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        admin.schema("equipment").table("equipment").delete().eq("id", item_id).execute()
        for user in (support, organiser):
            admin.auth.admin.delete_user(user["id"])


def test_the_availability_check_through_kong_reflects_live_events_and_requirements(auth_client, stock):
    headers = cookie_for(auth_client, stock["support"])
    planning = stock["hold"]("planning", "10:00", "11:00", 3)
    confirmed = stock["hold"]("confirmed", "11:30", "13:00", 2)
    stock["hold"]("rejected", "10:00", "11:00", 4)
    stock["hold"]("planning", "12:00", "13:00", 5)  # back-to-back with the window

    def check():
        response = httpx.get(f"{GATEWAY_BASE_URL}/equipment-requirements/availability", headers=headers,
                             params={**CHECK, "type": stock["item_type"], "quantity": 5}, timeout=20.0)
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert [entry["type"] for entry in items] == [stock["item_type"]]
        return items[0]

    first = check()
    assert (first["reserved"], first["available"], first["sufficient"]) == (5, 5, True)
    assert [r["event_id"] for r in first["reservations"]] == [planning, confirmed]

    stock["hold"]("planning", "09:00", "10:00", 1)
    second = check()
    assert (second["reserved"], second["available"], second["sufficient"]) == (6, 4, False)
