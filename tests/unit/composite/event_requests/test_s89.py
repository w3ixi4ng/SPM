"""S-89: the Coordinator cancels an event a venue's unavailability left
without an alternative.

TC-EVENTREQUESTS-129..134. The composite checks a booking is still flagged
(venue_bookings), records the cancellation (events), releases every booking
and hold (bookings), then notifies the Organiser with the reason and every
Attendee as in S-69.
"""

import httpx
import pytest

from .conftest import COORDINATOR_A, EVENT_ID, fake_response

URL = f"/event-requests/{EVENT_ID}/coordinator-cancellation"
COOKIE = {"sb_access_token": "coordinator-token"}
ORGANISER_O = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa0"
REASON = "Hall A is closed for repairs and no other hall fits 120 people that evening."
EVENT = {
    "id": EVENT_ID,
    "organiser_id": ORGANISER_O,
    "assigned_coordinator_id": COORDINATOR_A,
    "name": "Alumni networking evening",
    "start_date": "2026-11-20",
    "start_time": "18:00:00",
    "end_date": "2026-11-20",
    "end_time": "21:00:00",
    "status": "planning",
    "coordinator_cancellation_reason": None,
    "coordinator_cancelled_by": None,
    "coordinator_cancelled_at": None,
}
CANCELLED = {
    **EVENT,
    "status": "cancelled",
    "coordinator_cancellation_reason": REASON,
    "coordinator_cancelled_by": COORDINATOR_A,
    "coordinator_cancelled_at": "2026-11-01T06:30:00Z",
}
ATTENDEE_MESSAGE = (
    "Event cancelled: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm. "
    "It will not take place."
)
ORGANISER_MESSAGE = (
    "Your event Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, "
    f"was cancelled by your Event Coordinator: {REASON}"
)
ATTENDEE_A = "a0000000-0000-4000-8000-00000000000a"
ATTENDEE_B = "b0000000-0000-4000-8000-00000000000b"
WAITING_W = "c0000000-0000-4000-8000-00000000000c"
FLAGGED = [
    {"id": "b1", "venue_name": "Hall A", "requires_alternative_arrangements": True},
    {"id": "b2", "venue_name": "Room 2", "requires_alternative_arrangements": False},
]
NOT_RELEASED = (
    "The event is cancelled, but its venue bookings couldn't be released. Cancel again to retry."
)
NO_AFFECTED = (
    "Only an event with a venue booking affected by an unavailable venue can be cancelled here."
)


def _place(attendee_id):
    return {"id": f"r-{attendee_id}", "event_id": EVENT_ID, "attendee_id": attendee_id}


def _registered(registrations, places, waiting):
    async def get(path, **kwargs):
        if path == f"/registrations/events/{EVENT_ID}":
            return fake_response(200, [_place(a) for a in places])
        if path == f"/registrations/waiting-list/events/{EVENT_ID}":
            return fake_response(200, [_place(a) for a in waiting])
        return fake_response(404, {"detail": "Not found"})

    registrations.get.side_effect = get


@pytest.fixture
def flagged(events, venue_bookings, bookings, registrations, notifications):
    """The setting above: B1 flagged, A and B registered, W waiting."""
    order = []

    def record(name, response):
        order.append(name)
        return response

    events.get.side_effect = lambda path, **kw: record("events.get", fake_response(200, EVENT))
    events.post.side_effect = lambda path, **kw: record("events.post", fake_response(200, CANCELLED))
    venue_bookings.get.side_effect = lambda path, **kw: record("venue_bookings.get", fake_response(200, FLAGGED))
    bookings.delete.side_effect = lambda path, **kw: record("bookings.delete", fake_response(200, {"deleted": 2}))
    notifications.post.side_effect = lambda path, **kw: record("notifications.post", fake_response(201, []))
    _registered(registrations, [ATTENDEE_A, ATTENDEE_B], [WAITING_W])
    return order


