"""Real service round trip for the event_requests composite -- see TEST_CASES.md.

Every test below either blocks or exempts *every* coordinator that exists in
the project, not just the ones it created — GET /users/coordinators sees the
whole pool, so a leftover account from manual testing or an earlier run is
just as eligible as a fixture's, and would otherwise make the assignment
non-deterministic. See conftest.py's `block_other_coordinators`.
"""

from datetime import datetime

import httpx
import pytest

from .conftest import (
    BASE_URL,
    EVENTS_BASE_URL,
    GATEWAY_BASE_URL,
    all_coordinator_ids,
    all_technical_support_ids,
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
@pytest.mark.skip(reason="Superseded by S-83 manual Lead assignment")
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
@pytest.mark.skip(reason="S-83 does not reject submissions because Coordinators are busy")
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
        assert response.json() == {
            "detail": "No event coordinator is available for the requested date and time"
        }

    with httpx.Client(base_url=EVENTS_BASE_URL, timeout=15.0, headers=headers) as events_api:
        listed = request_with_retry(events_api, "GET", "/events")
        assert listed.status_code == 200, listed.text
        names = {event["name"] for event in listed.json()}
        assert SUBMITTED["name"] not in names


# --- TC-EVENTREQUESTS-103 ---------------------------------------------------
@pytest.mark.skip(reason="Superseded by TC-EVENTREQUESTS-108 through Kong")
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
@pytest.mark.skip(reason="S-83 removes conflict-driven automatic reassignment")
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
    """Submits an unassigned request, then seeds the prior assignment and
    return decision that S-13 starts from.
    """
    response = request_with_retry(api, "POST", "/event-requests", json=RETURN_WINDOW)
    assert response.status_code == 201, response.text
    event = response.json()
    organiser_session["event_ids"].append(event["id"])
    assert event["assigned_coordinator_id"] is None
    admin.schema("events").table("events").update(
        {**RETURN_DECISION, "assigned_coordinator_id": coordinator_id}
    ).eq("id", event["id"]).execute()
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
@pytest.mark.skip(reason="S-83 preserves the Coordinator and does not reject schedule conflicts")
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


# --- TC-EVENTREQUESTS-107 ---------------------------------------------------
def test_support_assignment_is_persisted_visible_and_idempotent(
    coordinator_session, technical_support_users, admin
):
    coordinator_id = coordinator_session["user_id"]
    headers = {"Cookie": f"sb_access_token={coordinator_session['access_token']}"}
    preferred = technical_support_users[1]
    created_event_ids: list[str] = []

    def insert_planning(name, start_time, end_time, **extra):
        row = (
            admin.schema("events")
            .table("events")
            .insert(
                {
                    "organiser_id": coordinator_id,
                    "status": "planning",
                    "assigned_coordinator_id": coordinator_id,
                    "name": name,
                    "purpose": "S-43 integration coverage",
                    "start_date": "2026-11-13",
                    "start_time": start_time,
                    "end_date": "2026-11-13",
                    "end_time": end_time,
                    "expected_attendance": 20,
                    "decision": "approved",
                    "decided_at": "2026-09-29T08:30:00+00:00",
                    "submitted_at": "2026-09-29T08:00:00+00:00",
                    **extra,
                }
            )
            .execute()
            .data[0]
        )
        created_event_ids.append(row["id"])
        return row

    try:
        for staff_id in all_technical_support_ids(admin) - {preferred["id"]}:
            insert_planning(
                f"Existing support assignment {staff_id}",
                "13:00",
                "14:00",
                technical_support_required=True,
                assigned_technical_support_id=staff_id,
                technical_support_assigned_at="2026-09-29T09:00:00+00:00",
            )
        target = insert_planning("S-43 target", "09:00", "12:00")

        with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0, headers=headers) as api:
            initial = request_with_retry(
                api,
                "GET",
                f"/event-requests/{target['id']}/technical-support-assignment",
            )
            assert initial.status_code == 200, initial.text
            assert initial.json()["assignment_state"] == "not_required"

            assigned = request_with_retry(
                api,
                "POST",
                f"/event-requests/{target['id']}/technical-support-assignment",
                json={"support_details": "Wireless microphone setup and sound check"},
            )
            assert assigned.status_code == 200, assigned.text
            first = assigned.json()
            assert first["assignment_state"] == "assigned"
            assert first["assigned_technical_support_id"] == preferred["id"]
            assert first["assigned_staff"]["email"] == preferred["email"]
            assigned_at = first["technical_support_assigned_at"]

            changed = request_with_retry(
                api,
                "POST",
                f"/event-requests/{target['id']}/technical-support-assignment",
                json={"support_details": "Updated support notes"},
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["assigned_technical_support_id"] == preferred["id"]
            assert changed.json()["technical_support_assigned_at"] == assigned_at

            fetched = request_with_retry(
                api,
                "GET",
                f"/event-requests/{target['id']}/technical-support-assignment",
            )
            assert fetched.status_code == 200, fetched.text
            assert fetched.json()["support_details"] == "Updated support notes"

        stored = (
            admin.schema("events")
            .table("events")
            .select("*")
            .eq("id", target["id"])
            .execute()
            .data[0]
        )
        assert stored["technical_support_required"] is True
        assert stored["assigned_technical_support_id"] == preferred["id"]
        assert datetime.fromisoformat(
            stored["technical_support_assigned_at"].replace("Z", "+00:00")
        ) == datetime.fromisoformat(assigned_at.replace("Z", "+00:00"))
        assert stored["technical_support_details"] == "Updated support notes"
    finally:
        for event_id in created_event_ids:
            admin.schema("events").table("events").delete().eq("id", event_id).execute()


# --- TC-EVENTREQUESTS-108 ---------------------------------------------------
def test_lead_assignment_persists_notifications_and_repairs_missing_rows(
    organiser_session, coordinator, second_coordinator, lead_session, admin
):
    organiser_headers = {
        "Cookie": f"sb_access_token={organiser_session['access_token']}"
    }
    lead_headers = {"Cookie": f"sb_access_token={lead_session['access_token']}"}

    def rows_for(event_id):
        return (
            admin.schema("notifications")
            .table("notifications")
            .select("*")
            .eq("event_id", event_id)
            .execute()
            .data
        )

    overlap = (
        admin.schema("events")
        .table("events")
        .insert(
            {
                "organiser_id": organiser_session["user_id"],
                "status": "submitted",
                "assigned_coordinator_id": coordinator,
                "name": "Existing overlapping assignment",
                "purpose": "Proves S-83 does not block schedule conflicts",
                "start_date": SUBMITTED["start_date"],
                "start_time": "10:00",
                "end_date": SUBMITTED["end_date"],
                "end_time": "11:00",
                "expected_attendance": 5,
                "submitted_at": "2026-10-08T00:00:00Z",
            }
        )
        .execute()
        .data[0]
    )
    organiser_session["event_ids"].append(overlap["id"])

    with (
        httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as gateway,
        httpx.Client(base_url=EVENTS_BASE_URL, timeout=15.0) as events_api,
    ):
        created = request_with_retry(
            gateway,
            "POST",
            "/event-requests",
            headers=organiser_headers,
            json=SUBMITTED,
        )
        assert created.status_code == 201, created.text
        event = created.json()
        organiser_session["event_ids"].append(event["id"])
        assert event["assigned_coordinator_id"] is None

        queue = request_with_retry(
            gateway, "GET", "/event-requests/unassigned", headers=lead_headers
        )
        assert queue.status_code == 200, queue.text
        assert event["id"] in {row["id"] for row in queue.json()}

        assigned = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{event['id']}/assignment",
            headers=lead_headers,
            json={"coordinator_id": coordinator},
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["assigned_coordinator_id"] == coordinator
        first_rows = rows_for(event["id"])
        assert len(first_rows) == 2
        assert {row["recipient_id"] for row in first_rows} == {
            coordinator, organiser_session["user_id"]
        }
        after_assignment = request_with_retry(
            gateway, "GET", "/event-requests/unassigned", headers=lead_headers
        )
        assert event["id"] not in {row["id"] for row in after_assignment.json()}

        repeated = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{event['id']}/assignment",
            headers=lead_headers,
            json={"coordinator_id": coordinator},
        )
        assert repeated.status_code == 200, repeated.text
        assert len(rows_for(event["id"])) == 2

        # Reproduce the durable state left by a notification-service failure:
        # the atomic event write committed, but neither notification exists.
        partial = request_with_retry(
            gateway,
            "POST",
            "/event-requests",
            headers=organiser_headers,
            json={**SUBMITTED, "name": "Assignment retry check"},
        )
        assert partial.status_code == 201, partial.text
        partial_event = partial.json()
        organiser_session["event_ids"].append(partial_event["id"])
        event_only = request_with_retry(
            events_api,
            "POST",
            f"/internal/events/{partial_event['id']}/assignment",
            json={"coordinator_id": coordinator},
        )
        assert event_only.status_code == 200, event_only.text
        assert rows_for(partial_event["id"]) == []

        repaired = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{partial_event['id']}/assignment",
            headers=lead_headers,
            json={"coordinator_id": coordinator},
        )
        assert repaired.status_code == 200, repaired.text
        assert repaired.json()["assigned_coordinator_id"] == coordinator
        assert len(rows_for(partial_event["id"])) == 2

        admin.schema("notifications").table("notifications").delete().eq(
            "event_id", partial_event["id"]
        ).eq("recipient_id", organiser_session["user_id"]).execute()
        assert len(rows_for(partial_event["id"])) == 1
        repaired_one = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{partial_event['id']}/assignment",
            headers=lead_headers,
            json={"coordinator_id": coordinator},
        )
        assert repaired_one.status_code == 200, repaired_one.text
        assert len(rows_for(partial_event["id"])) == 2

        changed_target = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{partial_event['id']}/assignment",
            headers=lead_headers,
            json={"coordinator_id": second_coordinator},
        )
        assert changed_target.status_code == 409, changed_target.text


