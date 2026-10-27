"""S-53: a registered Attendee withdraws until the event starts.

TC-EVENTREGISTRATIONS-036..041. The registrations service gives the freed
place to whoever has waited longest in the same step; this composite only
checks who may withdraw and when, then tells the promoted Attendee.
"""

from datetime import datetime, timezone

import httpx
import pytest

from .conftest import ATTENDEE_A, EVENT_E, me, published, response, sgt

ATTENDEE_B = "44444444-4444-4444-8444-444444444444"
PROMOTED_ID = "99999999-9999-4999-8999-999999999999"
WITHDRAW_E = f"/event-registrations/events/{EVENT_E}/registration"
NOT_REGISTERED = "You're not registered for this event."
STARTED = "This event has already started. You can no longer withdraw."
WITHDRAWN = {
    "event_id": EVENT_E, "registered": False, "registered_at": None,
    "waitlisted": False, "joined_at": None, "position": None,
}
A_ROW = {"id": "r-a", "event_id": EVENT_E, "attendee_id": ATTENDEE_A,
         "created_at": "2026-11-05T04:00:00Z"}
B_ROW = {"id": PROMOTED_ID, "event_id": EVENT_E, "attendee_id": ATTENDEE_B,
         "created_at": "2026-11-06T04:00:00Z"}
BEN = {"id": ATTENDEE_B, "name": "Ben Lee", "email": "ben@example.com"}


@pytest.fixture
def withdrawing(services):
    """A holds a place at E; no one is waiting unless a test promotes B."""
    services["registrations"].post.return_value = response(
        200, {"withdrawn": A_ROW, "promoted": None}
    )
    services["users"].post.return_value = response(200, [BEN])
    return services


def _promote_b(services):
    services["registrations"].post.return_value = response(
        200, {"withdrawn": A_ROW, "promoted": B_ROW}
    )


def _event_e_is(services, **changes):
    base = services["events"].get.side_effect

    async def events_get(path, **kwargs):
        if path == f"/internal/events/published/{EVENT_E}":
            return response(200, published(**changes))
        return await base(path, **kwargs)

    services["events"].get.side_effect = events_get


def _sent_rows(services):
    return [
        row
        for call in services["notifications"].post.call_args_list
        for row in call.kwargs["json"]["notifications"]
    ]


# --- TC-EVENTREGISTRATIONS-036 --------------------------------------------
def test_a_registered_attendee_withdraws(client, withdrawing):
    result = client.delete(WITHDRAW_E)

    assert result.status_code == 200
    assert result.json() == WITHDRAWN
    withdrawing["registrations"].post.assert_awaited_once_with(
        "/registrations/withdrawals",
        json={"event_id": EVENT_E, "attendee_id": ATTENDEE_A, "capacity": 2},
    )
    withdrawing["notifications"].post.assert_not_called()


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


# --- TC-EVENTREGISTRATIONS-039 --------------------------------------------
PROMOTION = (
    "A place opened up: you're now registered for Alumni networking evening, "
    "20 Nov 2026, 6:00 pm – 9:00 pm, at Seminar Room 2-1. Name: Ben Lee. "
    "Email: ben@example.com."
)


def test_the_promoted_attendee_is_notified(client, withdrawing):
    _promote_b(withdrawing)

    result = client.delete(WITHDRAW_E)

    assert result.status_code == 200
    assert result.json() == WITHDRAWN
    withdrawing["users"].post.assert_awaited_once_with(
        "/internal/users/profiles", json={"ids": [ATTENDEE_B]}
    )
    assert _sent_rows(withdrawing) == [
        {
            "recipient_id": ATTENDEE_B,
            "event_id": EVENT_E,
            "event_name": "Alumni networking evening",
            "kind": "waiting_list_promotion",
            "message": PROMOTION,
            "deduplication_key": f"waiting_list_promotion:{PROMOTED_ID}",
        }
    ]


def test_a_promotion_without_a_confirmed_venue(client, withdrawing):
    _promote_b(withdrawing)
    withdrawing["bookings"].get.side_effect = None
    withdrawing["bookings"].get.return_value = response(200, [])

    client.delete(WITHDRAW_E)

    (row,) = _sent_rows(withdrawing)
    assert "9:00 pm, venue to be confirmed. Name: Ben Lee." in row["message"]


def test_a_promotion_after_registration_has_closed(client, withdrawing, clock):
    clock.now = sgt("2026-11-16T12:00")
    _promote_b(withdrawing)

    assert client.delete(WITHDRAW_E).status_code == 200
    assert [row["recipient_id"] for row in _sent_rows(withdrawing)] == [ATTENDEE_B]


# --- TC-EVENTREGISTRATIONS-040 --------------------------------------------
def _notifications_fail(services):
    services["notifications"].post.return_value = response(500, {"detail": "boom"})


def _notifications_unreachable(services):
    services["notifications"].post.side_effect = httpx.ConnectError("down")


def _profiles_fail(services):
    services["users"].post.return_value = response(500, {"detail": "boom"})


def _venues_unreadable(services):
    services["bookings"].get.side_effect = None
    services["bookings"].get.return_value = response(500, {"detail": "boom"})


@pytest.mark.parametrize(
    ("failure", "sends"),
    [
        (_notifications_fail, True),
        (_notifications_unreachable, True),
        (_profiles_fail, False),
        (_venues_unreadable, False),
    ],
)
def test_a_failed_notification_keeps_the_withdrawal(client, withdrawing, failure, sends):
    _promote_b(withdrawing)
    failure(withdrawing)

    result = client.delete(WITHDRAW_E)

    assert result.status_code == 200
    assert result.json() == WITHDRAWN
    assert withdrawing["notifications"].post.called is sends


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
