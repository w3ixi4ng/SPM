"""Real service round trip for the event_requests composite -- see TEST_CASES.md."""

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
def test_free_coordinator_is_assigned_and_visible_on_the_event(organiser_session, coordinator):
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}

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

    blocking = (
        admin.schema("events")
        .table("events")
        .insert(
            {
                "organiser_id": organiser_session["user_id"],
                "status": "submitted",
                "assigned_coordinator_id": coordinator,
                "name": "Existing booking",
                "purpose": "Occupies the window",
                "start_date": SUBMITTED["start_date"],
                "start_time": SUBMITTED["start_time"],
                "end_date": SUBMITTED["end_date"],
                "end_time": SUBMITTED["end_time"],
                "expected_attendance": 5,
                "venue": "Room 2",
                "submitted_at": "2026-09-24T00:00:00Z",
            }
        )
        .execute()
    )
    organiser_session["event_ids"].append(blocking.data[0]["id"])

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=headers) as api:
        response = request_with_retry(api, "POST", "/event-requests", json=SUBMITTED)
        assert response.status_code == 409, response.text

    with httpx.Client(base_url=EVENTS_BASE_URL, timeout=15.0, headers=headers) as events_api:
        listed = request_with_retry(events_api, "GET", "/events")
        assert listed.status_code == 200, listed.text
        names = {event["name"] for event in listed.json()}
        assert SUBMITTED["name"] not in names


# --- TC-EVENTREQUESTS-103 ---------------------------------------------------
def test_every_event_requests_operation_routes_through_kong(organiser_session, coordinator):
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}

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
    """Two coordinators, each already blocked at a different window, so which
    one is eligible at each step is forced rather than left to the random
    tie-break: coordinator A is free for the initial submission but has a
    standing conflict at the window the event is edited into; B is the
    reverse. The edit has to move the assignment from A to B.
    """
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    initial_window = SUBMITTED  # 09:00-11:00
    edited_window = {"start_time": "13:00", "end_time": "15:00"}

    def seed_blocking_event(coordinator_id, start_time, end_time, name):
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
                    "start_date": SUBMITTED["start_date"],
                    "start_time": start_time,
                    "end_date": SUBMITTED["end_date"],
                    "end_time": end_time,
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
    seed_blocking_event(
        second_coordinator, initial_window["start_time"], initial_window["end_time"], "B's other booking"
    )
    # A is blocked at the window the event will be edited into, so once the
    # edit lands there, A conflicts with itself... except its own row is
    # excluded, so this second, distinct booking is what actually conflicts.
    seed_blocking_event(
        coordinator, edited_window["start_time"], edited_window["end_time"], "A's other booking"
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
        assert edited.json()["assigned_coordinator_id"] == second_coordinator
        assert edited.json()["start_time"] == "13:00:00"
