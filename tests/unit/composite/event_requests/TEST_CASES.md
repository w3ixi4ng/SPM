# Test cases — event_requests service (unit)

Covers `test_app.py`, `test_s83.py`, and `test_s84.py`: the composite workflows spanning the
events, users, and notifications atomic services. All three outbound HTTP
clients are faked; no network, database, or Docker.

| | |
| --- | --- |
| Suite | `pytest tests/unit/composite/event_requests` |
| Last run | 2026-10-18, branch `S-85/view-coordinator-assignments-and-active-events`, uncommitted working tree |
| Environment | Python 3.14.8, pytest 9.1.1; no network, database, or Docker |
| Result | 86 passed, 17 superseded S-12 cases skipped; 840 passed, 17 skipped across `tests/unit` |

**Story:** S-12 — when an organiser submits an event request, it is routed to
an event coordinator who has no other assigned event overlapping the
requested date/time range.

**Shared pre-conditions.** The FastAPI app built with `get_events_client` and
`get_users_client` overridden by fakes that record every call made through
them. A valid organiser session cookie authenticates via a faked
`GET /users/me` call unless a case says otherwise.

**Shared test data.**

```
organiser_id    11111111-1111-4111-8111-111111111111
coordinator A   aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa  (0 assigned events)
coordinator B   bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb  (2 assigned events)
event window    2026-10-20 18:00 -- 2026-10-20 21:00
submitted body  name, purpose, start/end date+time, expected_attendance,
                -- the same fields EventSubmittedCreate requires; venue is
                an optional preference since S-36
```

---

## TC-EVENTREQUESTS-001 — health check

- **Scenario:** The service reports itself up without calling either
  downstream client.
- **Pre-conditions:** Shared.
- **Steps:** `GET /health`.
- **Test data:** None.
- **Expected:** `200`, `{"status": "ok"}`; neither client called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_health_reports_ok`

## TC-EVENTREQUESTS-002 — authentication is required

- **Scenario:** A caller with no session cannot submit a request.
- **Pre-conditions:** No cookies on the request.
- **Steps:** `POST /event-requests` with the shared submitted body.
- **Test data:** Shared submitted body, no cookies.
- **Expected:** `401`; neither the users-coordinator lookup nor the events
  client is called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submit_requires_authentication`

## TC-EVENTREQUESTS-003 — only an event organiser may submit a request

- **Scenario:** A verified session with a different trusted role is refused.
- **Pre-conditions:** `GET /users/me` resolves to role `event_coordinator`.
- **Steps:** `POST /event-requests` with the shared submitted body.
- **Test data:** Shared submitted body.
- **Expected:** `403`; the events client is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submit_requires_organiser_role`

## TC-EVENTREQUESTS-004 — the request body is validated before any downstream call

- **Scenario:** Revised for S-36: `venue` is now an optional preference, so `name` stands in as the required field. An incomplete submission fails the same way it would against
  the events service directly, without spending a call on either dependency.
- **Pre-conditions:** Authenticated organiser.
- **Steps:** `POST /event-requests` with `name` omitted.
- **Test data:** Shared submitted body minus `name`.
- **Expected:** `422` identifying `name`; neither client called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submit_validates_before_any_downstream_call`

## TC-EVENTREQUESTS-005 — the sole eligible coordinator is assigned

- **Scenario:** One coordinator exists and has no conflict; they get the event.
- **Pre-conditions:** `GET /users/coordinators` returns only coordinator A;
  the events coordinator-load call reports A with `conflict: false,
  assigned_count: 0`; the internal create call echoes back the created event.
- **Steps:** `POST /event-requests` with the shared submitted body and window.
- **Test data:** Shared.
- **Expected:** `201`; response `assigned_coordinator_id` is coordinator A's
  id; the internal create call is sent `organiser_id` = the session's id and
  `assigned_coordinator_id` = coordinator A's id.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submit_assigns_the_sole_eligible_coordinator`

## TC-EVENTREQUESTS-006 — the least busy of several eligible coordinators is chosen

- **Scenario:** Both coordinators are free for the window, but one already
  carries more assigned load.
- **Pre-conditions:** `GET /users/coordinators` returns A and B; the
  coordinator-load call reports A `conflict: false, assigned_count: 0` and B
  `conflict: false, assigned_count: 2`.
- **Steps:** `POST /event-requests` with the shared body.
- **Test data:** Shared.
- **Expected:** `201`; assigned coordinator is A (`assigned_count: 0` beats
  `2`).
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submit_assigns_the_least_busy_of_several_eligible`

## TC-EVENTREQUESTS-007 — a tie in load is broken at random

- **Scenario:** Two coordinators are both free and equally loaded; the choice
  between them is not deterministic by id or list order.
- **Pre-conditions:** Coordinator-load reports A and B both `conflict: false,
  assigned_count: 1`. `random.choice` is monkeypatched to a stub that records
  its argument and returns a fixed element.
- **Steps:** `POST /event-requests` with the shared body.
- **Test data:** Shared.
- **Expected:** `random.choice` is called exactly once, with a sequence
  containing exactly A and B (order not asserted) and nothing else; the
  assigned coordinator in the response is whichever id the stub returned.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submit_breaks_a_tie_in_load_at_random`

## TC-EVENTREQUESTS-008 — every coordinator conflicts

- **Scenario:** No one is free for the requested window, so the request is
  refused rather than assigned to someone double-booked.
- **Pre-conditions:** `GET /users/coordinators` returns A and B; the
  coordinator-load call reports both `conflict: true`.
- **Steps:** `POST /event-requests` with the shared body.
- **Test data:** Shared.
- **Expected:** `409` with a message naming that no coordinator is available;
  the internal create call is never made.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submit_rejects_when_every_coordinator_conflicts`

## TC-EVENTREQUESTS-009 — no event coordinator accounts exist

- **Scenario:** A fresh deployment with no one in the role fails the same way
  as everyone being busy, not with a different error a caller has to special-case.
- **Pre-conditions:** `GET /users/coordinators` returns `[]`.
- **Steps:** `POST /event-requests` with the shared body.
- **Test data:** Shared.
- **Expected:** `409`, identical shape to TC-EVENTREQUESTS-008; the
  coordinator-load call and the internal create call are never made.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submit_rejects_when_no_coordinator_accounts_exist`

## TC-EVENTREQUESTS-010 — submitting an existing draft goes through the same assignment

- **Scenario:** The draft-then-submit path is assigned exactly like a direct
  submission, not left uncovered by this story.
