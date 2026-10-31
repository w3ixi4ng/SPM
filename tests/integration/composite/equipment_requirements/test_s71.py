"""TC-EQUIPMENTREQUIREMENTS-107: real S-71 service boundaries."""

import uuid

import httpx

from .conftest import GATEWAY_BASE_URL, _make_user, cookie_for, requires_env

pytestmark = requires_env


def test_equipment_change_notifies_the_confirmed_events_current_coordinator(
    admin, auth_client
):
    coordinator = _make_user(admin, "event_coordinator")
    support = _make_user(admin, "technical_support")
    organiser = _make_user(admin, "event_organiser")
    event_id = equipment_id = None
    event_name = f"spm-test S71 Forum {uuid.uuid4().hex[:6]}"
    equipment_name = f"spm-test S71 Projector {uuid.uuid4().hex[:6]}"
    try:
        equipment = admin.schema("equipment").table("equipment").insert(
            {
                "type": equipment_name,
                "description": "S-71 integration item",
                "storage_location": "AV Store",
                "total_quantity": 4,
                "operational_status": "available",
                "lifecycle_status": "active",
                "created_by": support["id"],
            }
        ).execute().data[0]
        equipment_id = equipment["id"]
        event_id = admin.schema("events").table("events").insert(
            {
                "organiser_id": organiser["id"],
                "assigned_coordinator_id": coordinator["id"],
                "status": "confirmed",
                "name": event_name,
                "purpose": "Prove affected equipment notification",
                "start_date": "2026-12-10",
                "start_time": "09:00",
                "end_date": "2026-12-10",
                "end_time": "12:00",
                "expected_attendance": 40,
                "decision": "approved",
                "decided_at": "2026-10-01T00:00:00Z",
                "submitted_at": "2026-09-30T00:00:00Z",
                "safety_decision": "approved",
                "safety_officer_id": str(uuid.uuid4()),
                "safety_decided_at": "2026-10-02T00:00:00Z",
            }
        ).execute().data[0]["id"]
        admin.schema("equipment").table("requirements").insert(
            {
                "event_id": event_id,
                "equipment_item_id": equipment_id,
                "required_quantity": 2,
                "recorded_by_coordinator_id": coordinator["id"],
            }
        ).execute()

        headers = cookie_for(auth_client, support)
        path = f"{GATEWAY_BASE_URL}/equipment-requirements/equipment/{equipment_id}"
        unavailable = {
            "type": equipment_name,
            "description": "S-71 integration item",
            "storage_location": "AV Store",
            "total_quantity": 4,
            "operational_status": "unavailable",
        }
        changed = httpx.put(path, headers=headers, json=unavailable, timeout=20.0)
        assert changed.status_code == 200, changed.text
        assert changed.json()["availability_notifications_sent"] is True

        # The same saved state and a later descriptive edit cannot duplicate it.
        repeated = httpx.put(path, headers=headers, json=unavailable, timeout=20.0)
        assert repeated.status_code == 200, repeated.text
        descriptive = httpx.put(
            path,
            headers=headers,
            json={**unavailable, "storage_location": "AV Cage"},
            timeout=20.0,
        )
        assert descriptive.status_code == 200, descriptive.text

        coordinator_headers = cookie_for(auth_client, coordinator)
        inbox = httpx.get(
            f"{GATEWAY_BASE_URL}/notifications",
            headers=coordinator_headers,
            timeout=20.0,
        )
        assert inbox.status_code == 200, inbox.text
        matching = [
            row
            for row in inbox.json()
            if row["event_id"] == event_id
            and row["kind"] == "equipment_unavailable"
        ]
        assert len(matching) == 1
        assert event_name in matching[0]["message"]
        assert equipment_name in matching[0]["message"]
        assert "Arrange replacement equipment before the event." in matching[0]["message"]
    finally:
        if event_id:
            admin.schema("notifications").table("notifications").delete().eq(
                "event_id", event_id
            ).execute()
            admin.schema("equipment").table("requirements").delete().eq(
                "event_id", event_id
            ).execute()
            admin.schema("events").table("events").delete().eq(
                "id", event_id
            ).execute()
        if equipment_id:
            admin.schema("equipment").table("equipment").delete().eq(
                "id", equipment_id
            ).execute()
        for account in (coordinator, support, organiser):
            admin.auth.admin.delete_user(account["id"])
