"""Unit tests for the events service endpoints -- see TEST_CASES.md."""

from unittest.mock import call

import pytest
from pydantic import ValidationError

from .conftest import (
    COORDINATOR_A,
    EVENT_ORGANISER_PERMISSIONS,
    EVENT_ID,
    EventRead,
    ORGANISER_ID,
    OTHER_USER_ID,
    ROLE_PERMISSIONS,
    authenticate,
    coordinator_event_row,
    event_row,
    fake_user,
    on_coordinator_rows,
    on_decision_update,
    on_insert,
    on_owned_list,
    on_owned_select,
    on_update,
    on_update_owned,
)

SUBMITTED = {
    "name": "Alumni networking evening",
    "purpose": "Connect alumni with graduating students",
    "start_date": "2026-10-20",
    "start_time": "18:00",
    "end_date": "2026-10-20",
    "end_time": "21:00",
    "expected_attendance": 120,
    "venue": "Main auditorium",
    "equipment_requests": {"projector": 1},
    "accessibility_requirements": "Wheelchair access",
}


# --- TC-EVENTS-012 --------------------------------------------------------
def test_health_reports_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- TC-EVENTS-031 --------------------------------------------------------
def test_prefixed_health_reports_ok_for_gateway(client):
    response = client.get("/events/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- TC-EVENTS-013 --------------------------------------------------------
def test_create_valid_draft(client, db, auth):
    authenticate(client, auth)
    stored = event_row(name="Planning draft")
    on_insert(db, [stored])

    response = client.post("/events/drafts", json={"name": "Planning draft"})

    assert response.status_code == 201
    assert response.json()["status"] == "draft"


# --- TC-EVENTS-014 --------------------------------------------------------
def test_create_submitted_event(client, db, auth):
    authenticate(client, auth)
    stored = event_row(status="submitted", **SUBMITTED)
    on_insert(db, [stored])

    response = client.post("/events", json=SUBMITTED)

    assert response.status_code == 201
    assert response.json()["status"] == "submitted"


# --- TC-EVENTS-015 --------------------------------------------------------
def test_create_derives_organiser_and_status_from_session(client, db, auth):
    authenticate(client, auth)
    on_insert(db, [event_row()])

    response = client.post("/events/drafts", json={})

    assert response.status_code == 201
    db.schema.return_value.table.return_value.insert.assert_called_once_with(
        {
            "name": None,
            "purpose": None,
            "start_date": None,
            "start_time": None,
            "end_date": None,
            "end_time": None,
            "expected_attendance": None,
            "venue": None,
            "equipment_requests": {},
            "accessibility_requirements": None,
            "special_requirements": None,
            "organiser_id": ORGANISER_ID,
            "status": "draft",
            # A draft has no submission time, and the column says so rather
            # than being left out -- see TC-EVENTS-045.
            "submitted_at": None,
        }
    )


# --- TC-EVENTS-016 --------------------------------------------------------
def test_create_rejects_wrong_role(client, db, auth):
    authenticate(client, auth, fake_user(role="event_coordinator"))

    response = client.post("/events/drafts", json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
    db.schema.assert_not_called()


# --- TC-EVENTS-017 --------------------------------------------------------
def test_create_rejects_missing_role(client, db, auth):
    authenticate(client, auth, fake_user(role=None))

    response = client.post("/events", json=SUBMITTED)

    assert response.status_code == 403
    db.schema.assert_not_called()


# --- TC-EVENTS-018 --------------------------------------------------------
def test_retrieve_owned_event(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(name="Owned draft")])

    response = client.get(f"/events/{EVENT_ID}")

    assert response.status_code == 200
    assert response.json()["name"] == "Owned draft"
    select = db.schema.return_value.table.return_value.select.return_value
    assert select.eq.call_args_list == [call("id", EVENT_ID)]
    select.eq.return_value.eq.assert_called_once_with("organiser_id", ORGANISER_ID)


# --- TC-EVENTS-019 --------------------------------------------------------
def test_cannot_retrieve_another_users_event(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [])

    response = client.get(f"/events/{EVENT_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"


# --- TC-EVENTS-020 --------------------------------------------------------
def test_update_owned_draft_uses_only_supplied_fields(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(name="Old name")])
    on_update_owned(db, [event_row(name="New name")])

    response = client.patch(f"/events/{EVENT_ID}", json={"name": "New name"})

    assert response.status_code == 200
    assert response.json()["name"] == "New name"
    db.schema.return_value.table.return_value.update.assert_called_once_with(
        {"name": "New name"}
    )


# --- TC-EVENTS-021 --------------------------------------------------------
def test_can_update_submitted_event(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(status="submitted", **SUBMITTED)])
    on_update_owned(db, [event_row(status="submitted", **{**SUBMITTED, "name": "Changed"})])

    response = client.patch(f"/events/{EVENT_ID}", json={"name": "Changed"})

    assert response.status_code == 200
    assert response.json()["name"] == "Changed"
    assert response.json()["status"] == "submitted"
    db.schema.return_value.table.return_value.update.assert_called_once_with(
        {"name": "Changed"}
    )


