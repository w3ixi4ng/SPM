"""Real S-86 enrichment and lifecycle transition through Kong."""

import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env


def test_safety_officer_reviews_enriched_event_and_approves(
    admin, auth_client, safety_world
):
    headers = cookie_for(auth_client, safety_world["officer"])
    event_id = safety_world["event_id"]

    queue = httpx.get(f"{GATEWAY_BASE_URL}/safety-checks", headers=headers, timeout=20.0)
    assert queue.status_code == 200, queue.text
    assert event_id in {row["id"] for row in queue.json()}

    detail = httpx.get(
        f"{GATEWAY_BASE_URL}/safety-checks/{event_id}", headers=headers, timeout=20.0
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["event"]["expected_attendance"] == 120
    assert body["organiser"]["id"] == safety_world["organiser"]["id"]
    assert body["technical_support"]["id"] == safety_world["support"]["id"]
    assert body["confirmed_venues"][0]["capacity"] == 200
    assert body["equipment_requirements"][0]["required_quantity"] == 4

    decided = httpx.post(
        f"{GATEWAY_BASE_URL}/safety-checks/{event_id}/decision",
        headers=headers,
        json={"decision": "approved"},
        timeout=20.0,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "confirmed"

    stored = admin.schema("events").table("events").select(
        "status,safety_decision,safety_decision_reason,safety_officer_id,safety_decided_at"
    ).eq("id", event_id).single().execute().data
    assert stored["status"] == "confirmed"
    assert stored["safety_decision"] == "approved"
    assert stored["safety_decision_reason"] is None
    assert stored["safety_officer_id"] == safety_world["officer"]["id"]
    assert stored["safety_decided_at"] is not None

    repeated = httpx.post(
        f"{GATEWAY_BASE_URL}/safety-checks/{event_id}/decision",
        headers=headers,
        json={"decision": "rejected", "reason": "Must not overwrite"},
        timeout=20.0,
    )
    assert repeated.status_code == 409, repeated.text
    unchanged = admin.schema("events").table("events").select(
        "status,safety_decision"
    ).eq("id", event_id).single().execute().data
    assert unchanged == {"status": "confirmed", "safety_decision": "approved"}


def test_changes_return_to_planning_and_complete_a_fresh_review_cycle(
    admin, auth_client, safety_world
):
    officer_headers = cookie_for(auth_client, safety_world["officer"])
    coordinator_headers = cookie_for(auth_client, safety_world["coordinator"])
    event_id = safety_world["event_id"]

    before_bookings = admin.schema("bookings").table("bookings").select(
        "id,status"
    ).eq("event_id", event_id).execute().data
    before_requirements = admin.schema("equipment").table("requirements").select(
        "id,required_quantity"
    ).eq("event_id", event_id).execute().data

    returned = httpx.post(
        f"{GATEWAY_BASE_URL}/safety-checks/{event_id}/decision",
        headers=officer_headers,
        json={
            "decision": "changes_requested",
            "reason": "Move speakers away from the emergency exit",
        },
        timeout=20.0,
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "planning"
    assert returned.json()["safety_review_history"][0]["decision"] == "changes_requested"

    detail = httpx.get(
        f"{GATEWAY_BASE_URL}/safety-checks/coordinator/events/{event_id}",
        headers=coordinator_headers,
        timeout=20.0,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["current_return"]["reason"].startswith("Move speakers")
    assert detail.json()["current_return"]["safety_officer"]["id"] == safety_world["officer"]["id"]

    resubmitted = httpx.post(
        f"{GATEWAY_BASE_URL}/safety-checks/coordinator/events/{event_id}/resubmit",
        headers=coordinator_headers,
        timeout=20.0,
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["status"] == "pending_safety_check"
    assert resubmitted.json()["safety_decision"] is None
    assert len(resubmitted.json()["safety_review_history"]) == 1

    assert admin.schema("bookings").table("bookings").select(
        "id,status"
    ).eq("event_id", event_id).execute().data == before_bookings
    assert admin.schema("equipment").table("requirements").select(
        "id,required_quantity"
    ).eq("event_id", event_id).execute().data == before_requirements

    queue = httpx.get(
        f"{GATEWAY_BASE_URL}/safety-checks",
        headers=officer_headers,
        timeout=20.0,
    )
    assert queue.status_code == 200, queue.text
    assert event_id in {row["id"] for row in queue.json()}

    approved = httpx.post(
        f"{GATEWAY_BASE_URL}/safety-checks/{event_id}/decision",
        headers=officer_headers,
        json={"decision": "approved"},
        timeout=20.0,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "confirmed"
    assert [row["decision"] for row in approved.json()["safety_review_history"]] == [
        "changes_requested",
        "approved",
    ]
