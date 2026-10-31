"""S-89: the assigned Coordinator cancels an event no alternative venue could
be found for. TC-EVENTS-208..213.

Only the event changes here; the event_requests composite checks a booking
is affected, releases the bookings and notifies.
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
    history_table,
    on_owned_select,
)

URL = f"/events/{EVENT_ID}/coordinator-cancellation"
REASON = "Hall A is closed for repairs and no other hall fits 120 people that evening."
CANCELLED_FIELDS = {
    "status", "coordinator_cancellation_reason", "coordinator_cancelled_by", "coordinator_cancelled_at",
}
DECIDED_FIELDS = {
    "cancellation_decision", "cancellation_decision_reason",
    "cancellation_decided_by", "cancellation_decided_at",
}
REQUESTED = {
    "cancellation_reason": "Speaker unavailable",
    "cancellation_requested_at": "2026-10-30T09:00:00+00:00",
    "cancellation_requested_by": ORGANISER_ID,
}


def _event(status="planning", **changes):
    values = {
        "status": status,
        "assigned_coordinator_id": COORDINATOR_A,
        "name": "Alumni networking evening",
        "start_date": "2026-11-20",
        "start_time": "18:00:00",
        "end_date": "2026-11-20",
        "end_time": "21:00:00",
        "expected_attendance": 120,
        "submitted_at": "2026-10-01T00:00:00Z",
    }
    if status not in ("draft", "submitted", "under_review"):
        values.update(decision="approved", decided_at="2026-10-02T00:00:00Z")
    values.update(changes)
    return event_row(**values)


def _cancelled(**changes):
    return _event(
        "cancelled",
        coordinator_cancellation_reason=REASON,
        coordinator_cancelled_by=COORDINATOR_A,
        coordinator_cancelled_at="2026-11-01T06:30:00+00:00",
        **changes,
    )


def _coordinator(client, auth, coordinator_id=COORDINATOR_A):
    authenticate(client, auth, fake_user(coordinator_id, "event_coordinator"))


def _update(db):
    return db.schema.return_value.table.return_value.update


def _guarded(db):
    # .update().eq(id).eq(assigned_coordinator_id).in_(status, cancellable)
    return _update(db).return_value.eq.return_value.eq.return_value.in_.return_value


def _without_pending_request(db, rows):
    _guarded(db).or_.return_value.execute.return_value = SimpleNamespace(data=rows)


def _with_pending_request(db, rows):
    guard = _guarded(db).not_.is_.return_value.is_.return_value
    guard.execute.return_value = SimpleNamespace(data=rows)


# --- TC-EVENTS-208 ---------------------------------------------------------
def test_the_assigned_coordinator_cancels_with_a_recorded_reason(client, db, auth):
    _coordinator(client, auth)
    on_owned_select(db, [_event()])
    _without_pending_request(db, [_cancelled()])

    response = client.post(URL, json={"reason": f"  {REASON}  "})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["coordinator_cancellation_reason"] == REASON
    assert body["coordinator_cancelled_by"] == COORDINATOR_A
    assert body["coordinator_cancelled_at"] is not None

    written = _update(db).call_args.args[0]
    assert set(written) == CANCELLED_FIELDS
    assert written["status"] == "cancelled"
    assert written["coordinator_cancellation_reason"] == REASON
    assert written["coordinator_cancelled_by"] == COORDINATOR_A
    assert written["coordinator_cancelled_at"].startswith("20")

    chain = _update(db).return_value
    assert chain.eq.call_args.args == ("id", EVENT_ID)
    assert chain.eq.return_value.eq.call_args.args == ("assigned_coordinator_id", COORDINATOR_A)
    column, statuses = chain.eq.return_value.eq.return_value.in_.call_args.args
    assert column == "status" and "planning" in statuses and "cancelled" not in statuses

    history_table(db).insert.assert_called_once()
    entry = history_table(db).insert.call_args.args[0]
    assert entry["event_id"] == EVENT_ID
    assert entry["actor_id"] == COORDINATOR_A
    assert entry["actor_role"] == "event_coordinator"
    assert entry["category"] == "review"
    assert entry["action"] == "event_cancelled_by_coordinator"
    assert entry["details"] == {"reason": REASON}


# --- TC-EVENTS-209 ---------------------------------------------------------
@pytest.mark.parametrize(
    "body",
    [{}, {"reason": "   "}, {"reason": "x" * 1001}, {"reason": REASON, "cancelled_by": "someone"}],
    ids=["missing", "blank", "too-long", "extra-field"],
)
def test_a_missing_blank_or_over_long_reason_is_refused(client, db, auth, body):
    _coordinator(client, auth)

    response = client.post(URL, json=body)

    assert response.status_code == 422
    _update(db).assert_not_called()
    history_table(db).insert.assert_not_called()


# --- TC-EVENTS-210 ---------------------------------------------------------
def test_a_pending_organiser_request_is_closed_as_approved(client, db, auth):
    _coordinator(client, auth)
    on_owned_select(db, [_event(**REQUESTED)])
    _with_pending_request(db, [_cancelled(
        **REQUESTED,
        cancellation_decision="approved",
        cancellation_decided_by=COORDINATOR_A,
        cancellation_decided_at="2026-11-01T06:30:00+00:00",
    )])

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cancellation_decision"] == "approved"
    assert body["cancellation_reason"] == "Speaker unavailable"
    assert body["coordinator_cancellation_reason"] == REASON

    written = _update(db).call_args.args[0]
    assert set(written) == CANCELLED_FIELDS | DECIDED_FIELDS
    assert "cancellation_reason" not in written
    assert written["cancellation_decision"] == "approved"
    assert written["cancellation_decision_reason"] is None
    assert written["cancellation_decided_by"] == COORDINATOR_A
    assert written["cancellation_decided_at"] == written["coordinator_cancelled_at"]
    guard = _guarded(db).not_.is_
    assert guard.call_args.args == ("cancellation_requested_at", "null")
    assert guard.return_value.is_.call_args.args == ("cancellation_decision", "null")


def test_a_declined_request_is_left_as_it_was(client, db, auth):
    declined = {
        **REQUESTED,
        "cancellation_decision": "declined",
        "cancellation_decision_reason": "Move the date instead",
        "cancellation_decided_by": COORDINATOR_A,
        "cancellation_decided_at": "2026-10-31T00:00:00+00:00",
    }
    _coordinator(client, auth)
    on_owned_select(db, [_event(**declined)])
    _without_pending_request(db, [_cancelled(**declined)])

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 200, response.text
    assert set(_update(db).call_args.args[0]) == CANCELLED_FIELDS
    assert _guarded(db).or_.call_args.args == (
        "cancellation_requested_at.is.null,cancellation_decision.not.is.null",
    )


def test_a_request_sent_meanwhile_makes_the_write_match_nothing(client, db, auth):
    _coordinator(client, auth)
    on_owned_select(db, [_event()])
    _without_pending_request(db, [])

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "This event changed while you were cancelling it. Reload it and try again."
    )
    history_table(db).insert.assert_not_called()


# --- TC-EVENTS-211 ---------------------------------------------------------
def test_a_coordinator_not_assigned_gets_404(client, db, auth):
    _coordinator(client, auth, COORDINATOR_B)
    on_owned_select(db, [])

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    lookup = db.schema.return_value.table.return_value.select.return_value
    assert lookup.eq.return_value.eq.call_args.args == ("assigned_coordinator_id", COORDINATOR_B)
    _update(db).assert_not_called()


@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "technical_support", "attendee"])
def test_other_roles_are_403(client, db, auth, role):
    authenticate(client, auth, fake_user(ORGANISER_ID, role))

    assert client.post(URL, json={"reason": REASON}).status_code == 403
    db.schema.assert_not_called()


def test_no_session_is_401(client, db):
    assert client.post(URL, json={"reason": REASON}).status_code == 401
    db.schema.assert_not_called()


# --- TC-EVENTS-212 ---------------------------------------------------------
@pytest.mark.parametrize(
    "event",
    [
        _event("draft", submitted_at=None),
        _event("rejected"),
        _event("returned"),
        _event("safety_rejected"),
        _event("cancelled", **REQUESTED, cancellation_decision="approved",
               cancellation_decided_by=COORDINATOR_A, cancellation_decided_at="2026-10-31T00:00:00Z"),
    ],
    ids=["draft", "rejected", "returned", "safety_rejected", "cancelled-by-s61"],
)
def test_an_event_that_is_not_live_cannot_be_cancelled(client, db, auth, event):
    _coordinator(client, auth)
    on_owned_select(db, [event])

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 409
    assert response.json()["detail"] == "This event can't be cancelled from its current status."
    _update(db).assert_not_called()
    history_table(db).insert.assert_not_called()


# --- TC-EVENTS-213 ---------------------------------------------------------
def test_cancelling_again_is_a_no_op_so_a_failed_release_can_be_retried(client, db, auth):
    _coordinator(client, auth)
    on_owned_select(db, [_cancelled()])

    response = client.post(URL, json={"reason": "A different reason"})

    assert response.status_code == 200, response.text
    assert response.json()["coordinator_cancellation_reason"] == REASON
    _update(db).assert_not_called()
    history_table(db).insert.assert_not_called()
