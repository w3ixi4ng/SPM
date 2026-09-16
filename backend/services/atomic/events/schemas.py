from datetime import date, datetime, time
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator


class EventStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"


# Shared by EventDraftCreate and EventSubmittedCreate: end_date, if set, may
# never be before start_date. end_time only has to be after start_time when
# the event stays on one calendar day -- a multi-day event (end_date after
# start_date) may end at a clock time earlier than it started.
def _check_end_after_start(start_date, start_time, end_date, end_time):
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    same_day = start_date is None or end_date is None or start_date == end_date
    if same_day and start_time is not None and end_time is not None and end_time <= start_time:
        raise ValueError("end_time must be after start_time")


class EventDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    purpose: str | None = None
    start_date: date | None = None
    start_time: time | None = None
    end_date: date | None = None
    end_time: time | None = None
    expected_attendance: PositiveInt | None = None
    venue: str | None = None
    equipment_requests: dict[str, PositiveInt] = Field(default_factory=dict)
    accessibility_requirements: str | None = None
    special_requirements: str | None = None

    @field_validator(
        "name",
        "purpose",
        "venue",
        "accessibility_requirements",
        "special_requirements",
        mode="before",
    )
    @classmethod
    def normalise_optional_text(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def end_must_follow_start(self):
        _check_end_after_start(self.start_date, self.start_time, self.end_date, self.end_time)
        return self


class EventDraftUpdate(EventDraftCreate):
    pass


class EventSubmittedCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    purpose: str
    start_date: date
    start_time: time
    end_date: date
    end_time: time
    expected_attendance: PositiveInt
    venue: str
    equipment_requests: dict[str, PositiveInt] = Field(default_factory=dict)
    accessibility_requirements: str | None = None
    special_requirements: str | None = None

    @field_validator(
        "name",
        "purpose",
        "venue",
        "accessibility_requirements",
        "special_requirements",
        mode="before",
    )
    @classmethod
    def normalise_text(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def end_must_follow_start(self):
        _check_end_after_start(self.start_date, self.start_time, self.end_date, self.end_time)
        return self


class EventRead(BaseModel):
    id: UUID
    organiser_id: UUID
    status: EventStatus
    name: str | None
    purpose: str | None
    start_date: date | None
    start_time: time | None
    end_date: date | None
    end_time: time | None
    expected_attendance: int | None
    venue: str | None
    equipment_requests: dict[str, int]
    accessibility_requirements: str | None
    special_requirements: str | None
    # Null while the request is a draft. With organiser_id this is the record
    # of who submitted it and when.
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
