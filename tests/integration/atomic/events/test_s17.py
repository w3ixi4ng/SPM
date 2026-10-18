"""TC-EVENTS-147. Run after the S-17 events SQL on .env.test."""
import uuid

import httpx
import pytest
from postgrest.exceptions import APIError

from .conftest import BASE_URL, requires_env

pytestmark = requires_env


@pytest.fixture
def planning_event(admin):
    support_id = str(uuid.uuid4())
    event_id = admin.schema("events").table("events").insert({
        "organiser_id": str(uuid.uuid4()),
        "assigned_coordinator_id": str(uuid.uuid4()),
        "status": "planning",
        "name": "spm-test S-17 sign-off",
        "purpose": "Prove the S-17 columns",
        "start_date": "2026-11-20",
        "start_time": "09:00",
        "end_date": "2026-11-20",
        "end_time": "17:00",
        "expected_attendance": 10,
        "decision": "approved",
        "decided_at": "2026-10-01T00:00:00Z",
        "submitted_at": "2026-09-30T00:00:00Z",
        "technical_support_required": True,
        "assigned_technical_support_id": support_id,
        "technical_support_assigned_at": "2026-10-01T01:00:00Z",
    }).execute().data[0]["id"]
    try:
        yield {"id": event_id, "support_id": support_id}
    finally:
        admin.schema("events").table("events").delete().eq("id", event_id).execute()


def refused(write):
    with pytest.raises(APIError) as caught:
        write.execute()
    assert caught.value.code == "23514", caught.value


# --- TC-EVENTS-147 --------------------------------------------------------
def test_status_and_signoff_columns(admin, planning_event):
    table = admin.schema("events").table("events")
    event_id = planning_event["id"]

    table.update({"status": "pending_safety_check"}).eq("id", event_id).execute()
    refused(table.update({"status": "pending_safety_check", "decision": None}).eq("id", event_id))
    table.update({"status": "planning"}).eq("id", event_id).execute()

    signed = httpx.put(
        f"{BASE_URL}/internal/events/{event_id}/technical-signoff",
        json={
            "technical_support_id": planning_event["support_id"],
            "decision": "declined",
            "reason": "Only one sound desk exists",
        },
        timeout=20,
    )
    assert signed.status_code == 200, signed.text
    stored = table.select(
        "technical_signoff_decision,technical_signoff_reason,technical_signoff_by,technical_signoff_at"
    ).eq("id", event_id).single().execute().data
    assert stored["technical_signoff_decision"] == "declined"
    assert stored["technical_signoff_reason"] == "Only one sound desk exists"
    assert stored["technical_signoff_by"] == planning_event["support_id"]
    assert stored["technical_signoff_at"] is not None

    refused(table.update({"technical_signoff_reason": None}).eq("id", event_id))
