from datetime import date, datetime, time
from enum import Enum
from typing import Any, Literal, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator


class EventStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    # S-85 includes assigned events being actively handled at this stage in
    # the Lead's oversight read model. Persistence transitions into this
    # state belong to the workflow that owns the review, not to S-85.
    UNDER_REVIEW = "under_review"
    # S-14: the outcomes of a coordinator's decision on a submitted request.
    # REJECTED is terminal; RETURNED goes back to the organiser to edit and
    # resubmit as the same record. S-36: an approval moves the event to
    # PLANNING -- it passed the coordinator's check and venue/equipment
    # planning is underway. There is no "approved" status; "approved" is only
    # ever the recorded *decision* (DecisionValue), which stays put while the
    # status moves on.
    PLANNING = "planning"
    CONFIRMED = "confirmed"
    PREPARATION = "preparation"
    SAFETY_REJECTED = "safety_rejected"
    SAFETY_CHANGES_REQUESTED = "safety_changes_requested"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    RETURNED = "returned"


class DecisionValue(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURNED = "returned"


class SafetyDecisionValue(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class SafetyReviewRecord(BaseModel):
    """One immutable Operational Safety Check audit entry.

    S-87 keeps this history on the Events-owned row so appending the review
    and changing the event lifecycle remain one atomic compare-and-set write.
    """

    review_number: int = Field(ge=1)
    decision: SafetyDecisionValue
    reason: str | None = None
    safety_officer_id: UUID
    decided_at: datetime
class EquipmentPreparationStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    READY = "ready"


class EquipmentPreparationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EquipmentPreparationStatus


# S-36: the event's venue requirements use the venue catalogue's fixed sets,
# so each venue can be checked against them. Repeated here rather than
# imported -- each Docker image holds only its own service's code. Keep in
# step with backend/services/atomic/venues/schemas.py and
# backend/sql/events.sql.
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

ROOM_LAYOUTS: tuple[str, ...] = get_args(RoomLayout)
FACILITIES: tuple[str, ...] = get_args(Facility)
ACCESSIBILITY_FEATURES: tuple[str, ...] = get_args(AccessibilityFeature)


def _unique_in_order(values: list) -> list:
    return list(dict.fromkeys(values))


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
    def normalise_optional_text(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("required_facilities", "required_accessibility")
    @classmethod
    def drop_duplicates(cls, value: list) -> list:
        return _unique_in_order(value)

    @model_validator(mode="after")
    def end_must_follow_start(self):
        _check_end_after_start(self.start_date, self.start_time, self.end_date, self.end_time)
        return self


class EventDraftUpdate(EventDraftCreate):
    pass


# S-14: the coordinator's decision on a submitted request. A separate schema
# from the event schemas above -- this is not a shape the event ever takes,
# it is an action taken on one.
class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: DecisionValue
    # Required (and non-blank) for reject/return, forbidden for approve --
    # an approval is not a judgement call that needs defending in the
    # record the way turning a request away does.
    reason: str | None = None
    # Only meaningful alongside a return: a clarification or amendment note
    # for the organiser. Forbidden for approve and reject.
    comment: str | None = None

    @field_validator("reason", "comment", mode="before")
    @classmethod
    def normalise_optional_text(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def reason_and_comment_match_the_decision(self):
        if self.decision in (DecisionValue.REJECTED, DecisionValue.RETURNED):
            if self.reason is None:
                raise ValueError("reason is required to reject or return a request")
        elif self.reason is not None:
            raise ValueError("reason is not accepted when approving a request")

        if self.comment is not None and self.decision != DecisionValue.RETURNED:
            raise ValueError("comment is only accepted when returning a request")

        return self


class EventSubmittedCreate(BaseModel):
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

    @field_validator("required_facilities", "required_accessibility")
    @classmethod
    def drop_duplicates(cls, value: list) -> list:
        return _unique_in_order(value)

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
    special_requirements: str | None
    room_layout: str | None
    required_facilities: list[str]
    required_accessibility: list[str]
    # Null until the event_requests composite assigns one on submission --
    # never set by the organiser's own request.
    assigned_coordinator_id: UUID | None
    # Monotonic compare-and-set token for S-84 reassignment. Initial S-83
    # assignment remains version 0; every real owner-to-owner transfer adds 1.
    coordinator_assignment_version: int = Field(default=0, ge=0)
    technical_support_required: bool = False
    technical_support_details: str | None = None
    assigned_technical_support_id: UUID | None = None
    technical_support_assigned_at: datetime | None = None
    equipment_preparation_status: EquipmentPreparationStatus = (
        EquipmentPreparationStatus.NOT_STARTED
    )
    equipment_preparation_updated_by: UUID | None = None
    equipment_preparation_updated_at: datetime | None = None
    # The coordinator's decision and its record -- all null until decided,
    # and cleared again on resubmit after a return. See
    # POST /events/{event_id}/decision.
    decision: DecisionValue | None
    decision_reason: str | None
    decision_comment: str | None
    decided_at: datetime | None
    # S-86: the current Operational Safety Check. These fields are separate
    # from the Coordinator's original request decision above: rejecting a
    # safety arrangement does not retroactively reject the event request.
    safety_decision: SafetyDecisionValue | None = None
    safety_decision_reason: str | None = None
    safety_officer_id: UUID | None = None
    safety_decided_at: datetime | None = None
    # S-62: the Organiser's cancellation request, all null until one is sent.
    # Requesting never changes status.
    cancellation_reason: str | None = None
    cancellation_requested_at: datetime | None = None
    cancellation_requested_by: UUID | None = None
    safety_review_history: list[SafetyReviewRecord] = Field(default_factory=list)
    # Null while the request is a draft. With organiser_id this is the record
    # of who submitted it and when.
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EventChangeRecord(BaseModel):
    """One immutable Coordinator edit, retained for the future S-82 view."""

    change_number: int = Field(ge=1)
    changed_by: UUID
    changed_at: datetime
    changes: dict[str, dict[str, Any]]


class CoordinatorEventRead(EventRead):
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    internal_notes: str | None = None
    edit_version: int = Field(default=0, ge=0)
    edit_history: list[EventChangeRecord] = Field(default_factory=list)
    safety_recheck_required: bool = False


class EventInformationUpdate(BaseModel):
    """Coordinator-owned S-18 fields.

    The service compares these values with storage. The browser cannot choose
    whether a change is significant and cannot supply audit/lifecycle fields.
    """

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
    def normalise_edit_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("contact_email")
    @classmethod
    def contact_email_is_plausible(cls, value):
        if value is not None and ("@" not in value or value.startswith("@") or value.endswith("@")):
            raise ValueError("contact_email must be a valid email address")
        return value

    @field_validator("required_facilities", "required_accessibility")
    @classmethod
    def unique_edit_lists(cls, value):
        return None if value is None else _unique_in_order(value)


class EventInformationImpact(BaseModel):
    event_id: UUID
    expected_version: int = Field(ge=0)
    changed_fields: list[str]
    significant_fields: list[str]
    requires_impact_acceptance: bool


class EventSafetySubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)


class CancellationRequestCreate(BaseModel):
    """S-62: only the reason comes from the browser. Who asked and when are
    set by the service."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def reason_is_trimmed_and_not_blank(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("reason is required")
        return value


class EventOptions(BaseModel):
    room_layouts: list[str]
    facilities: list[str]
    accessibility: list[str]


# --- Internal, composite-only schemas --------------------------------------
#
# Everything below this line is for the event_requests composite service,
# never for a browser. None of it is reachable through Kong -- see
# backend/kong/kong.yml and AGENTS.md's "A service with no browser-facing
# routes needs no Kong entry."


class CoordinatorLoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinator_ids: list[UUID]
    start_date: date
    start_time: time
    end_date: date
    end_time: time
    # Set when rechecking availability for an event that already exists (an
    # edit to a submitted request) -- that event's own row is excluded from
    # the conflict check and the count, so it never conflicts with itself.
    exclude_event_id: UUID | None = None


class CoordinatorLoad(BaseModel):
    coordinator_id: UUID
    # Whether this coordinator has an assigned submitted event overlapping
    # the requested window at all. Touching endpoints (one event's end_time
    # equal to the request's start_time, or vice versa) do not count.
    conflict: bool
    # This coordinator's total assigned submitted-event count, independent of
    # the requested window -- what "least busy" is measured against.
    assigned_count: int


class TechnicalSupportLoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_ids: list[UUID]
    start_date: date
    start_time: time
    end_date: date
    end_time: time


class TechnicalSupportLoad(BaseModel):
    staff_id: UUID
    conflict: bool
    assigned_count: int


class OverlappingEventsRequest(BaseModel):
    """S-44: a window to find the live events overlapping it. The window may
    span days, as an event's can."""

    model_config = ConfigDict(extra="forbid")

    start_date: date
    start_time: time
    end_date: date
    end_time: time

    @model_validator(mode="after")
    def end_after_start(self):
        if datetime.combine(self.end_date, self.end_time) <= datetime.combine(self.start_date, self.start_time):
            raise ValueError("The end must be after the start")
        return self


class OverlappingEvent(BaseModel):
    """Just what the availability check shows about an event holding
    equipment: which event, its state, and when."""

    id: UUID
    name: str | None
    status: str
    start_date: date
    start_time: time
    end_date: date
    end_time: time


class InternalTechnicalSupportAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinator_id: UUID
    technical_support_details: str | None = None
    assigned_technical_support_id: UUID | None = None

    @field_validator("technical_support_details", mode="before")
    @classmethod
    def normalise_details(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


# organiser_id and assigned_coordinator_id are never accepted from an
# organiser's own request (see EventSubmittedCreate's extra="forbid"); these
# two routes exist so the composite -- which has already verified both --
# can supply them directly, the same way this service derives them from a
# session on the public routes.
class InternalEventCreate(EventSubmittedCreate):
    organiser_id: UUID
    assigned_coordinator_id: UUID | None = None


class InternalEventSubmit(EventSubmittedCreate):
    organiser_id: UUID
    assigned_coordinator_id: UUID | None = None


class InternalCoordinatorAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinator_id: UUID


class InternalCoordinatorAssignmentResult(EventRead):
    assignment_created: bool


class InternalCoordinatorReassignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinator_id: UUID
    expected_coordinator_id: UUID
    expected_assignment_version: int = Field(ge=0)


class InternalCoordinatorReassignmentResult(EventRead):
    previous_coordinator_id: UUID
    reassignment_created: bool


class InternalSafetyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: SafetyDecisionValue
    reason: str | None = None
    safety_officer_id: UUID

    @field_validator("reason", mode="before")
    @classmethod
    def normalise_reason(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def reason_matches_decision(self):
        if self.decision in (
            SafetyDecisionValue.REJECTED,
            SafetyDecisionValue.CHANGES_REQUESTED,
        ):
            if self.reason is None:
                raise ValueError("reason is required to reject or request changes")
        elif self.reason is not None:
            raise ValueError("reason is not accepted when approving a safety check")
        return self


class InternalSafetyResubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinator_id: UUID


# Mirrors EventDraftUpdate (every field optional, same normalisation) plus
# organiser_id and an optional reassignment -- the composite's edit-recheck
# flow (backend/services/composite/event_requests) uses this to change a
# submitted event's date/time and its assigned_coordinator_id in one write,
# only when the current coordinator no longer fits the new window.
class InternalEventUpdate(EventDraftUpdate):
    organiser_id: UUID
    assigned_coordinator_id: UUID | None = None
