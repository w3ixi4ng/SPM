"""S-51: public event pages and Attendees registering inside the period.

TC-EVENTREGISTRATIONS-001..012; S-48 adds 013..018 and the window wording;
S-49 adds 019..023, the registration confirmation.
"""

from datetime import datetime, timezone

import httpx
import pytest

from .conftest import (
    ATTENDEE_A,
    EVENT_E,
    EVENT_F,
    REGISTERED_AT,
    VENUE_ID,
    me,
    published,
    response,
    sgt,
)

E_PUBLIC = {
    "id": EVENT_E,
    "name": "Alumni networking evening",
    "purpose": "Reconnect alumni with current students",
    "start_date": "2026-11-20",
    "start_time": "18:00:00",
    "end_date": "2026-11-20",
    "end_time": "21:00:00",
    "venues": ["Seminar Room 2-1"],
    "registration_required": True,
    "registration_opens_at": "2026-11-01T09:00:00",
    "registration_closes_at": "2026-11-15T18:00:00",
    # S-50
    "registration_closed_by_organiser": False,
    "is_full": False,
}
REGISTER_E = f"/event-registrations/events/{EVENT_E}/registration"
WINDOW = "from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm"
NOT_OPEN = f"Registration hasn't opened yet. It's open {WINDOW}."
CLOSED = f"Registration has closed. It was open {WINDOW}."


# --- TC-EVENTREGISTRATIONS-001 --------------------------------------------
def test_health_reports_ok(client):
    response_ = client.get("/health")

    assert response_.status_code == 200
    assert response_.json() == {"status": "ok"}


# --- TC-EVENTREGISTRATIONS-002 --------------------------------------------
def test_anyone_can_list_confirmed_events_without_signing_in(client, services):
    result = client.get("/event-registrations/events")

    assert result.status_code == 200
    e, f = result.json()
    assert e == E_PUBLIC
    assert f["id"] == EVENT_F
    assert f["registration_required"] is False
    assert f["registration_opens_at"] is None
    assert f["registration_closes_at"] is None
    assert f["venues"] == []
    for item in (e, f):
        assert not {"organiser_id", "expected_attendance", "contact_name"} & item.keys()
    services["users"].get.assert_not_called()


# --- TC-EVENTREGISTRATIONS-003 --------------------------------------------
def test_one_public_event_and_events_that_arent_public(client):
    result = client.get(f"/event-registrations/events/{EVENT_E}")
    assert result.status_code == 200
    assert result.json() == E_PUBLIC

    result = client.get("/event-registrations/events/99999999-9999-4999-8999-999999999999")
    assert result.status_code == 404
    assert result.json()["detail"] == "Event not found."


# --- TC-EVENTREGISTRATIONS-004 --------------------------------------------
def test_registering_needs_a_signed_in_attendee_account(client, services):
    services["users"].get.return_value = response(401, {"detail": "Not authenticated"})
    result = client.post(REGISTER_E)
    assert result.status_code == 401
    assert result.json()["detail"] == "Sign in to register for this event."

    services["users"].get.return_value = response(200, me(role="event_organiser"))
    result = client.post(REGISTER_E)
    assert result.status_code == 403
    assert result.json()["detail"] == "Only attendee accounts can register for events."
    services["registrations"].post.assert_not_called()

    services["users"].get.return_value = response(200, me())
    assert client.post(REGISTER_E).status_code == 201


# --- TC-EVENTREGISTRATIONS-005 --------------------------------------------
def test_registering_for_an_event_that_doesnt_need_it(client, services):
    result = client.post(f"/event-registrations/events/{EVENT_F}/registration")

    assert result.status_code == 409
    assert result.json()["detail"] == "This event doesn't need registration."
    services["registrations"].post.assert_not_called()


# --- TC-EVENTREGISTRATIONS-006 --------------------------------------------
@pytest.mark.parametrize("moment", ["2026-10-25T10:00", "2026-11-01T08:59"])
def test_registering_before_the_period_opens_is_blocked(client, services, clock, moment):
    clock.now = sgt(moment)

    result = client.post(REGISTER_E)

    assert result.status_code == 409
    assert result.json()["detail"] == NOT_OPEN
    services["registrations"].post.assert_not_called()


def test_registration_opens_at_exactly_the_opening_time(client, clock):
    clock.now = sgt("2026-11-01T09:00")

    assert client.post(REGISTER_E).status_code == 201


