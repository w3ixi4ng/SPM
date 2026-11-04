"""S-91: one confirmed booking is selected as an event's primary venue."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import BOOKING_ID, app, booking_row, database_module, lookups

COORDINATOR = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
COOKIE = {"sb_access_token": "verified-token"}
URL = f"/bookings/{BOOKING_ID}/primary"


@pytest.fixture
def signed_in():
    auth = MagicMock()
    app.dependency_overrides[database_module.get_auth] = lambda: auth

    def as_role(role):
        auth.auth.get_user.return_value.user = SimpleNamespace(
            id=COORDINATOR, app_metadata={"role": role}
        )

    as_role("event_coordinator")
    yield as_role
    app.dependency_overrides.pop(database_module.get_auth, None)


def test_a_coordinator_selects_a_confirmed_primary_atomically(client, db, signed_in):
    confirmed = booking_row(status="confirmed", is_primary=False)
    selected = {**confirmed, "is_primary": True, "primary_selected_by": COORDINATOR,
                "primary_selected_at": "2026-10-28T04:00:00+00:00"}
    lookups(db, [confirmed])
    db.schema.return_value.rpc.return_value.execute.return_value = SimpleNamespace(data=[selected])

    response = client.put(URL, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json()["is_primary"] is True
    db.schema.return_value.rpc.assert_called_once_with(
        "set_primary_booking",
        {"p_booking_id": BOOKING_ID, "p_selected_by": COORDINATOR},
    )


@pytest.mark.parametrize("current", ["pending", "held", "rejected", "replaced"])
def test_only_a_confirmed_booking_can_be_primary(client, db, signed_in, current):
    lookups(db, [booking_row(status=current)])

    response = client.put(URL, cookies=COOKIE)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only a confirmed venue booking can be primary"
    db.schema.return_value.rpc.assert_not_called()


def test_a_missing_booking_is_not_selected(client, db, signed_in):
    lookups(db)
    assert client.put(URL, cookies=COOKIE).status_code == 404
    db.schema.return_value.rpc.assert_not_called()


def test_primary_selection_requires_a_coordinator(client, db, signed_in):
    assert client.put(URL).status_code == 401
    for role in ("venue_staff", "event_organiser", "attendee", "technical_support"):
        signed_in(role)
        assert client.put(URL, cookies=COOKIE).status_code == 403
    db.schema.assert_not_called()
