"""S-71 equipment availability-change orchestration."""

from unittest.mock import AsyncMock

import pytest

from .conftest import (
    ITEM_ID,
    SUPPORT_ID,
    app_module,
    fake_response,
    user,
)

changes = app_module.availability_changes

E1 = "11111111-1111-4111-8111-111111111111"
E2 = "22222222-2222-4222-8222-222222222223"
E3 = "33333333-3333-4333-8333-333333333333"
C1 = "44444444-4444-4444-8444-444444444444"
C2 = "55555555-5555-4555-8555-555555555555"
C3 = "66666666-6666-4666-8666-666666666666"
PATH = f"/equipment-requirements/equipment/{ITEM_ID}"


def item(**updates):
    row = {
        "id": ITEM_ID,
        "type": "Projector",
        "description": "Laser projector",
        "storage_location": "AV Store",
        "total_quantity": 10,
        "operational_status": "available",
        "lifecycle_status": "active",
        "created_by": SUPPORT_ID,
        "created_at": "2026-10-01T01:00:00Z",
        "updated_at": "2026-10-30T01:00:00Z",
    }
    row.update(updates)
    return row


def event(event_id, name, status, coordinator, start="09:00:00", end="12:00:00"):
    return {
        "id": event_id,
        "name": name,
        "status": status,
        "assigned_coordinator_id": coordinator,
        "start_date": "2026-11-20",
        "start_time": start,
        "end_date": "2026-11-20",
        "end_time": end,
    }


EVENTS = [
    event(E1, "Autumn Forum", "confirmed", C1),
    event(E2, "Research Showcase", "preparation", C2, "10:00:00", "11:00:00"),
    event(E3, "Draft Workshop", "planning", C3),
]
REQUIREMENTS = [
    {"event_id": E1, "equipment_item_id": ITEM_ID, "required_quantity": 3},
    {"event_id": E2, "equipment_item_id": ITEM_ID, "required_quantity": 4},
    {"event_id": E3, "equipment_item_id": ITEM_ID, "required_quantity": 9},
]


def payload(**updates):
    body = {
        "type": "Projector",
        "description": "Laser projector",
        "storage_location": "AV Store",
        "total_quantity": 10,
        "operational_status": "available",
    }
    body.update(updates)
    return body


def arrange_change(services, after):
    services.me = fake_response(200, user("technical_support", SUPPORT_ID))
    services.events.get = AsyncMock(
        return_value=fake_response(200, EVENTS)
    )
    services.equipment.get = AsyncMock(
        side_effect=[
            fake_response(200, item()),
            fake_response(200, REQUIREMENTS),
        ]
    )
    services.equipment.put = AsyncMock(return_value=fake_response(200, after))
    services.equipment.post = AsyncMock(return_value=fake_response(200, after))


@pytest.mark.parametrize(
    ("method", "body", "after", "detail"),
    [
        (
            "put",
            payload(operational_status="unavailable"),
            item(operational_status="unavailable", updated_at="2026-10-30T02:00:00Z"),
            "the item is unavailable",
        ),
        (
            "put",
            payload(operational_status="maintenance"),
            item(operational_status="maintenance", updated_at="2026-10-30T03:00:00Z"),
            "the item is under maintenance",
        ),
        (
            "put",
            payload(total_quantity=5),
            item(total_quantity=5, updated_at="2026-10-30T04:00:00Z"),
            "available stock was reduced to 5",
        ),
        (
            "post",
            None,
            item(lifecycle_status="retired", updated_at="2026-10-30T05:00:00Z"),
            "the item was retired",
        ),
    ],
)
def test_degrading_change_notifies_each_committed_events_current_coordinator(
    client, services, method, body, after, detail
):
    arrange_change(services, after)

    if method == "put":
        response = client.put(PATH, json=body)
    else:
        response = client.post(f"{PATH}/retire")

    assert response.status_code == 200
    assert response.json()["availability_notifications_sent"] is True
    sent = services.notifications.post.await_args.kwargs["json"]["notifications"]
    assert [(row["event_id"], row["recipient_id"]) for row in sent] == [
        (E1, C1),
        (E2, C2),
    ]
    assert all(row["kind"] == "equipment_unavailable" for row in sent)
    assert all("Projector" in row["message"] and detail in row["message"] for row in sent)
    assert "Autumn Forum" in sent[0]["message"]
    assert "Research Showcase" in sent[1]["message"]
    assert all("Arrange replacement equipment before the event." in row["message"] for row in sent)
    assert all(row["event_id"] != E3 and row["recipient_id"] != C3 for row in sent)


