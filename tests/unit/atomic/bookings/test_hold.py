"""S-33 explicit tentative-hold placement and release."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import BOOKING_ID, app, booking_row, database_module, lookups, table

STAFF = "abababab-abab-4bab-8bab-abababababab"
COORDINATOR = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
COOKIE = {"sb_access_token": "verified-token"}


@pytest.fixture
def auth():
    fake = MagicMock()
    fake.auth.get_user.return_value.user = SimpleNamespace(
        id=STAFF, app_metadata={"role": "venue_staff"}
    )
    app.dependency_overrides[database_module.get_auth] = lambda: fake
    yield fake
    app.dependency_overrides.pop(database_module.get_auth, None)


def echo_update(db, base):
    update = table(db).update.return_value
    update.eq.return_value = update
    update.execute.side_effect = lambda: SimpleNamespace(
        data=[{**base, **table(db).update.call_args.args[0]}]
    )
    return update


def test_staff_places_and_releases_a_hold(client, db, auth):
    pending = booking_row()
    lookups(db, [pending], [], [])
    echo_update(db, pending)

    held = client.post(f"/bookings/{BOOKING_ID}/hold", cookies=COOKIE)

    assert held.status_code == 200, held.text
    assert held.json()["status"] == "held"
    assert held.json()["held_by"] == STAFF
    assert held.json()["held_at"]
    values = table(db).update.call_args.args[0]
    assert values["hold_released_at"] is None
    assert values["hold_release_reason"] is None

    held_row = {**pending, **values}
    table(db).select.return_value.execute.side_effect = None
    table(db).select.return_value.execute.return_value = SimpleNamespace(data=[held_row])
    echo_update(db, held_row)

    released = client.post(
        f"/bookings/{BOOKING_ID}/release",
        json={"reason": "staff_released"},
        cookies=COOKIE,
    )

    assert released.status_code == 200, released.text
    assert released.json()["status"] == "pending"
    assert released.json()["hold_release_reason"] == "staff_released"
    assert released.json()["hold_released_at"]


def test_overlapping_hold_is_identified_and_nothing_changes(client, db, auth):
    pending = booking_row()
    conflict = booking_row(
        id="55555555-5555-4555-8555-555555555555",
        status="held",
        start_time="10:00:00",
        end_time="13:00:00",
    )
    lookups(db, [pending], [conflict])

    response = client.post(f"/bookings/{BOOKING_ID}/hold", cookies=COOKIE)

    assert response.status_code == 409
    assert "already tentatively held" in response.json()["detail"]
    table(db).update.assert_not_called()


def test_only_staff_manage_holds_and_protected_fields_are_rejected(client, db, auth):
    auth.auth.get_user.return_value.user.app_metadata = {"role": "event_organiser"}
    assert client.post(f"/bookings/{BOOKING_ID}/hold", cookies=COOKIE).status_code == 403
    assert client.post(
        f"/bookings/{BOOKING_ID}/release",
        json={"reason": "staff_released"}, cookies=COOKIE,
    ).status_code == 403
    auth.auth.get_user.return_value.user.app_metadata = {"role": "venue_staff"}
    assert client.post(
        f"/bookings/{BOOKING_ID}/release",
        json={"reason": "staff_released", "held_by": STAFF}, cookies=COOKIE,
    ).status_code == 422


@pytest.mark.parametrize("reason", ["event_rejected", "event_cancelled"])
def test_staff_event_sync_release_reasons_are_audited(client, db, auth, reason):
    held = booking_row(status="held", held_by=STAFF, held_at="2026-11-01T00:00:00Z")
    lookups(db, [held])
    echo_update(db, held)

    response = client.post(
        f"/bookings/{BOOKING_ID}/release", json={"reason": reason}, cookies=COOKIE
    )

    assert response.status_code == 200
    assert response.json()["hold_release_reason"] == reason


def test_owning_coordinator_can_release_only_for_replacement(client, db, auth):
    held = booking_row(status="held", held_by=STAFF, held_at="2026-11-01T00:00:00Z")
    auth.auth.get_user.return_value.user = SimpleNamespace(
        id=COORDINATOR, app_metadata={"role": "event_coordinator"}
    )
    lookups(db, [held])
    echo_update(db, held)

    response = client.post(
        f"/bookings/{BOOKING_ID}/release",
        json={"reason": "booking_replaced"}, cookies=COOKIE,
    )

    assert response.status_code == 200
    assert response.json()["hold_release_reason"] == "booking_replaced"
