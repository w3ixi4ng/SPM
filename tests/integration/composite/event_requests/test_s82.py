"""TC-EVENTREQUESTS-123: real actions through Kong show up, with names, in
the assigned Coordinator's and a Lead's change history (S-82)."""

import uuid

import httpx

from .conftest import GATEWAY_BASE_URL, request_with_retry, requires_env

pytestmark = requires_env


def headers(session):
    return {"Cookie": f"sb_access_token={session['access_token']}"}


def test_real_actions_show_up_in_the_history(
    organiser_session, coordinator_session, second_coordinator_session, lead_session, admin,
):
    event = {
        "name": f"S-82 History {uuid.uuid4().hex[:6]}",
        "purpose": "S-82 integration round trip",
        "start_date": "2026-11-18", "start_time": "09:00",
        "end_date": "2026-11-18", "end_time": "12:00",
        "expected_attendance": 40,
    }
    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as api:
        created = request_with_retry(api, "POST", "/event-requests", headers=headers(organiser_session), json=event)
        assert created.status_code == 201, created.text
        event_id = created.json()["id"]
        organiser_session["event_ids"].append(event_id)

        assigned = request_with_retry(
            api, "POST", f"/event-requests/{event_id}/assignment",
            headers=headers(lead_session), json={"coordinator_id": coordinator_session["user_id"]},
        )
        assert assigned.status_code == 200, assigned.text
        approved = request_with_retry(
            api, "POST", f"/events/{event_id}/decision",
            headers=headers(coordinator_session), json={"decision": "approved"},
        )
        assert approved.status_code == 200, approved.text

        path = f"/event-requests/{event_id}/history"
        as_coordinator = request_with_retry(api, "GET", path, headers=headers(coordinator_session))
        as_lead = request_with_retry(api, "GET", path, headers=headers(lead_session))
        as_other = request_with_retry(api, "GET", path, headers=headers(second_coordinator_session))

    names = {
        row["id"]: row["name"]
        for row in admin.schema("users").table("users").select("id,name").in_("id", [
            organiser_session["user_id"], coordinator_session["user_id"], lead_session["user_id"],
        ]).execute().data
    }
    assert as_coordinator.status_code == 200, as_coordinator.text
    body = as_coordinator.json()
    assert body["event_name"] == event["name"]
    assert [
        (entry["action"], entry["actor"]["id"], entry["actor"]["name"]) for entry in body["entries"]
    ] == [
        ("request_approved", coordinator_session["user_id"], names[coordinator_session["user_id"]]),
        ("coordinator_assigned", lead_session["user_id"], names[lead_session["user_id"]]),
        ("submitted", organiser_session["user_id"], names[organiser_session["user_id"]]),
    ]
    assert body["people"] == {coordinator_session["user_id"]: names[coordinator_session["user_id"]]}

    assert as_lead.status_code == 200, as_lead.text
    assert as_lead.json()["entries"] == body["entries"]
    assert as_other.status_code == 404
