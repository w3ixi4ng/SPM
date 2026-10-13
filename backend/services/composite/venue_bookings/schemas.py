"""Request schema for the venue_bookings composite service.

This composite checks the Coordinator's request itself before spending a call
on any downstream service (see TC-VENUEBOOKINGS-004).

There is no response schema here: the bookings service already shaped the
booking it hands back, so this composite returns that JSON as-is.
"""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


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
