"""S-74: an Attendee is told about each change to their own registration.

TC-EVENTREGISTRATIONS-066..069. Registering, an offer and accepting it were
already notified (S-49, S-55); S-74 adds joining the waiting list,
withdrawing, and declining an offered place. Each notice goes to the Attendee
whose status changed, in the same request, keyed by the row that changed, and
is best effort: the change stands if its notice can't be stored.
"""

import logging

import httpx
import pytest

from .conftest import ATTENDEE_A, EVENT_E, response

ATTENDEE_B = "44444444-4444-4444-8444-444444444444"
REGISTRATION_E = f"/event-registrations/events/{EVENT_E}/registration"
WAIT_E = f"/event-registrations/events/{EVENT_E}/waiting-list"
OFFER_E = f"/event-registrations/events/{EVENT_E}/waiting-list/offer"
WHEN = "Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm"

A_PLACE = {"id": "r1", "event_id": EVENT_E, "attendee_id": ATTENDEE_A,
           "created_at": "2026-11-05T04:00:00Z"}
A_ENTRY = {"id": "w1", "event_id": EVENT_E, "attendee_id": ATTENDEE_A,
           "created_at": "2026-11-06T04:00:00Z", "offered_at": None}
B_ENTRY = {"id": "w0", "event_id": EVENT_E, "attendee_id": ATTENDEE_B,
           "created_at": "2026-11-05T05:00:00Z", "offered_at": None}
B_OFFERED = {**B_ENTRY, "offered_at": "2026-11-06T05:00:00Z"}


def _rows(services):
    return [
        row
        for call in services["notifications"].post.call_args_list
        for row in call.kwargs["json"]["notifications"]
    ]


def _notice(kind, message, row_id):
    return {
        "recipient_id": ATTENDEE_A,
        "event_id": EVENT_E,
        "event_name": "Alumni networking evening",
        "kind": kind,
        "message": message,
        "deduplication_key": f"{kind}:{row_id}",
    }


def _full_with_line(services, *line):
    """E (two places) is full, and its waiting list reads `line` once A joins."""
    services["registrations"].places[EVENT_E] = [
        {**A_PLACE, "id": f"p{n}", "attendee_id": f"other-{n}"} for n in range(2)
    ]
    services["registrations"].waiting[EVENT_E] = list(line)
    services["registrations"].post.return_value = response(201, A_ENTRY)


def _withdraws(services, offered=None):
    services["registrations"].post.return_value = response(
        200, {"withdrawn": A_PLACE, "offered": offered}
    )
    services["users"].post.return_value = response(
        200, [{"id": ATTENDEE_B, "name": "Ben Lim", "email": "ben@example.com"}]
    )


def _declines(services):
    services["registrations"].post.return_value = response(
        200, {"declined": {**A_ENTRY, "offered_at": "2026-11-06T05:00:00Z"}, "offered": None}
    )


# --- TC-EVENTREGISTRATIONS-066 --------------------------------------------
@pytest.mark.parametrize(
    "line, position, says",
    [
        ((B_ENTRY, A_ENTRY), 2, "You're 2nd in line."),
        ((A_ENTRY,), 1, "You're next in line."),
    ],
)
def test_joining_the_waiting_list_is_confirmed_with_the_place_in_line(
    client, services, line, position, says
):
    _full_with_line(services, *line)

    result = client.post(WAIT_E)

    assert result.status_code == 201, result.text
    assert result.json()["position"] == position
    assert _rows(services) == [_notice(
        "waiting_list_joined", f"You're on the waiting list for {WHEN}. {says}", "w1",
    )]


# --- TC-EVENTREGISTRATIONS-067 --------------------------------------------
def test_withdrawing_is_confirmed_to_the_attendee_who_withdrew(client, services):
    _withdraws(services, offered=B_OFFERED)

    result = client.delete(REGISTRATION_E)

    assert result.status_code == 200, result.text
    assert result.json()["registered"] is False
    sent = _rows(services)
    assert [row for row in sent if row["recipient_id"] == ATTENDEE_A] == [_notice(
        "registration_withdrawn",
        f"You've withdrawn from {WHEN}. Your place has been released.",
        "r1",
    )]
    # S-55 is unchanged: the next in line is still invited.
    assert [(row["recipient_id"], row["kind"]) for row in sent if row["recipient_id"] != ATTENDEE_A] == [
        (ATTENDEE_B, "waiting_list_offer"),
    ]


# --- TC-EVENTREGISTRATIONS-068 --------------------------------------------
def test_declining_an_offer_is_confirmed_to_the_attendee_who_declined(client, services):
    _declines(services)

    result = client.delete(OFFER_E)

    assert result.status_code == 200, result.text
    assert _rows(services) == [_notice(
        "waiting_list_offer_declined",
        f"You've declined the place at {WHEN}, and left the waiting list.",
        "w1",
    )]


# --- TC-EVENTREGISTRATIONS-069 --------------------------------------------
def test_a_refused_change_sends_nothing_and_a_failed_notice_does_not_undo_the_change(
    client, services, caplog
):
    # (a) Withdrawing a place A doesn't hold.
    services["registrations"].post.return_value = response(404, {"detail": "not registered"})
    refused = client.delete(REGISTRATION_E)
    assert refused.status_code == 404
    assert refused.json()["detail"] == "You're not registered for this event."

    # (b) Joining a waiting list A is already on.
    _full_with_line(services, A_ENTRY)
    services["registrations"].post.return_value = response(
        409, {"detail": "You're already on the waiting list for this event."}
    )
    again = client.post(WAIT_E)
    assert again.status_code == 409
    services["notifications"].post.assert_not_called()

    # (c) Each change succeeds although its notice can't be stored.
    changes = [
        (lambda: _full_with_line(services, A_ENTRY), lambda: client.post(WAIT_E), 201),
        (lambda: _withdraws(services), lambda: client.delete(REGISTRATION_E), 200),
        (lambda: _declines(services), lambda: client.delete(OFFER_E), 200),
    ]
    for failure in (response(500, {"detail": "boom"}), httpx.ConnectError("notifications down")):
        for arrange, act, status in changes:
            services["notifications"].post.reset_mock()
            if isinstance(failure, Exception):
                services["notifications"].post.side_effect = failure
            else:
                services["notifications"].post.side_effect = None
                services["notifications"].post.return_value = failure
            arrange()
            caplog.clear()
            with caplog.at_level(logging.ERROR):
                result = act()
            assert result.status_code == status, result.text
            assert services["notifications"].post.called
            assert caplog.records, "the failed notice is logged"
