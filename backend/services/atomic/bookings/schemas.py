from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator

# The venue catalogue's fixed option sets, repeated here rather than imported:
# each Docker image holds only its own service's code. A booking's
# room_layout / required_facilities / required_accessibility are compared
# against a venue's own lists, so they must come from the same sets. Keep in
# step with backend/services/atomic/venues/schemas.py and
# backend/sql/bookings.sql.
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

# S-36 only ever creates pending requests. Venue Staff's approve/reject adds
# the other statuses in its own story.
BookingStatus = Literal["pending"]


def _unique_in_order(values: list) -> list:
    return list(dict.fromkeys(values))


class BookingCreate(BaseModel):
    """What the venue_bookings composite sends once it has checked the
    request. The event, venue and coordinator details are a snapshot taken at
    submission -- Venue Staff assess what was asked, even if the event is
    edited afterwards.

    status and submitted_at are forbidden rather than ignored: the service
    sets both, and a caller trying to is a bug worth hearing about.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    venue_id: UUID
    coordinator_id: UUID
    coordinator_name: str = Field(min_length=1)
    # Already verified by the users service; this is a copy, not an input.
    coordinator_email: str = Field(min_length=1)
    booking_date: date
    start_time: time
    end_time: time
    event_name: str = Field(min_length=1)
    event_purpose: str = Field(min_length=1)
    expected_attendance: PositiveInt
    special_requirements: str | None = None
    required_accessibility: list[AccessibilityFeature] = Field(default_factory=list)
    required_facilities: list[Facility] = Field(default_factory=list)
    room_layout: RoomLayout | None = None
    notes: str | None = None
    venue_name: str = Field(min_length=1)

    @field_validator(
        "coordinator_name", "coordinator_email", "event_name", "event_purpose", "venue_name", mode="before"
    )
    @classmethod
    def strip_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("special_requirements", "notes", mode="before")
    @classmethod
    def blank_optional_text_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("required_accessibility", "required_facilities")
    @classmethod
    def drop_duplicates(cls, value: list) -> list:
        return _unique_in_order(value)

    @model_validator(mode="after")
    def end_must_follow_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class BookingRead(BaseModel):
    id: UUID
    event_id: UUID
    venue_id: UUID
    coordinator_id: UUID
    coordinator_name: str
    coordinator_email: str
    status: BookingStatus
    booking_date: date
    start_time: time
    end_time: time
    event_name: str
    event_purpose: str
    expected_attendance: int
    special_requirements: str | None
    required_accessibility: list[str]
    required_facilities: list[str]
    room_layout: str | None
    notes: str | None
    venue_name: str
    submitted_at: datetime
