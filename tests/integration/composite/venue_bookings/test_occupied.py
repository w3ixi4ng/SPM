"""TC-VENUEBOOKINGS-137 (S-34 reopened): one date's occupied times across
venues come back through the real stack -- the live list's new `to`, the
cross-venue blocks query and the route together."""

import uuid
from datetime import date, timedelta

import httpx

from .conftest import BASE_URL, cookie_for, requires_env

pytestmark = requires_env

EVERY_DAY = [{"day": d, "open": "08:00:00", "close": "20:00:00"}
             for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]


def test_a_dates_occupied_times_come_back_through_the_stack(admin, auth_client, world):
    day = date.today() + timedelta(days=9)
    D, before, after = day.isoformat(), (day - timedelta(days=1)).isoformat(), (day + timedelta(days=1)).isoformat()
    staff, coordinator = world["staff"], world["coordinator"]
    tag = uuid.uuid4().hex[:6]
    extra = [
        admin.schema("venues").table("venues").insert({
            "name": f"spm-test S34 {label} {tag}", "location": "10 Anson Road", "capacity": 100,
            "room_layouts": ["theatre"], "facilities": [], "accessibility": [],
            "operating_hours": EVERY_DAY, "created_by": staff["id"],
        }).execute().data[0]["id"]
        for label in ("Held", "Blocked")
    ]
    v1, v2, v3 = world["venue_id"], extra[0], extra[1]

    def booking(venue_id, on, start, end, status, **extra_fields):
        row = {
            "event_id": world["event_id"], "venue_id": venue_id, "venue_name": "spm-test S34",
            "coordinator_id": coordinator["id"], "coordinator_name": "spm-test Coordinator",
            "coordinator_email": coordinator["email"], "booking_date": on,
            "start_time": start, "end_time": end, "event_name": "spm-test S34",
            "event_purpose": "Occupied venues", "expected_attendance": 50, "status": status,
            **extra_fields,
        }
        admin.schema("bookings").table("bookings").insert(row).execute()

    try:
        booking(v1, D, "10:00", "12:00", "confirmed",
                decided_by=staff["id"], decided_at="2026-10-01T00:00:00+00:00")
        booking(v2, D, "12:00", "13:00", "held", held_by=staff["id"],
                held_at="2026-10-01T00:00:00+00:00", hold_expires_at="2099-01-01T00:00:00+00:00")
        booking(v2, D, "15:00", "16:00", "pending")
        booking(v1, after, "10:00", "12:00", "confirmed",
                decided_by=staff["id"], decided_at="2026-10-01T00:00:00+00:00")
        admin.schema("bookings").table("blocks").insert({
            "venue_id": v3, "venue_name": "spm-test S34 Blocked", "start_date": before,
            "start_time": "18:00", "end_date": D, "end_time": "14:00",
            "reason": "maintenance", "created_by": staff["id"],
        }).execute()

        with httpx.Client(base_url=BASE_URL, timeout=20.0,
                          headers=cookie_for(auth_client, coordinator)) as api:
            response = api.get("/venue-bookings/occupied", params={"date": D})

        assert response.status_code == 200, response.text
        ours = [
            (e["venue_id"], e["state"], e["start_date"], e["start_time"][:5], e["end_time"][:5])
            for e in response.json()["entries"] if e["venue_id"] in (v1, v2, v3)
        ]
        assert sorted(ours) == sorted([
            (v1, "confirmed", D, "10:00", "12:00"),
            (v2, "held", D, "12:00", "13:00"),
            (v3, "blocked", before, "18:00", "14:00"),
        ]), "-- check the bookings schema is exposed and granted, and the stack is on .env.test"
    finally:
        admin.schema("bookings").table("blocks").delete().in_("venue_id", extra).execute()
        admin.schema("bookings").table("bookings").delete().in_("venue_id", extra).execute()
        admin.schema("venues").table("venues").delete().in_("id", extra).execute()
