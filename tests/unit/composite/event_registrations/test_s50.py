"""S-50: registration capped at the event's expected attendance.

TC-EVENTREGISTRATIONS-019..026. Once full, an Attendee is offered the
waiting list; the Organiser can close registration early, and that close
wins over the waiting list.
"""

import pytest

from .conftest import ATTENDEE_A, EVENT_E, me, published, response, sgt

ATTENDEE_B = "44444444-4444-4444-8444-444444444444"
ATTENDEE_C = "55555555-5555-4555-8555-555555555555"
EVENT_G = "88888888-8888-4888-8888-888888888888"
CLOSED_AT = "2026-11-03T06:15:00+00:00"
JOINED_AT = "2026-11-05T04:00:00Z"
REGISTER_E = f"/event-registrations/events/{EVENT_E}/registration"
WAIT_E = f"/event-registrations/events/{EVENT_E}/waiting-list"

FULL = "This event is full. You can join the waiting list."
CLOSED_BY_ORGANISER = "The organiser has closed registration for this event."


def _row(attendee_id, created_at="2026-11-04T04:00:00Z", event_id=EVENT_E):
    return {"id": f"r-{attendee_id[:4]}", "event_id": event_id,
            "attendee_id": attendee_id, "created_at": created_at}


def _places(services, event_id, *attendees):
    services["registrations"].places[event_id] = [_row(a, event_id=event_id) for a in attendees]


def _waiting(services, event_id, *rows):
    services["registrations"].waiting[event_id] = list(rows)


def _event_e(services, **changes):
    """Replace E as the events service returns it."""
    base = services["events"].get.side_effect

    async def events_get(path, **kwargs):
        if path == f"/internal/events/published/{EVENT_E}":
            return response(200, published(**changes))
        if path == "/internal/events/published":
            return response(200, [published(**changes)])
        return await base(path, **kwargs)

    services["events"].get.side_effect = events_get


# --- TC-EVENTREGISTRATIONS-019 --------------------------------------------
def test_the_public_event_says_when_it_is_full_or_closed(client, services):
    _places(services, EVENT_E, ATTENDEE_A, ATTENDEE_B)
    _places(services, EVENT_G, ATTENDEE_A)
    base = services["events"].get.side_effect

    async def events_get(path, **kwargs):
        g = published(EVENT_G, expected_attendance=50, registration_closed_at=CLOSED_AT)
        if path == f"/internal/events/published/{EVENT_G}":
            return response(200, g)
        if path == "/internal/events/published":
            return response(200, [published(), g])
        return await base(path, **kwargs)

    services["events"].get.side_effect = events_get

    e = client.get(f"/event-registrations/events/{EVENT_E}").json()
    g = client.get(f"/event-registrations/events/{EVENT_G}").json()
    listed = client.get("/event-registrations/events").json()

    assert (e["is_full"], e["registration_closed_by_organiser"]) == (True, False)
    assert (g["is_full"], g["registration_closed_by_organiser"]) == (False, True)
    assert [(i["is_full"], i["registration_closed_by_organiser"]) for i in listed] == [
        (True, False), (False, True),
    ]
    for body in (e, g, *listed):
        assert not {"expected_attendance", "registration_closed_at"} & body.keys()


# --- TC-EVENTREGISTRATIONS-020 --------------------------------------------
def test_registering_is_capped_at_the_events_expected_attendance(client, services):
    result = client.post(REGISTER_E)

    assert result.status_code == 201
    assert result.json()["registered"] is True
    services["registrations"].post.assert_awaited_once_with(
        "/registrations", json={"event_id": EVENT_E, "attendee_id": ATTENDEE_A, "capacity": 2}
    )


# --- TC-EVENTREGISTRATIONS-021 --------------------------------------------
def test_a_full_event_offers_the_waiting_list_instead(client, services):
    services["registrations"].post.return_value = response(409, {"detail": "This event is full."})

    result = client.post(REGISTER_E)

    assert result.status_code == 409
    assert result.json() == {"detail": FULL}


# --- TC-EVENTREGISTRATIONS-022 --------------------------------------------
def test_registration_closed_by_the_organiser_is_refused(client, services):
    _event_e(services, registration_closed_at=CLOSED_AT)

    result = client.post(REGISTER_E)

    assert result.status_code == 409
    assert result.json() == {"detail": CLOSED_BY_ORGANISER}
    services["registrations"].post.assert_not_called()


# --- TC-EVENTREGISTRATIONS-023 --------------------------------------------
def test_joining_the_waiting_list_of_a_full_event(client, services):
    _places(services, EVENT_E, ATTENDEE_B, ATTENDEE_C)
    services["registrations"].post.return_value = response(
        201, {"id": "w1", "event_id": EVENT_E, "attendee_id": ATTENDEE_A, "created_at": JOINED_AT}
    )

    result = client.post(WAIT_E, json={"attendee_id": ATTENDEE_B})

    assert result.status_code == 201
    assert result.json() == {"event_id": EVENT_E, "waitlisted": True, "joined_at": JOINED_AT}
    services["registrations"].post.assert_awaited_once_with(
        "/registrations/waiting-list", json={"event_id": EVENT_E, "attendee_id": ATTENDEE_A}
    )


