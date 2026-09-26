"""Unit tests for the event_requests composite service -- see TEST_CASES.md."""

import httpx

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
    random_module,
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

    monkeypatch.setattr(random_module, "choice", fake_choice)

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 201
    assert recorded["seq"] == {COORDINATOR_A, COORDINATOR_B}
    sent = events.post.call_args_list[-1].kwargs["json"]
    assert sent["assigned_coordinator_id"] == COORDINATOR_B


# --- TC-EVENTREQUESTS-008 --------------------------------------------------
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
def test_submit_rejects_when_no_coordinator_accounts_exist(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[])

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 409
    events.post.assert_not_called()


# --- TC-EVENTREQUESTS-010 --------------------------------------------------
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
def test_events_service_failure_is_safe(client, users, events):
    users.get.side_effect = users_get_side_effect(coordinators=[coordinator(COORDINATOR_A)])
    events.post.side_effect = events_post_raises_on_load(httpx.ConnectError("boom"))

    response = client.post("/event-requests", json=SUBMITTED)

    assert response.status_code == 502
    assert "boom" not in response.text


# --- TC-EVENTREQUESTS-012 --------------------------------------------------
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
