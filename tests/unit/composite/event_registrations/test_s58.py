"""S-58: an Attendee sees whether each registration is confirmed, waiting or
withdrawn.

TC-EVENTREGISTRATIONS-070..073. The registrations service records each
withdrawal (and each declined offer); this composite lists it on the
Attendee's dashboard until a newer place or waiting-list entry replaces it.
"""

import pytest

from .conftest import ATTENDEE_A, EVENT_E, EVENT_F, published, response

EVENT_G = "88888888-8888-4888-8888-888888888888"
MINE = "/event-registrations/me/registrations"
WITHDRAWN_AT = "2026-10-28T02:15:00+00:00"


def _withdrawal(event_id=EVENT_E):
    return {"id": f"w-{event_id}", "event_id": event_id, "attendee_id": ATTENDEE_A,
            "withdrawn_at": WITHDRAWN_AT}


def _place(event_id):
    return {"id": f"r-{event_id}", "event_id": event_id, "attendee_id": ATTENDEE_A,
            "created_at": "2026-11-05T04:00:00Z"}


def _entry(event_id, offered_at=None):
    return {"id": f"q-{event_id}", "event_id": event_id, "attendee_id": ATTENDEE_A,
            "created_at": "2026-11-04T04:00:00Z", "offered_at": offered_at}


def _places(services, *event_ids):
    """The fake reads an Attendee's places from `/registrations/attendees/`."""
    base = services["registrations"].get.side_effect

    async def registrations_get(path, **kwargs):
        if path == f"/registrations/attendees/{ATTENDEE_A}":
            return response(200, [_place(event_id) for event_id in event_ids])
        return await base(path, **kwargs)

    services["registrations"].get.side_effect = registrations_get


def _attendee_view(services, event_id, answer):
    base = services["events"].get.side_effect

    async def events_get(path, **kwargs):
        if path == f"/internal/events/attendee-view/{event_id}":
            return answer
        return await base(path, **kwargs)

    services["events"].get.side_effect = events_get


# --- TC-EVENTREGISTRATIONS-070 --------------------------------------------
def test_an_event_the_attendee_withdrew_from_reads_withdrawn(client, services):
    services["registrations"].withdrawals[ATTENDEE_A] = [_withdrawal()]

    result = client.get(MINE)

    assert result.status_code == 200
    (row,) = result.json()
    assert row["event_id"] == EVENT_E
    assert row["status"] == "withdrawn"
    assert row["withdrawn_at"] == "2026-10-28T02:15:00Z"
    assert (row["registered_at"], row["joined_at"], row["position"], row["venue"]) == (
        None, None, None, None
    )
    assert row["details_confirmed"] is True
    assert (row["start_date"], row["start_time"]) == ("2026-11-20", "18:00:00")
    services["bookings"].get.assert_not_called()


def test_other_rows_carry_no_withdrawal(client, services):
    services["registrations"].withdrawals[ATTENDEE_A] = [_withdrawal()]
    _places(services, EVENT_F)
    services["registrations"].waiting[EVENT_G] = [_entry(EVENT_G)]
    _attendee_view(
        services, EVENT_G,
        response(200, {**published(EVENT_G, start_date="2026-11-25"), "status": "confirmed"}),
    )

    rows = client.get(MINE).json()

    # E and F start at the same moment, so only G's place after them is fixed.
    assert {row["event_id"]: (row["status"], row["withdrawn_at"]) for row in rows} == {
        EVENT_E: ("withdrawn", "2026-10-28T02:15:00Z"),
        EVENT_F: ("confirmed", None),
        EVENT_G: ("waitlisted", None),
    }
    assert rows[-1]["event_id"] == EVENT_G


# --- TC-EVENTREGISTRATIONS-071 --------------------------------------------
def test_registering_or_waiting_again_replaces_withdrawn(client, services):
    services["registrations"].withdrawals[ATTENDEE_A] = [_withdrawal(), _withdrawal(EVENT_F)]
    _places(services, EVENT_E)
    services["registrations"].waiting[EVENT_F] = [_entry(EVENT_F, "2026-11-06T04:00:00Z")]

    rows = client.get(MINE).json()

    assert sorted((row["event_id"], row["status"]) for row in rows) == sorted([
        (EVENT_E, "confirmed"), (EVENT_F, "offered"),
    ])
    assert [row["withdrawn_at"] for row in rows] == [None, None]


# --- TC-EVENTREGISTRATIONS-072 --------------------------------------------
def test_a_withdrawn_event_is_listed_while_re_checked_without_details(client, services):
    services["registrations"].withdrawals[ATTENDEE_A] = [_withdrawal()]
    _attendee_view(services, EVENT_E, response(200, {**published(), "status": "planning"}))

    (row,) = client.get(MINE).json()

    assert row["status"] == "withdrawn"
    assert row["withdrawn_at"] == "2026-10-28T02:15:00Z"
    assert row["details_confirmed"] is False
    assert [row[field] for field in ("start_date", "start_time", "end_date", "end_time", "venue")] == [
        None, None, None, None, None
    ]


def test_a_withdrawn_event_drops_out_once_over_or_cancelled(client, services):
    services["registrations"].withdrawals[ATTENDEE_A] = [_withdrawal()]
    _attendee_view(services, EVENT_E, response(404, {"detail": "Event not found."}))

    result = client.get(MINE)

    assert result.status_code == 200
    assert result.json() == []


# --- TC-EVENTREGISTRATIONS-073 --------------------------------------------
@pytest.mark.parametrize("status", [500, 503])
def test_the_list_fails_when_withdrawals_cant_be_read(client, services, status):
    base = services["registrations"].get.side_effect

    async def registrations_get(path, **kwargs):
        if path == f"/registrations/withdrawals/attendees/{ATTENDEE_A}":
            return response(status, {"detail": "Registration storage unavailable"})
        return await base(path, **kwargs)

    services["registrations"].get.side_effect = registrations_get

    result = client.get(MINE)

    assert result.status_code == 502
    assert result.json() == {"detail": "Registrations service unavailable"}
