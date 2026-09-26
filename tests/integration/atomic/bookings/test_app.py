"""Integration tests for the bookings service -- see TEST_CASES.md."""

import uuid

import httpx

from .conftest import BASE_URL, requires_env

pytestmark = requires_env


# --- TC-BOOKINGS-101 ------------------------------------------------------
def test_a_booking_saved_through_the_service_is_listed_as_pending(admin, booking_ids):
    body = {
        "event_id": str(uuid.uuid4()),
        "venue_id": str(uuid.uuid4()),
        "coordinator_id": str(uuid.uuid4()),
        "coordinator_name": "Grace Hopper",
        "coordinator_email": "grace@example.com",
        "booking_date": "2026-11-12",
        "start_time": "09:00",
        "end_time": "12:00",
        "event_name": f"spm-test booking {uuid.uuid4().hex[:8]}",
        "event_purpose": "Reconnect graduates with faculty",
        "expected_attendance": 120,
        "accessibility_requirements": "Two guests use wheelchairs",
        "required_accessibility": ["wheelchair_access", "lift"],
        "required_facilities": ["projector", "sound_system"],
        "room_layout": "theatre",
        "notes": "Access from 08:30 for setup",
        "venue_name": "Studio B",
    }

    created = httpx.post(f"{BASE_URL}/bookings", json=body, timeout=10.0)
    assert created.status_code == 201, created.text
    booking = created.json()
    booking_ids.append(booking["id"])
    assert booking["status"] == "pending"
    assert booking["submitted_at"]

    listed = httpx.get(f"{BASE_URL}/bookings", params={"status": "pending"}, timeout=10.0)
    assert listed.status_code == 200, listed.text
    assert booking["id"] in [row["id"] for row in listed.json()]

    rows = admin.schema("bookings").table("bookings").select("*").eq("id", booking["id"]).execute().data
    assert len(rows) == 1, "no row in bookings.bookings -- check the schema is exposed and granted"
    assert rows[0]["required_facilities"] == ["projector", "sound_system"]
    assert rows[0]["required_accessibility"] == ["wheelchair_access", "lift"]
    assert rows[0]["room_layout"] == "theatre"
