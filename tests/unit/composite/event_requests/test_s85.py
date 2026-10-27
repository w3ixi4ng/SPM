"""S-85 Event Coordinator Lead oversight tests."""

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
COORDINATOR_C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ACTIVE_STATUSES = [
    "submitted",
    "under_review",
    "returned",
    "planning",
    "pending_safety_check",
    "confirmed",
    "preparation",
    "safety_rejected",
    "safety_changes_requested",
]


def lead_me_response():
    return organiser_me_response(user_id=LEAD_ID, role="event_coordinator_lead")


def _users_get(pool):
    async def get(path, **kwargs):
        if path == "/users/me":
            return lead_me_response()
        if path == "/internal/users/coordinators":
            return fake_response(200, pool)
        raise AssertionError(path)

    return get


def _event(owner, status="submitted", name="Autumn Forum", **changes):
    return event_response(
        status_code=200,
        assigned_coordinator_id=owner,
        coordinator_assignment_version=0,
        status=status,
        name=name,
        **changes,
    ).json()


@pytest.mark.parametrize(
    "me_response,expected",
    [
        (fake_response(401, {"detail": "Not authenticated"}), 401),
        (organiser_me_response(role="event_organiser"), 403),
        (organiser_me_response(role="event_coordinator"), 403),
    ],
)
def test_only_a_lead_can_read_coordinator_overview(
    client, users, events, notifications, me_response, expected
):
    users.get.return_value = me_response

    response = client.get("/event-requests/coordinator-overview")

    assert response.status_code == expected
    assert users.get.await_count == 1
    events.get.assert_not_awaited()
    users.post.assert_not_awaited()
    notifications.post.assert_not_awaited()


def test_overview_groups_events_and_keeps_zero_assignment_coordinators(
    client, users, events
):
    pool = [
        coordinator(COORDINATOR_B, "Blair Coordinator"),
        coordinator(COORDINATOR_C, "Casey Coordinator"),
        coordinator(COORDINATOR_A, "Alex Coordinator"),
    ]
    users.get.side_effect = _users_get(pool)
    events.get.return_value = fake_response(
        200,
        [
            _event(COORDINATOR_A, name="A first"),
            _event(COORDINATOR_A, name="A second"),
            _event(COORDINATOR_B, name="B only"),
        ],
    )
    users.post.return_value = fake_response(
        200,
        [{"id": ORGANISER_ID, "name": "Ada Organiser", "email": "ada@example.com"}],
    )

    response = client.get("/event-requests/coordinator-overview")

    assert response.status_code == 200
    groups = response.json()["coordinators"]
    assert [group["coordinator"]["name"] for group in groups] == [
        "Alex Coordinator",
        "Blair Coordinator",
        "Casey Coordinator",
    ]
    assert [group["active_assignment_count"] for group in groups] == [2, 1, 0]
    assert [event["name"] for event in groups[0]["events"]] == ["A first", "A second"]
    assert [event["name"] for event in groups[1]["events"]] == ["B only"]
    assert groups[2]["events"] == []


@pytest.mark.parametrize("event_status", ACTIVE_STATUSES)
def test_overview_reports_invalid_owners_without_creating_groups(
    client, users, events, notifications, event_status
):
    deleted_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    wrong_role_id = "99999999-9999-4999-8999-999999999999"
    users.get.side_effect = _users_get([coordinator(COORDINATOR_A, "Alex Coordinator")])
    rows = [
        _event(COORDINATOR_A, status=event_status, id="11111111-1111-4111-8111-111111111111", name="A's event"),
        _event(deleted_id, status=event_status, id="22222222-2222-4222-8222-222222222222", name="Deleted owner"),
        _event(wrong_role_id, status=event_status, id="33333333-3333-4333-8333-333333333333", name="Wrong role"),
    ]
    events.get.return_value = fake_response(200, rows)
    users.post.return_value = fake_response(
        200, [{"id": ORGANISER_ID, "name": "Ada Organiser", "email": "ada@example.com"}],
    )

    response = client.get("/event-requests/coordinator-overview")

    assert response.status_code == 200
    body = response.json()
    assert [group["coordinator"]["id"] for group in body["coordinators"]] == [COORDINATOR_A]
    assert body["coordinators"][0]["active_assignment_count"] == 1
    assert [event["name"] for event in body["coordinators"][0]["events"]] == ["A's event"]
    assert body["invalid_assignments"] == [
        {"event_id": rows[1]["id"], "name": "Deleted owner", "status": event_status, "assigned_coordinator_id": deleted_id, "reason": "identity_missing"},
        {"event_id": rows[2]["id"], "name": "Wrong role", "status": event_status, "assigned_coordinator_id": wrong_role_id, "reason": "identity_missing"},
    ]
    users.post.assert_awaited_once_with("/internal/users/profiles", json={"ids": [ORGANISER_ID]})
    events.post.assert_not_awaited()
    notifications.post.assert_not_awaited()


