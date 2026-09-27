"""Schema tests for S-39 equipment catalogue input."""

import pytest
from pydantic import ValidationError

from .conftest import EquipmentCreate


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
