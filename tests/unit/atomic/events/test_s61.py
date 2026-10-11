"""S-61: the assigned Coordinator decides on a cancellation request.

TC-EVENTS-131..138. Only the event changes here; the event_requests
composite releases its venue bookings.
"""

from types import SimpleNamespace

import pytest

from .conftest import (
    COORDINATOR_A,
    COORDINATOR_B,
    EVENT_ID,
    ORGANISER_ID,
    authenticate,
    event_row,
    fake_user,
    on_owned_select,
)

URL = f"/events/{EVENT_ID}/cancellation-decision"
REQUESTED = {
    "cancellation_reason": "Keynote speaker withdrew",
    "cancellation_requested_at": "2026-10-11T09:00:00+00:00",
    "cancellation_requested_by": ORGANISER_ID,
}
DECIDED_FIELDS = {
    "cancellation_decision", "cancellation_decision_reason",
    "cancellation_decided_by", "cancellation_decided_at",
}


def _event(status="planning", **changes):
    values = {
        "status": status,
        "assigned_coordinator_id": COORDINATOR_A,
        "name": "Alumni networking evening",
        "purpose": "Reconnect graduates with faculty",
        "start_date": "2026-11-12",
        "start_time": "09:00:00",
        "end_date": "2026-11-12",
        "end_time": "18:00:00",
        "expected_attendance": 120,
        "submitted_at": "2026-10-01T00:00:00Z",
        **REQUESTED,
    }
    if status not in ("submitted", "under_review", "cancelled"):
        values.update(decision="approved", decided_at="2026-10-02T00:00:00Z")
    values.update(changes)
    return event_row(**values)


def _coordinator(client, auth, coordinator_id=COORDINATOR_A):
    authenticate(client, auth, fake_user(coordinator_id, "event_coordinator"))


def _assigned(db, rows):
    # _get_assigned_event: .select().eq(id).eq(assigned_coordinator_id) -- the
    # same chain shape as the organiser's owned-event lookup.
    on_owned_select(db, rows)


def _guarded_update(db, rows=None, error=None):
    # .update().eq(id).eq(assigned_coordinator_id)
    #   .not_.is_(requested_at, null).is_(decision, null)
    operation = (
        db.schema.return_value.table.return_value.update.return_value
        .eq.return_value.eq.return_value.not_.is_.return_value.is_.return_value
    )
    if error is not None:
        operation.execute.side_effect = error
    else:
        operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def _update(db):
    return db.schema.return_value.table.return_value.update


# --- TC-EVENTS-131 ---------------------------------------------------------
@pytest.mark.parametrize(
    "event_status",
    ["submitted", "under_review", "planning", "confirmed", "preparation", "safety_changes_requested"],
)
def test_the_assigned_coordinator_approves_a_cancellation_request(client, db, auth, event_status):
    _coordinator(client, auth)
    _assigned(db, [_event(event_status)])
    _guarded_update(db, [_event(
        "cancelled",
        cancellation_decision="approved",
        cancellation_decided_by=COORDINATOR_A,
        cancellation_decided_at="2026-10-11T10:00:00+00:00",
    )])

    response = client.post(URL, json={"decision": "approved"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["cancellation_decision"] == "approved"
    assert body["cancellation_decided_by"] == COORDINATOR_A
    assert body["cancellation_decided_at"] is not None
    assert body["cancellation_decision_reason"] is None

    written = _update(db).call_args.args[0]
    assert set(written) == DECIDED_FIELDS | {"status"}
    assert written["status"] == "cancelled"
    assert written["cancellation_decision"] == "approved"
    assert written["cancellation_decision_reason"] is None
    assert written["cancellation_decided_by"] == COORDINATOR_A
    assert written["cancellation_decided_at"].startswith("20")

    chain = _update(db).return_value
    assert chain.eq.call_args.args == ("id", EVENT_ID)
    assert chain.eq.return_value.eq.call_args.args == ("assigned_coordinator_id", COORDINATOR_A)
    requested_guard = chain.eq.return_value.eq.return_value.not_.is_
    assert requested_guard.call_args.args == ("cancellation_requested_at", "null")
    assert requested_guard.return_value.is_.call_args.args == ("cancellation_decision", "null")


# --- TC-EVENTS-132 ---------------------------------------------------------
def test_the_assigned_coordinator_declines_with_a_reason(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event()])
    reason = "Venue is non-refundable; move the date instead"
    _guarded_update(db, [_event(
        cancellation_decision="declined",
        cancellation_decision_reason=reason,
        cancellation_decided_by=COORDINATOR_A,
        cancellation_decided_at="2026-10-11T10:00:00+00:00",
    )])

    response = client.post(URL, json={"decision": "declined", "reason": f"  {reason}  "})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "planning"
    assert body["cancellation_decision"] == "declined"
    assert body["cancellation_decision_reason"] == reason
    written = _update(db).call_args.args[0]
    assert set(written) == DECIDED_FIELDS
    assert "status" not in written
    assert written["cancellation_decision_reason"] == reason


# --- TC-EVENTS-133 ---------------------------------------------------------
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"decision": "maybe"},
        {"decision": "declined"},
        {"decision": "declined", "reason": "   "},
        {"decision": "declined", "reason": "x" * 1001},
        {"decision": "approved", "reason": "ok"},
        {"decision": "approved", "status": "draft"},
    ],
    ids=["empty", "unknown", "decline-no-reason", "decline-blank", "decline-too-long",
         "approve-with-reason", "extra-field"],
)
def test_a_decision_with_a_missing_or_wrong_field_is_refused(client, db, auth, body):
    _coordinator(client, auth)

    response = client.post(URL, json=body)

    assert response.status_code == 422
    db.schema.assert_not_called()


