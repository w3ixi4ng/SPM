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
    assert decided.json()["status"] == "preparation"

    stored = admin.schema("events").table("events").select(
        "status,safety_decision,safety_decision_reason,safety_officer_id,safety_decided_at"
    ).eq("id", event_id).single().execute().data
    assert stored["status"] == "preparation"
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
    assert unchanged == {"status": "preparation", "safety_decision": "approved"}

