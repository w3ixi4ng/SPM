"""S-55: a freed place is offered to the next Attendee in line, never given.

TC-EVENTREGISTRATIONS-054..061. The registrations service records the offer
(and counts it as a taken place); this composite invites the Attendee, lets
only them accept or decline it before the event starts, and shows the offer on
their status and dashboard.
"""

import httpx
import pytest

from .conftest import ATTENDEE_A, EVENT_E, me, published, response, sgt

ATTENDEE_B = "44444444-4444-4444-8444-444444444444"
ATTENDEE_C = "55555555-5555-4555-8555-555555555555"
ATTENDEE_D = "66666666-6666-4666-8666-666666666666"
B_ENTRY_ID = "77777777-7777-4777-8777-777777777777"
C_ENTRY_ID = "88888888-8888-4888-8888-888888888888"
B_PLACE_ID = "99999999-9999-4999-8999-999999999999"
WITHDRAW_E = f"/event-registrations/events/{EVENT_E}/registration"
REGISTER_E = WITHDRAW_E
OFFER_E = f"/event-registrations/events/{EVENT_E}/waiting-list/offer"
WAIT_E = f"/event-registrations/events/{EVENT_E}/waiting-list"
MINE = "/event-registrations/me/registrations"
NO_OFFER = "You don't have a place on offer for this event."
STARTED = "This event has already started. The place can no longer be taken."

A_ROW = {"id": "r-a", "event_id": EVENT_E, "attendee_id": ATTENDEE_A,
         "created_at": "2026-11-05T04:00:00Z"}
B_ENTRY = {"id": B_ENTRY_ID, "event_id": EVENT_E, "attendee_id": ATTENDEE_B,
           "created_at": "2026-11-04T04:00:00Z", "offered_at": "2026-11-06T04:00:00Z"}
C_ENTRY = {"id": C_ENTRY_ID, "event_id": EVENT_E, "attendee_id": ATTENDEE_C,
           "created_at": "2026-11-04T05:00:00Z", "offered_at": None}
BEN = {"id": ATTENDEE_B, "name": "Ben Lee", "email": "ben@example.com", "role": "attendee"}
CY = {"id": ATTENDEE_C, "name": "Cy Tan", "email": "cy@example.com", "role": "attendee"}
NOT_HOLDING = {
    "event_id": EVENT_E, "registered": False, "registered_at": None,
    "waitlisted": False, "joined_at": None, "position": None, "offered": False,
}
OFFER = (
    "A place opened up at Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, "
    "at Seminar Room 2-1. It's held for you: accept it on the event page to register."
)


# S-74: withdrawing and declining also notify the Attendee who did it. These
# cases are about the next in line, so they read past that notice; S-74's own
# cases (test_s74.py) check it.
OWN_UPDATES = {"registration_withdrawn", "waiting_list_offer_declined"}


def _sent_rows(services):
    return [
        row
        for call in services["notifications"].post.call_args_list
        for row in call.kwargs["json"]["notifications"]
        if row["kind"] not in OWN_UPDATES
    ]


def _signed_in(services, user):
    services["users"].get.return_value = response(200, user)


def _event_e_is(services, **changes):
    base = services["events"].get.side_effect

    async def events_get(path, **kwargs):
        if path == f"/internal/events/published/{EVENT_E}":
            return response(200, published(**changes))
        return await base(path, **kwargs)

    services["events"].get.side_effect = events_get


def _no_venue(services):
    services["bookings"].get.side_effect = None
    services["bookings"].get.return_value = response(200, [])


# --- TC-EVENTREGISTRATIONS-054 --------------------------------------------
@pytest.fixture
def withdrawing(services):
    """A withdraws from E, and the freed place is offered to B."""
    services["registrations"].post.return_value = response(
        200, {"withdrawn": A_ROW, "offered": B_ENTRY}
    )
    services["users"].post.return_value = response(200, [BEN])
    return services


