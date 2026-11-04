"""TC-BOOKINGS-130. Run after the S-90 SQL on .env.test."""
import uuid

import httpx

from .conftest import BASE_URL, requires_env
from .test_availability import booking_body
from .test_decision import actors  # noqa: F401 -- actors is a fixture
from .test_replacement_venue import approve, create, read

pytestmark = requires_env


def replacement_for(booking_ids, original):
    return create(booking_ids, {
        **booking_body(str(uuid.uuid4()), "10:00", "12:00"),
        "event_id": original["event_id"], "replaces_booking_id": original["id"],
    })


def ask(original, coordinator):
    response = httpx.post(f"{BASE_URL}/bookings/{original['id']}/restore-request",
                          headers=coordinator, timeout=20)
    assert response.status_code == 200, (
        f"{response.text} -- check the S-90 block of bookings.sql is applied"
    )
    return response.json()


# --- TC-BOOKINGS-130 ------------------------------------------------------
def test_a_confirmed_restore_leaves_the_replacement_withdrawn_and_its_slot_free(admin, booking_ids, actors):
    _, staff = actors("venue_staff")
    coordinator_id, coordinator = actors("event_coordinator")

    # 1-2: asked for, then confirmed.
    v1 = str(uuid.uuid4())
    original = create(booking_ids, booking_body(v1, "10:00", "12:00"))
    approve(original["id"], staff)
    replacement = replacement_for(booking_ids, original)
    assert ask(original, coordinator)["restore_requested_by"] == coordinator_id
    assert read(admin, original["id"])["restore_requested_at"] is not None

    decided = httpx.post(f"{BASE_URL}/bookings/{original['id']}/restore-decision", headers=staff,
                         json={"decision": "approved"}, timeout=20)
    assert decided.status_code == 200, decided.text
    assert [row["id"] for row in decided.json()["withdrawn"]] == [replacement["id"]]
    withdrawn = read(admin, replacement["id"])
    assert withdrawn["status"] == "withdrawn"
    assert withdrawn["withdrawn_at"] is not None
    kept = read(admin, original["id"])
    assert kept["status"] == "confirmed"
    assert kept["restore_requested_at"] is None
    assert kept["alternative_resolution_note"] == "Restored to the original venue"
    assert kept["alternative_resolved_by"] == coordinator_id

    # 3: the withdrawn request no longer holds its venue.
    free = create(booking_ids, {**booking_body(replacement["venue_id"], "10:00", "12:00")})
    assert approve(free["id"], staff)["status"] == "confirmed"

    # 4: a replacement confirmed first ends the restore request.
    original_2 = create(booking_ids, booking_body(str(uuid.uuid4()), "14:00", "16:00"))
    approve(original_2["id"], staff)
    replacement_3 = create(booking_ids, {
        **booking_body(str(uuid.uuid4()), "14:00", "16:00"),
        "event_id": original_2["event_id"], "replaces_booking_id": original_2["id"],
    })
    ask(original_2, coordinator)
    assert approve(replacement_3["id"], staff)["status"] == "confirmed"
    replaced = read(admin, original_2["id"])
    assert replaced["status"] == "replaced"
    assert replaced["restore_requested_at"] is None
    assert replaced["restore_requested_by"] is None
