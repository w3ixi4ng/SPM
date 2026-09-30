"""Unit tests for the venue_bookings composite service -- see TEST_CASES.md."""

import httpx
import pytest

from .conftest import (
    BOOKING_ID,
    COORDINATOR_ID,
    EVENT_ID,
    REQUEST,
    STAFF_ID,
    VENUE_ID,
    fake_response,
    me,
    requested,
)

UNSUITABLE = "This venue can't take this booking"


def assert_refused(response, services, *keys):
    """TC-VENUEBOOKINGS "refused at submission": 422, the key named, nothing saved."""
    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == UNSUITABLE
    for key in keys:
        assert key in body["errors"]
    services.bookings.post.assert_not_called()


def assert_nothing_downstream(services, *, users=True):
    if users:
        services.users.get.assert_not_called()
    services.events.get.assert_not_called()
    services.venues.get.assert_not_called()
    services.bookings.post.assert_not_called()
    services.bookings.get.assert_not_called()


# --- TC-VENUEBOOKINGS-001 --------------------------------------------------
def test_health_reports_ok(client, services):
    for path in ("/health", "/venue-bookings/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    assert_nothing_downstream(services)


# --- TC-VENUEBOOKINGS-002 --------------------------------------------------
def test_a_request_needs_a_session(client, services):
    services.user = fake_response(401, {"detail": "Not authenticated"})

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert_nothing_downstream(services, users=False)


# --- TC-VENUEBOOKINGS-003 --------------------------------------------------
@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "technical_support", "attendee"])
def test_only_an_event_coordinator_can_submit(client, services, role):
    services.user = me(role=role)

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied"}
    assert_nothing_downstream(services, users=False)


# --- TC-VENUEBOOKINGS-004 --------------------------------------------------
@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({k: v for k, v in REQUEST.items() if k != "venue_id"}, "venue_id"),
        ({k: v for k, v in REQUEST.items() if k != "booking_date"}, "booking_date"),
        (requested(end_time="09:00"), "body"),
        # The requirements are the event's; the request may not carry them.
        (requested(room_layout="theatre"), "room_layout"),
        (requested(required_facilities=["projector"]), "required_facilities"),
        (requested(status="approved"), "status"),
    ],
)
def test_the_body_is_checked_before_any_downstream_call(client, services, body, field):
    response = client.post("/venue-bookings", json=body)

    assert response.status_code == 422
    assert field in response.json()["errors"]
    assert_nothing_downstream(services)


def test_an_end_time_before_the_start_names_the_problem(client, services):
    response = client.post("/venue-bookings", json=requested(end_time="09:00"))

    assert "end_time must be after start_time" in str(response.json()["errors"])


# --- TC-VENUEBOOKINGS-005 --------------------------------------------------
def test_a_coordinator_cannot_book_for_an_event_not_assigned_to_them(client, services):
    services.event = fake_response(404, {"detail": "Event not found"})
    client.cookies.set("sb_access_token", "coordinator-token")

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}
    sent_cookies = services.events.get.call_args.kwargs["cookies"]
    assert sent_cookies["sb_access_token"] == "coordinator-token"
    services.venues.get.assert_not_called()
    services.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-006 --------------------------------------------------
@pytest.mark.parametrize("event_status", ["submitted", "returned", "rejected"])
def test_only_an_event_in_planning_can_have_a_venue_requested(client, services, event_status):
    services.set_event(status=event_status)

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 409
    assert response.json() == {"detail": "A venue can only be requested for an event in planning"}
    services.venues.get.assert_not_called()
    services.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-007 --------------------------------------------------
def test_the_venue_must_exist(client, services):
    services.venue = fake_response(404, {"detail": "Venue not found"})

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 404
    assert response.json() == {"detail": "Venue not found"}
    assert services.venues.get.call_args.args[0] == f"/venues/{VENUE_ID}"
    services.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-008 --------------------------------------------------
@pytest.mark.parametrize(
    ("booking_date", "start", "end"),
    [
        ("2026-11-13", "09:00", "12:00"),
        ("2026-11-12", "08:30", "10:00"),
        ("2026-11-12", "17:00", "19:00"),
    ],
)
def test_the_booking_must_fall_inside_the_event(client, services, booking_date, start, end):
    response = client.post(
        "/venue-bookings",
        json=requested(booking_date=booking_date, start_time=start, end_time=end),
    )

    assert_refused(response, services, "booking_date")
    assert response.json()["errors"]["booking_date"] == (
        "The booking must fall within the event's date and time"
    )


