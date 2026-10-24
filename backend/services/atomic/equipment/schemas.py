from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator

OperationalStatus = Literal["available", "unavailable", "maintenance"]
LifecycleStatus = Literal["active", "retired"]


class EquipmentCreate(BaseModel):
    """Client-owned fields for a new equipment type/pool."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    description: str | None = None
    total_quantity: PositiveInt

    @field_validator("type", mode="before")
    @classmethod
    def strip_type(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def blank_description_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class EquipmentUpdate(BaseModel):
    """Complete set of catalogue fields Technical Support may edit."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    description: str | None = None
    total_quantity: PositiveInt
    operational_status: OperationalStatus

    @field_validator("type", mode="before")
    @classmethod
    def strip_type(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def blank_description_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class EquipmentRead(BaseModel):
    id: UUID
    type: str
    description: str | None
    total_quantity: int
    operational_status: OperationalStatus
    lifecycle_status: LifecycleStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class EquipmentRequirementWrite(BaseModel):
    """Internal payload from the equipment_requirements composite."""

    model_config = ConfigDict(extra="forbid")

    required_quantity: PositiveInt
    recorded_by_coordinator_id: UUID


class EquipmentRequirementRemove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded_by_coordinator_id: UUID


class EquipmentRequirementRead(BaseModel):
    id: UUID
    event_id: UUID
    equipment_item_id: UUID
    required_quantity: int
    recorded_by_coordinator_id: UUID
    created_at: datetime
    updated_at: datetime


class EquipmentRequirementItem(BaseModel):
    id: UUID
    type: str
    description: str | None
    total_quantity: int
    operational_status: OperationalStatus
    lifecycle_status: LifecycleStatus


class EquipmentRequirementDetail(EquipmentRequirementRead):
    equipment: EquipmentRequirementItem
