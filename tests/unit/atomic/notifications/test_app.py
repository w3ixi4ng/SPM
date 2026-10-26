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


def test_internal_batch_accepts_three_reassignment_recipients(client, db):
    former = RECIPIENT
    new = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    body = {
        "notifications": [
            {
                "recipient_id": recipient,
                "event_id": EVENT_ID,
                "event_name": "Autumn Forum",
                "kind": "event_reassignment",
                "message": message,
                "deduplication_key": f"event_reassignment:{EVENT_ID}:1:{recipient}",
            }
            for recipient, message in (
                (former, "Autumn Forum has been reassigned to Blair."),
                (new, "You have been assigned to Autumn Forum."),
                (ORGANISER, "Autumn Forum has been reassigned from Alex to Blair."),
            )
        ]
    }
    rows = [
        notification_row(
            recipient,
            index,
            kind="event_reassignment",
            message=item["message"],
            deduplication_key=item["deduplication_key"],
        )
        for index, (recipient, item) in enumerate(
            ((row["recipient_id"], row) for row in body["notifications"]), start=1
        )
    ]
    db.schema.return_value.table.return_value.upsert.return_value.execute.return_value = (
        SimpleNamespace(data=rows)
    )

    response = client.post("/internal/notifications", json=body)

    assert response.status_code == 201
    assert len(response.json()) == 3
    sent = db.schema.return_value.table.return_value.upsert.call_args.args[0]
    assert {row["recipient_id"] for row in sent} == {former, new, ORGANISER}
    assert all(row["kind"] == "event_reassignment" for row in sent)


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


# --- TC-NOTIFICATIONS-009 ---------------------------------------------------
VENUE_UNAVAILABLE = {
    "recipient_id": RECIPIENT,
    "event_id": EVENT_ID,
    "event_name": "Alumni talk",
    "kind": "venue_unavailable",
    "message": (
        "Studio B is unavailable from 13 Nov 2026 09:00 to 14 Nov 2026 17:00 (Equipment failure). "
        "Your booking on 13 Nov 2026 from 10:00 to 12:00 needs alternative arrangements."
    ),
    "deduplication_key": (
        "venue_unavailable:cccccccc-cccc-4ccc-8ccc-cccccccccccc:"
        f"44444444-4444-4444-8444-444444444444:{RECIPIENT}"
    ),
}


def test_a_venue_unavailable_notification_is_accepted(client, db):
    db.schema.return_value.table.return_value.upsert.return_value.execute.return_value = (
        SimpleNamespace(data=[{**VENUE_UNAVAILABLE, "id": 1, "created_at": "2026-11-10T01:00:00Z"}])
    )

    response = client.post("/internal/notifications", json={"notifications": [VENUE_UNAVAILABLE]})

    assert response.status_code == 201
    assert response.json()[0]["kind"] == "venue_unavailable"


def test_an_unknown_kind_is_still_refused(client, db):
    response = client.post(
        "/internal/notifications",
        json={"notifications": [{**VENUE_UNAVAILABLE, "kind": "venue_closed"}]},
    )

    assert response.status_code == 422
    db.schema.assert_not_called()


REGISTRATION_CONFIRMATION = {
    "recipient_id": "33333333-3333-4333-8333-333333333333",
    "event_id": "22222222-2222-4222-8222-222222222222",
    "event_name": "Alumni networking evening",
    "kind": "registration_confirmation",
    "message": (
        "Registration confirmed: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, "
        "at Seminar Room 2-1. Name: Ada Tan. Email: ada@example.com."
    ),
    "deduplication_key": "registration_confirmation:88888888-8888-4888-8888-888888888888",
}


def test_a_registration_confirmation_is_accepted(client, db):
    db.schema.return_value.table.return_value.upsert.return_value.execute.return_value = (
        SimpleNamespace(
            data=[{**REGISTRATION_CONFIRMATION, "id": 1, "created_at": "2026-11-05T04:00:00Z"}]
        )
    )

    response = client.post(
        "/internal/notifications", json={"notifications": [REGISTRATION_CONFIRMATION]}
    )

    assert response.status_code == 201
    assert response.json()[0]["kind"] == "registration_confirmation"
