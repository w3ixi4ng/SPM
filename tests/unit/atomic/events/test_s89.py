"""S-89: the assigned Coordinator cancels an event venue unavailability left
without an alternative.

TC-EVENTS-400..411. Only the event and its history change here; the
event_requests composite verifies the unavailability, closes and releases the
bookings and notifies.
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
)

URL = f"/internal/events/{EVENT_ID}/venue-cancellation"
COMPLETE_URL = f"{URL}/complete"
AFFECTED = "b1b1b1b1-b1b1-4b1b-8b1b-b1b1b1b1b1b1"
REASON = "Hall A is closed for structural repairs on the event date"
ALTERNATIVES = "Discussed Hall B and Seminar Room 3 with the Organiser on 30 Oct; neither fits 180 guests"
BODY = {
    "reason": REASON,
    "alternatives_considered": ALTERNATIVES,
    "expected_version": 7,
    "affected_booking_ids": [AFFECTED],
}
OPEN_STATUSES = (
    "planning", "pending_safety_check", "confirmed", "preparation", "safety_changes_requested",
)
CANCELLED = {
    "status": "cancelled",
    "venue_cancellation_previous_status": "confirmed",
    "venue_cancellation_reason": REASON,
    "venue_cancellation_alternatives": ALTERNATIVES,
    "venue_cancellation_booking_ids": [AFFECTED],
    "venue_cancelled_by": COORDINATOR_A,
    "venue_cancelled_at": "2026-11-01T02:00:00Z",
}


def _event(status="confirmed", **changes):
    values = {
        "status": status,
        "assigned_coordinator_id": COORDINATOR_A,
        "name": "Alumni networking evening",
        "start_date": "2026-11-20",
        "start_time": "09:00:00",
        "end_date": "2026-11-20",
        "end_time": "21:00:00",
        "expected_attendance": 180,
        "edit_version": 7,
        "submitted_at": "2026-10-01T00:00:00Z",
    }
    if status not in ("draft", "submitted", "under_review"):
        values.update(decision="approved", decided_at="2026-10-02T00:00:00Z")
    values.update(changes)
    return event_row(**values)


def _coordinator(client, auth, coordinator_id=COORDINATOR_A, role="event_coordinator"):
    authenticate(client, auth, fake_user(coordinator_id, role))


def _table(db):
    return db.schema.return_value.table.return_value


def _assigned(db, *reads):
    """Each read of _get_assigned_event in turn: .select().eq(id).eq(coordinator)."""
    operation = _table(db).select.return_value.eq.return_value.eq.return_value
    operation.execute.side_effect = [SimpleNamespace(data=rows) for rows in reads]
    return operation


def _guarded(db, rows=None, error=None):
    # .update().eq(id).eq(coordinator).eq(edit_version).in_(status).is_(cancelled_at).or_(request)
    operation = (
        _table(db).update.return_value.eq.return_value.eq.return_value.eq.return_value
        .in_.return_value.is_.return_value.or_.return_value
    )
    if error is not None:
        operation.execute.side_effect = error
    else:
        operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def _complete_update(db, rows):
    # .update().eq(id).eq(coordinator).is_(completed_at, null)
    operation = _table(db).update.return_value.eq.return_value.eq.return_value.is_.return_value
    operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def _history(db):
    return history_table(db).insert


# --- TC-EVENTS-400 -------------------------------------------------------------
def test_the_assigned_coordinators_cancellation_is_recorded_on_the_event(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event()])
    _guarded(db, [_event(**CANCELLED, edit_version=8)])

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    values = _table(db).update.call_args.args[0]
    assert values["status"] == "cancelled"
    assert values["venue_cancellation_reason"] == REASON
    assert values["venue_cancellation_alternatives"] == ALTERNATIVES
    assert values["venue_cancellation_booking_ids"] == [AFFECTED]
    assert values["venue_cancelled_by"] == COORDINATOR_A
    assert values["venue_cancelled_at"]
    assert values["edit_version"] == 8
    assert values["venue_cancellation_previous_status"] == "confirmed"
    assert not any(key.startswith("cancellation_") for key in values)

    update = _table(db).update.return_value
    assert update.eq.call_args.args == ("id", EVENT_ID)
    assert update.eq.return_value.eq.call_args.args == ("assigned_coordinator_id", COORDINATOR_A)
    assert update.eq.return_value.eq.return_value.eq.call_args.args == ("edit_version", 7)
    status_filter = update.eq.return_value.eq.return_value.eq.return_value.in_
    assert status_filter.call_args.args == ("status", OPEN_STATUSES)
    assert status_filter.return_value.is_.call_args.args == ("venue_cancelled_at", "null")

    # The S-82 entry is its own, retryable step (TC-EVENTS-410).
    _history(db).assert_not_called()


# --- TC-EVENTS-401 -------------------------------------------------------------
@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_a_browser_without_the_service_token_cannot_cancel(client, db, auth, token):
    _coordinator(client, auth)
    if token is None:
        del client.headers["X-Assignment-Service-Token"]
    else:
        client.headers["X-Assignment-Service-Token"] = token

    response = client.post(URL, json=BODY)

    assert response.status_code == 403
    _table(db).update.assert_not_called()
    _history(db).assert_not_called()


def test_no_session_is_not_authenticated(client, db, auth):
    response = client.post(URL, json=BODY)

    assert response.status_code == 401
    _table(db).update.assert_not_called()


@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "event_coordinator_lead"])
def test_other_roles_cannot_cancel(client, db, auth, role):
    _coordinator(client, auth, ORGANISER_ID, role)

    response = client.post(URL, json=BODY)

    assert response.status_code == 403
    _table(db).update.assert_not_called()


def test_a_coordinator_not_assigned_to_the_event_gets_404(client, db, auth):
    _coordinator(client, auth, COORDINATOR_B)
    _assigned(db, [])

    response = client.post(URL, json=BODY)

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    _table(db).update.assert_not_called()
    _history(db).assert_not_called()


# --- TC-EVENTS-402 -------------------------------------------------------------
@pytest.mark.parametrize(
    "changes",
    [
        {"reason": "   "},
        {"reason": None},
        {"alternatives_considered": ""},
        {"reason": "x" * 1001},
        {"alternatives_considered": "x" * 1001},
        {"expected_version": None},
        {"expected_version": -1},
        {"affected_booking_ids": []},
        {"status": "cancelled"},
    ],
)
def test_the_reason_and_alternatives_must_both_be_recorded(client, db, auth, changes):
    _coordinator(client, auth)
    body = {**BODY, **changes}
    body = {key: value for key, value in body.items() if value is not None}

    response = client.post(URL, json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == "Please check the details you entered"
    _table(db).update.assert_not_called()
    _history(db).assert_not_called()


def test_values_are_trimmed_and_1000_characters_are_accepted(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event()])
    _guarded(db, [_event(**CANCELLED, edit_version=8)])

    response = client.post(URL, json={
        **BODY, "reason": f"  {'r' * 1000}  ", "alternatives_considered": f"\n{'a' * 1000}\n",
    })

    assert response.status_code == 200
    values = _table(db).update.call_args.args[0]
    assert values["venue_cancellation_reason"] == "r" * 1000
    assert values["venue_cancellation_alternatives"] == "a" * 1000


# --- TC-EVENTS-403 -------------------------------------------------------------
@pytest.mark.parametrize("event_status", OPEN_STATUSES)
def test_an_event_whose_venues_can_still_change_is_cancellable(client, db, auth, event_status):
    _coordinator(client, auth)
    _assigned(db, [_event(event_status)])
    _guarded(db, [_event(**CANCELLED, edit_version=8)])

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    assert _table(db).update.call_args.args[0]["venue_cancellation_previous_status"] == event_status


@pytest.mark.parametrize(
    "event_status", ["draft", "submitted", "under_review", "returned", "rejected", "safety_rejected"]
)
def test_any_other_status_is_refused(client, db, auth, event_status):
    _coordinator(client, auth)
    _assigned(db, [_event(event_status)])

    response = client.post(URL, json=BODY)

    assert response.status_code == 409
    assert response.json()["detail"] == "This event can't be cancelled from its current status."
    _table(db).update.assert_not_called()


# --- TC-EVENTS-404 -------------------------------------------------------------
def test_a_waiting_organiser_request_is_decided_through_s61_instead(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(
        cancellation_reason="Speaker withdrew",
        cancellation_requested_at="2026-10-30T00:00:00Z",
        cancellation_requested_by=ORGANISER_ID,
    )])

    response = client.post(URL, json=BODY)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "The Organiser has asked to cancel this event. Approve their request instead."
    )
    _table(db).update.assert_not_called()


def test_a_declined_organiser_request_does_not_stand_in_the_way(client, db, auth):
    _coordinator(client, auth)
    declined = {
        "cancellation_reason": "Speaker withdrew",
        "cancellation_requested_at": "2026-10-30T00:00:00Z",
        "cancellation_requested_by": ORGANISER_ID,
        "cancellation_decision": "declined",
        "cancellation_decision_reason": "Speaker replaced",
        "cancellation_decided_by": COORDINATOR_A,
        "cancellation_decided_at": "2026-10-31T00:00:00Z",
    }
    _assigned(db, [_event(**declined)])
    guarded = _guarded(db, [_event(**declined, **CANCELLED, edit_version=8)])

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    values = _table(db).update.call_args.args[0]
    assert not any(key.startswith("cancellation_") for key in values)
    # The same rule in the write itself, so a request arriving after the read
    # makes it match nothing.
    or_filter = (
        _table(db).update.return_value.eq.return_value.eq.return_value.eq.return_value
        .in_.return_value.is_.return_value.or_
    )
    assert or_filter.call_args.args == (
        "cancellation_requested_at.is.null,cancellation_decision.not.is.null",
    )
    assert guarded.execute.called


# --- TC-EVENTS-405 -------------------------------------------------------------
def test_a_screen_older_than_the_event_cannot_cancel(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(edit_version=8)])

    response = client.post(URL, json=BODY)

    assert response.status_code == 409
    assert response.json()["detail"] == "This event changed since you opened it. Reload and try again."
    _table(db).update.assert_not_called()
    _history(db).assert_not_called()


def test_a_write_that_loses_the_race_is_refused_without_history(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event()], [_event(edit_version=8)])
    _guarded(db, [])

    response = client.post(URL, json=BODY)

    assert response.status_code == 409
    assert response.json()["detail"] == "This event changed since you opened it. Reload and try again."
    _history(db).assert_not_called()


def test_losing_to_an_organiser_request_says_so(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event()], [_event(
        cancellation_reason="Speaker withdrew",
        cancellation_requested_at="2026-10-30T00:00:00Z",
        cancellation_requested_by=ORGANISER_ID,
    )])
    _guarded(db, [])

    response = client.post(URL, json=BODY)

    assert response.status_code == 409
    assert "Approve their request instead" in response.json()["detail"]
    _history(db).assert_not_called()


# --- TC-EVENTS-406 -------------------------------------------------------------
def test_repeating_a_cancellation_resumes_it_without_rewriting(client, db, auth):
    _coordinator(client, auth)
    stored = _event(**CANCELLED, edit_version=8)
    _assigned(db, [stored])

    response = client.post(URL, json={**BODY, "reason": "A different reason", "expected_version": 3})

    assert response.status_code == 200
    assert response.json()["venue_cancellation_reason"] == REASON
    _table(db).update.assert_not_called()
    _history(db).assert_not_called()


def test_an_event_cancelled_through_s61_is_final(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(
        "cancelled",
        cancellation_reason="Speaker withdrew",
        cancellation_requested_at="2026-10-30T00:00:00Z",
        cancellation_requested_by=ORGANISER_ID,
        cancellation_decision="approved",
        cancellation_decided_by=COORDINATOR_A,
        cancellation_decided_at="2026-10-31T00:00:00Z",
    )])

    response = client.post(URL, json=BODY)

    assert response.status_code == 409
    assert response.json()["detail"] == "This event is already cancelled."
    _table(db).update.assert_not_called()


# --- TC-EVENTS-407 -------------------------------------------------------------
def _recorded(db, rows):
    # .select("id").eq(event_id).eq(action) on event_history
    lookup = history_table(db).select.return_value.eq.return_value.eq.return_value
    lookup.execute.return_value = SimpleNamespace(data=rows)
    return history_table(db).select


def test_completion_is_marked_once(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(**CANCELLED)])
    _recorded(db, [{"id": 1}])
    _complete_update(db, [_event(**CANCELLED, venue_cancellation_completed_at="2026-11-01T02:01:00Z")])

    response = client.post(COMPLETE_URL)

    assert response.status_code == 200
    assert response.json()["venue_cancellation_completed_at"]
    assert set(_table(db).update.call_args.args[0]) == {"venue_cancellation_completed_at"}
    filtered = _table(db).update.return_value.eq.return_value.eq.return_value.is_
    assert filtered.call_args.args == ("venue_cancellation_completed_at", "null")


def test_completing_again_changes_nothing(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(**CANCELLED, venue_cancellation_completed_at="2026-11-01T02:01:00Z")])

    response = client.post(COMPLETE_URL)

    assert response.status_code == 200
    _table(db).update.assert_not_called()


def test_only_a_venue_cancellation_can_be_completed(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event()])

    response = client.post(COMPLETE_URL)

    assert response.status_code == 409
    assert response.json()["detail"] == "This event has not been cancelled for venue unavailability."
    _table(db).update.assert_not_called()


def test_completion_needs_the_service_token(client, db, auth):
    _coordinator(client, auth)
    del client.headers["X-Assignment-Service-Token"]

    response = client.post(COMPLETE_URL)

    assert response.status_code == 403
    _table(db).update.assert_not_called()


# --- TC-EVENTS-408 -------------------------------------------------------------
def test_a_cancelled_event_stays_closed_to_coordinator_edits(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(**CANCELLED, edit_version=8)])

    response = client.patch(
        f"/events/assigned/{EVENT_ID}", json={"expected_version": 8, "internal_notes": "Late note"},
    )

    assert response.status_code == 409
    _table(db).update.assert_not_called()


def test_a_cancelled_event_stays_closed_to_organiser_requests(client, db, auth):
    authenticate(client, auth, fake_user(ORGANISER_ID, "event_organiser"))
    owned = _table(db).select.return_value.eq.return_value.eq.return_value
    owned.execute.return_value = SimpleNamespace(data=[_event(**CANCELLED, edit_version=8)])

    cancellation = client.post(
        f"/events/{EVENT_ID}/cancellation-request", json={"reason": "No longer needed"},
    )
    accepted = {
        "start_date": "2026-11-20", "start_time": "09:00:00",
        "end_date": "2026-11-20", "end_time": "21:00:00",
        "expected_attendance": 180, "venue": "Main Hall",
        "special_requirements": None, "room_layout": "theatre",
        "required_facilities": [], "required_accessibility": [],
    }
    change = client.post(
        f"/events/{EVENT_ID}/change-request/internal",
        json={
            "expected_event_updated_at": "2026-09-14T00:00:00Z",
            "proposed_values": {**accepted, "expected_attendance": 150},
            "accepted_equipment": [], "proposed_equipment": [],
        },
    )

    assert cancellation.status_code == 409
    assert change.status_code == 409
    assert change.json()["detail"] == "This event cannot receive a change request"
    _table(db).update.assert_not_called()


# --- TC-EVENTS-409 -------------------------------------------------------------
def test_a_storage_failure_is_reported_never_a_cancellation(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event()])
    _guarded(db, error=RuntimeError("connection reset"))

    response = client.post(URL, json=BODY)

    assert response.status_code == 500
    assert response.json()["detail"] == "Event storage unavailable"
    _history(db).assert_not_called()


def test_completion_waits_for_the_history_entry(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(**CANCELLED)])
    _recorded(db, [])

    response = client.post(COMPLETE_URL)

    assert response.status_code == 409
    assert response.json()["detail"] == "The cancellation has not been recorded in the event history yet."
    _table(db).update.assert_not_called()


# --- TC-EVENTS-410 -------------------------------------------------------------
HISTORY_URL = f"{URL}/history"


def test_the_history_entry_is_built_from_the_stored_record(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(**CANCELLED)])
    _recorded(db, [])
    history_table(db).insert.return_value.execute.return_value = SimpleNamespace(data=[{"id": 7}])

    response = client.post(HISTORY_URL)

    assert response.status_code == 200
    assert response.json() == {"recorded": True}
    entry = _history(db).call_args.args[0]
    assert entry == {
        "event_id": EVENT_ID,
        "actor_id": COORDINATOR_A,
        "actor_role": "event_coordinator",
        "category": "review",
        "action": "cancelled_venue_unavailable",
        "details": {
            "reason": REASON,
            "alternatives_considered": ALTERNATIVES,
            "previous_status": "confirmed",
            "affected_booking_ids": [AFFECTED],
        },
        "occurred_at": "2026-11-01T02:00:00Z",
    }


def test_recording_again_never_writes_a_second_entry(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(**CANCELLED)])
    _recorded(db, [{"id": 7}])

    response = client.post(HISTORY_URL)

    assert response.status_code == 200
    _history(db).assert_not_called()


class Duplicate(Exception):
    code = "23505"


def test_a_concurrent_duplicate_counts_as_recorded(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(**CANCELLED)])
    _recorded(db, [])
    history_table(db).insert.return_value.execute.side_effect = Duplicate()

    response = client.post(HISTORY_URL)

    assert response.status_code == 200
    assert response.json() == {"recorded": True}


def test_a_failed_history_write_is_reported(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event(**CANCELLED)])
    _recorded(db, [])
    history_table(db).insert.return_value.execute.side_effect = RuntimeError("connection reset")

    response = client.post(HISTORY_URL)

    assert response.status_code == 500
    assert response.json()["detail"] == "Event storage unavailable"


# --- TC-EVENTS-411 -------------------------------------------------------------
def test_history_is_only_for_a_venue_cancellation_and_the_composite(client, db, auth):
    _coordinator(client, auth)
    _assigned(db, [_event()])

    not_cancelled = client.post(HISTORY_URL)
    del client.headers["X-Assignment-Service-Token"]
    no_token = client.post(HISTORY_URL)

    assert not_cancelled.status_code == 409
    assert not_cancelled.json()["detail"] == "This event has not been cancelled for venue unavailability."
    assert no_token.status_code == 403
    _history(db).assert_not_called()
