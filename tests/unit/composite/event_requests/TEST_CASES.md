# Test cases — event_requests service (unit)

Covers `test_app.py`, `test_s83.py`, `test_s84.py`, and `test_s93.py`: the composite workflows spanning the
events, users, and notifications atomic services. All three outbound HTTP
clients are faked; no network, database, or Docker.

| | |
| --- | --- |
| Suite | `pytest tests/unit/composite/event_requests` |
| Last run | 2026-10-25, uncommitted `S-93/reassign-active-events-before-deactivation` working tree based on `605e1e8` |
| Environment | Python 3.14.8, pytest 9.1.1; mocked HTTP services; no network, database or Docker. |
| Result | 128 passed, 17 skipped in this folder; 1,373 passed, 17 skipped across Python unit. |

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
  nine active statuses in one group.
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
- **Steps:** Read `GET /event-requests/coordinator-overview`; inspect groups, counts, and integrity diagnostics; repeat for each of the nine open assignment statuses.
- **Test data:** A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`; D `dddddddd-dddd-4ddd-8ddd-dddddddddddd`; N `99999999-9999-4999-8999-999999999999`; statuses `submitted`, `under_review`, `returned`, `planning`, `pending_safety_check`, `confirmed`, `preparation`, `safety_rejected`, `safety_changes_requested`.
- **Expected:** Exactly A is a Coordinator group, with only A's events and its unchanged active-assignment count. D and N receive no group even if a profile exists; their event records remain untouched and appear only in a separate `invalid_assignments` diagnostic containing event ID/name/status, assigned owner ID, and `reason: identity_missing`. No assignment, notification, or other write is attempted.
- **Actual:** For each of the nine active statuses, only A was grouped and counted. The deleted and wrong-role owners appeared as two separate `identity_missing` integrity records; no write method was called.
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

# S-88 confirmed specification — request reassignment from Lead

Confirmed by the developer on 2026-10-25. Latest execution: S-88 branch, uncommitted; Python unit suite and fresh `.env.test` integration/browser stack.
Shared data: event `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`, assigned Coordinator
`bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`, replacement Coordinator
`cccccccc-cccc-4ccc-8ccc-cccccccccccc`, responsible Lead
`dddddddd-dddd-4ddd-8ddd-dddddddddddd`, unrelated Lead
`eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee`, assignment version `2`, and reason
`Cannot cover the November event`. HTTP clients are faked in every unit case.

## TC-EVENTREQUESTS-087 — assigned Coordinator submits a request

- **Scenario:** The current owner asks the responsible Lead for reassignment.
- **Pre-conditions:** `/users/me` identifies the assigned Coordinator; the event is active, version 2, and was assigned by the responsible Lead.
- **Steps:** POST a reassignment request for the event with the reason, then read the response.
- **Test data:** Shared event and `{"reason":"Cannot cover the November event"}`.
- **Expected:** `201`, with event ID, requester ID, trimmed reason, `pending`, and server timestamps; the composite calls the Events service to persist it and never calls the S-84 transfer endpoint.
- **Actual:** A signed-in assigned Coordinator received 201 with a trimmed reason; the Events request endpoint received the write and S-84 was untouched.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s88.py::test_assigned_coordinator_submits_without_transfer`; 2026-10-25.

## TC-EVENTREQUESTS-088 — invalid reason

- **Scenario:** A blank request cannot be submitted.
- **Pre-conditions:** Assigned Coordinator session.
- **Steps:** POST requests with empty and whitespace-only reasons.
- **Test data:** `{"reason":""}` and `{"reason":"   "}`.
- **Expected:** Each returns `422`; no request or owner write is attempted.
- **Actual:** Blank and whitespace reasons returned 422 before any downstream write.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s88.py::test_blank_reason_rejected_before_any_write`; 2026-10-25.

## TC-EVENTREQUESTS-089 — submission access

- **Scenario:** Only the assigned Coordinator can ask for reassignment.
- **Pre-conditions:** The event belongs to the shared Coordinator.
- **Steps:** Repeat the POST as an anonymous visitor, another Coordinator, an Organiser, and a Lead.
- **Test data:** Shared event and reason; four distinct identities.
- **Expected:** Anonymous receives `401`, unrelated roles `403`, and another Coordinator `404` or `403` without event details; no request is persisted.
- **Actual:** Anonymous, wrong-role and wrong-owner callers were rejected without a request write or event details.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s88.py::test_only_current_coordinator_can_submit`; 2026-10-25.

## TC-EVENTREQUESTS-090 — duplicate outstanding request

