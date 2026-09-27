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
