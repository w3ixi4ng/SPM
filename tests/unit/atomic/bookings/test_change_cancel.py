"""S-80: a Coordinator changes or cancels one booking.

TC-BOOKINGS-057..051.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import BOOKING_ID, app, booking_row, database_module, lookups, table

COORDINATOR = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
STAFF = "abababab-abab-4bab-8bab-abababababab"
STUDIO_C = "dddddddd-dddd-4ddd-8ddd-000000000002"
COOKIE = {"sb_access_token": "verified-token"}
URL = f"/bookings/{BOOKING_ID}"
CHANGE = {
    "venue_id": STUDIO_C,
    "venue_name": "Studio C",
    "booking_date": "2026-11-12",
    "start_time": "14:00",
    "end_time": "16:00",
    "notes": "Move to Studio C",
}
CLEARED = {
    "held_by", "held_at", "hold_released_at", "hold_release_reason",
    "decided_by", "decided_at", "decision_reason", "decision_alternative",
}
REVIEWED = {
    "held": {"held_by": STAFF, "held_at": "2026-10-10T09:00:00+00:00"},
    "confirmed": {"decided_by": STAFF, "decided_at": "2026-10-10T09:00:00+00:00"},
    "pending": {},
}


@pytest.fixture
def signed_in():
    fake = MagicMock()
    app.dependency_overrides[database_module.get_auth] = lambda: fake

    def as_role(role):
        fake.auth.get_user.return_value.user = SimpleNamespace(id=COORDINATOR, app_metadata={"role": role})

    as_role("event_coordinator")
    yield as_role
    app.dependency_overrides.pop(database_module.get_auth, None)


def _changed(db, row):
    update = table(db).update.return_value.eq.return_value.in_.return_value
    update.execute.return_value = SimpleNamespace(data=[row])
    return update


def _deleted(db, rows):
    delete = table(db).delete.return_value.eq.return_value.in_.return_value
    delete.execute.return_value = SimpleNamespace(data=rows)
    return delete


# --- TC-BOOKINGS-057 -------------------------------------------------------
@pytest.mark.parametrize("current", ["pending", "held", "confirmed"])
def test_a_change_goes_back_to_pending_and_touches_only_this_booking(client, db, signed_in, current):
    query = lookups(db, [booking_row(status=current, **REVIEWED[current])], [], [])
    _changed(db, booking_row(**{**CHANGE, "start_time": "14:00:00", "end_time": "16:00:00"}, status="pending"))

    response = client.patch(URL, json=CHANGE, params={"setup_minutes": 0, "turnaround_minutes": 0}, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"
    assert response.json()["venue_name"] == "Studio C"
    written = table(db).update.call_args.args[0]
    assert written["status"] == "pending"
    assert {key: written[key] for key in CHANGE} == {**CHANGE, "start_time": "14:00:00", "end_time": "16:00:00"}
    assert all(written[field] is None for field in CLEARED)
    assert table(db).update.return_value.eq.call_args.args == ("id", BOOKING_ID)
    guard = table(db).update.return_value.eq.return_value.in_
    assert guard.call_args.args == ("status", ["pending", "held", "confirmed"])
    # The overlap lookup leaves this booking out.
    query.neq.assert_any_call("id", BOOKING_ID)


# --- TC-BOOKINGS-058 -------------------------------------------------------
def test_a_change_into_a_taken_slot_is_refused(client, db, signed_in):
    taken = {"id": "other", "status": "confirmed", "event_name": "Other", "venue_name": "Studio C",
             "booking_date": "2026-11-12", "start_time": "13:00:00", "end_time": "15:00:00"}
    lookups(db, [booking_row(status="held", **REVIEWED["held"])], [taken], [])

    response = client.patch(URL, json=CHANGE, cookies=COOKIE)

    assert response.status_code == 409
    assert response.json()["detail"] == "Studio C is already confirmed on 12 Nov 2026 from 13:00 to 15:00."
    table(db).update.assert_not_called()


def test_a_change_into_a_blocked_period_is_refused(client, db, signed_in):
    block = {"id": "b1", "venue_name": "Studio C", "start_date": "2026-11-12", "start_time": "00:00:00",
             "end_date": "2026-11-13", "end_time": "00:00:00"}
    lookups(db, [booking_row(status="held", **REVIEWED["held"])], [], [block])

    response = client.patch(URL, json=CHANGE, cookies=COOKIE)

    assert response.status_code == 409
    assert response.json()["detail"].startswith("Studio C is unavailable from 12 Nov 2026 00:00")
    table(db).update.assert_not_called()


def test_moving_over_its_own_old_time_is_fine(client, db, signed_in):
    # The lookup leaves the booking itself out, so its own old 09:00-12:00
    # never counts against a new 10:00-13:00 at the same venue.
    lookups(db, [booking_row(status="held", **REVIEWED["held"])], [], [])
    _changed(db, booking_row(status="pending", start_time="10:00:00", end_time="13:00:00"))

    response = client.patch(URL, json={**CHANGE, "start_time": "10:00", "end_time": "13:00"}, cookies=COOKIE)

    assert response.status_code == 200, response.text


# --- TC-BOOKINGS-059 -------------------------------------------------------
def test_a_rejected_booking_cannot_be_changed(client, db, signed_in):
    lookups(db, [booking_row(status="rejected", decided_by=STAFF, decided_at="2026-10-10T09:00:00+00:00",
                             decision_reason="Too small")])

    response = client.patch(URL, json=CHANGE, cookies=COOKIE)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only a pending, held or confirmed booking can be changed"
    table(db).update.assert_not_called()


def test_a_missing_booking_is_404(client, db, signed_in):
    lookups(db)  # every lookup finds nothing

    assert client.patch(URL, json=CHANGE, cookies=COOKIE).status_code == 404
    assert client.delete(URL, cookies=COOKIE).status_code == 404
    table(db).update.assert_not_called()
    table(db).delete.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [{**CHANGE, "start_time": "16:00", "end_time": "14:00"}, {**CHANGE, "status": "confirmed"}],
    ids=["end-before-start", "extra-field"],
)
def test_a_malformed_change_is_422(client, db, signed_in, body):
    assert client.patch(URL, json=body, cookies=COOKIE).status_code == 422
    db.schema.assert_not_called()


# --- TC-BOOKINGS-060 -------------------------------------------------------
@pytest.mark.parametrize("current", ["pending", "held", "confirmed"])
def test_cancelling_deletes_that_booking_only(client, db, signed_in, current):
    lookups(db, [booking_row(status=current, **REVIEWED[current])])
    _deleted(db, [booking_row(status=current)])

    response = client.delete(URL, cookies=COOKIE)

    assert response.status_code == 204
    table(db).delete.assert_called_once_with()
    assert table(db).delete.return_value.eq.call_args.args == ("id", BOOKING_ID)
    guard = table(db).delete.return_value.eq.return_value.in_
    assert guard.call_args.args == ("status", ["pending", "held", "confirmed"])


def test_a_rejected_booking_cannot_be_cancelled(client, db, signed_in):
    lookups(db, [booking_row(status="rejected", decided_by=STAFF, decided_at="2026-10-10T09:00:00+00:00",
                             decision_reason="Too small")])

    response = client.delete(URL, cookies=COOKIE)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only a pending, held or confirmed booking can be cancelled"
    table(db).delete.assert_not_called()


# --- TC-BOOKINGS-061 -------------------------------------------------------
def test_without_a_session_nothing_changes(client, db):
    assert client.patch(URL, json=CHANGE).status_code == 401
    assert client.delete(URL).status_code == 401
    db.schema.assert_not_called()


@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "technical_support", "attendee"])
def test_other_roles_cannot_change_or_cancel(client, db, signed_in, role):
    signed_in(role)

    assert client.patch(URL, json=CHANGE, cookies=COOKIE).status_code == 403
    assert client.delete(URL, cookies=COOKIE).status_code == 403
    db.schema.assert_not_called()
