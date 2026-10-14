import httpx
import pytest

from .conftest import (
    COORDINATOR_A,
    COORDINATOR_B,
    EVENT_ID,
    ORGANISER_ID,
    coordinator,
    event_response,
    fake_response,
    organiser_me_response,
)


LEAD_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def lead_me_response():
    return organiser_me_response(user_id=LEAD_ID, role="event_coordinator_lead")


def request_body(target=COORDINATOR_B, expected=COORDINATOR_A, version=0):
    return {
        "coordinator_id": target,
        "expected_coordinator_id": expected,
        "expected_assignment_version": version,
    }


def reassigned_event(created=True):
    return event_response(
        status_code=200,
        name="Autumn Forum",
        assigned_coordinator_id=COORDINATOR_B,
        previous_coordinator_id=COORDINATOR_A,
        coordinator_assignment_version=1,
        reassignment_created=created,
    )


@pytest.mark.parametrize("action", ["list", "reassign"])
@pytest.mark.parametrize("role,expected", [("event_organiser", 403), (None, 401)])
def test_only_a_lead_can_list_or_reassign_active_assignments(
    client, users, events, notifications, action, role, expected
):
    users.get.return_value = (
        fake_response(401, {"detail": "Not authenticated"})
        if role is None
        else organiser_me_response(role=role)
    )

    response = (
        client.get("/event-requests/assigned-active")
        if action == "list"
        else client.post(
            f"/event-requests/{EVENT_ID}/reassignment", json=request_body()
        )
    )

    assert response.status_code == expected
    events.get.assert_not_awaited()
    events.post.assert_not_awaited()
    notifications.post.assert_not_awaited()


def test_lead_lists_active_assignments_with_profiles(client, users, events):
    users.get.return_value = lead_me_response()
    events.get.return_value = fake_response(
        200,
        [
            event_response(
                status_code=200,
                name="Autumn Forum",
                assigned_coordinator_id=COORDINATOR_A,
                coordinator_assignment_version=0,
            ).json()
        ],
    )
    users.post.return_value = fake_response(
        200,
        [
            {"id": ORGANISER_ID, "name": "Ada Organiser", "email": "ada@example.com"},
            {"id": COORDINATOR_A, "name": "Alex Coordinator", "email": "alex@example.com"},
        ],
    )

    response = client.get("/event-requests/assigned-active")

    assert response.status_code == 200
    item = response.json()[0]
    assert item["organiser"]["name"] == "Ada Organiser"
    assert item["coordinator"]["name"] == "Alex Coordinator"
    assert item["coordinator_assignment_version"] == 0
    events.get.assert_awaited_once_with("/internal/events/assigned-active")
    users.post.assert_awaited_once_with(
        "/internal/users/profiles", json={"ids": [ORGANISER_ID, COORDINATOR_A]}
    )