def test_a_withdrawal_invites_the_next_in_line(client, withdrawing):
    result = client.delete(WITHDRAW_E)

    assert result.status_code == 200
    assert result.json() == NOT_HOLDING
    withdrawing["users"].post.assert_awaited_once_with(
        "/internal/users/profiles", json={"ids": [ATTENDEE_B]}
    )
    assert _sent_rows(withdrawing) == [
        {
            "recipient_id": ATTENDEE_B,
            "event_id": EVENT_E,
            "event_name": "Alumni networking evening",
            "kind": "waiting_list_offer",
            "message": OFFER,
            "deduplication_key": f"waiting_list_offer:{B_ENTRY_ID}",
        }
    ]
    # B is invited, not registered: the composite never takes a place for B.
    posted = [call.args[0] for call in withdrawing["registrations"].post.call_args_list]
    assert posted == ["/registrations/withdrawals"]


def test_an_invitation_without_a_confirmed_venue(client, withdrawing):
    _no_venue(withdrawing)

    client.delete(WITHDRAW_E)

    (row,) = _sent_rows(withdrawing)
    assert "9:00 pm, venue to be confirmed. It's held for you: " in row["message"]


def test_an_invitation_after_registration_has_closed(client, withdrawing, clock):
    clock.now = sgt("2026-11-16T12:00")

    assert client.delete(WITHDRAW_E).status_code == 200
    assert [(row["recipient_id"], row["kind"]) for row in _sent_rows(withdrawing)] == [
        (ATTENDEE_B, "waiting_list_offer")
    ]


# --- TC-EVENTREGISTRATIONS-055 --------------------------------------------
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
def test_a_failed_invitation_keeps_the_withdrawal(client, withdrawing, failure, sends):
    failure(withdrawing)

    result = client.delete(WITHDRAW_E)

    assert result.status_code == 200
    assert result.json() == NOT_HOLDING
    assert bool(_sent_rows(withdrawing)) is sends


# --- TC-EVENTREGISTRATIONS-056 --------------------------------------------
@pytest.fixture
def held(services):
    """E holds one place (A) of 2; B's offer holds the other; C waits."""
    services["registrations"].places[EVENT_E] = [A_ROW]
    services["registrations"].waiting[EVENT_E] = [B_ENTRY, C_ENTRY]
    return services


def test_a_held_offer_counts_as_a_taken_place(client, held):
    assert client.get(f"/event-registrations/events/{EVENT_E}").json()["is_full"] is True
    listed = client.get("/event-registrations/events").json()
    assert next(row for row in listed if row["id"] == EVENT_E)["is_full"] is True


def test_a_newcomer_can_join_the_waiting_list_while_an_offer_is_held(client, held):
    _signed_in(held, {**me(user_id=ATTENDEE_D)})
    d_entry = {"id": "w-d", "event_id": EVENT_E, "attendee_id": ATTENDEE_D,
               "created_at": "2026-11-05T05:00:00Z", "offered_at": None}

    async def join(path, **kwargs):
        held["registrations"].waiting[EVENT_E].append(d_entry)
        return response(201, d_entry)

    held["registrations"].post.side_effect = join

    result = client.post(WAIT_E)

    assert result.status_code == 201
    assert result.json()["position"] == 3


def test_without_an_open_offer_the_place_is_free(client, held):
    held["registrations"].waiting[EVENT_E] = [{**B_ENTRY, "offered_at": None}, C_ENTRY]
    _signed_in(held, {**me(user_id=ATTENDEE_D)})

    result = client.post(WAIT_E)

    assert result.status_code == 409
    assert result.json() == {"detail": "This event still has places. Register instead."}


# --- TC-EVENTREGISTRATIONS-057 --------------------------------------------
def test_the_invited_attendees_status_shows_the_offer(client, held):
    _signed_in(held, BEN)
    b = client.get(REGISTER_E).json()
    assert (b["registered"], b["waitlisted"], b["position"], b["offered"]) == (False, True, 1, True)
    assert b["joined_at"] == "2026-11-04T04:00:00Z"

    _signed_in(held, CY)
    c = client.get(REGISTER_E).json()
    assert (c["waitlisted"], c["position"], c["offered"]) == (True, 2, False)

    _signed_in(held, me())
    a = client.get(REGISTER_E).json()
    assert (a["registered"], a["offered"]) == (True, False)


