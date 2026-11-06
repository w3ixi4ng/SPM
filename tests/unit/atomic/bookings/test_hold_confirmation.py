"""S-81 reopened: the Event Coordinator confirms a tentative hold before Venue
Staff can approve it. TC-BOOKINGS-470 to 474."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import BOOKING_ID, app, booking_row, database_module, lookups, table

STAFF = "abababab-abab-4bab-8bab-abababababab"
COORDINATOR = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
COOKIE = {"sb_access_token": "verified-token"}
CONFIRM = f"/internal/bookings/{BOOKING_ID}/confirm-hold"
DECIDE = f"/bookings/{BOOKING_ID}/decision"
SERVICE_HEADERS = {"X-Assignment-Service-Token": "test-service-token"}
CONFIRM_BODY = {"coordinator_id": COORDINATOR}
NOT_CONFIRMED = "This hold can't be approved until the Event Coordinator confirms it."
HELD = booking_row(status="held", held_by=STAFF, held_at="2026-11-05T01:00:00+00:00",
                   hold_expires_at="2099-01-01T04:00:00+00:00")
CONFIRMED_HOLD = {**HELD, "hold_confirmed_by": COORDINATOR, "hold_confirmed_at": "2026-11-05T02:00:00+00:00"}


@pytest.fixture
def signed_in():
    fake = MagicMock()

    def as_role(role, user_id):
        fake.auth.get_user.return_value.user = SimpleNamespace(id=user_id, app_metadata={"role": role})

    app.dependency_overrides[database_module.get_auth] = lambda: fake
    yield as_role
    app.dependency_overrides.pop(database_module.get_auth, None)


@pytest.fixture
def trusted(monkeypatch):
    monkeypatch.setenv("ASSIGNMENT_SERVICE_SECRET", "test-service-token")


def confirm(client, headers=SERVICE_HEADERS):
    return client.post(CONFIRM, headers=headers, json=CONFIRM_BODY)


def echo_update(db, base):
    update = table(db).update.return_value
    for method in ("eq", "in_", "or_", "is_", "gt"):
        getattr(update, method).return_value = update
    update.execute.side_effect = lambda: SimpleNamespace(data=[{**base, **table(db).update.call_args.args[0]}])
    return update


def written(db):
    return table(db).update.call_args.args[0]


# --- TC-BOOKINGS-470 --------------------------------------------------------
def test_the_coordinator_confirms_a_held_booking(client, db, trusted):
    lookups(db, [HELD])
    update = echo_update(db, HELD)

    response = confirm(client)

    assert response.status_code == 200, response.text
    assert response.json()["hold_confirmed_by"] == COORDINATOR
    assert response.json()["hold_confirmed_at"]
    table(db).update.assert_called_once()
    assert set(written(db)) == {"hold_confirmed_by", "hold_confirmed_at"}
    update.eq.assert_any_call("status", "held")


# --- TC-BOOKINGS-471 --------------------------------------------------------
def test_confirming_twice_changes_nothing(client, db, trusted):
    lookups(db, [CONFIRMED_HOLD])

    response = confirm(client)

    assert response.status_code == 200, response.text
    assert response.json()["hold_confirmed_at"] == "2026-11-05T02:00:00Z"
    table(db).update.assert_not_called()


# --- TC-BOOKINGS-472 --------------------------------------------------------
@pytest.mark.parametrize("row", [
    booking_row(status="pending"),
    booking_row(status="confirmed", decided_by=STAFF, decided_at="2026-11-05T00:00:00+00:00"),
    booking_row(status="rejected", decided_by=STAFF, decided_at="2026-11-05T00:00:00+00:00"),
    # A hold already past its expiry reads back released by expire_holds.
    booking_row(status="pending", held_by=STAFF, held_at="2026-11-01T00:00:00+00:00",
                hold_released_at="2026-11-02T00:00:00+00:00", hold_release_reason="expired"),
])
def test_only_a_live_hold_can_be_confirmed(client, db, trusted, row):
    lookups(db, [row])

    response = confirm(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only a tentative hold can be confirmed"
    db.schema.return_value.rpc.assert_called_with("expire_holds", {})
    table(db).update.assert_not_called()


def test_only_the_trusted_composite_confirms_a_hold(client, db, trusted):
    lookups(db, [HELD])

    assert confirm(client, headers={}).status_code == 403
    table(db).update.assert_not_called()


def test_confirming_a_missing_booking_is_not_found(client, db, trusted):
    lookups(db, [])

    response = confirm(client)

    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


# --- TC-BOOKINGS-473 --------------------------------------------------------
def test_an_unconfirmed_hold_cannot_be_approved(client, db, signed_in):
    signed_in("venue_staff", STAFF)
    lookups(db, [HELD])

    response = client.post(DECIDE, json={"decision": "approved"}, cookies=COOKIE)

    assert response.status_code == 409
    assert response.json()["detail"] == NOT_CONFIRMED
    table(db).update.assert_not_called()


def test_an_unconfirmed_hold_can_still_be_rejected(client, db, signed_in):
    signed_in("venue_staff", STAFF)
    lookups(db, [HELD])
    echo_update(db, HELD)

    response = client.post(DECIDE, json={"decision": "rejected", "reason": "Room needs repairs"}, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"


@pytest.mark.parametrize("row", [CONFIRMED_HOLD, booking_row(status="pending")], ids=["confirmed hold", "never held"])
def test_a_confirmed_hold_and_a_never_held_request_are_approved(client, db, signed_in, row):
    signed_in("venue_staff", STAFF)
    lookups(db, [row], [], [])
    update = echo_update(db, row)

    response = client.post(DECIDE, json={"decision": "approved"}, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    # The write itself refuses a hold that is not confirmed by then.
    update.or_.assert_called_once_with("status.eq.pending,hold_confirmed_at.not.is.null")


# --- TC-BOOKINGS-474 --------------------------------------------------------
def test_releasing_a_hold_clears_its_confirmation(client, db, signed_in):
    signed_in("venue_staff", STAFF)
    lookups(db, [CONFIRMED_HOLD])
    echo_update(db, CONFIRMED_HOLD)

    response = client.post(f"/bookings/{BOOKING_ID}/release", json={"reason": "staff_released"}, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert (written(db)["hold_confirmed_by"], written(db)["hold_confirmed_at"]) == (None, None)


def test_a_new_hold_needs_a_new_confirmation(client, db, signed_in):
    signed_in("venue_staff", STAFF)
    stale = booking_row(status="pending", hold_confirmed_by=COORDINATOR, hold_confirmed_at="2026-11-01T00:00:00+00:00")
    lookups(db, [stale], [], [])
    echo_update(db, stale)

    response = client.post(f"/bookings/{BOOKING_ID}/hold", json={"expires_at": "2099-11-12T10:00:00+08:00"}, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert (written(db)["hold_confirmed_by"], written(db)["hold_confirmed_at"]) == (None, None)
