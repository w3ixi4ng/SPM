"""TC-EVENTS-455 (was TC-EVENTS-126): real S-26 Events persistence and
authorization, and S-26 AC2 -- preparation only after the Safety Officer's
approval."""

import uuid

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, requires_env

pytestmark = requires_env
PASSWORD = "correct-horse-battery-staple"


def make_user(admin, role):
    email = f"spm-test-s26-{role}-{uuid.uuid4().hex[:8]}@example.com"
    created = admin.auth.admin.create_user({
        "email": email,
        "password": PASSWORD,
        "email_confirm": True,
        "app_metadata": {"role": role},
    })
    return {"id": str(created.user.id), "email": email}


def cookie(auth_client, user):
    signed_in = auth_client.auth.sign_in_with_password({
        "email": user["email"], "password": PASSWORD,
    })
    return {"Cookie": f"sb_access_token={signed_in.session.access_token}"}


def test_equipment_preparation_round_trip(admin, auth_client):
    organiser = make_user(admin, "event_organiser")
    coordinator = make_user(admin, "event_coordinator")
    support = make_user(admin, "technical_support")
    other_support = make_user(admin, "technical_support")
    safety_officer = make_user(admin, "safety_officer")
    event_id = planning_id = None

    def insert_event(status, name, start, end, **extra):
        return admin.schema("events").table("events").insert({
            "organiser_id": organiser["id"],
            "assigned_coordinator_id": coordinator["id"],
            "status": status,
            "name": name,
            "purpose": "Verify preparation persistence",
            "start_date": "2026-11-20",
            "start_time": start,
            "end_date": "2026-11-20",
            "end_time": end,
            "expected_attendance": 40,
            "decision": "approved",
            "decided_at": "2026-10-01T00:00:00Z",
            "submitted_at": "2026-09-30T00:00:00Z",
            "technical_support_required": True,
            "assigned_technical_support_id": support["id"],
            "technical_support_assigned_at": "2026-10-01T01:00:00Z",
            **extra,
        }).execute().data[0]

    try:
        event = insert_event(
            "confirmed", "S-26 integration event", "09:00", "12:00",
            safety_decision="approved",
            safety_officer_id=safety_officer["id"],
            safety_decided_at="2026-10-05T00:00:00Z",
        )
        event_id = event["id"]
        planning_id = insert_event("planning", "S-26 integration event, not yet approved", "13:00", "16:00")["id"]
        initial = admin.schema("events").table("events").select(
            "equipment_preparation_status,equipment_preparation_updated_by,equipment_preparation_updated_at"
        ).eq("id", event_id).execute().data[0]
        assert initial["equipment_preparation_status"] == "not_started"
        assert initial["equipment_preparation_updated_by"] is None
        assert initial["equipment_preparation_updated_at"] is None

        support_headers = cookie(auth_client, support)
        for value in ("in_progress", "ready"):
            response = httpx.put(
                f"{GATEWAY_BASE_URL}/events/support-assigned/{event_id}/equipment-preparation",
                headers=support_headers,
                json={"status": value},
                timeout=15.0,
            )
            assert response.status_code == 200, response.text
            assert response.json()["equipment_preparation_status"] == value

        support_read = httpx.get(
            f"{GATEWAY_BASE_URL}/events/support-assigned/{event_id}",
            headers=support_headers,
            timeout=15.0,
        )
        assert support_read.status_code == 200, support_read.text
        coordinator_read = httpx.get(
            f"{GATEWAY_BASE_URL}/events/assigned/{event_id}",
            headers=cookie(auth_client, coordinator),
            timeout=15.0,
        )
        assert coordinator_read.status_code == 200, coordinator_read.text
        assert support_read.json()["equipment_preparation_status"] == "ready"
        assert coordinator_read.json()["equipment_preparation_status"] == "ready"

        denied = httpx.put(
            f"{GATEWAY_BASE_URL}/events/support-assigned/{event_id}/equipment-preparation",
            headers=cookie(auth_client, other_support),
            json={"status": "not_started"},
            timeout=15.0,
        )
        assert denied.status_code == 404, denied.text

        stored = admin.schema("events").table("events").select(
            "equipment_preparation_status,equipment_preparation_updated_by,equipment_preparation_updated_at"
        ).eq("id", event_id).execute().data[0]
        assert stored["equipment_preparation_status"] == "ready"
        assert stored["equipment_preparation_updated_by"] == support["id"]
        assert stored["equipment_preparation_updated_at"] is not None

        # S-26 AC2: an event the Safety Officer hasn't approved can't be prepared.
        refused = httpx.put(
            f"{GATEWAY_BASE_URL}/events/support-assigned/{planning_id}/equipment-preparation",
            headers=support_headers,
            json={"status": "ready"},
            timeout=15.0,
        )
        assert refused.status_code == 409, refused.text
        assert refused.json() == {
            "detail": "Equipment preparation can be updated once the Safety Officer has approved the event"
        }
        untouched = admin.schema("events").table("events").select(
            "equipment_preparation_status,equipment_preparation_updated_by,equipment_preparation_updated_at"
        ).eq("id", planning_id).execute().data[0]
        assert untouched == {
            "equipment_preparation_status": "not_started",
            "equipment_preparation_updated_by": None,
            "equipment_preparation_updated_at": None,
        }
    finally:
        for created in (event_id, planning_id):
            if created:
                admin.schema("events").table("events").delete().eq("id", created).execute()
        for user in (organiser, coordinator, support, other_support, safety_officer):
            admin.auth.admin.delete_user(user["id"])
