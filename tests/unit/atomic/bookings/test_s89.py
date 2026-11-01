"""S-89: a cancelled event's bookings are released, not deleted, and closed
to new active bookings from before the event is cancelled.

TC-BOOKINGS-400..408. The release itself is one database function
(bookings.release_event_bookings) that closes the event and moves its
pending, held and confirmed bookings to `released` under the event's lock;
the statuses it touches and leaves alone are proven against real Postgres in
TC-BOOKINGS-450. Here: the route, its trust checks, and that a released
booking and a closed event stay closed on every write path.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import BOOKING, BOOKING_ID, app, booking_row, database_module, lookups, table

EVENT_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
COORDINATOR = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
STAFF = "55555555-5555-4555-8555-555555555555"
COOKIE = {"sb_access_token": "verified-token"}
URL = f"/internal/events/{EVENT_ID}/bookings/release"
EVENT_CLOSED = "This event is being cancelled, so its venue bookings can no longer change."
OPERATION = "0e0e0e0e-0e0e-4e0e-8e0e-0e0e0e0e0e0e"
RELEASE = {"reason": "event_cancelled", "operation_id": OPERATION}
RELEASED = {
    "status": "released",
    "released_at": "2026-11-01T02:00:00+00:00",
    "released_by": COORDINATOR,
    "release_reason": "event_cancelled",
}


class ClosedEvent(Exception):
    """What supabase-py raises when the closed-event trigger refuses a write."""

    code = "P0001"
    message = "event_bookings_closed"


@pytest.fixture
def signed_in():
    fake = MagicMock()
    app.dependency_overrides[database_module.get_auth] = lambda: fake

    def as_role(role, user_id=COORDINATOR):
        fake.auth.get_user.return_value.user = SimpleNamespace(id=user_id, app_metadata={"role": role})

    as_role("event_coordinator")
    yield as_role
    app.dependency_overrides.pop(database_module.get_auth, None)


def _rpc(db, rows=None, error=None):
    operation = db.schema.return_value.rpc.return_value
    if error is not None:
        operation.execute.side_effect = error
    else:
        operation.execute.return_value = SimpleNamespace(data=rows)
    return db.schema.return_value.rpc


def _release_calls(db):
    return [call for call in db.schema.return_value.rpc.call_args_list if call.args[0] == "release_event_bookings"]


# --- TC-BOOKINGS-400 -----------------------------------------------------------
def test_every_active_booking_hold_and_request_is_released(client, db, signed_in):
    ids = [f"{index}0000000-0000-4000-8000-000000000000" for index in range(1, 6)]
    rpc = _rpc(db, [booking_row(id=booking_id, **RELEASED) for booking_id in ids])

    response = client.post(URL, json=RELEASE, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json() == {"released": ids, "count": 5}
    rpc.assert_called_once_with("release_event_bookings", {
        "p_event_id": EVENT_ID,
        "p_operation_id": OPERATION,
        "p_released_by": COORDINATOR,
        "p_reason": "event_cancelled",
    })


# --- TC-BOOKINGS-401 -----------------------------------------------------------
def test_nothing_is_deleted_or_updated_row_by_row(client, db, signed_in):
    _rpc(db, [])

    client.post(URL, json=RELEASE, cookies=COOKIE)

    table(db).delete.assert_not_called()
    table(db).update.assert_not_called()


# --- TC-BOOKINGS-402 -----------------------------------------------------------
def test_releasing_again_is_a_no_op(client, db, signed_in):
    _rpc(db, [])

    first = client.post(URL, json=RELEASE, cookies=COOKIE)
    second = client.post(URL, json=RELEASE, cookies=COOKIE)

    assert first.json() == second.json() == {"released": [], "count": 0}


# --- TC-BOOKINGS-403 -----------------------------------------------------------
def test_without_a_session_nothing_is_released(client, db):
    response = client.post(URL, json=RELEASE)

    assert response.status_code == 401
    assert _release_calls(db) == []


@pytest.mark.parametrize("role", ["venue_staff", "event_organiser"])
def test_only_a_coordinator_can_release(client, db, signed_in, role):
    signed_in(role)

    response = client.post(URL, json=RELEASE, cookies=COOKIE)

    assert response.status_code == 403
    assert _release_calls(db) == []


@pytest.mark.parametrize("body", [
    {**RELEASE, "reason": "staff_released"}, {}, {"reason": "event_cancelled"}, {**RELEASE, "by": STAFF},
])
def test_only_an_event_cancellation_is_a_reason(client, db, signed_in, body):
    response = client.post(URL, json=body, cookies=COOKIE)

    assert response.status_code == 422
    assert _release_calls(db) == []


# --- TC-BOOKINGS-404 -----------------------------------------------------------
def test_a_released_booking_cannot_be_decided(client, db, signed_in):
    signed_in("venue_staff", STAFF)
    lookups(db, [booking_row(**RELEASED)])

    response = client.post(
        f"/bookings/{BOOKING_ID}/decision", json={"decision": "approved"}, cookies=COOKIE,
    )

    assert response.status_code == 409
    table(db).update.assert_not_called()


def test_a_released_booking_cannot_be_held(client, db, signed_in):
    signed_in("venue_staff", STAFF)
    lookups(db, [booking_row(**RELEASED)])

    response = client.post(
        f"/bookings/{BOOKING_ID}/hold", json={"expires_at": "2099-01-01T00:00:00+00:00"}, cookies=COOKIE,
    )

    assert response.status_code == 409
    table(db).update.assert_not_called()


def test_a_released_booking_cannot_be_changed_or_cancelled(client, db, signed_in):
    lookups(db, [booking_row(**RELEASED)], [booking_row(**RELEASED)])

    changed = client.patch(
        f"/bookings/{BOOKING_ID}",
        json={key: BOOKING[key] for key in ("venue_id", "booking_date", "start_time", "end_time", "venue_name")},
        cookies=COOKIE,
    )
    cancelled = client.delete(f"/bookings/{BOOKING_ID}", cookies=COOKIE)

    assert changed.status_code == 409
    assert changed.json()["detail"] == "Only a pending, held or confirmed booking can be changed"
    assert cancelled.status_code == 409
    assert cancelled.json()["detail"] == "Only a pending, held or confirmed booking can be cancelled"
    table(db).update.assert_not_called()
    table(db).delete.assert_not_called()


def test_a_released_booking_cannot_have_its_flag_resolved(client, db, signed_in):
    lookups(db, [booking_row(**RELEASED)])

    response = client.post(
        f"/bookings/{BOOKING_ID}/alternative-resolution", json={"note": "Moved online"}, cookies=COOKIE,
    )

    assert response.status_code == 409
    table(db).update.assert_not_called()


def test_a_released_booking_cannot_be_replaced(client, db):
    lookups(db, [booking_row(**RELEASED)])

    response = client.post("/bookings", json={**BOOKING, "replaces_booking_id": BOOKING_ID})

    assert response.status_code == 409
    assert response.json()["detail"] == "This booking can no longer be replaced"
    table(db).insert.assert_not_called()


def test_a_released_booking_never_blocks_a_new_request(client, db):
    query = lookups(db)
    table(db).insert.return_value.execute.return_value = MagicMock(data=[booking_row()])

    response = client.post("/bookings", json=BOOKING)

    assert response.status_code == 201
    status_filters = [call.args for call in query.in_.call_args_list if call.args[0] == "status"]
    assert status_filters and all("released" not in args[1] for args in status_filters)


# --- TC-BOOKINGS-404, closed event -------------------------------------------
def test_a_new_request_for_a_closed_event_is_refused(client, db):
    lookups(db)
    table(db).insert.return_value.execute.side_effect = ClosedEvent()

    response = client.post("/bookings", json=BOOKING)

    assert response.status_code == 409
    assert response.json()["detail"] == EVENT_CLOSED


def test_confirming_a_booking_of_a_closed_event_is_refused(client, db, signed_in):
    signed_in("venue_staff", STAFF)
    lookups(db, [booking_row(status="pending")], [], [])
    db.schema.return_value.table.return_value.update.return_value.eq.return_value.in_.return_value \
        .execute.side_effect = ClosedEvent()

    response = client.post(
        f"/bookings/{BOOKING_ID}/decision", json={"decision": "approved"}, cookies=COOKIE,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == EVENT_CLOSED


def test_holding_a_booking_of_a_closed_event_is_refused(client, db, signed_in):
    signed_in("venue_staff", STAFF)
    lookups(db, [booking_row(status="pending")], [], [])
    table(db).update.return_value.eq.return_value.eq.return_value.execute.side_effect = ClosedEvent()

    response = client.post(
        f"/bookings/{BOOKING_ID}/hold", json={"expires_at": "2099-01-01T00:00:00+00:00"}, cookies=COOKIE,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == EVENT_CLOSED


def test_changing_a_booking_of_a_closed_event_is_refused(client, db, signed_in):
    lookups(db, [booking_row(status="confirmed")], [], [])
    table(db).update.return_value.eq.return_value.in_.return_value.execute.side_effect = ClosedEvent()

    response = client.patch(
        f"/bookings/{BOOKING_ID}",
        json={key: BOOKING[key] for key in ("venue_id", "booking_date", "start_time", "end_time", "venue_name")},
        cookies=COOKIE,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == EVENT_CLOSED


# --- TC-BOOKINGS-405 -----------------------------------------------------------
def test_released_bookings_are_still_listed_for_their_event(client, db):
    query = lookups(db, [
        booking_row(id=BOOKING_ID, **RELEASED),
        booking_row(id="66666666-6666-4666-8666-666666666666", status="rejected",
                    decided_by=STAFF, decided_at="2026-10-02T00:00:00+00:00", decision_reason="Too small"),
    ])

    response = client.get("/bookings", params={"event_id": EVENT_ID})

    assert response.status_code == 200
    first = response.json()[0]
    assert first["status"] == "released"
    assert first["release_reason"] == "event_cancelled"
    assert first["released_by"] == COORDINATOR
    assert first["released_at"]
    assert query.eq.call_args.args == ("event_id", EVENT_ID)


# --- TC-BOOKINGS-406 -----------------------------------------------------------
def test_a_storage_failure_is_not_reported_as_a_release(client, db, signed_in):
    _rpc(db, error=RuntimeError("connection reset"))

    response = client.post(URL, json=RELEASE, cookies=COOKIE)

    assert response.status_code == 500
    assert response.json()["detail"] == "Booking storage unavailable"


def test_released_bookings_are_not_actionable_or_live(client, db):
    query = lookups(db, [], [])

    actionable = client.get("/bookings", params={"status": "actionable"})
    live = client.get("/bookings", params={"status": "live", "from": "2026-11-01"})

    assert actionable.status_code == live.status_code == 200
    status_filters = [call.args[1] for call in query.in_.call_args_list if call.args[0] == "status"]
    assert status_filters == [["pending", "held"], ["held", "confirmed"]]


# --- TC-BOOKINGS-407 -----------------------------------------------------------
CLOSURE = f"/internal/events/{EVENT_ID}/bookings/closure"
CLOSING = {
    "event_id": EVENT_ID, "operation_id": OPERATION, "state": "closing", "closed_by": COORDINATOR,
    "created_at": "2026-11-01T02:00:00+00:00", "closed_at": None, "reason": "event_cancelled",
}


def test_the_closure_intent_is_recorded_before_the_event_is_cancelled(client, db, signed_in):
    rpc = _rpc(db, [CLOSING])

    response = client.post(CLOSURE, json=RELEASE, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "closing"
    assert response.json()["operation_id"] == OPERATION
    rpc.assert_called_once_with("close_event_bookings", {
        "p_event_id": EVENT_ID,
        "p_operation_id": OPERATION,
        "p_closed_by": COORDINATOR,
        "p_reason": "event_cancelled",
    })


def test_an_existing_closure_is_returned_with_its_own_operation(client, db, signed_in):
    other = "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f"
    _rpc(db, [{**CLOSING, "operation_id": other}])

    response = client.post(CLOSURE, json=RELEASE, cookies=COOKIE)

    assert response.status_code == 200
    assert response.json()["operation_id"] == other


@pytest.mark.parametrize("role, expected", [(None, 401), ("venue_staff", 403), ("event_organiser", 403)])
def test_only_a_coordinator_can_close_or_reopen(client, db, signed_in, role, expected):
    if role:
        signed_in(role)
    cookies = COOKIE if role else None

    closed = client.post(CLOSURE, json=RELEASE, cookies=cookies)
    reopened = client.post(f"{CLOSURE}/reopen", json={"operation_id": OPERATION}, cookies=cookies)

    assert closed.status_code == reopened.status_code == expected
    db.schema.return_value.rpc.assert_not_called()


# --- TC-BOOKINGS-408 -----------------------------------------------------------
def test_reopening_withdraws_only_this_operations_or_an_abandoned_intent(client, db, signed_in):
    rpc = _rpc(db, [CLOSING])

    response = client.post(f"{CLOSURE}/reopen", json={"operation_id": OPERATION}, cookies=COOKIE)

    assert response.status_code == 200
    assert response.json() == {"reopened": True}
    rpc.assert_called_once_with("reopen_event_bookings", {
        "p_event_id": EVENT_ID,
        "p_operation_id": OPERATION,
        "p_abandoned_after": "2 minutes",
    })


def test_reopening_someone_elses_live_intent_or_a_closed_event_does_nothing(client, db, signed_in):
    _rpc(db, [])

    response = client.post(f"{CLOSURE}/reopen", json={"operation_id": OPERATION}, cookies=COOKIE)

    assert response.status_code == 200
    assert response.json() == {"reopened": False}


@pytest.mark.parametrize("body", [{}, {"operation_id": "not-a-uuid"}, {"operation_id": OPERATION, "x": 1}])
def test_a_malformed_reopen_is_refused(client, db, signed_in, body):
    response = client.post(f"{CLOSURE}/reopen", json=body, cookies=COOKIE)

    assert response.status_code == 422
    db.schema.return_value.rpc.assert_not_called()