def test_overview_groups_profileless_trusted_coordinators_and_keeps_idle(
    client, users, events, notifications
):
    pool = [
        coordinator(COORDINATOR_A, "Alex Coordinator"),
        {"id": COORDINATOR_B, "name": "blair@example.com", "email": "blair@example.com"},
        {"id": COORDINATOR_C, "name": "casey@example.com", "email": "casey@example.com"},
    ]
    users.get.side_effect = _users_get(pool)
    rows = [
        _event(COORDINATOR_A, id="11111111-1111-4111-8111-111111111111", name="A"),
        _event(COORDINATOR_B, id="22222222-2222-4222-8222-222222222222", name="B1"),
        _event(COORDINATOR_B, id="33333333-3333-4333-8333-333333333333", name="B2"),
    ]
    async def scoped_events_get(path, **kwargs):
        if path.endswith("/assignment-scope"):
            return fake_response(200, {**rows[0], "assigning_lead_id": LEAD_ID})
        return fake_response(200, rows)

    events.get.side_effect = scoped_events_get
    users.post.return_value = fake_response(
        200, [{"id": ORGANISER_ID, "name": "Ada Organiser", "email": "ada@example.com"}],
    )

    response = client.get("/event-requests/coordinator-overview")

    assert response.status_code == 200
    groups = {group["coordinator"]["id"]: group for group in response.json()["coordinators"]}
    assert set(groups) == {COORDINATOR_A, COORDINATOR_B, COORDINATOR_C}
    assert {key: group["active_assignment_count"] for key, group in groups.items()} == {
        COORDINATOR_A: 1, COORDINATOR_B: 2, COORDINATOR_C: 0,
    }
    assert groups[COORDINATOR_B]["coordinator"]["name"] == "blair@example.com"
    assert [event["name"] for event in groups[COORDINATOR_B]["events"]] == ["B1", "B2"]
    assert groups[COORDINATOR_C]["events"] == []
    assert response.json()["invalid_assignments"] == []

    events.post.return_value = fake_response(200, {
        **rows[0],
        "assigned_coordinator_id": COORDINATOR_C,
        "previous_coordinator_id": COORDINATOR_A,
        "coordinator_assignment_version": 1,
        "reassignment_created": True,
    })
    notifications.post.return_value = fake_response(201, [{"id": 1}])
    moved = client.post(f"/event-requests/{rows[0]['id']}/reassignment", json={
        "coordinator_id": COORDINATOR_C,
        "expected_coordinator_id": COORDINATOR_A,
        "expected_assignment_version": 0,
    })
    assert moved.status_code == 200
    events.get.side_effect = None
    events.get.return_value = fake_response(200, [
        {**rows[0], "assigned_coordinator_id": COORDINATOR_C, "coordinator_assignment_version": 1},
        *rows[1:],
    ])
    refreshed = client.get("/event-requests/coordinator-overview")
    assert refreshed.status_code == 200
    updated = {group["coordinator"]["id"]: group for group in refreshed.json()["coordinators"]}
    assert {key: group["active_assignment_count"] for key, group in updated.items()} == {
        COORDINATOR_A: 0, COORDINATOR_B: 2, COORDINATOR_C: 1,
    }
    assert [event["id"] for event in updated[COORDINATOR_C]["events"]] == [rows[0]["id"]]


