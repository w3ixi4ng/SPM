"""Real notification persistence, privacy, and idempotency coverage."""

import uuid

import httpx

from .conftest import BASE_URL, requires_env

pytestmark = requires_env


# --- TC-NOTIFICATIONS-101 -------------------------------------------------
def test_assignment_notifications_persist_and_are_recipient_private(
    admin, notification_users
):
    organiser, coordinator, unrelated = notification_users
    event_id = str(uuid.uuid4())
    batch = {
        "notifications": [
            {
                "recipient_id": coordinator["id"],
                "event_id": event_id,
                "event_name": "Autumn Forum",
                "kind": "event_assignment",
                "message": "You have been assigned to Autumn Forum.",
                "deduplication_key": f"event_assignment:{event_id}:{coordinator['id']}",
            },
            {
                "recipient_id": organiser["id"],
                "event_id": event_id,
                "event_name": "Autumn Forum",
                "kind": "event_assignment",
                "message": "A Coordinator has been assigned to Autumn Forum.",
                "deduplication_key": f"event_assignment:{event_id}:{organiser['id']}",
            },
        ]
    }

    def inbox(api, user):
        return api.get(
            "/notifications",
            headers={"Cookie": f"sb_access_token={user['access_token']}"},
        )

    def matching_rows():
        return (
            admin.schema("notifications")
            .table("notifications")
            .select("*")
            .eq("event_id", event_id)
            .execute()
            .data
        )

    with httpx.Client(base_url=BASE_URL, timeout=15.0) as api:
        created = api.post("/internal/notifications", json=batch)
        assert created.status_code == 201, created.text

        for user in (organiser, coordinator):
            first = inbox(api, user)
            second = inbox(api, user)
            assert first.status_code == second.status_code == 200
            assert [row["event_id"] for row in first.json()].count(event_id) == 1
            assert [row["event_id"] for row in second.json()].count(event_id) == 1
        assert all(row["event_id"] != event_id for row in inbox(api, unrelated).json())

        repeated = api.post("/internal/notifications", json=batch)
        assert repeated.status_code == 201, repeated.text
        assert len(matching_rows()) == 2

        for missing_recipient in (organiser["id"], coordinator["id"]):
            admin.schema("notifications").table("notifications").delete().eq(
                "event_id", event_id
            ).eq("recipient_id", missing_recipient).execute()
            assert len(matching_rows()) == 1

            repaired = api.post("/internal/notifications", json=batch)
            assert repaired.status_code == 201, repaired.text
            rows = matching_rows()
            assert len(rows) == 2
            assert {row["recipient_id"] for row in rows} == {
                organiser["id"], coordinator["id"]
            }
