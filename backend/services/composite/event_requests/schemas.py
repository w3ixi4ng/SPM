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

from datetime import date, datetime, time, timedelta, timezone
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationInfo,
    field_validator,
    model_validator,
)

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


# S-51: as the events service's RegistrationSettings. The period is
# Singapore wall-clock time, stored without a timezone.
SINGAPORE = timezone(timedelta(hours=8))
_REGISTRATION_DATE_PROMPTS = {
    "registration_opens_at": "Choose when registration opens.",
    "registration_closes_at": "Choose when registration closes.",
}


class RegistrationSettings(BaseModel):
    """Whether attendees register, and when. A submission needs both dates
    once registration is on, opening before closing, and closing before the
    event starts. The events service repeats every check on the merged
    record; this copy only spares a doomed call."""

    REGISTRATION_DATES_REQUIRED: ClassVar[bool] = True
    PARTIAL: ClassVar[bool] = False

    registration_required: bool = False
    registration_opens_at: datetime | None = Field(default=None, validate_default=True)
    registration_closes_at: datetime | None = Field(default=None, validate_default=True)

    @field_validator("registration_opens_at", "registration_closes_at")
    @classmethod
    def check_registration_date(cls, value: datetime | None, info: ValidationInfo):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(SINGAPORE).replace(tzinfo=None)
        if not info.data.get("registration_required"):
            return value
        if value is None:
            if cls.REGISTRATION_DATES_REQUIRED:
                raise ValueError(_REGISTRATION_DATE_PROMPTS[info.field_name])
            return value
        if info.field_name == "registration_closes_at":
            opens = info.data.get("registration_opens_at")
            if opens is not None and value <= opens:
                raise ValueError("Registration must close after it opens.")
        return value

    @model_validator(mode="after")
    def registration_closes_before_start(self):
        if not self.registration_required:
            if not self.PARTIAL:
                self.registration_opens_at = None
                self.registration_closes_at = None
            return self
        start_date = getattr(self, "start_date", None)
        start_time = getattr(self, "start_time", None)
        closes = self.registration_closes_at
        if closes is not None and start_date is not None and start_time is not None:
            if closes >= datetime.combine(start_date, start_time):
                raise ValueError("Registration must close before the event starts.")
        return self


class EventRequestSubmit(RegistrationSettings):
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
class EventRequestUpdate(RegistrationSettings):
    model_config = ConfigDict(extra="forbid")

    # A PATCH names only what changed: the events service checks the period
    # against the stored record, and clears it when registration goes off.
    REGISTRATION_DATES_REQUIRED: ClassVar[bool] = False
    PARTIAL: ClassVar[bool] = True

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


class ReassignmentRequestSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reason is required")
        return value


class CancellationDecision(BaseModel):
    """S-61: the Coordinator's decision on a cancellation request. Only the
    shape is checked here; the events service enforces the rules (a reason
    when declining, none when approving) and answers with its own 422."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "declined"]
    reason: str | None = None


class EventDecision(BaseModel):
    """S-63 browser decision forwarded to Events before notifying its owner."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected", "returned"]
    reason: str | None = None
    comment: str | None = None

    @field_validator("reason", "comment", mode="before")
    @classmethod
    def normalise_decision_text(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def decision_details_match(self):
        if self.decision in {"rejected", "returned"} and self.reason is None:
            raise ValueError("reason is required to reject or return a request")
        if self.decision == "approved" and self.reason is not None:
            raise ValueError("reason is not accepted when approving a request")
        if self.comment is not None and self.decision != "returned":
            raise ValueError("comment is only accepted when returning a request")
        return self


class EventInformationUpdate(BaseModel):
    """S-18 Coordinator fields mirrored for S-63 composite orchestration."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    impact_accepted: bool = False
    name: str | None = None
    purpose: str | None = None
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=50)
    internal_notes: str | None = Field(default=None, max_length=4000)
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
        "name", "purpose", "contact_name", "contact_email", "contact_phone",
        "internal_notes", "venue", "special_requirements", "room_layout", mode="before",
    )
    @classmethod
    def normalise_information_text(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("contact_email")
    @classmethod
    def plausible_email(cls, value):
        if value is not None and ("@" not in value or value.startswith("@") or value.endswith("@")):
            raise ValueError("contact_email must be a valid email address")
        return value

    @field_validator("required_facilities", "required_accessibility")
    @classmethod
    def unique_information_options(cls, value):
        return None if value is None else list(dict.fromkeys(value))


class EventChangeValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    start_time: time
    end_date: date
    end_time: time
    expected_attendance: PositiveInt
    venue: str | None = None
    special_requirements: str | None = None
    room_layout: RoomLayout | None = None
    required_facilities: list[Facility]
    required_accessibility: list[AccessibilityFeature]

    @field_validator("venue", "special_requirements", mode="before")
    @classmethod
    def trim_optional_text(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("required_facilities", "required_accessibility")
    @classmethod
    def canonical_options(cls, value: list) -> list:
        return sorted(set(value))

    @model_validator(mode="after")
    def valid_window(self):
        _check_end_after_start(self.start_date, self.start_time, self.end_date, self.end_time)
        return self


class EventChangeEquipment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_item_id: UUID
    required_quantity: PositiveInt


class EventChangeSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: EventChangeValues
    equipment: list[EventChangeEquipment]

    @model_validator(mode="after")
    def unique_equipment(self):
        ids = [item.equipment_item_id for item in self.equipment]
        if len(ids) != len(set(ids)):
            raise ValueError("Equipment items must be unique")
        return self


class EventChangeAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_event_updated_at: datetime
    impact_ids: list[str]
    operation_id: UUID | None = None


class EventChangeReject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reason is required")
        return value


class EventImpactResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_impact_version: int = Field(ge=0)
    action: str = Field(min_length=1, max_length=200)
    evidence: dict


class CoordinatorSignificantEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edit: dict
    impact_ids: list[str]
