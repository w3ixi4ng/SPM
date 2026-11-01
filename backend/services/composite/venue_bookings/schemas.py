"""Request schema for the venue_bookings composite service.

This composite checks the Coordinator's request itself before spending a call
on any downstream service (see TC-VENUEBOOKINGS-004).

There is no response schema here: the bookings service already shaped the
booking it hands back, so this composite returns that JSON as-is.
"""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VenueBookingChange(BaseModel):
    """S-80: where and when one booking now is, and its notes. The event is
    the booking's own, so there is no event_id; the venue's name is looked up
    by this service."""

    model_config = ConfigDict(extra="forbid")

    venue_id: UUID
    booking_date: date
    start_time: time
    end_time: time
    notes: str | None = None

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


class VenueBookingRequest(BaseModel):
    """What a Coordinator chooses: the venue, the date and time, and notes.
    Everything else on the booking -- the event's name, purpose, attendance
    and venue requirements, the venue's name, the Coordinator's own name and
    email -- is looked up by this service, never taken from the browser. The
    requirements belong to the event (S-36): the organiser gives them.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    venue_id: UUID
    booking_date: date
    start_time: time
    end_time: time
    notes: str | None = None

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


# S-30: repeated from the bookings service's schemas.py (each Docker image
# holds only its own service's code). Keep in step with it and with
# backend/sql/bookings.sql.
BlockReason = Literal["maintenance", "equipment_failure", "renovation", "safety", "other"]


class BlockRequest(BaseModel):
    """What Venue Staff choose when marking a venue unavailable. The venue's
    name is looked up from the venues service and who added it comes from the
    session -- neither is taken from the browser."""

    model_config = ConfigDict(extra="forbid")

    venue_id: UUID
    start_date: date
    start_time: time
    end_date: date
    end_time: time
    reason: BlockReason
    note: str | None = None

    @field_validator("note", mode="before")
    @classmethod
    def blank_note_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def valid_block(self):
        # S-77: a timed period, ending after it starts. The bookings service
        # checks the same again.
        start = datetime.combine(self.start_date, self.start_time)
        end = datetime.combine(self.end_date, self.end_time)
        if end <= start:
            raise ValueError("The period must end after it starts")
        if self.reason == "other" and self.note is None:
            raise ValueError("Add a description when the reason is other")
        return self


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


class HoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def future_timezone_aware_expiry(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must include a timezone")
        if value <= datetime.now(value.tzinfo):
            raise ValueError("The hold expiry must be in the future")
        return value


class VenuePreparationRequest(BaseModel):
    """S-25: one booking's preparation state and optimistic version."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["not_started", "in_progress", "ready"]
    expected_version: int = Field(ge=0)


class ReplacementRequest(BaseModel):
    """S-78: what a Coordinator chooses for a replacement -- the venue, and
    notes. The date and times are the affected booking's, and everything else
    is the event's, so neither is taken from the browser."""

    model_config = ConfigDict(extra="forbid")

    venue_id: UUID
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def blank_notes_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class ResolutionRequest(BaseModel):
    """S-78: what a Coordinator arranged instead of replacing the venue."""

    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value):
        return value.strip() if isinstance(value, str) else value


class RestoreDecision(BaseModel):
    """S-90: Venue Staff confirm or decline a Coordinator's restore request."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "declined"]
