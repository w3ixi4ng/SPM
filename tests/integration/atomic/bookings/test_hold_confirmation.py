"""TC-BOOKINGS-131 (S-81 reopened): the Coordinator's confirmation of a hold
is stored, gates approval, and is cleared when the hold is released. Run after
the S-81 confirmation block of bookings.sql on .env.test."""
import uuid

import httpx

from .conftest import BASE_URL, requires_env
from .test_availability import booking_body
from .test_decision import actors  # noqa: F401 -- actors is a fixture

pytestmark = requires_env

NOT_CONFIRMED = "This hold can't be approved until the Event Coordinator confirms it."
EXPIRY = {"expires_at": "2099-01-01T00:00:00+00:00"}


def _create(booking_ids, body):
    response = httpx.post(f"{BASE_URL}/bookings", json=body, timeout=20)
    assert response.status_code == 201, response.text
    booking_ids.append(response.json()["id"])
    return response.json()["id"]


def test_the_confirmation_is_stored_gates_approval_and_is_cleared_on_release(admin, booking_ids, actors):
    _, staff = actors("venue_staff")
    coordinator_id, coordinator = actors("event_coordinator")
    venue_id = str(uuid.uuid4())
    h1 = _create(booking_ids, booking_body(venue_id, "09:00", "10:00"))
    h2 = _create(booking_ids, booking_body(venue_id, "13:00", "14:00"))

    def row(booking_id):
        return admin.schema("bookings").table("bookings").select(
            "status,hold_confirmed_by,hold_confirmed_at").eq("id", booking_id).execute().data[0]

    def post(path, headers, **json):
        return httpx.post(f"{BASE_URL}{path}", headers=headers, json=json or None, timeout=20)

    # 1. An unconfirmed hold can't be approved.
    assert post(f"/bookings/{h1}/hold", staff, **EXPIRY).status_code == 200
    refused = post(f"/bookings/{h1}/decision", staff, decision="approved")
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == NOT_CONFIRMED
    assert row(h1)["status"] == "held"

    # 2. The Coordinator confirms it; the row records who and when.
    confirmed = post(f"/bookings/{h1}/hold-confirmation", coordinator)
    assert confirmed.status_code == 200, f"{confirmed.text} -- check the S-81 confirmation SQL is applied"
    stored = row(h1)
    assert stored["hold_confirmed_by"] == coordinator_id and stored["hold_confirmed_at"]

    # 3. Now it is approved, keeping its confirmation.
    approved = post(f"/bookings/{h1}/decision", staff, decision="approved")
    assert approved.status_code == 200, approved.text
    assert row(h1)["status"] == "confirmed" and row(h1)["hold_confirmed_by"] == coordinator_id

    # 4. Releasing a confirmed hold clears the confirmation.
    assert post(f"/bookings/{h2}/hold", staff, **EXPIRY).status_code == 200
    assert post(f"/bookings/{h2}/hold-confirmation", coordinator).status_code == 200
    assert post(f"/bookings/{h2}/release", staff, reason="staff_released").status_code == 200
    assert row(h2) == {"status": "pending", "hold_confirmed_by": None, "hold_confirmed_at": None}
