"""TC-VENUEBOOKINGS-139 (S-81 reopened): through Kong, the Coordinator
confirms a hold, the Venue Staff who placed it are told, and only then can
they approve it. Run after the S-81 confirmation blocks of bookings.sql and
notifications.sql on .env.test."""

import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env

NOT_CONFIRMED = "This hold can't be approved until the Event Coordinator confirms it."


def test_through_kong_the_coordinator_confirms_and_venue_staff_are_told(admin, auth_client, world):
    coordinator = cookie_for(auth_client, world["coordinator"])
    staff = cookie_for(auth_client, world["staff"])
    inbox = admin.schema("notifications").table("notifications")
    try:
        with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
            # 1. Requested, then held.
            created = api.post("/venue-bookings", headers=coordinator, json={
                "event_id": world["event_id"], "venue_id": world["venue_id"],
                "booking_date": "2026-11-12", "start_time": "09:00", "end_time": "12:00",
            })
            assert created.status_code == 201, created.text
            booking_id = created.json()["id"]
            held = api.post(f"/venue-bookings/{booking_id}/hold", headers=staff,
                            json={"expires_at": "2099-01-01T12:00:00+08:00"})
            assert held.status_code == 200, held.text

            # 2. Not approvable yet.
            refused = api.post(f"/venue-bookings/{booking_id}/decision", headers=staff, json={"decision": "approved"})
            assert refused.status_code == 409, refused.text
            assert refused.json()["detail"] == NOT_CONFIRMED

            # 3. The Coordinator confirms it.
            confirmed = api.post(f"/venue-bookings/{booking_id}/hold-confirmation", headers=coordinator)
            assert confirmed.status_code == 200, f"{confirmed.text} -- check the S-81 confirmation SQL is applied"
            assert confirmed.json()["hold_confirmed_by"] == world["coordinator"]["id"]

            # 4. The staff member who held it is told, then approves it.
            listed = api.get("/notifications", headers=staff)
            assert listed.status_code == 200, listed.text
            [notice] = [n for n in listed.json() if n["kind"] == "venue_hold_confirmed"]
            assert "12 Nov 2026, 09:00–12:00" in notice["message"], notice["message"]
            assert created.json()["venue_name"] in notice["message"]
            approved = api.post(f"/venue-bookings/{booking_id}/decision", headers=staff, json={"decision": "approved"})
            assert approved.status_code == 200, approved.text
            assert approved.json()["status"] == "confirmed"
    finally:
        inbox.delete().eq("event_id", world["event_id"]).execute()
