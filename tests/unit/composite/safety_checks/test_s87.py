"""Confirmed S-87 Coordinator return-and-resubmit orchestration tests."""

import httpx
import pytest


EVENT_ID = "33333333-3333-4333-8333-333333333333"
COORDINATOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_COORDINATOR_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OFFICER_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def response(status, body):
    return httpx.Response(status, json=body)


def profile(user_id=COORDINATOR_ID, role="event_coordinator"):
    return {
        "id": user_id,
        "name": "Casey Coordinator",
        "email": "casey@example.com",
        "role": role,
    }


def returned_event(**changes):
    review = {
        "review_number": 1,
        "decision": "changes_requested",
        "reason": "Move speakers away from the emergency exit",
        "safety_officer_id": OFFICER_ID,
        "decided_at": "2026-10-10T09:00:00Z",
    }
    event = {
        "id": EVENT_ID,
        "assigned_coordinator_id": COORDINATOR_ID,
        "status": "planning",
        "name": "Safety Forum",
        "safety_decision": "changes_requested",
        "safety_decision_reason": review["reason"],
        "safety_officer_id": OFFICER_ID,
        "safety_decided_at": review["decided_at"],
        "safety_review_history": [review],
    }
    event.update(changes)
    return event


@pytest.mark.parametrize(
    "me_response,expected",
    [
        (response(401, {"detail": "Not authenticated"}), 401),
        (response(200, profile(role="event_organiser")), 403),
        (response(200, profile(role="safety_officer")), 403),
    ],
)
def test_only_event_coordinators_can_open_or_resubmit_returned_work(
    client, services, me_response, expected
):
    services["users"].get.return_value = me_response

    detail = client.get(f"/safety-checks/coordinator/events/{EVENT_ID}")
    submit = client.post(f"/safety-checks/coordinator/events/{EVENT_ID}/resubmit")

    assert detail.status_code == expected
    assert submit.status_code == expected
    services["events"].get.assert_not_awaited()
    services["events"].post.assert_not_awaited()


def test_returned_detail_exposes_feedback_with_officer_identity(client, services):
    services["users"].get.return_value = response(200, profile())
    services["events"].get.return_value = response(200, returned_event())
    services["users"].post.return_value = response(
        200,
        [{"id": OFFICER_ID, "name": "Sam Safety", "email": "sam@example.com"}],
    )

    result = client.get(f"/safety-checks/coordinator/events/{EVENT_ID}")

    assert result.status_code == 200
    body = result.json()
    assert body["event"]["status"] == "planning"
    assert body["current_return"]["reason"].startswith("Move speakers")
    assert body["current_return"]["safety_officer"]["name"] == "Sam Safety"
    assert body["safety_review_history"][0]["decision"] == "changes_requested"
    services["events"].get.assert_awaited_once_with(
        f"/internal/events/{EVENT_ID}/safety-return",
        params={"coordinator_id": COORDINATOR_ID},
    )


def test_other_coordinator_cannot_manage_event_not_assigned_to_them(client, services):
    services["users"].get.return_value = response(
        200, profile(OTHER_COORDINATOR_ID)
    )
    services["events"].get.return_value = response(404, {"detail": "Event not found"})
    services["events"].post.return_value = response(404, {"detail": "Event not found"})

    assert client.get(f"/safety-checks/coordinator/events/{EVENT_ID}").status_code == 404
    assert client.post(f"/safety-checks/coordinator/events/{EVENT_ID}/resubmit").status_code == 404


def arranged(services):
    """S-17: resubmission first checks every arrangement. One confirmed,
    unflagged booking and no equipment requirement is a ready event."""
    services["events"].get.return_value = response(200, returned_event())

    async def bookings_get(path, params=None):
        if path == "/bookings":
            return response(200, [{
                "id": "b1b1b1b1-0000-4000-8000-000000000001",
                "event_id": EVENT_ID,
                "venue_id": "f1f1f1f1-0000-4000-8000-000000000001",
                "venue_name": "Hall A",
                "status": "confirmed",
                "booking_date": "2026-11-20",
                "start_time": "09:00:00",
                "end_time": "17:00:00",
            }])
        return response(200, [])

    services["bookings"].get.side_effect = bookings_get
    services["venues"].get.return_value = response(200, {"id": "f1", "name": "Hall A"})
    services["equipment"].get.return_value = response(200, [])


def test_resubmit_forwards_verified_current_coordinator_and_returns_pending(
    client, services
):
    services["users"].get.return_value = response(200, profile())
    arranged(services)
    services["events"].post.return_value = response(
        200,
        returned_event(
            status="pending_safety_check",
            safety_decision=None,
            safety_decision_reason=None,
            safety_officer_id=None,
            safety_decided_at=None,
        ),
    )

    result = client.post(f"/safety-checks/coordinator/events/{EVENT_ID}/resubmit")

    assert result.status_code == 200
    assert result.json()["status"] == "pending_safety_check"
    assert result.json()["safety_review_history"][0]["decision"] == "changes_requested"
    services["events"].post.assert_awaited_once_with(
        f"/internal/events/{EVENT_ID}/safety-resubmit",
        json={"coordinator_id": COORDINATOR_ID},
    )


@pytest.mark.parametrize("status", [404, 409])
def test_return_and_resubmit_preserve_identified_atomic_errors(
    client, services, status
):
    services["users"].get.return_value = response(200, profile())
    services["events"].get.return_value = response(status, {"detail": "identified"})
    services["events"].post.return_value = response(status, {"detail": "identified"})

    detail = client.get(f"/safety-checks/coordinator/events/{EVENT_ID}")
    submit = client.post(f"/safety-checks/coordinator/events/{EVENT_ID}/resubmit")

    assert detail.status_code == status
    assert submit.status_code == status


def test_upstream_failure_is_controlled_and_does_not_retry_a_write(client, services):
    services["users"].get.return_value = response(200, profile())
    arranged(services)
    services["events"].post.side_effect = httpx.ConnectError("down")

    result = client.post(f"/safety-checks/coordinator/events/{EVENT_ID}/resubmit")

    assert result.status_code == 502
    services["events"].post.assert_awaited_once()