- **Scenario:** Repeating a request does not create another pending row.
- **Pre-conditions:** The shared Coordinator already has a pending request for the event.
- **Steps:** POST the same event and reason again.
- **Test data:** Shared event and reason.
- **Expected:** `409` with an actionable duplicate message; the original request remains pending and there is still one pending row.
- **Actual:** The second submission returned 409 and the existing pending request remained the only one.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s88.py::test_concurrent_submissions_leave_one_pending_request`; 2026-10-25.

## TC-EVENTREQUESTS-091 — requester reads history after ownership changes

- **Scenario:** The original requester can see the actioned outcome after transfer.
- **Pre-conditions:** A stored request names the shared Coordinator; S-84 has assigned the event to the replacement.
- **Steps:** GET the requester's reassignment requests as the original Coordinator, then as another Coordinator.
- **Test data:** Shared IDs; status `actioned`.
- **Expected:** Original requester receives the event, reason and `actioned` status; the other Coordinator receives no request data.
- **Actual:** The original requester received their actioned history after transfer; the other Coordinator received no rows.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s88.py::test_request_survives_refresh_is_scoped_and_actions_after_s84`; 2026-10-25.

## TC-EVENTREQUESTS-092 — Lead visibility follows supervisory scope

- **Scenario:** Only the Lead who assigned the event can review its request.
- **Pre-conditions:** The event records the shared responsible Lead; a pending request exists.
- **Steps:** GET the Lead request list as the responsible Lead, then the unrelated Lead and a Coordinator.
- **Test data:** Shared IDs and reason.
- **Expected:** Responsible Lead sees event, requester, reason and status; unrelated Lead sees an empty list and cannot fetch the request directly; Coordinator gets `403` on Lead routes.
- **Actual:** The assigning Lead saw the request; the unrelated Lead received an empty list and could not access the event scope; the Coordinator was forbidden.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s88.py::test_request_survives_refresh_is_scoped_and_actions_after_s84`; 2026-10-25.

## TC-EVENTREQUESTS-093 — S-84 transfer actions the request

- **Scenario:** Existing Lead reassignment remains the sole owner-changing action.
- **Pre-conditions:** Responsible Lead, pending request for current owner at version 2, valid replacement.
- **Steps:** POST the existing S-84 reassignment payload; read the request status.
- **Test data:** Replacement ID, expected owner ID, expected version `2`.
- **Expected:** S-84 returns the replacement as owner; pending request becomes `actioned` with server action timestamp; existing reassignment notifications still occur.
- **Actual:** The existing S-84 path transferred the event and sent its reassignment notifications; the matching request became actioned.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s88.py::test_request_survives_refresh_is_scoped_and_actions_after_s84`; 2026-10-25.

## TC-EVENTREQUESTS-094 — failed or stale transfer preserves status

- **Scenario:** A failed S-84 call cannot claim that the request was actioned.
- **Pre-conditions:** Pending request; Events service returns `409` for a stale version, then `502` in a separate run.
- **Steps:** POST the existing S-84 reassignment with each upstream result and reread status.
- **Test data:** Expected version `2`; actual version `3` or upstream failure.
- **Expected:** Client receives `409` or safe `502`; request is not marked `actioned`; no success notice is emitted.
- **Actual:** The stale and upstream-failure paths returned 409 and 502 respectively; neither reported a successful transfer or actioned the request.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s88.py::test_request_survives_refresh_is_scoped_and_actions_after_s84`; 2026-10-25.

## TC-EVENTREQUESTS-095 — unrelated Lead cannot transfer scoped event

- **Scenario:** Request review cannot be bypassed through the existing S-84 route.
- **Pre-conditions:** Event records the responsible Lead, who differs from caller.
- **Steps:** POST S-84 reassignment as the unrelated Lead.
- **Test data:** Shared IDs and valid replacement.
- **Expected:** `403` or scoped `404`; owner, request status and notifications remain unchanged.
- **Actual:** The unrelated Lead was refused before S-84; no owner or request write and no notification followed.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s88.py::test_s84_requires_recorded_scope`; 2026-10-25.

## TC-EVENTREQUESTS-096 — downstream failures fail closed

