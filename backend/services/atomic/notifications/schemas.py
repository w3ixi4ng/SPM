from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NotificationKind = Literal[
    "event_assignment",
    "event_reassignment",
    "venue_unavailable",
    "venue_hold_expiry",
    "registration_confirmation",
    "waiting_list_promotion",
]


class NotificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_id: UUID
    event_id: UUID
    event_name: str = Field(min_length=1, max_length=200)
    kind: NotificationKind
    message: str = Field(min_length=1, max_length=500)
    deduplication_key: str = Field(min_length=1, max_length=300)

    @field_validator("event_name", "message", "deduplication_key", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class NotificationBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notifications: list[NotificationCreate] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def keys_are_unique(self):
        keys = [item.deduplication_key for item in self.notifications]
        if len(keys) != len(set(keys)):
            raise ValueError("deduplication_key must be unique within the batch")
        return self


class NotificationRead(BaseModel):
    id: int
    recipient_id: UUID
    event_id: UUID
    event_name: str
    kind: NotificationKind
    message: str
    deduplication_key: str
    created_at: datetime
