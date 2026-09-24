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
        response = api.post("/event-requests", json=SUBMITTED)
        assert response.status_code == 201, response.text
        event = response.json()
        organiser_session["event_ids"].append(event["id"])
        assert event["assigned_coordinator_id"] == coordinator

    with httpx.Client(base_url=EVENTS_BASE_URL, timeout=15.0, headers=headers) as events_api:
        fetched = events_api.get(f"/events/{event['id']}")
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
        response = api.post("/event-requests", json=SUBMITTED)
        assert response.status_code == 409, response.text

    with httpx.Client(base_url=EVENTS_BASE_URL, timeout=15.0, headers=headers) as events_api:
        listed = events_api.get("/events")
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
        response = api.post("/event-requests", json=SUBMITTED)
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
    reverse. The edit has to move the assignment from A to B. Every other
    coordinator in the project is blocked at both windows, so a third,
    unrelated account can never be the one picked instead.
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
        created = api.post("/event-requests", json=SUBMITTED)
        assert created.status_code == 201, created.text
        event = created.json()
        organiser_session["event_ids"].append(event["id"])
        assert event["assigned_coordinator_id"] == coordinator

        edited = api.patch(f"/event-requests/{event['id']}", json={"start_time": "13:00", "end_time": "15:00"})
        assert edited.status_code == 200, edited.text
        assert edited.json()["assigned_coordinator_id"] == second_coordinator
        assert edited.json()["start_time"] == "13:00:00"