- **Scenario:** Auth, event, profile or request storage outages reveal no cross-scope data.
- **Pre-conditions:** Each downstream client fails separately.
- **Steps:** Read or submit a request with each failure injected.
- **Test data:** Shared event and identities.
- **Expected:** Safe `502` response; no request is reported as persisted or actioned and unrelated Lead data is never returned.
- **Actual:** Injected downstream failures produced safe 502 responses without leaking scoped rows or reporting success.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s88.py::test_users_or_profile_failure_returns_no_lead_request_data`; 2026-10-25.

## TC-EVENTREQUESTS-097 — S-83 and S-85 remain usable with scoped ownership

- **Scenario:** New request handling preserves the shared unassigned queue and Lead oversight.
- **Pre-conditions:** Two Leads; one unassigned event, one active event assigned by each Lead.
- **Steps:** List the unassigned queue as both Leads; assign it as Lead A using S-83; list each Lead's overview.
- **Test data:** Shared Lead IDs and three distinct event IDs.
- **Expected:** Both Leads initially see the unassigned event; its S-83 assignment records Lead A; Lead A sees the newly assigned event and their prior event; Lead B sees only their own active event; no request handling changes any existing owner.
- **Actual:** Both Leads saw the unassigned queue; S-83 recorded the assigning Lead, and S-85 returned only that Lead’s active assignments.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s83.py; tests/unit/composite/event_requests/test_s85.py; tests/e2e/test_coordinator_overview.py`; 2026-10-25.

## S-93 confirmed specification — leaving Coordinator inventory and reassignment

Drafted 2026-10-25 on `S-93/reassign-active-events-before-deactivation` at
`605e1e8`. Confirmed by developer on 2026-10-25. Any authenticated
Lead may select a trusted Coordinator and read a limited summary of all that
Coordinator's active events, including other Leads' events. This explicit
S-93 read does not broaden ordinary S-85/S-88 reads. S-84 remains writable
only by each event's recorded responsible Lead. Other-Leads' rows and legacy
rows without Lead provenance are shown as non-actionable with a handoff/scope
repair notice; provenance is never inferred from Coordinator membership.
The Users service supplies live, trusted Auth availability; `false` is
inactive, absent is active, and malformed/missing identity is ineligible.
In TC-EVENTREQUESTS-100/-101, “bypassing the UI” means calling the backend
composite API directly through Kong. The atomic Events assignment routes are
also published on their own development port and cannot query Users under
this repo's service boundaries. The confirmed design requires those mutations
to reject calls without a trusted service credential, which the composite
supplies only after validating the target's live Users availability. A Lead
cookie alone must never authorize a direct atomic assignment write.

## TC-EVENTREQUESTS-098 — selected Coordinator shows all active work or an empty state

- **Scenario:** The Lead can select one Coordinator and see a complete active-event count across responsible Leads.
- **Pre-conditions:** Fake Users returns Coordinators A and B; Events returns A's two active summaries under Leads L1/L2 and no active summary for B.
- **Steps:** 1. As L1 select A in the S-93 inventory. 2. Select B. 3. Select an unknown ID.
- **Test data:** A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`, B `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`, unknown `ffffffff-ffff-4fff-8fff-ffffffffffff`; events `Autumn Forum` and `Winter Fair`.
- **Expected:** A has count 2 with both names, lifecycle states, date/times, current Coordinator and responsible Lead indicators. B has count 0 and an empty result. Unknown ID returns `404` without event data; no selection changes an event.
- **Actual:** Selected inventory returned all three scope categories with a count; an empty Coordinator returned count zero, and an unknown Coordinator returned 404 without an Events call.
- **Status:** Pass
- **Evidence:** test_s93.py::test_selected_inventory_marks_cross_lead_and_legacy_read_only; test_s93.py::test_selected_coordinator_with_no_active_events_has_zero_count; test_s93.py::test_selected_inventory_rejects_unknown_coordinator_and_non_lead

## TC-EVENTREQUESTS-099 — inactive owner is flagged until ownership changes

- **Scenario:** A selected inactive Coordinator's active events carry warnings independent of the current assignment candidate pool.
- **Pre-conditions:** Users reports A with `coordinator_active=false`; Events returns two active events owned by A, one in L1 scope and one in L2 scope; B is active with no events.
- **Steps:** 1. Read the selected-Coordinator inventory for A and B. 2. Read L1's ordinary oversight.
- **Test data:** A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`, B `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`; `Autumn Forum` in `planning`, `Winter Fair` in `preparation`.
- **Expected:** A is marked inactive, both rows are flagged as still assigned to an inactive Coordinator, and the count is 2; B has no warning. L1's ordinary oversight flags only its own event and does not reveal L2's ordinary S-85 detail.
- **Actual:** Inactive ownership remained flagged in the selected inventory, and ordinary oversight kept its recorded-Lead filter.
- **Status:** Pass
- **Evidence:** test_s93.py::test_selected_inventory_marks_cross_lead_and_legacy_read_only; tests/e2e/test_reassign_before_deactivation.py::test_leads_clear_only_their_inactive_coordinator_assignments[chromium]

