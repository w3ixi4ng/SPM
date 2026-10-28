"""S-56: a registered Attendee sees their event's confirmed date, time and venue.

TC-EVENTREGISTRATIONS-042, 044..050. The details are shown on each row of the
Attendee's list while the event is confirmed; an event sent back for
re-checking stays listed with them hidden. The venue is the primary one -- the
confirmed booking explicitly selected under S-91 -- and only an Attendee
holding a place sees it.
"""

import httpx
import pytest

from .conftest import ATTENDEE_A, EVENT_E, published, response

MINE = "/event-registrations/me/registrations"
H1, H2, H3 = "h1", "h2", "h3"


def _booking(booking_id, venue_name, status, submitted_at, **extra):
    return {"id": booking_id, "venue_id": f"v-{booking_id}", "venue_name": venue_name,
            "status": status, "submitted_at": submitted_at, **extra}


HALL_A = _booking(H1, "Hall A", "confirmed", "2026-10-01T02:00:00Z", is_primary=True)


@pytest.fixture
def held(services):
    """A holds a place at E; E is confirmed, with H1 its one confirmed booking."""
    services["registrations"].places[EVENT_E] = [
        {"id": "r1", "event_id": EVENT_E, "attendee_id": ATTENDEE_A,
         "created_at": "2026-11-05T04:00:00Z"},
    ]
    base = services["registrations"].get.side_effect

    async def registrations_get(path, **kwargs):
        if path == f"/registrations/attendees/{ATTENDEE_A}":
            return response(200, services["registrations"].places[EVENT_E])
        return await base(path, **kwargs)

    services["registrations"].get.side_effect = registrations_get
    _event_status(services, "confirmed")
    _bookings(services, [HALL_A])
    return services


def _event_status(services, status, **extra):
    async def events_get(path, **kwargs):
        if path == f"/internal/events/attendee-view/{EVENT_E}":
            return response(200, {**published(), **extra, "status": status})
        return response(404, {"detail": "Event not found."})

    services["events"].get.side_effect = events_get


def _bookings(services, rows):
    services["bookings"].get.side_effect = None
    services["bookings"].get.return_value = response(200, rows)


def _only_row(client):
    result = client.get(MINE)
    assert result.status_code == 200
    rows = result.json()
    assert len(rows) == 1
    return rows[0]


# --- TC-EVENTREGISTRATIONS-042 --------------------------------------------
def test_a_held_place_at_a_confirmed_event_shows_when_and_where(client, held):
    row = _only_row(client)

    assert row["event_id"] == EVENT_E
    assert (row["start_date"], row["start_time"]) == ("2026-11-20", "18:00:00")
    assert (row["end_date"], row["end_time"]) == ("2026-11-20", "21:00:00")
    assert row["status"] == "confirmed"
    assert row["details_confirmed"] is True
    assert row["venue"] == "Hall A"
    held["bookings"].get.assert_called_once_with("/bookings", params={"event_id": EVENT_E})


# --- TC-EVENTREGISTRATIONS-044 --------------------------------------------
@pytest.mark.parametrize("status", ["planning", "pending_safety_check", "safety_changes_requested"])
def test_an_event_being_rechecked_shows_details_to_be_confirmed(client, held, status):
    _event_status(held, status)

    row = _only_row(client)

    assert row["name"] == "Alumni networking evening"
    assert row["status"] == "confirmed"
    assert row["details_confirmed"] is False
    for field in ("start_date", "start_time", "end_date", "end_time", "venue"):
        assert row[field] is None


# --- TC-EVENTREGISTRATIONS-045 --------------------------------------------
@pytest.mark.parametrize(
    "rows, venue",
    [
        ([_booking(H2, "Room B", "confirmed", "2026-10-03T02:00:00Z"), HALL_A], "Hall A"),
        (
            [
                _booking("p", "Room P", "pending", "2026-09-01T02:00:00Z"),
                _booking("q", "Room Q", "held", "2026-09-02T02:00:00Z"),
                _booking("r", "Room R", "rejected", "2026-09-03T02:00:00Z"),
                HALL_A,
            ],
            "Hall A",
        ),
        ([_booking("p", "Room P", "pending", "2026-09-01T02:00:00Z")], None),
        ([], None),
    ],
    ids=["first-confirmed", "unconfirmed-ignored", "only-pending", "none"],
)
def test_only_the_explicit_confirmed_primary_venue_is_shown(client, held, rows, venue):
    _bookings(held, rows)

    row = _only_row(client)

    assert row["venue"] == venue
    assert row["details_confirmed"] is True


