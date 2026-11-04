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


# --- TC-EQUIPMENT-104 ----------------------------------------------------
def test_retirement_is_idempotent_and_preserves_existing_requirement(
    admin, make_session, equipment_ids
):
    staff = make_session("technical_support")
    coordinator = make_session("event_coordinator")
    suffix = uuid.uuid4().hex[:8]
    original_event_id = str(uuid.uuid4())
    new_event_id = str(uuid.uuid4())
    item = {
        "type": f"spm-test S42 Microphone {suffix}",
        "description": "Retirement integration item",
        "total_quantity": 12,
    }

    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=staff["headers"]
    ) as gateway:
        created = gateway.post("/equipment", json=item)
        assert created.status_code == 201, created.text
        before_item = created.json()
        item_id = before_item["id"]
        equipment_ids.append(item_id)

    with httpx.Client(base_url=BASE_URL, timeout=15.0) as internal:
        created_requirement = internal.put(
            f"/internal/equipment-requirements/{original_event_id}/{item_id}",
            json={
                "required_quantity": 6,
                "recorded_by_coordinator_id": coordinator["user_id"],
            },
        )
        assert created_requirement.status_code == 200, created_requirement.text
        before_requirement = created_requirement.json()

    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=staff["headers"]
    ) as gateway:
        retired = gateway.post(f"/equipment/{item_id}/retire")
        assert retired.status_code == 200, retired.text
        first_retired = retired.json()
        assert first_retired["lifecycle_status"] == "retired"
        assert first_retired["updated_at"] != before_item["updated_at"]

        detail = gateway.get(f"/equipment/{item_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json() == first_retired

        catalogue = gateway.get("/equipment")
        assert catalogue.status_code == 200, catalogue.text
        catalogue_item = next(row for row in catalogue.json() if row["id"] == item_id)
        assert catalogue_item == first_retired

    unchanged = (
        "id",
        "type",
        "description",
        "total_quantity",
        "operational_status",
        "created_by",
        "created_at",
    )
    for field in unchanged:
        assert first_retired[field] == before_item[field]

    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=coordinator["headers"]
    ) as gateway:
        selection = gateway.get("/equipment/selection")
        assert selection.status_code == 200, selection.text
        assert item_id not in {row["id"] for row in selection.json()}

    with httpx.Client(base_url=BASE_URL, timeout=15.0) as internal:
        refused = internal.put(
            f"/internal/equipment-requirements/{new_event_id}/{item_id}",
            json={
                "required_quantity": 3,
                "recorded_by_coordinator_id": coordinator["user_id"],
            },
        )
        assert refused.status_code == 409, refused.text

        requirements = internal.get(
            "/internal/equipment-requirements",
            params={"event_id": original_event_id},
        )
        assert requirements.status_code == 200, requirements.text
        after_requirement = requirements.json()[0]

    for field in ("id", "event_id", "equipment_item_id", "required_quantity"):
        assert after_requirement[field] == before_requirement[field]
    assert after_requirement["equipment"]["lifecycle_status"] == "retired"

    stored_items = (
        admin.schema("equipment")
        .table("equipment")
        .select("*")
        .eq("id", item_id)
        .execute()
        .data
    )
    stored_requirements = (
        admin.schema("equipment")
        .table("requirements")
        .select("*")
        .eq("id", before_requirement["id"])
        .execute()
        .data
    )
    assert len(stored_items) == 1
    assert stored_items[0]["lifecycle_status"] == "retired"
    assert len(stored_requirements) == 1
    assert stored_requirements[0]["event_id"] == original_event_id
    assert stored_requirements[0]["equipment_item_id"] == item_id
    assert stored_requirements[0]["required_quantity"] == 6

    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=staff["headers"]
    ) as gateway:
        repeated = gateway.post(f"/equipment/{item_id}/retire")
        assert repeated.status_code == 200, repeated.text
        assert repeated.json() == first_retired


# --- TC-EQUIPMENT-105 ----------------------------------------------------
def test_storage_location_round_trips_and_can_be_cleared(
    admin, make_session, equipment_ids
):
    staff = make_session("technical_support")
    item = {
        "type": f"spm-test S92 Projector {uuid.uuid4().hex[:8]}",
        "description": "S-92 integration item",
        "storage_location": "Store B, Shelf 4",
        "total_quantity": 3,
    }

    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=staff["headers"]
    ) as gateway:
        created = gateway.post("/equipment", json=item)
        assert created.status_code == 201, created.text
        saved = created.json()
        equipment_ids.append(saved["id"])
        assert saved["storage_location"] == "Store B, Shelf 4"

        updated_payload = {
            "type": item["type"],
            "description": item["description"],
            "storage_location": "AV Cage, Rack 2",
            "total_quantity": item["total_quantity"],
            "operational_status": "available",
        }
        updated = gateway.put(f"/equipment/{saved['id']}", json=updated_payload)
        assert updated.status_code == 200, updated.text
        assert updated.json()["storage_location"] == "AV Cage, Rack 2"

        catalogue = gateway.get("/equipment")
        assert catalogue.status_code == 200, catalogue.text
        row = next(entry for entry in catalogue.json() if entry["id"] == saved["id"])
        assert row["storage_location"] == "AV Cage, Rack 2"

        cleared = gateway.put(
            f"/equipment/{saved['id']}",
            json={**updated_payload, "storage_location": None},
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["storage_location"] is None

    stored = (
        admin.schema("equipment")
        .table("equipment")
        .select("storage_location")
        .eq("id", saved["id"])
        .execute()
        .data
    )
    assert stored == [{"storage_location": None}]
