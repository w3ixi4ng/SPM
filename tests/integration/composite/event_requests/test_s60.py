"""S-60 accepted decisions through Kong and both owning persistence services."""

import uuid
from concurrent.futures import ThreadPoolExecutor
import os

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, _make_user, request_with_retry, requires_env
from .test_s59 import EVENT, cookie, proposal
from tests.supabase_client import create_client


pytestmark = requires_env


def test_real_acceptance_preserves_arrangements(
    organiser_session, coordinator_session, second_coordinator_session,
    technical_support_users, admin,
):
    tag = uuid.uuid4().hex[:8]
    technician_id = technical_support_users[0]["id"]
    venue_staff = _make_user(admin, "venue_staff")
    attendee = _make_user(admin, "attendee")
    event_id = item_id = request_id = None
    venue_ids = []
    try:
        item_id = admin.schema("equipment").table("equipment").insert({
            "type": f"S60 Projector {tag}", "total_quantity": 10, "created_by": technician_id,
        }).execute().data[0]["id"]
        for capacity, name in ((130, "Hall A"), (220, "Hall B")):
            venue_ids.append(admin.schema("venues").table("venues").insert({
                "name": f"S60 {name} {tag}", "location": "10 Anson Road", "capacity": capacity,
                "room_layouts": ["theatre", "banquet"] if capacity == 220 else ["theatre"],
                "facilities": ["projector"], "created_by": venue_staff["id"],
                "operating_hours": [{"day": "wed", "open": "08:00:00", "close": "20:00:00"}],
            }).execute().data[0]["id"])
        event_id = admin.schema("events").table("events").insert({
            **EVENT, "name": f"S60 Forum {tag}", "organiser_id": organiser_session["user_id"],
            "assigned_coordinator_id": coordinator_session["user_id"], "status": "confirmed",
            "room_layout": "theatre", "submitted_at": "2026-10-01T00:00:00Z",
            "decision": "approved", "decided_at": "2026-10-02T00:00:00Z",
            "safety_decision": "approved", "safety_officer_id": technician_id,
            "safety_decided_at": "2026-10-03T00:00:00Z",
            "technical_support_required": True,
            "assigned_technical_support_id": technician_id,
            "technical_support_assigned_at": "2026-10-02T00:00:00Z",
            "technical_signoff_decision": "approved", "technical_signoff_by": technician_id,
            "technical_signoff_at": "2026-10-03T00:00:00Z",
        }).execute().data[0]["id"]
        organiser_session["event_ids"].append(event_id)
        admin.schema("equipment").table("requirements").insert({
            "event_id": event_id, "equipment_item_id": item_id, "required_quantity": 2,
            "recorded_by_coordinator_id": coordinator_session["user_id"],
        }).execute()
        for venue_id in venue_ids:
            admin.schema("bookings").table("bookings").insert({
                "event_id": event_id, "venue_id": venue_id,
                "coordinator_id": coordinator_session["user_id"],
                "coordinator_name": "Integration Tester", "coordinator_email": "integration@example.com",
                "booking_date": "2026-11-18", "start_time": "09:00", "end_time": "12:00",
                "event_name": f"S60 Forum {tag}", "event_purpose": "S-60 integration",
                "expected_attendance": 120, "venue_name": "S60 Hall", "status": "confirmed",
                "decided_by": venue_staff["id"], "decided_at": "2026-10-03T00:00:00Z",
            }).execute()
        admin.schema("registrations").table("registrations").insert({
            "event_id": event_id, "attendee_id": attendee["id"],
        }).execute()
        path = f"/event-requests/{event_id}/change-requests"
        with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
            sent = request_with_retry(api, "POST", path, headers=cookie(organiser_session), json={
                "values": {"start_date": "2026-11-18", "start_time": "09:00",
                           "end_date": "2026-11-18", "end_time": "12:00",
                           "expected_attendance": 150, "venue": None,
                           "special_requirements": None, "room_layout": "banquet",
                           "required_facilities": [], "required_accessibility": []},
                "equipment": [{"equipment_item_id": item_id, "required_quantity": 3}],
            })
            assert sent.status_code == 201, sent.text
            request_id = sent.json()["id"]
            review_path = f"{path}/{request_id}/review"
            review = request_with_retry(api, "GET", review_path, headers=cookie(coordinator_session))
            assert review.status_code == 200, review.text
            reviewed = review.json()
            codes = {(item["arrangement_id"], item["code"]) for item in reviewed["impacts"]}
            bookings = admin.schema("bookings").table("bookings").select("id,venue_id,status").eq("event_id", event_id).execute().data
            small = next(row["id"] for row in bookings if row["venue_id"] == venue_ids[0])
            large = next(row["id"] for row in bookings if row["venue_id"] == venue_ids[1])
            assert (small, "capacity") in codes and (small, "layout") in codes
            assert (large, "capacity") not in codes and (large, "layout") not in codes
            assert (item_id, "requirement") in codes
            assert request_with_retry(api, "GET", review_path, headers=cookie(second_coordinator_session)).status_code == 404

            accepted = request_with_retry(api, "POST", f"{path}/{request_id}/accept",
                headers=cookie(coordinator_session), json={
                    "expected_event_updated_at": reviewed["event"]["updated_at"],
                    "impact_ids": [item["id"] for item in reviewed["impacts"]],
                })
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["status"] == "accepted"
            assert accepted.json()["accepted_values"]["expected_attendance"] == 120
            assert accepted.json()["proposed_values"]["expected_attendance"] == 150
            assert accepted.json()["reviewed_by"] == coordinator_session["user_id"]
            assert accepted.json()["impact_acknowledged_at"]
            stored = admin.schema("events").table("events").select("status,expected_attendance,safety_decision,safety_recheck_required,assigned_technical_support_id,technical_signoff_decision").eq("id", event_id).single().execute().data
            assert stored["status"] == "planning" and stored["expected_attendance"] == 150
            assert stored["safety_decision"] is None and stored["safety_recheck_required"] is True
            assert stored["assigned_technical_support_id"] == technician_id
            assert stored["technical_signoff_decision"] == "approved"
            assert admin.schema("equipment").table("requirements").select("required_quantity").eq("event_id", event_id).single().execute().data["required_quantity"] == 3
            assert admin.schema("bookings").table("bookings").select("id,venue_id,status").eq("event_id", event_id).execute().data == bookings
            assert admin.schema("registrations").table("registrations").select("attendee_id").eq("event_id", event_id).single().execute().data["attendee_id"] == attendee["id"]
            blocked = request_with_retry(api, "POST", f"/safety-checks/coordinator/events/{event_id}/submit", headers=cookie(coordinator_session))
            assert blocked.status_code == 409, blocked.text
            assert any(item["code"] == "change_impact" for item in blocked.json()["outstanding"])
            again = request_with_retry(api, "POST", f"{path}/{request_id}/accept", headers=cookie(coordinator_session), json={
                "expected_event_updated_at": reviewed["event"]["updated_at"],
                "impact_ids": [item["id"] for item in reviewed["impacts"]],
                "operation_id": accepted.json()["operation_id"],
            })
            assert again.status_code == 200, again.text
    finally:
        if event_id:
            admin.schema("registrations").table("registrations").delete().eq("event_id", event_id).execute()
            admin.schema("bookings").table("bookings").delete().eq("event_id", event_id).execute()
            admin.schema("equipment").table("change_operations").delete().eq("event_id", event_id).execute()
            admin.schema("events").table("change_requests").delete().eq("event_id", event_id).execute()
            admin.schema("equipment").table("requirements").delete().eq("event_id", event_id).execute()
            admin.schema("equipment").table("requirement_changes").delete().eq("event_id", event_id).execute()
        for venue_id in venue_ids:
            admin.schema("venues").table("venues").delete().eq("id", venue_id).execute()
        if item_id:
            admin.schema("equipment").table("equipment").delete().eq("id", item_id).execute()
        admin.auth.admin.delete_user(attendee["id"])
        admin.auth.admin.delete_user(venue_staff["id"])


