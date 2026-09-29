"""Real service round trip for the event_requests composite -- see TEST_CASES.md.

Every test below either blocks or exempts *every* coordinator that exists in
the project, not just the ones it created — GET /users/coordinators sees the
whole pool, so a leftover account from manual testing or an earlier run is
just as eligible as a fixture's, and would otherwise make the assignment
non-deterministic. See conftest.py's `block_other_coordinators`.
"""

import httpx

from .conftest import (
    BASE_URL,
    EVENTS_BASE_URL,
    GATEWAY_BASE_URL,
    all_coordinator_ids,
    block_other_coordinators,
    request_with_retry,
    requires_env,
)

pytestmark = requires_env

SUBMITTED = {
    "name": "Coordinator assignment check",
    "purpose": "Prove the end-to-end routing",
    "start_date": "2026-11-05",
    "start_time": "09:00",
    "end_date": "2026-11-05",
    "end_time": "11:00",
    "expected_attendance": 10,
    "venue": "Room 1",
}


# --- TC-EVENTREQUESTS-101 ---------------------------------------------------
def test_free_coordinator_is_assigned_and_visible_on_the_event(organiser_session, coordinator, admin):
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    organiser_session["event_ids"].extend(
        block_other_coordinators(admin, organiser_session["user_id"], {coordinator}, SUBMITTED)
    )

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=headers) as api:
        response = request_with_retry(api, "POST", "/event-requests", json=SUBMITTED)
        assert response.status_code == 201, response.text
        event = response.json()
        organiser_session["event_ids"].append(event["id"])
        assert event["assigned_coordinator_id"] == coordinator

    with httpx.Client(base_url=EVENTS_BASE_URL, timeout=15.0, headers=headers) as events_api:
        fetched = request_with_retry(events_api, "GET", f"/events/{event['id']}")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["assigned_coordinator_id"] == coordinator


# --- TC-EVENTREQUESTS-102 ---------------------------------------------------
def test_fully_booked_coordinator_pool_rejects_the_submission(organiser_session, coordinator, admin):
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    assert coordinator in all_coordinator_ids(admin)  # sanity: the fixture registered

    # Blocking "no one" exempt means every coordinator that exists gets a
    # covering booking -- including `coordinator` itself.
    organiser_session["event_ids"].extend(
        block_other_coordinators(admin, organiser_session["user_id"], set(), SUBMITTED)
    )

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=headers) as api:
        response = request_with_retry(api, "POST", "/event-requests", json=SUBMITTED)
        assert response.status_code == 409, response.text

    with httpx.Client(base_url=EVENTS_BASE_URL, timeout=15.0, headers=headers) as events_api:
        listed = request_with_retry(events_api, "GET", "/events")
        assert listed.status_code == 200, listed.text
        names = {event["name"] for event in listed.json()}
        assert SUBMITTED["name"] not in names


# --- TC-EVENTREQUESTS-103 ---------------------------------------------------
def test_every_event_requests_operation_routes_through_kong(organiser_session, coordinator, admin):
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    organiser_session["event_ids"].extend(
        block_other_coordinators(admin, organiser_session["user_id"], {coordinator}, SUBMITTED)
    )

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0, headers=headers) as api:
        response = request_with_retry(api, "POST", "/event-requests", json=SUBMITTED)
        assert response.status_code == 201, response.text
        event = response.json()
        organiser_session["event_ids"].append(event["id"])
        assert event["assigned_coordinator_id"] == coordinator


