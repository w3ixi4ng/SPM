"""Unit tests for the venues service's Pydantic schemas -- see TEST_CASES.md."""

import pytest
from pydantic import ValidationError

from .conftest import MINIMAL_VENUE, VALID_VENUE, VenueCreate


def venue(**changes):
    return {**MINIMAL_VENUE, **changes}


def error_fields(exc_info) -> set[str]:
    return {str(error["loc"][0]) for error in exc_info.value.errors()}


# --- TC-VENUES-001 --------------------------------------------------------
def test_complete_venue_is_accepted_and_normalised():
    created = VenueCreate(
        **{
            **VALID_VENUE,
            "name": "  Harbourfront Hall  ",
            "location": "  1 Harbourfront Walk, Singapore 098585 ",
            "facilities": ["projector", "wifi", "stage", "wifi"],
        }
    )

    assert created.name == "Harbourfront Hall"
    assert created.location == "1 Harbourfront Walk, Singapore 098585"
    assert created.facilities == ["projector", "wifi", "stage"]
    assert created.model_dump(mode="json", exclude={"name", "location", "facilities"}) == {
        "capacity": 250,
        "accessibility": ["wheelchair_access", "accessible_toilets"],
        "room_layouts": ["theatre", "banquet"],
        "operating_hours": [
            {"day": "mon", "open": "09:00:00", "close": "18:00:00"},
            {"day": "sat", "open": "10:00:00", "close": "22:00:00"},
        ],
        "description": "Waterfront hall with a raised stage.",
    }


# --- TC-VENUES-002 --------------------------------------------------------
def test_minimal_venue_is_accepted():
    created = VenueCreate(**MINIMAL_VENUE)

    assert created.facilities == []
    assert created.accessibility == []
    assert created.description is None


# --- TC-VENUES-003 --------------------------------------------------------
@pytest.mark.parametrize(
    "field", ["name", "location", "capacity", "room_layouts", "operating_hours"]
)
def test_each_required_field_must_be_present(field):
    payload = {key: value for key, value in MINIMAL_VENUE.items() if key != field}

    with pytest.raises(ValidationError) as exc_info:
        VenueCreate(**payload)

    assert error_fields(exc_info) == {field}


# --- TC-VENUES-004 --------------------------------------------------------
@pytest.mark.parametrize("field", ["name", "location"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_name_and_location_cannot_be_blank(field, blank):
    with pytest.raises(ValidationError) as exc_info:
        VenueCreate(**venue(**{field: blank}))

    assert error_fields(exc_info) == {field}


# --- TC-VENUES-005 --------------------------------------------------------
@pytest.mark.parametrize("capacity", [0, -5, 10.5, "abc"])
def test_capacity_must_be_a_positive_whole_number(capacity):
    with pytest.raises(ValidationError) as exc_info:
        VenueCreate(**venue(capacity=capacity))

    assert error_fields(exc_info) == {"capacity"}


def test_capacity_of_one_is_accepted():
    assert VenueCreate(**venue(capacity=1)).capacity == 1


# --- TC-VENUES-006 --------------------------------------------------------
def test_room_layouts_cannot_be_empty():
    with pytest.raises(ValidationError) as exc_info:
        VenueCreate(**venue(room_layouts=[]))

    assert error_fields(exc_info) == {"room_layouts"}


# --- TC-VENUES-007 --------------------------------------------------------
def test_operating_hours_cannot_be_empty():
    with pytest.raises(ValidationError) as exc_info:
        VenueCreate(**venue(operating_hours=[]))

    assert error_fields(exc_info) == {"operating_hours"}


# --- TC-VENUES-008 --------------------------------------------------------
@pytest.mark.parametrize("facilities", [["wifi", "jacuzzi"], ["WiFi"]])
def test_unknown_facility_is_rejected(facilities):
    with pytest.raises(ValidationError) as exc_info:
        VenueCreate(**venue(facilities=facilities))

    assert error_fields(exc_info) == {"facilities"}


# --- TC-VENUES-009 --------------------------------------------------------
def test_unknown_room_layout_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        VenueCreate(**venue(room_layouts=["theatre", "amphitheatre"]))

    assert error_fields(exc_info) == {"room_layouts"}


# --- TC-VENUES-010 --------------------------------------------------------
def test_unknown_accessibility_feature_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        VenueCreate(**venue(accessibility=["ramp"]))

    assert error_fields(exc_info) == {"accessibility"}


# --- TC-VENUES-011 --------------------------------------------------------
@pytest.mark.parametrize(("opens", "closes"), [("18:00", "09:00"), ("09:00", "09:00")])
def test_close_must_be_after_open(opens, closes):
    hours = [{"day": "tue", "open": opens, "close": closes}]

    with pytest.raises(ValidationError, match="close must be after open") as exc_info:
        VenueCreate(**venue(operating_hours=hours))

    assert error_fields(exc_info) == {"operating_hours"}


# --- TC-VENUES-012 --------------------------------------------------------
def test_day_cannot_repeat_in_operating_hours():
    hours = [
        {"day": "mon", "open": "09:00", "close": "12:00"},
        {"day": "mon", "open": "13:00", "close": "18:00"},
    ]

    with pytest.raises(ValidationError, match="mon is listed more than once") as exc_info:
        VenueCreate(**venue(operating_hours=hours))

    assert error_fields(exc_info) == {"operating_hours"}


# --- TC-VENUES-013 --------------------------------------------------------
@pytest.mark.parametrize(
    "entry",
    [
        {"day": "funday", "open": "09:00", "close": "17:00"},
        {"day": "mon", "open": "25:00", "close": "26:00"},
        {"day": "mon", "open": "nine", "close": "17:00"},
    ],
)
def test_operating_hours_reject_bad_day_or_time(entry):
    with pytest.raises(ValidationError) as exc_info:
        VenueCreate(**venue(operating_hours=[entry]))

    assert error_fields(exc_info) == {"operating_hours"}


# --- TC-VENUES-014 --------------------------------------------------------
def test_blank_description_becomes_none():
    assert VenueCreate(**venue(description="   ")).description is None