# --- TC-EVENTREGISTRATIONS-024 --------------------------------------------
@pytest.mark.parametrize(
    "situation, status, detail",
    [
        ("signed_out", 401, "Sign in to register for this event."),
        ("organiser", 403, "Only attendee accounts can register for events."),
        ("not_full", 409, "This event still has places. Register instead."),
        ("period_over", 409,
         "Registration has closed. It was open from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm."),
        ("closed_by_organiser", 409, CLOSED_BY_ORGANISER),
        ("already_registered", 409, "You're already registered for this event."),
        ("already_waiting", 409, "You're already on the waiting list for this event."),
        ("registration_off", 409, "This event doesn't need registration."),
    ],
)
def test_when_the_waiting_list_is_refused(client, services, clock, situation, status, detail):
    _places(services, EVENT_E, ATTENDEE_B, ATTENDEE_C)
    if situation == "signed_out":
        services["users"].get.return_value = response(401, {"detail": "Not authenticated"})
    elif situation == "organiser":
        services["users"].get.return_value = response(200, me(role="event_organiser"))
    elif situation == "not_full":
        _places(services, EVENT_E, ATTENDEE_B)
    elif situation == "period_over":
        clock.now = sgt("2026-11-16T12:00")
    elif situation == "closed_by_organiser":
        _event_e(services, registration_closed_at=CLOSED_AT)
    elif situation == "already_registered":
        _places(services, EVENT_E, ATTENDEE_A, ATTENDEE_B)
    elif situation == "already_waiting":
        services["registrations"].post.return_value = response(
            409, {"detail": "You're already on the waiting list for this event."}
        )
    elif situation == "registration_off":
        _event_e(services, registration_required=False,
                 registration_opens_at=None, registration_closes_at=None)

    result = client.post(WAIT_E)

    assert result.status_code == status
    assert result.json()["detail"] == detail
    if situation != "already_waiting":
        services["registrations"].post.assert_not_called()


# --- TC-EVENTREGISTRATIONS-025 --------------------------------------------
def test_the_attendees_status_shows_the_waiting_list(client, services):
    _waiting(services, EVENT_E, _row(ATTENDEE_A, JOINED_AT))
    result = client.get(REGISTER_E)
    assert result.status_code == 200
    assert result.json() == {
        "event_id": EVENT_E, "registered": False, "registered_at": None,
        "waitlisted": True, "joined_at": JOINED_AT,
    }

    _waiting(services, EVENT_E)
    result = client.get(REGISTER_E)
    assert result.json()["waitlisted"] is False
    assert result.json()["joined_at"] is None

    _places(services, EVENT_E, ATTENDEE_A)
    services["registrations"].get.reset_mock()
    result = client.get(REGISTER_E)
    assert result.json()["registered"] is True
    assert result.json()["waitlisted"] is False
    paths = [c.args[0] for c in services["registrations"].get.call_args_list]
    assert not any("waiting-list" in path for path in paths)


# --- TC-EVENTREGISTRATIONS-026 --------------------------------------------
def test_the_organiser_sees_the_waiting_list_in_join_order(client, services):
    async def events_get(path, **kwargs):
        if path == f"/events/{EVENT_E}":
            return response(200, {"id": EVENT_E})
        return response(404, {"detail": "Event not found."})

    services["events"].get.side_effect = events_get
    _places(services, EVENT_E, ATTENDEE_A, ATTENDEE_B)
    _waiting(services, EVENT_E,
             _row(ATTENDEE_C, "2026-11-05T04:00:00Z"),
             _row("66666666-6666-4666-8666-666666666666", "2026-11-05T05:00:00Z"))
    services["users"].post.return_value = response(200, [
        {"id": ATTENDEE_A, "name": "Ada Tan", "email": "ada@example.com"},
        {"id": ATTENDEE_B, "name": "Ben Lim", "email": "ben@example.com"},
        {"id": ATTENDEE_C, "name": "Cai Wen", "email": "cai@example.com"},
        {"id": "66666666-6666-4666-8666-666666666666", "name": "Dev Rao", "email": "dev@example.com"},
    ])

    result = client.get(f"/event-registrations/events/{EVENT_E}/attendees")

    assert result.status_code == 200
    body = result.json()
    assert body["count"] == 2
    assert body["waiting_list"] == [
        {"attendee_id": ATTENDEE_C, "name": "Cai Wen", "email": "cai@example.com",
         "joined_at": "2026-11-05T04:00:00Z"},
        {"attendee_id": "66666666-6666-4666-8666-666666666666", "name": "Dev Rao",
         "email": "dev@example.com", "joined_at": "2026-11-05T05:00:00Z"},
    ]

    _waiting(services, EVENT_E)
    assert client.get(f"/event-registrations/events/{EVENT_E}/attendees").json()["waiting_list"] == []
