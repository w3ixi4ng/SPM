import httpx
import pytest

from .conftest import (
    COORDINATOR_A,
    COORDINATOR_B,
    EVENT_ID,
    ORGANISER_ID,
    SUBMITTED,
    coordinator,
    event_response,
    fake_response,
    organiser_me_response,
)


LEAD_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def lead_me_response():
    return organiser_me_response(user_id=LEAD_ID, role="event_coordinator_lead")


def test_new_submission_enters_the_unassigned_queue(client, users, events):
    users.get.return_value = organiser_me_response()
    events.post.return_value = event_response(assigned_coordinator_id=None)

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 201
    sent = events.post.call_args.kwargs["json"]
    assert sent["organiser_id"] == ORGANISER_ID
    assert sent["assigned_coordinator_id"] is None
    assert users.get.await_args_list[0].args[0] == "/users/me"
    assert all(call.args[0] != "/internal/users/coordinators" for call in users.get.await_args_list)


def test_first_draft_submission_is_unassigned(client, users, events):
    users.get.return_value = organiser_me_response()
    events.get.return_value = event_response(status_code=200, status="draft", assigned_coordinator_id=None)
    events.post.return_value = event_response(status_code=200, assigned_coordinator_id=None)

    response = client.post(f"/event-requests/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 200
    assert events.post.call_args.kwargs["json"]["assigned_coordinator_id"] is None


def test_returned_resubmission_keeps_its_coordinator(client, users, events):
    users.get.return_value = organiser_me_response()
    events.get.return_value = event_response(
        status_code=200, status="returned", assigned_coordinator_id=COORDINATOR_A
    )
    events.post.return_value = event_response(status_code=200, assigned_coordinator_id=COORDINATOR_A)

    response = client.post(
        f"/event-requests/{EVENT_ID}/submit",
        json={**SUBMITTED, "start_time": "19:00", "end_time": "22:00"},
    )

    assert response.status_code == 200
    assert events.post.call_args.kwargs["json"]["assigned_coordinator_id"] == COORDINATOR_A
    assert all(call.args[0] != "/events/coordinator-load" for call in events.post.await_args_list)


@pytest.mark.parametrize(
    "role",
    ["event_coordinator", "event_organiser", "venue_staff", "technical_support", "attendee", "unknown"],
)
def test_only_a_lead_can_view_the_unassigned_queue(client, users, events, role):
    users.get.return_value = organiser_me_response(role=role)

    response = client.get("/event-requests/unassigned")

    assert response.status_code == 403
    events.get.assert_not_awaited()


def test_unassigned_queue_requires_authentication(client, users, events):
    users.get.return_value = fake_response(401, {"detail": "Not authenticated"})

    response = client.get("/event-requests/unassigned")

    assert response.status_code == 401
    events.get.assert_not_awaited()


def test_lead_queue_returns_basic_event_and_organiser_information(client, users, events):
    async def users_get(path, **kwargs):
        assert path == "/users/me"
        return lead_me_response()

    users.get.side_effect = users_get
    users.post.return_value = fake_response(
        200,
        [{"id": ORGANISER_ID, "name": "Ada Organiser", "email": "ada@example.com"}],
    )
    events.get.return_value = fake_response(
        200, [event_response(status_code=200, assigned_coordinator_id=None).json()]
    )

    response = client.get("/event-requests/unassigned")

    assert response.status_code == 200
    item = response.json()[0]
    assert item["name"] == SUBMITTED["name"]
    assert item["expected_attendance"] == 120
    assert item["organiser"]["name"] == "Ada Organiser"
    users.post.assert_awaited_once_with("/internal/users/profiles", json={"ids": [ORGANISER_ID]})


def test_lead_lists_trusted_coordinators_without_availability_filtering(
    client, users, events
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        if path == "/internal/users/coordinators":
            return fake_response(
                200,
                [coordinator(COORDINATOR_A), coordinator(COORDINATOR_B)],
            )
        raise AssertionError(path)

    users.get.side_effect = users_get

    response = client.get("/event-requests/coordinators")

    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {COORDINATOR_A, COORDINATOR_B}
    events.post.assert_not_awaited()


def test_lead_can_assign_a_conflicting_trusted_coordinator(
    client, users, events, notifications
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        if path == "/internal/users/coordinators":
            return fake_response(200, [coordinator(COORDINATOR_A, "Alex Coordinator")])
        raise AssertionError(path)

    users.get.side_effect = users_get
    events.post.return_value = event_response(
        status_code=200,
        assigned_coordinator_id=COORDINATOR_A,
        assignment_created=True,
        name="Autumn Forum",
    )
    notifications.post.return_value = fake_response(201, [{"id": 1}, {"id": 2}])

    response = client.post(
        f"/event-requests/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 200
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_A
    assert all(call.args[0] != "/events/coordinator-load" for call in events.post.await_args_list)
    batch = notifications.post.call_args.kwargs["json"]["notifications"]
    assert {row["recipient_id"] for row in batch} == {COORDINATOR_A, ORGANISER_ID}
    assert len({row["deduplication_key"] for row in batch}) == 2


def test_assignment_rejects_ids_outside_the_trusted_coordinator_pool(
    client, users, events, notifications
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        if path == "/internal/users/coordinators":
            return fake_response(200, [coordinator(COORDINATOR_A)])
        raise AssertionError(path)

    users.get.side_effect = users_get

    response = client.post(
        f"/event-requests/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_B},
    )

    assert response.status_code == 422
    events.post.assert_not_awaited()
    notifications.post.assert_not_awaited()


@pytest.mark.parametrize(
    "role,expected",
    [
        ("event_coordinator", 403),
        ("event_organiser", 403),
        ("venue_staff", 403),
        ("technical_support", 403),
        ("attendee", 403),
        (None, 401),
    ],
)
def test_only_a_lead_can_assign_an_event_request(
    client, users, events, notifications, role, expected
):
    users.get.return_value = (
        fake_response(401, {"detail": "Not authenticated"})
        if role is None
        else organiser_me_response(role=role)
    )

    response = client.post(
        f"/event-requests/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == expected
    events.post.assert_not_awaited()
    notifications.post.assert_not_awaited()


@pytest.mark.parametrize("downstream_status", [404, 409])
def test_assignment_preserves_missing_and_concurrent_results(
    client, users, events, notifications, downstream_status
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        return fake_response(200, [coordinator(COORDINATOR_A)])

    users.get.side_effect = users_get
    events.post.return_value = fake_response(
        downstream_status, {"detail": "Event unavailable"}
    )

    response = client.post(
        f"/event-requests/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == downstream_status
    assert response.json() == {"detail": "Event unavailable"}
    notifications.post.assert_not_awaited()


def test_assignment_notifies_coordinator_and_organiser_in_app(
    client, users, events, notifications
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        return fake_response(200, [coordinator(COORDINATOR_A, "Alex Coordinator")])

    users.get.side_effect = users_get
    events.post.return_value = event_response(
        status_code=200,
        assigned_coordinator_id=COORDINATOR_A,
        assignment_created=True,
        name="Autumn Forum",
    )
    notifications.post.return_value = fake_response(201, [{"id": 1}, {"id": 2}])

    response = client.post(
        f"/event-requests/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 200
    notifications.post.assert_awaited_once()
    call = notifications.post.await_args
    assert call.args[0] == "/internal/notifications"
    rows = call.kwargs["json"]["notifications"]
    assert {row["recipient_id"] for row in rows} == {COORDINATOR_A, ORGANISER_ID}
    assert all(row["kind"] == "event_assignment" for row in rows)
    assert {row["deduplication_key"] for row in rows} == {
        f"event_assignment:{EVENT_ID}:{COORDINATOR_A}",
        f"event_assignment:{EVENT_ID}:{ORGANISER_ID}",
    }


def test_assignment_retry_repairs_notifications_idempotently(
    client, users, events, notifications
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        return fake_response(200, [coordinator(COORDINATOR_A, "Alex Coordinator")])

    users.get.side_effect = users_get
    events.post.side_effect = [
        event_response(status_code=200, assigned_coordinator_id=COORDINATOR_A, assignment_created=True),
        event_response(status_code=200, assigned_coordinator_id=COORDINATOR_A, assignment_created=False),
    ]
    notifications.post.side_effect = [
        fake_response(502, {"detail": "down"}),
        fake_response(201, [{"id": 1}, {"id": 2}]),
    ]

    first = client.post(
        f"/event-requests/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )
    second = client.post(
        f"/event-requests/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
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


def test_assignment_reports_notifications_connection_failure(
    client, users, events, notifications
):
    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        return fake_response(200, [coordinator(COORDINATOR_A)])

    users.get.side_effect = users_get
    events.post.return_value = event_response(status_code=200, assigned_coordinator_id=COORDINATOR_A)
    notifications.post.side_effect = httpx.ConnectError("down")

    response = client.post(
        f"/event-requests/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Notifications service unavailable"}


def test_s83_dependency_failures_are_safe(client, users, events, notifications):
    users.get.return_value = lead_me_response()
    events.get.side_effect = httpx.ConnectError("events down")

    queue = client.get("/event-requests/unassigned")

    assert queue.status_code == 502
    assert queue.json() == {"detail": "Events service unavailable"}

    events.get.side_effect = None
    events.get.return_value = fake_response(
        200, [event_response(status_code=200, assigned_coordinator_id=None).json()]
    )
    users.post.side_effect = httpx.ConnectError("users down")

    profiles = client.get("/event-requests/unassigned")

    assert profiles.status_code == 502
    assert profiles.json() == {"detail": "Users service unavailable"}

    users.post.side_effect = None

    async def users_get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        return fake_response(200, [coordinator(COORDINATOR_A)])

    users.get.side_effect = users_get
    events.post.side_effect = httpx.ConnectError("events down")

    assignment = client.post(
        f"/event-requests/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert assignment.status_code == 502
    assert assignment.json() == {"detail": "Events service unavailable"}
    notifications.post.assert_not_awaited()