# --- TC-EVENTREQUESTS-104 ---------------------------------------------------
def test_editing_the_datetime_reassigns_when_the_current_coordinator_now_conflicts(
    organiser_session, coordinator, second_coordinator, admin
):
    """Two coordinators are blocked at opposite windows: A is free initially
    but conflicts after the edit, while B is available at the edited window.
    The shared test project can gain another free coordinator after the
    blocking snapshot, so the contract asserted here is that the edit moves
    the event away from conflicted A to a different eligible coordinator.
    """
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    initial_window = SUBMITTED  # 09:00-11:00
    edited_window = {**SUBMITTED, "start_time": "13:00", "end_time": "15:00"}

    def seed_blocking_event(coordinator_id, window, name):
        row = (
            admin.schema("events")
            .table("events")
            .insert(
                {
                    "organiser_id": organiser_session["user_id"],
                    "status": "submitted",
                    "assigned_coordinator_id": coordinator_id,
                    "name": name,
                    "purpose": "Blocks a window for this test",
                    "start_date": window["start_date"],
                    "start_time": window["start_time"],
                    "end_date": window["end_date"],
                    "end_time": window["end_time"],
                    "expected_attendance": 5,
                    "venue": "Room 2",
                    "submitted_at": "2026-09-24T00:00:00Z",
                }
            )
            .execute()
        )
        organiser_session["event_ids"].append(row.data[0]["id"])

    # B is blocked at the initial window, so A is the only one eligible when
    # the event is first submitted -- not a tie, so the pick is deterministic.
    seed_blocking_event(second_coordinator, initial_window, "B's other booking")
    # A is blocked at the window the event will be edited into, so once the
    # edit lands there, A conflicts with itself... except its own row is
    # excluded, so this second, distinct booking is what actually conflicts.
    seed_blocking_event(coordinator, edited_window, "A's other booking")

    # Any third coordinator in the pool is free at whichever window the one
    # actually being blocked there isn't -- block them at both, at every step.
    exempt = {coordinator, second_coordinator}
    organiser_session["event_ids"].extend(
        block_other_coordinators(admin, organiser_session["user_id"], exempt, initial_window)
    )
    organiser_session["event_ids"].extend(
        block_other_coordinators(admin, organiser_session["user_id"], exempt, edited_window)
    )

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=headers) as api:
        created = request_with_retry(api, "POST", "/event-requests", json=SUBMITTED)
        assert created.status_code == 201, created.text
        event = created.json()
        organiser_session["event_ids"].append(event["id"])
        assert event["assigned_coordinator_id"] == coordinator

        edited = request_with_retry(
            api, "PATCH", f"/event-requests/{event['id']}", json={"start_time": "13:00", "end_time": "15:00"}
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["assigned_coordinator_id"] != coordinator
        assert edited.json()["assigned_coordinator_id"] in all_coordinator_ids(admin)
        assert edited.json()["start_time"] == "13:00:00"


# --- S-13: the organiser responds to a return -------------------------------

RETURN_WINDOW = {**SUBMITTED, "start_date": "2026-11-12", "end_date": "2026-11-12", "expected_attendance": 120}
RETURN_DECISION = {
    "status": "returned",
    "decision": "returned",
    "decision_reason": "Expected attendance exceeds the venue's capacity",
    "decision_comment": "Reduce attendance to 80 or choose a larger venue",
    "decided_at": "2026-09-20T10:00:00+00:00",
}


def _submit_and_return(api, admin, organiser_session, coordinator_id):
    """Submits RETURN_WINDOW so it lands on `coordinator_id`, then has the
    admin client record a return on it -- the coordinator's decision is
    S-14's to prove; S-13 starts from a request that has already come back.
    """
    organiser_session["event_ids"].extend(
        block_other_coordinators(admin, organiser_session["user_id"], {coordinator_id}, RETURN_WINDOW)
    )
    response = request_with_retry(api, "POST", "/event-requests", json=RETURN_WINDOW)
    assert response.status_code == 201, response.text
    event = response.json()
    organiser_session["event_ids"].append(event["id"])
    assert event["assigned_coordinator_id"] == coordinator_id
    admin.schema("events").table("events").update(RETURN_DECISION).eq("id", event["id"]).execute()
    return event["id"]


# --- TC-EVENTREQUESTS-105 ---------------------------------------------------
def test_a_returned_request_is_amended_resubmitted_and_back_with_its_coordinator(
    organiser_session, coordinator_session, admin
):
    coordinator_id = coordinator_session["user_id"]
    organiser = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    as_coordinator = {"Cookie": f"sb_access_token={coordinator_session['access_token']}"}

    with (
        httpx.Client(base_url=BASE_URL, timeout=15.0, headers=organiser) as api,
        httpx.Client(base_url=EVENTS_BASE_URL, timeout=15.0, headers=organiser) as events_api,
    ):
        event_id = _submit_and_return(api, admin, organiser_session, coordinator_id)
        before = request_with_retry(events_api, "GET", "/events")
        assert before.status_code == 200, before.text

        amended = {**RETURN_WINDOW, "expected_attendance": 80}
        resubmitted = request_with_retry(api, "POST", f"/event-requests/{event_id}/submit", json=amended)
        assert resubmitted.status_code == 200, resubmitted.text
        assert resubmitted.json()["id"] == event_id

        fetched = request_with_retry(events_api, "GET", f"/events/{event_id}")
        assert fetched.status_code == 200, fetched.text
        event = fetched.json()
        assert event["status"] == "submitted"
        assert event["expected_attendance"] == 80
        assert event["assigned_coordinator_id"] == coordinator_id
        for field in ("decision", "decision_reason", "decision_comment", "decided_at"):
            assert event[field] is None, field

        after = request_with_retry(events_api, "GET", "/events")
        assert len(after.json()) == len(before.json())

    with httpx.Client(base_url=EVENTS_BASE_URL, timeout=15.0, headers=as_coordinator) as queue_api:
        queue = request_with_retry(queue_api, "GET", "/events/assigned")
        assert queue.status_code == 200, queue.text
        matching = [row for row in queue.json() if row["id"] == event_id]
        assert len(matching) == 1
        assert matching[0]["status"] == "submitted"
        assert matching[0]["expected_attendance"] == 80


# --- TC-EVENTREQUESTS-106 ---------------------------------------------------
def test_a_failed_resubmission_leaves_the_returned_request_exactly_as_it_was(
    organiser_session, coordinator_session, admin
):
    coordinator_id = coordinator_session["user_id"]
    organiser = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    blocked_window = {**RETURN_WINDOW, "start_time": "13:00", "end_time": "15:00", "expected_attendance": 80}

    with (
        httpx.Client(base_url=BASE_URL, timeout=15.0, headers=organiser) as api,
        httpx.Client(base_url=EVENTS_BASE_URL, timeout=15.0, headers=organiser) as events_api,
    ):
        event_id = _submit_and_return(api, admin, organiser_session, coordinator_id)
        # Nobody exempt: the event's own coordinator is busy at the new window too.
        organiser_session["event_ids"].extend(
            block_other_coordinators(admin, organiser_session["user_id"], set(), blocked_window)
        )

        before = request_with_retry(events_api, "GET", f"/events/{event_id}")
        assert before.status_code == 200, before.text

        refused = request_with_retry(api, "POST", f"/event-requests/{event_id}/submit", json=blocked_window)
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"] == "No event coordinator is available for the requested date and time"

        after = request_with_retry(events_api, "GET", f"/events/{event_id}")
        assert after.status_code == 200, after.text
        assert after.json() == before.json()
        assert after.json()["status"] == "returned"
        assert after.json()["start_time"] == "09:00:00"
        assert after.json()["expected_attendance"] == 120