# --- TC-EVENTREGISTRATIONS-058 --------------------------------------------
@pytest.fixture
def accepting(services):
    _signed_in(services, BEN)
    services["registrations"].post.return_value = response(201, {
        "id": B_PLACE_ID, "event_id": EVENT_E, "attendee_id": ATTENDEE_B,
        "created_at": "2026-11-06T04:00:00+00:00",
    })
    return services


@pytest.mark.parametrize(
    ("now", "changes"),
    [
        ("2026-11-05T12:00", {}),
        ("2026-11-16T12:00", {}),
        ("2026-11-05T12:00", {"registration_closed_at": "2026-11-04T02:00:00+00:00"}),
    ],
)
def test_the_invited_attendee_accepts_and_is_registered(client, accepting, clock, now, changes):
    clock.now = sgt(now)
    _event_e_is(accepting, **changes)

    result = client.post(OFFER_E)

    assert result.status_code == 201
    body = result.json()
    assert (body["registered"], body["registered_at"], body["offered"]) == (
        True, "2026-11-06T04:00:00Z", False
    )
    accepting["registrations"].post.assert_awaited_once_with(
        "/registrations/offers/acceptances",
        json={"event_id": EVENT_E, "attendee_id": ATTENDEE_B},
    )
    assert _sent_rows(accepting) == [
        {
            "recipient_id": ATTENDEE_B,
            "event_id": EVENT_E,
            "event_name": "Alumni networking evening",
            "kind": "registration_confirmation",
            "message": (
                "Registration confirmed: Alumni networking evening, 20 Nov 2026, "
                "6:00 pm – 9:00 pm, at Seminar Room 2-1. Name: Ben Lee. Email: ben@example.com."
            ),
            "deduplication_key": f"registration_confirmation:{B_PLACE_ID}",
        }
    ]


def test_a_failed_confirmation_keeps_the_acceptance(client, accepting):
    _notifications_fail(accepting)

    assert client.post(OFFER_E).status_code == 201


# --- TC-EVENTREGISTRATIONS-059 --------------------------------------------
@pytest.fixture
def declining(services):
    _signed_in(services, BEN)
    services["users"].post.return_value = response(200, [CY])
    return services


def _declines(services, offered):
    services["registrations"].post.return_value = response(
        200, {"declined": B_ENTRY, "offered": offered}
    )


def test_declining_invites_the_next_in_line(client, declining):
    _declines(declining, {**C_ENTRY, "offered_at": "2026-11-07T04:00:00Z"})

    result = client.delete(OFFER_E)

    assert result.status_code == 200
    assert result.json() == NOT_HOLDING
    declining["registrations"].post.assert_awaited_once_with(
        "/registrations/offers/declines",
        json={"event_id": EVENT_E, "attendee_id": ATTENDEE_B, "capacity": 2},
    )
    assert _sent_rows(declining) == [
        {
            "recipient_id": ATTENDEE_C,
            "event_id": EVENT_E,
            "event_name": "Alumni networking evening",
            "kind": "waiting_list_offer",
            "message": OFFER,
            "deduplication_key": f"waiting_list_offer:{C_ENTRY_ID}",
        }
    ]


def test_declining_with_no_one_else_waiting(client, declining):
    _declines(declining, None)

    result = client.delete(OFFER_E)

    assert result.status_code == 200
    assert result.json() == NOT_HOLDING
    assert _sent_rows(declining) == []


def test_a_failed_invitation_keeps_the_decline(client, declining):
    _declines(declining, {**C_ENTRY, "offered_at": "2026-11-07T04:00:00Z"})
    _notifications_fail(declining)

    assert client.delete(OFFER_E).status_code == 200


# --- TC-EVENTREGISTRATIONS-060 --------------------------------------------
ANSWERS = [("post", 201), ("delete", 200)]


def _answer(client, method):
    return getattr(client, method)(OFFER_E)


@pytest.fixture
def answering(services):
    _signed_in(services, BEN)
    services["registrations"].post.side_effect = lambda path, **kwargs: (
        response(201, {"id": B_PLACE_ID, "event_id": EVENT_E, "attendee_id": ATTENDEE_B,
                       "created_at": "2026-11-06T04:00:00Z"})
        if path.endswith("acceptances")
        else response(200, {"declined": B_ENTRY, "offered": None})
    )
    return services


