"""Unit tests for the bookings service -- see TEST_CASES.md."""

from datetime import datetime

import pytest

from .conftest import BOOKING, BOOKING_STORED, booking_row, on_insert, on_pending_list, table


def _without(*fields):
    return {key: value for key, value in BOOKING.items() if key not in fields}


# --- TC-BOOKINGS-001 ------------------------------------------------------
def test_health_reports_ok(client, db):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    db.schema.assert_not_called()


# --- TC-BOOKINGS-002 ------------------------------------------------------
def test_a_booking_is_stored_as_pending_with_a_service_set_submission_time(client, db):
    on_insert(db, [booking_row()])

    response = client.post("/bookings", json=BOOKING)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == booking_row()["id"]
    assert body["status"] == "pending"
    assert body["submitted_at"] is not None
    for field in ("event_name", "venue_name", "expected_attendance", "required_facilities"):
        assert body[field] == BOOKING[field]

    db.schema.assert_called_with("bookings")
    db.schema.return_value.table.assert_called_with("bookings")
    sent = table(db).insert.call_args[0][0]
    assert {key: sent[key] for key in BOOKING_STORED} == BOOKING_STORED
    assert sent["status"] == "pending"
    datetime.fromisoformat(sent["submitted_at"])


# --- TC-BOOKINGS-003 ------------------------------------------------------
@pytest.mark.parametrize(
    "extra",
    [{"status": "approved"}, {"submitted_at": "2020-01-01T00:00:00Z"}],
)
def test_a_caller_cannot_choose_the_status_or_submission_time(client, db, extra):
    response = client.post("/bookings", json={**BOOKING, **extra})

    assert response.status_code == 422
    table(db).insert.assert_not_called()


# --- TC-BOOKINGS-004 ------------------------------------------------------
@pytest.mark.parametrize(
    "field",
    [
        "event_id",
        "venue_id",
        "coordinator_id",
        "coordinator_name",
        "coordinator_email",
        "booking_date",
        "start_time",
        "end_time",
        "event_name",
        "event_purpose",
        "expected_attendance",
        "venue_name",
    ],
)
def test_every_required_field_is_required(client, db, field):
    response = client.post("/bookings", json=_without(field))

    assert response.status_code == 422
    assert field in response.json()["errors"]
    table(db).insert.assert_not_called()


# --- TC-BOOKINGS-005 ------------------------------------------------------
def test_the_optional_fields_may_be_left_out(client, db):
    on_insert(db, [booking_row()])
    optional = (
        "accessibility_requirements",
        "required_accessibility",
        "required_facilities",
        "room_layout",
        "notes",
    )

    response = client.post("/bookings", json=_without(*optional))

    assert response.status_code == 201
    sent = table(db).insert.call_args[0][0]
    assert sent["accessibility_requirements"] is None
    assert sent["required_accessibility"] == []
    assert sent["required_facilities"] == []
    assert sent["room_layout"] is None
    assert sent["notes"] is None


# --- TC-BOOKINGS-006 ------------------------------------------------------
@pytest.mark.parametrize("end_time", ["09:00", "08:00"])
def test_the_end_time_must_be_after_the_start_time(client, db, end_time):
    response = client.post("/bookings", json={**BOOKING, "end_time": end_time})

    assert response.status_code == 422
    assert "end_time must be after start_time" in str(response.json()["errors"])
    table(db).insert.assert_not_called()


# --- TC-BOOKINGS-007 ------------------------------------------------------
@pytest.mark.parametrize("attendance", [0, -5])
def test_expected_attendance_must_be_positive(client, db, attendance):
    response = client.post("/bookings", json={**BOOKING, "expected_attendance": attendance})

    assert response.status_code == 422
    assert "expected_attendance" in response.json()["errors"]
    table(db).insert.assert_not_called()


# --- TC-BOOKINGS-008 ------------------------------------------------------
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("room_layout", "ballroom"),
        ("required_facilities", ["jacuzzi"]),
        ("required_accessibility", ["ramp"]),
    ],
)
def test_the_chosen_options_come_from_the_catalogue_sets(client, db, field, value):
    response = client.post("/bookings", json={**BOOKING, field: value})

    assert response.status_code == 422
    assert any(key.startswith(field) for key in response.json()["errors"])
    table(db).insert.assert_not_called()


# --- TC-BOOKINGS-009 ------------------------------------------------------
def test_text_is_trimmed_and_blank_optional_text_becomes_null(client, db):
    on_insert(db, [booking_row()])

    response = client.post(
        "/bookings",
        json={
            **BOOKING,
            "notes": "  Access from 08:30  ",
            "accessibility_requirements": "   ",
            "required_facilities": ["projector", "projector"],
        },
    )

    assert response.status_code == 201
    sent = table(db).insert.call_args[0][0]
    assert sent["notes"] == "Access from 08:30"
    assert sent["accessibility_requirements"] is None
    assert sent["required_facilities"] == ["projector"]


# --- TC-BOOKINGS-010 ------------------------------------------------------
def test_the_pending_list_holds_pending_bookings_oldest_first(client, db):
    rows = [
        booking_row(id="55555555-5555-4555-8555-555555555555", submitted_at="2026-10-01T09:00:00+00:00"),
        booking_row(id="66666666-6666-4666-8666-666666666666", submitted_at="2026-10-02T09:00:00+00:00"),
    ]
    on_pending_list(db, rows)

    response = client.get("/bookings", params={"status": "pending"})

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [row["id"] for row in rows]
    table(db).select.assert_called_once_with("*")
    table(db).select.return_value.eq.assert_called_once_with("status", "pending")
    table(db).select.return_value.eq.return_value.order.assert_called_once_with("submitted_at")


# --- TC-BOOKINGS-011 ------------------------------------------------------
def test_no_pending_bookings_is_an_empty_list(client, db):
    on_pending_list(db, [])

    response = client.get("/bookings", params={"status": "pending"})

    assert response.status_code == 200
    assert response.json() == []


# --- TC-BOOKINGS-012 ------------------------------------------------------
def test_an_unknown_status_filter_is_refused(client, db):
    response = client.get("/bookings", params={"status": "whatever"})

    assert response.status_code == 422
    db.schema.assert_not_called()


# --- TC-BOOKINGS-013 ------------------------------------------------------
def test_a_storage_failure_is_reported_not_swallowed(client, db):
    table(db).insert.return_value.execute.side_effect = RuntimeError("connection reset")
    table(db).select.return_value.eq.return_value.order.return_value.execute.side_effect = RuntimeError(
        "connection reset"
    )

    created = client.post("/bookings", json=BOOKING)
    listed = client.get("/bookings", params={"status": "pending"})

    for response in (created, listed):
        assert response.status_code == 500
        assert response.json() == {"detail": "Booking storage unavailable"}
