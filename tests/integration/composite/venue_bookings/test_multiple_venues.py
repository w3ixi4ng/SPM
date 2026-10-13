"""TC-VENUEBOOKINGS-109 (S-79): one event holds bookings at several venues,
each checked on its own, through Kong."""

import uuid

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env

DAY = "2026-11-12"  # a Thursday; every venue here is open thu 08:00-20:00


@pytest.fixture
def more_venues(admin, world):
    """Main Hall (300) and Seminar Room (40) beside the world's 150-seat venue,
    each offering what the world's event needs. Deleted afterwards."""
    tag = uuid.uuid4().hex[:8]
    ids = []
    try:
        for name, capacity in (("Main Hall", 300), ("Seminar Room", 40)):
            ids.append(admin.schema("venues").table("venues").insert({
                "name": f"spm-test {name} {tag}",
                "location": "10 Anson Road",
                "capacity": capacity,
                "facilities": ["projector"],
                "accessibility": ["wheelchair_access"],
                "room_layouts": ["theatre"],
                "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
                "created_by": world["staff"]["id"],
            }).execute().data[0]["id"])
        yield ids
    finally:
        for venue_id in ids:
            admin.schema("venues").table("venues").delete().eq("id", venue_id).execute()


def test_one_event_holds_bookings_at_several_venues(admin, auth_client, world, more_venues):
    coordinator = cookie_for(auth_client, world["coordinator"])
    staff = cookie_for(auth_client, world["staff"])
    hall, seminar = more_venues
    studio = world["venue_id"]
    event_id = world["event_id"]

    def request(venue_id, start, end):
        return api.post("/venue-bookings", headers=coordinator, json={
            "event_id": event_id, "venue_id": venue_id, "booking_date": DAY,
            "start_time": start, "end_time": end,
        })

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        # 1. Main Hall for the main programme, which Venue Staff hold.
        first = request(hall, "09:00", "17:00")
        assert first.status_code == 201, first.text
        held = api.post(f"/venue-bookings/{first.json()['id']}/hold", headers=staff,
                        json={"expires_at": "2099-01-01T12:00:00+08:00"})
        assert held.status_code == 200, held.text

        # 2. A breakout in another venue at the same time keeps the first.
        second = request(studio, "13:00", "15:00")
        assert second.status_code == 201, second.text
        kept = admin.schema("bookings").table("bookings").select(
            "status,hold_release_reason"
        ).eq("id", first.json()["id"]).execute().data[0]
        assert kept == {"status": "held", "hold_release_reason": None}

        # 3. A venue too small for the event's total attendance is refused.
        too_small = request(seminar, "13:00", "15:00")
        assert too_small.status_code == 422, too_small.text
        assert "holds 40 people; this event expects 120" in too_small.json()["errors"]["expected_attendance"]

        # 4. The event's own hold still blocks the same venue.
        clash = request(hall, "16:00", "18:00")
        assert clash.status_code == 409, clash.text
        assert "is already tentatively held on" in clash.json()["detail"]

        # 5. Both are listed for the event, each with its status.
        listed = api.get("/venue-bookings", headers=coordinator, params={"event_id": event_id})
        assert listed.status_code == 200, listed.text
        rows = {row["id"]: row for row in listed.json()}
        assert set(rows) == {first.json()["id"], second.json()["id"]}
        assert rows[first.json()["id"]]["status"] == "held"
        assert rows[second.json()["id"]]["status"] == "pending"
        assert {row["event_id"] for row in rows.values()} == {event_id}

    stored = admin.schema("bookings").table("bookings").select("id").eq("event_id", event_id).execute().data
    assert len(stored) == 2
