"""Real service/database round trip for the events atomic service."""

import httpx
import pytest

from .conftest import BASE_URL, GATEWAY_BASE_URL, requires_env

pytestmark = requires_env


def test_draft_to_submission_round_trip(organiser_session):
    headers = {
        "Cookie": f"sb_access_token={organiser_session['access_token']}"
    }
    submitted = {
        "name": "Alumni networking evening",
        "purpose": "Connect alumni with graduating students",
        "event_date": "2026-10-20",
        "start_time": "18:00",
        "end_time": "21:00",
        "expected_attendance": 120,
        "venue": "Main auditorium",
        "equipment_requests": {"projector": 1},
    }

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=headers) as api:
        created = api.post("/events/drafts", json={"name": "Planning draft"})
        assert created.status_code == 201, created.text
        draft = created.json()
        organiser_session["event_ids"].append(draft["id"])
        assert draft["status"] == "draft"
        assert draft["organiser_id"] == organiser_session["user_id"]

        listed = api.get("/events")
        assert listed.status_code == 200, listed.text
        assert draft["id"] in {event["id"] for event in listed.json()}
        assert all(
            event["organiser_id"] == organiser_session["user_id"]
            for event in listed.json()
        )

        fetched = api.get(f"/events/{draft['id']}")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["id"] == draft["id"]

        updated = api.patch(
            f"/events/{draft['id']}", json={"purpose": "Initial planning"}
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["purpose"] == "Initial planning"

        final = api.post(f"/events/{draft['id']}/submit", json=submitted)
        assert final.status_code == 200, final.text
        assert final.json()["status"] == "submitted"
        assert final.json()["name"] == submitted["name"]


def test_kong_routes_every_event_operation(organiser_session):
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    submitted = {
        "name": "Gateway integration event",
        "purpose": "Verify every events route through Kong",
        "event_date": "2026-11-12",
        "start_time": "09:00",
        "end_time": "11:00",
        "expected_attendance": 40,
        "venue": "Seminar room",
        "equipment_requests": {"projector": 1},
    }

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0, headers=headers) as api:
        health = api.get("/events/health")
        assert health.status_code == 200, health.text
        assert health.json() == {"status": "ok"}

        created = api.post("/events/drafts", json={})
        assert created.status_code == 201, created.text
        draft = created.json()
        organiser_session["event_ids"].append(draft["id"])
        assert draft["organiser_id"] == organiser_session["user_id"]

        listed = api.get("/events")
        assert listed.status_code == 200, listed.text
        assert draft["id"] in {event["id"] for event in listed.json()}
        assert all(
            event["organiser_id"] == organiser_session["user_id"]
            for event in listed.json()
        )

        fetched = api.get(f"/events/{draft['id']}")
        assert fetched.status_code == 200, fetched.text

        updated = api.patch(f"/events/{draft['id']}", json={"name": "Gateway draft"})
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "Gateway draft"

        final = api.post(f"/events/{draft['id']}/submit", json=submitted)
        assert final.status_code == 200, final.text
        assert final.json()["status"] == "submitted"

        immediate = api.post("/events", json=submitted)
        assert immediate.status_code == 201, immediate.text
        organiser_session["event_ids"].append(immediate.json()["id"])
        assert immediate.json()["status"] == "submitted"
