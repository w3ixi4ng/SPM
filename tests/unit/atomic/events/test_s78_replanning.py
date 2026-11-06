"""S-78 revision: approving a replacement venue returns a confirmed event, or
one waiting for its safety check, to planning.

TC-EVENTS-412..416. The venue_bookings composite calls this internal route
before it records the approval; only the event and its history change here.
"""

from types import SimpleNamespace

import pytest

from .conftest import EVENT_ID, history_table

URL = f"/internal/events/{EVENT_ID}/venue-replanning"
STAFF = "5a5a5a5a-5a5a-45a5-85a5-5a5a5a5a5a5a"
REPLACEMENT = "c2c2c2c2-c2c2-4c2c-8c2c-c2c2c2c2c2c2"
BODY = {
    "actor_id": STAFF,
    "booking_id": REPLACEMENT,
    "venue_name": "Hall W",
    "replaced_venue_name": "Hall V",
}
RESET = {
    "status": "planning",
    "safety_recheck_required": True,
    "safety_decision": None,
    "safety_decision_reason": None,
    "safety_officer_id": None,
    "safety_decided_at": None,
}


def _events(db):
    return db.schema.return_value.table("events")


def _reads(db, *statuses):
    """Each `select().eq(id)` read in turn: one status each, or None for no row."""
    _events(db).select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[] if value is None else [{"id": EVENT_ID, "status": value}])
        for value in statuses
    ]


def _update(db, rows):
    operation = _events(db).update.return_value.eq.return_value.in_.return_value
    operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


# --- TC-EVENTS-412 / 413 ----------------------------------------------------
@pytest.mark.parametrize("previous", ["confirmed", "pending_safety_check"])
def test_a_confirmed_or_waiting_event_returns_to_planning(client, db, previous):
    _reads(db, previous)
    update = _update(db, [{"id": EVENT_ID, "status": "planning"}])

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    assert response.json() == {"replanned": True, "status": "planning"}
    _events(db).update.assert_called_once_with(RESET)
    _events(db).update.return_value.eq.assert_called_once_with("id", EVENT_ID)
    _events(db).update.return_value.eq.return_value.in_.assert_called_once_with(
        "status", ["confirmed", "pending_safety_check"]
    )
    update.execute.assert_called_once()
    history_table(db).insert.assert_called_once_with({
        "event_id": EVENT_ID,
        "actor_id": STAFF,
        "actor_role": "venue_staff",
        "category": "venue",
        "action": "venue_replanned",
        "details": {
            "booking_id": REPLACEMENT,
            "venue_name": "Hall W",
            "replaced_venue_name": "Hall V",
            "previous_status": previous,
        },
    })


# --- TC-EVENTS-414 ----------------------------------------------------------
@pytest.mark.parametrize("current", ["planning", "cancelled"])
def test_any_other_status_is_left_as_it_is(client, db, current):
    _reads(db, current)

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    assert response.json() == {"replanned": False, "status": current}
    _events(db).update.assert_not_called()
    history_table(db).insert.assert_not_called()


# --- TC-EVENTS-415 ----------------------------------------------------------
def test_calling_again_after_the_event_moved_writes_nothing(client, db):
    # (a) A retry: the first call already returned it to planning.
    _reads(db, "planning")

    response = client.post(URL, json=BODY)

    assert response.json() == {"replanned": False, "status": "planning"}
    _events(db).update.assert_not_called()
    history_table(db).insert.assert_not_called()


def test_a_concurrent_change_is_reported_without_history(client, db):
    # (b) Confirmed when read, but the conditional update matched no row.
    _reads(db, "confirmed", "planning")
    _update(db, [])

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    assert response.json() == {"replanned": False, "status": "planning"}
    history_table(db).insert.assert_not_called()


# --- TC-EVENTS-416 ----------------------------------------------------------
@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_only_the_composite_may_call_it(client, db, token):
    if token is None:
        del client.headers["X-Assignment-Service-Token"]
    else:
        client.headers["X-Assignment-Service-Token"] = token

    response = client.post(URL, json=BODY)

    assert response.status_code == 403
    assert response.json()["detail"] == "Trusted assignment service required"
    _events(db).update.assert_not_called()
    history_table(db).insert.assert_not_called()


def test_an_unknown_event_is_not_found(client, db):
    _reads(db, None)

    response = client.post(URL, json=BODY)

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    _events(db).update.assert_not_called()
    history_table(db).insert.assert_not_called()
