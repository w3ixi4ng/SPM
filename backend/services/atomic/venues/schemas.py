from datetime import datetime, time
from typing import Literal, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# The fixed option sets. Every venue chooses from these and nothing else; the
# API rejects any other value, GET /venues/options serves them to the form,
# and backend/sql/venues.sql repeats them as check constraints. Adding an
# option means changing it here AND there, then re-running the SQL.
Facility = Literal[
    "projector",
    "screen",
    "sound_system",
    "microphones",
    "wifi",
    "stage",
    "whiteboard",
    "video_conferencing",
    "catering_kitchen",
    "air_conditioning",
    "parking",
]
AccessibilityFeature = Literal[
    "wheelchair_access",
    "step_free_entrance",
    "accessible_toilets",
    "lift",
    "hearing_loop",
    "accessible_parking",
]
RoomLayout = Literal[
    "theatre",
    "classroom",
    "boardroom",
    "u_shape",
    "banquet",
    "cocktail",
]
Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

FACILITIES: tuple[str, ...] = get_args(Facility)
ACCESSIBILITY_FEATURES: tuple[str, ...] = get_args(AccessibilityFeature)
ROOM_LAYOUTS: tuple[str, ...] = get_args(RoomLayout)
DAYS: tuple[str, ...] = get_args(Day)

# Postgres `integer`. Not a business limit -- just keeps an absurd capacity a
# readable 422 instead of an out-of-range error from the database.
MAX_CAPACITY = 2_147_483_647


def _unique_in_order(values: list) -> list:
    return list(dict.fromkeys(values))


class OpeningHours(BaseModel):
    day: Day
    open: time
    close: time

    @model_validator(mode="after")
    def close_must_follow_open(self):
        if self.close <= self.open:
            raise ValueError("close must be after open")
        return self


class VenueCreate(BaseModel):
    # Unknown fields are dropped rather than rejected, so a client-supplied
    # created_by is simply ignored -- the service sets it from the session.
    name: str = Field(min_length=1)
    location: str = Field(min_length=1)
    capacity: int = Field(ge=1, le=MAX_CAPACITY)
    facilities: list[Facility] = Field(default_factory=list)
    accessibility: list[AccessibilityFeature] = Field(default_factory=list)
    room_layouts: list[RoomLayout] = Field(min_length=1)
    operating_hours: list[OpeningHours] = Field(min_length=1)
    description: str | None = None
    # S-75: minutes needed before an event to prepare the venue and after it
    # to reset it. Whole minutes, 0 or more; strict, so "30" and 1.5 are
    # refused rather than coerced.
    setup_minutes: int = Field(default=0, ge=0, strict=True)
    turnaround_minutes: int = Field(default=0, ge=0, strict=True)

    @field_validator("name", "location", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def blank_description_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("facilities", "accessibility", "room_layouts")
    @classmethod
    def drop_duplicates(cls, value: list) -> list:
        return _unique_in_order(value)

    @field_validator("operating_hours")
    @classmethod
    def one_window_per_day(cls, value: list[OpeningHours]) -> list[OpeningHours]:
        seen: set[str] = set()
        for hours in value:
            if hours.day in seen:
                raise ValueError(f"{hours.day} is listed more than once")
            seen.add(hours.day)
        return sorted(value, key=lambda hours: DAYS.index(hours.day))


class VenueUpdate(BaseModel):
    """Only S-28 fields and S-75's times; omitted values are preserved,
    explicit nulls refused."""

    model_config = ConfigDict(extra="forbid")

    location: str = Field(default=None, min_length=1)
    capacity: int = Field(default=None, ge=1, le=MAX_CAPACITY, strict=True)
    facilities: list[Facility] = Field(default=None)
    accessibility: list[AccessibilityFeature] = Field(default=None)
    setup_minutes: int = Field(default=None, ge=0, strict=True)
    turnaround_minutes: int = Field(default=None, ge=0, strict=True)

    @field_validator("location", mode="before")
    @classmethod
    def strip_location(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("facilities", "accessibility")
    @classmethod
    def drop_duplicates(cls, value):
        return _unique_in_order(value)

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one editable venue field")
        return self


class VenueRead(BaseModel):
    id: UUID
    name: str
    location: str
    capacity: int
    facilities: list[str]
    accessibility: list[str]
    room_layouts: list[str]
    operating_hours: list[OpeningHours]
    description: str | None
    # Defaults keep a row from before the S-75 columns readable.
    setup_minutes: int = 0
    turnaround_minutes: int = 0
    created_by: UUID
    created_at: datetime


class VenueOptions(BaseModel):
    facilities: list[str]
    accessibility: list[str]
    room_layouts: list[str]
    days: list[str]