def test_rejection_releases_pending_slot_without_changing_accepted_event(
    organiser_session, coordinator_session, lead_session, admin,
):
    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        created = request_with_retry(api, "POST", "/event-requests",
            headers=cookie(organiser_session), json={**EVENT, "name": f"S60 Reject {uuid.uuid4().hex[:8]}"})
        assert created.status_code == 201, created.text
        event_id = created.json()["id"]
        organiser_session["event_ids"].append(event_id)
        assigned = request_with_retry(api, "POST", f"/event-requests/{event_id}/assignment",
            headers=cookie(lead_session), json={"coordinator_id": coordinator_session["user_id"]})
        assert assigned.status_code == 200, assigned.text
        path = f"/event-requests/{event_id}/change-requests"
        first = request_with_retry(api, "POST", path, headers=cookie(organiser_session), json=proposal(150))
        assert first.status_code == 201, first.text
        rejected = request_with_retry(api, "POST", f"{path}/{first.json()['id']}/reject",
            headers=cookie(coordinator_session), json={"reason": "  Venue unavailable  "})
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "rejected"
        assert rejected.json()["decision_reason"] == "Venue unavailable"
        assert rejected.json()["reviewed_by"] == coordinator_session["user_id"]
        assert rejected.json()["resolved_at"]
        stored = admin.schema("events").table("events").select("expected_attendance").eq("id", event_id).single().execute().data
        assert stored["expected_attendance"] == 120
        next_request = request_with_retry(api, "POST", path, headers=cookie(organiser_session), json=proposal(130))
        assert next_request.status_code == 201, next_request.text
        history = admin.schema("events").table("change_requests").select("status").eq("event_id", event_id).execute().data
        assert sorted(row["status"] for row in history) == ["pending", "rejected"]


