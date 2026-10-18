"""TC-EQUIPMENTREQUIREMENTS-105. Run after the S-17 events SQL on .env.test."""
import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env

SIGNOFF = (
    "technical_signoff_decision,technical_signoff_reason,"
    "technical_signoff_override_comment,technical_signoff_by,technical_signoff_at"
)


# --- TC-EQUIPMENTREQUIREMENTS-105 -----------------------------------------
def test_signoff_stored_and_cleared_by_change(admin, auth_client, world):
    event_id = world["event_id"]
    requirement = f"{GATEWAY_BASE_URL}/equipment-requirements/{event_id}/{world['equipment_id']}"
    coordinator = cookie_for(auth_client, world["coordinator"])
    support = cookie_for(auth_client, world["support"])

    def signoff():
        return admin.schema("events").table("events").select(SIGNOFF).eq(
            "id", event_id
        ).single().execute().data

    saved = httpx.put(requirement, headers=coordinator, json={"required_quantity": 1}, timeout=20)
    assert saved.status_code == 200, saved.text

    approved = httpx.post(
        f"{GATEWAY_BASE_URL}/equipment-requirements/{event_id}/sign-off",
        headers=support, json={"decision": "approved"}, timeout=20,
    )
    assert approved.status_code == 200, approved.text
    assert signoff()["technical_signoff_decision"] == "approved"
    assert signoff()["technical_signoff_by"] == world["support"]["id"]

    changed = httpx.put(requirement, headers=coordinator, json={"required_quantity": 2}, timeout=20)
    assert changed.status_code == 200, changed.text
    assert all(value is None for value in signoff().values())