def test_overview_enriches_event_summaries_with_profiles(client, users, events):
    pool = [coordinator(COORDINATOR_A, "Alex Coordinator")]
    users.get.side_effect = _users_get(pool)
    events.get.return_value = fake_response(
        200,
        [
            _event(
                COORDINATOR_A,
                status="under_review",
                start_date="2026-11-18",
                start_time="09:00:00",
                end_date="2026-11-18",
                end_time="12:00:00",
            )
        ],
    )
    users.post.return_value = fake_response(
        200,
        [{"id": ORGANISER_ID, "name": "Ada Organiser", "email": "ada@example.com"}],
    )

    response = client.get("/event-requests/coordinator-overview")

    assert response.status_code == 200
    summary = response.json()["coordinators"][0]["events"][0]
    assert summary["id"] == EVENT_ID
    assert summary["name"] == "Autumn Forum"
    assert summary["status"] == "under_review"
    assert summary["organiser"]["name"] == "Ada Organiser"
    assert summary["coordinator"]["name"] == "Alex Coordinator"
    assert summary["start_date"] == "2026-11-18"
    assert summary["start_time"] == "09:00:00"
    assert summary["end_date"] == "2026-11-18"
    assert summary["end_time"] == "12:00:00"
    assert summary["coordinator_assignment_version"] == 0
    users.post.assert_awaited_once_with(
        "/internal/users/profiles", json={"ids": [ORGANISER_ID]}
    )


@pytest.mark.parametrize("pool", [[], [coordinator(COORDINATOR_A, "Alex Coordinator")]])
def test_overview_handles_empty_events_and_empty_pool(client, users, events, pool):
    users.get.side_effect = _users_get(pool)
    events.get.return_value = fake_response(200, [])

    response = client.get("/event-requests/coordinator-overview")

    assert response.status_code == 200
    groups = response.json()["coordinators"]
    assert len(groups) == len(pool)
    assert all(group["active_assignment_count"] == 0 for group in groups)
    assert all(group["events"] == [] for group in groups)
    assert response.json()["invalid_assignments"] == []
    users.post.assert_not_awaited()


@pytest.mark.parametrize("failure", ["pool", "events", "profiles"])
def test_overview_dependency_failures_are_controlled_and_read_only(
    client, users, events, notifications, failure
):
    pool = [coordinator(COORDINATOR_A, "Alex Coordinator")]
    users.get.side_effect = _users_get(pool)
    events.get.return_value = fake_response(200, [_event(COORDINATOR_A)])
    users.post.return_value = fake_response(
        200,
        [{"id": ORGANISER_ID, "name": "Ada Organiser", "email": "ada@example.com"}],
    )

    if failure == "pool":
        async def failing_users_get(path, **kwargs):
            if path == "/users/me":
                return lead_me_response()
            raise httpx.ConnectError("users down")

        users.get.side_effect = failing_users_get
    elif failure == "events":
        events.get.side_effect = httpx.ConnectError("events down")
    else:
        users.post.return_value = fake_response(500, {"detail": "down"})

    response = client.get("/event-requests/coordinator-overview")

    assert response.status_code == 502
    assert response.json()["detail"] in {
        "Users service unavailable",
        "Events service unavailable",
    }
    events.post.assert_not_awaited()
    events.patch.assert_not_awaited()
    notifications.post.assert_not_awaited()


def test_overview_accepts_all_five_active_statuses(client, users, events):
    pool = [coordinator(COORDINATOR_A, "Alex Coordinator")]
    users.get.side_effect = _users_get(pool)
    events.get.return_value = fake_response(
        200,
        [_event(COORDINATOR_A, status=status, name=status) for status in ACTIVE_STATUSES],
    )
    users.post.return_value = fake_response(
        200,
        [{"id": ORGANISER_ID, "name": "Ada Organiser", "email": "ada@example.com"}],
    )

    response = client.get("/event-requests/coordinator-overview")

    assert response.status_code == 200
    events_in_group = response.json()["coordinators"][0]["events"]
    assert [event["status"] for event in events_in_group] == ACTIVE_STATUSES