- **Pre-conditions:** As TC-EVENTREQUESTS-005, one eligible coordinator.
- **Steps:** `POST /event-requests/{event_id}/submit` with the shared body.
- **Test data:** A draft id owned by the authenticated organiser.
- **Expected:** `200`; the internal submit-with-assignment call on the events
  client is sent `event_id`, `organiser_id`, `assigned_coordinator_id`, and
  the submitted fields; response carries the assigned coordinator.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submitting_an_existing_draft_goes_through_the_same_assignment`

## TC-EVENTREQUESTS-011 — a downstream events-service failure is safe

- **Scenario:** An unreachable or erroring events service does not leak
  internals to the organiser.
- **Pre-conditions:** The coordinator-load call raises a connection error.
- **Steps:** `POST /event-requests` with the shared body.
- **Test data:** Shared.
- **Expected:** `502` with a generic detail; no stack trace or upstream text
  in the body.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_events_service_failure_is_safe`

## TC-EVENTREQUESTS-012 — a downstream users-service failure is safe

- **Scenario:** Same as TC-EVENTREQUESTS-011, for the coordinator lookup.
- **Pre-conditions:** `GET /users/coordinators` raises a connection error.
- **Steps:** `POST /event-requests` with the shared body.
- **Test data:** Shared.
- **Expected:** `502` with a generic detail; the events client is never
  called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_users_service_failure_is_safe`

## TC-EVENTREQUESTS-013 — gateway-compatible health path

- **Scenario:** Kong can check health beneath the service's own route prefix,
  same pattern as the atomic services.
- **Pre-conditions:** Shared.
- **Steps:** `GET /event-requests/health`.
- **Test data:** None.
- **Expected:** `200`, `{"status": "ok"}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_prefixed_health_reports_ok_for_gateway`

---

**Follow-up (same session).** `PATCH /event-requests/{event_id}` — editing a
submitted event's date/time never rechecked the assigned coordinator before
this. Fetches the current event via the organiser's forwarded session first,
then decides: recheck only when it is currently `submitted`, assigned, and
the edit actually changes one of the four date/time fields to a different
value than it already had.

## TC-EVENTREQUESTS-014 — editing a draft never rechecks

- **Scenario:** A draft has no assignment to recheck.
- **Pre-conditions:** `GET /events/{id}` (forwarded) reports `status: draft`,
  `assigned_coordinator_id: null`.
- **Steps:** `PATCH /event-requests/{event_id}` with any field.
- **Test data:** `{"venue": "Room 9"}`.
- **Expected:** `200`; the edit is forwarded as-is to the plain
  `PATCH /events/{event_id}`; the events coordinator-load endpoint is never
  called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_editing_a_draft_never_rechecks`

## TC-EVENTREQUESTS-015 — editing a non-datetime field on a submitted event never rechecks

- **Scenario:** Only the four date/time fields can create a scheduling
  conflict; nothing else is worth a recheck.
- **Pre-conditions:** `GET /events/{id}` reports `status: submitted` with an
  assigned coordinator.
- **Steps:** `PATCH /event-requests/{event_id}` with `venue` only.
- **Test data:** `{"venue": "Main auditorium"}`.
- **Expected:** `200`; forwarded as a plain passthrough; coordinator-load
  never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_editing_a_non_datetime_field_on_a_submitted_event_never_rechecks`

## TC-EVENTREQUESTS-016 — resubmitting the same date/time never rechecks

- **Scenario:** Presence of a date/time key in the request is not enough on
  its own — the value has to actually differ from what is already stored,
  since a form that always sends every field would otherwise trigger a
  recheck on every save.
- **Pre-conditions:** `GET /events/{id}` reports `start_time: "18:00:00"`.
- **Steps:** `PATCH /event-requests/{event_id}` with `start_time: "18:00"`
  (the same instant, organiser-style input without seconds).
- **Test data:** As above.
- **Expected:** `200`; forwarded as a plain passthrough; coordinator-load
  never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_resubmitting_the_same_datetime_never_rechecks`

## TC-EVENTREQUESTS-017 — the current coordinator is kept if still free

- **Scenario:** A recheck that finds no conflict makes no reassignment —
  only a plain edit is forwarded, not an internal write.
- **Pre-conditions:** `GET /events/{id}` reports `submitted`, assigned to
  coordinator A; the coordinator-load call for A alone (with
  `exclude_event_id` set) reports `conflict: false`.
- **Steps:** `PATCH /event-requests/{event_id}` changing `start_time`.
- **Test data:** `{"start_time": "20:00"}`.
- **Expected:** `200`; exactly one coordinator-load call, for `[A]` with
  `exclude_event_id` equal to the event's id; the edit is forwarded to the
  plain `PATCH /events/{event_id}`, not the internal route.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_editing_the_datetime_keeps_the_current_coordinator_if_still_free`

## TC-EVENTREQUESTS-018 — reassigns when the current coordinator now conflicts

- **Scenario:** A recheck that finds a conflict runs the full assignment
  logic and writes the edit and the new assignment together.
- **Pre-conditions:** As TC-EVENTREQUESTS-017, but coordinator A's recheck
  reports `conflict: true`; a second coordinator B is conflict-free.
- **Steps:** `PATCH /event-requests/{event_id}` changing `start_time`.
- **Test data:** `{"start_time": "20:00"}`.
- **Expected:** `200`; response `assigned_coordinator_id` is B; the internal
  `PATCH /events/{event_id}/internal` call carries `organiser_id`,
  `assigned_coordinator_id: B`, and the changed `start_time` together.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_editing_the_datetime_reassigns_when_the_current_coordinator_now_conflicts`

## TC-EVENTREQUESTS-019 — rejected when no coordinator is free after a conflict

- **Scenario:** Same all-busy guarantee as submission: nothing is written
  rather than leaving the event double-booked or unassigned.
- **Pre-conditions:** The only coordinator, A, reports `conflict: true` on
  recheck.
- **Steps:** `PATCH /event-requests/{event_id}` changing `start_time`.
- **Test data:** `{"start_time": "20:00"}`.
- **Expected:** `409`; neither the plain nor the internal PATCH is ever
  called — the event is left exactly as it was.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_editing_the_datetime_rejects_when_no_coordinator_is_free`

## TC-EVENTREQUESTS-020 — editing an event that is not found is 404

- **Scenario:** Ownership and existence are checked before anything else,
  the same as every other route here.
- **Pre-conditions:** `GET /events/{id}` (forwarded) returns `404`.
- **Steps:** `PATCH /event-requests/{event_id}` with any field.
- **Test data:** `{"venue": "Main auditorium"}`.
- **Expected:** `404`; neither a coordinator-load call nor any PATCH is made.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_editing_an_event_that_is_not_found_is_404`