# --- TC-EVENTS-040 --------------------------------------------------------
def test_updating_submitted_event_still_requires_submitted_fields(client, db, auth):
    # A PATCH on a submitted event is validated against the submitted-required
    # rules, not the draft's permissive ones -- otherwise it could null out a
    # field the database's own constraint requires, turning a readable 422
    # into an opaque storage failure.
    authenticate(client, auth)
    on_owned_select(db, [event_row(status="submitted", **SUBMITTED)])

    response = client.patch(f"/events/{EVENT_ID}", json={"venue": ""})

    assert response.status_code == 422
    assert "venue" in response.json()["errors"]
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-022 --------------------------------------------------------
def test_submit_existing_draft(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row()])
    submitted = event_row(status="submitted", **SUBMITTED)
    on_update(db, [submitted])

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    sent = db.schema.return_value.table.return_value.update.call_args[0][0]
    assert sent["submitted_at"] is not None
    excluded = {"submitted_at", "decision", "decision_reason", "decision_comment", "decided_at"}
    assert {key: value for key, value in sent.items() if key not in excluded} == {
        **SUBMITTED,
        "special_requirements": None,
        "start_time": "18:00:00",
        "end_time": "21:00:00",
        "status": "submitted",
    }
    # A resubmission clears whatever decision sent it back -- exercised more
    # directly for the returned-status case in TC-EVENTS-070.
    assert sent["decision"] is None
    assert sent["decision_reason"] is None
    assert sent["decision_comment"] is None
    assert sent["decided_at"] is None


# --- TC-EVENTS-023 --------------------------------------------------------
def test_cannot_resubmit_submitted_event(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(status="submitted", **SUBMITTED)])

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 409
    assert response.json()["detail"] == "Event has already been submitted"
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-024 --------------------------------------------------------
def test_database_failure_returns_safe_500(client, db, auth):
    authenticate(client, auth)
    on_insert(db, error=RuntimeError("database credentials leaked here"))

    response = client.post("/events/drafts", json={})

    assert response.status_code == 500
    assert response.json() == {"detail": "Event storage unavailable"}
    assert "credentials" not in response.text


# --- TC-EVENTS-025 --------------------------------------------------------
def test_create_requires_authentication(client, db, auth):
    response = client.post("/events/drafts", json={})

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    db.schema.assert_not_called()


# --- TC-EVENTS-026 --------------------------------------------------------
def test_update_validates_time_order_against_existing_draft(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(start_time="18:00:00")])

    response = client.patch(f"/events/{EVENT_ID}", json={"end_time": "17:00"})

    assert response.status_code == 422
    assert "end_time must be after start_time" in response.json()["errors"]["body"]
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-027 --------------------------------------------------------
def test_event_organiser_has_the_sprint_one_permissions():
    assert ROLE_PERMISSIONS["event_organiser"] == {
        "dashboard:view",
        "events:create",
        "events:save_draft",
        "events:view_own",
        "events:update_own_draft",
        "events:submit_own",
    }
    assert ROLE_PERMISSIONS["event_organiser"] == EVENT_ORGANISER_PERMISSIONS


# --- TC-EVENTS-028 --------------------------------------------------------
def test_other_known_roles_only_have_dashboard_permission():
    for role in ("venue_staff", "technical_support", "attendee"):
        assert ROLE_PERMISSIONS[role] == {"dashboard:view"}