# --- TC-EVENTREGISTRATIONS-051..053 ---------------------------------------
def test_secondary_confirmed_venues_are_never_exposed_to_the_attendee(client, held):
    _bookings(held, [
        _booking(H2, "Room B", "confirmed", "2026-09-01T02:00:00Z"),
        HALL_A,
        _booking(H3, "Hall C", "held", "2026-08-01T02:00:00Z", is_primary=True),
    ])

    assert _only_row(client)["venue"] == "Hall A"


def test_confirmed_venues_without_a_primary_read_to_be_confirmed(client, held):
    _bookings(held, [
        _booking(H1, "Hall A", "confirmed", "2026-10-01T02:00:00Z"),
        _booking(H2, "Room B", "confirmed", "2026-10-02T02:00:00Z"),
    ])

    assert _only_row(client)["venue"] is None


# --- TC-EVENTREGISTRATIONS-046 --------------------------------------------
@pytest.mark.parametrize(
    "rows, venue",
    [
        (
            [
                HALL_A,
                _booking(H3, "Hall C", "pending", "2026-10-10T02:00:00Z", replaces_booking_id=H1),
            ],
            "Hall A",
        ),
        (
            [
                _booking(H1, "Hall A", "replaced", "2026-10-01T02:00:00Z", replaced_by_booking_id=H3),
                _booking(H2, "Room B", "confirmed", "2026-10-03T02:00:00Z"),
                _booking(H3, "Hall C", "confirmed", "2026-10-10T02:00:00Z", replaces_booking_id=H1, is_primary=True),
            ],
            "Hall C",
        ),
    ],
    ids=["replacement-pending", "replacement-confirmed"],
)
def test_a_venue_issue_shows_only_once_the_change_is_confirmed(client, held, rows, venue):
    _bookings(held, rows)

    row = _only_row(client)

    assert row["venue"] == venue
    assert set(row) == {
        "event_id", "name", "start_date", "start_time", "end_date", "end_time", "status",
        "registered_at", "joined_at", "position", "details_confirmed", "venue",
    }


# --- TC-EVENTREGISTRATIONS-047 --------------------------------------------
def test_a_waiting_list_entry_shows_no_venue(client, services):
    services["registrations"].waiting[EVENT_E] = [
        {"id": "w0", "event_id": EVENT_E, "attendee_id": "someone-else",
         "created_at": "2026-11-05T03:00:00Z"},
        {"id": "w1", "event_id": EVENT_E, "attendee_id": ATTENDEE_A,
         "created_at": "2026-11-05T04:00:00Z"},
    ]
    _event_status(services, "confirmed")
    _bookings(services, [HALL_A])

    row = _only_row(client)

    assert row["status"] == "waitlisted"
    assert row["position"] == 2
    assert (row["start_date"], row["start_time"]) == ("2026-11-20", "18:00:00")
    assert (row["end_date"], row["end_time"]) == ("2026-11-20", "21:00:00")
    assert row["venue"] is None
    services["bookings"].get.assert_not_called()


# --- TC-EVENTREGISTRATIONS-048 --------------------------------------------
def test_the_list_carries_no_internal_planning_information(client, held):
    _event_status(
        held, "confirmed",
        expected_attendance=120, registration_closed_at="2026-11-03T06:15:00Z",
        organiser_id="o1", assigned_coordinator_id="c1",
    )
    _bookings(held, [{**HALL_A, "coordinator_name": "Cora", "coordinator_email": "cora@example.com",
                      "notes": "Back door code 1234", "special_requirements": "Stage"}])

    row = _only_row(client)

    assert set(row) == {
        "event_id", "name", "start_date", "start_time", "end_date", "end_time", "status",
        "registered_at", "joined_at", "position", "details_confirmed", "venue",
    }
    text = str(row)
    for internal in ("Reconnect alumni", "120", "Cora", "1234", "Stage", "o1", "c1"):
        assert internal not in text


# --- TC-EVENTREGISTRATIONS-049 --------------------------------------------
def test_a_cancelled_or_closed_event_is_not_listed(client, held):
    held["events"].get.side_effect = None
    held["events"].get.return_value = response(404, {"detail": "Event not found."})

    result = client.get(MINE)

    assert result.status_code == 200
    assert result.json() == []


# --- TC-EVENTREGISTRATIONS-050 --------------------------------------------
@pytest.mark.parametrize(
    "failure",
    [response(500, {"detail": "Internal server error"}), httpx.ConnectError("down")],
    ids=["500", "unreachable"],
)
def test_the_bookings_service_fails(client, held, failure):
    held["bookings"].get.return_value = None
    if isinstance(failure, Exception):
        held["bookings"].get.side_effect = failure
    else:
        held["bookings"].get.return_value = failure

    result = client.get(MINE)

    assert result.status_code == 502
    assert result.json()["detail"] == "Bookings service unavailable"
