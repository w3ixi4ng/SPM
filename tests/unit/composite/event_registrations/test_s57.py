"""S-57: the Organiser, and the event's assigned Coordinator, see who is registered.

TC-EVENTREGISTRATIONS-062..065. The events service decides who may see the
list: `GET /events/E` answers the owning Organiser, and when it refuses with
403 the composite asks `GET /events/assigned/E`, which answers the assigned
Coordinator. Withdrawn Attendees hold no place, so they are simply absent.
"""

import pytest

from .conftest import ATTENDEE_A, EVENT_E, response

ATTENDEE_B = "44444444-4444-4444-8444-444444444444"
ATTENDEES_E = f"/event-registrations/events/{EVENT_E}/attendees"
FORBIDDEN = response(403, {"detail": "Insufficient permissions"})
NOT_FOUND = response(404, {"detail": "Event not found"})

ADA = {"id": ATTENDEE_A, "name": "Ada Tan", "email": "ada@example.com"}
BEN = {"id": ATTENDEE_B, "name": "Ben Lim", "email": "ben@example.com"}
ADA_ROW = {"id": "r1", "event_id": EVENT_E, "attendee_id": ATTENDEE_A,
           "created_at": "2026-11-05T04:00:00Z"}
BEN_ROW = {"id": "r2", "event_id": EVENT_E, "attendee_id": ATTENDEE_B,
           "created_at": "2026-11-06T04:00:00Z"}
ADA_LISTED = {"attendee_id": ATTENDEE_A, "name": "Ada Tan", "email": "ada@example.com",
              "registered_at": "2026-11-05T04:00:00Z"}
BEN_LISTED = {"attendee_id": ATTENDEE_B, "name": "Ben Lim", "email": "ben@example.com",
              "registered_at": "2026-11-06T04:00:00Z"}


def _event_answers(services, owned, assigned):
    async def events_get(path, **kwargs):
        if path == f"/events/{EVENT_E}":
            return owned
        if path == f"/events/assigned/{EVENT_E}":
            return assigned
        return NOT_FOUND

    services["events"].get.side_effect = events_get


def _profiles(services, *people):
    async def users_post(path, json=None, **kwargs):
        return response(200, [person for person in people if person["id"] in json["ids"]])

    services["users"].post.side_effect = users_post


# --- TC-EVENTREGISTRATIONS-062 --------------------------------------------
def test_the_assigned_coordinator_sees_who_registered(client, services):
    _event_answers(services, owned=FORBIDDEN, assigned=response(200, {"id": EVENT_E}))
    services["registrations"].places[EVENT_E] = [ADA_ROW, BEN_ROW]
    _profiles(services, ADA, BEN)

    client.cookies.set("sb-access-token", "coordinator")
    result = client.get(ATTENDEES_E)

    assert result.status_code == 200
    assert result.json() == {
        "event_id": EVENT_E,
        "count": 2,
        "attendees": [ADA_LISTED, BEN_LISTED],
        "waiting_list": [],
    }
    calls = services["events"].get.call_args_list
    assert [call.args[0] for call in calls] == [f"/events/{EVENT_E}", f"/events/assigned/{EVENT_E}"]
    assert all(call.kwargs["cookies"] == {"sb-access-token": "coordinator"} for call in calls)


# --- TC-EVENTREGISTRATIONS-063 --------------------------------------------
def test_a_coordinator_not_assigned_to_the_event_is_refused(client, services):
    _event_answers(services, owned=FORBIDDEN, assigned=NOT_FOUND)

    result = client.get(ATTENDEES_E)

    assert result.status_code == 404
    assert result.json()["detail"] == "Event not found"
    services["registrations"].get.assert_not_called()
    services["users"].post.assert_not_called()


# --- TC-EVENTREGISTRATIONS-064 --------------------------------------------
@pytest.mark.parametrize("role", ["attendee", "venue_staff", "event_coordinator_lead"])
def test_every_other_role_is_still_refused_the_attendee_list(client, services, role):
    _event_answers(services, owned=FORBIDDEN, assigned=FORBIDDEN)

    client.cookies.set("sb-access-token", role)
    result = client.get(ATTENDEES_E)

    assert result.status_code == 403
    assert result.json()["detail"] == "Insufficient permissions"
    services["registrations"].get.assert_not_called()
    services["users"].post.assert_not_called()


def test_signed_out_is_answered_without_asking_as_a_coordinator(client, services):
    _event_answers(services, owned=response(401, {"detail": "Not authenticated"}),
                   assigned=response(200, {"id": EVENT_E}))

    result = client.get(ATTENDEES_E)

    assert result.status_code == 401
    assert result.json()["detail"] == "Sign in to see who has registered."
    paths = [call.args[0] for call in services["events"].get.call_args_list]
    assert paths == [f"/events/{EVENT_E}"]
    services["registrations"].get.assert_not_called()


# --- TC-EVENTREGISTRATIONS-065 --------------------------------------------
def test_each_read_shows_the_registrations_as_they_are_now(client, services):
    _event_answers(services, owned=response(200, {"id": EVENT_E}), assigned=FORBIDDEN)
    _profiles(services, ADA, BEN)
    places = services["registrations"].places

    places[EVENT_E] = [ADA_ROW, BEN_ROW]
    both = client.get(ATTENDEES_E).json()
    places[EVENT_E] = [BEN_ROW]  # A withdrew
    one = client.get(ATTENDEES_E)
    places[EVENT_E] = []  # B withdrew
    none = client.get(ATTENDEES_E)

    assert both["count"] == 2
    assert both["attendees"] == [ADA_LISTED, BEN_LISTED]
    assert one.status_code == 200
    assert one.json()["count"] == 1
    assert one.json()["attendees"] == [BEN_LISTED]
    assert ATTENDEE_A not in one.text
    assert none.status_code == 200
    assert none.json() == {"event_id": EVENT_E, "count": 0, "attendees": [], "waiting_list": []}
    place_reads = [
        call for call in services["registrations"].get.call_args_list
        if call.args[0] == f"/registrations/events/{EVENT_E}"
    ]
    assert len(place_reads) == 3
