"""TC-VENUEBOOKINGS-138 (S-78 revision): approving a replacement venue
returns a confirmed event to planning, through Kong and the real services.

Proves what the unit fakes can't: venue_bookings reaches the events
service's internal route with its service token, the reset satisfies the
events table's constraints, and the notices are stored for the Coordinator
and Organiser but not an Attendee.
"""

import httpx

from .conftest import GATEWAY_BASE_URL, _make_user, cookie_for, requires_env
from .test_replacement_venue import flagged_booking, row_for, more  # noqa: F401 -- more is a fixture

pytestmark = requires_env


# --- TC-VENUEBOOKINGS-138 --------------------------------------------------
def test_approving_a_replacement_replans_a_confirmed_event(admin, auth_client, world, more):
    add_venue, _ = more
    w = add_venue("W")
    events = admin.schema("events").table("events")
    event_id = world["event_id"]
    organiser_id = events.select("organiser_id").eq("id", event_id).execute().data[0]["organiser_id"]
    attendee = _make_user(admin, "attendee", "spm-test S78R Attendee")
    coordinator = cookie_for(auth_client, world["coordinator"])
    staff = cookie_for(auth_client, world["staff"])

    try:
        with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=30.0) as api:
            # 1. A venue can only be requested in planning, so flag the
            #    booking first, then confirm the event as a Safety Officer would.
            o = flagged_booking(api, world, coordinator, staff)
            events.update({
                "status": "confirmed", "safety_decision": "approved",
                "safety_officer_id": world["staff"]["id"], "safety_decided_at": "2026-10-03T00:00:00Z",
            }).eq("id", event_id).execute()
            admin.schema("registrations").table("registrations").insert(
                {"event_id": event_id, "attendee_id": attendee["id"]}
            ).execute()

            sent = api.post(f"/venue-bookings/{o}/replacement", headers=coordinator, json={"venue_id": w})
            assert sent.status_code == 201, sent.text
            r = sent.json()["id"]

            # 2. Venue Staff approve the replacement.
            decided = api.post(f"/venue-bookings/{r}/decision", headers=staff, json={"decision": "approved"})
            assert decided.status_code == 200, (
                f"{decided.text} -- is ASSIGNMENT_SERVICE_SECRET set in .env.test "
                "and the stack recreated with --build?"
            )
            assert row_for(api, coordinator, world, r)["status"] == "confirmed"

        # 3. The event is back in planning and needs a fresh safety check.
        stored = events.select("status,safety_decision,safety_recheck_required").eq(
            "id", event_id).execute().data[0]
        assert stored == {"status": "planning", "safety_decision": None, "safety_recheck_required": True}
        history = admin.schema("events").table("event_history").select("action,details").eq(
            "event_id", event_id).eq("action", "venue_replanned").execute().data
        assert len(history) == 1
        assert history[0]["details"]["previous_status"] == "confirmed"

        notices = admin.schema("notifications").table("notifications").select(
            "recipient_id,message").eq("event_id", event_id).execute().data
        told = {row["recipient_id"] for row in notices if "is back in planning" in row["message"]}
        assert told == {world["coordinator"]["id"], organiser_id}
        assert not any(row["recipient_id"] == attendee["id"] for row in notices)
    finally:
        # 4. The world fixture removes the event, its bookings and accounts.
        admin.schema("notifications").table("notifications").delete().eq("event_id", event_id).execute()
        admin.schema("registrations").table("registrations").delete().eq("event_id", event_id).execute()
        admin.auth.admin.delete_user(attendee["id"])
