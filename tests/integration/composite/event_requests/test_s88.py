"""S-88 real HTTP and Supabase persistence checks (TC-EVENTREQUESTS-113/114)."""

import httpx
from concurrent.futures import ThreadPoolExecutor

from .conftest import GATEWAY_BASE_URL, _make_user, request_with_retry, requires_env

pytestmark = requires_env

EVENT = {
    "name": "November Forum",
    "purpose": "S-88 integration round trip",
    "start_date": "2026-11-18", "start_time": "09:00",
    "end_date": "2026-11-18", "end_time": "12:00",
    "expected_attendance": 25,
}


def headers(token):
    return {"Cookie": f"sb_access_token={token}"}


def test_request_survives_refresh_is_scoped_and_actions_after_s84(
    organiser_session, coordinator_session, second_coordinator_session,
    lead_session, admin, auth_client,
):
    other_lead = _make_user(admin, "event_coordinator_lead")
    try:
        other_token = auth_client.auth.sign_in_with_password({
            "email": other_lead["email"], "password": other_lead["password"],
        }).session.access_token
        with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as api:
            created = request_with_retry(api, "POST", "/event-requests", headers=headers(organiser_session["access_token"]), json=EVENT)
            assert created.status_code == 201, created.text
            event_id = created.json()["id"]
            organiser_session["event_ids"].append(event_id)

            assigned = request_with_retry(api, "POST", f"/event-requests/{event_id}/assignment",
                                          headers=headers(lead_session["access_token"]),
                                          json={"coordinator_id": coordinator_session["user_id"]})
            assert assigned.status_code == 200, assigned.text
            assert assigned.json()["assigning_lead_id"] == lead_session["user_id"]

            sent = request_with_retry(api, "POST", f"/event-requests/{event_id}/reassignment-request",
                                      headers=headers(coordinator_session["access_token"]),
                                      json={"reason": "Cannot cover the November event"})
            assert sent.status_code == 201, sent.text
            assert sent.json()["status"] == "pending"
            duplicate = request_with_retry(api, "POST", f"/event-requests/{event_id}/reassignment-request",
                                           headers=headers(coordinator_session["access_token"]),
                                           json={"reason": "Cannot cover the November event"})
            assert duplicate.status_code == 409

            stored = admin.schema("events").table("events").select("assigned_coordinator_id").eq("id", event_id).execute().data[0]
            assert stored["assigned_coordinator_id"] == coordinator_session["user_id"]
            mine = request_with_retry(api, "GET", "/event-requests/reassignment-requests/mine",
                                      headers=headers(coordinator_session["access_token"]))
            assert next(row for row in mine.json() if row["event_id"] == event_id)["status"] == "pending"

            visible = request_with_retry(api, "GET", "/event-requests/reassignment-requests/lead",
                                         headers=headers(lead_session["access_token"]))
            row = next(row for row in visible.json() if row["event_id"] == event_id)
            assert row["requester_id"] == coordinator_session["user_id"]
            assert row["reason"] == "Cannot cover the November event"
            unrelated = request_with_retry(api, "GET", "/event-requests/reassignment-requests/lead",
                                           headers=headers(other_token))
            assert event_id not in {row["event_id"] for row in unrelated.json()}

            body = {"coordinator_id": second_coordinator_session["user_id"],
                    "expected_coordinator_id": coordinator_session["user_id"],
                    "expected_assignment_version": assigned.json()["coordinator_assignment_version"]}
            forbidden = request_with_retry(api, "POST", f"/event-requests/{event_id}/reassignment",
                                           headers=headers(other_token), json=body)
            assert forbidden.status_code == 404
            stale_transfer = request_with_retry(api, "POST", f"/event-requests/{event_id}/reassignment",
                                                headers=headers(lead_session["access_token"]),
                                                json={**body, "expected_assignment_version": 99})
            assert stale_transfer.status_code == 409
            still_pending = admin.schema("events").table("reassignment_requests").select("status").eq("event_id", event_id).execute().data[0]
            assert still_pending["status"] == "pending"

            moved = request_with_retry(api, "POST", f"/event-requests/{event_id}/reassignment",
                                       headers=headers(lead_session["access_token"]), json=body)
            assert moved.status_code == 200, moved.text
            assert moved.json()["assigned_coordinator_id"] == second_coordinator_session["user_id"]
            after = request_with_retry(api, "GET", "/event-requests/reassignment-requests/mine",
                                       headers=headers(coordinator_session["access_token"]))
            actioned = next(row for row in after.json() if row["event_id"] == event_id)
            assert actioned["status"] == "actioned"
            assert actioned["actioned_at"] is not None
            stale = request_with_retry(api, "POST", f"/event-requests/{event_id}/reassignment-request",
                                       headers=headers(coordinator_session["access_token"]),
                                       json={"reason": "Old owner retry"})
            assert stale.status_code == 404
    finally:
        admin.auth.admin.delete_user(other_lead["id"])


def test_concurrent_submissions_leave_one_pending_request(
    organiser_session, coordinator_session, lead_session, admin,
):
    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as api:
        created = request_with_retry(api, "POST", "/event-requests",
                                     headers=headers(organiser_session["access_token"]),
                                     json={**EVENT, "name": "Concurrent S-88 Forum"})
        assert created.status_code == 201, created.text
        event_id = created.json()["id"]
        organiser_session["event_ids"].append(event_id)
        assigned = request_with_retry(api, "POST", f"/event-requests/{event_id}/assignment",
                                      headers=headers(lead_session["access_token"]),
                                      json={"coordinator_id": coordinator_session["user_id"]})
        assert assigned.status_code == 200, assigned.text

    def submit():
        with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as api:
            return request_with_retry(api, "POST", f"/event-requests/{event_id}/reassignment-request",
                                      headers=headers(coordinator_session["access_token"]),
                                      json={"reason": "Concurrent handoff"}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(statuses) == [201, 409]
    rows = admin.schema("events").table("reassignment_requests").select("id,status").eq("event_id", event_id).execute().data
    assert len(rows) == 1 and rows[0]["status"] == "pending"