def _cancel(client, reason=REASON):
    return client.post(URL, json={"reason": reason}, cookies=COOKIE)


def _sent_rows(notifications):
    return [
        row
        for call in notifications.post.call_args_list
        for row in call.kwargs["json"]["notifications"]
    ]


def _nothing_after_the_check(events, bookings, notifications):
    events.post.assert_not_called()
    bookings.delete.assert_not_called()
    notifications.post.assert_not_called()


# --- TC-EVENTREQUESTS-129 --------------------------------------------------
def test_cancelling_a_flagged_event_releases_its_bookings_and_notifies_everyone(
    client, flagged, events, venue_bookings, bookings, notifications,
):
    response = _cancel(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["coordinator_cancellation_reason"] == REASON
    assert body["released_bookings"] == 2
    assert body["notified_attendees"] == 3
    assert body["organiser_notified"] is True

    assert flagged == [
        "events.get", "venue_bookings.get", "events.post", "bookings.delete", "notifications.post",
    ]
    assert events.get.call_args.args == (f"/events/assigned/{EVENT_ID}",)
    assert venue_bookings.get.call_args.args == ("/venue-bookings",)
    assert venue_bookings.get.call_args.kwargs["params"] == {"event_id": EVENT_ID}
    assert events.post.call_args.args == (f"/events/{EVENT_ID}/coordinator-cancellation",)
    assert events.post.call_args.kwargs["json"] == {"reason": REASON}
    for fake in (events.get, venue_bookings.get, events.post, bookings.delete):
        assert fake.call_args.kwargs["cookies"] == COOKIE
    assert bookings.delete.call_args.args == (f"/internal/events/{EVENT_ID}/bookings",)
    assert sorted(row["recipient_id"] for row in _sent_rows(notifications)) == sorted(
        [ORGANISER_O, ATTENDEE_A, ATTENDEE_B, WAITING_W]
    )


# --- TC-EVENTREQUESTS-130 --------------------------------------------------
def test_the_organisers_notification_names_the_event_and_gives_the_reason(client, flagged, notifications):
    assert _cancel(client).status_code == 200

    organiser = [row for row in _sent_rows(notifications) if row["recipient_id"] == ORGANISER_O]
    assert organiser == [{
        "recipient_id": ORGANISER_O,
        "event_id": EVENT_ID,
        "event_name": "Alumni networking evening",
        "kind": "event_cancelled_by_coordinator",
        "message": ORGANISER_MESSAGE,
        "deduplication_key": f"event_cancelled_by_coordinator:{EVENT_ID}:{ORGANISER_O}",
    }]


# --- TC-EVENTREQUESTS-131 --------------------------------------------------
def test_attendees_get_exactly_s69s_notification(client, flagged, notifications):
    assert _cancel(client).status_code == 200

    attendees = [row for row in _sent_rows(notifications) if row["recipient_id"] != ORGANISER_O]
    assert attendees == [
        {
            "recipient_id": attendee_id,
            "event_id": EVENT_ID,
            "event_name": "Alumni networking evening",
            "kind": "event_cancelled",
            "message": ATTENDEE_MESSAGE,
            "deduplication_key": f"event_cancelled:{EVENT_ID}:{attendee_id}",
        }
        for attendee_id in (ATTENDEE_A, ATTENDEE_B, WAITING_W)
    ]
    assert not any(REASON in row["message"] for row in attendees)


# --- TC-EVENTREQUESTS-132 --------------------------------------------------
@pytest.mark.parametrize(
    "rows",
    [
        [{**row, "requires_alternative_arrangements": False} for row in FLAGGED],
        [],
    ],
    ids=["none-flagged-or-resolved", "no-bookings"],
)
def test_an_event_with_no_flagged_booking_cannot_be_cancelled_this_way(
    client, flagged, events, venue_bookings, bookings, notifications, rows,
):
    venue_bookings.get.side_effect = None
    venue_bookings.get.return_value = fake_response(200, rows)

    response = _cancel(client)

    assert response.status_code == 409
    assert response.json()["detail"] == NO_AFFECTED
    _nothing_after_the_check(events, bookings, notifications)


# --- TC-EVENTREQUESTS-133 --------------------------------------------------
def test_a_failed_release_is_retried_by_cancelling_again(
    client, flagged, events, venue_bookings, bookings, notifications,
):
    bookings.delete.side_effect = None
    bookings.delete.return_value = fake_response(500, {"detail": "boom"})

    first = _cancel(client)

    assert first.status_code == 502
    assert first.json()["detail"] == NOT_RELEASED
    notifications.post.assert_not_called()

    events.get.side_effect = None
    events.get.return_value = fake_response(200, CANCELLED)
    venue_bookings.get.reset_mock()
    venue_bookings.get.side_effect = None
    venue_bookings.get.return_value = fake_response(200, [])
    bookings.delete.return_value = fake_response(200, {"deleted": 2})

    second = _cancel(client)

    assert second.status_code == 200, second.text
    assert second.json()["released_bookings"] == 2
    venue_bookings.get.assert_not_called()
    sent = _sent_rows(notifications)
    assert len(sent) == 4

    third = _cancel(client)

    assert third.status_code == 200
    keys = [row["deduplication_key"] for row in _sent_rows(notifications)]
    assert set(keys) == {row["deduplication_key"] for row in sent}


def test_a_failed_notification_is_retried_by_cancelling_again(client, flagged, events, notifications):
    notifications.post.side_effect = None
    notifications.post.return_value = fake_response(500, None)

    response = _cancel(client)

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "The event is cancelled, but the Organiser and Attendees weren't notified. Cancel again to retry."
    )