# --- TC-EVENTREGISTRATIONS-007 --------------------------------------------
@pytest.mark.parametrize("moment", ["2026-11-15T18:00", "2026-11-18T09:00"])
def test_registering_after_the_period_closes_is_blocked(client, services, clock, moment):
    clock.now = sgt(moment)

    result = client.post(REGISTER_E)

    assert result.status_code == 409
    assert result.json()["detail"] == CLOSED
    services["registrations"].post.assert_not_called()


def test_registration_is_still_open_a_minute_before_closing(client, clock):
    clock.now = sgt("2026-11-15T17:59")

    assert client.post(REGISTER_E).status_code == 201


# --- TC-EVENTREGISTRATIONS-008 --------------------------------------------
def test_registering_inside_the_period_takes_a_place(client, services):
    result = client.post(REGISTER_E, json={"attendee_id": "someone-else"})

    assert result.status_code == 201
    assert result.json() == {
        "event_id": EVENT_E,
        "registered": True,
        "registered_at": REGISTERED_AT,
        "waitlisted": False,
        "joined_at": None,
        "position": None,
    }
    services["registrations"].post.assert_awaited_once_with(
        "/registrations", json={"event_id": EVENT_E, "attendee_id": ATTENDEE_A, "capacity": 2}
    )


# --- TC-EVENTREGISTRATIONS-009 --------------------------------------------
def test_registering_twice(client, services):
    services["registrations"].post.return_value = response(
        409, {"detail": "You're already registered for this event."}
    )

    result = client.post(REGISTER_E)

    assert result.status_code == 409
    assert result.json()["detail"] == "You're already registered for this event."


# --- TC-EVENTREGISTRATIONS-010 --------------------------------------------
@pytest.mark.parametrize(
    "instant, status",
    [
        (datetime(2026, 11, 1, 0, 59, tzinfo=timezone.utc), 409),
        (datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc), 201),
    ],
)
def test_now_is_singapore_time_whatever_the_servers_clock(client, clock, instant, status):
    clock.now = instant

    result = client.post(REGISTER_E)

    assert result.status_code == status
    if status == 409:
        assert result.json()["detail"] == NOT_OPEN


# --- TC-EVENTREGISTRATIONS-011 --------------------------------------------
def test_an_attendee_sees_whether_they_hold_a_place(client, services):
    services["registrations"].get.return_value = response(
        200,
        {"id": "r1", "event_id": EVENT_E, "attendee_id": ATTENDEE_A, "created_at": REGISTERED_AT},
    )
    result = client.get(REGISTER_E)
    assert result.status_code == 200
    assert result.json() == {
        "event_id": EVENT_E, "registered": True, "registered_at": REGISTERED_AT,
        "waitlisted": False, "joined_at": None, "position": None,
    }
    services["registrations"].get.assert_awaited_with(
        f"/registrations/events/{EVENT_E}/attendees/{ATTENDEE_A}"
    )

    services["registrations"].get.return_value = response(
        404, {"detail": "You're not registered for this event."}
    )
    result = client.get(REGISTER_E)
    assert result.status_code == 200
    assert result.json() == {
        "event_id": EVENT_E, "registered": False, "registered_at": None,
        "waitlisted": False, "joined_at": None, "position": None,
    }


# --- TC-EVENTREGISTRATIONS-012 --------------------------------------------
def test_a_service_it_depends_on_is_down(client, services):
    services["events"].get.side_effect = httpx.ConnectError("events down")
    result = client.post(REGISTER_E)
    assert result.status_code == 502
    assert result.json()["detail"] == "Events service unavailable"

    services["events"].get.side_effect = None
    services["events"].get.return_value = response(200, published())
    services["registrations"].post.side_effect = httpx.ConnectError("registrations down")
    result = client.post(REGISTER_E)
    assert result.status_code == 502
    assert result.json()["detail"] == "Registrations service unavailable"


# --- S-48 ------------------------------------------------------------------
ATTENDEE_B = "44444444-4444-4444-8444-444444444444"
EVENT_G = "88888888-8888-4888-8888-888888888888"
ATTENDEES_E = f"/event-registrations/events/{EVENT_E}/attendees"
MINE = "/event-registrations/me/registrations"


def _row(event_id, attendee_id, created_at):
    return {"id": "r", "event_id": event_id, "attendee_id": attendee_id, "created_at": created_at}


def _organiser_owns_e(services, answer=None):
    async def events_get(path, **kwargs):
        if path == f"/events/{EVENT_E}":
            return answer or response(200, {"id": EVENT_E})
        return response(404, {"detail": "Event not found."})

    services["events"].get.side_effect = events_get


