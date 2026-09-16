"""Unit tests for the events service's Pydantic schemas -- see TEST_CASES.md."""

import pytest
from pydantic import ValidationError

from .conftest import EventDraftCreate, EventDraftUpdate, EventSubmittedCreate


SUBMITTED = {
    "name": "Alumni networking evening",
    "purpose": "Connect alumni with graduating students",
    "start_date": "2026-10-20",
    "start_time": "18:00",
    "end_date": "2026-10-20",
    "end_time": "21:00",
    "expected_attendance": 120,
    "venue": "Main auditorium",
    "equipment_requests": {"projector": 1, "microphone": 2},
    "accessibility_requirements": "Wheelchair access",
}


# --- TC-EVENTS-001 --------------------------------------------------------
def test_valid_draft_accepts_and_normalises_supplied_values():
    draft = EventDraftCreate(
        name="  Alumni networking evening  ",
        expected_attendance=120,
        start_time="18:00",
        end_time="21:00",
        equipment_requests={"projector": 1},
        accessibility_requirements="   ",
    )

    assert draft.name == "Alumni networking evening"
    assert draft.expected_attendance == 120
    assert draft.equipment_requests == {"projector": 1}
    assert draft.accessibility_requirements is None


# --- TC-EVENTS-002 --------------------------------------------------------
def test_empty_draft_is_valid():
    assert EventDraftCreate().model_dump() == {
        "name": None,
        "purpose": None,
        "start_date": None,
        "start_time": None,
        "end_date": None,
        "end_time": None,
        "expected_attendance": None,
        "venue": None,
        "equipment_requests": {},
        "accessibility_requirements": None,
        "special_requirements": None,
    }


# --- TC-EVENTS-003 --------------------------------------------------------
def test_draft_rejects_non_positive_attendance():
    with pytest.raises(ValidationError):
        EventDraftCreate(expected_attendance=0)


# --- TC-EVENTS-004 --------------------------------------------------------
def test_draft_rejects_non_positive_equipment_quantity():
    with pytest.raises(ValidationError):
        EventDraftCreate(equipment_requests={"projector": 0})


# --- TC-EVENTS-005 --------------------------------------------------------
def test_draft_rejects_invalid_time_ordering():
    with pytest.raises(ValidationError, match="end_time must be after start_time"):
        EventDraftCreate(start_time="21:00", end_time="18:00")


# --- TC-EVENTS-006 --------------------------------------------------------
def test_valid_submitted_request_is_accepted():
    submitted = EventSubmittedCreate(**SUBMITTED)

    assert submitted.name == SUBMITTED["name"]
    assert submitted.expected_attendance == 120
    assert submitted.equipment_requests == {"projector": 1, "microphone": 2}


# --- TC-EVENTS-007 --------------------------------------------------------
def test_submitted_request_rejects_missing_required_field():
    payload = {key: value for key, value in SUBMITTED.items() if key != "venue"}

    with pytest.raises(ValidationError) as exc_info:
        EventSubmittedCreate(**payload)

    assert ("venue",) in {error["loc"] for error in exc_info.value.errors()}


# --- TC-EVENTS-008 --------------------------------------------------------
def test_submitted_request_rejects_blank_required_text():
    with pytest.raises(ValidationError) as exc_info:
        EventSubmittedCreate(**{**SUBMITTED, "name": "   "})

    assert ("name",) in {error["loc"] for error in exc_info.value.errors()}


# --- TC-EVENTS-009 --------------------------------------------------------
def test_submitted_request_rejects_non_positive_attendance():
    with pytest.raises(ValidationError):
        EventSubmittedCreate(**{**SUBMITTED, "expected_attendance": -1})


# --- TC-EVENTS-010 --------------------------------------------------------
def test_submitted_request_rejects_invalid_time_ordering():
    with pytest.raises(ValidationError, match="end_time must be after start_time"):
        EventSubmittedCreate(**{**SUBMITTED, "end_time": "18:00"})


# --- TC-EVENTS-011 --------------------------------------------------------
def test_request_schemas_reject_server_managed_fields():
    server_managed = {
        "id": "11111111-1111-4111-8111-111111111111",
        "organiser_id": "22222222-2222-4222-8222-222222222222",
        "status": "submitted",
        "created_at": "2026-09-14T00:00:00Z",
        "updated_at": "2026-09-14T00:00:00Z",
    }

    with pytest.raises(ValidationError) as exc_info:
        EventDraftUpdate(**server_managed)

    assert {error["loc"] for error in exc_info.value.errors()} == {
        ("id",),
        ("organiser_id",),
        ("status",),
        ("created_at",),
        ("updated_at",),
    }


# --- TC-EVENTS-037 --------------------------------------------------------
def test_draft_rejects_end_date_before_start_date():
    with pytest.raises(ValidationError, match="end_date must be on or after start_date"):
        EventDraftCreate(start_date="2026-10-20", end_date="2026-10-19")


# --- TC-EVENTS-038 --------------------------------------------------------
def test_submitted_request_rejects_end_date_before_start_date():
    with pytest.raises(ValidationError, match="end_date must be on or after start_date"):
        EventSubmittedCreate(**{**SUBMITTED, "end_date": "2026-10-19"})


# --- TC-EVENTS-039 --------------------------------------------------------
def test_submitted_request_allows_end_time_before_start_time_across_days():
    submitted = EventSubmittedCreate(
        **{
            **SUBMITTED,
            "start_date": "2026-10-20",
            "start_time": "22:00",
            "end_date": "2026-10-21",
            "end_time": "02:00",
        }
    )

    assert submitted.end_date > submitted.start_date
    assert submitted.end_time < submitted.start_time


# --- TC-EVENTS-041 --------------------------------------------------------
def test_draft_accepts_special_requirements():
    draft = EventDraftCreate(special_requirements="  Sign-up sheet on the door  ")

    assert draft.special_requirements == "Sign-up sheet on the door"


# --- TC-EVENTS-042 --------------------------------------------------------
def test_submitted_request_accepts_special_requirements():
    submitted = EventSubmittedCreate(
        **SUBMITTED, special_requirements="Registration closes a week before"
    )

    assert submitted.special_requirements == "Registration closes a week before"


# --- TC-EVENTS-043 --------------------------------------------------------
def test_special_requirements_is_optional_for_submission():
    # Omitted entirely, and blank, are both fine -- the field is a place to
    # say something, not something that must be said.
    assert EventSubmittedCreate(**SUBMITTED).special_requirements is None
    assert (
        EventSubmittedCreate(**SUBMITTED, special_requirements="   ").special_requirements
        is None
    )