def test_the_bookings_service_being_down_is_502(client, flagged, bookings, notifications):
    bookings.delete.side_effect = httpx.ConnectError("down")

    response = _cancel(client)

    assert response.status_code == 502
    assert response.json()["detail"] == NOT_RELEASED
    notifications.post.assert_not_called()


# --- TC-EVENTREQUESTS-134 --------------------------------------------------
@pytest.mark.parametrize("status_code", [404, 403])
def test_a_refused_read_passes_through(client, flagged, events, venue_bookings, bookings, notifications, status_code):
    events.get.side_effect = None
    events.get.return_value = fake_response(status_code, {"detail": "From events"})

    response = _cancel(client)

    assert response.status_code == status_code
    assert response.json()["detail"] == "From events"
    venue_bookings.get.assert_not_called()
    _nothing_after_the_check(events, bookings, notifications)


@pytest.mark.parametrize("status_code", [409, 422])
def test_a_refused_cancellation_passes_through(client, flagged, events, bookings, notifications, status_code):
    events.post.side_effect = None
    events.post.return_value = fake_response(status_code, {"detail": "From events"})

    response = _cancel(client)

    assert response.status_code == status_code
    assert response.json()["detail"] == "From events"
    bookings.delete.assert_not_called()
    notifications.post.assert_not_called()


def test_the_venue_bookings_service_being_down_is_502(client, flagged, events, venue_bookings, bookings, notifications):
    venue_bookings.get.side_effect = httpx.ConnectError("down")

    response = _cancel(client)

    assert response.status_code == 502
    assert response.json()["detail"] == "The venue bookings service is unavailable. Nothing was changed."
    _nothing_after_the_check(events, bookings, notifications)


def test_an_event_cancelled_through_s61_is_refused(client, flagged, events, venue_bookings, bookings, notifications):
    events.get.side_effect = None
    events.get.return_value = fake_response(200, {**EVENT, "status": "cancelled"})

    response = _cancel(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "This event can't be cancelled from its current status."
    venue_bookings.get.assert_not_called()
    _nothing_after_the_check(events, bookings, notifications)


def test_a_missing_reason_is_422_before_any_call(client, events):
    response = client.post(URL, json={}, cookies=COOKIE)

    assert response.status_code == 422
    events.get.assert_not_called()