def test_only_events_that_become_short_are_returned_and_back_to_back_does_not_overlap():
    e1 = event(E1, "One", "confirmed", C1, "09:00:00", "10:00:00")
    e2 = event(E2, "Two", "preparation", C2, "09:30:00", "10:30:00")
    e3 = event(E3, "Back to back", "confirmed", C3, "10:30:00", "11:30:00")
    requirements = [
        {"event_id": E1, "equipment_item_id": ITEM_ID, "required_quantity": 3},
        {"event_id": E2, "equipment_item_id": ITEM_ID, "required_quantity": 4},
        {"event_id": E3, "equipment_item_id": ITEM_ID, "required_quantity": 2},
    ]

    affected = changes.newly_affected(
        item(total_quantity=10),
        item(total_quantity=5),
        [e1, e2, e3],
        requirements,
    )

    assert [row["id"] for row in affected] == [E1, E2]

    already_short = changes.newly_affected(
        item(total_quantity=2),
        item(total_quantity=1),
        [e1],
        [requirements[0]],
    )
    assert already_short == []


@pytest.mark.parametrize(
    ("body", "after"),
    [
        (
            payload(type="Auditorium Projector", storage_location="Store B"),
            item(type="Auditorium Projector", storage_location="Store B", updated_at="2026-10-30T06:00:00Z"),
        ),
        (
            payload(total_quantity=12),
            item(total_quantity=12, updated_at="2026-10-30T07:00:00Z"),
        ),
        (
            payload(total_quantity=8),
            item(total_quantity=8, updated_at="2026-10-30T08:00:00Z"),
        ),
    ],
)
def test_harmless_catalogue_edits_do_not_notify(client, services, body, after):
    arrange_change(services, after)

    response = client.put(PATH, json=body)

    assert response.status_code == 200
    services.notifications.post.assert_not_awaited()


def test_rebuilding_one_saved_change_uses_the_same_deduplication_key():
    changed = item(operational_status="maintenance", updated_at="2026-10-30T09:00:00Z")
    affected = [EVENTS[0]]

    first = changes.notifications(changed, affected)
    second = changes.notifications(changed, affected)

    assert first == second
    assert first[0]["deduplication_key"] == (
        f"equipment_unavailable:{ITEM_ID}:2026-10-30T09:00:00Z:{E1}:{C1}"
    )


def test_notification_failure_does_not_claim_the_catalogue_write_was_rolled_back(
    client, services
):
    after = item(operational_status="unavailable", updated_at="2026-10-30T10:00:00Z")
    arrange_change(services, after)
    services.notifications.post = AsyncMock(return_value=fake_response(500, {}))

    response = client.put(PATH, json=payload(operational_status="unavailable"))

    assert response.status_code == 200
    assert response.json()["operational_status"] == "unavailable"
    assert response.json()["availability_notifications_sent"] is False


def test_catalogue_orchestration_is_limited_to_technical_support(client, services):
    response = client.put(PATH, json=payload(operational_status="maintenance"))

    assert response.status_code == 403
    services.equipment.get.assert_not_awaited()
    services.equipment.put.assert_not_awaited()
    services.notifications.post.assert_not_awaited()