# --- TC-EVENTS-057 --------------------------------------------------------
def test_event_coordinator_has_the_view_and_decide_permissions():
    assert ROLE_PERMISSIONS["event_coordinator"] == {
        "dashboard:view",
        "events:view_assigned",
        "events:decide",
    }


# --- TC-EVENTS-029 --------------------------------------------------------
def test_unknown_role_is_rejected(client, db, auth):
    authenticate(client, auth, fake_user(role="invented_role"))

    response = client.post("/events/drafts", json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "Recognized role required"
    db.schema.assert_not_called()


# --- TC-EVENTS-030 --------------------------------------------------------
def test_user_metadata_role_is_not_trusted(client, db, auth):
    user = fake_user(role="attendee")
    user.user_metadata = {"role": "event_organiser"}
    authenticate(client, auth, user)

    response = client.post("/events/drafts", json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
    db.schema.assert_not_called()


# --- TC-EVENTS-032 --------------------------------------------------------
def test_list_returns_only_authenticated_organisers_events(client, db, auth):
    authenticate(client, auth)
    rows = [
        event_row(name="Recent draft"),
        event_row(
            id="44444444-4444-4444-8444-444444444444",
            status="submitted",
            **SUBMITTED,
        ),
    ]
    on_owned_list(db, rows)

    response = client.get("/events")

    assert response.status_code == 200
    assert [event["name"] for event in response.json()] == [
        "Recent draft",
        "Alumni networking evening",
    ]
    select = db.schema.return_value.table.return_value.select.return_value
    select.eq.assert_called_once_with("organiser_id", ORGANISER_ID)
    select.eq.return_value.order.assert_called_once_with("updated_at", desc=True)


# --- TC-EVENTS-033 --------------------------------------------------------
def test_list_returns_empty_array_when_organiser_has_no_events(client, db, auth):
    authenticate(client, auth)
    on_owned_list(db, [])

    response = client.get("/events")

    assert response.status_code == 200
    assert response.json() == []


# --- TC-EVENTS-034 --------------------------------------------------------
def test_list_rejects_role_without_view_permission(client, db, auth):
    authenticate(client, auth, fake_user(role="attendee"))

    response = client.get("/events")

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
    db.schema.assert_not_called()


# --- TC-EVENTS-035 --------------------------------------------------------
def test_update_validates_date_order_against_existing_draft(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(start_date="2026-10-20")])

    response = client.patch(f"/events/{EVENT_ID}", json={"end_date": "2026-10-19"})

    assert response.status_code == 422
    assert "end_date must be on or after start_date" in response.json()["errors"]["body"]
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-036 --------------------------------------------------------
def test_create_accepts_multi_day_event_with_end_time_before_start_time(client, db, auth):
    authenticate(client, auth)
    overnight = {
        **SUBMITTED,
        "start_date": "2026-10-20",
        "start_time": "22:00",
        "end_date": "2026-10-21",
        "end_time": "02:00",
    }
    on_insert(db, [event_row(status="submitted", **overnight)])

    response = client.post("/events", json=overnight)

    assert response.status_code == 201
    assert response.json()["status"] == "submitted"


# --- TC-EVENTS-044 --------------------------------------------------------
def test_creating_a_submitted_event_records_the_submission_time(client, db, auth):
    authenticate(client, auth)
    on_insert(db, [event_row(status="submitted", submitted_at="2026-09-17T10:00:00Z", **SUBMITTED)])

    response = client.post("/events", json=SUBMITTED)

    assert response.status_code == 201
    # The service sets it; a client cannot choose its own submission time, so
    # what matters is what went to the database, not what came back.
    sent = db.schema.return_value.table.return_value.insert.call_args[0][0]
    assert sent["submitted_at"] is not None


# --- TC-EVENTS-045 --------------------------------------------------------
def test_creating_a_draft_records_no_submission_time(client, db, auth):
    authenticate(client, auth)
    on_insert(db, [event_row()])

    response = client.post("/events/drafts", json={"name": "Planning draft"})

    assert response.status_code == 201
    sent = db.schema.return_value.table.return_value.insert.call_args[0][0]
    assert sent["submitted_at"] is None


# --- TC-EVENTS-046 --------------------------------------------------------
def test_submitting_a_draft_records_the_submission_time(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row()])
    on_update(db, [event_row(status="submitted", submitted_at="2026-09-17T10:00:00Z", **SUBMITTED)])

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 200
    sent = db.schema.return_value.table.return_value.update.call_args[0][0]
    assert sent["submitted_at"] is not None