# --- TC-VENUEBOOKINGS-009 --------------------------------------------------
def test_a_booking_may_use_the_events_full_window(client, services):
    response = client.post("/venue-bookings", json=requested(start_time="09:00", end_time="18:00"))

    assert response.status_code == 201


def test_a_booking_may_use_one_day_of_a_multi_day_event(client, services):
    services.set_event(start_date="2026-11-12", start_time="18:00:00", end_date="2026-11-13", end_time="12:00:00")

    response = client.post(
        "/venue-bookings",
        json=requested(booking_date="2026-11-13", start_time="08:00", end_time="12:00"),
    )

    assert response.status_code == 201


# --- TC-VENUEBOOKINGS-010 --------------------------------------------------
def test_the_venue_must_be_open_that_day(client, services):
    services.set_event(start_date="2026-11-14", start_time="10:00:00", end_date="2026-11-14", end_time="12:00:00")

    response = client.post(
        "/venue-bookings",
        json=requested(booking_date="2026-11-14", start_time="10:00", end_time="12:00"),
    )

    assert_refused(response, services, "operating_hours")
    assert response.json()["errors"]["operating_hours"] == "Studio B is closed on Saturdays"


# --- TC-VENUEBOOKINGS-011 --------------------------------------------------
@pytest.mark.parametrize(("start", "end"), [("07:00", "09:00"), ("19:00", "21:00")])
def test_the_booking_must_fall_inside_opening_hours(client, services, start, end):
    services.set_event(start_time="06:00:00", end_time="23:00:00")

    response = client.post("/venue-bookings", json=requested(start_time=start, end_time=end))

    assert_refused(response, services, "operating_hours")
    assert response.json()["errors"]["operating_hours"] == "Studio B is open 08:00–20:00 on Thursdays"


def test_opening_hours_are_inclusive(client, services):
    services.set_event(start_time="06:00:00", end_time="23:00:00")

    response = client.post("/venue-bookings", json=requested(start_time="08:00", end_time="20:00"))

    assert response.status_code == 201


# --- TC-VENUEBOOKINGS-012 --------------------------------------------------
def test_the_venue_must_hold_the_expected_attendance(client, services):
    services.set_event(expected_attendance=151)

    response = client.post("/venue-bookings", json=REQUEST)

    assert_refused(response, services, "expected_attendance")
    assert response.json()["errors"]["expected_attendance"] == (
        "Studio B holds 150 people; this event expects 151"
    )


def test_attendance_equal_to_capacity_is_accepted(client, services):
    services.set_event(expected_attendance=150)

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 201


# --- TC-VENUEBOOKINGS-013 --------------------------------------------------
def test_every_required_facility_must_be_at_the_venue(client, services):
    services.set_event(required_facilities=["projector", "stage", "whiteboard"])

    response = client.post("/venue-bookings", json=REQUEST)

    assert_refused(response, services, "required_facilities")
    assert response.json()["errors"]["required_facilities"] == "Studio B does not have: stage, whiteboard"


# --- TC-VENUEBOOKINGS-014 --------------------------------------------------
def test_every_required_accessibility_feature_must_be_at_the_venue(client, services):
    services.set_event(required_accessibility=["wheelchair_access", "hearing_loop"])

    response = client.post("/venue-bookings", json=REQUEST)

    assert_refused(response, services, "required_accessibility")
    assert response.json()["errors"]["required_accessibility"] == "Studio B does not have: hearing_loop"


# --- TC-VENUEBOOKINGS-015 --------------------------------------------------
def test_the_room_layout_must_be_one_the_venue_offers(client, services):
    services.set_event(room_layout="banquet")

    response = client.post("/venue-bookings", json=REQUEST)

    assert_refused(response, services, "room_layout")
    assert response.json()["errors"]["room_layout"] == "Studio B does not offer the banquet layout"


# --- TC-VENUEBOOKINGS-016 --------------------------------------------------
def test_every_problem_is_reported_at_once(client, services):
    services.set_event(expected_attendance=200, room_layout="banquet", required_facilities=["stage"])

    response = client.post("/venue-bookings", json=requested(start_time="07:00", end_time="10:00"))

    assert_refused(response, services)
    assert set(response.json()["errors"]) == {
        "booking_date",
        "operating_hours",
        "expected_attendance",
        "required_facilities",
        "room_layout",
    }


# --- TC-VENUEBOOKINGS-017 --------------------------------------------------
def test_an_event_with_no_venue_requirements_and_no_notes(client, services):
    services.set_event(room_layout=None, required_facilities=[], required_accessibility=[])
    required_only = {
        key: REQUEST[key] for key in ("event_id", "venue_id", "booking_date", "start_time", "end_time")
    }

    response = client.post("/venue-bookings", json=required_only)

    assert response.status_code == 201
    sent = services.sent_booking()
    assert sent["room_layout"] is None
    assert sent["required_facilities"] == []
    assert sent["required_accessibility"] == []
    assert sent["notes"] is None


