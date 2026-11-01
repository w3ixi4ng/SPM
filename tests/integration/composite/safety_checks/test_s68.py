"""S-68 across Events, Registrations, Notifications and Safety Checks."""

import uuid

import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, make_user, requires_env

pytestmark = requires_env


def test_real_reconfirmation_notifies_only_current_registrations(admin, auth_client):
    organiser = make_user(admin, "event_organiser")
    coordinator = make_user(admin, "event_coordinator")
    officer = make_user(admin, "safety_officer")
    registered = [make_user(admin, "attendee") for _ in range(2)]
    waiting = make_user(admin, "attendee")
    unrelated = make_user(admin, "attendee")
    users = [organiser, coordinator, officer, *registered, waiting, unrelated]
    event_id = str(uuid.uuid4())
    name = f"spm-test S-68 {uuid.uuid4().hex[:8]}"
    try:
        admin.schema("events").table("events").insert({
            "id": event_id,
            "organiser_id": organiser["id"],
            "assigned_coordinator_id": coordinator["id"],
            "status": "pending_safety_check",
            "name": name,
            "purpose": "Prove attendee reschedule notifications",
            "start_date": "2026-11-20",
            "start_time": "13:00",
            "end_date": "2026-11-20",
            "end_time": "16:00",
            "expected_attendance": 30,
            "decision": "approved",
            "decided_at": "2026-09-30T09:00:00Z",
            "submitted_at": "2026-09-29T09:00:00Z",
            "safety_review_history": [{
                "review_number": 1,
                "decision": "approved",
                "reason": None,
                "safety_officer_id": officer["id"],
                "decided_at": "2026-10-01T09:00:00Z",
            }],
        }).execute()
        admin.schema("events").table("event_history").insert({
            "event_id": event_id,
            "actor_id": coordinator["id"],
            "actor_role": "event_coordinator",
            "category": "edit",
            "action": "edited",
            "details": {"changes": {
                "start_date": {"before": "2026-11-18", "after": "2026-11-20"},
                "start_time": {"before": "09:00:00", "after": "13:00:00"},
                "end_date": {"before": "2026-11-18", "after": "2026-11-20"},
                "end_time": {"before": "12:00:00", "after": "16:00:00"},
            }},
            "occurred_at": "2026-10-05T09:00:00Z",
        }).execute()
        admin.schema("registrations").table("registrations").insert([
            {"event_id": event_id, "attendee_id": person["id"]}
            for person in registered
        ]).execute()
        admin.schema("registrations").table("waiting_list").insert({
            "event_id": event_id,
            "attendee_id": waiting["id"],
        }).execute()

        approved = httpx.post(
            f"{GATEWAY_BASE_URL}/safety-checks/{event_id}/decision",
            headers=cookie_for(auth_client, officer),
            json={"decision": "approved"},
            timeout=20.0,
        )

        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "confirmed"
        rows = admin.schema("notifications").table("notifications").select(
            "recipient_id,event_name,kind,message,deduplication_key"
        ).eq("event_id", event_id).eq("kind", "event_schedule_changed").execute().data
        assert {row["recipient_id"] for row in rows} == {
            person["id"] for person in registered
        }
        assert all(row["event_name"] == name for row in rows)
        assert all("20 Nov 2026, 1:00 pm to 4:00 pm" in row["message"] for row in rows)
        assert waiting["id"] not in {row["recipient_id"] for row in rows}
        assert unrelated["id"] not in {row["recipient_id"] for row in rows}

        stale = httpx.post(
            f"{GATEWAY_BASE_URL}/safety-checks/{event_id}/decision",
            headers=cookie_for(auth_client, officer),
            json={"decision": "approved"},
            timeout=20.0,
        )
        assert stale.status_code == 409, stale.text
        repeated = admin.schema("notifications").table("notifications").select("id").eq(
            "event_id", event_id
        ).eq("kind", "event_schedule_changed").execute().data
        assert len(repeated) == 2
    finally:
        admin.schema("notifications").table("notifications").delete().eq(
            "event_id", event_id
        ).execute()
        admin.schema("registrations").table("registrations").delete().eq(
            "event_id", event_id
        ).execute()
        admin.schema("registrations").table("waiting_list").delete().eq(
            "event_id", event_id
        ).execute()
        admin.schema("events").table("events").delete().eq("id", event_id).execute()
        for user in users:
            admin.auth.admin.delete_user(user["id"])
