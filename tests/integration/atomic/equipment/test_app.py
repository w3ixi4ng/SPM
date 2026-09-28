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


# --- TC-EQUIPMENT-103 ----------------------------------------------------
def test_updated_item_is_immediate_and_preserves_requirement(
    admin, make_session, equipment_ids
):
    staff = make_session("technical_support")
    coordinator = make_session("event_coordinator")
    suffix = uuid.uuid4().hex[:8]
    event_id = str(uuid.uuid4())
    original = {
        "type": f"spm-test S41 Microphone {suffix}",
        "description": "Before S-41",
        "total_quantity": 12,
    }

    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=staff["headers"]
    ) as gateway:
        created = gateway.post("/equipment", json=original)
        assert created.status_code == 201, created.text
        item_id = created.json()["id"]
        equipment_ids.append(item_id)

    with httpx.Client(base_url=BASE_URL, timeout=15.0) as internal:
        created_requirement = internal.put(
            f"/internal/equipment-requirements/{event_id}/{item_id}",
            json={
                "required_quantity": 6,
                "recorded_by_coordinator_id": coordinator["user_id"],
            },
        )
        assert created_requirement.status_code == 200, created_requirement.text
        before = created_requirement.json()

    unavailable = {
        "type": f"spm-test S41 Radio Microphone {suffix}",
        "description": "Updated by S-41",
        "total_quantity": 18,
        "operational_status": "unavailable",
    }
    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=staff["headers"]
    ) as gateway:
        detail = gateway.get(f"/equipment/{item_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["type"] == original["type"]

        updated = gateway.put(f"/equipment/{item_id}", json=unavailable)
        assert updated.status_code == 200, updated.text
        assert {
            key: updated.json()[key] for key in unavailable
        } == unavailable

        catalogue = gateway.get("/equipment")
        assert catalogue.status_code == 200, catalogue.text
        row = next(item for item in catalogue.json() if item["id"] == item_id)
        assert {key: row[key] for key in unavailable} == unavailable

    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=coordinator["headers"]
    ) as gateway:
        selection = gateway.get("/equipment/selection")
        assert selection.status_code == 200, selection.text
        assert item_id not in {item["id"] for item in selection.json()}

    with httpx.Client(base_url=BASE_URL, timeout=15.0) as internal:
        requirements = internal.get(
            "/internal/equipment-requirements", params={"event_id": event_id}
        )
        assert requirements.status_code == 200, requirements.text
        after = requirements.json()[0]

    for field in ("id", "event_id", "equipment_item_id", "required_quantity"):
        assert after[field] == before[field]
    assert after["equipment"]["type"] == unavailable["type"]
    assert after["equipment"]["description"] == unavailable["description"]
    assert after["equipment"]["total_quantity"] == 18
    assert after["equipment"]["operational_status"] == "unavailable"

    maintenance = {**unavailable, "operational_status": "maintenance"}
    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=staff["headers"]
    ) as gateway:
        updated = gateway.put(f"/equipment/{item_id}", json=maintenance)
        assert updated.status_code == 200, updated.text

    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=coordinator["headers"]
    ) as gateway:
        selection = gateway.get("/equipment/selection")
        assert selection.status_code == 200, selection.text
        assert item_id not in {item["id"] for item in selection.json()}

    stored = (
        admin.schema("equipment")
        .table("requirements")
        .select("*")
        .eq("id", before["id"])
        .execute()
        .data
    )
    assert len(stored) == 1
    assert stored[0]["event_id"] == event_id
    assert stored[0]["equipment_item_id"] == item_id
    assert stored[0]["required_quantity"] == 6