# --- TC-EVENTREQUESTS-109 ---------------------------------------------------
def test_reassignment_transfers_access_and_repairs_notifications(
    organiser_session,
    coordinator_session,
    second_coordinator_session,
    lead_session,
    admin,
):
    organiser_headers = {
        "Cookie": f"sb_access_token={organiser_session['access_token']}"
    }
    lead_headers = {"Cookie": f"sb_access_token={lead_session['access_token']}"}
    first_headers = {
        "Cookie": f"sb_access_token={coordinator_session['access_token']}"
    }
    second_headers = {
        "Cookie": f"sb_access_token={second_coordinator_session['access_token']}"
    }

    def reassignment_rows(event_id, version=1):
        prefix = f"event_reassignment:{event_id}:{version}:"
        return [
            row
            for row in (
                admin.schema("notifications")
                .table("notifications")
                .select("*")
                .eq("event_id", event_id)
                .eq("kind", "event_reassignment")
                .execute()
                .data
            )
            if row["deduplication_key"].startswith(prefix)
        ]

    # B is deliberately busy at the target window; S-84 still permits the
    # Lead to select B.
    overlap = (
        admin.schema("events")
        .table("events")
        .insert(
            {
                "organiser_id": organiser_session["user_id"],
                "status": "submitted",
                "assigned_coordinator_id": second_coordinator_session["user_id"],
                "name": "Overlapping S-84 assignment",
                "purpose": "Proves conflicts do not block Lead reassignment",
                "start_date": SUBMITTED["start_date"],
                "start_time": SUBMITTED["start_time"],
                "end_date": SUBMITTED["end_date"],
                "end_time": SUBMITTED["end_time"],
                "expected_attendance": 5,
                "submitted_at": "2026-10-08T00:00:00Z",
            }
        )
        .execute()
        .data[0]
    )
    organiser_session["event_ids"].append(overlap["id"])

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as gateway:
        created = request_with_retry(
            gateway,
            "POST",
            "/event-requests",
            headers=organiser_headers,
            json={**SUBMITTED, "name": "S-84 access transfer"},
        )
        assert created.status_code == 201, created.text
        event = created.json()
        organiser_session["event_ids"].append(event["id"])

        assigned = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{event['id']}/assignment",
            headers=lead_headers,
            json={"coordinator_id": coordinator_session["user_id"]},
        )
        assert assigned.status_code == 200, assigned.text

        active = request_with_retry(
            gateway, "GET", "/event-requests/assigned-active", headers=lead_headers
        )
        assert active.status_code == 200, active.text
        listed = next(row for row in active.json() if row["id"] == event["id"])
        assert listed["assigned_coordinator_id"] == coordinator_session["user_id"]
        assert listed["coordinator_assignment_version"] == 0

        request_body = {
            "coordinator_id": second_coordinator_session["user_id"],
            "expected_coordinator_id": coordinator_session["user_id"],
            "expected_assignment_version": 0,
        }
        moved = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{event['id']}/reassignment",
            headers=lead_headers,
            json=request_body,
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["assigned_coordinator_id"] == second_coordinator_session["user_id"]
        assert moved.json()["coordinator_assignment_version"] == 1

        first_queue = request_with_retry(
            gateway, "GET", "/events/assigned", headers=first_headers
        )
        second_queue = request_with_retry(
            gateway, "GET", "/events/assigned", headers=second_headers
        )
        assert event["id"] not in {row["id"] for row in first_queue.json()}
        assert event["id"] in {row["id"] for row in second_queue.json()}

        rows = reassignment_rows(event["id"])
        assert len(rows) == 3
        assert {row["recipient_id"] for row in rows} == {
            coordinator_session["user_id"],
            second_coordinator_session["user_id"],
            organiser_session["user_id"],
        }

        repeated = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{event['id']}/reassignment",
            headers=lead_headers,
            json=request_body,
        )
        assert repeated.status_code == 200, repeated.text
        assert len(reassignment_rows(event["id"])) == 3

        admin.schema("notifications").table("notifications").delete().eq(
            "deduplication_key",
            f"event_reassignment:{event['id']}:1:{organiser_session['user_id']}",
        ).execute()
        assert len(reassignment_rows(event["id"])) == 2
        repaired = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{event['id']}/reassignment",
            headers=lead_headers,
            json=request_body,
        )
        assert repaired.status_code == 200, repaired.text
        assert len(reassignment_rows(event["id"])) == 3

        newer = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{event['id']}/reassignment",
            headers=lead_headers,
            json={
                "coordinator_id": coordinator_session["user_id"],
                "expected_coordinator_id": second_coordinator_session["user_id"],
                "expected_assignment_version": 1,
            },
        )
        assert newer.status_code == 200, newer.text
        assert newer.json()["coordinator_assignment_version"] == 2

        stale = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{event['id']}/reassignment",
            headers=lead_headers,
            json=request_body,
        )
        assert stale.status_code == 409, stale.text
        stored = (
            admin.schema("events")
            .table("events")
            .select("assigned_coordinator_id,coordinator_assignment_version")
            .eq("id", event["id"])
            .execute()
            .data[0]
        )
        assert stored == {
            "assigned_coordinator_id": coordinator_session["user_id"],
            "coordinator_assignment_version": 2,
        }


