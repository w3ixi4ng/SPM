"""S-87 atomic lifecycle, audit-history and concurrency specifications."""

from types import SimpleNamespace

from .conftest import COORDINATOR_A, COORDINATOR_B, EVENT_ID, event_row


OFFICER_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def returned_event(**changes):
    review = {
        "review_number": 1,
        "decision": "changes_requested",
        "reason": "Move speakers away from the emergency exit",
        "safety_officer_id": OFFICER_ID,
        "decided_at": "2026-10-10T09:00:00Z",
    }
    values = {
        "status": "planning",
        "name": "Safety Forum",
        "purpose": "Operational safety review",
        "start_date": "2026-11-18",
        "start_time": "09:00:00",
        "end_date": "2026-11-18",
        "end_time": "12:00:00",
        "expected_attendance": 120,
        "submitted_at": "2026-10-09T00:00:00Z",
        "decision": "approved",
        "decided_at": "2026-10-10T00:00:00Z",
        "assigned_coordinator_id": COORDINATOR_A,
        "technical_support_required": True,
        "technical_support_details": "Keep speakers clear of exits",
        "assigned_technical_support_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        "technical_support_assigned_at": "2026-10-10T01:00:00Z",
        "safety_decision": "changes_requested",
        "safety_decision_reason": review["reason"],
        "safety_officer_id": OFFICER_ID,
        "safety_decided_at": review["decided_at"],
        "safety_review_history": [review],
    }
    values.update(changes)
    return event_row(**values)


def event_select(db, rows):
    operation = db.schema.return_value.table.return_value.select.return_value.eq.return_value
    operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def assigned_select(db, rows):
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def resubmit_update(db, rows):
    operation = (
        db.schema.return_value.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def test_changes_requested_returns_to_planning_and_appends_immutable_history(client, db):
    current = returned_event(
        status="pending_safety_check",
        safety_decision=None,
        safety_decision_reason=None,
        safety_officer_id=None,
        safety_decided_at=None,
        safety_review_history=[],
    )
    stored = returned_event()
    event_select(db, [current])
    operation = (
        db.schema.return_value.table.return_value.update.return_value.eq.return_value.eq.return_value.is_.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=[stored])

    response = client.post(
        f"/internal/events/safety-review/{EVENT_ID}/decision",
        json={
            "decision": "changes_requested",
            "reason": "Move speakers away from the emergency exit",
            "safety_officer_id": OFFICER_ID,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "planning"
    values = db.schema.return_value.table.return_value.update.call_args.args[0]
    assert values["safety_decision"] == "changes_requested"
    assert values["safety_review_history"][0]["decision"] == "changes_requested"
    assert values["safety_review_history"][0]["review_number"] == 1
    assert "technical_support_details" not in values
    assert "assigned_technical_support_id" not in values


def test_only_currently_assigned_coordinator_can_open_returned_safety_work(client, db):
    assigned_select(db, [returned_event()])
    allowed = client.get(
        f"/internal/events/{EVENT_ID}/safety-return",
        params={"coordinator_id": COORDINATOR_A},
    )
    assert allowed.status_code == 200
    assert allowed.json()["safety_review_history"][0]["reason"].startswith("Move speakers")

    assigned_select(db, [])
    denied = client.get(
        f"/internal/events/{EVENT_ID}/safety-return",
        params={"coordinator_id": COORDINATOR_B},
    )
    assert denied.status_code == 404


def test_only_safety_returned_planning_event_can_be_resubmitted(client, db):
    for ineligible in (
        returned_event(safety_decision=None, safety_review_history=[]),
        returned_event(status="confirmed"),
        returned_event(status="pending_safety_check", safety_decision=None),
        returned_event(safety_decision="approved"),
    ):
        assigned_select(db, [ineligible])
        response = client.post(
            f"/internal/events/{EVENT_ID}/safety-resubmit",
            json={"coordinator_id": COORDINATOR_A},
        )
        assert response.status_code == 409

    db.schema.return_value.table.return_value.update.assert_not_called()


def test_resubmit_clears_only_current_blocker_and_preserves_history(client, db):
    current = returned_event()
    pending = returned_event(
        status="pending_safety_check",
        safety_decision=None,
        safety_decision_reason=None,
        safety_officer_id=None,
        safety_decided_at=None,
    )
    assigned_select(db, [current])
    resubmit_update(db, [pending])

    response = client.post(
        f"/internal/events/{EVENT_ID}/safety-resubmit",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending_safety_check"
    assert response.json()["safety_decision"] is None
    assert response.json()["safety_review_history"] == current["safety_review_history"]
    values = db.schema.return_value.table.return_value.update.call_args.args[0]
    assert values == {
        "status": "pending_safety_check",
        "safety_decision": None,
        "safety_decision_reason": None,
        "safety_officer_id": None,
        "safety_decided_at": None,
    }


def test_repeated_or_concurrent_resubmit_is_409_without_fallback_write(client, db):
    assigned_select(db, [returned_event()])
    operation = resubmit_update(db, [])

    response = client.post(
        f"/internal/events/{EVENT_ID}/safety-resubmit",
        json={"coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 409
    assert "changed" in response.json()["detail"].lower()
    operation.execute.assert_called_once()
    assert db.schema.return_value.table.return_value.update.call_count == 1
