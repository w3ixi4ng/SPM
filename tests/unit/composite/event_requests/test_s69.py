"""S-69: an approved cancellation notifies the event's Attendees.

TC-EVENTREQUESTS-124..128. After the events service records the approval and
the bookings are released (S-61), everyone holding a place, waiting, or
holding an offered place gets one `event_cancelled` notification, sent in
batches the notifications service accepts and deduplicated per Attendee.
"""

import httpx
import pytest

from .conftest import COORDINATOR_A, EVENT_ID, event_response, fake_response

URL = f"/event-requests/{EVENT_ID}/cancellation-decision"
COOKIE = {"sb_access_token": "coordinator-token"}
APPROVED = {
    "status": "cancelled",
    "name": "Alumni networking evening",
    "start_date": "2026-11-20",
    "start_time": "18:00:00",
    "end_date": "2026-11-20",
    "end_time": "21:00:00",
    "cancellation_decision": "approved",
    "cancellation_decided_by": COORDINATOR_A,
    "cancellation_decided_at": "2026-10-11T10:00:00Z",
}
MESSAGE = (
    "Event cancelled: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm. "
    "It will not take place."
)
NOT_NOTIFIED = (
    "The event is cancelled, but its attendees were not notified. "
    "Approve again to notify them."
)
ATTENDEE_A = "a0000000-0000-4000-8000-00000000000a"
ATTENDEE_B = "b0000000-0000-4000-8000-00000000000b"
WAITING_W = "c0000000-0000-4000-8000-00000000000c"
OFFERED_O = "d0000000-0000-4000-8000-00000000000d"


def _place(attendee_id):
    return {"id": f"r-{attendee_id}", "event_id": EVENT_ID, "attendee_id": attendee_id,
            "created_at": "2026-11-05T04:00:00Z"}


def _waiting(attendee_id, offered_at=None):
    return {**_place(attendee_id), "offered_at": offered_at}


def _registered(registrations, places, waiting):
    async def get(path, **kwargs):
        if path == f"/registrations/events/{EVENT_ID}":
            return fake_response(200, places)
        if path == f"/registrations/waiting-list/events/{EVENT_ID}":
            return fake_response(200, waiting)
        return fake_response(404, {"detail": "Not found"})

    registrations.get.side_effect = get


@pytest.fixture
def approved(events, bookings, notifications):
    events.post.return_value = event_response(200, **APPROVED)
    bookings.delete.return_value = fake_response(200, {"deleted": 0})
    notifications.post.return_value = fake_response(201, [])


def _approve(client):
    return client.post(URL, json={"decision": "approved"}, cookies=COOKIE)


def _sent_rows(notifications):
    return [
        row
        for call in notifications.post.call_args_list
        for row in call.kwargs["json"]["notifications"]
    ]


def _row(attendee_id, message=MESSAGE):
    return {
        "recipient_id": attendee_id,
        "event_id": EVENT_ID,
        "event_name": "Alumni networking evening",
        "kind": "event_cancelled",
        "message": message,
        "deduplication_key": f"event_cancelled:{EVENT_ID}:{attendee_id}",
    }


# --- TC-EVENTREQUESTS-124 ----------------------------------------------------
def test_approving_a_cancellation_notifies_everyone_registered_or_waiting(
    client, approved, bookings, registrations, notifications
):
    calls = []
    released = bookings.delete.return_value
    bookings.delete.side_effect = lambda *a, **k: calls.append("bookings") or released
    sent = notifications.post.return_value
    notifications.post.side_effect = lambda *a, **k: calls.append("notifications") or sent
    _registered(
        registrations,
        [_place(ATTENDEE_A), _place(ATTENDEE_B)],
        [_waiting(WAITING_W), _waiting(OFFERED_O, offered_at="2026-11-06T04:00:00Z")],
    )

    response = _approve(client)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert response.json()["notified_attendees"] == 4
    assert notifications.post.call_count == 1
    assert notifications.post.call_args.args == ("/internal/notifications",)
    assert _sent_rows(notifications) == [
        _row(ATTENDEE_A), _row(ATTENDEE_B), _row(WAITING_W), _row(OFFERED_O),
    ]
    assert calls == ["bookings", "notifications"]