---

**S-14 additions.** `POST /event-requests/{event_id}/submit` now also
handles resubmitting a `returned` request, not only a first-time draft
submission — S-14 requires the organiser to be able to edit and resubmit a
returned request as the same record. The two cases pick a coordinator
differently: a draft has no prior assignment, so it is a fresh pick across
the whole pool (unchanged); a returned request already has one, so
resubmitting keeps that coordinator if they are still free and only falls
back to a fresh pick when they are not — the same recheck-then-reassign
shape as editing a submitted event's date/time (TC-EVENTREQUESTS-017/018).

## TC-EVENTREQUESTS-021 — resubmitting a returned request keeps the same coordinator if still free

- **Pre-conditions:** `GET /events/{id}` (forwarded) reports `status:
  returned`, assigned to coordinator A; the has-conflict check for A alone
  reports `conflict: false`.
- **Steps:** `POST /event-requests/{event_id}/submit` with the standard
  submitted payload.
- **Test data:** As above.
- **Expected:** `200`; response `assigned_coordinator_id` is still A; only
  the has-conflict check runs, not a full-pool pick.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_resubmitting_a_returned_request_keeps_the_same_coordinator_if_still_free`

## TC-EVENTREQUESTS-022 — resubmitting reassigns when the coordinator now conflicts

- **Pre-conditions:** As above, but coordinator A's has-conflict check
  reports `conflict: true`; a second coordinator B is conflict-free.
- **Steps:** `POST /event-requests/{event_id}/submit` with the standard
  submitted payload.
- **Test data:** As above.
- **Expected:** `200`; response `assigned_coordinator_id` is B; the internal
  submit call carries B, not A.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_resubmitting_a_returned_request_reassigns_when_the_coordinator_now_conflicts`

## TC-EVENTREQUESTS-023 — resubmitting rejects when no one is free

- **Pre-conditions:** As TC-EVENTREQUESTS-022, but the only coordinator, A,
  conflicts and no one else exists.
- **Steps:** `POST /event-requests/{event_id}/submit` with the standard
  submitted payload.
- **Test data:** As above.
- **Expected:** `409`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_resubmitting_a_returned_request_rejects_when_no_one_is_free`

## TC-EVENTREQUESTS-024 — resubmitting an event that is not found is 404

- **Pre-conditions:** `GET /events/{id}` (forwarded) returns `404`.
- **Steps:** `POST /event-requests/{event_id}/submit` with the standard
  submitted payload.
- **Test data:** None.
- **Expected:** `404`; only `/users/me` is called -- no coordinator lookup,
  no events.post call at all.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_resubmitting_an_event_that_is_not_found_is_404`

## TC-EVENTREQUESTS-025 — a draft submission still picks fresh with no prior coordinator

- **Scenario:** Confirms the resubmit logic above does not change the
  original, unrelated case: a draft has nothing to recheck.
- **Pre-conditions:** `GET /events/{id}` reports `status: draft`,
  `assigned_coordinator_id: null`; two coordinators, unequal load.
- **Steps:** `POST /event-requests/{event_id}/submit` with the standard
  submitted payload.
- **Test data:** Coordinator A with load 3, coordinator B with load 0, both
  conflict-free.
- **Expected:** `200`; assigned to B, the least busy.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_draft_submission_still_picks_fresh_with_no_prior_coordinator`

## S-13 — failed resubmissions write nothing

TC-EVENTREQUESTS-021 to -024 cover how a resubmission picks its coordinator.
The cases below cover S-13 AC6: when a resubmission fails, the composite
either never writes or passes the failure straight back.

## TC-EVENTREQUESTS-026 — no free coordinator means the returned event is never written

- **Scenario:** Extends TC-EVENTREQUESTS-023. The refusal happens before any
  write, so the stored event keeps its previous details.
- **Pre-conditions:** `GET /events/{id}` reports `status: returned`, assigned
  to coordinator A; A conflicts at the amended window; no other coordinator
  exists.
- **Steps:** `POST /event-requests/{event_id}/submit` with the standard
  submitted payload.
- **Test data:** As above.
- **Expected:** `409`; `detail` is
  `"No event coordinator is available for the requested date and time"`;
  `events.post` is never called with `/events/{event_id}/submit/internal`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_no_free_coordinator_means_the_returned_event_is_never_written`

## TC-EVENTREQUESTS-027 — an unreachable events service on resubmit is 502

- **Pre-conditions:** `GET /events/{id}` reports `status: returned`, assigned
  to A; A is free; `events.post` to `/submit/internal` raises
  `httpx.ConnectError`.
- **Steps:** `POST /event-requests/{event_id}/submit` with the standard
  submitted payload.
- **Test data:** As above.
- **Expected:** `502`; `detail` is `"Events service unavailable"`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_an_unreachable_events_service_on_resubmit_is_502`

## TC-EVENTREQUESTS-028 — a status change underneath the resubmission is passed back as 409

- **Pre-conditions:** `GET /events/{id}` reports `status: returned`, assigned
  to A; A is free; `/submit/internal` answers `409`.
- **Steps:** `POST /event-requests/{event_id}/submit` with the standard
  submitted payload.
- **Test data:** As above.
- **Expected:** `409`; `detail` is
  `"This request is no longer awaiting changes. Reload to see its current status."`,
  the same wording as TC-EVENTS-086.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_status_change_underneath_the_resubmission_is_passed_back_as_409`

---

**S-36 venue requirements.** The organiser's submission can carry the
event's venue requirements and no venue.

## TC-EVENTREQUESTS-029 — venue requirements pass through to the events service

- **Pre-conditions:** Shared; one free coordinator.
- **Steps:** `POST /event-requests` with the shared body minus `venue`, plus
  `room_layout: "theatre"`, `required_facilities: ["projector"]`,
  `required_accessibility: ["lift"]`.
- **Test data:** As above.
- **Expected:** `201`. The body sent to `POST /events/internal` carries the
  three fields as given and `venue: null`.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_venue_requirements_pass_through_to_the_events_service`

## TC-EVENTREQUESTS-030 — venue requirements outside the catalogue are refused first

- **Pre-conditions:** Shared.
- **Steps:** `POST /event-requests` with `required_facilities: ["jacuzzi"]`.
- **Test data:** As above.
- **Expected:** `422` naming `required_facilities`; neither client called.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_venue_requirements_outside_the_catalogue_are_refused_first`

