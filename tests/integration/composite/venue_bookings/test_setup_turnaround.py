"""TC-VENUEBOOKINGS-107 (S-75): new setup/turnaround times flag the clash they
create and are used for the next request, through Kong."""

import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env
from .test_availability import more_events  # noqa: F401 -- a fixture

pytestmark = requires_env

DAY = "2026-11-12"  # a Thursday; the world's venue is open thu 08:00-20:00


def seed(admin, world, event_id, status, start, end):
    row = {
        "event_id": event_id, "venue_id": world["venue_id"],
        "coordinator_id": world["coordinator"]["id"], "coordinator_name": "spm-test Coordinator",
        "coordinator_email": world["coordinator"]["email"], "booking_date": DAY,
        "start_time": start, "end_time": end, "event_name": f"spm-test S75 {status}",
        "event_purpose": "Setup/turnaround", "expected_attendance": 10, "venue_name": "spm-test venue",
        "status": status,
    }
    if status == "confirmed":
        row.update(decided_by=world["staff"]["id"], decided_at="2026-10-01T00:00:00+00:00")
    if status == "held":
        row.update(
            held_by=world["staff"]["id"], held_at="2026-10-01T00:00:00+00:00",
            hold_expires_at="2099-01-01T04:00:00+00:00",
        )
    return admin.schema("bookings").table("bookings").insert(row).execute().data[0]


def test_new_times_flag_the_clash_and_govern_the_next_request(admin, auth_client, world, more_events):
    staff = cookie_for(auth_client, world["staff"])
    coordinator = cookie_for(auth_client, world["coordinator"])
    event_b, event_c = more_events
    a = seed(admin, world, world["event_id"], "confirmed", "10:00", "12:00")
    b = seed(admin, world, event_b, "held", "12:30", "14:00")

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        def clash_pairs():
            response = api.get("/venue-bookings/clashes", headers=staff, params={"venue_id": world["venue_id"]})
            assert response.status_code == 200, response.text
            return response.json()["pairs"]

        # 1. With 0/0 nothing clashes.
        assert clash_pairs() == []

        # 2. Staff set the venue's times.
        saved = api.patch(f"/venues/{world['venue_id']}", headers=staff,
                          json={"setup_minutes": 30, "turnaround_minutes": 45})
        assert saved.status_code == 200, saved.text

        # 3. The A-B pair is listed, and B's Coordinator sees the warning.
        [pair] = clash_pairs()
        assert {pair["first"]["id"], pair["second"]["id"]} == {a["id"], b["id"]}
        listed = api.get("/venue-bookings", headers=coordinator, params={"event_id": event_b})
        assert listed.status_code == 200, listed.text
        [b_row] = listed.json()
        assert [c["start_time"][:5] for c in b_row["clashes"]] == ["10:00"]
        stored = admin.schema("bookings").table("bookings").select("id,status").in_("id", [a["id"], b["id"]]).execute().data
        assert sorted(row["status"] for row in stored) == ["confirmed", "held"]

        # 4. The next request is checked by the new times.
        refused = api.post("/venue-bookings", headers=coordinator, json={
            "event_id": event_c, "venue_id": world["venue_id"], "booking_date": DAY,
            "start_time": "12:00", "end_time": "12:30",
        })
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"].endswith("it is in use until 12:45.")
