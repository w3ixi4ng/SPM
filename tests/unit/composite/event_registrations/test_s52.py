"""S-52: an Attendee on a full event's waiting list sees their place in line.

TC-EVENTREGISTRATIONS-027..030. The place is the Attendee's 1-based index in
the event's waiting list, as the registrations service orders it: first come,
first served. The dashboard list shows places and waiting-list entries
together, each marked as one or the other.
"""

from .conftest import ATTENDEE_A, EVENT_E, published, response

ATTENDEE_B = "44444444-4444-4444-8444-444444444444"
ATTENDEE_C = "55555555-5555-4555-8555-555555555555"
EVENT_G = "88888888-8888-4888-8888-888888888888"
EVENT_H = "99999999-9999-4999-8999-999999999999"
REGISTER_E = f"/event-registrations/events/{EVENT_E}/registration"
WAIT_E = f"/event-registrations/events/{EVENT_E}/waiting-list"
MINE = "/event-registrations/me/registrations"
A_JOINED = "2026-11-05T05:00:00Z"


def _row(attendee_id, created_at, event_id=EVENT_E):
    return {"id": f"w-{attendee_id[:4]}-{event_id[:4]}", "event_id": event_id,
            "attendee_id": attendee_id, "created_at": created_at}


def _e_waiting_list(services):
    """B, then A, then C: A is 2nd in line."""
    services["registrations"].waiting[EVENT_E] = [
        _row(ATTENDEE_B, "2026-11-05T04:00:00Z"),
        _row(ATTENDEE_A, A_JOINED),
        _row(ATTENDEE_C, "2026-11-05T06:00:00Z"),
    ]


def _failing(services, path):
    """The registrations service answers 500 on one path, as before elsewhere."""
    base = services["registrations"].get.side_effect

    async def registrations_get(requested, **kwargs):
        if requested == path:
            return response(500, {"detail": "Internal server error"})
        return await base(requested, **kwargs)

    services["registrations"].get.side_effect = registrations_get


# --- TC-EVENTREGISTRATIONS-027 --------------------------------------------
def test_the_attendees_status_gives_their_place_in_line(client, services):
    _e_waiting_list(services)
    result = client.get(REGISTER_E)
    assert result.status_code == 200
    assert result.json() == {
        "event_id": EVENT_E, "registered": False, "registered_at": None,
        "waitlisted": True, "joined_at": A_JOINED, "position": 2, "offered": False,
    }

    services["registrations"].waiting[EVENT_E] = [_row(ATTENDEE_B, "2026-11-05T04:00:00Z")]
    result = client.get(REGISTER_E)
    assert result.json()["waitlisted"] is False
    assert result.json()["joined_at"] is None
    assert result.json()["position"] is None

    _e_waiting_list(services)
    services["registrations"].places[EVENT_E] = [_row(ATTENDEE_A, "2026-11-04T04:00:00Z")]
    services["registrations"].get.reset_mock()
    result = client.get(REGISTER_E)
    assert result.json()["registered"] is True
    assert result.json()["position"] is None
    paths = [call.args[0] for call in services["registrations"].get.await_args_list]
    assert not [path for path in paths if "waiting-list" in path]


# --- TC-EVENTREGISTRATIONS-028 --------------------------------------------
def test_joining_the_waiting_list_answers_with_the_place_in_line(client, services):
    services["registrations"].places[EVENT_E] = [
        _row(ATTENDEE_B, "2026-11-04T04:00:00Z"), _row(ATTENDEE_C, "2026-11-04T05:00:00Z"),
    ]
    services["registrations"].post.return_value = response(
        201, {"id": "w1", "event_id": EVENT_E, "attendee_id": ATTENDEE_A,
              "created_at": "2026-11-05T05:00:00+00:00"}
    )
    services["registrations"].waiting[EVENT_E] = [
        _row(ATTENDEE_B, "2026-11-05T04:00:00Z"), _row(ATTENDEE_A, A_JOINED),
    ]

    result = client.post(WAIT_E)

    assert result.status_code == 201
    assert result.json() == {
        "event_id": EVENT_E, "waitlisted": True, "joined_at": A_JOINED, "position": 2,
    }


# --- TC-EVENTREGISTRATIONS-029 --------------------------------------------
def test_the_attendees_dashboard_list_includes_the_waiting_list(client, services):
    services["registrations"].places[EVENT_G] = [_row(ATTENDEE_A, "2026-11-02T04:00:00Z", EVENT_G)]
    base_registrations = services["registrations"].get.side_effect

    async def registrations_get(path, **kwargs):
        if path == f"/registrations/attendees/{ATTENDEE_A}":
            return response(200, services["registrations"].places[EVENT_G])
        return await base_registrations(path, **kwargs)

    services["registrations"].get.side_effect = registrations_get
    _e_waiting_list(services)
    services["registrations"].waiting[EVENT_H] = [_row(ATTENDEE_A, "2026-11-03T04:00:00Z", EVENT_H)]

    base_events = services["events"].get.side_effect

    async def events_get(path, **kwargs):
        if path == f"/internal/events/attendee-view/{EVENT_G}":
            return response(200, {**published(EVENT_G, name="Careers fair",
                                              start_date="2026-11-10", start_time="10:00:00",
                                              end_date="2026-11-10", end_time="16:00:00"),
                                   "status": "confirmed"})
        # H is no longer public: the default answer is 404.
        return await base_events(path, **kwargs)

    services["events"].get.side_effect = events_get

    result = client.get(MINE)

    assert result.status_code == 200
    assert result.json() == [
        {"event_id": EVENT_G, "name": "Careers fair",
         "start_date": "2026-11-10", "start_time": "10:00:00",
         "end_date": "2026-11-10", "end_time": "16:00:00",
         "status": "confirmed", "registered_at": "2026-11-02T04:00:00Z",
         "joined_at": None, "position": None,
         # S-56: G has no confirmed booking; a waiting-list entry shows no venue.
         "details_confirmed": True, "venue": None},
        {"event_id": EVENT_E, "name": "Alumni networking evening",
         "start_date": "2026-11-20", "start_time": "18:00:00",
         "end_date": "2026-11-20", "end_time": "21:00:00",
         "status": "waitlisted", "registered_at": None,
         "joined_at": A_JOINED, "position": 2,
         "details_confirmed": True, "venue": None},
    ]
    services["registrations"].get.assert_any_call(
        f"/registrations/waiting-list/attendees/{ATTENDEE_A}"
    )


# --- TC-EVENTREGISTRATIONS-030 --------------------------------------------
def test_the_waiting_list_cant_be_read(client, services):
    _e_waiting_list(services)
    _failing(services, f"/registrations/waiting-list/events/{EVENT_E}")
    result = client.get(REGISTER_E)
    assert result.status_code == 502
    assert result.json() == {"detail": "Registrations service unavailable"}

    _failing(services, f"/registrations/waiting-list/attendees/{ATTENDEE_A}")
    result = client.get(MINE)
    assert result.status_code == 502
    assert result.json() == {"detail": "Registrations service unavailable"}