def _registrations_answer(services, rows):
    services["registrations"].get.return_value = response(200, rows)


# --- TC-EVENTREGISTRATIONS-013 --------------------------------------------
def test_the_organiser_sees_who_registered_for_their_event(client, services):
    _organiser_owns_e(services)
    _registrations_answer(
        services,
        [
            _row(EVENT_E, ATTENDEE_A, "2026-11-05T04:00:00Z"),
            _row(EVENT_E, ATTENDEE_B, "2026-11-06T04:00:00Z"),
        ],
    )
    services["users"].post.return_value = response(
        200,
        [
            {"id": ATTENDEE_B, "name": "Ben Lim", "email": "ben@example.com"},
            {"id": ATTENDEE_A, "name": "Ada Tan", "email": "ada@example.com"},
        ],
    )

    client.cookies.set("sb-access-token", "organiser")
    result = client.get(ATTENDEES_E)

    assert result.status_code == 200
    assert result.json() == {
        "event_id": EVENT_E,
        "count": 2,
        "attendees": [
            {"attendee_id": ATTENDEE_A, "name": "Ada Tan", "email": "ada@example.com",
             "registered_at": "2026-11-05T04:00:00Z"},
            {"attendee_id": ATTENDEE_B, "name": "Ben Lim", "email": "ben@example.com",
             "registered_at": "2026-11-06T04:00:00Z"},
        ],
        "waiting_list": [],
    }
    path = services["events"].get.call_args.args[0]
    assert path == f"/events/{EVENT_E}"
    assert services["events"].get.call_args.kwargs["cookies"] == {"sb-access-token": "organiser"}
    services["registrations"].get.assert_any_call(f"/registrations/events/{EVENT_E}")
    services["users"].post.assert_called_once_with(
        "/internal/users/profiles", json={"ids": [ATTENDEE_A, ATTENDEE_B]}
    )


# --- TC-EVENTREGISTRATIONS-014 --------------------------------------------
def test_an_event_no_one_has_registered_for_yet(client, services):
    _organiser_owns_e(services)
    _registrations_answer(services, [])

    result = client.get(ATTENDEES_E)

    assert result.status_code == 200
    assert result.json() == {"event_id": EVENT_E, "count": 0, "attendees": [], "waiting_list": []}
    services["users"].post.assert_not_called()


# --- TC-EVENTREGISTRATIONS-015 --------------------------------------------
@pytest.mark.parametrize(
    "answer, status, detail",
    [
        (response(401, {"detail": "Not authenticated"}), 401, "Sign in to see who has registered."),
        (response(403, {"detail": "Insufficient permissions"}), 403, "Insufficient permissions"),
        (response(404, {"detail": "Event not found"}), 404, "Event not found"),
    ],
)
def test_only_the_events_own_organiser_sees_its_attendees(client, services, answer, status, detail):
    _organiser_owns_e(services, answer)

    result = client.get(ATTENDEES_E)

    assert result.status_code == status
    assert result.json()["detail"] == detail
    services["registrations"].get.assert_not_called()
    services["users"].post.assert_not_called()


# --- TC-EVENTREGISTRATIONS-016 --------------------------------------------
def test_an_attendee_sees_the_events_they_registered_for(client, services):
    _registrations_answer(
        services,
        [
            _row(EVENT_E, ATTENDEE_A, "2026-11-05T04:00:00Z"),
            _row(EVENT_G, ATTENDEE_A, "2026-11-02T04:00:00Z"),
        ],
    )
    base = services["events"].get.side_effect

    async def events_get(path, **kwargs):
        if path == f"/internal/events/published/{EVENT_G}":
            return response(200, {**E_PUBLIC, "id": EVENT_G, "name": "Careers fair",
                                  "start_date": "2026-11-10", "start_time": "10:00:00",
                                  "end_date": "2026-11-10", "end_time": "16:00:00"})
        return await base(path, **kwargs)

    services["events"].get.side_effect = events_get

    # The attendee id comes from the session; nothing in the request names one.
    result = client.get(MINE)

    assert result.status_code == 200
    g, e = result.json()
    assert g["event_id"] == EVENT_G
    assert g["registered_at"] == "2026-11-02T04:00:00Z"
    assert e == {
        "event_id": EVENT_E,
        "name": "Alumni networking evening",
        "start_date": "2026-11-20",
        "start_time": "18:00:00",
        "end_date": "2026-11-20",
        "end_time": "21:00:00",
        # S-52: every row says whether it is a place or a waiting-list entry.
        "status": "confirmed",
        "registered_at": "2026-11-05T04:00:00Z",
        "joined_at": None,
        "position": None,
    }
    services["registrations"].get.assert_any_call(f"/registrations/attendees/{ATTENDEE_A}")


