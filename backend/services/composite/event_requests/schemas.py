"""Request schema for the event_requests composite service.

This is a deliberate, small duplicate of the events service's
``EventSubmittedCreate`` (see
``backend/services/atomic/events/schemas.py``) -- not an import across
services. Each Docker image only ever contains its own service's code, and
this composite validates the organiser's submission itself, before spending a
call on either downstream service (see TC-EVENTREQUESTS-004).

There is no response schema here: the events service already validated and
shaped the event it hands back, so this composite returns that JSON as-is.
"""

from datetime import date, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator

# S-36: the venue catalogue's sets, as in the events service.
RoomLayout = Literal["theatre", "classroom", "boardroom", "u_shape", "banquet", "cocktail"]
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


def _check_end_after_start(start_date, start_time, end_date, end_time):
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    same_day = start_date is None or end_date is None or start_date == end_date
    if same_day and start_time is not None and end_time is not None and end_time <= start_time:
        raise ValueError("end_time must be after start_time")


class EventRequestSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    purpose: str
    start_date: date
    start_time: time
    end_date: date
    end_time: time
    expected_attendance: PositiveInt
    # S-36: only a preference -- the Coordinator books the actual venue.
    venue: str | None = None
    special_requirements: str | None = None
    room_layout: RoomLayout | None = None
    required_facilities: list[Facility] = Field(default_factory=list)
    required_accessibility: list[AccessibilityFeature] = Field(default_factory=list)

    @field_validator(
        "name",
        "purpose",
        "venue",
        "special_requirements",
        "room_layout",
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


# Mirrors the events service's EventDraftUpdate: every field optional, same
# normalisation, but the cross-field date/time check only fires when the
# relevant pair is present -- a PATCH may touch just one of them. Used by
# PATCH /event-requests/{event_id} to validate the organiser's edit before
# any downstream call, the same reason EventRequestSubmit exists.
class EventRequestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    purpose: str | None = None
    start_date: date | None = None
    start_time: time | None = None
    end_date: date | None = None
    end_time: time | None = None
    expected_attendance: PositiveInt | None = None
    venue: str | None = None
    special_requirements: str | None = None
    room_layout: RoomLayout | None = None
    required_facilities: list[Facility] | None = None
    required_accessibility: list[AccessibilityFeature] | None = None

    @field_validator(
        "name",
        "purpose",
        "venue",
        "special_requirements",
        "room_layout",
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


class TechnicalSupportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    support_details: str | None = None

    @field_validator("support_details", mode="before")
    @classmethod
    def normalise_details(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class CoordinatorAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinator_id: UUID


class CoordinatorReassignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinator_id: UUID
    expected_coordinator_id: UUID
    expected_assignment_version: int = Field(ge=0)


class CancellationDecision(BaseModel):
    """S-61: the Coordinator's decision on a cancellation request. Only the
    shape is checked here; the events service enforces the rules (a reason
    when declining, none when approving) and answers with its own 422."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "declined"]
    reason: str | None = None