# --- TC-VENUEBOOKINGS-018 --------------------------------------------------
def test_the_request_carries_the_events_requirements_for_venue_staff(client, services):
    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 201
    assert services.sent_booking() == {
        "event_id": EVENT_ID,
        "venue_id": VENUE_ID,
        "coordinator_id": COORDINATOR_ID,
        "coordinator_name": "Grace Hopper",
        "coordinator_email": "grace@example.com",
        "booking_date": "2026-11-12",
        "start_time": "09:00:00",
        "end_time": "12:00:00",
        "event_name": "Alumni networking evening",
        "event_purpose": "Reconnect graduates with faculty",
        "expected_attendance": 120,
        "special_requirements": "Vegetarian catering for 40",
        "required_accessibility": ["wheelchair_access"],
        "required_facilities": ["projector"],
        "room_layout": "theatre",
        "notes": "Access from 08:30 for setup",
        "venue_name": "Studio B",
    }
    body = response.json()
    assert body["id"] == BOOKING_ID
    assert body["status"] == "pending"


# --- TC-VENUEBOOKINGS-019 --------------------------------------------------
def test_submitting_a_request_writes_nothing_to_the_event(client, services):
    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 201
    services.events.get.assert_called_once()
    assert services.events.get.call_args.args[0] == f"/events/assigned/{EVENT_ID}"
    services.events.post.assert_not_called()
    services.events.patch.assert_not_called()
    services.events.put.assert_not_called()


# --- TC-VENUEBOOKINGS-020 --------------------------------------------------
def _fail(services, which, how):
    failure = httpx.ConnectError("connection refused") if how == "raise" else None

    async def broken(*args, **kwargs):
        if failure:
            raise failure
        return fake_response(500, {"detail": "Internal server error"})

    {
        "users": services.users.get,
        "events": services.events.get,
        "venues": services.venues.get,
        "bookings": services.bookings.post,
    }[which].side_effect = broken


@pytest.mark.parametrize("how", ["raise", "500"])
@pytest.mark.parametrize(
    ("which", "detail"),
    [
        ("users", "Users service unavailable"),
        ("events", "Events service unavailable"),
        ("venues", "Venues service unavailable"),
        ("bookings", "Bookings service unavailable"),
    ],
)
def test_a_service_that_cannot_be_reached_is_a_502(client, services, which, detail, how):
    _fail(services, which, how)

    response = client.post("/venue-bookings", json=REQUEST)

    assert response.status_code == 502
    assert response.json() == {"detail": detail}
    if which != "bookings":
        services.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-021 --------------------------------------------------
def test_the_pending_list_needs_a_session(client, services):
    services.user = fake_response(401, {"detail": "Not authenticated"})

    response = client.get("/venue-bookings/pending")

    assert response.status_code == 401
    services.bookings.get.assert_not_called()


# --- TC-VENUEBOOKINGS-022 --------------------------------------------------
@pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "technical_support", "attendee"])
def test_only_venue_staff_see_the_pending_list(client, services, role):
    services.user = me(role=role)

    response = client.get("/venue-bookings/pending")

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied"}
    services.bookings.get.assert_not_called()


# --- TC-VENUEBOOKINGS-023 --------------------------------------------------
def test_any_venue_staff_member_sees_every_pending_request(client, services):
    services.user = me(role="venue_staff", id=STAFF_ID)
    pending = [
        {"id": "55555555-5555-4555-8555-555555555555", "venue_id": VENUE_ID, "status": "pending"},
        {"id": "66666666-6666-4666-8666-666666666666", "venue_id": "77777777-7777-4777-8777-777777777777", "status": "pending"},
    ]
    services.pending = fake_response(200, pending)

    response = client.get("/venue-bookings/pending")

    assert response.status_code == 200
    assert response.json() == pending
    services.bookings.get.assert_called_once()
    assert services.bookings.get.call_args.args[0] == "/bookings"
    assert services.bookings.get.call_args.kwargs["params"] == {"status": "actionable"}


