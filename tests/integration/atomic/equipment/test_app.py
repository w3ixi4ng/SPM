"""Real service/database round trips for the equipment atomic service."""

import uuid

import httpx

from .conftest import BASE_URL, GATEWAY_BASE_URL, requires_env

pytestmark = requires_env


# --- TC-EQUIPMENT-101 ----------------------------------------------------
def test_created_item_is_immediately_available(admin, make_session, equipment_ids):
    staff = make_session("technical_support")
    coordinator = make_session("event_coordinator")
    item = {
        "type": f"spm-test Wireless Microphone {uuid.uuid4().hex[:8]}",
        "description": "Integration microphone",
        "total_quantity": 12,
    }

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=staff["headers"]) as api:
        created = api.post("/equipment", json=item)
        assert created.status_code == 201, created.text
        saved = created.json()
        equipment_ids.append(saved["id"])
        assert saved["created_by"] == staff["user_id"]
        assert saved["operational_status"] == "available"
        assert saved["lifecycle_status"] == "active"

        catalogue = api.get("/equipment")
        assert catalogue.status_code == 200, catalogue.text
        assert saved["id"] in {row["id"] for row in catalogue.json()}

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=coordinator["headers"]) as api:
        selection = api.get("/equipment/selection")
        assert selection.status_code == 200, selection.text
        assert saved["id"] in {row["id"] for row in selection.json()}

        refused = api.post("/equipment", json={**item, "type": f"{item['type']} refused"})
        assert refused.status_code == 403, refused.text

    rows = (
        admin.schema("equipment")
        .table("equipment")
        .select("*")
        .eq("id", saved["id"])
        .execute()
        .data
    )
    assert len(rows) == 1, "no row in equipment.equipment -- check schema exposure and grants"
    assert rows[0]["type"] == item["type"]


# --- TC-EQUIPMENT-102 ----------------------------------------------------
def test_kong_routes_every_s39_operation(make_session, equipment_ids):
    staff = make_session("technical_support")
    item = {
        "type": f"spm-test Gateway Microphone {uuid.uuid4().hex[:8]}",
        "total_quantity": 8,
    }

    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=staff["headers"]
    ) as api:
        health = api.get("/equipment/health")
        assert health.status_code == 200, health.text

        created = api.post("/equipment", json=item)
        assert created.status_code == 201, created.text
        item_id = created.json()["id"]
        equipment_ids.append(item_id)

        catalogue = api.get("/equipment")
        assert catalogue.status_code == 200, catalogue.text
        assert item_id in {row["id"] for row in catalogue.json()}

        selection = api.get("/equipment/selection")
        assert selection.status_code == 200, selection.text
        assert item_id in {row["id"] for row in selection.json()}