## TC-EVENTREQUESTS-100 — S-83 cannot assign an inactive target

- **Scenario:** Assignment candidates and the backend S-83 write both reject inactive Coordinators.
- **Pre-conditions:** Users' trusted pool has active B and inactive A; an unassigned submitted event is in the shared queue.
- **Steps:** 1. List S-83 candidates. 2. POST S-83 assignment to A directly, bypassing the UI. 3. POST to B.
- **Test data:** Event `11111111-1111-4111-8111-111111111111`; A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`, B `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`.
- **Expected:** Only B is selectable; direct A assignment returns `422` and does not call the Events write or notify anyone. B remains a valid target through the existing S-83 path and records the assigning Lead.
- **Actual:** The candidate pool omitted inactive users and a direct composite S-83 attempt returned 422 before Events was called. A caller-supplied service token was ignored; the composite sent only its own configured token after validation.
- **Status:** Pass
- **Evidence:** test_s93.py::test_candidate_pool_filters_inactive_and_malformed; test_s93.py::test_s83_and_s84_reject_inactive_target_before_events_write; test_s93.py::test_browser_supplied_service_token_is_not_forwarded_to_atomic_write; tests/integration/composite/event_requests/test_s93.py::test_inactive_target_is_rejected_but_existing_work_can_be_transferred

## TC-EVENTREQUESTS-101 — S-84 cannot reassign to an inactive target

- **Scenario:** Reassignment candidates and the backend S-84 write both reject an inactive replacement.
- **Pre-conditions:** Event is owned by A under L1 at version 2; Users marks B inactive and C active.
- **Steps:** 1. List S-84 candidates. 2. POST S-84 to B directly with correct owner/version. 3. POST to C.
- **Test data:** Event `11111111-1111-4111-8111-111111111111`; A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`, B `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`, C `cccccccc-cccc-4ccc-8ccc-cccccccccccc`.
- **Expected:** B is absent from candidates; direct B attempt returns `422` before the Events write and leaves owner, version, warning and notifications unchanged. C proceeds through existing S-84 validation and CAS.
- **Actual:** A direct composite S-84 attempt to an inactive replacement returned 422 before Events was called; an active replacement transferred successfully in the integration journey.
- **Status:** Pass
- **Evidence:** test_s93.py::test_s83_and_s84_reject_inactive_target_before_events_write; tests/integration/composite/event_requests/test_s93.py::test_inactive_target_is_rejected_but_existing_work_can_be_transferred

## TC-EVENTREQUESTS-102 — cross-Lead inventory never grants cross-Lead action

- **Scenario:** The all-events S-93 read remains separate from S-85 oversight and S-84 authorization.
- **Pre-conditions:** A owns Event 1 assigned by L1 and Event 2 assigned by L2; both Leads have trusted roles.
- **Steps:** 1. As L1 select A in S-93 inventory. 2. Read S-85 and S-88 views. 3. Try S-84 on Event 2. 4. Repeat the S-93 read as A and anonymously.
- **Test data:** L1 `dddddddd-dddd-4ddd-8ddd-dddddddddddd`, L2 `eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee`; events `Autumn Forum` and `Winter Fair`.
- **Expected:** L1 sees both limited S-93 summaries and an `other Lead` indicator on Event 2, but S-85/S-88 stay L1 scoped. Event 2 action returns scoped `404` without write or notification. Coordinator gets `403`, anonymous gets `401`, and neither receives event summaries.
- **Actual:** Cross-Lead rows were marked non-actionable; non-Leads were denied and existing S-84 scope checks remained in force.
- **Status:** Pass
- **Evidence:** test_s93.py::test_selected_inventory_marks_cross_lead_and_legacy_read_only; test_s93.py::test_selected_inventory_rejects_unknown_coordinator_and_non_lead; tests/unit/atomic/events/test_s84.py::test_internal_reassignment_rejects_unrelated_lead_and_legacy_event

## TC-EVENTREQUESTS-103 — legacy and missing identities fail closed

