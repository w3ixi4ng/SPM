"""S-59 proposal visibility and concurrent submission through Kong."""

from concurrent.futures import ThreadPoolExecutor
import uuid

import httpx

from .conftest import GATEWAY_BASE_URL, _make_user, request_with_retry, requires_env

pytestmark = requires_env

EVENT = {
    "name": "S59 Autumn Forum", "purpose": "Change request integration",
    "start_date": "2026-11-18", "start_time": "09:00",
    "end_date": "2026-11-18", "end_time": "12:00",
    "expected_attendance": 120,
}


def cookie(session):
    return {"Cookie": f"sb_access_token={session['access_token']}"}


def proposal(attendance):
    return {"values": {
        "start_date": "2026-11-18", "start_time": "09:00",
        "end_date": "2026-11-18", "end_time": "12:00",
        "expected_attendance": attendance, "venue": None,
        "special_requirements": None, "room_layout": None,
        "required_facilities": [], "required_accessibility": [],
    }, "equipment": []}


def test_mixed_proposal_preserves_accepted_arrangements(
    organiser_session, coordinator_session, second_coordinator_session,
    technical_support_users, admin,
):
    tag = uuid.uuid4().hex[:8]
    technician_id = technical_support_users[0]["id"]
    venue_staff = _make_user(admin, "venue_staff")
    attendee = _make_user(admin, "attendee")
    event_id = item_id = venue_id = None
    try:
        item_id = admin.schema("equipment").table("equipment").insert({
            "type": f"S59 Projector {tag}", "total_quantity": 10,
            "created_by": technician_id,
        }).execute().data[0]["id"]
        venue_id = admin.schema("venues").table("venues").insert({
            "name": f"S59 Hall {tag}", "location": "10 Anson Road",
            "capacity": 300, "room_layouts": ["theatre", "banquet"],
            "facilities": ["projector"], "created_by": venue_staff["id"],
            "operating_hours": [{"day": "wed", "open": "08:00:00", "close": "20:00:00"}],
        }).execute().data[0]["id"]
        event_id = admin.schema("events").table("events").insert({
            **EVENT, "name": f"S59 Autumn Forum {tag}",
            "organiser_id": organiser_session["user_id"],
            "assigned_coordinator_id": coordinator_session["user_id"],
            "status": "confirmed", "room_layout": "theatre",
            "submitted_at": "2026-10-01T00:00:00Z", "decision": "approved",
            "decided_at": "2026-10-02T00:00:00Z", "safety_decision": "approved",
            "safety_officer_id": technician_id,
            "safety_decided_at": "2026-10-03T00:00:00Z",
            "technical_support_required": True,
            "assigned_technical_support_id": technician_id,
            "technical_support_assigned_at": "2026-10-02T00:00:00Z",
            "technical_signoff_decision": "approved",
            "technical_signoff_by": technician_id,
            "technical_signoff_at": "2026-10-03T00:00:00Z",
        }).execute().data[0]["id"]
        organiser_session["event_ids"].append(event_id)
        admin.schema("equipment").table("requirements").insert({
            "event_id": event_id, "equipment_item_id": item_id,
            "required_quantity": 2,
            "recorded_by_coordinator_id": coordinator_session["user_id"],
        }).execute()
        admin.schema("bookings").table("bookings").insert({
            "event_id": event_id, "venue_id": venue_id,
            "coordinator_id": coordinator_session["user_id"],
            "coordinator_name": "Integration Tester",
            "coordinator_email": "integration@example.com",
            "booking_date": "2026-11-18", "start_time": "09:00",
            "end_time": "12:00", "event_name": f"S59 Autumn Forum {tag}",
            "event_purpose": "Change request integration",
            "expected_attendance": 120, "venue_name": f"S59 Hall {tag}",
            "status": "confirmed", "decided_by": venue_staff["id"],
            "decided_at": "2026-10-03T00:00:00Z",
        }).execute()
        admin.schema("registrations").table("registrations").insert({
            "event_id": event_id, "attendee_id": attendee["id"],
        }).execute()

        path = f"/event-requests/{event_id}/change-requests"
        with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as api:
            before = request_with_retry(api, "GET", path, headers=cookie(organiser_session))
            assert before.status_code == 200, before.text
            assert before.json()["equipment"][0]["required_quantity"] == 2
            values = proposal(150)["values"] | {"room_layout": "banquet"}
            sent = request_with_retry(api, "POST", path, headers=cookie(organiser_session), json={
                "values": values,
                "equipment": [{"equipment_item_id": item_id, "required_quantity": 3}],
            })
            assert sent.status_code == 201, sent.text
            assert sent.json()["requested_by"] == organiser_session["user_id"]
            assert sent.json()["submitted_at"]
            for session in (organiser_session, coordinator_session):
                visible = request_with_retry(api, "GET", path, headers=cookie(session))
                assert visible.status_code == 200, visible.text
                change = visible.json()["requests"][0]
                assert change["status"] == "pending"
                assert change["accepted_values"]["expected_attendance"] == 120
                assert change["proposed_values"]["expected_attendance"] == 150
                assert change["accepted_equipment"][0]["required_quantity"] == 2
                assert change["proposed_equipment"][0]["required_quantity"] == 3
            assert request_with_retry(api, "GET", path, headers=cookie(second_coordinator_session)).status_code == 404

        stored = admin.schema("events").table("events").select(
            "status,expected_attendance,room_layout,assigned_technical_support_id,technical_signoff_decision"
        ).eq("id", event_id).execute().data[0]
        assert stored == {
            "status": "confirmed", "expected_attendance": 120,
            "room_layout": "theatre", "assigned_technical_support_id": technician_id,
            "technical_signoff_decision": "approved",
        }
        assert admin.schema("equipment").table("requirements").select("required_quantity").eq("event_id", event_id).execute().data[0]["required_quantity"] == 2
        assert admin.schema("bookings").table("bookings").select("status").eq("event_id", event_id).execute().data[0]["status"] == "confirmed"
        assert admin.schema("registrations").table("registrations").select("attendee_id").eq("event_id", event_id).execute().data[0]["attendee_id"] == attendee["id"]
    finally:
        if event_id:
            admin.schema("registrations").table("registrations").delete().eq("event_id", event_id).execute()
            admin.schema("bookings").table("bookings").delete().eq("event_id", event_id).execute()
            admin.schema("equipment").table("requirements").delete().eq("event_id", event_id).execute()
        if venue_id:
            admin.schema("venues").table("venues").delete().eq("id", venue_id).execute()
        if item_id:
            admin.schema("equipment").table("equipment").delete().eq("id", item_id).execute()
        admin.auth.admin.delete_user(attendee["id"])
        admin.auth.admin.delete_user(venue_staff["id"])