# --- TC-EVENTREGISTRATIONS-017 --------------------------------------------
def test_an_attendee_with_no_public_registrations(client, services):
    _registrations_answer(services, [])
    result = client.get(MINE)
    assert result.status_code == 200
    assert result.json() == []
    services["events"].get.assert_not_called()

    _registrations_answer(services, [_row(EVENT_E, ATTENDEE_A, REGISTERED_AT)])
    services["events"].get.side_effect = None
    services["events"].get.return_value = response(404, {"detail": "Event not found."})
    result = client.get(MINE)
    assert result.status_code == 200
    assert result.json() == []


# --- TC-EVENTREGISTRATIONS-018 --------------------------------------------
@pytest.mark.parametrize(
    "answer, status, detail",
    [
        (response(401, {"detail": "Not authenticated"}), 401, "Sign in to register for this event."),
        (response(200, me(role="event_organiser")), 403, "Only attendee accounts can register for events."),
    ],
)
def test_the_attendees_list_needs_a_signed_in_attendee(client, services, answer, status, detail):
    services["users"].get.return_value = answer

    result = client.get(MINE)

    assert result.status_code == status
    assert result.json()["detail"] == detail
    services["registrations"].get.assert_not_called()


# --- S-49: registration confirmation --------------------------------------

REGISTRATION_ID = "88888888-8888-4888-8888-888888888888"
CONFIRMED_E = (
    "Registration confirmed: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, "
    "at Seminar Room 2-1. Name: Ada Tan. Email: ada@example.com."
)


@pytest.fixture
def ada(services):
    """Attendee A as the S-49 cases name her, and the id her place is given."""
    services["users"].get.return_value = response(200, {**me(), "name": "Ada Tan"})
    services["registrations"].post.return_value = response(
        201,
        {"id": REGISTRATION_ID, "event_id": EVENT_E, "attendee_id": ATTENDEE_A,
         "created_at": REGISTERED_AT},
    )
    return services


def _sent_rows(services):
    calls = services["notifications"].post.call_args_list
    assert len(calls) == 1
    path = calls[0].args[0]
    assert path == "/internal/notifications"
    return calls[0].kwargs["json"]["notifications"]


def _event_e_is(services, **changes):
    async def events_get(path, **kwargs):
        if path == f"/internal/events/published/{EVENT_E}":
            return response(200, published(**changes))
        return response(404, {"detail": "Event not found."})

    services["events"].get.side_effect = events_get


def _bookings_are(services, rows):
    services["bookings"].get.side_effect = None
    services["bookings"].get.return_value = response(200, rows)


# --- TC-EVENTREGISTRATIONS-019 --------------------------------------------
def test_a_successful_registration_sends_the_attendee_one_confirmation(client, ada):
    order = []
    registered = ada["registrations"].post.return_value
    ada["registrations"].post.side_effect = lambda *a, **k: order.append("registrations") or registered
    ada["notifications"].post.side_effect = (
        lambda *a, **k: order.append("notifications") or response(201, [])
    )

    result = client.post(REGISTER_E)

    assert result.status_code == 201
    assert _sent_rows(ada) == [
        {
            "recipient_id": ATTENDEE_A,
            "event_id": EVENT_E,
            "event_name": "Alumni networking evening",
            "kind": "registration_confirmation",
            "message": CONFIRMED_E,
            "deduplication_key": f"registration_confirmation:{REGISTRATION_ID}",
        }
    ]
    assert order == ["registrations", "notifications"]


# --- TC-EVENTREGISTRATIONS-020 --------------------------------------------
def test_an_event_spanning_days_shows_both_dates(client, ada):
    _event_e_is(ada, start_time="12:00:00", end_date="2026-11-21", end_time="00:30:00")

    result = client.post(REGISTER_E)

    assert result.status_code == 201
    assert _sent_rows(ada)[0]["message"] == (
        "Registration confirmed: Alumni networking evening, 20 Nov 2026, 12:00 pm – "
        "21 Nov 2026, 12:30 am, at Seminar Room 2-1. Name: Ada Tan. Email: ada@example.com."
    )