# --- TC-EVENTS-047 --------------------------------------------------------
def test_cannot_update_another_users_draft(client, db, auth):
    authenticate(client, auth)
    # The owned lookup filters on organiser_id, so another user's event is
    # indistinguishable from one that does not exist.
    on_owned_select(db, [])

    response = client.patch(f"/events/{EVENT_ID}", json={"name": "Changed"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-048 --------------------------------------------------------
def test_cannot_submit_another_users_draft(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [])

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- S-12: coordinator load and internal assignment routes ---------------
# These are composite-only -- no session cookies, no `authenticate()` call --
# because the caller is the event_requests service, not a browser.


# --- TC-EVENTS-049 --------------------------------------------------------
def test_coordinator_load_reports_no_conflict_with_empty_schedule(client, db):
    on_coordinator_rows(db, [])

    response = client.post(
        "/events/coordinator-load",
        json={
            "coordinator_ids": [COORDINATOR_A],
            "start_date": "2026-10-20",
            "start_time": "18:00",
            "end_date": "2026-10-20",
            "end_time": "21:00",
        },
    )

    assert response.status_code == 200
    assert response.json() == [
        {"coordinator_id": COORDINATOR_A, "conflict": False, "assigned_count": 0}
    ]


# --- TC-EVENTS-050 --------------------------------------------------------
def test_coordinator_load_reports_a_conflict_on_any_overlap(client, db):
    on_coordinator_rows(db, [coordinator_event_row(COORDINATOR_A)])

    response = client.post(
        "/events/coordinator-load",
        json={
            "coordinator_ids": [COORDINATOR_A],
            "start_date": "2026-10-20",
            "start_time": "20:00",
            "end_date": "2026-10-20",
            "end_time": "22:00",
        },
    )

    assert response.status_code == 200
    result = response.json()[0]
    assert result["conflict"] is True
    assert result["assigned_count"] == 1


# --- TC-EVENTS-051 --------------------------------------------------------
def test_coordinator_load_back_to_back_events_do_not_conflict(client, db):
    on_coordinator_rows(db, [coordinator_event_row(COORDINATOR_A)])

    response = client.post(
        "/events/coordinator-load",
        json={
            "coordinator_ids": [COORDINATOR_A],
            "start_date": "2026-10-20",
            "start_time": "21:00",
            "end_date": "2026-10-20",
            "end_time": "22:00",
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["conflict"] is False


# --- TC-EVENTS-052 --------------------------------------------------------
def test_coordinator_load_query_only_counts_submitted_and_planning_events(client, db):
    on_coordinator_rows(db, [])

    client.post(
        "/events/coordinator-load",
        json={
            "coordinator_ids": [COORDINATOR_A],
            "start_date": "2026-10-20",
            "start_time": "18:00",
            "end_date": "2026-10-20",
            "end_time": "21:00",
        },
    )

    # Drafts, returned, and rejected are filtered out in the query itself,
    # not after -- so they never reach the conflict or count logic at all.
    # Planning counts alongside submitted -- both are live commitments.
    db.schema.return_value.table.return_value.select.return_value.in_.return_value.in_.assert_called_once_with(
        "status", ["submitted", "planning"]
    )


# --- TC-EVENTS-053 --------------------------------------------------------
def test_internal_create_trusts_caller_organiser_and_coordinator_ids(client, db):
    stored = event_row(status="submitted", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)
    on_insert(db, [stored])

    response = client.post(
        "/events/internal",
        json={**SUBMITTED, "organiser_id": ORGANISER_ID, "assigned_coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 201
    sent = db.schema.return_value.table.return_value.insert.call_args[0][0]
    assert sent["organiser_id"] == ORGANISER_ID
    assert sent["assigned_coordinator_id"] == COORDINATOR_A
    assert sent["status"] == "submitted"
    assert sent["submitted_at"] is not None


# --- TC-EVENTS-054 --------------------------------------------------------
def test_internal_submit_sets_the_assignment(client, db):
    on_owned_select(db, [event_row()])
    on_update(db, [event_row(status="submitted", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)])

    response = client.post(
        f"/events/{EVENT_ID}/submit/internal",
        json={**SUBMITTED, "organiser_id": ORGANISER_ID, "assigned_coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 200
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_A
    sent = db.schema.return_value.table.return_value.update.call_args[0][0]
    assert sent["assigned_coordinator_id"] == COORDINATOR_A
    assert sent["status"] == "submitted"


# --- TC-EVENTS-055 --------------------------------------------------------
def test_internal_submit_still_enforces_ownership(client, db):
    # The owned-and-draft lookup finds nothing for an organiser who does not
    # own this draft, exactly as the public route behaves.
    on_owned_select(db, [])

    response = client.post(
        f"/events/{EVENT_ID}/submit/internal",
        json={**SUBMITTED, "organiser_id": OTHER_USER_ID, "assigned_coordinator_id": COORDINATOR_A},
    )

    assert response.status_code == 404
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-056 --------------------------------------------------------
def test_assigned_coordinator_id_is_null_until_assigned(client, db, auth):
    authenticate(client, auth)
    on_insert(db, [event_row(name="Planning draft")])

    response = client.post("/events/drafts", json={"name": "Planning draft"})

    assert response.json()["assigned_coordinator_id"] is None


# --- Coordinator-facing views of assigned requests ------------------------


# --- TC-EVENTS-058 --------------------------------------------------------
def test_coordinator_lists_only_their_assigned_events(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))
    assigned = event_row(status="submitted", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)
    on_owned_list(db, [assigned])

    response = client.get("/events/assigned")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == assigned["id"]
    assert body[0]["assigned_coordinator_id"] == COORDINATOR_A
    db.schema.return_value.table.return_value.select.return_value.eq.assert_called_once_with(
        "assigned_coordinator_id", COORDINATOR_A
    )


# --- TC-EVENTS-059 --------------------------------------------------------
def test_coordinator_cannot_view_an_event_not_assigned_to_them(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))
    on_owned_select(db, [])

    response = client.get(f"/events/assigned/{EVENT_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"


# --- TC-EVENTS-060 --------------------------------------------------------
def test_organiser_cannot_list_assigned_events(client, db, auth):
    authenticate(client, auth)  # default role is event_organiser

    response = client.get("/events/assigned")

    assert response.status_code == 403
    db.schema.return_value.table.return_value.select.assert_not_called()


# --- TC-EVENTS-061 --------------------------------------------------------
def test_coordinator_views_one_assigned_event(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))
    assigned = event_row(status="submitted", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)
    on_owned_select(db, [assigned])

    response = client.get(f"/events/assigned/{EVENT_ID}")

    assert response.status_code == 200
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_A


# --- Rechecking a submitted event's assignment on edit ---------------------


# --- TC-EVENTS-062 --------------------------------------------------------
def test_coordinator_load_excludes_the_given_event_from_conflict_and_count(client, db):
    on_coordinator_rows(db, [coordinator_event_row(COORDINATOR_A, id=EVENT_ID)])

    response = client.post(
        "/events/coordinator-load",
        json={
            "coordinator_ids": [COORDINATOR_A],
            "start_date": "2026-10-20",
            "start_time": "18:00",
            "end_date": "2026-10-20",
            "end_time": "21:00",
            "exclude_event_id": EVENT_ID,
        },
    )

    assert response.status_code == 200
    result = response.json()[0]
    # Without exclude_event_id this would conflict with itself (identical
    # window) and count toward assigned_count -- excluded, it does neither.
    assert result["conflict"] is False
    assert result["assigned_count"] == 0


# --- TC-EVENTS-063 --------------------------------------------------------
def test_internal_update_reassigns_the_coordinator(client, db):
    on_owned_select(db, [event_row(status="submitted", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)])
    on_update_owned(
        db,
        [
            event_row(
                status="submitted",
                start_time="20:00:00",
                assigned_coordinator_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                **{k: v for k, v in SUBMITTED.items() if k != "start_time"},
            )
        ],
    )

    response = client.patch(
        f"/events/{EVENT_ID}/internal",
        json={
            "organiser_id": ORGANISER_ID,
            "start_time": "20:00",
            "assigned_coordinator_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        },
    )

    assert response.status_code == 200
    sent = db.schema.return_value.table.return_value.update.call_args[0][0]
    assert sent["start_time"] == "20:00:00"
    assert sent["assigned_coordinator_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    assert "organiser_id" not in sent


# --- TC-EVENTS-064 --------------------------------------------------------
def test_internal_update_without_reassignment_leaves_coordinator_untouched(client, db):
    on_owned_select(db, [event_row(status="submitted", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)])
    on_update_owned(db, [event_row(status="submitted", venue="Room 9", assigned_coordinator_id=COORDINATOR_A, **{k: v for k, v in SUBMITTED.items() if k != "venue"})])

    response = client.patch(
        f"/events/{EVENT_ID}/internal",
        json={"organiser_id": ORGANISER_ID, "venue": "Room 9"},
    )

    assert response.status_code == 200
    sent = db.schema.return_value.table.return_value.update.call_args[0][0]
    assert sent == {"venue": "Room 9"}


# --- TC-EVENTS-065 --------------------------------------------------------
def test_internal_update_enforces_ownership(client, db):
    on_owned_select(db, [])

    response = client.patch(
        f"/events/{EVENT_ID}/internal",
        json={"organiser_id": OTHER_USER_ID, "venue": "Room 9"},
    )

    assert response.status_code == 404
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-066 --------------------------------------------------------
def test_internal_update_validates_the_resulting_submitted_event(client, db):
    on_owned_select(db, [event_row(status="submitted", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)])

    response = client.patch(
        f"/events/{EVENT_ID}/internal",
        json={"organiser_id": ORGANISER_ID, "venue": ""},
    )

    assert response.status_code == 422
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- S-14: coordinator decisions (approve / reject / return) --------------


# --- TC-EVENTS-067 --------------------------------------------------------
def test_coordinator_approves_a_submitted_request(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))
    on_owned_select(db, [event_row(status="submitted", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)])
    on_decision_update(
        db,
        [event_row(status="planning", decision="approved", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)],
    )

    response = client.post(f"/events/{EVENT_ID}/decision", json={"decision": "approved"})

    assert response.status_code == 200
    assert response.json()["status"] == "planning"
    sent = db.schema.return_value.table.return_value.update.call_args[0][0]
    assert sent["status"] == "planning"
    assert sent["decision"] == "approved"
    assert sent["decision_reason"] is None
    assert sent["decision_comment"] is None
    assert sent["decided_at"] is not None


# --- TC-EVENTS-068 --------------------------------------------------------
def test_reject_requires_a_reason(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))

    response = client.post(f"/events/{EVENT_ID}/decision", json={"decision": "rejected"})

    assert response.status_code == 422
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-069 --------------------------------------------------------
def test_coordinator_rejects_with_a_reason(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))
    on_owned_select(db, [event_row(status="submitted", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)])
    on_decision_update(
        db,
        [
            event_row(
                status="rejected",
                decision="rejected",
                decision_reason="Venue unavailable",
                assigned_coordinator_id=COORDINATOR_A,
                **SUBMITTED,
            )
        ],
    )

    response = client.post(
        f"/events/{EVENT_ID}/decision",
        json={"decision": "rejected", "reason": "Venue unavailable"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["decision_reason"] == "Venue unavailable"


# --- TC-EVENTS-070 --------------------------------------------------------
def test_coordinator_returns_with_a_reason_and_comment(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))
    on_owned_select(db, [event_row(status="submitted", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)])
    on_decision_update(
        db,
        [
            event_row(
                status="returned",
                decision="returned",
                decision_reason="Missing risk assessment",
                decision_comment="Please attach the venue's fire safety form",
                assigned_coordinator_id=COORDINATOR_A,
                **SUBMITTED,
            )
        ],
    )

    response = client.post(
        f"/events/{EVENT_ID}/decision",
        json={
            "decision": "returned",
            "reason": "Missing risk assessment",
            "comment": "Please attach the venue's fire safety form",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "returned"
    assert response.json()["decision_comment"] == "Please attach the venue's fire safety form"


# --- TC-EVENTS-071 --------------------------------------------------------
def test_return_requires_a_reason(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))

    response = client.post(
        f"/events/{EVENT_ID}/decision",
        json={"decision": "returned", "comment": "please fix the venue"},
    )

    assert response.status_code == 422
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-072 --------------------------------------------------------
def test_approve_rejects_a_reason(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))

    response = client.post(
        f"/events/{EVENT_ID}/decision",
        json={"decision": "approved", "reason": "looks fine"},
    )

    assert response.status_code == 422
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-073 --------------------------------------------------------
def test_comment_is_rejected_outside_a_return(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))

    response = client.post(
        f"/events/{EVENT_ID}/decision",
        json={"decision": "rejected", "reason": "no venue", "comment": "extra note"},
    )

    assert response.status_code == 422
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-074 --------------------------------------------------------
def test_a_coordinator_cannot_decide_an_event_not_assigned_to_them(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))
    on_owned_select(db, [])

    response = client.post(f"/events/{EVENT_ID}/decision", json={"decision": "approved"})

    assert response.status_code == 404
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-075 --------------------------------------------------------
def test_a_decision_already_made_cannot_be_decided_again(client, db, auth):
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))
    on_owned_select(
        db, [event_row(status="planning", decision="approved", assigned_coordinator_id=COORDINATOR_A, **SUBMITTED)]
    )

    response = client.post(f"/events/{EVENT_ID}/decision", json={"decision": "approved"})

    assert response.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-076 --------------------------------------------------------
def test_an_organiser_cannot_decide_a_request(client, db, auth):
    authenticate(client, auth)  # default role event_organiser

    response = client.post(f"/events/{EVENT_ID}/decision", json={"decision": "approved"})

    assert response.status_code == 403
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- S-14: resubmitting after a return -------------------------------------


# --- TC-EVENTS-077 --------------------------------------------------------
def test_a_returned_request_can_be_resubmitted(client, db, auth):
    authenticate(client, auth)
    on_owned_select(
        db,
        [event_row(status="returned", decision="returned", decision_reason="Missing details", **SUBMITTED)],
    )
    on_update(db, [event_row(status="submitted", **SUBMITTED)])

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    sent = db.schema.return_value.table.return_value.update.call_args[0][0]
    assert sent["decision"] is None
    assert sent["decision_reason"] is None
    assert sent["decision_comment"] is None
    assert sent["decided_at"] is None


# --- TC-EVENTS-078 --------------------------------------------------------
def test_a_planning_request_cannot_be_resubmitted(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(status="planning", decision="approved", **SUBMITTED)])

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-079 --------------------------------------------------------
def test_a_rejected_request_cannot_be_resubmitted(client, db, auth):
    authenticate(client, auth)
    on_owned_select(
        db, [event_row(status="rejected", decision="rejected", decision_reason="No venue", **SUBMITTED)]
    )

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- S-14: a rejected request is permanently closed ------------------------


# --- TC-EVENTS-080 --------------------------------------------------------
def test_a_rejected_event_cannot_be_edited(client, db, auth):
    authenticate(client, auth)
    on_owned_select(
        db, [event_row(status="rejected", decision="rejected", decision_reason="No venue", **SUBMITTED)]
    )

    response = client.patch(f"/events/{EVENT_ID}", json={"venue": "New Venue"})

    assert response.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-081 --------------------------------------------------------
def test_internal_update_also_blocks_a_rejected_event(client, db):
    on_owned_select(
        db, [event_row(status="rejected", decision="rejected", decision_reason="No venue", **SUBMITTED)]
    )

    response = client.patch(
        f"/events/{EVENT_ID}/internal",
        json={"organiser_id": ORGANISER_ID, "venue": "New Venue"},
    )

    assert response.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-082 --------------------------------------------------------
def test_editing_a_returned_event_still_requires_submitted_fields(client, db, auth):
    authenticate(client, auth)
    on_owned_select(
        db,
        [event_row(status="returned", decision="returned", decision_reason="Fix the venue", **SUBMITTED)],
    )

    response = client.patch(f"/events/{EVENT_ID}", json={"venue": ""})

    assert response.status_code == 422
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- S-13: the organiser responds to a return ------------------------------

RETURNED = {
    "status": "returned",
    "decision": "returned",
    "decision_reason": "Expected attendance exceeds the venue's capacity",
    "decision_comment": "Reduce attendance to 80 or choose a larger venue",
    "decided_at": "2026-09-20T10:00:00+00:00",
    "assigned_coordinator_id": COORDINATOR_A,
    "submitted_at": "2026-09-18T09:00:00+00:00",
}


# --- TC-EVENTS-083 --------------------------------------------------------
def test_the_organiser_can_read_the_return_reason_and_comment(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(**RETURNED, **SUBMITTED)])

    response = client.get(f"/events/{EVENT_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "returned"
    assert body["decision"] == "returned"
    assert body["decision_reason"] == "Expected attendance exceeds the venue's capacity"
    assert body["decision_comment"] == "Reduce attendance to 80 or choose a larger venue"
    assert body["decided_at"].startswith("2026-09-20T10:00:00")


# --- TC-EVENTS-084 --------------------------------------------------------
def test_saving_an_amendment_to_a_returned_event_keeps_it_returned(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(**RETURNED, **SUBMITTED)])
    on_update_owned(db, [event_row(**RETURNED, **{**SUBMITTED, "expected_attendance": 80})])

    response = client.patch(f"/events/{EVENT_ID}", json={"expected_attendance": 80})

    assert response.status_code == 200
    assert response.json()["status"] == "returned"
    db.schema.return_value.table.return_value.update.assert_called_once_with({"expected_attendance": 80})


