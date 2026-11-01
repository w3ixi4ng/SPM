"""TC-SAFETYCHECKS-104: through the real services, the Safety Officer sees the
safety review's history and nothing else (S-82 AC3)."""

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, _world, cookie_for, requires_env

pytestmark = requires_env


@pytest.fixture
def ready_world(admin):
    """A planning event with every S-17 arrangement already in place --
    seeded directly, so the only history is what the test itself does."""
    for world in _world(admin, event_status="planning", booking_status="confirmed", signed_off=True):
        admin.schema("events").table("events").update({
            "equipment_preparation_status": "ready",
            "equipment_preparation_updated_by": world["support"]["id"],
            "equipment_preparation_updated_at": "2026-10-02T00:00:00Z",
        }).eq("id", world["event_id"]).execute()
        yield world


def test_the_safety_officer_sees_the_safety_history(auth_client, ready_world):
    event_id = ready_world["event_id"]
    coordinator = cookie_for(auth_client, ready_world["coordinator"])
    officer = cookie_for(auth_client, ready_world["officer"])
    edit_url = f"{GATEWAY_BASE_URL}/events/assigned/{event_id}"

    with httpx.Client(timeout=20.0) as api:
        phone = api.patch(edit_url, headers=coordinator, json={"expected_version": 0, "contact_phone": "91234567"})
        assert phone.status_code == 200, phone.text
        significant_edit = {"expected_version": 1, "expected_attendance": 150}
        reviewed = api.post(
            f"{GATEWAY_BASE_URL}/event-requests/{event_id}/information/impact",
            headers=coordinator, json=significant_edit,
        )
        assert reviewed.status_code == 200, reviewed.text
        attendance = api.patch(
            f"{GATEWAY_BASE_URL}/event-requests/{event_id}/information/significant",
            headers=coordinator,
            json={"edit": significant_edit, "impact_ids": [item["id"] for item in reviewed.json()["impacts"]]},
        )
        assert attendance.status_code == 200, attendance.text
        submitted = api.post(f"{GATEWAY_BASE_URL}/safety-checks/coordinator/events/{event_id}/submit", headers=coordinator)
        assert submitted.status_code == 200, submitted.text
        decided = api.post(f"{GATEWAY_BASE_URL}/safety-checks/{event_id}/decision", headers=officer, json={
            "decision": "changes_requested", "reason": "Fire exit blocked",
            "expected_event_updated_at": submitted.json()["updated_at"],
        })
        assert decided.status_code == 200, decided.text

        history = api.get(f"{GATEWAY_BASE_URL}/safety-checks/{event_id}/history", headers=officer)

    assert history.status_code == 200, history.text
    entries = history.json()["entries"]
    assert [(entry["action"], entry["actor"]["id"]) for entry in entries] == [
        ("safety_changes_requested", ready_world["officer"]["id"]),
        ("safety_submitted", ready_world["coordinator"]["id"]),
        ("edited", ready_world["coordinator"]["id"]),
    ]
    assert entries[0]["details"]["reason"] == "Fire exit blocked"
    assert entries[2]["details"]["changes"] == {"expected_attendance": {"before": 120, "after": 150}}
