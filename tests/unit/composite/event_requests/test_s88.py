"""S-88 request authorization, Lead scope, and S-84 handoff."""

import httpx
import pytest

from .conftest import (
    COORDINATOR_A, COORDINATOR_B, EVENT_ID, coordinator, event_response,
    fake_response, organiser_me_response,
)

LEAD_A = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
LEAD_B = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
REQUEST = {"reason": "  Cannot cover the November event  "}


def me(user_id=COORDINATOR_A, role="event_coordinator"):
    return organiser_me_response(user_id=user_id, role=role)


def scoped_event(lead_id=LEAD_A):
    return event_response(status_code=200, assigning_lead_id=lead_id,
                          coordinator_assignment_version=2).json()


def request_row(status="pending"):
    return {
        "id": "ffffffff-ffff-4fff-8fff-ffffffffffff", "event_id": EVENT_ID,
        "event_name": "November Forum", "requester_id": COORDINATOR_A,
        "assigning_lead_id": LEAD_A, "assignment_version": 2,
        "reason": "Cannot cover the November event", "status": status,
        "created_at": "2026-10-25T00:00:00Z",
        "actioned_at": "2026-10-25T01:00:00Z" if status == "actioned" else None,
    }


def test_assigned_coordinator_submits_without_transfer(client, users, events):
    users.get.return_value = me()
    events.get.return_value = fake_response(200, scoped_event())
    events.post.return_value = fake_response(201, request_row())
    result = client.post(f"/event-requests/{EVENT_ID}/reassignment-request", json=REQUEST)
    assert result.status_code == 201
    assert result.json()["status"] == "pending"
    assert events.post.await_args.args[0].endswith("/reassignment-request")
    assert events.post.await_args.kwargs["json"] == {"reason": "Cannot cover the November event"}
    assert all(not call.args[0].endswith("/reassignment") for call in events.post.await_args_list)


@pytest.mark.parametrize("reason", ["", "   "])
def test_blank_reason_rejected_before_any_write(client, users, events, reason):
    users.get.return_value = me()
    result = client.post(f"/event-requests/{EVENT_ID}/reassignment-request",
                         json={"reason": reason})
    assert result.status_code == 422
    events.post.assert_not_awaited()


@pytest.mark.parametrize("role,identity,expected", [
    (None, COORDINATOR_A, 401), ("event_organiser", COORDINATOR_A, 403),
    ("event_coordinator_lead", LEAD_A, 403),
    ("event_coordinator", COORDINATOR_B, 404),
])
def test_only_current_coordinator_can_submit(client, users, events, role, identity, expected):
    users.get.return_value = (fake_response(401, {}) if role is None else me(identity, role))
    events.get.return_value = fake_response(404, {})
    result = client.post(f"/event-requests/{EVENT_ID}/reassignment-request", json=REQUEST)
    assert result.status_code == expected
    events.post.assert_not_awaited()


def test_legacy_event_with_no_lead_is_not_routed(client, users, events):
    users.get.return_value = me()
    events.get.return_value = fake_response(200, scoped_event(None))
    result = client.post(f"/event-requests/{EVENT_ID}/reassignment-request", json=REQUEST)
    assert result.status_code == 409
    events.post.assert_not_awaited()


@pytest.mark.parametrize("upstream,expected", [(409, 409), (500, 502)])
def test_duplicate_or_storage_failure_is_safe(client, users, events, upstream, expected):
    users.get.return_value = me()
    events.get.return_value = fake_response(200, scoped_event())
    events.post.return_value = fake_response(upstream, {"detail": "A reassignment request is already pending"})
    result = client.post(f"/event-requests/{EVENT_ID}/reassignment-request", json=REQUEST)
    assert result.status_code == expected


def test_requester_keeps_history_after_transfer(client, users, events):
    users.get.return_value = me()
    events.get.return_value = fake_response(200, [request_row("actioned")])
    result = client.get("/event-requests/reassignment-requests/mine")
    assert result.status_code == 200
    assert result.json()[0]["status"] == "actioned"
    events.get.assert_awaited_once_with("/events/reassignment-requests/mine", cookies={})


def test_lead_list_is_scoped_and_enriched(client, users, events):
    users.get.return_value = me(LEAD_A, "event_coordinator_lead")
    users.post.return_value = fake_response(200, [{"id": COORDINATOR_A, "name": "Alex"}])
    events.get.return_value = fake_response(200, [request_row()])
    result = client.get("/event-requests/reassignment-requests/lead")
    assert result.status_code == 200
    assert result.json()[0]["requester"]["name"] == "Alex"
    events.get.assert_awaited_once_with("/internal/reassignment-requests/lead", cookies={})

    users.get.return_value = me(LEAD_B, "event_coordinator_lead")
    events.get.return_value = fake_response(200, [])
    other = client.get("/event-requests/reassignment-requests/lead")
    assert other.json() == []
    assert events.get.await_args.args[0] == "/internal/reassignment-requests/lead"


@pytest.mark.parametrize("lead_id,expected", [(LEAD_B, 404), (LEAD_A, 200), (None, 409)])
def test_s84_requires_recorded_scope(client, users, events, notifications, lead_id, expected):
    users.get.side_effect = lambda path, **kw: (
        me(LEAD_A, "event_coordinator_lead") if path == "/users/me"
        else fake_response(200, [coordinator(COORDINATOR_A), coordinator(COORDINATOR_B)])
    )
    events.get.return_value = fake_response(200, scoped_event(lead_id))
    events.post.return_value = event_response(
        status_code=200, assigned_coordinator_id=COORDINATOR_B,
        previous_coordinator_id=COORDINATOR_A, assigning_lead_id=LEAD_A,
        coordinator_assignment_version=3, reassignment_created=True,
    )
    notifications.post.return_value = fake_response(201, [])
    result = client.post(f"/event-requests/{EVENT_ID}/reassignment", json={
        "coordinator_id": COORDINATOR_B,
        "expected_coordinator_id": COORDINATOR_A,
        "expected_assignment_version": 2,
    })
    assert result.status_code == expected
    if expected != 200:
        events.post.assert_not_awaited()
    else:
        assert events.post.await_args.kwargs["json"]["expected_assignment_version"] == 2


def test_upstream_read_failure_returns_safe_error(client, users, events):
    users.get.return_value = me()
    events.get.side_effect = httpx.ConnectError("down")
    result = client.get("/event-requests/reassignment-requests/mine")
    assert result.status_code == 502


def test_users_or_profile_failure_returns_no_lead_request_data(client, users, events):
    users.get.side_effect = httpx.ConnectError("users down")
    denied = client.get("/event-requests/reassignment-requests/lead")
    assert denied.status_code == 502
    events.get.assert_not_awaited()

    users.get.side_effect = None
    users.get.return_value = me(LEAD_A, "event_coordinator_lead")
    events.get.return_value = fake_response(200, [request_row()])
    users.post.side_effect = httpx.ConnectError("profiles down")
    failed = client.get("/event-requests/reassignment-requests/lead")
    assert failed.status_code == 502
    assert "requester" not in failed.text
