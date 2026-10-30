"""S-53: a registered Attendee withdraws until the event starts.

TC-EVENTREGISTRATIONS-036..041. S-55 retired 039 and 040: the freed place is
now offered, not given, and test_s55.py covers telling the next in line.
"""

from datetime import datetime, timezone

import httpx
import pytest

from .conftest import ATTENDEE_A, EVENT_E, me, published, response, sgt

WITHDRAW_E = f"/event-registrations/events/{EVENT_E}/registration"
NOT_REGISTERED = "You're not registered for this event."
STARTED = "This event has already started. You can no longer withdraw."
WITHDRAWN = {
    "event_id": EVENT_E, "registered": False, "registered_at": None,
    "waitlisted": False, "joined_at": None, "position": None, "offered": False,
}
A_ROW = {"id": "r-a", "event_id": EVENT_E, "attendee_id": ATTENDEE_A,
         "created_at": "2026-11-05T04:00:00Z"}


@pytest.fixture
def withdrawing(services):
    """A holds a place at E; no one is waiting."""
    services["registrations"].post.return_value = response(
        200, {"withdrawn": A_ROW, "offered": None}
    )
    return services


def _event_e_is(services, **changes):
    base = services["events"].get.side_effect

    async def events_get(path, **kwargs):
        if path == f"/internal/events/published/{EVENT_E}":
            return response(200, published(**changes))
        return await base(path, **kwargs)

    services["events"].get.side_effect = events_get


# --- TC-EVENTREGISTRATIONS-036 --------------------------------------------
def test_a_registered_attendee_withdraws(client, withdrawing):
    result = client.delete(WITHDRAW_E)

    assert result.status_code == 200
    assert result.json() == WITHDRAWN
    withdrawing["registrations"].post.assert_awaited_once_with(
        "/registrations/withdrawals",
        json={"event_id": EVENT_E, "attendee_id": ATTENDEE_A, "capacity": 2},
    )
    # S-74: the only notice is the withdrawing Attendee's own; no one was offered the place.
    sent = [
        row["kind"]
        for call in withdrawing["notifications"].post.call_args_list
        for row in call.kwargs["json"]["notifications"]
    ]
    assert sent == ["registration_withdrawn"]


# --- TC-EVENTREGISTRATIONS-037 --------------------------------------------
@pytest.mark.parametrize(
    ("now", "changes"),
    [
        ("2026-11-16T12:00", {}),
        ("2026-11-05T12:00", {"registration_closed_at": "2026-11-04T02:00:00+00:00"}),
        ("2026-11-20T17:59", {}),
    ],
)
def test_withdrawing_is_open_until_the_event_starts(client, withdrawing, clock, now, changes):
    clock.now = sgt(now)
    _event_e_is(withdrawing, **changes)

    result = client.delete(WITHDRAW_E)

    assert result.status_code == 200
    withdrawing["registrations"].post.assert_awaited_once()


@pytest.mark.parametrize("now", ["2026-11-20T18:00", "2026-11-21T09:00"])
def test_withdrawing_is_refused_once_the_event_starts(client, withdrawing, clock, now):
    clock.now = sgt(now)

    result = client.delete(WITHDRAW_E)

    assert result.status_code == 409
    assert result.json() == {"detail": STARTED}
    withdrawing["registrations"].post.assert_not_called()


def test_the_cutoff_is_read_in_singapore_time(client, withdrawing, clock):
    clock.now = datetime(2026, 11, 20, 9, 59, tzinfo=timezone.utc)

    assert client.delete(WITHDRAW_E).status_code == 200


# --- TC-EVENTREGISTRATIONS-038 --------------------------------------------
def test_withdrawing_needs_a_signed_in_attendee(client, withdrawing):
    withdrawing["users"].get.return_value = response(401, {"detail": "Not signed in"})
    result = client.delete(WITHDRAW_E)
    assert result.status_code == 401
    assert result.json() == {"detail": "Sign in to withdraw your registration."}

    withdrawing["users"].get.return_value = response(200, me(role="event_organiser"))
    result = client.delete(WITHDRAW_E)
    assert result.status_code == 403
    assert result.json() == {"detail": "Only attendee accounts can register for events."}

    withdrawing["registrations"].post.assert_not_called()


def test_withdrawing_from_an_event_that_isnt_public(client, withdrawing):
    missing = "00000000-0000-4000-8000-000000000000"
    result = client.delete(f"/event-registrations/events/{missing}/registration")

    assert result.status_code == 404
    assert result.json() == {"detail": "Event not found."}
    withdrawing["registrations"].post.assert_not_called()


def test_withdrawing_without_a_place(client, withdrawing):
    """Also A only waiting: the registrations service holds no place for A."""
    withdrawing["registrations"].post.return_value = response(404, {"detail": NOT_REGISTERED})
    withdrawing["registrations"].waiting[EVENT_E] = [A_ROW]

    result = client.delete(WITHDRAW_E)

    assert result.status_code == 404
    assert result.json() == {"detail": NOT_REGISTERED}
    assert withdrawing["registrations"].waiting[EVENT_E] == [A_ROW]
    withdrawing["notifications"].post.assert_not_called()


# --- TC-EVENTREGISTRATIONS-041 --------------------------------------------
@pytest.mark.parametrize(
    "fail",
    [
        lambda post: setattr(post, "return_value", response(500, {"detail": "boom"})),
        lambda post: setattr(post, "side_effect", httpx.ConnectError("down")),
    ],
)
def test_the_registrations_service_fails(client, withdrawing, fail):
    fail(withdrawing["registrations"].post)

    result = client.delete(WITHDRAW_E)

    assert result.status_code == 502
    assert result.json() == {"detail": "Registrations service unavailable"}
    withdrawing["notifications"].post.assert_not_called()