# --- TC-VENUEBOOKINGS-024 --------------------------------------------------
@pytest.mark.parametrize("how", ["raise", "500"])
def test_the_pending_list_fails_loudly_when_bookings_is_down(client, services, how):
    services.user = me(role="venue_staff", id=STAFF_ID)

    async def broken(*args, **kwargs):
        if how == "raise":
            raise httpx.ConnectError("connection refused")
        return fake_response(500, {"detail": "Internal server error"})

    services.bookings.get.side_effect = broken

    response = client.get("/venue-bookings/pending")

    assert response.status_code == 502
    assert response.json() == {"detail": "Bookings service unavailable"}


# --- S-36 AC4: a coordinator lists the requests sent for an event ----------

EVENT_LIST = f"/venue-bookings?event_id={EVENT_ID}"


# --- TC-VENUEBOOKINGS-025 --------------------------------------------------
def test_listing_an_events_requests_needs_a_session(client, services):
    services.user = fake_response(401, {"detail": "Not authenticated"})

    response = client.get(EVENT_LIST)

    assert response.status_code == 401
    services.events.get.assert_not_called()
    services.bookings.get.assert_not_called()


# --- TC-VENUEBOOKINGS-026 --------------------------------------------------
@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "technical_support", "attendee"])
def test_only_an_event_coordinator_can_list_an_events_requests(client, services, role):
    services.user = me(role=role)

    response = client.get(EVENT_LIST)

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied"}
    services.events.get.assert_not_called()
    services.bookings.get.assert_not_called()


# --- TC-VENUEBOOKINGS-027 --------------------------------------------------
@pytest.mark.parametrize("path", ["/venue-bookings", "/venue-bookings?event_id=not-a-uuid"])
def test_the_event_id_is_required_and_must_be_a_uuid(client, services, path):
    response = client.get(path)

    assert response.status_code == 422
    assert "query.event_id" in response.json()["errors"]
    assert_nothing_downstream(services)


# --- TC-VENUEBOOKINGS-028 --------------------------------------------------
def test_a_coordinator_cannot_list_requests_for_an_event_not_assigned_to_them(client, services):
    services.event = fake_response(404, {"detail": "Event not found"})
    client.cookies.set("sb_access_token", "coordinator-token")

    response = client.get(EVENT_LIST)

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}
    assert services.events.get.call_args.kwargs["cookies"]["sb_access_token"] == "coordinator-token"
    services.bookings.get.assert_not_called()


# --- TC-VENUEBOOKINGS-029 --------------------------------------------------
def test_the_events_requests_come_back_with_their_status(client, services):
    sent = [
        {"id": "55555555-5555-4555-8555-555555555555", "event_id": EVENT_ID, "status": "pending"},
        {"id": "66666666-6666-4666-8666-666666666666", "event_id": EVENT_ID, "status": "pending"},
    ]
    services.pending = fake_response(200, sent)

    response = client.get(EVENT_LIST)

    assert response.status_code == 200
    assert response.json() == sent
    services.bookings.get.assert_called_once()
    assert services.bookings.get.call_args.args[0] == "/bookings"
    assert services.bookings.get.call_args.kwargs["params"] == {"event_id": EVENT_ID}


# --- TC-VENUEBOOKINGS-030 --------------------------------------------------
@pytest.mark.parametrize("how", ["raise", "500"])
@pytest.mark.parametrize(
    ("which", "detail"),
    [("events", "Events service unavailable"), ("bookings", "Bookings service unavailable")],
)
def test_listing_an_events_requests_is_a_502_when_a_service_is_down(client, services, which, detail, how):
    async def broken(*args, **kwargs):
        if how == "raise":
            raise httpx.ConnectError("connection refused")
        return fake_response(500, {"detail": "Internal server error"})

    {"events": services.events.get, "bookings": services.bookings.get}[which].side_effect = broken

    response = client.get(EVENT_LIST)

    assert response.status_code == 502
    assert response.json() == {"detail": detail}


# TC-VENUEBOOKINGS-031: no new suitability implementation, just regression coverage.
@pytest.mark.parametrize("changes,key", [
    ({"capacity": 1}, "expected_attendance"),
    ({"facilities": []}, "required_facilities"),
    ({"accessibility": []}, "required_accessibility"),
])
def test_submission_rereads_updated_venue(client, services, changes, key):
    services.set_event(required_facilities=["projector"], required_accessibility=["wheelchair_access"])
    services.set_venue(facilities=["projector"], accessibility=["wheelchair_access"])
    assert client.post("/venue-bookings", json=REQUEST).status_code == 201
    services.bookings.post.reset_mock()
    services.set_venue(**changes)
    response = client.post("/venue-bookings", json=REQUEST)
    assert_refused(response, services, key)
    assert services.venues.get.call_count == 2
    assert all(call.args[0] == f"/venues/{VENUE_ID}" for call in services.venues.get.call_args_list)
