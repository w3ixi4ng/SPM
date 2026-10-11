"""S-61: the Coordinator's cancellation decision, orchestrated.

TC-EVENTREQUESTS-064..067. The events service records the decision; on
approval the bookings service then removes the event's venue bookings.
"""

import httpx
import pytest

from .conftest import COORDINATOR_A, EVENT_ID, event_response, fake_response

URL = f"/event-requests/{EVENT_ID}/cancellation-decision"
COOKIE = {"sb_access_token": "coordinator-token"}
APPROVED = {
    "status": "cancelled",
    "cancellation_decision": "approved",
    "cancellation_decided_by": COORDINATOR_A,
    "cancellation_decided_at": "2026-10-11T10:00:00Z",
}
NOT_RELEASED = (
    "The event is cancelled, but its venue bookings were not released. "
    "Approve again to release them."
)


def _approve(client):
    return client.post(URL, json={"decision": "approved"}, cookies=COOKIE)


# --- TC-EVENTREQUESTS-064 ----------------------------------------------------
def test_approving_cancels_the_event_then_releases_its_bookings(client, events, bookings):
    calls = []
    cancelled = event_response(200, **APPROVED)
    events.post.side_effect = lambda *a, **k: calls.append("events") or cancelled
    bookings.delete.side_effect = lambda *a, **k: calls.append("bookings") or fake_response(200, {"deleted": 2})

    response = _approve(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["cancellation_decision"] == "approved"
    assert body["released_bookings"] == 2
    assert calls == ["events", "bookings"]
    assert events.post.call_args.args == (f"/events/{EVENT_ID}/cancellation-decision",)
    assert events.post.call_args.kwargs["json"] == {"decision": "approved"}
    assert events.post.call_args.kwargs["cookies"] == COOKIE
    assert bookings.delete.call_args.args == (f"/internal/events/{EVENT_ID}/bookings",)
    assert bookings.delete.call_args.kwargs["cookies"] == COOKIE


# --- TC-EVENTREQUESTS-065 ----------------------------------------------------
def test_declining_touches_only_the_event(client, events, bookings):
    events.post.return_value = event_response(
        200, status="planning", cancellation_decision="declined",
        cancellation_decision_reason="Move the date instead",
    )

    response = client.post(
        URL, json={"decision": "declined", "reason": "Move the date instead"}, cookies=COOKIE
    )

    assert response.status_code == 200
    assert response.json()["status"] == "planning"
    assert "released_bookings" not in response.json()
    assert events.post.call_args.kwargs["json"] == {"decision": "declined", "reason": "Move the date instead"}
    bookings.delete.assert_not_called()


# --- TC-EVENTREQUESTS-066 ----------------------------------------------------
@pytest.mark.parametrize(
    ("status_code", "body"),
    [
        (401, {"detail": "Not authenticated"}),
        (403, {"detail": "Permission denied"}),
        (404, {"detail": "Event not found"}),
        (409, {"detail": "This cancellation request has already been decided."}),
        (422, {"detail": "Please check the details you entered", "errors": {"body": "reason is required"}}),
    ],
)
def test_a_refused_decision_releases_nothing(client, events, bookings, status_code, body):
    events.post.return_value = fake_response(status_code, body)

    response = _approve(client)

    assert response.status_code == status_code
    assert response.json() == body
    bookings.delete.assert_not_called()


# --- TC-EVENTREQUESTS-067 ----------------------------------------------------
@pytest.mark.parametrize(
    "failure",
    [fake_response(500, {"detail": "Booking storage unavailable"}), httpx.ReadTimeout("slow")],
    ids=["bookings-500", "bookings-timeout"],
)
def test_a_failed_release_says_so(client, events, bookings, failure):
    events.post.return_value = event_response(200, **APPROVED)
    if isinstance(failure, Exception):
        bookings.delete.side_effect = failure
    else:
        bookings.delete.return_value = failure

    response = _approve(client)

    assert response.status_code == 502
    assert response.json()["detail"] == NOT_RELEASED


def test_approving_again_finishes_the_release(client, events, bookings):
    # The events service answers a repeat approval with the cancelled event
    # (TC-EVENTS-136), so the composite simply removes the bookings again.
    events.post.return_value = event_response(200, **APPROVED)
    bookings.delete.return_value = fake_response(200, {"deleted": 2})

    response = _approve(client)

    assert response.status_code == 200
    assert response.json()["released_bookings"] == 2


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("refused"), fake_response(500, {"detail": "Event storage unavailable"})],
    ids=["events-unreachable", "events-500"],
)
def test_events_down_changes_nothing(client, events, bookings, failure):
    if isinstance(failure, Exception):
        events.post.side_effect = failure
    else:
        events.post.return_value = failure

    response = _approve(client)

    assert response.status_code == 502
    assert response.json()["detail"] == "The events service is unavailable. Nothing was changed."
    bookings.delete.assert_not_called()