@pytest.mark.parametrize(("method", "ok"), ANSWERS)
def test_answering_needs_a_signed_in_attendee(client, answering, method, ok):
    answering["users"].get.return_value = response(401, {"detail": "Not signed in"})
    result = _answer(client, method)
    assert result.status_code == 401
    assert result.json() == {"detail": "Sign in to respond to this offer."}

    answering["users"].get.return_value = response(200, me(role="event_organiser"))
    result = _answer(client, method)
    assert result.status_code == 403
    assert result.json() == {"detail": "Only attendee accounts can register for events."}

    answering["registrations"].post.assert_not_called()


@pytest.mark.parametrize(("method", "ok"), ANSWERS)
def test_answering_an_offer_for_an_event_that_isnt_public(client, answering, method, ok):
    missing = "00000000-0000-4000-8000-000000000000"
    result = getattr(client, method)(f"/event-registrations/events/{missing}/waiting-list/offer")

    assert result.status_code == 404
    assert result.json() == {"detail": "Event not found."}
    answering["registrations"].post.assert_not_called()


@pytest.mark.parametrize(("method", "ok"), ANSWERS)
def test_answering_is_open_until_the_event_starts(client, answering, clock, method, ok):
    clock.now = sgt("2026-11-20T18:00")
    result = _answer(client, method)
    assert result.status_code == 409
    assert result.json() == {"detail": STARTED}
    answering["registrations"].post.assert_not_called()

    clock.now = sgt("2026-11-20T17:59")
    assert _answer(client, method).status_code == ok


@pytest.mark.parametrize(("method", "ok"), ANSWERS)
def test_answering_without_an_offer(client, answering, method, ok):
    _signed_in(answering, CY)
    answering["registrations"].post.side_effect = None
    answering["registrations"].post.return_value = response(404, {"detail": NO_OFFER})

    result = _answer(client, method)

    assert result.status_code == 404
    assert result.json() == {"detail": NO_OFFER}
    answering["notifications"].post.assert_not_called()


@pytest.mark.parametrize(("method", "ok"), ANSWERS)
@pytest.mark.parametrize(
    "fail",
    [
        lambda post: setattr(post, "return_value", response(500, {"detail": "boom"})),
        lambda post: setattr(post, "side_effect", httpx.ConnectError("down")),
    ],
)
def test_answering_when_the_registrations_service_fails(client, answering, method, ok, fail):
    answering["registrations"].post.side_effect = None
    fail(answering["registrations"].post)

    result = _answer(client, method)

    assert result.status_code == 502
    assert result.json() == {"detail": "Registrations service unavailable"}
    answering["notifications"].post.assert_not_called()


# --- TC-EVENTREGISTRATIONS-061 --------------------------------------------
@pytest.mark.parametrize(("offered_at", "status"), [
    ("2026-11-06T04:00:00Z", "offered"),
    (None, "waitlisted"),
])
def test_the_dashboard_shows_an_offer(client, services, offered_at, status):
    _signed_in(services, BEN)
    services["registrations"].waiting[EVENT_E] = [{**B_ENTRY, "offered_at": offered_at}]

    result = client.get(MINE)

    assert result.status_code == 200
    (row,) = result.json()
    assert row["event_id"] == EVENT_E
    assert row["status"] == status
    assert (row["position"], row["joined_at"], row["registered_at"]) == (
        1, "2026-11-04T04:00:00Z", None
    )
    assert row["venue"] is None
    assert (row["start_date"], row["start_time"]) == ("2026-11-20", "18:00:00")


def test_an_offer_is_listed_only_while_the_event_is_confirmed(client, services):
    _signed_in(services, BEN)
    services["registrations"].waiting[EVENT_E] = [B_ENTRY]
    base = services["events"].get.side_effect

    async def events_get(path, **kwargs):
        if path == f"/internal/events/attendee-view/{EVENT_E}":
            return response(200, {**published(), "status": "planning"})
        return await base(path, **kwargs)

    services["events"].get.side_effect = events_get

    assert client.get(MINE).json() == []
