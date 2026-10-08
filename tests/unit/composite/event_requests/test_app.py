"""Unit tests for the event_requests composite service -- see TEST_CASES.md."""

import httpx
import pytest
from unittest.mock import call

from .conftest import (
    COORDINATOR_A,
    COORDINATOR_B,
    EVENT_ID,
    ORGANISER_ID,
    SUBMITTED,
    coordinator,
    event_response,
    events_patch_side_effect,
    events_post_coordinator_load_side_effect,
    events_post_raises_on_load,
    events_post_side_effect,
    events_post_side_effect_with_loads,
    fake_response,
    load_response,
    load_row,
    organiser_me_response,
    users_get_raises_on_coordinators,
    users_get_side_effect,
)


# --- TC-EVENTREQUESTS-001 --------------------------------------------------
def test_health_reports_ok(client, users, events):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    users.get.assert_not_called()
    events.get.assert_not_called()
    events.post.assert_not_called()


# --- TC-EVENTREQUESTS-013 --------------------------------------------------
def test_prefixed_health_reports_ok_for_gateway(client, users, events):
    response = client.get("/event-requests/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- TC-EVENTREQUESTS-002 --------------------------------------------------
def test_submit_requires_authentication(client, users, events):
    users.get.return_value = fake_response(401, {"detail": "Not authenticated"})

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 401
    events.post.assert_not_called()


# --- TC-EVENTREQUESTS-003 --------------------------------------------------
def test_submit_requires_organiser_role(client, users, events):
    users.get.return_value = organiser_me_response(role="event_coordinator")

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 403
    events.post.assert_not_called()


# --- TC-EVENTREQUESTS-004 --------------------------------------------------
def test_submit_validates_before_any_downstream_call(client, users, events):
    incomplete = {key: value for key, value in SUBMITTED.items() if key != "name"}

    response = client.post("/event-requests", json=incomplete)

    assert response.status_code == 422
    assert "name" in response.json()["errors"]
    users.get.assert_not_called()
    events.post.assert_not_called()


# --- TC-EVENTREQUESTS-005 --------------------------------------------------
@pytest.mark.skip(reason="Superseded by S-83 manual Lead assignment")
def test_submit_assigns_the_sole_eligible_coordinator(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.post.side_effect = events_post_side_effect(
        loads=[load_row(COORDINATOR_A, conflict=False, assigned_count=0)],
        create_path="/events/internal",
        create_status=201,
        create_body=event_response(assigned_coordinator_id=COORDINATOR_A).json(),
    )

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 201
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_A
    sent = events.post.call_args_list[-1].kwargs["json"]
    assert sent["organiser_id"] == ORGANISER_ID
    assert sent["assigned_coordinator_id"] == COORDINATOR_A


# --- TC-EVENTREQUESTS-006 --------------------------------------------------
@pytest.mark.skip(reason="Superseded by S-83 manual Lead assignment")
def test_submit_assigns_the_least_busy_of_several_eligible(client, users, events):
    users.get.side_effect = users_get_side_effect(
        coordinators=[coordinator(COORDINATOR_A), coordinator(COORDINATOR_B)]
    )
    events.post.side_effect = events_post_side_effect(
        loads=[
            load_row(COORDINATOR_A, conflict=False, assigned_count=0),
            load_row(COORDINATOR_B, conflict=False, assigned_count=2),
        ],
        create_path="/events/internal",
        create_status=201,
        create_body=event_response(assigned_coordinator_id=COORDINATOR_A).json(),
    )

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 201
    sent = events.post.call_args_list[-1].kwargs["json"]
    assert sent["assigned_coordinator_id"] == COORDINATOR_A


# --- TC-EVENTREQUESTS-007 --------------------------------------------------
@pytest.mark.skip(reason="Superseded by S-83 manual Lead assignment")
def test_submit_breaks_a_tie_in_load_at_random(client, users, events, monkeypatch):
    users.get.side_effect = users_get_side_effect(
        coordinators=[coordinator(COORDINATOR_A), coordinator(COORDINATOR_B)]
    )
    events.post.side_effect = events_post_side_effect(
        loads=[
            load_row(COORDINATOR_A, conflict=False, assigned_count=1),
            load_row(COORDINATOR_B, conflict=False, assigned_count=1),
        ],
        create_path="/events/internal",
        create_status=201,
        create_body=event_response(assigned_coordinator_id=COORDINATOR_B).json(),
    )

    recorded = {}

    def fake_choice(seq):
        recorded["seq"] = set(seq)
        return COORDINATOR_B

    # This retired S-12 test is skipped before its body executes. The former
    # random selector no longer exists because S-83 makes assignment manual.

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 201
    assert recorded["seq"] == {COORDINATOR_A, COORDINATOR_B}
    sent = events.post.call_args_list[-1].kwargs["json"]
    assert sent["assigned_coordinator_id"] == COORDINATOR_B


# --- TC-EVENTREQUESTS-008 --------------------------------------------------
@pytest.mark.skip(reason="S-83 does not block a Lead's choice on conflicts")
def test_submit_rejects_when_every_coordinator_conflicts(client, users, events):
    users.get.side_effect = users_get_side_effect(
        coordinators=[coordinator(COORDINATOR_A), coordinator(COORDINATOR_B)]
    )

    async def events_post(path, **kwargs):
        assert path == "/events/coordinator-load"
        return load_response(
            [
                load_row(COORDINATOR_A, conflict=True, assigned_count=1),
                load_row(COORDINATOR_B, conflict=True, assigned_count=1),
            ]
        )

    events.post.side_effect = events_post

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 409
    assert "coordinator" in response.json()["detail"].lower()


# --- TC-EVENTREQUESTS-009 --------------------------------------------------
@pytest.mark.skip(reason="S-83 accepts submission into the unassigned queue")
def test_submit_rejects_when_no_coordinator_accounts_exist(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[])

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 409
    events.post.assert_not_called()


# --- TC-EVENTREQUESTS-010 --------------------------------------------------
@pytest.mark.skip(reason="Superseded by S-83 unassigned first submission")
def test_submitting_an_existing_draft_goes_through_the_same_assignment(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.get.return_value = event_response(status_code=200, status="draft", assigned_coordinator_id=None)
    events.post.side_effect = events_post_side_effect(
        loads=[load_row(COORDINATOR_A, conflict=False, assigned_count=0)],
        create_path=f"/events/{EVENT_ID}/submit/internal",
        create_status=200,
        create_body=event_response(status_code=200, assigned_coordinator_id=COORDINATOR_A).json(),
    )

    response = client.post(f"/event-requests/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 200
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_A
    sent = events.post.call_args_list[-1].kwargs["json"]
    assert sent["organiser_id"] == ORGANISER_ID
    assert sent["assigned_coordinator_id"] == COORDINATOR_A


# --- TC-EVENTREQUESTS-011 --------------------------------------------------
@pytest.mark.skip(reason="Superseded S-12 fixture expected coordinator-load")
def test_events_service_failure_is_safe(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.post.side_effect = events_post_raises_on_load(httpx.ConnectError("boom"))

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 502
    assert "boom" not in response.text


# --- TC-EVENTREQUESTS-012 --------------------------------------------------
@pytest.mark.skip(reason="Superseded S-12 coordinator-pool lookup")
def test_users_service_failure_is_safe(client, users, events):
    users.get.side_effect = users_get_raises_on_coordinators(httpx.ConnectError("boom"))

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 502
    assert "boom" not in response.text
    events.post.assert_not_called()


# --- Editing a submitted, assigned event rechecks availability ------------
# TC-EVENTREQUESTS-014 through -020: PATCH /event-requests/{event_id}.

EDIT = {"venue": "Main auditorium"}
DATETIME_EDIT = {"start_time": "20:00"}


def _current(status_code=200, **overrides):
    return event_response(status_code=status_code, **overrides)


# --- TC-EVENTREQUESTS-014 --------------------------------------------------
def test_editing_a_draft_never_rechecks(client, users, events):
    users.get.return_value = organiser_me_response()
    events.get.return_value = _current(status="draft", assigned_coordinator_id=None)
    events.patch.side_effect = events_patch_side_effect(
        plain_response=fake_response(200, {"id": EVENT_ID, "status": "draft", "venue": "Room 9"})
    )

    response = client.patch(f"/event-requests/{EVENT_ID}", json={"venue": "Room 9"})

    assert response.status_code == 200
    events.post.assert_not_called()  # no coordinator-load call at all
    events.patch.assert_called_once()
    assert events.patch.call_args[0][0] == f"/events/{EVENT_ID}"


# --- TC-EVENTREQUESTS-015 --------------------------------------------------
def test_editing_a_non_datetime_field_on_a_submitted_event_never_rechecks(client, users, events):
    users.get.return_value = organiser_me_response()
    events.get.return_value = _current()
    events.patch.side_effect = events_patch_side_effect(
        plain_response=fake_response(200, {"id": EVENT_ID, "venue": "Room 9"})
    )

    response = client.patch(f"/event-requests/{EVENT_ID}", json=EDIT)

    assert response.status_code == 200
    events.post.assert_not_called()


# --- TC-EVENTREQUESTS-016 --------------------------------------------------
def test_resubmitting_the_same_datetime_never_rechecks(client, users, events):
    users.get.return_value = organiser_me_response()
    events.get.return_value = _current()  # start_time is already "18:00:00"
    events.patch.side_effect = events_patch_side_effect(
        plain_response=fake_response(200, {"id": EVENT_ID})
    )

    response = client.patch(f"/event-requests/{EVENT_ID}", json={"start_time": "18:00"})

    assert response.status_code == 200
    events.post.assert_not_called()


# --- TC-EVENTREQUESTS-017 --------------------------------------------------
@pytest.mark.skip(reason="S-83 edits never auto-recheck assignments")
def test_editing_the_datetime_keeps_the_current_coordinator_if_still_free(client, users, events):
    users.get.return_value = organiser_me_response()
    events.get.return_value = _current()
    events.post.side_effect = events_post_coordinator_load_side_effect(
        {COORDINATOR_A: {"conflict": False, "assigned_count": 0}}
    )
    events.patch.side_effect = events_patch_side_effect(
        plain_response=fake_response(200, {"id": EVENT_ID, "start_time": "20:00:00"})
    )

    response = client.patch(f"/event-requests/{EVENT_ID}", json=DATETIME_EDIT)

    assert response.status_code == 200
    # Only the has-conflict check runs; no full pool pick, no internal PATCH.
    assert events.post.call_count == 1
    load_call = events.post.call_args
    assert load_call[1]["json"]["coordinator_ids"] == [COORDINATOR_A]
    assert load_call[1]["json"]["exclude_event_id"] == EVENT_ID
    assert events.patch.call_args[0][0] == f"/events/{EVENT_ID}"


# --- TC-EVENTREQUESTS-018 --------------------------------------------------
@pytest.mark.skip(reason="S-83 edits never auto-reassign")
def test_editing_the_datetime_reassigns_when_the_current_coordinator_now_conflicts(client, users, events):
    users.get.side_effect = users_get_side_effect(
        coordinators=[coordinator(COORDINATOR_A), coordinator(COORDINATOR_B)]
    )
    events.get.return_value = _current()  # currently assigned to A
    events.post.side_effect = events_post_coordinator_load_side_effect(
        {
            COORDINATOR_A: {"conflict": True, "assigned_count": 1},
            COORDINATOR_B: {"conflict": False, "assigned_count": 0},
        }
    )
    events.patch.side_effect = events_patch_side_effect(
        internal_response=fake_response(
            200, {"id": EVENT_ID, "assigned_coordinator_id": COORDINATOR_B, "start_time": "20:00:00"}
        )
    )

    response = client.patch(f"/event-requests/{EVENT_ID}", json=DATETIME_EDIT)

    assert response.status_code == 200
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_B
    internal_call = events.patch.call_args
    assert internal_call[0][0] == f"/events/{EVENT_ID}/internal"
    assert internal_call[1]["json"]["assigned_coordinator_id"] == COORDINATOR_B
    assert internal_call[1]["json"]["organiser_id"] == ORGANISER_ID
    assert internal_call[1]["json"]["start_time"] == "20:00:00"


# --- TC-EVENTREQUESTS-019 --------------------------------------------------
@pytest.mark.skip(reason="S-83 removes automatic conflict rejection")
def test_editing_the_datetime_rejects_when_no_coordinator_is_free(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.get.return_value = _current()
    events.post.side_effect = events_post_coordinator_load_side_effect(
        {COORDINATOR_A: {"conflict": True, "assigned_count": 1}}
    )

    response = client.patch(f"/event-requests/{EVENT_ID}", json=DATETIME_EDIT)

    assert response.status_code == 409
    events.patch.assert_not_called()


# --- TC-EVENTREQUESTS-020 --------------------------------------------------
@pytest.mark.skip(reason="Replaced by the S-83 passthrough edit case")
def test_editing_an_event_that_is_not_found_is_404(client, users, events):
    users.get.return_value = organiser_me_response()
    events.get.return_value = fake_response(404, {"detail": "Event not found"})

    response = client.patch(f"/event-requests/{EVENT_ID}", json=EDIT)

    assert response.status_code == 404
    events.patch.assert_not_called()
    events.post.assert_not_called()


# --- S-14: resubmitting a returned request ---------------------------------
# TC-EVENTREQUESTS-021 through -025: POST /event-requests/{event_id}/submit
# for a request that is currently `returned`, not `draft`.


# --- TC-EVENTREQUESTS-021 --------------------------------------------------
@pytest.mark.skip(reason="Replaced by S-83 continuity without a conflict check")
def test_resubmitting_a_returned_request_keeps_the_same_coordinator_if_still_free(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.get.return_value = event_response(status_code=200, status="returned", assigned_coordinator_id=COORDINATOR_A)
    events.post.side_effect = events_post_side_effect_with_loads(
        {COORDINATOR_A: {"conflict": False, "assigned_count": 1}},
        extra_path=f"/events/{EVENT_ID}/submit/internal",
        extra_response=fake_response(
            200, event_response(status_code=200, assigned_coordinator_id=COORDINATOR_A).json()
        ),
    )

    response = client.post(f"/event-requests/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 200
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_A
    # Only the has-conflict check runs -- no full-pool pick, since the
    # current coordinator is still free.
    assert events.post.call_args_list[0][1]["json"]["coordinator_ids"] == [COORDINATOR_A]
    sent = events.post.call_args_list[-1].kwargs["json"]
    assert sent["assigned_coordinator_id"] == COORDINATOR_A


# --- TC-EVENTREQUESTS-022 --------------------------------------------------
@pytest.mark.skip(reason="S-83 returned requests are not automatically reassigned")
def test_resubmitting_a_returned_request_reassigns_when_the_coordinator_now_conflicts(client, users, events):
    users.get.side_effect = users_get_side_effect(
        coordinators=[coordinator(COORDINATOR_A), coordinator(COORDINATOR_B)]
    )
    events.get.return_value = event_response(status_code=200, status="returned", assigned_coordinator_id=COORDINATOR_A)
    events.post.side_effect = events_post_side_effect_with_loads(
        {
            COORDINATOR_A: {"conflict": True, "assigned_count": 1},
            COORDINATOR_B: {"conflict": False, "assigned_count": 0},
        },
        extra_path=f"/events/{EVENT_ID}/submit/internal",
        extra_response=fake_response(
            200, event_response(status_code=200, assigned_coordinator_id=COORDINATOR_B).json()
        ),
    )

    response = client.post(f"/event-requests/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 200
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_B
    sent = events.post.call_args_list[-1].kwargs["json"]
    assert sent["assigned_coordinator_id"] == COORDINATOR_B


# --- TC-EVENTREQUESTS-023 --------------------------------------------------
@pytest.mark.skip(reason="S-83 returned requests keep their coordinator")
def test_resubmitting_a_returned_request_rejects_when_no_one_is_free(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.get.return_value = event_response(status_code=200, status="returned", assigned_coordinator_id=COORDINATOR_A)
    events.post.side_effect = events_post_coordinator_load_side_effect(
        {COORDINATOR_A: {"conflict": True, "assigned_count": 1}}
    )

    response = client.post(f"/event-requests/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 409


# --- TC-EVENTREQUESTS-024 --------------------------------------------------
def test_resubmitting_an_event_that_is_not_found_is_404(client, users, events):
    users.get.return_value = organiser_me_response()
    events.get.return_value = fake_response(404, {"detail": "Event not found"})

    response = client.post(f"/event-requests/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 404
    users.get.assert_called_once()  # only /users/me -- no coordinator lookup
    events.post.assert_not_called()


# --- TC-EVENTREQUESTS-025 --------------------------------------------------
@pytest.mark.skip(reason="S-83 first draft submission enters the queue")
def test_a_draft_submission_still_picks_fresh_with_no_prior_coordinator(client, users, events):
    """Unaffected by the resubmit logic above: a draft has no assignment to
    recheck, so this is the same fresh, whole-pool pick as before.
    """
    users.get.side_effect = users_get_side_effect(
        coordinators=[coordinator(COORDINATOR_A), coordinator(COORDINATOR_B)]
    )
    events.get.return_value = event_response(status_code=200, status="draft", assigned_coordinator_id=None)
    events.post.side_effect = events_post_side_effect_with_loads(
        {
            COORDINATOR_A: {"conflict": False, "assigned_count": 3},
            COORDINATOR_B: {"conflict": False, "assigned_count": 0},
        },
        extra_path=f"/events/{EVENT_ID}/submit/internal",
        extra_response=fake_response(
            200, event_response(status_code=200, assigned_coordinator_id=COORDINATOR_B).json()
        ),
    )

    response = client.post(f"/event-requests/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 200
    sent = events.post.call_args_list[-1].kwargs["json"]
    assert sent["assigned_coordinator_id"] == COORDINATOR_B


# --- S-13: failed resubmissions write nothing ------------------------------

SUBMIT_INTERNAL = f"/events/{EVENT_ID}/submit/internal"
NO_LONGER_AWAITING_CHANGES = "This request is no longer awaiting changes. Reload to see its current status."


def _paths_posted(events):
    return [call.args[0] for call in events.post.call_args_list]


# --- TC-EVENTREQUESTS-026 --------------------------------------------------
@pytest.mark.skip(reason="S-83 no longer checks coordinator availability on resubmit")
def test_no_free_coordinator_means_the_returned_event_is_never_written(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.get.return_value = event_response(status_code=200, status="returned", assigned_coordinator_id=COORDINATOR_A)
    events.post.side_effect = events_post_coordinator_load_side_effect(
        {COORDINATOR_A: {"conflict": True, "assigned_count": 1}}
    )

    response = client.post(f"/event-requests/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 409
    assert response.json()["detail"] == "No event coordinator is available for the requested date and time"
    assert SUBMIT_INTERNAL not in _paths_posted(events)


# --- TC-EVENTREQUESTS-027 --------------------------------------------------
def test_an_unreachable_events_service_on_resubmit_is_502(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.get.return_value = event_response(status_code=200, status="returned", assigned_coordinator_id=COORDINATOR_A)
    check_load = events_post_coordinator_load_side_effect({COORDINATOR_A: {"conflict": False, "assigned_count": 1}})

    async def _post(path, **kwargs):
        if path == SUBMIT_INTERNAL:
            raise httpx.ConnectError("events unreachable")
        return await check_load(path, **kwargs)

    events.post.side_effect = _post

    response = client.post(f"/event-requests/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 502
    assert response.json()["detail"] == "Events service unavailable"


# --- TC-EVENTREQUESTS-028 --------------------------------------------------
def test_a_status_change_underneath_the_resubmission_is_passed_back_as_409(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.get.return_value = event_response(status_code=200, status="returned", assigned_coordinator_id=COORDINATOR_A)
    events.post.side_effect = events_post_side_effect_with_loads(
        {COORDINATOR_A: {"conflict": False, "assigned_count": 1}},
        extra_path=SUBMIT_INTERNAL,
        extra_response=fake_response(409, {"detail": NO_LONGER_AWAITING_CHANGES}),
    )

    response = client.post(f"/event-requests/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 409
    assert response.json()["detail"] == NO_LONGER_AWAITING_CHANGES


# --- S-36: venue requirements on the event ----------------------------------


# --- TC-EVENTREQUESTS-029 --------------------------------------------------
def test_venue_requirements_pass_through_to_the_events_service(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.post.side_effect = events_post_side_effect(
        loads=[load_row(COORDINATOR_A, conflict=False, assigned_count=0)],
        create_path="/events/internal",
        create_status=201,
        create_body=event_response(assigned_coordinator_id=COORDINATOR_A).json(),
    )
    requirements = {
        "room_layout": "theatre",
        "required_facilities": ["projector"],
        "required_accessibility": ["lift"],
    }
    without_venue = {key: value for key, value in SUBMITTED.items() if key != "venue"}

    response = client.post("/event-requests", json={**without_venue, **requirements})

    assert response.status_code == 201
    sent = events.post.call_args_list[-1].kwargs["json"]
    assert sent["venue"] is None
    for field, value in requirements.items():
        assert sent[field] == value


# --- TC-EVENTREQUESTS-030 --------------------------------------------------
def test_venue_requirements_outside_the_catalogue_are_refused_first(client, users, events):
    response = client.post("/event-requests", json={**SUBMITTED, "required_facilities": ["jacuzzi"]})

    assert response.status_code == 422
    assert any(key.startswith("required_facilities") for key in response.json()["errors"])
    users.get.assert_not_called()
    events.post.assert_not_called()


SUPPORT_A = "44444444-4444-4444-8444-444444444444"
SUPPORT_B = "55555555-5555-4555-8555-555555555555"


def support_profile(user_id, name):
    return {"id": user_id, "name": name, "email": f"{name.lower()}@example.com"}


def planning_event(**changes):
    values = {
        "status": "planning",
        "assigned_coordinator_id": COORDINATOR_A,
        "technical_support_required": False,
        "technical_support_details": None,
        "assigned_technical_support_id": None,
        "technical_support_assigned_at": None,
        **changes,
    }
    return event_response(status_code=200, **values)


def support_users(pool, role="event_coordinator"):
    async def _get(path, **kwargs):
        if path == "/users/me":
            return organiser_me_response(user_id=COORDINATOR_A, role=role)
        if path == "/users/technical-support":
            return fake_response(200, pool)
        raise AssertionError(f"unexpected users.get({path!r})")
    return _get


def assigned_support_event(staff_id=SUPPORT_A, details="Sound check"):
    return planning_event(
        technical_support_required=True,
        technical_support_details=details,
        assigned_technical_support_id=staff_id,
        technical_support_assigned_at="2026-09-29T09:00:00Z",
    )


# --- TC-EVENTREQUESTS-031 --------------------------------------------------
@pytest.mark.parametrize(
    ("role", "expected"),
    [("event_organiser", 403), ("technical_support", 403), (None, 403)],
)
def test_only_the_assigned_coordinator_requests_support_assignment(client, users, events, role, expected):
    users.get.side_effect = support_users([], role=role)

    response = client.post(
        f"/event-requests/{EVENT_ID}/technical-support-assignment", json={}
    )

    assert response.status_code == expected
    events.get.assert_not_called()


def test_unassigned_coordinator_cannot_request_support(client, users, events):
    users.get.side_effect = support_users([])
    events.get.return_value = fake_response(404, {"detail": "Event not found"})

    response = client.post(
        f"/event-requests/{EVENT_ID}/technical-support-assignment", json={}
    )

    assert response.status_code == 404
    events.post.assert_not_called()
    events.put.assert_not_called()


# --- TC-EVENTREQUESTS-032 --------------------------------------------------
def test_assignment_runs_only_after_explicit_support_action(client, users, events):
    users.get.side_effect = support_users([])
    events.get.return_value = planning_event()

    response = client.get(
        f"/event-requests/{EVENT_ID}/technical-support-assignment"
    )

    assert response.status_code == 200
    assert response.json()["assignment_state"] == "not_required"
    assert [call.args[0] for call in users.get.call_args_list] == ["/users/me"]
    events.post.assert_not_called()
    events.put.assert_not_called()


# --- TC-EVENTREQUESTS-033 / 034 / 035 ------------------------------------
def test_support_assignment_chooses_least_busy_then_lowest_id(client, users, events):
    pool = [support_profile(SUPPORT_B, "SupportB"), support_profile(SUPPORT_A, "SupportA")]
    users.get.side_effect = support_users(pool)
    events.get.return_value = planning_event()
    events.post.return_value = fake_response(
        200,
        [
            {"staff_id": SUPPORT_B, "conflict": False, "assigned_count": 1},
            {"staff_id": SUPPORT_A, "conflict": False, "assigned_count": 1},
        ],
    )
    events.put.return_value = assigned_support_event(SUPPORT_A)

    response = client.post(
        f"/event-requests/{EVENT_ID}/technical-support-assignment",
        json={"support_details": "  Sound check  "},
    )

    assert response.status_code == 200
    assert response.json()["assignment_state"] == "assigned"
    assert response.json()["assigned_staff"]["id"] == SUPPORT_A
    assert events.put.call_args.kwargs["json"] == {
        "coordinator_id": COORDINATOR_A,
        "technical_support_details": "Sound check",
        "assigned_technical_support_id": SUPPORT_A,
    }


# --- TC-EVENTREQUESTS-036 --------------------------------------------------
@pytest.mark.parametrize("pool", [[], [support_profile(SUPPORT_A, "SupportA")]])
def test_no_available_support_staff_is_recorded_honestly(client, users, events, pool):
    users.get.side_effect = support_users(pool)
    events.get.return_value = planning_event()
    events.post.return_value = fake_response(
        200, [{"staff_id": SUPPORT_A, "conflict": True, "assigned_count": 2}]
    )
    events.put.return_value = planning_event(
        technical_support_required=True,
        technical_support_details="Sound check",
    )

    response = client.post(
        f"/event-requests/{EVENT_ID}/technical-support-assignment",
        json={"support_details": "Sound check"},
    )

    assert response.status_code == 200
    assert response.json()["assignment_state"] == "unassigned"
    assert "currently available" in response.json()["message"]
    assert events.put.call_args.kwargs["json"]["assigned_technical_support_id"] is None


# --- TC-EVENTREQUESTS-037 --------------------------------------------------
def test_existing_support_assignment_is_returned_without_reassignment(client, users, events):
    pool = [support_profile(SUPPORT_A, "SupportA")]
    users.get.side_effect = support_users(pool)
    events.get.return_value = assigned_support_event()

    unchanged = client.post(
        f"/event-requests/{EVENT_ID}/technical-support-assignment",
        json={"support_details": "Sound check"},
    )

    assert unchanged.status_code == 200
    events.post.assert_not_called()
    events.put.assert_not_called()

    events.put.return_value = assigned_support_event(details="Updated notes")
    changed = client.post(
        f"/event-requests/{EVENT_ID}/technical-support-assignment",
        json={"support_details": "Updated notes"},
    )
    assert changed.status_code == 200
    assert changed.json()["assigned_technical_support_id"] == SUPPORT_A
    assert changed.json()["technical_support_assigned_at"] == "2026-09-29T09:00:00Z"
    events.post.assert_not_called()


# --- TC-EVENTREQUESTS-038 --------------------------------------------------
@pytest.mark.parametrize(
    "event_status",
    ["draft", "submitted", "returned", "rejected", "confirmed", "completed", "cancelled"],
)
def test_support_assignment_rejects_every_non_planning_target(client, users, events, event_status):
    users.get.side_effect = support_users([])
    events.get.return_value = planning_event(status=event_status)

    response = client.post(
        f"/event-requests/{EVENT_ID}/technical-support-assignment", json={}
    )

    assert response.status_code == 409
    assert [call.args[0] for call in users.get.call_args_list] == ["/users/me"]
    events.post.assert_not_called()
    events.put.assert_not_called()


# --- TC-EVENTREQUESTS-039 --------------------------------------------------
def test_support_assignment_preserves_a_stale_write_conflict(client, users, events):
    pool = [support_profile(SUPPORT_A, "SupportA")]
    users.get.side_effect = support_users(pool)
    events.get.return_value = planning_event()
    events.post.return_value = fake_response(
        200, [{"staff_id": SUPPORT_A, "conflict": False, "assigned_count": 0}]
    )
    events.put.return_value = fake_response(409, {"detail": "The event changed"})

    response = client.post(
        f"/event-requests/{EVENT_ID}/technical-support-assignment", json={}
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "The event changed"}
