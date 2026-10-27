"""S-93 trusted Auth availability across Kong, composite, and atomic ports."""

import httpx
import uuid

from .conftest import BASE_URL, EVENTS_BASE_URL, GATEWAY_BASE_URL, request_with_retry, requires_env
from .test_app import SUBMITTED

pytestmark = requires_env


def test_inactive_target_is_rejected_but_existing_work_can_be_transferred(
    organiser_session, coordinator, second_coordinator, lead_session, admin, auth_client, request,
):
    lead_headers = {"Cookie": f"sb_access_token={lead_session['access_token']}"}
    organiser_headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    existing = admin.auth.admin.get_user_by_id(coordinator).user
    admin.auth.admin.update_user_by_id(coordinator, {
        "app_metadata": {**existing.app_metadata, "team": "operations", "coordinator_active": False},
    })
    inactive_account = admin.auth.admin.get_user_by_id(coordinator).user
    assert inactive_account.app_metadata["role"] == "event_coordinator"
    assert inactive_account.app_metadata["team"] == "operations"
    signed_in = auth_client.auth.sign_in_with_password({
        "email": inactive_account.email, "password": "correct-horse-battery-staple",
    })
    assert signed_in.session.access_token
    with (
        httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15, headers=lead_headers) as gateway,
        httpx.Client(base_url=BASE_URL, timeout=15, headers=organiser_headers) as organiser_api,
        httpx.Client(base_url=EVENTS_BASE_URL, timeout=15, headers=lead_headers) as atomic,
    ):
        created = request_with_retry(organiser_api, "POST", "/event-requests", json={
            **SUBMITTED, "name": "S-93 eligibility and transfer",
        })
        assert created.status_code == 201, created.text
        event_id = created.json()["id"]
        organiser_session["event_ids"].append(event_id)

        candidates = request_with_retry(gateway, "GET", "/event-requests/coordinators")
        assert candidates.status_code == 200, candidates.text
        assert coordinator not in {item["id"] for item in candidates.json()}
        assert second_coordinator in {item["id"] for item in candidates.json()}
        status = request_with_retry(gateway, "GET", f"/event-requests/coordinators/{coordinator}/active-events")
        assert status.status_code == 200 and status.json()["coordinator"]["coordinator_active"] is False

        rejected = request_with_retry(gateway, "POST", f"/event-requests/{event_id}/assignment", json={"coordinator_id": coordinator})
        assert rejected.status_code == 422
        for credential in ({}, {"X-Assignment-Service-Token": "forged"}):
            bypass = request_with_retry(atomic, "POST", f"/internal/events/{event_id}/assignment", headers={**lead_headers, **credential}, json={"coordinator_id": coordinator})
            assert bypass.status_code == 403

        assigned = request_with_retry(gateway, "POST", f"/event-requests/{event_id}/assignment", json={"coordinator_id": second_coordinator})
        assert assigned.status_code == 200, assigned.text
        admin.schema("events").table("events").update({
            "status": "planning", "decision": "approved", "decided_at": "2026-10-02T00:00:00Z",
            "technical_support_required": True, "technical_support_details": "Check microphones",
            "assigned_technical_support_id": lead_session["user_id"],
            "technical_support_assigned_at": "2026-10-02T01:00:00Z",
            "internal_notes": "Preserve this event note",
            "edit_version": 1,
            "edit_history": [{
                "change_number": 1, "changed_by": second_coordinator,
                "changed_at": "2026-10-02T02:00:00Z",
                "changes": {"internal_notes": {"before": None, "after": "Preserve this event note"}},
            }],
        }).eq("id", event_id).execute()
        booking = admin.schema("bookings").table("bookings").insert({
            "event_id": event_id, "venue_id": str(uuid.uuid4()),
            "coordinator_id": second_coordinator, "coordinator_name": "Former Coordinator",
            "coordinator_email": "former@example.com", "booking_date": "2026-11-05",
            "start_time": "09:00", "end_time": "11:00", "event_name": "S-93 eligibility and transfer",
            "event_purpose": SUBMITTED["purpose"], "expected_attendance": 10,
            "venue_name": "Room 1",
        }).execute().data[0]
        request.addfinalizer(lambda booking_id=booking["id"]: admin.schema("bookings").table("bookings").delete().eq("id", booking_id).execute())
        item = admin.schema("equipment").table("equipment").insert({
            "type": f"S93 microphone {uuid.uuid4().hex[:8]}", "total_quantity": 10,
            "created_by": lead_session["user_id"],
        }).execute().data[0]
        request.addfinalizer(lambda item_id=item["id"]: admin.schema("equipment").table("equipment").delete().eq("id", item_id).execute())
        requirement = admin.schema("equipment").table("requirements").insert({
            "event_id": event_id, "equipment_item_id": item["id"],
            "required_quantity": 2, "recorded_by_coordinator_id": second_coordinator,
        }).execute().data[0]
        request.addfinalizer(lambda requirement_id=requirement["id"]: admin.schema("equipment").table("requirements").delete().eq("id", requirement_id).execute())
        pending_request = admin.schema("events").table("reassignment_requests").insert({
            "event_id": event_id, "event_name": "S-93 eligibility and transfer",
            "requester_id": second_coordinator, "assigning_lead_id": lead_session["user_id"],
            "assignment_version": 0, "reason": "Leaving the team",
        }).execute().data[0]
        before = admin.schema("events").table("events").select(
            "internal_notes,edit_history,technical_support_required,technical_support_details,assigned_technical_support_id,technical_support_assigned_at"
        ).eq("id", event_id).execute().data[0]
        admin.auth.admin.update_user_by_id(second_coordinator, {
            "app_metadata": {"role": "event_coordinator", "coordinator_active": False},
        })
        for credential in ({}, {"X-Assignment-Service-Token": "forged"}):
            bypass = request_with_retry(atomic, "POST", f"/internal/events/{event_id}/reassignment", headers={**lead_headers, **credential}, json={
                "coordinator_id": coordinator,
                "expected_coordinator_id": second_coordinator,
                "expected_assignment_version": 0,
            })
            assert bypass.status_code == 403
        inventory = request_with_retry(gateway, "GET", f"/event-requests/coordinators/{second_coordinator}/active-events")
        assert inventory.status_code == 200, inventory.text
        assert inventory.json()["active_assignment_count"] == 1
        assert inventory.json()["events"][0]["inactive_owner"] is True

        admin.auth.admin.update_user_by_id(coordinator, {
            "app_metadata": {**inactive_account.app_metadata, "coordinator_active": True},
        })
        restored = admin.auth.admin.get_user_by_id(coordinator).user
        assert restored.app_metadata["team"] == "operations"
        assert restored.app_metadata["coordinator_active"] is True
        moved = request_with_retry(gateway, "POST", f"/event-requests/{event_id}/reassignment", json={
            "coordinator_id": coordinator,
            "expected_coordinator_id": second_coordinator,
            "expected_assignment_version": 0,
        })
        assert moved.status_code == 200, moved.text
        assert moved.json()["coordinator_assignment_version"] == 1
        after_event = admin.schema("events").table("events").select(
            "internal_notes,edit_history,technical_support_required,technical_support_details,assigned_technical_support_id,technical_support_assigned_at"
        ).eq("id", event_id).execute().data[0]
        assert after_event == before
        assert admin.schema("bookings").table("bookings").select("id,event_id,coordinator_id").eq("id", booking["id"]).execute().data[0]["event_id"] == event_id
        assert admin.schema("equipment").table("requirements").select("id,event_id,required_quantity").eq("id", requirement["id"]).execute().data[0]["required_quantity"] == 2
        actioned = admin.schema("events").table("reassignment_requests").select("status,actioned_at").eq("id", pending_request["id"]).execute().data[0]
        assert actioned["status"] == "actioned" and actioned["actioned_at"]
        after = request_with_retry(gateway, "GET", f"/event-requests/coordinators/{second_coordinator}/active-events")
        assert after.status_code == 200 and after.json()["active_assignment_count"] == 0
