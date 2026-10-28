"""Schema tests for S-39 equipment catalogue input."""

import pytest
from pydantic import ValidationError

from .conftest import (
    EquipmentCreate,
    EquipmentRequirementWrite,
    EquipmentUpdate,
    STAFF_ID,
)


# --- TC-EQUIPMENT-001 ----------------------------------------------------
def test_valid_item_is_normalized_and_server_fields_are_forbidden():
    item = EquipmentCreate(
        type="  Wireless Microphone  ",
        description="  Handheld wireless microphone with receiver  ",
        storage_location="  Store B, Shelf 4  ",
        total_quantity=12,
    )

    assert item.model_dump() == {
        "type": "Wireless Microphone",
        "description": "Handheld wireless microphone with receiver",
        "storage_location": "Store B, Shelf 4",
        "total_quantity": 12,
    }

    with pytest.raises(ValidationError) as exc_info:
        EquipmentCreate(
            type="Wireless Microphone",
            total_quantity=12,
            operational_status="maintenance",
            lifecycle_status="retired",
            created_by="11111111-1111-4111-8111-111111111111",
        )

    assert {error["loc"] for error in exc_info.value.errors()} == {
        ("operational_status",),
        ("lifecycle_status",),
        ("created_by",),
    }


# --- TC-EQUIPMENT-002 ----------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    [
        {"total_quantity": 12},
        {"type": "   ", "total_quantity": 12},
        {"type": "Wireless Microphone"},
        {"type": "Wireless Microphone", "total_quantity": 0},
        {"type": "Wireless Microphone", "total_quantity": -1},
        {"type": "Wireless Microphone", "total_quantity": 1.5},
    ],
)
def test_required_fields_and_positive_whole_quantity_are_enforced(payload):
    with pytest.raises(ValidationError):
        EquipmentCreate(**payload)


# --- TC-EQUIPMENT-012 ----------------------------------------------------
@pytest.mark.parametrize("quantity", [0, -1, 1.5])
def test_requirement_quantity_must_be_a_positive_whole_number(quantity):
    with pytest.raises(ValidationError):
        EquipmentRequirementWrite(
            required_quantity=quantity,
            recorded_by_coordinator_id=STAFF_ID,
        )


def test_requirement_payload_forbids_server_relationship_fields():
    with pytest.raises(ValidationError):
        EquipmentRequirementWrite(
            required_quantity=6,
            recorded_by_coordinator_id=STAFF_ID,
            event_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        )


# --- TC-EQUIPMENT-018 ----------------------------------------------------
@pytest.mark.parametrize("status", ["available", "unavailable", "maintenance"])
def test_valid_update_is_normalized(status):
    item = EquipmentUpdate(
        type="  Radio Microphone  ",
        description="   ",
        storage_location="   ",
        total_quantity=18,
        operational_status=status,
    )

    assert item.model_dump() == {
        "type": "Radio Microphone",
        "description": None,
        "storage_location": None,
        "total_quantity": 18,
        "operational_status": status,
    }


# --- TC-EQUIPMENT-019 ----------------------------------------------------
@pytest.mark.parametrize(
    "changes",
    [
        {"type": "   "},
        {"total_quantity": 0},
        {"total_quantity": -1},
        {"total_quantity": 1.5},
        {"operational_status": "damaged"},
        {"id": "22222222-2222-4222-8222-222222222222"},
        {"lifecycle_status": "retired"},
        {"created_by": STAFF_ID},
        {"created_at": "2026-09-28T00:00:00Z"},
        {"updated_at": "2026-09-28T00:00:00Z"},
    ],
)
def test_invalid_updates_are_rejected(changes):
    payload = {
        "type": "Radio Microphone",
        "description": None,
        "storage_location": "AV Cage, Rack 2",
        "total_quantity": 18,
        "operational_status": "available",
        **changes,
    }

    with pytest.raises(ValidationError):
        EquipmentUpdate(**payload)


# --- TC-EQUIPMENT-031 ----------------------------------------------------
def test_storage_location_is_optional_trimmed_and_limited():
    assert EquipmentCreate(
        type="Projector", total_quantity=2, storage_location="  Store A, Bay 9  "
    ).storage_location == "Store A, Bay 9"
    assert EquipmentCreate(
        type="Projector", total_quantity=2, storage_location="   "
    ).storage_location is None

    with pytest.raises(ValidationError) as exc_info:
        EquipmentCreate(
            type="Projector", total_quantity=2, storage_location="x" * 201
        )
    assert exc_info.value.errors()[0]["loc"] == ("storage_location",)
