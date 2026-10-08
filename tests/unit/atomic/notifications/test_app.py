from types import SimpleNamespace

from .conftest import EVENT_ID, ORGANISER, RECIPIENT, authenticate, notification_row


def batch():
    return {
        "notifications": [
            {
                "recipient_id": RECIPIENT,
                "event_id": EVENT_ID,
                "event_name": "Autumn Forum",
                "kind": "event_assignment",
                "message": "You have been assigned to Autumn Forum.",
                "deduplication_key": f"event_assignment:{EVENT_ID}:{RECIPIENT}",
            },
            {
                "recipient_id": ORGANISER,
                "event_id": EVENT_ID,
                "event_name": "Autumn Forum",
                "kind": "event_assignment",
                "message": "Alex Coordinator has been assigned to Autumn Forum.",
                "deduplication_key": f"event_assignment:{EVENT_ID}:{ORGANISER}",
            },
        ]
    }


def test_health_reports_ok(client, db, auth):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    db.assert_not_called()
    auth.assert_not_called()


def test_list_notifications_requires_authentication(client, db):
    response = client.get("/notifications")
    assert response.status_code == 401
    db.schema.assert_not_called()


def test_user_lists_only_their_notifications_newest_first(client, db, auth):
    authenticate(client, auth)
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value.order.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=[notification_row()])

    response = client.get("/notifications")

    assert response.status_code == 200
    assert response.json()[0]["recipient_id"] == RECIPIENT
    db.schema.return_value.table.return_value.select.return_value.eq.assert_called_once_with(
        "recipient_id", RECIPIENT
    )
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.order.assert_called_once_with(
        "created_at", desc=True
    )


def test_empty_notification_inbox_returns_an_empty_list(client, db, auth):
    authenticate(client, auth)
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value.order.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=[])
    assert client.get("/notifications").json() == []


def test_internal_batch_persists_both_assignment_notifications(client, db):
    rows = [notification_row(), notification_row(ORGANISER, 2)]
    operation = db.schema.return_value.table.return_value.upsert.return_value
    operation.execute.return_value = SimpleNamespace(data=rows)

    response = client.post("/internal/notifications", json=batch())

    assert response.status_code == 201
    assert len(response.json()) == 2
    args, kwargs = db.schema.return_value.table.return_value.upsert.call_args
    assert len(args[0]) == 2
    assert kwargs == {"on_conflict": "deduplication_key"}


def test_internal_batch_is_idempotent_by_deduplication_key(client, db):
    rows = [notification_row(), notification_row(ORGANISER, 2)]
    operation = db.schema.return_value.table.return_value.upsert.return_value
    operation.execute.side_effect = [SimpleNamespace(data=rows), SimpleNamespace(data=rows)]

    first = client.post("/internal/notifications", json=batch())
    second = client.post("/internal/notifications", json=batch())

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert db.schema.return_value.table.return_value.upsert.call_count == 2
    for call in db.schema.return_value.table.return_value.upsert.call_args_list:
        assert call.kwargs["on_conflict"] == "deduplication_key"


def test_duplicate_keys_in_one_batch_are_rejected_before_storage(client, db):
    body = batch()
    body["notifications"][1]["deduplication_key"] = body["notifications"][0]["deduplication_key"]
    response = client.post("/internal/notifications", json=body)
    assert response.status_code == 422
    db.schema.assert_not_called()


def test_notification_storage_failures_are_safe(client, db, auth):
    authenticate(client, auth)
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value.order.return_value
    )
    operation.execute.side_effect = RuntimeError("boom")
    response = client.get("/notifications")
    assert response.status_code == 500
    assert response.json() == {"detail": "Notification storage unavailable"}
