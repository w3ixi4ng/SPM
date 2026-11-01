"""TC-BOOKINGS-450..452 (S-89). Run after the S-89 block of bookings.sql on .env.test.

Releasing a cancelled event's bookings keeps every row, satisfies the real
decision, hold, primary and exclusion constraints, frees the venue time, and
closes the event so no booking for it becomes active again. The closure
intent, recorded before the event is cancelled, already refuses every direct
mutation -- including when they race it.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

from .conftest import BASE_URL, requires_env
from .test_availability import booking_body
from .test_decision import actors  # noqa: F401 -- actors is a fixture

pytestmark = requires_env

ACTIVE = ("pending", "held", "confirmed")
CLOSED = "This event is being cancelled, so its venue bookings can no longer change."


def _ops():
    return str(uuid.uuid4())


def _create(booking_ids, body):
    response = httpx.post(f"{BASE_URL}/bookings", json=body, timeout=20)
    assert response.status_code == 201, response.text
    booking_ids.append(response.json()["id"])
    return response.json()


def _read(admin, booking_id):
    rows = admin.schema("bookings").table("bookings").select("*").eq("id", booking_id).execute().data
    assert len(rows) == 1, "the row is gone -- S-89 must never delete a booking"
    return rows[0]


def test_release_keeps_every_row_and_frees_the_venue_time(admin, booking_ids, actors):
    _, staff = actors("venue_staff")
    coordinator_id, coordinator = actors("event_coordinator")
    event_id, other_event = str(uuid.uuid4()), str(uuid.uuid4())
    v1, v2, v3 = (str(uuid.uuid4()) for _ in range(3))

    def body(venue_id, start, end, event=event_id):
        return {**booking_body(venue_id, start, end), "event_id": event, "event_name": "spm-test S-89"}

    try:
        pending = _create(booking_ids, body(v1, "09:00", "10:00"))
        held = _create(booking_ids, body(v2, "09:00", "10:00"))
        hold = httpx.post(f"{BASE_URL}/bookings/{held['id']}/hold", headers=staff,
                          json={"expires_at": "2030-01-01T00:00:00+00:00"}, timeout=20)
        assert hold.status_code == 200, hold.text
        confirmed = _create(booking_ids, body(v3, "09:00", "12:00"))
        approved = httpx.post(f"{BASE_URL}/bookings/{confirmed['id']}/decision", headers=staff,
                              json={"decision": "approved"}, timeout=20)
        assert approved.status_code == 200, approved.text
        assert _read(admin, confirmed["id"])["is_primary"] is True
        rejected = _create(booking_ids, body(v1, "13:00", "14:00"))
        refused = httpx.post(f"{BASE_URL}/bookings/{rejected['id']}/decision", headers=staff,
                             json={"decision": "rejected", "reason": "spm-test too small"}, timeout=20)
        assert refused.status_code == 200, refused.text
        other = _create(booking_ids, body(str(uuid.uuid4()), "09:00", "12:00", other_event))

        # 1. Release.
        url = f"{BASE_URL}/internal/events/{event_id}/bookings/release"
        operation = _ops()
        released = httpx.post(url, headers=coordinator, json={"reason": "event_cancelled", "operation_id": operation}, timeout=20)
        assert released.status_code == 200, (
            f"{released.text} -- check the S-89 block of bookings.sql is applied"
        )
        assert released.json()["count"] == 3
        assert set(released.json()["released"]) == {pending["id"], held["id"], confirmed["id"]}

        # 2. The rows are all still there.
        for row_id in (pending["id"], held["id"], confirmed["id"]):
            row = _read(admin, row_id)
            assert row["status"] == "released"
            assert row["release_reason"] == "event_cancelled"
            assert row["released_by"] == coordinator_id
            assert row["released_at"]
            assert row["is_primary"] is False
        held_row = _read(admin, held["id"])
        assert held_row["hold_release_reason"] == "event_cancelled"
        assert held_row["hold_released_at"]
        assert _read(admin, rejected["id"])["status"] == "rejected"
        assert _read(admin, other["id"])["status"] == "pending"

        # 3. The confirmed slot is free for another event.
        newcomer = _create(booking_ids, body(v3, "09:00", "12:00", str(uuid.uuid4())))
        taken = httpx.post(f"{BASE_URL}/bookings/{newcomer['id']}/decision", headers=staff,
                           json={"decision": "approved"}, timeout=20)
        assert taken.status_code == 200, taken.text

        # 4. Releasing again changes nothing.
        before = _read(admin, confirmed["id"])["released_at"]
        again = httpx.post(url, headers=coordinator, json={"reason": "event_cancelled", "operation_id": operation}, timeout=20)
        assert again.status_code == 200, again.text
        assert again.json() == {"released": [], "count": 0}
        assert _read(admin, confirmed["id"])["released_at"] == before

        # 5. The event is closed: no new active booking for it, by any route.
        late = httpx.post(f"{BASE_URL}/bookings", json=body(str(uuid.uuid4()), "15:00", "16:00"), timeout=20)
        assert late.status_code == 409, late.text
        assert late.json()["detail"] == CLOSED

        # 6. A released event is never reopened, by anyone.
        reopened = httpx.post(f"{BASE_URL}/internal/events/{event_id}/bookings/closure/reopen",
                              headers=coordinator, json={"operation_id": operation}, timeout=20)
        assert reopened.status_code == 200 and reopened.json() == {"reopened": False}
    finally:
        admin.schema("bookings").table("closed_events").delete().eq("event_id", event_id).execute()


def _closure(coordinator, event_id, operation):
    return httpx.post(f"{BASE_URL}/internal/events/{event_id}/bookings/closure", headers=coordinator,
                      json={"reason": "event_cancelled", "operation_id": operation}, timeout=20)


def _reopen(coordinator, event_id, operation):
    return httpx.post(f"{BASE_URL}/internal/events/{event_id}/bookings/closure/reopen", headers=coordinator,
                      json={"operation_id": operation}, timeout=20)


# --- TC-BOOKINGS-451 ------------------------------------------------------------
def test_the_closure_intent_refuses_every_direct_mutation_and_is_withdrawable(admin, booking_ids, actors):
    _, staff = actors("venue_staff")
    _, coordinator = actors("event_coordinator")
    event_id = str(uuid.uuid4())

    def body(start, end):
        return {**booking_body(str(uuid.uuid4()), start, end), "event_id": event_id, "event_name": "spm-test S-89"}

    try:
        pending = _create(booking_ids, body("09:00", "10:00"))
        to_hold = _create(booking_ids, body("09:00", "10:00"))
        held = _create(booking_ids, body("11:00", "12:00"))
        hold = httpx.post(f"{BASE_URL}/bookings/{held['id']}/hold", headers=staff,
                          json={"expires_at": "2030-01-01T00:00:00+00:00"}, timeout=20)
        assert hold.status_code == 200, hold.text

        mine, other = _ops(), _ops()
        recorded = _closure(coordinator, event_id, mine)
        assert recorded.status_code == 200, f"{recorded.text} -- check the S-89 bookings.sql block is applied"
        assert recorded.json()["state"] == "closing"
        # A second attempt gets the existing intent, with its owner.
        assert _closure(coordinator, event_id, other).json()["operation_id"] == mine

        # Every direct route that would make a booking active is refused.
        refused = [
            httpx.post(f"{BASE_URL}/bookings", json=body("13:00", "14:00"), timeout=20),
            httpx.post(f"{BASE_URL}/bookings/{pending['id']}/decision", headers=staff,
                       json={"decision": "approved"}, timeout=20),
            httpx.post(f"{BASE_URL}/bookings/{to_hold['id']}/hold", headers=staff,
                       json={"expires_at": "2030-01-01T00:00:00+00:00"}, timeout=20),
            httpx.patch(f"{BASE_URL}/bookings/{pending['id']}", headers=coordinator, json={
                "venue_id": str(uuid.uuid4()), "venue_name": "Studio C", "booking_date": "2026-11-12",
                "start_time": "15:00", "end_time": "16:00",
            }, timeout=20),
        ]
        for response in refused:
            assert response.status_code == 409, response.text
            assert response.json()["detail"] == CLOSED
        assert _read(admin, pending["id"])["status"] == "pending"
        assert _read(admin, to_hold["id"])["status"] == "pending"

        # Giving time back still works: a hold can be released.
        let_go = httpx.post(f"{BASE_URL}/bookings/{held['id']}/release", headers=staff,
                            json={"reason": "staff_released"}, timeout=20)
        assert let_go.status_code == 200, let_go.text
        # And rejecting changes nothing active.
        rejected = httpx.post(f"{BASE_URL}/bookings/{to_hold['id']}/decision", headers=staff,
                              json={"decision": "rejected", "reason": "spm-test"}, timeout=20)
        assert rejected.status_code == 200, rejected.text

        # Only the owner (or an abandoned intent) can withdraw it.
        assert _reopen(coordinator, event_id, other).json() == {"reopened": False}
        assert _reopen(coordinator, event_id, mine).json() == {"reopened": True}
        reconfirmed = httpx.post(f"{BASE_URL}/bookings/{pending['id']}/decision", headers=staff,
                                 json={"decision": "approved"}, timeout=20)
        assert reconfirmed.status_code == 200, reconfirmed.text
    finally:
        admin.schema("bookings").table("closed_events").delete().eq("event_id", event_id).execute()


# --- TC-BOOKINGS-452 ------------------------------------------------------------
def test_confirmations_racing_the_closure_never_survive_the_release(admin, booking_ids, actors):
    _, staff = actors("venue_staff")
    _, coordinator = actors("event_coordinator")
    event_id = str(uuid.uuid4())
    pendings = [
        _create(booking_ids, {**booking_body(str(uuid.uuid4()), "09:00", "10:00"), "event_id": event_id})
        for _ in range(8)
    ]
    operation = _ops()

    def confirm(booking):
        return httpx.post(f"{BASE_URL}/bookings/{booking['id']}/decision", headers=staff,
                          json={"decision": "approved"}, timeout=30)

    try:
        with ThreadPoolExecutor(max_workers=9) as pool:
            confirmations = [pool.submit(confirm, booking) for booking in pendings]
            closure = pool.submit(_closure, coordinator, event_id, operation)
            answers = [future.result() for future in confirmations]
            assert closure.result().status_code == 200, closure.result().text

        # Each one either landed before the closure or was refused by it --
        # never a deadlock, a 500, or any other answer.
        for answer in answers:
            assert answer.status_code in (200, 409), answer.text
            if answer.status_code == 409:
                assert answer.json()["detail"] == CLOSED

        # After the closure nothing new can become active ...
        late = confirm(next((b for b, a in zip(pendings, answers) if a.status_code == 409), pendings[0]))
        assert late.status_code == 409

        # ... and the release leaves nothing active, whatever won the race.
        released = httpx.post(f"{BASE_URL}/internal/events/{event_id}/bookings/release", headers=coordinator,
                              json={"reason": "event_cancelled", "operation_id": operation}, timeout=20)
        assert released.status_code == 200, released.text
        rows = admin.schema("bookings").table("bookings").select("status").eq("event_id", event_id).execute().data
        assert rows and all(row["status"] == "released" for row in rows)
    finally:
        admin.schema("bookings").table("closed_events").delete().eq("event_id", event_id).execute()
