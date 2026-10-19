"""Integration tests for S-40 and S-43 -- see TEST_CASES.md."""

import httpx
import uuid

from .conftest import GATEWAY_BASE_URL, _make_user, cookie_for, requires_env

pytestmark = requires_env


# --- TC-EQUIPMENTREQUIREMENTS-101 -----------------------------------------
def test_coordinator_records_edits_and_deletes_requirement_visible_to_support(admin, auth_client, world):
    coordinator = cookie_for(auth_client, world["coordinator"])
    support = cookie_for(auth_client, world["support"])
    path = f"{GATEWAY_BASE_URL}/equipment-requirements/{world['event_id']}/{world['equipment_id']}"

    created = httpx.put(path, headers=coordinator, json={"required_quantity": 2, "impact_accepted": True}, timeout=15.0)
    assert created.status_code == 200, created.text
    assert created.json()["required_quantity"] == 2

    edited = httpx.put(path, headers=coordinator, json={"required_quantity": 4, "impact_accepted": True}, timeout=15.0)
    assert edited.status_code == 200, edited.text
    assert edited.json()["required_quantity"] == 4

    visible = httpx.get(f"{GATEWAY_BASE_URL}/equipment-requirements", headers=support, timeout=15.0)
    assert visible.status_code == 200, visible.text
    matching = [row for row in visible.json() if row["event_id"] == world["event_id"]]
    assert len(matching) == 1
    assert matching[0]["equipment"]["id"] == world["equipment_id"]
    assert matching[0]["required_quantity"] == 4

    removed = httpx.delete(f"{path}?impact_accepted=true", headers=coordinator, timeout=15.0)
    assert removed.status_code == 204, removed.text
    rows = admin.schema("equipment").table("requirements").select("id").eq("event_id", world["event_id"]).execute()
    assert rows.data == []
    history = admin.schema("equipment").table("requirement_changes").select(
        "action,before_quantity,after_quantity,changed_by"
    ).eq("event_id", world["event_id"]).order("changed_at").execute().data
    assert [entry["action"] for entry in history] == ["created", "updated", "removed"]
    assert history[0]["after_quantity"] == 2
    assert history[1]["before_quantity"] == 2 and history[1]["after_quantity"] == 4
    assert history[2]["before_quantity"] == 4 and history[2]["after_quantity"] is None
    assert all(entry["changed_by"] == world["coordinator"]["id"] for entry in history)


# --- TC-EQUIPMENTREQUIREMENTS-102 -----------------------------------------
def test_reassignment_uses_current_assignment_not_recorded_by_audit(admin, auth_client, world):
    old_headers = cookie_for(auth_client, world["coordinator"])
    new_headers = cookie_for(auth_client, world["new_coordinator"])
    path = f"{GATEWAY_BASE_URL}/equipment-requirements/{world['event_id']}/{world['equipment_id']}"

    first = httpx.put(path, headers=old_headers, json={"required_quantity": 2, "impact_accepted": True}, timeout=15.0)
    assert first.status_code == 200, first.text
    assert first.json()["recorded_by_coordinator_id"] == world["coordinator"]["id"]

    admin.schema("events").table("events").update({
        "assigned_coordinator_id": world["new_coordinator"]["id"]
    }).eq("id", world["event_id"]).execute()

    refused = httpx.put(path, headers=old_headers, json={"required_quantity": 3, "impact_accepted": True}, timeout=15.0)
    assert refused.status_code == 404, refused.text

    accepted = httpx.put(path, headers=new_headers, json={"required_quantity": 5, "impact_accepted": True}, timeout=15.0)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["required_quantity"] == 5
    assert accepted.json()["recorded_by_coordinator_id"] == world["new_coordinator"]["id"]
    stored = admin.schema("equipment").table("requirements").select("*").eq(
        "event_id", world["event_id"]
    ).eq("equipment_item_id", world["equipment_id"]).execute().data
    assert len(stored) == 1
    assert stored[0]["required_quantity"] == 5
    assert stored[0]["recorded_by_coordinator_id"] == world["new_coordinator"]["id"]


