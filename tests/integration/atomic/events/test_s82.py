"""TC-EVENTS-203 to -205. Run after the S-82 block of events.sql on .env.test:
the event_history table, its grants and trigger, and backfill_event_history."""

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from postgrest.exceptions import APIError

from .conftest import BASE_URL, requires_env

pytestmark = requires_env


def _event(admin, organiser_id, **changes):
    values = {
        "organiser_id": organiser_id,
        "status": "planning",
        "name": f"spm-test S-82 {uuid.uuid4().hex[:6]}",
        "purpose": "Prove the S-82 history table",
        "start_date": "2026-11-18",
        "start_time": "09:00",
        "end_date": "2026-11-18",
        "end_time": "12:00",
        "expected_attendance": 120,
        "submitted_at": "2026-10-01T01:00:00Z",
        "decision": "approved",
        "decided_at": "2026-10-02T01:00:00Z",
        **changes,
    }
    return admin.schema("events").table("events").insert(values).execute().data[0]["id"]


def _history(event_id):
    response = httpx.get(f"{BASE_URL}/internal/events/{event_id}/history", timeout=20)
    assert response.status_code == 200, response.text
    return response.json()


VENUE_ENTRY = {
    "actor_role": "event_coordinator",
    "action": "venue_requested",
    "details": {"venue_name": "Hall One"},
}


# --- TC-EVENTS-203 ----------------------------------------------------------
def test_an_appended_entry_is_stored_and_read_back(admin, organiser_session):
    coordinator_id = str(uuid.uuid4())
    event_id = _event(admin, organiser_session["user_id"], assigned_coordinator_id=coordinator_id)
    organiser_session["event_ids"].append(event_id)

    appended = httpx.post(
        f"{BASE_URL}/internal/events/{event_id}/history",
        json={**VENUE_ENTRY, "actor_id": coordinator_id},
        timeout=20,
    )
    assert appended.status_code == 201, appended.text
    stored = appended.json()
    occurred = datetime.fromisoformat(stored["occurred_at"].replace("Z", "+00:00"))
    assert abs((datetime.now(timezone.utc) - occurred).total_seconds()) < 60

    assert [(entry["id"], entry["category"]) for entry in _history(event_id)] == [(stored["id"], "venue")]

    admin.schema("events").table("events").delete().eq("id", event_id).execute()
    organiser_session["event_ids"].remove(event_id)
    left = admin.schema("events").table("event_history").select("id").eq("event_id", event_id).execute()
    assert left.data == [], "deleting the event should remove its history"


# --- TC-EVENTS-204 ----------------------------------------------------------
def test_the_database_refuses_to_change_or_delete_an_entry(admin, organiser_session):
    event_id = _event(admin, organiser_session["user_id"])
    organiser_session["event_ids"].append(event_id)
    stored = httpx.post(
        f"{BASE_URL}/internal/events/{event_id}/history",
        json={**VENUE_ENTRY, "actor_id": str(uuid.uuid4())},
        timeout=20,
    ).json()
    history = admin.schema("events").table("event_history")

    with pytest.raises(APIError) as changed:
        history.update({"action": "request_rejected"}).eq("id", stored["id"]).execute()
    assert changed.value.code == "42501"
    with pytest.raises(APIError) as deleted:
        history.delete().eq("id", stored["id"]).execute()
    assert deleted.value.code == "42501"

    [read] = history.select("*").eq("id", stored["id"]).execute().data
    assert read["action"] == "venue_requested"
    assert read["details"] == {"venue_name": "Hall One"}


# --- TC-EVENTS-205 ----------------------------------------------------------
def test_backfill_rebuilds_existing_history_once(admin, organiser_session):
    organiser_id = organiser_session["user_id"]
    coordinator_id, officer_id, lead_id = (str(uuid.uuid4()) for _ in range(3))
    event_id = _event(
        admin, organiser_id,
        assigned_coordinator_id=coordinator_id,
        assigning_lead_id=lead_id,
        edit_history=[{
            "change_number": 1, "changed_by": coordinator_id, "changed_at": "2026-10-03T01:00:00Z",
            "changes": {"expected_attendance": {"before": 120, "after": 150}},
        }],
        safety_review_history=[{
            "review_number": 1, "decision": "changes_requested", "reason": "Fire exit blocked",
            "safety_officer_id": officer_id, "decided_at": "2026-10-04T01:00:00Z",
        }],
    )
    organiser_session["event_ids"].append(event_id)
    requests = admin.schema("events").table("reassignment_requests")
    request_id = requests.insert({
        "event_id": event_id, "event_name": "S-82", "requester_id": coordinator_id,
        "assigning_lead_id": lead_id, "assignment_version": 0, "reason": "Leaving the team",
        "created_at": "2026-10-05T01:00:00Z",
    }).execute().data[0]["id"]

    try:
        backfill = admin.schema("events").rpc("backfill_event_history", {"p_event_id": event_id})
        assert backfill.execute().data == 5
        assert backfill.execute().data == 0

        entries = _history(event_id)
        assert [(entry["action"], entry["actor_id"], entry["occurred_at"][:19]) for entry in entries] == [
            ("reassignment_requested", coordinator_id, "2026-10-05T01:00:00"),
            ("safety_changes_requested", officer_id, "2026-10-04T01:00:00"),
            ("edited", coordinator_id, "2026-10-03T01:00:00"),
            ("request_approved", None, "2026-10-02T01:00:00"),
            ("submitted", organiser_id, "2026-10-01T01:00:00"),
        ]
        assert all(entry["details"]["backfilled"] is True for entry in entries)
    finally:
        requests.delete().eq("id", request_id).execute()