# --- TC-EVENTS-134 ---------------------------------------------------------
def test_no_session_is_401(client, db):
    assert client.post(URL, json={"decision": "approved"}).status_code == 401
    db.schema.assert_not_called()


@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "technical_support", "attendee"])
def test_other_roles_are_403(client, db, auth, role):
    authenticate(client, auth, fake_user(ORGANISER_ID, role))

    assert client.post(URL, json={"decision": "approved"}).status_code == 403
    db.schema.assert_not_called()


@pytest.mark.parametrize("coordinator_id", [COORDINATOR_B, COORDINATOR_A], ids=["not-assigned", "missing"])
def test_an_unassigned_or_missing_event_is_404(client, db, auth, coordinator_id):
    _coordinator(client, auth, coordinator_id)
    _assigned(db, [])

    response = client.post(URL, json={"decision": "approved"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    lookup = db.schema.return_value.table.return_value.select.return_value
    assert lookup.eq.return_value.eq.call_args.args == ("assigned_coordinator_id", coordinator_id)
    _update(db).assert_not_called()


# --- TC-EVENTS-135 ---------------------------------------------------------
@pytest.mark.parametrize(
    ("event", "decisions", "detail"),
    [
        (
            {"cancellation_reason": None, "cancellation_requested_at": None, "cancellation_requested_by": None},
            [{"decision": "approved"}, {"decision": "declined", "reason": "No"}],
            "There is no cancellation request to decide for this event.",
        ),
        (
            {"cancellation_decision": "declined", "cancellation_decision_reason": "No",
             "cancellation_decided_by": COORDINATOR_A, "cancellation_decided_at": "2026-10-11T10:00:00Z"},
            [{"decision": "approved"}, {"decision": "declined", "reason": "No"}],
            "This cancellation request has already been decided.",
        ),
        (
            {"status": "cancelled", "cancellation_decision": "approved",
             "cancellation_decided_by": COORDINATOR_A, "cancellation_decided_at": "2026-10-11T10:00:00Z"},
            [{"decision": "declined", "reason": "No"}],
            "This cancellation request has already been decided.",
        ),
    ],
    ids=["no-request", "already-declined", "already-approved"],
)
def test_there_must_be_a_pending_request_to_decide(client, db, auth, event, decisions, detail):
    _coordinator(client, auth)
    _assigned(db, [_event(**event)])

    for decision in decisions:
        response = client.post(URL, json=decision)
        assert response.status_code == 409, decision
        assert response.json()["detail"] == detail
    _update(db).assert_not_called()


# --- TC-EVENTS-136 ---------------------------------------------------------
def test_approving_an_already_approved_request_again_changes_nothing(client, db, auth):
    _coordinator(client, auth)
    approved = _event(
        "cancelled",
        cancellation_decision="approved",
        cancellation_decided_by=COORDINATOR_A,
        cancellation_decided_at="2026-10-11T10:00:00+00:00",
    )
    _assigned(db, [approved])

    response = client.post(URL, json={"decision": "approved"})

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancellation_decision"] == "approved"
    _update(db).assert_not_called()


# --- TC-EVENTS-137 ---------------------------------------------------------
def test_a_decision_that_loses_a_race_is_refused_without_overwriting(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event()])
    _guarded_update(db, [])

    response = client.post(URL, json={"decision": "approved"})

    assert response.status_code == 409
    assert response.json()["detail"] == "This cancellation request has already been decided."
    _update(db).assert_called_once()


# --- TC-EVENTS-138 ---------------------------------------------------------
def _request_guard(db, rows):
    operation = (
        db.schema.return_value.table.return_value.update.return_value
        .eq.return_value.eq.return_value.in_.return_value.or_.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)


def test_after_a_decline_the_organiser_can_request_again(client, db, auth):
    authenticate(client, auth)
    declined = _event(
        cancellation_decision="declined",
        cancellation_decision_reason="Move the date instead",
        cancellation_decided_by=COORDINATOR_A,
        cancellation_decided_at="2026-10-11T10:00:00+00:00",
    )
    on_owned_select(db, [declined])
    _request_guard(db, [_event(cancellation_reason="Speaker still unavailable")])

    response = client.post(
        f"/events/{EVENT_ID}/cancellation-request", json={"reason": "Speaker still unavailable"}
    )

    assert response.status_code == 200, response.text
    written = _update(db).call_args.args[0]
    assert written["cancellation_reason"] == "Speaker still unavailable"
    assert written["cancellation_requested_by"] == ORGANISER_ID
    assert all(written[field] is None for field in DECIDED_FIELDS)
    status_guard = _update(db).return_value.eq.return_value.eq.return_value.in_
    assert status_guard.return_value.or_.call_args.args == (
        "cancellation_requested_at.is.null,cancellation_decision.eq.declined",
    )


@pytest.mark.parametrize(
    ("event", "detail"),
    [
        ({}, "A cancellation request has already been sent for this event."),
        (
            {"status": "cancelled", "cancellation_decision": "approved",
             "cancellation_decided_by": COORDINATOR_A, "cancellation_decided_at": "2026-10-11T10:00:00Z"},
            "This event can't be cancelled from its current status.",
        ),
    ],
    ids=["pending", "approved"],
)
def test_a_pending_or_approved_request_still_blocks_another(client, db, auth, event, detail):
    authenticate(client, auth)
    on_owned_select(db, [_event(**event)])

    response = client.post(f"/events/{EVENT_ID}/cancellation-request", json={"reason": "Again"})

    assert response.status_code == 409
    assert response.json()["detail"] == detail
    _update(db).assert_not_called()