---

## S-43 — Auto-Assign Technical Support

The existing composite already owns the `users` + `events` boundary. S-43 uses
an explicit `POST /event-requests/{event_id}/technical-support-assignment`
action whose optional body field is `support_details`; the action itself is
the Coordinator's explicit indication that support is required. A companion
GET returns the persisted requirement and the assigned profile after reload.

## TC-EVENTREQUESTS-031 — only the currently assigned Coordinator can request assignment

- **Pre-conditions:** Anonymous user, every wrong authenticated role, an
  Event Coordinator not assigned to the event, then its assigned Coordinator.
- **Steps:** Call the S-43 POST action as each identity.
- **Expected:** Anonymous returns `401`; all wrong roles return `403`; an
  unassigned Coordinator receives `404`; only the current assigned Coordinator
  proceeds to availability lookup. No client-supplied staff id is accepted.
- **Actual:** As expected in the full unit run.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_the_assigned_coordinator_requests_support_assignment`

## TC-EVENTREQUESTS-032 — assignment runs only after the explicit support action

- **Scenario:** Equipment requirements alone never imply on-site support.
- **Pre-conditions:** A planning event may have S-40 requirements but its
  support fields are still false/null/null.
- **Steps:** Read the support state, then call the explicit POST action with
  details `Wireless microphone setup and sound check`.
- **Expected:** The GET before the action makes no staff/load/write calls and
  reports support not required. Only the POST obtains candidates and records
  required=true with the normalized details.
- **Actual:** As expected in the full unit run.
- **Status:** Pass
- **Evidence:** `test_app.py::test_assignment_runs_only_after_explicit_support_action`

## TC-EVENTREQUESTS-033 — the sole available Technical Support Staff member is assigned

- **Pre-conditions:** The trusted pool contains Staff A; load reports no
  conflict.
- **Steps:** Request assignment for a planning event.
- **Expected:** The composite sends Staff A to the guarded events write and
  returns the saved requirement plus A's id, name, and email.
- **Actual:** As expected in the full unit run.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_sole_available_support_staff_member_is_assigned`

## TC-EVENTREQUESTS-034 — overlapping live work removes a candidate

- **Pre-conditions:** Load reports Staff A conflicts with another planning or
  confirmed event, while Staff B is free.
- **Steps:** Request assignment.
- **Expected:** Staff B is assigned. Submitted/under-review work is already
  excluded by the events load boundary and cannot remove a candidate.
- **Actual:** As expected in the full unit run.
- **Status:** Pass
- **Evidence:** `test_app.py::test_overlapping_live_support_work_removes_a_candidate`

## TC-EVENTREQUESTS-035 — least busy selection and ties are deterministic

- **Pre-conditions:** First, free staff A/B/C have live assignment counts
  `2/0/1`. Then A and B are both free with count `0`, and B's UUID sorts first.
- **Steps:** Request assignment for each load response.
- **Expected:** The first request chooses B as least busy. The tied request
  chooses the lexicographically lowest UUID every time; no randomness is used.
- **Actual:** As expected in the full unit run.
- **Status:** Pass
- **Evidence:** `test_app.py::test_support_assignment_chooses_least_busy_then_lowest_id`

## TC-EVENTREQUESTS-036 — no available staff records required but unassigned

- **Pre-conditions:** In turn, the trusted pool is empty and every candidate
  reports an overlap.
- **Steps:** Request support assignment with details.
- **Expected:** The guarded event write still records required=true and the
  details with a null staff id. The response contains no fabricated profile
  and returns `200` with `assignment_state="unassigned"` and a clear statement
  that no Technical Support Staff member is currently available.
- **Actual:** As expected in the full unit run.
- **Status:** Pass
- **Evidence:** `test_app.py::test_no_available_support_staff_is_recorded_honestly`

## TC-EVENTREQUESTS-037 — an existing assignment is stable on repeated requests

- **Pre-conditions:** The event is already required and assigned to Staff A
  with a stored assignment timestamp.
- **Steps:** Repeat the assignment POST first with unchanged notes, then with
  changed notes.
- **Expected:** Both responses keep Staff A and the same assignment timestamp;
  candidate/load calls are skipped. Unchanged notes issue no write. Changed
  notes update only the support details without reallocating staff or changing
  the assignment timestamp.
- **Actual:** As expected in the full unit run.
- **Status:** Pass
- **Evidence:** `test_app.py::test_existing_support_assignment_is_returned_without_reassignment`

## TC-EVENTREQUESTS-038 — only a planning target can start S-43

- **Pre-conditions:** The assigned event is returned with each non-planning
  status in turn.
- **Steps:** Request support assignment for `draft`, `submitted`, `returned`,
  `rejected`, `confirmed`, `completed`, and `cancelled`.
- **Expected:** Every request returns `409`; no pool/load/write call occurs.
  A confirmed event can block a staff member's availability for another event,
  but cannot itself start a new S-43 assignment because the target rule is
  planning-only.
- **Actual:** As expected in the full unit run.
- **Status:** Pass
- **Evidence:** `test_app.py::test_support_assignment_rejects_every_non_planning_target`

## TC-EVENTREQUESTS-039 — downstream failures and races are safe

- **Pre-conditions:** Users lookup, load lookup, and event write each fail in
  turn; separately, the conditional write returns `409` after a status or
  Coordinator race.
- **Steps:** Request assignment in every case.
- **Expected:** Dependency failures return a service-specific safe `502` and
  never claim assignment. The events `409` is preserved and no stale success
  response is shown.
- **Actual:** As expected in the full unit run.
- **Status:** Pass
- **Evidence:** `test_app.py::test_support_assignment_dependency_failures_are_safe`, `test_app.py::test_support_assignment_preserves_a_stale_write_conflict`

---

## S-83 — Assign Event Requests from Unassigned Queue

Story: S-83 Assign Event Requests from Unassigned Queue.

Acceptance criteria confirmed by the developer on 2026-10-08:

1. A newly submitted request is stored as `submitted` without an assigned
   coordinator.
2. Only an authenticated Event Coordinator Lead can view the unassigned queue
   and assign a request.
3. The queue shows the event name, start/end date and time, expected
   attendance, and organiser.
4. The Lead may assign any user whose trusted role is `event_coordinator`;
   scheduling conflicts do not block assignment.
5. Assignment removes the request from the queue and makes it visible to the
   selected coordinator.
6. Concurrent or repeated assignment to a different coordinator is rejected.
7. Persistent in-app notifications are created for both the assigned
   coordinator and the event organiser. No email or external notification is
   required.