# --- TC-EVENTS-085 --------------------------------------------------------
def test_resubmission_updates_the_original_record_and_never_inserts(client, db, auth):
    authenticate(client, auth)
    amended = {**SUBMITTED, "expected_attendance": 80}
    on_owned_select(db, [event_row(**RETURNED, **SUBMITTED)])
    on_update(db, [event_row(status="submitted", **amended)])

    response = client.post(f"/events/{EVENT_ID}/submit", json=amended)

    assert response.status_code == 200
    assert response.json()["id"] == EVENT_ID
    table = db.schema.return_value.table.return_value
    table.insert.assert_not_called()
    table.update.assert_called_once()
    assert table.update.call_args[0][0]["expected_attendance"] == 80
    update = table.update.return_value
    update.eq.assert_called_once_with("id", EVENT_ID)
    update.eq.return_value.eq.assert_called_once_with("organiser_id", ORGANISER_ID)
    update.eq.return_value.eq.return_value.in_.assert_called_once_with("status", ("draft", "returned"))


# --- TC-EVENTS-086 --------------------------------------------------------
def test_a_resubmission_that_loses_a_race_changes_nothing_and_says_so(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(**RETURNED, **SUBMITTED)])
    on_update(db, [])

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "This request is no longer awaiting changes. Reload to see its current status."
    )
    db.schema.return_value.table.return_value.update.assert_called_once()


# --- TC-EVENTS-087 --------------------------------------------------------
def test_a_storage_failure_during_resubmission_is_reported(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(**RETURNED, **SUBMITTED)])
    table = db.schema.return_value.table.return_value
    table.update.return_value.eq.return_value.eq.return_value.in_.return_value.execute.side_effect = (
        RuntimeError("connection reset")
    )

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 500
    assert response.json() == {"detail": "Event storage unavailable"}
    table.update.assert_called_once()


# --- S-36: approved is a decision, never a status ---------------------------


# --- TC-EVENTS-088 --------------------------------------------------------
def test_approved_is_no_longer_a_status_an_event_can_be_read_in(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(status="planning", decision="approved", **SUBMITTED)])

    response = client.get(f"/events/{EVENT_ID}")

    assert response.status_code == 200
    assert response.json()["status"] == "planning"
    assert response.json()["decision"] == "approved"

    with pytest.raises(ValidationError) as excinfo:
        EventRead.model_validate(event_row(status="approved", decision="approved", **SUBMITTED))
    assert any(error["loc"] == ("status",) for error in excinfo.value.errors())
