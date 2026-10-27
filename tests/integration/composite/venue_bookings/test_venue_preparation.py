"""S-25 real users/events/bookings boundary through Kong."""
import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env


def test_venue_preparation_round_trip(admin, auth_client, world):
    event_id = world["event_id"]
    staff_id = world["staff"]["id"]
    admin.schema("events").table("events").update({
        "status": "preparation",
        "safety_decision": "approved",
        "safety_officer_id": staff_id,
        "safety_decided_at": "2026-10-20T09:00:00Z",
    }).eq("id", event_id).execute()
    row = admin.schema("bookings").table("bookings").insert({
        "event_id": event_id,
        "venue_id": world["venue_id"],
        "coordinator_id": world["coordinator"]["id"],
        "coordinator_name": "spm-test Coordinator",
        "coordinator_email": world["coordinator"]["email"],
        "status": "confirmed",
        "decided_by": staff_id,
        "decided_at": "2026-10-20T08:00:00Z",
        "booking_date": "2026-11-12", "start_time": "09:00", "end_time": "12:00",
        "event_name": "spm-test preparation", "event_purpose": "S-25 integration",
        "expected_attendance": 120, "venue_name": "spm-test Venue",
    }).execute().data[0]

    staff = cookie_for(auth_client, world["staff"])
    listed = httpx.get(f"{GATEWAY_BASE_URL}/venue-bookings/preparation", headers=staff, timeout=20)
    assert listed.status_code == 200, listed.text
    assert row["id"] in [booking["id"] for booking in listed.json()]

    path = f"{GATEWAY_BASE_URL}/venue-bookings/{row['id']}/preparation"
    first = httpx.put(path, headers=staff, json={"status": "in_progress", "expected_version": 0}, timeout=20)
    assert first.status_code == 200, first.text
    assert first.json()["venue_preparation_status"] == "in_progress"
    assert first.json()["venue_preparation_updated_by"] == staff_id
    ready = httpx.put(path, headers=staff, json={"status": "ready", "expected_version": 1}, timeout=20)
    assert ready.status_code == 200, ready.text
    assert ready.json()["venue_preparation_version"] == 2

    stale = httpx.put(path, headers=staff, json={"status": "not_started", "expected_version": 1}, timeout=20)
    assert stale.status_code == 409
    coordinator = cookie_for(auth_client, world["coordinator"])
    assert httpx.put(path, headers=coordinator, json={"status": "ready", "expected_version": 2}, timeout=20).status_code == 403

    stored = admin.schema("bookings").table("bookings").select(
        "venue_preparation_status,venue_preparation_updated_by,venue_preparation_updated_at,venue_preparation_version"
    ).eq("id", row["id"]).execute().data[0]
    assert stored["venue_preparation_status"] == "ready"
    assert stored["venue_preparation_updated_by"] == staff_id
    assert stored["venue_preparation_updated_at"] is not None
    assert stored["venue_preparation_version"] == 2
