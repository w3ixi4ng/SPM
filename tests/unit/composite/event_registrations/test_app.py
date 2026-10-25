"""S-51: public event pages and Attendees registering inside the period.

TC-EVENTREGISTRATIONS-001..012; S-48 adds 013..018 and the window wording.
"""

from datetime import datetime, timezone

import httpx
import pytest

from .conftest import (
    ATTENDEE_A,
    EVENT_E,
    EVENT_F,
    REGISTERED_AT,
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
        "waitlisted": False, "joined_at": None,
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
        "waitlisted": False, "joined_at": None,
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
        "registered_at": "2026-11-05T04:00:00Z",
    }
    services["registrations"].get.assert_called_once_with(f"/registrations/attendees/{ATTENDEE_A}")


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
