"""Request schema for the venue_bookings composite service.

The option sets are a deliberate duplicate of the venue catalogue's (see
backend/services/atomic/venues/schemas.py) -- not an import across services.
This composite checks the Coordinator's request itself before spending a call
on any downstream service (see TC-VENUEBOOKINGS-004).

There is no response schema here: the bookings service already shaped the
booking it hands back, so this composite returns that JSON as-is.
"""

from datetime import date, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    "cabaret",
    "cocktail",
]


class VenueBookingRequest(BaseModel):
    """What a Coordinator chooses. Everything else on the booking -- the
    event's name, purpose, attendance and accessibility needs, the venue's
    name, the Coordinator's own name and email -- is looked up by this
    service, never taken from the browser.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    venue_id: UUID
    booking_date: date
    start_time: time
    end_time: time
    room_layout: RoomLayout | None = None
    required_facilities: list[Facility] = Field(default_factory=list)
    required_accessibility: list[AccessibilityFeature] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def blank_notes_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("required_facilities", "required_accessibility")
    @classmethod
    def drop_duplicates(cls, value: list) -> list:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def end_must_follow_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self