8. Draft, returned, and already-assigned requests are not in the queue.

The following cases were executed in the full unit run on 2026-10-08 on
branch `S-83/assign-event-requests-from-unassigned-queue`.

## TC-EVENTREQUESTS-040 — a new request is submitted without automatic assignment

- **Scenario:** S-83 replaces automatic coordinator selection with the Lead's
  unassigned queue.
- **Pre-conditions:** Shared organiser session; the events create endpoint
  returns a submitted event with `assigned_coordinator_id=null`.
- **Steps:** `POST /event-requests` with the shared submitted body.
- **Test data:** Shared organiser id and event window.
- **Expected:** `201`; the events create call contains the organiser id and no
  coordinator id. No coordinator-pool or coordinator-load request is made.
- **Actual:** The submitted event carried a null Coordinator and neither pool nor load was queried.
- **Status:** Pass
- **Evidence:** `test_app.py::test_new_submission_enters_the_unassigned_queue`

## TC-EVENTREQUESTS-041 — a draft's first submission is unassigned

- **Scenario:** Submitting a saved draft follows the same S-83 queue path as a
  brand-new request.
- **Pre-conditions:** The organiser owns a `draft`; the internal submit call
  accepts the complete payload.
- **Steps:** `POST /event-requests/{event_id}/submit`.
- **Test data:** Event `22222222-2222-4222-8222-222222222222`; shared submitted
  body.
- **Expected:** `200` with status `submitted` and
  `assigned_coordinator_id=null`; no coordinator availability call occurs.
- **Actual:** The draft was submitted with a null Coordinator without an availability call.
- **Status:** Pass
- **Evidence:** `test_app.py::test_first_draft_submission_is_unassigned`

## TC-EVENTREQUESTS-042 — a returned request keeps its existing coordinator

- **Scenario:** A returned request is not a new unassigned request when the
  organiser resubmits it.
- **Pre-conditions:** The organiser owns a `returned` event assigned to
  coordinator A.
- **Steps:** Resubmit the returned event with a changed date/time that overlaps
  coordinator A's other work.
- **Test data:** Coordinator A; shared event moved to `19:00`–`22:00`.
- **Expected:** `200`; coordinator A remains assigned. No coordinator pool,
  load, or conflict call occurs, and the event never enters the Lead queue.
- **Actual:** Coordinator A was preserved despite the changed overlapping window; no conflict call occurred.
- **Status:** Pass
- **Evidence:** `test_app.py::test_returned_resubmission_keeps_its_coordinator`

## TC-EVENTREQUESTS-043 — only a Lead can view the unassigned queue

- **Scenario:** Queue access is restricted to the new trusted Lead role.
- **Pre-conditions:** `/users/me` returns each recognized non-Lead role, an
  unknown role, and no session in turn.
- **Steps:** `GET /event-requests/unassigned` for every caller.
- **Test data:** `event_coordinator`, `event_organiser`, `venue_staff`,
  `technical_support`, `attendee`, `unknown`, and unauthenticated.
- **Expected:** Non-Lead authenticated callers receive `403`; no session
  receives `401`; the events service is never called.
- **Actual:** Every named non-Lead role returned `403`, no session returned `401`, and events was untouched.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_a_lead_can_view_the_unassigned_queue`

## TC-EVENTREQUESTS-044 — the queue contains only unassigned submissions and basic information

- **Scenario:** The Lead receives enough information to choose an owner, with
  organiser profiles resolved through the users service.
- **Pre-conditions:** A Lead session; events returns one unassigned submitted
  event; users resolves its organiser profile.
- **Steps:** `GET /event-requests/unassigned`.
- **Test data:** Event `Autumn Forum`, `2026-10-20 18:00`–`21:00`, attendance
  `120`; organiser `Ada Organiser <ada@example.com>`.
- **Expected:** `200`; the item contains id, name, start/end date and time,
  expected attendance, and organiser id/name/email. No draft, returned, or
  assigned event is requested or returned.
- **Actual:** The queue item contained event and resolved organiser details from the two owning services.
- **Status:** Pass
- **Evidence:** `test_app.py::test_lead_queue_returns_basic_event_and_organiser_information`

## TC-EVENTREQUESTS-045 — the Lead can list eligible coordinators

- **Scenario:** The assignment control offers only trusted Event Coordinator
  accounts.
- **Pre-conditions:** A Lead session; `/internal/users/coordinators` returns A and B.
- **Steps:** `GET /event-requests/coordinators`.
- **Test data:** Coordinator A and B profiles.
- **Expected:** `200` with the two id/name/email profiles; other roles receive
  `403`; no availability or workload lookup is made.
- **Actual:** Both trusted Coordinator profiles returned without a load or availability lookup.
- **Status:** Pass
- **Evidence:** `test_app.py::test_lead_lists_trusted_coordinators_without_availability_filtering`

## TC-EVENTREQUESTS-046 — a Lead assigns any trusted coordinator despite a conflict

- **Scenario:** Suitability is the Lead's judgment; scheduling overlap is not
  an assignment rejection rule.
- **Pre-conditions:** A Lead session; coordinator B appears in the trusted
  coordinator pool; the events assignment succeeds.
- **Steps:** `POST /event-requests/{event_id}/assignment` with B's id.
- **Test data:** Event id from TC-EVENTREQUESTS-044; coordinator B, who is
  described by the fixture as having an overlapping event.
- **Expected:** `200` with B assigned. The composite does not request
  coordinator load or conflict data.
- **Actual:** The trusted Coordinator was assigned and no coordinator-load call occurred.
- **Status:** Pass
- **Evidence:** `test_app.py::test_lead_can_assign_a_conflicting_trusted_coordinator`

## TC-EVENTREQUESTS-047 — a non-coordinator cannot be selected

- **Scenario:** A user id is not sufficient; eligibility comes from trusted
  Auth `app_metadata.role` exposed by the users service.
- **Pre-conditions:** A Lead session; the trusted coordinator pool does not
  contain the submitted id.
- **Steps:** Attempt assignment using an organiser id, then an unknown UUID.
- **Test data:** Organiser `11111111-1111-4111-8111-111111111111`; unknown
  `99999999-9999-4999-8999-999999999999`.
- **Expected:** Each request returns `422` identifying `coordinator_id`; no
  event write and no notification call occurs.
- **Actual:** An id outside the trusted Coordinator pool returned `422`; event and notification services were untouched.
- **Status:** Pass
- **Evidence:** `test_app.py::test_assignment_rejects_ids_outside_the_trusted_coordinator_pool`

## TC-EVENTREQUESTS-048 — only a Lead can assign a request

- **Scenario:** Assignment cannot be performed by a coordinator, organiser, or
  another internal role.
- **Pre-conditions:** The non-Lead caller roles from TC-EVENTREQUESTS-043.
- **Steps:** `POST /event-requests/{event_id}/assignment` with coordinator A.
- **Test data:** Shared event and coordinator A.
- **Expected:** `403` for authenticated non-Leads and `401` without a session;
  users eligibility, event assignment, and notifications are untouched.
- **Actual:** All named non-Lead roles returned `403` and no session returned `401`, before any downstream write.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_a_lead_can_assign_an_event_request`