@pytest.mark.parametrize("starting_status", ["confirmed", "preparation", "pending_safety_check"])
def test_significant_acceptance_requires_fresh_safety_for_each_lifecycle_state(
    starting_status, organiser_session, coordinator_session, admin,
):
    prior_review = [{
        "review_number": 1, "decision": "approved", "reason": None,
        "safety_officer_id": str(uuid.uuid4()), "decided_at": "2026-10-03T00:00:00Z",
    }]
    row = {
        **EVENT, "name": f"S60 Lifecycle {starting_status} {uuid.uuid4().hex[:8]}",
        "organiser_id": organiser_session["user_id"],
        "assigned_coordinator_id": coordinator_session["user_id"],
        "status": starting_status, "submitted_at": "2026-10-01T00:00:00Z",
        "decision": "approved", "decided_at": "2026-10-02T00:00:00Z",
        "safety_review_history": prior_review,
    }
    if starting_status != "pending_safety_check":
        row.update({"safety_decision": "approved", "safety_officer_id": prior_review[0]["safety_officer_id"],
                    "safety_decided_at": prior_review[0]["decided_at"]})
    event_id = admin.schema("events").table("events").insert(row).execute().data[0]["id"]
    organiser_session["event_ids"].append(event_id)
    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        path = f"/event-requests/{event_id}/change-requests"
        submitted = request_with_retry(api, "POST", path, headers=cookie(organiser_session), json=proposal(150))
        assert submitted.status_code == 201, submitted.text
        review = request_with_retry(api, "GET", f"{path}/{submitted.json()['id']}/review", headers=cookie(coordinator_session))
        assert review.status_code == 200, review.text
        accepted = request_with_retry(api, "POST", f"{path}/{submitted.json()['id']}/accept",
            headers=cookie(coordinator_session), json={
                "expected_event_updated_at": review.json()["event"]["updated_at"],
                "impact_ids": [item["id"] for item in review.json()["impacts"]],
            })
        assert accepted.status_code == 200, accepted.text
    stored = admin.schema("events").table("events").select(
        "status,expected_attendance,safety_recheck_required,safety_decision,safety_review_history"
    ).eq("id", event_id).single().execute().data
    assert stored == {
        "status": "planning", "expected_attendance": 150,
        "safety_recheck_required": True, "safety_decision": None,
        "safety_review_history": prior_review,
    }