# --- TC-EVENTREGISTRATIONS-021 --------------------------------------------
def test_no_confirmed_venue_reads_to_be_confirmed(client, ada):
    _bookings_are(ada, [{"id": "b1", "venue_id": VENUE_ID, "status": "pending"}])

    result = client.post(REGISTER_E)

    assert result.status_code == 201
    assert _sent_rows(ada)[0]["message"] == (
        "Registration confirmed: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, "
        "venue to be confirmed. Name: Ada Tan. Email: ada@example.com."
    )


def test_several_confirmed_venues_are_joined(client, ada):
    hall = "99999999-9999-4999-8999-999999999999"
    _bookings_are(ada, [
        {"id": "b1", "venue_id": VENUE_ID, "status": "confirmed"},
        {"id": "b2", "venue_id": hall, "status": "confirmed"},
    ])
    names = {VENUE_ID: "Seminar Room 2-1", hall: "Hall A"}

    async def venues_get(path, **kwargs):
        venue_id = path.rsplit("/", 1)[-1]
        return response(200, {"id": venue_id, "name": names[venue_id]})

    ada["venues"].get.side_effect = venues_get

    result = client.post(REGISTER_E)

    assert result.status_code == 201
    assert _sent_rows(ada)[0]["message"] == (
        "Registration confirmed: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, "
        "at Seminar Room 2-1, Hall A. Name: Ada Tan. Email: ada@example.com."
    )


# --- TC-EVENTREGISTRATIONS-022 --------------------------------------------
def _signed_out(services, clock):
    services["users"].get.return_value = response(401, {"detail": "Not authenticated"})


def _organiser(services, clock):
    services["users"].get.return_value = response(200, me(role="event_organiser"))


def _missing_event(services, clock):
    services["events"].get.side_effect = None
    services["events"].get.return_value = response(404, {"detail": "Event not found."})


def _registration_off(services, clock):
    _event_e_is(services, registration_required=False,
                registration_opens_at=None, registration_closes_at=None)


def _before_opening(services, clock):
    clock.now = sgt("2026-10-31T12:00")


def _at_closing(services, clock):
    clock.now = sgt("2026-11-15T18:00")


def _already_registered(services, clock):
    services["registrations"].post.return_value = response(
        409, {"detail": "You're already registered for this event."}
    )


def _registrations_down(services, clock):
    services["registrations"].post.return_value = response(500, {"detail": "boom"})


@pytest.mark.parametrize(
    ("setup", "status", "detail"),
    [
        (_signed_out, 401, "Sign in to register for this event."),
        (_organiser, 403, "Only attendee accounts can register for events."),
        (_missing_event, 404, "Event not found."),
        (_registration_off, 409, "This event doesn't need registration."),
        (_before_opening, 409, NOT_OPEN),
        (_at_closing, 409, CLOSED),
        (_already_registered, 409, "You're already registered for this event."),
        (_registrations_down, 502, "Registrations service unavailable"),
    ],
)
def test_no_confirmation_when_the_registration_did_not_succeed(
    client, ada, clock, setup, status, detail
):
    setup(ada, clock)

    result = client.post(REGISTER_E)

    assert result.status_code == status
    assert result.json()["detail"] == detail
    ada["notifications"].post.assert_not_called()


# --- TC-EVENTREGISTRATIONS-023 --------------------------------------------
# S-50: every registration answer also says whether the Attendee is waitlisted.
REGISTERED_E = {
    "event_id": EVENT_E, "registered": True, "registered_at": REGISTERED_AT,
    "waitlisted": False, "joined_at": None, "position": None,
}


def test_a_confirmation_that_isnt_stored_keeps_the_registration(client, ada):
    ada["notifications"].post.return_value = response(500, {"detail": "Internal server error"})

    result = client.post(REGISTER_E)

    assert result.status_code == 201
    assert result.json() == REGISTERED_E


def test_an_unreachable_notifications_service_keeps_the_registration(client, ada):
    ada["notifications"].post.side_effect = httpx.ConnectError("down")

    result = client.post(REGISTER_E)

    assert result.status_code == 201
    assert result.json() == REGISTERED_E


def test_unreadable_venues_keep_the_registration_and_send_nothing(client, ada):
    ada["bookings"].get.side_effect = None
    ada["bookings"].get.return_value = response(500, {"detail": "boom"})

    result = client.post(REGISTER_E)

    assert result.status_code == 201
    assert result.json() == REGISTERED_E
    ada["notifications"].post.assert_not_called()
