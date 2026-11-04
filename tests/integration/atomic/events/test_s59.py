"""S-59 Events persistence and direct-port protection (TC-EVENTS-201)."""

import os

import httpx

from .conftest import BASE_URL, requires_env

pytestmark = requires_env


def test_change_request_is_stored_separately_and_one_pending_is_enforced(organiser_session, admin):
    token = organiser_session["access_token"]
    cookie = {"Cookie": f"sb_access_token={token}"}
    accepted = {
        "name": "S59 Events persistence", "purpose": "Verify proposal storage",
        "start_date": "2026-11-18", "start_time": "09:00",
        "end_date": "2026-11-18", "end_time": "12:00",
        "expected_attendance": 120,
    }
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as api:
        created = api.post("/events/drafts", headers=cookie, json=accepted)
        assert created.status_code == 201, created.text
        event_id = created.json()["id"]
        organiser_session["event_ids"].append(event_id)
        submitted = api.post(f"/events/{event_id}/submit", headers=cookie, json=accepted)
        assert submitted.status_code == 200, submitted.text
        event = submitted.json()
        body = {
            "expected_event_updated_at": event["updated_at"],
            "proposed_values": {
                "start_date": "2026-11-18", "start_time": "09:00",
                "end_date": "2026-11-18", "end_time": "12:00",
                "expected_attendance": 150, "venue": None,
                "special_requirements": None, "room_layout": None,
                "required_facilities": [], "required_accessibility": [],
            },
            "accepted_equipment": [], "proposed_equipment": [],
        }
        path = f"/events/{event_id}/change-request/internal"
        assert api.post(path, headers=cookie, json=body).status_code == 403
        trusted = {**cookie, "X-Assignment-Service-Token": os.environ["ASSIGNMENT_SERVICE_SECRET"]}
        sent = api.post(path, headers=trusted, json=body)
        assert sent.status_code == 201, sent.text
        duplicate = api.post(path, headers=trusted, json=body)
        assert duplicate.status_code == 409
        current = api.get(f"/events/{event_id}", headers=cookie)
        assert current.json()["expected_attendance"] == 120
        rows = admin.schema("events").table("change_requests").select("*").eq("event_id", event_id).execute().data
        assert len(rows) == 1
        assert rows[0]["requested_by"] == organiser_session["user_id"]
        assert rows[0]["submitted_at"] and rows[0]["status"] == "pending"
        assert rows[0]["accepted_values"]["expected_attendance"] == 120
        assert rows[0]["proposed_values"]["expected_attendance"] == 150


def test_stale_event_baseline_cannot_be_stored_as_a_change_request(organiser_session, admin):
    token = organiser_session["access_token"]
    cookie = {"Cookie": f"sb_access_token={token}"}
    accepted = {
        "name": "S59 Stale baseline", "purpose": "Verify stale rejection",
        "start_date": "2026-11-18", "start_time": "09:00",
        "end_date": "2026-11-18", "end_time": "12:00",
        "expected_attendance": 120,
    }
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as api:
        created = api.post("/events/drafts", headers=cookie, json=accepted)
        assert created.status_code == 201, created.text
        event_id = created.json()["id"]
        organiser_session["event_ids"].append(event_id)
        submitted = api.post(f"/events/{event_id}/submit", headers=cookie, json=accepted)
        assert submitted.status_code == 200, submitted.text
        stale_updated_at = submitted.json()["updated_at"]
        changed = api.patch(f"/events/{event_id}", headers=cookie, json={"expected_attendance": 130})
        assert changed.status_code == 200, changed.text
        assert changed.json()["expected_attendance"] == 130
        assert changed.json()["updated_at"] != stale_updated_at
        trusted = {**cookie, "X-Assignment-Service-Token": os.environ["ASSIGNMENT_SERVICE_SECRET"]}
        response = api.post(f"/events/{event_id}/change-request/internal", headers=trusted, json={
            "expected_event_updated_at": stale_updated_at,
            "proposed_values": {
                "start_date": "2026-11-18", "start_time": "09:00",
                "end_date": "2026-11-18", "end_time": "12:00",
                "expected_attendance": 150, "venue": None,
                "special_requirements": None, "room_layout": None,
                "required_facilities": [], "required_accessibility": [],
            },
            "accepted_equipment": [], "proposed_equipment": [],
        })
        assert response.status_code == 409, response.text
        assert api.get(f"/events/{event_id}", headers=cookie).json()["expected_attendance"] == 130
        assert admin.schema("events").table("change_requests").select("id").eq("event_id", event_id).execute().data == []