## TC-EVENTREQUESTS-049 — missing and stale assignment targets preserve their result

- **Scenario:** The composite does not hide an absent event or a concurrent
  assignment behind a generic dependency error.
- **Pre-conditions:** The events service returns `404`, then `409` because a
  different Lead assigned the event first.
- **Steps:** Attempt the same valid assignment in each case.
- **Test data:** Shared event and coordinator A.
- **Expected:** The client receives the same `404` or `409`; notification
  creation is not attempted.
- **Actual:** Atomic `404` and `409` responses were preserved and notifications were not attempted.
- **Status:** Pass
- **Evidence:** `test_app.py::test_assignment_preserves_missing_and_concurrent_results`

## TC-EVENTREQUESTS-050 — assignment creates both persistent in-app notifications

- **Scenario:** Both people named by the developer are notified after a valid
  assignment.
- **Pre-conditions:** A Lead session; valid coordinator A; the events response
  includes organiser id and event name; notifications accepts the batch.
- **Steps:** Assign coordinator A.
- **Test data:** Event `Autumn Forum`; organiser and coordinator A ids.
- **Expected:** One notification batch contains exactly two recipients—the
  organiser and coordinator A—with event id, event name, assignment kind,
  in-app message, and stable deduplication keys. Repeating the same assignment
  with the same keys must leave exactly one assignment notification for the
  coordinator and one for the organiser, never duplicates. No email/external
  call exists.
- **Actual:** One internal batch contained exactly the organiser and Coordinator with stable per-recipient keys and no external channel.
- **Status:** Pass
- **Evidence:** `test_app.py::test_assignment_notifies_coordinator_and_organiser_in_app`

## TC-EVENTREQUESTS-051 — retry repairs notifications without changing assignment

- **Scenario:** A transient notification failure is recoverable without a
  second assignment or duplicate notification.
- **Pre-conditions:** The event assignment to coordinator A has succeeded. The
  notification call then fails in each uncertain state: (a) neither
  notification persisted, (b) only the coordinator or only the organiser
  notification persisted, and (c) both persisted but the success response was
  lost. On retry, events reports A as the existing idempotent assignment and
  notifications accepts the same stable deduplication keys.
- **Steps:** For each uncertain state, retry the identical assignment request
  and inspect the resulting logical notifications.
- **Test data:** Shared event and coordinator A.
- **Expected:** The failed first call does not claim notifications were
  delivered. Every retry returns `200`, preserves coordinator A without a
  second assignment write, creates whichever recipient notification is
  missing, and finishes with exactly one coordinator notification and one
  organiser notification—never zero, one, three, or four rows.
- **Actual:** The first notification failure returned `502`; the identical retry accepted the existing assignment and resent the same two stable keys. Missing-row outcomes are covered by TC-NOTIFICATIONS-101.
- **Status:** Pass
- **Evidence:** `test_app.py::test_assignment_retry_repairs_notifications_idempotently`

## TC-EVENTREQUESTS-052 — dependency failures are named and never fabricated as success

- **Scenario:** Lead authentication, coordinator listing, event queue,
  organiser lookup, event assignment, and notification calls fail safely.
- **Pre-conditions:** Each downstream call raises or returns a non-contract
  status in turn.
- **Steps:** Exercise list, coordinator-list, and assignment operations.
- **Test data:** Shared Lead, event, organiser, and coordinator ids.
- **Expected:** Each case returns a service-specific `502`; later calls in the
  workflow are skipped and no fabricated queue, assignment, or notification
  response is returned.
- **Actual:** Event queue, organiser lookup, event assignment, and notification connection failures returned the named safe `502` without fabricated success.
- **Status:** Pass
- **Evidence:** `test_app.py::test_s83_dependency_failures_are_safe`

---

## S-84 — Reassign Event Coordinator

Story: S-84 Reassign Event Coordinator. Acceptance criteria and test cases
confirmed by the developer on 2026-10-08. Executed locally on 2026-10-09.

## TC-EVENTREQUESTS-053 — only a Lead can list or reassign active assignments

- **Expected:** A Lead can call the assigned-active list and reassignment
  action. Authenticated non-Leads receive `403`; no session receives `401`;
  downstream services are untouched on denial.
- **Actual:** Non-Leads and missing sessions were rejected before any events
  or notification call.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_only_a_lead_can_list_or_reassign_active_assignments`

## TC-EVENTREQUESTS-054 — assigned events include trusted organiser and owner profiles

- **Expected:** The Lead list returns basic event information, assignment
  version, organiser profile, and current Coordinator profile. Missing profile
  data falls back safely to the opaque id.
- **Actual:** The Lead list joined organiser and current-owner profiles while
  preserving the event's assignment version.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_lead_lists_active_assignments_with_profiles`

## TC-EVENTREQUESTS-055 — any trusted different Coordinator may be selected

- **Expected:** A trusted Coordinator is accepted despite an overlapping
  schedule; a non-Coordinator or selecting the current owner returns `422`
  before the event write.
- **Actual:** A trusted different Coordinator was accepted without a load
  query; same-owner and untrusted targets returned `422`.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_lead_reassigns_without_schedule_filtering`, `test_s84.py::test_reassignment_rejects_invalid_or_same_target`

## TC-EVENTREQUESTS-056 — reassignment notifies former owner, new owner, and organiser

- **Expected:** One internal notification batch contains exactly those three
  recipients with `event_reassignment` messages and keys scoped by event,
  returned assignment version, and recipient. No external channel is called.
- **Actual:** One batch contained exactly the former owner, new owner, and
  organiser with version-scoped reassignment keys.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_reassignment_creates_three_persistent_notifications`

## TC-EVENTREQUESTS-057 — retry repairs any missing reassignment notification

