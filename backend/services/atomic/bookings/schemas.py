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

# S-36 creates pending requests; S-37 records final staff decisions. S-78: a
# booking whose replacement is confirmed becomes `replaced`. Keep in step with
# backend/sql/bookings.sql.
BookingStatus = Literal["pending", "held", "confirmed", "rejected", "replaced"]
VenuePreparationStatus = Literal["not_started", "in_progress", "ready"]
HoldReleaseReason = Literal[
    "staff_released",
    "event_rejected",
    "event_cancelled",
    "booking_replaced",
    "expired",
]


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
    # S-78: the booking this request replaces, for the same event.
    replaces_booking_id: UUID | None = None

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


class BookingChange(BaseModel):
    """S-80: a Coordinator moves one booking. Only where and when it is, and
    its notes; the event snapshot stays as it was taken. venue_name is
    looked up by the composite, never taken from the browser."""

    model_config = ConfigDict(extra="forbid")

    venue_id: UUID
    venue_name: str = Field(min_length=1)
    booking_date: date
    start_time: time
    end_time: time
    notes: str | None = None

    @field_validator("venue_name", mode="before")
    @classmethod
    def strip_venue_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("notes", mode="before")
    @classmethod
    def blank_notes_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def end_must_follow_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class BookingRead(BaseModel):
    decision_reason: str | None = None
    decision_alternative: str | None = None
    decided_by: UUID | None = None
    decided_at: datetime | None = None
    held_by: UUID | None = None
    held_at: datetime | None = None
    hold_expires_at: datetime | None = None
    hold_released_at: datetime | None = None
    hold_release_reason: HoldReleaseReason | None = None
    venue_preparation_status: VenuePreparationStatus = "not_started"
    venue_preparation_updated_by: UUID | None = None
    venue_preparation_updated_at: datetime | None = None
    venue_preparation_version: int = 0
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
    # S-78
    replaces_booking_id: UUID | None = None
    replaced_by_booking_id: UUID | None = None
    replaced_at: datetime | None = None
    alternative_resolved_at: datetime | None = None
    alternative_resolved_by: UUID | None = None
    alternative_resolution_note: str | None = None


class VenuePreparationUpdate(BaseModel):
    """S-25 state plus the version the staff member loaded.

    Audit identity and time are deliberately absent and extra fields are
    rejected: both are owned by the service.
    """

    model_config = ConfigDict(extra="forbid")

    status: VenuePreparationStatus
    expected_version: int = Field(ge=0)


# S-77: why Venue Staff marked a venue unavailable. Keep in step with
# backend/sql/bookings.sql.
BlockReason = Literal["maintenance", "equipment_failure", "renovation", "safety", "other"]


class BlockCreate(BaseModel):
    """S-77: a period a venue cannot be used, from start_date + start_time up
    to, but not including, end_date + end_time. venue_name is a snapshot the
    venue_bookings composite takes from the venues service, for messages.
    created_by and created_at are forbidden: this service sets both from the
    verified session and the clock.
    """

    model_config = ConfigDict(extra="forbid")

    venue_id: UUID
    venue_name: str = Field(min_length=1)
    start_date: date
    start_time: time
    end_date: date
    end_time: time
    reason: BlockReason
    note: str | None = None

    @field_validator("venue_name", mode="before")
    @classmethod
    def strip_venue_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("note", mode="before")
    @classmethod
    def blank_note_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def valid_block(self):
        start = datetime.combine(self.start_date, self.start_time)
        end = datetime.combine(self.end_date, self.end_time)
        if end <= start:
            raise ValueError("The period must end after it starts")
        if self.reason == "other" and self.note is None:
            raise ValueError("Add a description when the reason is other")
        return self


class BlockRead(BaseModel):
    id: UUID
    venue_id: UUID
    venue_name: str
    start_date: date
    start_time: time
    end_date: date
    end_time: time
    reason: BlockReason
    note: str | None
    created_by: UUID
    created_at: datetime


class BookingDecision(BaseModel):
    """Final decision only; request snapshots and audit fields are server-owned."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    reason: str | None = None
    alternative: str | None = None

    @field_validator("reason", "alternative", mode="before")
    @classmethod
    def trim_explanation(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def rejection_needs_explanation(self):
        if self.decision == "rejected" and not (self.reason or self.alternative):
            raise ValueError("Provide a reason or alternative to reject this request")
        return self


class HoldRelease(BaseModel):
    """Why an active hold is released. The caller and timestamp are trusted
    service data and therefore cannot be supplied in this payload."""

    model_config = ConfigDict(extra="forbid")

    reason: HoldReleaseReason


class HoldCreate(BaseModel):
    """A hold always ends at an explicit, timezone-aware instant."""

    model_config = ConfigDict(extra="forbid")

    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def expiry_has_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must include a timezone")
        return value


class AlternativeResolution(BaseModel):
    """S-78: what a Coordinator arranged instead, for a booking an unavailable
    period affects. Who resolved it and when are set by this service."""

    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value):
        return value.strip() if isinstance(value, str) else value
