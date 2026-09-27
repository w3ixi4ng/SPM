"""Schema tests for S-39 equipment catalogue input."""

import pytest
from pydantic import ValidationError

from .conftest import EquipmentCreate, EquipmentRequirementWrite, STAFF_ID


# --- TC-EQUIPMENT-001 ----------------------------------------------------
def test_valid_item_is_normalized_and_server_fields_are_forbidden():
    item = EquipmentCreate(
        type="  Wireless Microphone  ",
        description="  Handheld wireless microphone with receiver  ",
        total_quantity=12,
    )

    assert item.model_dump() == {
        "type": "Wireless Microphone",
        "description": "Handheld wireless microphone with receiver",
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