# --- TC-EVENTREQUESTS-110 ---------------------------------------------------
def test_coordinator_overview_groups_and_tracks_reassignment(
    organiser_session,
    coordinator_session,
    second_coordinator_session,
    lead_session,
    admin,
):
    organiser_headers = {
        "Cookie": f"sb_access_token={organiser_session['access_token']}"
    }
    lead_headers = {"Cookie": f"sb_access_token={lead_session['access_token']}"}
    first_id = coordinator_session["user_id"]
    second_id = second_coordinator_session["user_id"]

    admin.schema("users").table("users").update({"name": "Alex Coordinator"}).eq(
        "id", first_id
    ).execute()
    admin.schema("users").table("users").update({"name": "Blair Coordinator"}).eq(
        "id", second_id
    ).execute()

    def notification_count(event_id):
        return len(
            admin.schema("notifications")
            .table("notifications")
            .select("id")
            .eq("event_id", event_id)
            .execute()
            .data
        )

    def group(response, coordinator_id):
        return next(
            item
            for item in response.json()["coordinators"]
            if item["coordinator"]["id"] == coordinator_id
        )

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as gateway:
        created = request_with_retry(
            gateway,
            "POST",
            "/event-requests",
            headers=organiser_headers,
            json={**SUBMITTED, "name": "S-85 oversight forum"},
        )
        assert created.status_code == 201, created.text
        event = created.json()
        organiser_session["event_ids"].append(event["id"])

        assigned = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{event['id']}/assignment",
            headers=lead_headers,
            json={"coordinator_id": first_id},
        )
        assert assigned.status_code == 200, assigned.text
        after_assignment_notifications = notification_count(event["id"])

        initial = request_with_retry(
            gateway,
            "GET",
            "/event-requests/coordinator-overview",
            headers=lead_headers,
        )
        assert initial.status_code == 200, initial.text
        first = group(initial, first_id)
        second = group(initial, second_id)
        assert first["active_assignment_count"] == 1
        assert second["active_assignment_count"] == 0
        assert second["events"] == []
        summary = next(row for row in first["events"] if row["id"] == event["id"])
        assert summary["name"] == "S-85 oversight forum"
        assert summary["status"] == "submitted"
        assert summary["organiser"]["id"] == organiser_session["user_id"]
        assert summary["coordinator"]["name"] == "Alex Coordinator"
        assert summary["start_date"] == SUBMITTED["start_date"]
        assert summary["start_time"].startswith(SUBMITTED["start_time"])
        assert notification_count(event["id"]) == after_assignment_notifications

        moved = request_with_retry(
            gateway,
            "POST",
            f"/event-requests/{event['id']}/reassignment",
            headers=lead_headers,
            json={
                "coordinator_id": second_id,
                "expected_coordinator_id": first_id,
                "expected_assignment_version": 0,
            },
        )
        assert moved.status_code == 200, moved.text
        after_reassignment_notifications = notification_count(event["id"])

        refreshed = request_with_retry(
            gateway,
            "GET",
            "/event-requests/coordinator-overview",
            headers=lead_headers,
        )
        assert refreshed.status_code == 200, refreshed.text
        first = group(refreshed, first_id)
        second = group(refreshed, second_id)
        assert first["active_assignment_count"] == 0
        assert first["events"] == []
        assert second["active_assignment_count"] == 1
        moved_summary = next(
            row for row in second["events"] if row["id"] == event["id"]
        )
        assert moved_summary["coordinator"]["name"] == "Blair Coordinator"
        assert moved_summary["coordinator_assignment_version"] == 1
        assert notification_count(event["id"]) == after_reassignment_notifications

        denied = request_with_retry(
            gateway,
            "GET",
            "/event-requests/coordinator-overview",
            headers=organiser_headers,
        )
        assert denied.status_code == 403, denied.text
