"""S-63 real Events-to-Notifications boundaries through Kong."""

import uuid

import httpx

from .conftest import GATEWAY_BASE_URL, requires_env

pytestmark = requires_env


def _headers(session):
    return {"Cookie": f"sb_access_token={session['access_token']}"}


def _event(organiser_id, coordinator_id, status, name):
    event = {
        "organiser_id": organiser_id,
        "assigned_coordinator_id": coordinator_id,
        "status": status,
        "name": name,
        "purpose": "Prove S-63 organiser notifications",
        "start_date": "2026-11-18",
        "start_time": "09:00",
        "end_date": "2026-11-18",
        "end_time": "12:00",
        "expected_attendance": 40,
        "venue": "Seminar Room 3",
        "submitted_at": "2026-10-01T00:00:00Z",
    }
    if status == "planning":
        event.update({
            "decision": "approved",
            "decided_at": "2026-10-01T01:00:00Z",
        })
    return event


def _inbox(api, organiser, event_id, kind):
    response = api.get("/notifications", headers=_headers(organiser))
    assert response.status_code == 200, response.text
    return [
        row for row in response.json()
        if row["event_id"] == event_id and row["kind"] == kind
    ]


# --- TC-EVENTREQUESTS-204 -------------------------------------------------
def test_a_real_returned_outcome_reaches_the_organiser_inbox(
    admin, organiser_session, coordinator_session
):
    name = f"spm-test S-63 decision {uuid.uuid4().hex[:8]}"
    event = admin.schema("events").table("events").insert(_event(
        organiser_session["user_id"], coordinator_session["user_id"], "submitted", name
    )).execute().data[0]
    organiser_session["event_ids"].append(event["id"])

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        decided = api.post(
            f"/event-requests/{event['id']}/decision",
            headers=_headers(coordinator_session),
            json={
                "decision": "returned",
                "reason": "Missing contact details",
                "comment": "Add a telephone number",
            },
        )

        assert decided.status_code == 200, (
            f"{decided.text} -- apply the S-63 notifications.sql block to TEST"
        )
        assert decided.json()["status"] == "returned"
        [row] = _inbox(api, organiser_session, event["id"], "event_request_decision")
        assert row["event_name"] == name
        assert "returned for amendment" in row["message"]
        assert "Missing contact details" in row["message"]
        assert "Add a telephone number" in row["message"]
        assert "resubmit" in row["message"]


# --- TC-EVENTREQUESTS-205 -------------------------------------------------
def test_a_real_postponement_reaches_the_organiser_once(
    admin, organiser_session, coordinator_session
):
    name = f"spm-test S-63 schedule {uuid.uuid4().hex[:8]}"
    event = admin.schema("events").table("events").insert(_event(
        organiser_session["user_id"], coordinator_session["user_id"], "planning", name
    )).execute().data[0]
    organiser_session["event_ids"].append(event["id"])
    payload = {
        "expected_version": 0,
        "impact_accepted": True,
        "start_date": "2026-11-20",
        "end_date": "2026-11-20",
    }

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        moved = api.patch(
            f"/event-requests/{event['id']}/information",
            headers=_headers(coordinator_session),
            json=payload,
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["start_date"] == "2026-11-20"

        [row] = _inbox(api, organiser_session, event["id"], "event_schedule_changed")
        assert row["event_name"] == name
        assert "postponed" in row["message"]
        assert "18 Nov 2026 09:00–12:00" in row["message"]
        assert "20 Nov 2026 09:00–12:00" in row["message"]
        assert "Review the updated event details" in row["message"]

        stale = api.patch(
            f"/event-requests/{event['id']}/information",
            headers=_headers(coordinator_session),
            json=payload,
        )
        assert stale.status_code == 409, stale.text
        assert len(_inbox(
            api, organiser_session, event["id"], "event_schedule_changed"
        )) == 1