# --- TC-EVENTREQUESTS-125 ----------------------------------------------------
def test_the_message_names_an_event_ending_on_a_later_day_in_full(
    client, events, approved, registrations, notifications
):
    events.post.return_value = event_response(
        200, **{**APPROVED, "end_date": "2026-11-21", "end_time": "00:30:00"}
    )
    _registered(registrations, [_place(ATTENDEE_A)], [])

    response = _approve(client)

    assert response.status_code == 200, response.text
    assert _sent_rows(notifications) == [_row(
        ATTENDEE_A,
        "Event cancelled: Alumni networking evening, 20 Nov 2026, 6:00 pm – "
        "21 Nov 2026, 12:30 am. It will not take place.",
    )]


# --- TC-EVENTREQUESTS-126 ----------------------------------------------------
def test_large_events_are_notified_in_batches_of_20(
    client, approved, registrations, notifications
):
    held = [f"{n:08x}-0000-4000-8000-000000000000" for n in range(23)]
    waiting = [f"{n:08x}-1111-4111-8111-111111111111" for n in range(2)]
    _registered(registrations, [_place(i) for i in held], [_waiting(i) for i in waiting])

    response = _approve(client)

    assert response.status_code == 200, response.text
    assert response.json()["notified_attendees"] == 25
    sizes = [len(call.kwargs["json"]["notifications"]) for call in notifications.post.call_args_list]
    assert sizes == [20, 5]
    recipients = [row["recipient_id"] for row in _sent_rows(notifications)]
    assert sorted(recipients) == sorted(held + waiting)


# --- TC-EVENTREQUESTS-127 ----------------------------------------------------
def test_no_one_is_notified_unless_a_cancellation_is_confirmed(
    client, events, approved, registrations, notifications
):
    # (a) Declined: the event stays as it was.
    events.post.return_value = event_response(
        200, status="confirmed", cancellation_decision="declined",
        cancellation_decision_reason="Go ahead as planned",
    )
    declined = client.post(
        URL, json={"decision": "declined", "reason": "Go ahead as planned"}, cookies=COOKIE
    )
    assert declined.status_code == 200
    registrations.get.assert_not_called()
    notifications.post.assert_not_called()

    # (b) Approved, but no one registered or waiting.
    events.post.return_value = event_response(200, **APPROVED)
    nobody = _approve(client)
    assert nobody.status_code == 200, nobody.text
    assert nobody.json()["notified_attendees"] == 0
    notifications.post.assert_not_called()

    # (c) The events service refuses the decision.
    registrations.get.reset_mock()
    events.post.return_value = fake_response(403, {"detail": "Permission denied"})
    refused = _approve(client)
    assert refused.status_code == 403
    registrations.get.assert_not_called()
    notifications.post.assert_not_called()


# --- TC-EVENTREQUESTS-128 ----------------------------------------------------
def test_a_failed_notification_is_retried_by_approving_again(
    client, approved, registrations, notifications
):
    everyone = (
        [_place(ATTENDEE_A), _place(ATTENDEE_B)],
        [_waiting(WAITING_W), _waiting(OFFERED_O, offered_at="2026-11-06T04:00:00Z")],
    )

    # (a) The registrations service is down.
    registrations.get.side_effect = httpx.ConnectError("registrations down")
    down = _approve(client)
    assert down.status_code == 502
    assert down.json()["detail"] == NOT_NOTIFIED
    notifications.post.assert_not_called()

    # (b) The notifications service fails.
    _registered(registrations, *everyone)
    notifications.post.return_value = fake_response(500, {"detail": "boom"})
    failed = _approve(client)
    assert failed.status_code == 502
    assert failed.json()["detail"] == NOT_NOTIFIED

    # (c) Approving again -- a no-op on the event -- sends them.
    notifications.post.reset_mock()
    notifications.post.return_value = fake_response(201, [])
    retried = _approve(client)
    assert retried.status_code == 200, retried.text
    assert retried.json()["notified_attendees"] == 4
    assert [row["deduplication_key"] for row in _sent_rows(notifications)] == [
        f"event_cancelled:{EVENT_ID}:{attendee}"
        for attendee in (ATTENDEE_A, ATTENDEE_B, WAITING_W, OFFERED_O)
    ]
