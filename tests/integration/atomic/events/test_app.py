"""Real service/database round trip for the events atomic service."""

import uuid

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
        "start_date": "2026-10-20",
        "start_time": "18:00",
        "end_date": "2026-10-20",
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
        # The submission is recorded, not just the state change: organiser_id
        # says who, submitted_at says when. A real column and a real write,
        # which is the part only this test can prove.
        assert final.json()["submitted_at"] is not None
        assert final.json()["organiser_id"] == organiser_session["user_id"]


def test_kong_routes_every_event_operation(organiser_session):
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    submitted = {
        "name": "Gateway integration event",
        "purpose": "Verify every events route through Kong",
        "start_date": "2026-11-12",
        "start_time": "09:00",
        "end_date": "2026-11-12",
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


# --- TC-EVENTS-103 ---------------------------------------------------------
def test_coordinator_load_and_internal_assignment_round_trip(admin):
    """Seeds rows directly -- these two internal routes have no browser-facing
    equivalent to drive them through, so there is no organiser session here.
    """
    coordinator_id = str(uuid.uuid4())
    organiser_id = str(uuid.uuid4())
    event_ids: list[str] = []

    try:
        submitted_row = (
            admin.schema("events")
            .table("events")
            .insert(
                {
                    "organiser_id": organiser_id,
                    "status": "submitted",
                    "name": "Coordinator load check",
                    "purpose": "Prove overlap detection against real rows",
                    "start_date": "2026-11-05",
                    "start_time": "09:00",
                    "end_date": "2026-11-05",
                    "end_time": "11:00",
                    "expected_attendance": 10,
                    "venue": "Room 1",
                    "assigned_coordinator_id": coordinator_id,
                    "submitted_at": "2026-09-24T00:00:00Z",
                }
            )
            .execute()
        )
        event_ids.append(submitted_row.data[0]["id"])

        # A draft can never legitimately carry an assignment through the API
        # (POST /events/drafts accepts no such field) -- inserted directly to
        # prove the query excludes one anyway, not just that the API never
        # produces one.
        draft_row = (
            admin.schema("events")
            .table("events")
            .insert(
                {
                    "organiser_id": organiser_id,
                    "status": "draft",
                    "assigned_coordinator_id": coordinator_id,
                    "start_date": "2026-11-05",
                    "start_time": "13:00",
                    "end_date": "2026-11-05",
                    "end_time": "14:00",
                }
            )
            .execute()
        )
        event_ids.append(draft_row.data[0]["id"])

        with httpx.Client(base_url=BASE_URL, timeout=15.0) as api:
            window = lambda start, end: {  # noqa: E731
                "coordinator_ids": [coordinator_id],
                "start_date": "2026-11-05",
                "start_time": start,
                "end_date": "2026-11-05",
                "end_time": end,
            }

            overlapping = api.post("/events/coordinator-load", json=window("10:00", "12:00"))
            assert overlapping.status_code == 200, overlapping.text
            result = overlapping.json()[0]
            assert result["conflict"] is True
            assert result["assigned_count"] == 1  # the draft is never counted

            back_to_back = api.post("/events/coordinator-load", json=window("11:00", "12:00"))
            assert back_to_back.status_code == 200, back_to_back.text
            assert back_to_back.json()[0]["conflict"] is False

            over_the_draft = api.post("/events/coordinator-load", json=window("13:00", "14:00"))
            assert over_the_draft.status_code == 200, over_the_draft.text
            assert over_the_draft.json()[0]["conflict"] is False
    finally:
        for event_id in event_ids:
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