- **Expected:** If the event transition commits but notification persistence
  fails, the identical request returns `502`; retry receives the same version
  and previous owner, preserves the new owner, and sends the same three keys.
  Notification upsert creates only missing rows and never duplicates.
- **Actual:** The first notification failure returned `502`; retry used the
  same three keys and preserved the committed event transition.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_reassignment_retry_repairs_notifications_idempotently`

## TC-EVENTREQUESTS-058 — missing, ineligible, stale, and dependency failures remain explicit

- **Expected:** Atomic `404`/`409` results are preserved. Users, events, and
  notification outages return named `502` responses; later calls are skipped.
- **Actual:** Atomic `404`/`409` responses were preserved and a simulated
  events outage returned the named `502` without fabricated success.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_reassignment_preserves_atomic_conflicts`, `test_s84.py::test_reassignment_dependency_failures_are_safe`

---

## S-85 — View Coordinator Assignments and Active Events

Story: S-85 View Coordinator Assignments and Active Events. Acceptance
criteria and test cases confirmed by the developer on 2026-10-09. Executed
locally on 2026-10-09.

## TC-EVENTREQUESTS-059 — only an authenticated Lead can read oversight

- **Scenario:** The coordinator overview is a Lead-only read operation.
- **Pre-conditions:** Users returns a Lead, another trusted role, or no valid
  session in turn.
- **Steps:** `GET /event-requests/coordinator-overview` for every caller.
- **Test data:** `event_coordinator_lead`, `event_coordinator`,
  `event_organiser`, and anonymous.
- **Expected:** The Lead receives `200`; authenticated non-Leads receive
  `403`; anonymous receives `401`. Denied requests make no coordinator-pool,
  event, profile, notification, or persistence call.
- **Actual:** Anonymous, Organiser, and Coordinator requests were rejected
  before Events, profile, notification, or write calls; the Lead cases below
  returned the overview.
- **Status:** Pass
- **Evidence:** `test_s85.py::test_only_a_lead_can_read_coordinator_overview`

## TC-EVENTREQUESTS-060 — every Coordinator is grouped with an assignment count

- **Scenario:** Oversight includes idle Coordinators as well as assigned ones.
- **Pre-conditions:** The trusted coordinator pool contains A, B, and C;
  active events contain two for A, one for B, and none for C.
- **Steps:** Read the overview and inspect group ordering, membership, and
  counts.
- **Test data:** Three Coordinator profiles and three active events.
- **Expected:** Exactly one group per trusted Coordinator is returned; counts
  are A=2, B=1, C=0; C has an empty `events` list. Events are grouped only by
  their current `assigned_coordinator_id`.
- **Actual:** The response sorted A/B/C by name, grouped event counts 2/1/0,
  and retained C with an empty event list.
- **Status:** Pass
- **Evidence:** `test_s85.py::test_overview_groups_events_and_keeps_zero_assignment_coordinators`

## TC-EVENTREQUESTS-061 — event summaries contain trusted profiles and required fields

- **Scenario:** Each grouped event gives the Lead the confirmed oversight
  information without exposing unrelated user data.
- **Pre-conditions:** Events returns active rows and Users returns organiser
  profiles.
- **Steps:** Read the overview and inspect one event summary.
- **Test data:** `Autumn Forum`, `under_review`, organiser Ada, coordinator
  Alex, `2026-11-18 09:00`–`12:00`.
- **Expected:** The summary includes event id/name/status, organiser profile,
  start/end date and time, current Coordinator profile, and S-84 assignment
  version. Missing organiser profiles use the existing safe id fallback.
- **Actual:** The enriched `under_review` summary contained every required
  identity, schedule, status, and version field. A separate case accepted all
  five active statuses in one group.
- **Status:** Pass
- **Evidence:** `test_s85.py::test_overview_enriches_event_summaries_with_profiles`

## TC-EVENTREQUESTS-062 — empty oversight remains structurally complete

- **Scenario:** A Lead can distinguish no active assignments from a failed
  request.
- **Pre-conditions:** The Coordinator pool exists but Events returns no active
  assigned rows; separately, both are empty.
- **Steps:** Read the overview for each state.
- **Expected:** Existing Coordinators are returned with count 0 and empty
  event lists; a completely empty pool returns
  `{"coordinators":[],"invalid_assignments":[]}` with `200`, never a
  fabricated error or missing shape.
- **Actual:** An existing idle Coordinator returned count 0 and `events: []`;
  an empty pool returned `{"coordinators": [], "invalid_assignments": []}`
  without a profile call.
- **Status:** Pass
- **Evidence:** `test_s85.py::test_overview_handles_empty_events_and_empty_pool`

## TC-EVENTREQUESTS-063 — upstream failures are controlled and read-only

- **Scenario:** Users or Events outages do not produce partial or misleading
  oversight data.
- **Pre-conditions:** Authentication succeeds; coordinator-pool, event-list,
  or organiser-profile calls raise or return a non-contract status in turn.
- **Steps:** Read the overview for every failure.
- **Expected:** A named `502` is returned, later calls are skipped where
  possible, and notifications plus all write methods remain untouched.
- **Actual:** Pool, Events, and profile failures each returned the named
  controlled `502`; notification and Events write methods remained untouched.
- **Status:** Pass
- **Evidence:** `test_s85.py::test_overview_dependency_failures_are_controlled_and_read_only`

## S-85 oversight integrity regression — confirmed 2026-10-18

These cases supplement the already-confirmed S-83 cases 043–052, S-84 cases
053–058, and S-85 cases 059–063. They do not replace those regressions.

## TC-EVENTREQUESTS-064 — only trusted pool members receive oversight groups

