"""S-86 persistence and lifecycle tests for Operational Safety Checks."""

from types import SimpleNamespace

import pytest

from .conftest import EVENT_ID, event_row


OFFICER_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
REVIEW_UPDATED_AT = "2026-09-14T00:00:00Z"


def _reviewable(**changes):
    values = {
        "status": "pending_safety_check",
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
        "safety_decision": None,
        "safety_decision_reason": None,
        "safety_officer_id": None,
        "safety_decided_at": None,
        "safety_review_history": [],
    }
    values.update(changes)
    return event_row(**values)


def _review_select(db, rows):
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value.is_.return_value.order.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def _event_select(db, rows):
    operation = db.schema.return_value.table.return_value.select.return_value.eq.return_value
    operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def _decision_update(db, rows):
    operation = (
        db.schema.return_value.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.is_.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def test_safety_queue_selects_only_undecided_pending_events(client, db):
    _review_select(db, [_reviewable()])

    response = client.get("/internal/events/safety-review")

    assert response.status_code == 200
    assert response.json()[0]["status"] == "pending_safety_check"
    query = db.schema.return_value.table.return_value.select.return_value
    query.eq.assert_called_once_with("status", "pending_safety_check")
    query.eq.return_value.is_.assert_called_once_with("safety_decision", "null")
    query.eq.return_value.is_.return_value.order.assert_called_once_with(
        "updated_at", desc=False
    )


def test_safety_detail_distinguishes_missing_from_ineligible(client, db):
    _event_select(db, [])
    missing = client.get(f"/internal/events/safety-review/{EVENT_ID}")
    assert missing.status_code == 404

    _event_select(db, [_reviewable(status="planning")])
    stale = client.get(f"/internal/events/safety-review/{EVENT_ID}")
    assert stale.status_code == 409

    _event_select(db, [_reviewable(safety_decision="approved")])
    decided = client.get(f"/internal/events/safety-review/{EVENT_ID}")
    assert decided.status_code == 409


@pytest.mark.parametrize(
    "decision,reason,status",
    [
        ("approved", None, "confirmed"),
        ("rejected", "Emergency exits are obstructed", "safety_rejected"),
        (
            "changes_requested",
            "Revise crowd movement and equipment placement",
            "planning",
        ),
    ],
)
def test_safety_decision_records_audit_and_distinct_lifecycle_state(
    client, db, decision, reason, status
):
    current = _reviewable()
    stored = _reviewable(
        status=status,
        safety_decision=decision,
        safety_decision_reason=reason,
        safety_officer_id=OFFICER_ID,
        safety_decided_at="2026-10-10T09:00:00Z",
        safety_review_history=[
            {
                "review_number": 1,
                "decision": decision,
                "reason": reason,
                "safety_officer_id": OFFICER_ID,
                "decided_at": "2026-10-10T09:00:00Z",
            }
        ],
    )
    _event_select(db, [current])
    _decision_update(db, [stored])

    response = client.post(
        f"/internal/events/safety-review/{EVENT_ID}/decision",
        json={
            "decision": decision,
            "reason": reason,
            "safety_officer_id": OFFICER_ID,
            "expected_event_updated_at": REVIEW_UPDATED_AT,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == status
    assert response.json()["safety_decision"] == decision
    values = db.schema.return_value.table.return_value.update.call_args.args[0]
    assert values["status"] == status
    assert values["safety_decision_reason"] == reason
    assert values["safety_officer_id"] == OFFICER_ID
    assert values["safety_decided_at"]
    assert values["safety_review_history"] == [
        {
            "review_number": 1,
            "decision": decision,
            "reason": reason,
            "safety_officer_id": OFFICER_ID,
            "decided_at": values["safety_decided_at"],
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "rejected", "reason": "   ", "safety_officer_id": OFFICER_ID},
        {"decision": "changes_requested", "safety_officer_id": OFFICER_ID},
        {"decision": "approved", "reason": "Not allowed", "safety_officer_id": OFFICER_ID},
        {"decision": "unsafe", "reason": "No", "safety_officer_id": OFFICER_ID},
    ],
)
def test_invalid_safety_decisions_are_rejected_before_storage(client, db, payload):
    response = client.post(
        f"/internal/events/safety-review/{EVENT_ID}/decision", json=payload
    )

    assert response.status_code == 422
    db.schema.return_value.table.return_value.update.assert_not_called()


def test_missing_event_is_404_and_stale_event_is_409_without_update(client, db):
    _event_select(db, [])
    missing = client.post(
        f"/internal/events/safety-review/{EVENT_ID}/decision",
        json={"decision": "approved", "safety_officer_id": OFFICER_ID, "expected_event_updated_at": REVIEW_UPDATED_AT},
    )
    assert missing.status_code == 404
    db.schema.return_value.table.return_value.update.assert_not_called()

    _event_select(db, [_reviewable(status="confirmed", safety_decision="approved")])
    stale = client.post(
        f"/internal/events/safety-review/{EVENT_ID}/decision",
        json={"decision": "approved", "safety_officer_id": OFFICER_ID, "expected_event_updated_at": REVIEW_UPDATED_AT},
    )
    assert stale.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()


def test_empty_conditional_update_reports_concurrent_decision_without_overwrite(client, db):
    _event_select(db, [_reviewable()])
    operation = _decision_update(db, [])

    response = client.post(
        f"/internal/events/safety-review/{EVENT_ID}/decision",
        json={"decision": "approved", "safety_officer_id": OFFICER_ID, "expected_event_updated_at": REVIEW_UPDATED_AT},
    )

    assert response.status_code == 409
    assert "already" in response.json()["detail"].lower()
    operation.execute.assert_called_once()


def test_old_safety_review_cannot_decide_new_event_version(client, db):
    _event_select(db, [_reviewable(updated_at="2026-10-27T10:00:00Z")])

    response = client.post(
        f"/internal/events/safety-review/{EVENT_ID}/decision",
        json={"decision": "approved", "safety_officer_id": OFFICER_ID,
              "expected_event_updated_at": REVIEW_UPDATED_AT},
    )

    assert response.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()