# --- TC-EQUIPMENTREQUIREMENTS-104 -----------------------------------------
def test_support_staff_only_reads_own_active_event_requirements(
    admin, auth_client
):
    support_a = _make_user(admin, "technical_support")
    support_b = _make_user(admin, "technical_support")
    coordinator = _make_user(admin, "event_coordinator")
    organiser = _make_user(admin, "event_organiser")
    users = (support_a, support_b, coordinator, organiser)
    event_ids = []
    equipment_ids = []

    def create_equipment(label: str) -> str:
        equipment_id = admin.schema("equipment").table("equipment").insert({
            "type": f"spm-test S43 {label} {uuid.uuid4().hex[:8]}",
            "description": "S-43 assignment visibility test item",
            "total_quantity": 10,
            "created_by": support_a["id"],
        }).execute().data[0]["id"]
        equipment_ids.append(equipment_id)
        return equipment_id

    def create_event(label: str, status: str, support_id: str) -> str:
        event_id = admin.schema("events").table("events").insert({
            "organiser_id": organiser["id"],
            "assigned_coordinator_id": coordinator["id"],
            "status": status,
            "name": f"spm-test S43 {label}",
            "purpose": "Prove Technical Support assignment isolation",
            "start_date": "2026-11-14",
            "start_time": "09:00",
            "end_date": "2026-11-14",
            "end_time": "12:00",
            "expected_attendance": 60,
            "decision": "approved",
            "decided_at": "2026-10-01T00:00:00Z",
            "submitted_at": "2026-09-30T00:00:00Z",
            "technical_support_required": True,
            "technical_support_details": f"Prepare equipment for {label}",
            "assigned_technical_support_id": support_id,
            "technical_support_assigned_at": "2026-10-01T01:00:00Z",
            # S-17: Confirmed is reached only through the Safety Officer's approval.
            **({"safety_decision": "approved", "safety_officer_id": str(uuid.uuid4()),
                "safety_decided_at": "2026-10-02T00:00:00Z"} if status == "confirmed" else {}),
        }).execute().data[0]["id"]
        event_ids.append(event_id)
        return event_id

    try:
        equipment_a = create_equipment("Support A active")
        equipment_inactive = create_equipment("Support A inactive")
        equipment_b = create_equipment("Support B active")
        active_a = create_event("Support A active", "planning", support_a["id"])
        inactive_a = create_event("Support A inactive", "cancelled", support_a["id"])
        active_b = create_event("Support B active", "confirmed", support_b["id"])

        for event_id, equipment_id, quantity in (
            (active_a, equipment_a, 2),
            (inactive_a, equipment_inactive, 3),
            (active_b, equipment_b, 4),
        ):
            admin.schema("equipment").table("requirements").insert({
                "event_id": event_id,
                "equipment_item_id": equipment_id,
                "required_quantity": quantity,
                "recorded_by_coordinator_id": coordinator["id"],
            }).execute()

        headers_a = cookie_for(auth_client, support_a)
        headers_b = cookie_for(auth_client, support_b)

        events_a = httpx.get(
            f"{GATEWAY_BASE_URL}/events/support-assigned",
            headers=headers_a,
            timeout=15.0,
        )
        assert events_a.status_code == 200, events_a.text
        assert [row["id"] for row in events_a.json()] == [active_a]

        requirements_a = httpx.get(
            f"{GATEWAY_BASE_URL}/equipment-requirements",
            headers=headers_a,
            timeout=15.0,
        )
        assert requirements_a.status_code == 200, requirements_a.text
        assert [(row["event_id"], row["equipment_item_id"]) for row in requirements_a.json()] == [
            (active_a, equipment_a)
        ]

        for hidden_event in (inactive_a, active_b):
            hidden_event_response = httpx.get(
                f"{GATEWAY_BASE_URL}/events/support-assigned/{hidden_event}",
                headers=headers_a,
                timeout=15.0,
            )
            assert hidden_event_response.status_code == 404, hidden_event_response.text

            hidden_requirements = httpx.get(
                f"{GATEWAY_BASE_URL}/equipment-requirements",
                params={"event_id": hidden_event},
                headers=headers_a,
                timeout=15.0,
            )
            assert hidden_requirements.status_code == 404, hidden_requirements.text

        events_b = httpx.get(
            f"{GATEWAY_BASE_URL}/events/support-assigned",
            headers=headers_b,
            timeout=15.0,
        )
        assert events_b.status_code == 200, events_b.text
        assert [row["id"] for row in events_b.json()] == [active_b]

        requirements_b = httpx.get(
            f"{GATEWAY_BASE_URL}/equipment-requirements",
            headers=headers_b,
            timeout=15.0,
        )
        assert requirements_b.status_code == 200, requirements_b.text
        assert [(row["event_id"], row["equipment_item_id"]) for row in requirements_b.json()] == [
            (active_b, equipment_b)
        ]
    finally:
        for event_id in event_ids:
            admin.schema("equipment").table("requirements").delete().eq(
                "event_id", event_id
            ).execute()
        for event_id in event_ids:
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        for equipment_id in equipment_ids:
            admin.schema("equipment").table("equipment").delete().eq(
                "id", equipment_id
            ).execute()
        for user in users:
            admin.auth.admin.delete_user(user["id"])
