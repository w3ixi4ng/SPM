"""TC-EVENTS-131: real S-18 edit, lifecycle, and audit boundary."""

import uuid

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, requires_env

pytestmark = requires_env
PASSWORD = "correct-horse-battery-staple"


def make_user(admin, role):
    email = f"spm-test-s18-{role}-{uuid.uuid4().hex[:8]}@example.com"
    created = admin.auth.admin.create_user({
        "email": email, "password": PASSWORD, "email_confirm": True,
        "app_metadata": {"role": role},
    })
    return {"id": str(created.user.id), "email": email}


def cookie(auth_client, user):
    signed_in = auth_client.auth.sign_in_with_password({"email": user["email"], "password": PASSWORD})
    return {"Cookie": f"sb_access_token={signed_in.session.access_token}"}


def test_coordinator_edit_lifecycle_and_audit_round_trip(admin, auth_client):
    organiser = make_user(admin, "event_organiser")
    coordinator = make_user(admin, "event_coordinator")
    other = make_user(admin, "event_coordinator")
    officer = make_user(admin, "safety_officer")
    event_id = None
    try:
        review = {
            "review_number": 1, "decision": "approved", "reason": None,
            "safety_officer_id": officer["id"], "decided_at": "2026-10-18T09:00:00Z",
        }
        event = admin.schema("events").table("events").insert({
            "organiser_id": organiser["id"],
            "assigned_coordinator_id": coordinator["id"],
            "status": "preparation",
            "name": "S-18 integration event",
            "purpose": "Original description",
            "start_date": "2026-11-20", "start_time": "09:00",
            "end_date": "2026-11-20", "end_time": "12:00",
            "expected_attendance": 40,
            "decision": "approved", "decided_at": "2026-10-01T00:00:00Z",
            "submitted_at": "2026-09-30T00:00:00Z",
            "safety_decision": "approved", "safety_officer_id": officer["id"],
            "safety_decided_at": review["decided_at"], "safety_review_history": [review],
            "equipment_preparation_status": "ready",
        }).execute().data[0]
        event_id = event["id"]
        headers = cookie(auth_client, coordinator)
        base = f"{GATEWAY_BASE_URL}/events/assigned/{event_id}"

        routine = httpx.patch(base, headers=headers, json={
            "expected_version": 0,
            "purpose": "Updated description",
            "contact_name": "Sam Lee",
            "contact_email": "sam.lee@example.com",
            "contact_phone": "+65 6123 4567",
            "internal_notes": "Call on arrival",
        }, timeout=15.0)
        assert routine.status_code == 200, routine.text
        assert routine.json()["status"] == "preparation"
        assert routine.json()["edit_version"] == 1

        preview = httpx.post(f"{base}/edit-impact", headers=headers, json={
            "expected_version": 1, "expected_attendance": 55,
        }, timeout=15.0)
        assert preview.status_code == 200, preview.text
        assert preview.json()["significant_fields"] == ["expected_attendance"]

        changed = httpx.patch(base, headers=headers, json={
            "expected_version": 1, "impact_accepted": True,
            "expected_attendance": 55,
        }, timeout=15.0)
        assert changed.status_code == 200, changed.text
        assert changed.json()["status"] == "planning"
        assert changed.json()["safety_recheck_required"] is True
        assert changed.json()["equipment_preparation_status"] == "ready"
        assert changed.json()["safety_review_history"] == [review]

        hidden = httpx.patch(base, headers=cookie(auth_client, other), json={
            "expected_version": 2, "purpose": "No access",
        }, timeout=15.0)
        assert hidden.status_code == 404

        stored = admin.schema("events").table("events").select(
            "purpose,contact_name,expected_attendance,status,edit_version,edit_history,safety_review_history,equipment_preparation_status"
        ).eq("id", event_id).execute().data[0]
        assert stored["purpose"] == "Updated description"
        assert stored["expected_attendance"] == 55
        assert stored["edit_version"] == 2
        assert len(stored["edit_history"]) == 2
        assert all(entry["changed_by"] == coordinator["id"] for entry in stored["edit_history"])
        assert stored["safety_review_history"] == [review]
        assert stored["equipment_preparation_status"] == "ready"
        assert stored["status"] == "planning"
    finally:
        if event_id:
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        for user in (organiser, coordinator, other, officer):
            admin.auth.admin.delete_user(user["id"])
