"""Request schema for the venue_bookings composite service.

This composite checks the Coordinator's request itself before spending a call
on any downstream service (see TC-VENUEBOOKINGS-004).

There is no response schema here: the bookings service already shaped the
booking it hands back, so this composite returns that JSON as-is.
"""

from datetime import date, time
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
