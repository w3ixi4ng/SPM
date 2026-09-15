from datetime import date, datetime, time
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator


class EventStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"


class EventDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    purpose: str | None = None
    event_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    expected_attendance: PositiveInt | None = None
    venue: str | None = None
    equipment_requests: dict[str, PositiveInt] = Field(default_factory=dict)
    accessibility_requirements: str | None = None

    @field_validator("name", "purpose", "venue", "accessibility_requirements", mode="before")
    @classmethod
    def normalise_optional_text(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def end_must_follow_start(self):
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be after start_time")
        return self


class EventDraftUpdate(EventDraftCreate):
    pass


class EventSubmittedCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    purpose: str
    event_date: date
    start_time: time
    end_time: time
    expected_attendance: PositiveInt
    venue: str
    equipment_requests: dict[str, PositiveInt] = Field(default_factory=dict)
    accessibility_requirements: str | None = None

    @field_validator("name", "purpose", "venue", "accessibility_requirements", mode="before")
    @classmethod
    def normalise_text(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def end_must_follow_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class EventRead(BaseModel):
    id: UUID
    organiser_id: UUID
    status: EventStatus
    name: str | None
    purpose: str | None
    event_date: date | None
    start_time: time | None
    end_time: time | None
    expected_attendance: int | None
    venue: str | None
    equipment_requests: dict[str, int]
    accessibility_requirements: str | None
    created_at: datetime
    updated_at: datetime
