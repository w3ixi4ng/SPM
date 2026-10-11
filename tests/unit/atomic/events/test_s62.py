"""S-62: an Organiser requests cancellation of their own event.

TC-EVENTS-123..129. The request is stored on the event; its status never
changes.
"""

from types import SimpleNamespace

import pytest

from .conftest import (
    EVENT_ID,
    ORGANISER_ID,
    OTHER_USER_ID,
    authenticate,
    event_row,
    fake_user,
    on_owned_list,
    on_owned_select,
)

REASON = "Keynote speaker withdrew and no replacement is available"
ELIGIBLE = ["submitted", "under_review", "planning", "confirmed", "preparation", "safety_changes_requested"]
INELIGIBLE = ["draft", "returned", "rejected", "cancelled", "safety_rejected"]
URL = f"/events/{EVENT_ID}/cancellation-request"


def _live(status="planning", **changes):
    values = {
        "status": status,
        "name": "Alumni networking evening",
        "purpose": "Reconnect graduates with faculty",
        "start_date": "2026-11-12",
        "start_time": "09:00:00",
        "end_date": "2026-11-12",
        "end_time": "18:00:00",
        "expected_attendance": 120,
        "submitted_at": "2026-10-01T00:00:00Z",
    }
    if status not in ("draft", "submitted", "under_review"):
        values.update(decision="approved", decided_at="2026-10-02T00:00:00Z")
    values.update(changes)
    return event_row(**values)


def _guarded_update(db, rows=None, error=None):
    # .update().eq(id).eq(organiser_id).in_(status, [...]).is_(requested_at, null)
    operation = (
        db.schema.return_value.table.return_value.update.return_value
        .eq.return_value.eq.return_value.in_.return_value.is_.return_value
    )
    if error is not None:
        operation.execute.side_effect = error
    else:
        operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def _update(db):
    return db.schema.return_value.table.return_value.update


# --- TC-EVENTS-123 ---------------------------------------------------------
@pytest.mark.parametrize("event_status", ELIGIBLE)
def test_the_organiser_requests_cancellation_of_an_eligible_event(client, db, auth, event_status):
    authenticate(client, auth)
    on_owned_select(db, [_live(event_status)])
    stored = _live(
        event_status,
        cancellation_reason=REASON,
        cancellation_requested_at="2026-10-11T09:00:00+00:00",
        cancellation_requested_by=ORGANISER_ID,
    )
    _guarded_update(db, [stored])

    response = client.post(URL, json={"reason": f"  {REASON}  "})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == event_status
    assert body["cancellation_reason"] == REASON
    assert body["cancellation_requested_by"] == ORGANISER_ID
    assert body["cancellation_requested_at"] is not None

    _update(db).assert_called_once()
    written = _update(db).call_args.args[0]
    assert set(written) == {"cancellation_reason", "cancellation_requested_at", "cancellation_requested_by"}
    assert written["cancellation_reason"] == REASON
    assert written["cancellation_requested_by"] == ORGANISER_ID
    assert written["cancellation_requested_at"].startswith("20")

    chain = _update(db).return_value
    assert chain.eq.call_args.args == ("id", EVENT_ID)
    assert chain.eq.return_value.eq.call_args.args == ("organiser_id", ORGANISER_ID)
    status_guard = chain.eq.return_value.eq.return_value.in_
    assert status_guard.call_args.args[0] == "status"
    assert set(status_guard.call_args.args[1]) == set(ELIGIBLE)
    assert status_guard.return_value.is_.call_args.args == ("cancellation_requested_at", "null")


# --- TC-EVENTS-124 ---------------------------------------------------------
@pytest.mark.parametrize("event_status", INELIGIBLE)
def test_an_event_that_is_not_eligible_cannot_have_a_request(client, db, auth, event_status):
    authenticate(client, auth)
    on_owned_select(db, [_live(event_status)])

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 409
    assert response.json()["detail"] == "This event can't be cancelled from its current status."
    _update(db).assert_not_called()


# --- TC-EVENTS-125 ---------------------------------------------------------
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"reason": ""},
        {"reason": "   "},
        {"reason": "x" * 1001},
        {"reason": "ok", "cancellation_requested_at": "2020-01-01T00:00:00Z"},
    ],
    ids=["missing", "empty", "blank", "too-long", "extra-field"],
)
def test_a_missing_blank_or_too_long_reason_is_refused(client, db, auth, body):
    authenticate(client, auth)

    response = client.post(URL, json=body)

    assert response.status_code == 422
    db.schema.assert_not_called()


# --- TC-EVENTS-126 ---------------------------------------------------------
def test_no_session_is_401(client, db):
    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 401
    db.schema.assert_not_called()


@pytest.mark.parametrize("role", ["event_coordinator", "venue_staff", "technical_support", "attendee"])
def test_other_roles_are_403(client, db, auth, role):
    authenticate(client, auth, fake_user(OTHER_USER_ID, role))

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 403
    db.schema.assert_not_called()


def test_someone_elses_or_a_missing_event_is_404(client, db, auth):
    # The lookup is scoped to the caller, so both look the same: no row.
    authenticate(client, auth)
    on_owned_select(db, [])

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    lookup = db.schema.return_value.table.return_value.select.return_value
    assert lookup.eq.return_value.eq.call_args.args == ("organiser_id", ORGANISER_ID)
    _update(db).assert_not_called()


# --- TC-EVENTS-127 ---------------------------------------------------------
def test_a_second_request_is_refused_and_the_first_kept(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [_live(
        cancellation_reason="Venue flooded",
        cancellation_requested_at="2026-10-10T09:00:00+00:00",
        cancellation_requested_by=ORGANISER_ID,
    )])

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 409
    assert response.json()["detail"] == "A cancellation request has already been sent for this event."
    _update(db).assert_not_called()


def test_a_request_that_loses_a_race_is_refused_without_overwriting(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [_live()])
    _guarded_update(db, [])

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 409
    assert response.json()["detail"] == "A cancellation request has already been sent for this event."
    # One guarded write and no unguarded retry.
    _update(db).assert_called_once()


# --- TC-EVENTS-128 ---------------------------------------------------------
def test_a_storage_failure_leaves_the_event_as_it_was(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [_live()])
    _guarded_update(db, error=RuntimeError("connection reset"))

    response = client.post(URL, json={"reason": REASON})

    assert response.status_code == 500
    assert response.json() == {"detail": "Event storage unavailable"}
    _update(db).assert_called_once()
    assert "status" not in _update(db).call_args.args[0]


# --- TC-EVENTS-129 ---------------------------------------------------------
def test_the_request_is_returned_with_the_event(client, db, auth):
    authenticate(client, auth)
    requested = _live(
        cancellation_reason=REASON,
        cancellation_requested_at="2026-10-11T09:00:00+00:00",
        cancellation_requested_by=ORGANISER_ID,
    )
    other = _live(id="44444444-4444-4444-8444-444444444444")
    on_owned_select(db, [requested])
    on_owned_list(db, [requested, other])

    one = client.get(f"/events/{EVENT_ID}")
    listed = client.get("/events")

    assert one.status_code == 200 and listed.status_code == 200
    for row in (one.json(), listed.json()[0]):
        assert row["status"] == "planning"
        assert row["cancellation_reason"] == REASON
        assert row["cancellation_requested_at"].startswith("2026-10-11T09:00:00")
        assert row["cancellation_requested_by"] == ORGANISER_ID
    second = listed.json()[1]
    assert (
        second["cancellation_reason"],
        second["cancellation_requested_at"],
        second["cancellation_requested_by"],
    ) == (None, None, None)