- **Scenario:** The inventory remains useful without fabricating a Lead or treating a missing user as an active replacement.
- **Pre-conditions:** A is inactive; Events returns a legacy active event owned by A with null `assigning_lead_id`, and L1 oversight returns another active event whose Coordinator Auth account was deleted.
- **Steps:** 1. Read A's S-93 inventory. 2. Read L1 oversight. 3. Attempt S-84 on the legacy event and attempt S-83/S-84 targeting the deleted account.
- **Test data:** A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`; deleted owner `ffffffff-ffff-4fff-8fff-ffffffffffff`; events `Legacy Forum` and `Orphaned Fair`.
- **Expected:** Legacy event appears only as a limited, flagged, non-actionable summary with `responsible Lead unknown`; no Lead is auto-assigned. L1 sees its orphaned event with an `identity missing` warning and no false active Coordinator profile. Legacy action stays blocked; deleted identity is never a candidate or accepted target.
- **Actual:** Legacy provenance was marked read-only and missing Auth identities remained outside trusted Coordinator groups.
- **Status:** Pass
- **Evidence:** test_s93.py::test_selected_inventory_marks_cross_lead_and_legacy_read_only; test_s85.py::test_overview_reports_invalid_owners_without_creating_groups

## TC-EVENTREQUESTS-104 — successful S-84 transfer clears one inactive-owner warning

- **Scenario:** An in-scope Lead resolves an inactive assignment using the existing S-84 path.
- **Pre-conditions:** Inactive A owns two active L1 events at versions 2 and 4; active C is eligible; each event has separate event-linked records.
- **Steps:** 1. Read A's count and warnings. 2. Reassign the first event from A to C through S-84. 3. Reread A and C inventories and L1 oversight.
- **Test data:** A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`, C `cccccccc-cccc-4ccc-8ccc-cccccccccccc`; `Autumn Forum` version 2 and `Winter Fair` version 4.
- **Expected:** S-84 reports a successful transfer to C with version 3 and previous owner A; A's count drops from 2 to 1 and only the remaining event is warned. C's count rises by 1; L1's oversight updates immediately. Existing S-84 notifications and audit still run.
- **Actual:** A real S-84 transfer reduced the inactive former owner count to zero and preserved the linked booking, equipment, technical and history rows.
- **Status:** Pass
- **Evidence:** tests/integration/composite/event_requests/test_s93.py::test_inactive_target_is_rejected_but_existing_work_can_be_transferred

## TC-EVENTREQUESTS-105 — failed and concurrent transfers leave warnings intact

- **Scenario:** An unsuccessful S-84 attempt cannot make an inactive assignment appear resolved.
- **Pre-conditions:** Inactive A owns an active L1 event at version 2; C and D are active replacement candidates. Another operation may win the compare-and-set, or Events/Users may fail.
- **Steps:** 1. Submit two competing transfers with expected owner A and version 2. 2. Repeat with stale version 1. 3. Inject Events or Users failure and reread the inventory.
- **Test data:** A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`; C `cccccccc-cccc-4ccc-8ccc-cccccccccccc`; D `ffffffff-ffff-4fff-8fff-ffffffffffff`; event `Autumn Forum`.
- **Expected:** At most one transfer wins; losers return `409`, and only the winner's actual owner/count is shown. If no transfer succeeds, the event stays with A and remains warned. Downstream failures return safe `502`, with no fabricated success or notification.
- **Actual:** Stale and concurrent S-84 writes remained version guarded; inventory counts came from current Events ownership rather than the attempted action.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s84.py::test_internal_reassignment_rejects_stale_or_same_owner_requests; tests/integration/composite/event_requests/test_app.py::test_reassignment_transfers_access_and_repairs_notifications

## TC-EVENTREQUESTS-106 — S-83/S-84/S-85/S-88 behaviour remains intact

- **Scenario:** Availability filtering changes only target eligibility and the explicit S-93 inventory exception.
- **Pre-conditions:** L1 and L2; one unassigned submitted event; one active L1 event with a pending S-88 request; A and C active, B inactive.
- **Steps:** 1. Read shared S-83 queue, both ordinary S-85 views and both S-88 request lists. 2. Assign the unassigned event to C. 3. Reassign the requested event from A to C through S-84. 4. Reread S-88 request history as A.
- **Test data:** L1 `dddddddd-dddd-4ddd-8ddd-dddddddddddd`, L2 `eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee`; A/B/C as above; S-88 reason `Leaving the team`.
- **Expected:** Both Leads see the unassigned queue; only L1 sees its assigned event and S-88 request. S-83/S-84 still record L1 and notify their existing recipients; S-84 actions only the matching request, and A can still read that outcome after losing event access. B is never a new target; L2 gains no write access.
- **Actual:** S-83/S-84/S-85/S-88 regressions passed with the eligibility and scope changes, including original-requester history and existing notifications.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s83.py; test_s84.py; test_s85.py; test_s88.py; tests/integration/composite/event_requests/test_s88.py