def test_real_concurrent_acceptance_and_recovery(
    organiser_session, coordinator_session, lead_session, admin,
):
    """An interrupted two-owner operation retains its slot and recovers once."""
    event_id = None
    try:
        with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
            created = request_with_retry(api, "POST", "/event-requests",
                headers=cookie(organiser_session),
                json={**EVENT, "name": f"S60 Recovery {uuid.uuid4().hex[:8]}"})
            assert created.status_code == 201, created.text
            event_id = created.json()["id"]
            organiser_session["event_ids"].append(event_id)
            assigned = request_with_retry(api, "POST", f"/event-requests/{event_id}/assignment",
                headers=cookie(lead_session), json={"coordinator_id": coordinator_session["user_id"]})
            assert assigned.status_code == 200, assigned.text
            path = f"/event-requests/{event_id}/change-requests"
            submitted = request_with_retry(api, "POST", path,
                headers=cookie(organiser_session), json=proposal(150))
            assert submitted.status_code == 201, submitted.text
            request_id = submitted.json()["id"]
            baseline = admin.schema("events").table("events").select(
                "updated_at,expected_attendance"
            ).eq("id", event_id).single().execute().data
            operation_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

            def prepare(operation_id):
                store = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
                try:
                    row = store.schema("events").rpc("prepare_change_acceptance", {
                        "p_request_id": request_id,
                        "p_coordinator_id": coordinator_session["user_id"],
                        "p_operation_id": operation_id,
                        "p_impacts": [],
                        "p_expected_updated_at": baseline["updated_at"],
                    }).execute().data[0]
                    return row["operation_id"]
                except Exception as exc:
                    return getattr(exc, "code", None)

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(prepare, operation_ids))
            winners = [value for value in outcomes if value in operation_ids]
            assert len(winners) == 1, outcomes
            assert outcomes.count("23514") == 1, outcomes
            operation_id = winners[0]
            applying = admin.schema("events").table("change_requests").select(
                "status,operation_id"
            ).eq("id", request_id).single().execute().data
            assert applying == {"status": "applying", "operation_id": operation_id}
            assert admin.schema("events").table("events").select("expected_attendance").eq(
                "id", event_id).single().execute().data["expected_attendance"] == 120
            blocked = request_with_retry(api, "POST", path,
                headers=cookie(organiser_session), json=proposal(130))
            assert blocked.status_code == 409, blocked.text

            applied = admin.schema("equipment").rpc("apply_change_batch", {
                "p_operation_id": operation_id, "p_event_id": event_id,
                "p_actor_id": coordinator_session["user_id"],
                "p_baseline": [], "p_proposed": [],
            }).execute().data[0]
            assert applied["status"] == "applied"
            wrong_operation = next(value for value in operation_ids if value != operation_id)
            with pytest.raises(Exception) as failure:
                admin.schema("events").rpc("complete_change_acceptance", {
                    "p_request_id": request_id, "p_coordinator_id": coordinator_session["user_id"],
                    "p_operation_id": wrong_operation,
                }).execute()
            assert getattr(failure.value, "code", None) == "23514"
            assert admin.schema("events").table("change_requests").select("status").eq(
                "id", request_id).single().execute().data["status"] == "applying"
            assert admin.schema("equipment").table("change_operations").select("status").eq(
                "id", operation_id).single().execute().data["status"] == "applied"

            params = {"p_request_id": request_id, "p_coordinator_id": coordinator_session["user_id"],
                      "p_operation_id": operation_id}
            accepted = admin.schema("events").rpc("complete_change_acceptance", params).execute().data[0]
            assert accepted["status"] == "accepted"
            assert admin.schema("events").rpc("complete_change_acceptance", params).execute().data[0]["id"] == request_id
            assert admin.schema("equipment").rpc("finish_change_batch", {
                "p_operation_id": operation_id,
            }).execute().data[0]["status"] == "finalized"
            assert admin.schema("equipment").rpc("finish_change_batch", {
                "p_operation_id": operation_id,
            }).execute().data[0]["status"] == "finalized"
            assert admin.schema("events").table("events").select("expected_attendance").eq(
                "id", event_id).single().execute().data["expected_attendance"] == 150
            history = admin.schema("events").table("event_history").select("id").eq(
                "event_id", event_id).eq("action", "change_request_accepted").execute().data
            assert len(history) == 1
            reopened = request_with_retry(api, "POST", path,
                headers=cookie(organiser_session), json=proposal(130))
            assert reopened.status_code == 201, reopened.text
    finally:
        if event_id:
            admin.schema("equipment").table("change_operations").delete().eq("event_id", event_id).execute()
