"""S-17 across real services: blocked, arranged, submitted, approved, Confirmed."""

import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env


# --- TC-SAFETYCHECKS-103 ---------------------------------------------------
def test_submission_through_to_confirmed(admin, auth_client, planning_world):
    event_id = planning_world["event_id"]
    coordinator = cookie_for(auth_client, planning_world["coordinator"])
    support = cookie_for(auth_client, planning_world["support"])
    officer = cookie_for(auth_client, planning_world["officer"])
    organiser = cookie_for(auth_client, planning_world["organiser"])
    submit_url = f"{GATEWAY_BASE_URL}/safety-checks/coordinator/events/{event_id}/submit"

    def stored_status():
        return admin.schema("events").table("events").select("status").eq(
            "id", event_id
        ).single().execute().data["status"]

    # 1. Blocked, every outstanding item listed, nothing changed.
    blocked = httpx.post(submit_url, headers=coordinator, timeout=20.0)
    assert blocked.status_code == 409, blocked.text
    assert [item["code"] for item in blocked.json()["outstanding"]] == [
        "venue_missing",
        "venue_awaiting",
        "technical_signoff_awaiting",
        "equipment_preparation",
    ]
    assert stored_status() == "planning"

    # 2. Venue Staff confirm the booking; Technical Support signs off and
    # marks preparation ready.
    admin.schema("bookings").table("bookings").update({
        "status": "confirmed",
        "decided_by": planning_world["venue_staff"]["id"],
        "decided_at": "2026-10-03T00:00:00Z",
    }).eq("event_id", event_id).execute()
    signed = httpx.post(
        f"{GATEWAY_BASE_URL}/equipment-requirements/{event_id}/sign-off",
        headers=support, json={"decision": "approved"}, timeout=20.0,
    )
    assert signed.status_code == 200, signed.text
    ready = httpx.put(
        f"{GATEWAY_BASE_URL}/events/support-assigned/{event_id}/equipment-preparation",
        headers=support, json={"status": "ready"}, timeout=20.0,
    )
    assert ready.status_code == 200, ready.text

    # 3. Submitted.
    submitted = httpx.post(submit_url, headers=coordinator, timeout=20.0)
    assert submitted.status_code == 200, submitted.text
    assert stored_status() == "pending_safety_check"

    # 4. In the Safety Officer's queue.
    queue = httpx.get(f"{GATEWAY_BASE_URL}/safety-checks", headers=officer, timeout=20.0)
    assert queue.status_code == 200, queue.text
    assert event_id in {row["id"] for row in queue.json()}

    # 5. Approved: Confirmed.
    approved = httpx.post(
        f"{GATEWAY_BASE_URL}/safety-checks/{event_id}/decision",
        headers=officer, json={"decision": "approved", "expected_event_updated_at": submitted.json()["updated_at"]}, timeout=20.0,
    )
    assert approved.status_code == 200, approved.text
    assert stored_status() == "confirmed"

    # 6. The Organiser sees it.
    seen = httpx.get(f"{GATEWAY_BASE_URL}/events/{event_id}", headers=organiser, timeout=20.0)
    assert seen.status_code == 200, seen.text
    assert seen.json()["status"] == "confirmed"