def test_unassigned_submitted_request_survives_assignment_and_is_scoped(
    organiser_session, coordinator_session, second_coordinator_session,
    lead_session, admin,
):
    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as api:
        created = request_with_retry(api, "POST", "/event-requests", headers=cookie(organiser_session), json=EVENT)
        assert created.status_code == 201, created.text
        event_id = created.json()["id"]
        organiser_session["event_ids"].append(event_id)
        unchanged = request_with_retry(api, "POST", f"/event-requests/{event_id}/change-requests",
            headers=cookie(organiser_session), json=proposal(120))
        assert unchanged.status_code == 422
        path = f"/event-requests/{event_id}/change-requests"
        sent = request_with_retry(api, "POST", path, headers=cookie(organiser_session), json=proposal(150))
        assert sent.status_code == 201, sent.text
        assert sent.json()["status"] == "pending"
        assert sent.json()["requested_by"] == organiser_session["user_id"]
        assert sent.json()["submitted_at"]
        assert request_with_retry(api, "POST", path, headers=cookie(organiser_session), json=proposal(180)).status_code == 409
        assert request_with_retry(api, "POST", path, headers=cookie(coordinator_session), json=proposal(180)).status_code == 403
        before = request_with_retry(api, "GET", path, headers=cookie(organiser_session))
        assert before.status_code == 200 and len(before.json()["requests"]) == 1
        assert before.json()["event"]["assigned_coordinator_id"] is None

        assigned = request_with_retry(api, "POST", f"/event-requests/{event_id}/assignment",
            headers=cookie(lead_session), json={"coordinator_id": coordinator_session["user_id"]})
        assert assigned.status_code == 200, assigned.text
        visible = request_with_retry(api, "GET", path, headers=cookie(coordinator_session))
        assert visible.status_code == 200 and visible.json()["requests"][0]["proposed_values"]["expected_attendance"] == 150
        assert request_with_retry(api, "GET", path, headers=cookie(second_coordinator_session)).status_code == 404
        stored = admin.schema("events").table("events").select("expected_attendance,status").eq("id", event_id).execute().data[0]
        assert stored == {"expected_attendance": 120, "status": "submitted"}


def test_two_concurrent_submissions_leave_one_pending_row(organiser_session, admin):
    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as api:
        created = request_with_retry(api, "POST", "/event-requests", headers=cookie(organiser_session), json={**EVENT, "name": "S59 Concurrent Forum"})
        assert created.status_code == 201, created.text
        event_id = created.json()["id"]
        organiser_session["event_ids"].append(event_id)

    def submit(attendance):
        with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as api:
            return request_with_retry(api, "POST", f"/event-requests/{event_id}/change-requests",
                headers=cookie(organiser_session), json=proposal(attendance)).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, (150, 180)))
    assert sorted(statuses) == [201, 409]
    rows = admin.schema("events").table("change_requests").select("status").eq("event_id", event_id).execute().data
    assert rows == [{"status": "pending"}]