- **Scenario:** Active events assigned to an ineligible or nonexistent owner are reported separately, never presented as Coordinator groups.
- **Pre-conditions:** The Users coordinator pool contains A only. Events returns one active event for A, one for a deleted Auth user D, and one for a user N whose trusted role is `safety_officer`; profile lookup may return a profile for N but none for D.
- **Steps:** Read `GET /event-requests/coordinator-overview`; inspect groups, counts, and integrity diagnostics; repeat for each of the five existing active statuses.
- **Test data:** A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`; D `dddddddd-dddd-4ddd-8ddd-dddddddddddd`; N `99999999-9999-4999-8999-999999999999`; statuses `submitted`, `under_review`, `returned`, `planning`, `confirmed`.
- **Expected:** Exactly A is a Coordinator group, with only A's events and its unchanged active-assignment count. D and N receive no group even if a profile exists; their event records remain untouched and appear only in a separate `invalid_assignments` diagnostic containing event ID/name/status and assigned owner ID. No assignment, notification, or other write is attempted.
- **Actual:** For each of the five active statuses, only A was grouped and counted. The deleted and wrong-role owners appeared as two separate integrity records; no write method was called.
- **Status:** Pass
- **Evidence:** `test_s85.py::test_overview_reports_invalid_owners_without_creating_groups`; local unit run, 2026-10-18.

## TC-EVENTREQUESTS-065 — profile-less trusted Coordinators remain visible and countable

- **Scenario:** S-85 oversight groups every trusted Coordinator, regardless of profile or current workload.
- **Pre-conditions:** The trusted pool contains A with a profile and one active event, B without a profile and two active events, and C without a profile and no active events. The Users pool supplies safe Auth identity display fields for B and C.
- **Steps:** Read the overview; inspect each group's identity, event ownership, count, and ordering; reassign A's event to C through the existing S-84 path and read the overview again.
- **Test data:** A `Alex <alex@example.com>`; B Auth email `blair@example.com`; C Auth email `casey@example.com`; event counts 1/2/0 before reassignment.
- **Expected:** Exactly three groups appear, using the profile display for A and Auth email display for B/C, with counts 1/2/0. B's two events appear only under B; C remains visible while idle. After S-84 reassignment, the next overview reports 0/2/1, while the existing target-role validation, queue, and notification behavior remain unchanged.
- **Actual:** All three trusted Coordinators appeared with counts 1/2/0 and profile-less Auth email display. The S-84 transfer to idle C succeeded; a fresh overview returned counts 0/2/1.
- **Status:** Pass
- **Evidence:** `test_s85.py::test_overview_groups_profileless_trusted_coordinators_and_keeps_idle`; local unit run, 2026-10-18.

## S-61 — review and approve cancellation request

Story: S-61 Review and Approve Cancellation Request.
Confirmed by the developer on 2026-10-11.
A new route, `POST /event-requests/{id}/cancellation-decision`, reached by the
browser through Kong. It forwards the decision to the events service and, on
approval, removes the event's venue bookings. This composite gains a
bookings client (`BOOKINGS_SERVICE_URL`). The criteria mapping and agreed
decisions are in the S-61 section of `tests/unit/atomic/events/TEST_CASES.md`.

### TC-EVENTREQUESTS-069 — approving cancels the event, then releases its bookings

- **Scenario:** The two services are called in order and the result says what
  was released (S-61 AC1, AC2).
- **Pre-conditions:** The events fake answers the decision with `200` and E
  `cancelled`. The bookings fake answers the delete with `{"deleted": 2}`.
- **Steps:** `POST /event-requests/E/cancellation-decision` `{"decision": "approved"}`
  with the Coordinator's cookie.
- **Expected:** `200` with the event as the events service returned it, plus
  `"released_bookings": 2`. The events call comes first, then
  `DELETE /internal/events/E/bookings`. Both carry the caller's cookie.
- **Actual:** `200` with the cancelled event and `released_bookings` 2; events then bookings, both with the cookie.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s61.py::test_approving_cancels_the_event_then_releases_its_bookings`

### TC-EVENTREQUESTS-070 — declining touches only the event

- **Scenario:** A decline leaves every booking in place.
- **Pre-conditions:** The events fake answers with `200` and E still `planning`.
- **Steps:** `POST /event-requests/E/cancellation-decision`
  `{"decision": "declined", "reason": "Move the date instead"}`.
- **Expected:** `200` with the event, and no `released_bookings`. The body
  is forwarded unchanged. The bookings service is never called.
- **Actual:** `200`, still `planning`, no `released_bookings`; body forwarded; bookings not called.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s61.py::test_declining_touches_only_the_event`

### TC-EVENTREQUESTS-066 — a refused decision releases nothing

- **Scenario:** If the events service says no, bookings are untouched.
- **Pre-conditions:** The events fake answers with each refusal.
- **Steps:** Approve E once per refusal.
- **Test data:** `401`, `403`, `404` "Event not found", `409` "This
  cancellation request has already been decided.", `422` with field errors.
- **Expected:** The same status and body reach the caller. The bookings
  service is never called.
- **Actual:** Each of `401`, `403`, `404`, `409`, `422` reached the caller unchanged; bookings not called.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s61.py::test_a_refused_decision_releases_nothing`

### TC-EVENTREQUESTS-067 — a failed release says so, and approving again finishes it

- **Scenario:** The event is cancelled but its bookings weren't removed (S-61
  decision 7).
- **Pre-conditions:** The events fake answers the approval with `200` E
  `cancelled`.
- **Steps:**
  1. Approve with the bookings fake answering `500`.
  2. Approve with the bookings fake timing out.
  3. Approve again with the bookings fake answering `{"deleted": 2}`.
  4. Approve with the events service unreachable.
- **Expected:**
  1. and 2. `502` "The event is cancelled, but its venue bookings were not
     released. Approve again to release them."
  3. `200` with `"released_bookings": 2`.
  4. `502` "The events service is unavailable. Nothing was changed.", with
     no bookings call.
- **Actual:** Bookings `500` and timeout gave `502` with the not-released message; approving again gave `200` with 2 released; events unreachable or `500` gave `502` "The events service is unavailable. Nothing was changed." with no bookings call.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s61.py::test_a_failed_release_says_so`; `tests/unit/composite/event_requests/test_s61.py::test_approving_again_finishes_the_release`; `tests/unit/composite/event_requests/test_s61.py::test_events_down_changes_nothing`

### TC-EVENTREQUESTS-068 — a refused edit keeps the events service's reason

- **Scenario:** Saving changes to a closed event says why, instead of
  claiming the service is down (added 2026-10-13 at the developer's request;
  affected rejected events before S-61 and cancelled ones since).
- **Pre-conditions:** Organiser session; the events fake answers the
  forwarded `PATCH` with `409` and each detail.
- **Steps:** `PATCH /event-requests/E` `{"venue": "Room 9"}`.
- **Test data:** "This event has been cancelled and is closed."; "This
  request has been rejected and is closed".
- **Expected:** `409` with the same detail (before: `502` "Events service
  unavailable"). `200`, `404` and `422` still pass through as before, and any
  other answer is still `502`.
- **Actual:** Both details came back as `409` unchanged; a `500` from the events service is still `502` "Events service unavailable".
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s61.py::test_a_refused_edit_keeps_the_events_services_reason`; `tests/unit/composite/event_requests/test_s61.py::test_an_unexpected_answer_on_edit_is_still_a_502`; `pytest tests/unit`: 967 passed, 17 skipped, 2026-10-13.
