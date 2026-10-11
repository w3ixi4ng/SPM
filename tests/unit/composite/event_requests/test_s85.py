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
    "confirmed",
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