def test_lead_reassigns_without_schedule_filtering(
    client, users, events, notifications
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        if path == "/internal/users/coordinators":
            return fake_response(
                200,
                [
                    coordinator(COORDINATOR_A, "Alex Coordinator"),
                    coordinator(COORDINATOR_B, "Blair Coordinator"),
                ],
            )
        raise AssertionError(path)

    users.get.side_effect = users_get
    events.post.return_value = reassigned_event()
    notifications.post.return_value = fake_response(201, [{"id": 1}, {"id": 2}, {"id": 3}])

    response = client.post(
        f"/event-requests/{EVENT_ID}/reassignment", json=request_body()
    )

    assert response.status_code == 200
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_B
    assert events.post.await_args.args[0] == f"/internal/events/{EVENT_ID}/reassignment"
    assert events.post.await_args.kwargs["json"] == request_body()
    assert all(call.args[0] != "/events/coordinator-load" for call in events.post.await_args_list)


@pytest.mark.parametrize(
    "body,pool",
    [
        (request_body(target=COORDINATOR_A), [coordinator(COORDINATOR_A)]),
        (request_body(target=COORDINATOR_B), [coordinator(COORDINATOR_A)]),
    ],
)
def test_reassignment_rejects_invalid_or_same_target(
    client, users, events, notifications, body, pool
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        return fake_response(200, pool)

    users.get.side_effect = users_get

    response = client.post(
        f"/event-requests/{EVENT_ID}/reassignment", json=body
    )

    assert response.status_code == 422
    events.post.assert_not_awaited()
    notifications.post.assert_not_awaited()


def test_reassignment_creates_three_persistent_notifications(
    client, users, events, notifications
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        return fake_response(
            200,
            [
                coordinator(COORDINATOR_A, "Alex Coordinator"),
                coordinator(COORDINATOR_B, "Blair Coordinator"),
            ],
        )

    users.get.side_effect = users_get
    events.post.return_value = reassigned_event()
    notifications.post.return_value = fake_response(201, [{"id": 1}, {"id": 2}, {"id": 3}])

    response = client.post(
        f"/event-requests/{EVENT_ID}/reassignment", json=request_body()
    )

    assert response.status_code == 200
    rows = notifications.post.await_args.kwargs["json"]["notifications"]
    assert {row["recipient_id"] for row in rows} == {
        COORDINATOR_A,
        COORDINATOR_B,
        ORGANISER_ID,
    }
    assert all(row["kind"] == "event_reassignment" for row in rows)
    assert {row["deduplication_key"] for row in rows} == {
        f"event_reassignment:{EVENT_ID}:1:{COORDINATOR_A}",
        f"event_reassignment:{EVENT_ID}:1:{COORDINATOR_B}",
        f"event_reassignment:{EVENT_ID}:1:{ORGANISER_ID}",
    }


def test_reassignment_retry_repairs_notifications_idempotently(
    client, users, events, notifications
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        return fake_response(
            200,
            [
                coordinator(COORDINATOR_A, "Alex Coordinator"),
                coordinator(COORDINATOR_B, "Blair Coordinator"),
            ],
        )

    users.get.side_effect = users_get
    events.post.side_effect = [reassigned_event(True), reassigned_event(False)]
    notifications.post.side_effect = [
        fake_response(502, {"detail": "down"}),
        fake_response(201, [{"id": 1}, {"id": 2}, {"id": 3}]),
    ]

    first = client.post(
        f"/event-requests/{EVENT_ID}/reassignment", json=request_body()
    )
    second = client.post(
        f"/event-requests/{EVENT_ID}/reassignment", json=request_body()
    )

    assert first.status_code == 502
    assert second.status_code == 200
    first_keys = {
        row["deduplication_key"]
        for row in notifications.post.await_args_list[0].kwargs["json"]["notifications"]
    }
    second_keys = {
        row["deduplication_key"]
        for row in notifications.post.await_args_list[1].kwargs["json"]["notifications"]
    }
    assert first_keys == second_keys


@pytest.mark.parametrize("downstream_status", [404, 409])
def test_reassignment_preserves_atomic_conflicts(
    client, users, events, notifications, downstream_status
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        return fake_response(
            200,
            [coordinator(COORDINATOR_A), coordinator(COORDINATOR_B)],
        )

    users.get.side_effect = users_get
    events.post.return_value = fake_response(
        downstream_status, {"detail": "Reassignment unavailable"}
    )

    response = client.post(
        f"/event-requests/{EVENT_ID}/reassignment", json=request_body()
    )

    assert response.status_code == downstream_status
    notifications.post.assert_not_awaited()


def test_reassignment_dependency_failures_are_safe(
    client, users, events, notifications
):
    users.get.return_value = lead_me_response()
    events.get.side_effect = httpx.ConnectError("events down")

    listed = client.get("/event-requests/assigned-active")

    assert listed.status_code == 502
    assert listed.json() == {"detail": "Events service unavailable"}
