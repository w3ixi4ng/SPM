"""TC-VENUEBOOKINGS-110 (S-80): one booking changes and another is cancelled,
and the event's other bookings stay as they were, through Kong."""

import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env
from .test_availability import more_events  # noqa: F401 -- a fixture

pytestmark = requires_env

DAY = "2026-11-12"  # a Thursday; the world's venue is open thu 08:00-20:00


def seed(admin, world, status, start, end):
    row = {
        "event_id": world["event_id"], "venue_id": world["venue_id"],
        "coordinator_id": world["coordinator"]["id"], "coordinator_name": "spm-test Coordinator",
        "coordinator_email": world["coordinator"]["email"], "booking_date": DAY,
        "start_time": start, "end_time": end, "event_name": "spm-test S80",
        "event_purpose": "Change or cancel", "expected_attendance": 120, "venue_name": "spm-test venue",
        "status": status,
    }
    if status == "confirmed":
        row.update(decided_by=world["staff"]["id"], decided_at="2026-10-01T00:00:00+00:00")
    if status == "held":
        row.update(held_by=world["staff"]["id"], held_at="2026-10-01T00:00:00+00:00")
    return admin.schema("bookings").table("bookings").insert(row).execute().data[0]


def test_one_booking_changes_another_is_cancelled_and_the_rest_stay(admin, auth_client, world, more_events):
    coordinator = cookie_for(auth_client, world["coordinator"])
    a = seed(admin, world, "confirmed", "09:00", "12:00")
    b = seed(admin, world, "held", "13:00", "15:00")
    c = seed(admin, world, "pending", "15:00", "16:00")
    other_event = more_events[0]

    def stored(booking_id):
        rows = admin.schema("bookings").table("bookings").select("*").eq("id", booking_id).execute().data
        return rows[0] if rows else None

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0, headers=coordinator) as api:
        # 1. Move B later; it goes back to pending with no hold.
        changed = api.patch(f"/venue-bookings/{b['id']}", json={
            "venue_id": world["venue_id"], "booking_date": DAY, "start_time": "16:00", "end_time": "17:00",
        })
        assert changed.status_code == 200, changed.text
        row = stored(b["id"])
        assert (row["status"], row["start_time"][:5], row["end_time"][:5]) == ("pending", "16:00", "17:00")
        assert (row["held_by"], row["held_at"]) == (None, None)

        # 2. B's old slot is free for another event.
        taken = api.post("/venue-bookings", json={
            "event_id": other_event, "venue_id": world["venue_id"], "booking_date": DAY,
            "start_time": "13:00", "end_time": "15:00",
        })
        assert taken.status_code == 201, taken.text

        # 3. Cancel A.
        cancelled = api.delete(f"/venue-bookings/{a['id']}")
        assert cancelled.status_code == 204, cancelled.text
        assert stored(a["id"]) is None

        # 4. Only B and C are left on the event, C as it was.
        listed = api.get("/venue-bookings", params={"event_id": world["event_id"]})
        assert listed.status_code == 200, listed.text
        rows = {row["id"]: row for row in listed.json()}
        assert set(rows) == {b["id"], c["id"]}
        assert (rows[c["id"]]["status"], rows[c["id"]]["start_time"][:5]) == ("pending", "15:00")
