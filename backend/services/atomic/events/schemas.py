from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, ClassVar, Literal, get_args
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
    # S-17: the Coordinator submitted a fully arranged event for the
    # Operational Safety Check (S-86). Only the Safety Officer's approval
    # moves it on to CONFIRMED.
    PENDING_SAFETY_CHECK = "pending_safety_check"
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


class TechnicalSignoffDecision(str, Enum):
    APPROVED = "approved"
    DECLINED = "declined"


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


# S-51: the period is Singapore wall-clock time and stored without a
# timezone, like the event's own dates and times. A client that sends an
# offset anyway is converted, so a comparison never mixes naive and aware.
SINGAPORE = timezone(timedelta(hours=8))
REGISTRATION_FIELDS = frozenset(
    {"registration_required", "registration_opens_at", "registration_closes_at"}
)
_REGISTRATION_DATE_PROMPTS = {
    "registration_opens_at": "Choose when registration opens.",
    "registration_closes_at": "Choose when registration closes.",
}


class RegistrationSettings(BaseModel):
    """S-51: whether attendees register for the event, and when they may.

    Shared by every organiser payload. The two dates are checked field by
    field (``validate_default``, so a missing one is still seen) so an error
    names the date that is wrong. Closing before the event starts needs the
    start, so it is checked once the whole model is built.
    """

    # A submitted request needs both dates once registration is on; a draft
    # may turn it on and choose them later.
    REGISTRATION_DATES_REQUIRED: ClassVar[bool] = False
    # A PATCH body names only what changed, so registration being "off" there
    # means "not mentioned" and must not clear stored dates. The route clears
    # them from the merged record instead.
    PARTIAL: ClassVar[bool] = False

    registration_required: bool = False
    registration_opens_at: datetime | None = Field(default=None, validate_default=True)
    registration_closes_at: datetime | None = Field(default=None, validate_default=True)

    @field_validator("registration_opens_at", "registration_closes_at")
    @classmethod
    def check_registration_date(cls, value: datetime | None, info: ValidationInfo):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(SINGAPORE).replace(tzinfo=None)
        # Not checked while registration is off: the dates are about to be
        # cleared, so their order is no reason to refuse the request.
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


class EventDraftCreate(RegistrationSettings):
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
    PARTIAL: ClassVar[bool] = True


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


class EventSubmittedCreate(RegistrationSettings):
    model_config = ConfigDict(extra="forbid")

    REGISTRATION_DATES_REQUIRED: ClassVar[bool] = True

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


class EventAssignmentSummary(BaseModel):
    """The only event fields exposed in S-93's cross-Lead inventory."""

    id: UUID
    name: str | None
    status: EventStatus
    start_date: date | None
    start_time: time | None
    end_date: date | None
    end_time: time | None
    assigned_coordinator_id: UUID
    assigning_lead_id: UUID | None
    coordinator_assignment_version: int = Field(ge=0)


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
    assigning_lead_id: UUID | None = None
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
    # S-17: the assigned Technical Support's sign-off on the equipment
    # arrangements, all null while awaiting one.
    technical_signoff_decision: TechnicalSignoffDecision | None = None
    technical_signoff_reason: str | None = None
    technical_signoff_override_comment: str | None = None
    technical_signoff_by: UUID | None = None
    technical_signoff_at: datetime | None = None
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
    # S-61: the assigned Coordinator's latest decision on that request.
    cancellation_decision: Literal["approved", "declined"] | None = None
    cancellation_decision_reason: str | None = None
    cancellation_decided_by: UUID | None = None
    cancellation_decided_at: datetime | None = None
    # S-51: off, with no period, unless the Organiser turned it on.
    registration_required: bool = False
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    # S-50: when the Organiser closed registration early; null while open.
    registration_closed_at: datetime | None = None
    # Null while the request is a draft. With organiser_id this is the record
    # of who submitted it and when.
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PublishedEventRead(BaseModel):
    """S-51: a confirmed event's public details -- what anyone may read
    without signing in. Nothing about who organises it or how it is being
    run.

    S-50: internal only, so it also carries the cap and the Organiser's close
    decision for the event_registrations composite; that composite turns
    them into `is_full` and `registration_closed_by_organiser` and never
    passes the attendance figure on."""

    id: UUID
    name: str | None
    purpose: str | None
    start_date: date | None
    start_time: time | None
    end_date: date | None
    end_time: time | None
    registration_required: bool
    registration_opens_at: datetime | None
    registration_closes_at: datetime | None
    expected_attendance: int | None = None
    registration_closed_at: datetime | None = None


class AttendeeEventRead(PublishedEventRead):
    """S-56: an event as its registered Attendees may see it, with its status
    so the event_registrations composite can tell confirmed details from ones
    being re-checked after a significant change."""

    status: str


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


class CancellationDecisionCreate(BaseModel):
    """S-61: approve, or decline with a reason. Who decided and when are
    set by the service."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "declined"]
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def blank_reason_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def reason_only_when_declining(self):
        if self.decision == "declined" and self.reason is None:
            raise ValueError("reason is required when declining")
        if self.decision == "approved" and self.reason is not None:
            raise ValueError("reason is not accepted when approving")
        return self


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


class ReassignmentRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reason is required")
        return value


class ReassignmentRequestRead(BaseModel):
    id: UUID
    event_id: UUID
    event_name: str
    requester_id: UUID
    assigning_lead_id: UUID
    assignment_version: int
    reason: str
    status: Literal["pending", "actioned"]
    created_at: datetime
    actioned_at: datetime | None


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


class InternalSafetySubmission(BaseModel):
    """S-17: the safety_checks composite has already checked readiness."""

    model_config = ConfigDict(extra="forbid")

    coordinator_id: UUID


class InternalTechnicalSignoff(BaseModel):
    """S-17: approve, or decline with a reason. An approval given over an
    S-44 shortage carries the comment Technical Support gave for it."""

    model_config = ConfigDict(extra="forbid")

    technical_support_id: UUID
    decision: TechnicalSignoffDecision
    reason: str | None = Field(default=None, max_length=500)
    override_comment: str | None = Field(default=None, max_length=500)

    @field_validator("reason", "override_comment", mode="before")
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def fields_match_decision(self):
        if self.decision is TechnicalSignoffDecision.DECLINED:
            if self.reason is None:
                raise ValueError("reason is required to decline")
            if self.override_comment is not None:
                raise ValueError("override_comment is only given with an approval")
        elif self.reason is not None:
            raise ValueError("reason is not accepted when approving")
        return self


# Mirrors EventDraftUpdate (every field optional, same normalisation) plus
# organiser_id and an optional reassignment -- the composite's edit-recheck
# flow (backend/services/composite/event_requests) uses this to change a
# submitted event's date/time and its assigned_coordinator_id in one write,
# only when the current coordinator no longer fits the new window.
class InternalEventUpdate(EventDraftUpdate):
    organiser_id: UUID
    assigned_coordinator_id: UUID | None = None


# S-82: the event change history. Every action maps to the category the
# Safety Officer's view filters on. The events service records its own
# actions; the venue and equipment ones arrive from their composites through
# POST /internal/events/{event_id}/history, which accepts only those.
EVENT_HISTORY_ACTIONS: dict[str, str] = {
    "submitted": "submission",
    "edited": "edit",
    "request_approved": "review",
    "request_rejected": "review",
    "request_returned": "review",
    "cancellation_requested": "review",
    "cancellation_approved": "review",
    "cancellation_declined": "review",
    "coordinator_assigned": "assignment",
    "reassignment_requested": "assignment",
    "coordinator_reassigned": "assignment",
    "technical_support_assigned": "assignment",
    "technical_signoff_approved": "equipment",
    "technical_signoff_declined": "equipment",
    "equipment_preparation_changed": "equipment",
    "safety_submitted": "safety",
    "safety_resubmitted": "safety",
    "safety_approved": "safety",
    "safety_changes_requested": "safety",
    "safety_rejected": "safety",
}
COMPOSITE_HISTORY_ACTIONS: dict[str, str] = {
    "venue_requested": "venue",
    "venue_request_changed": "venue",
    "venue_request_withdrawn": "venue",
    "venue_replacement_requested": "venue",
    "venue_alternative_resolved": "venue",
    "venue_held": "venue",
    "venue_released": "venue",
    "venue_confirmed": "venue",
    "venue_rejected": "venue",
    "equipment_requirement_set": "equipment",
    "equipment_requirement_removed": "equipment",
}
HISTORY_CATEGORIES = {**EVENT_HISTORY_ACTIONS, **COMPOSITE_HISTORY_ACTIONS}
# The parts of an edit the Operational Safety Check depends on (S-82 AC3).
SAFETY_EDIT_FIELDS = frozenset({
    "expected_attendance", "venue", "room_layout",
    "required_facilities", "required_accessibility",
})
SAFETY_HISTORY_CATEGORIES = frozenset({"safety", "venue", "equipment"})

HistoryActorRole = Literal[
    "event_organiser", "event_coordinator", "event_coordinator_lead",
    "venue_staff", "technical_support", "safety_officer",
]


class HistoryEntryCreate(BaseModel):
    """A venue or equipment action from a composite. The time and category
    are the service's to set, so neither is accepted."""

    model_config = ConfigDict(extra="forbid")

    actor_id: UUID
    actor_role: HistoryActorRole
    action: str
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def composite_action(cls, value):
        if value not in COMPOSITE_HISTORY_ACTIONS:
            raise ValueError("not an action this route records")
        return value


class HistoryEntryRead(BaseModel):
    id: int
    event_id: UUID
    # Null only on a backfilled entry whose actor was never stored.
    actor_id: UUID | None
    actor_role: str | None
    category: str
    action: str
    details: dict[str, Any]
    occurred_at: datetime


class HistoryScopeRead(BaseModel):
    """S-82: who may read an event's history, for the composites. No other
    event detail crosses over."""

    id: UUID
    name: str | None
    status: str
    assigned_coordinator_id: UUID | None
    # Whether a Safety Officer has ever decided on it, so an event sent back
    # to planning after a review still counts as having reached them.
    safety_reviewed: bool

class EventChangeValues(BaseModel):
    """Complete proposed S-59 values; never an accepted Events update."""

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


class InternalEventChangeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_event_updated_at: datetime
    proposed_values: EventChangeValues
    accepted_equipment: list[EventChangeEquipment]
    proposed_equipment: list[EventChangeEquipment]

    @model_validator(mode="after")
    def unique_equipment(self):
        for items in (self.accepted_equipment, self.proposed_equipment):
            ids = [item.equipment_item_id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError("Equipment items must be unique")
        return self


class EventChangeRequestRead(BaseModel):
    id: UUID
    event_id: UUID
    requested_by: UUID
    submitted_at: datetime
    status: Literal["pending", "accepted", "rejected"]
    expected_event_updated_at: datetime
    accepted_values: dict[str, Any]
    proposed_values: EventChangeValues
    accepted_equipment: list[EventChangeEquipment]
    proposed_equipment: list[EventChangeEquipment]
    resolved_at: datetime | None = None
