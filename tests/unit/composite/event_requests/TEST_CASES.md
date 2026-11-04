# Test cases — event_requests service (unit)

Covers `test_app.py`, `test_s83.py`, `test_s84.py`, and `test_s93.py`: the composite workflows spanning the
events, users, and notifications atomic services. All three outbound HTTP
clients are faked; no network, database, or Docker.

| | |
| --- | --- |
| Suite | `pytest tests/unit/composite/event_requests` |
| Last run | 2026-10-27, S-93 merge tree of `5aed635` and `origin/sprint4` `0d143d7` |
| Environment | Python 3.14.8, pytest 9.1.1; mocked HTTP services; no network, database or Docker. |
| Result | 128 passed, 17 skipped in this folder; 1,503 passed, 17 skipped across Python unit. |

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

---

## S-82 — View Event Change History

`test_s82.py`. `GET /event-requests/{event_id}/history` returns an event's
history to its assigned Coordinator and to any Lead, with names filled in from
the users service.

**Shared test data.**

```
event E            11111111-1111-4111-8111-111111111111
Coordinator C      aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa  "Alex Coordinator"
Coordinator C2     bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb  "Blair Coordinator"
Lead L             dddddddd-dddd-4ddd-8ddd-dddddddddddd  "Lee Lead"
Lead L2            eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee
Organiser O        22222222-2222-4222-8222-222222222222  "Ada Organiser"
```

Events fake history for E, newest first:
1. `coordinator_reassigned` by L, `{"from_coordinator_id": C, "to_coordinator_id": C2}`
2. `edited` by C
3. `submitted` by O

## TC-EVENTREQUESTS-117 — the assigned Coordinator reads the event's history

- **Scenario:** The Coordinator responsible for an event sees who did what and when (S-82 AC2).
- **Pre-conditions:** Signed in as C2; Events says E is assigned to C2; Users profiles return the names above.
- **Steps:** `GET /event-requests/E/history`.
- **Test data:** As above.
- **Expected:** `200` with
  ```json
  {
    "event_id": "E",
    "event_name": "Autumn Forum",
    "entries": [
      {"id": 3, "occurred_at": "...", "category": "assignment", "action": "coordinator_reassigned",
       "details": {"from_coordinator_id": "C", "to_coordinator_id": "C2"},
       "actor": {"id": "L", "name": "Lee Lead", "role": "event_coordinator_lead"}},
      ...
    ],
    "people": {"C": "Alex Coordinator", "C2": "Blair Coordinator"}
  }
  ```
  The entries are in the Events order (newest first). `people` names every user id that appears in an entry's `details`. Users is asked for all ids in one `POST /internal/users/profiles` call.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_the_assigned_coordinator_reads_the_history; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTREQUESTS-118 — any Lead reads any event's history

- **Scenario:** A Lead sees the history of every event, not only those they assigned (developer decision 6).
- **Pre-conditions:** Signed in as L2; E was assigned by L.
- **Steps:** `GET /event-requests/E/history`.
- **Test data:** As above.
- **Expected:** `200` with the same body as TC-EVENTREQUESTS-117.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_any_lead_reads_any_history; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTREQUESTS-119 — a Coordinator not assigned to the event is turned away

- **Scenario:** A former or unrelated Coordinator cannot read the history.
- **Pre-conditions:** E is assigned to C2.
- **Steps:**
  1. As C (the former Coordinator), `GET /event-requests/E/history`.
  2. As C, the same for an event that does not exist.
- **Test data:** As above.
- **Expected:** Both `404` "Event not found". The Events history read is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_an_unassigned_coordinator_is_turned_away; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTREQUESTS-120 — other roles cannot read the history here

- **Scenario:** Only Coordinators and Leads use this route.
- **Pre-conditions:** As in each row.
- **Steps / Test data / Expected:**
  | Caller | Response |
  | --- | --- |
  | No session | `401` |
  | `event_organiser` O | `403` |
  | `safety_officer` | `403` |
  | `technical_support` | `403` |
  | `venue_staff` | `403` |
  | `attendee` | `403` |

  The Events history read is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_other_roles_cannot_read_the_history; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTREQUESTS-121 — missing people are shown honestly

- **Scenario:** A deleted account or a backfilled entry with no recorded actor never shows a made-up name.
- **Pre-conditions:** As C2. Events history: one `request_approved` with `actor_id: null`, `details.backfilled: true`; one `edited` by `ffffffff-ffff-4fff-8fff-ffffffffffff`, whom Users does not return.
- **Steps:** `GET /event-requests/E/history`.
- **Test data:** As above.
- **Expected:** `200`. The first entry's `actor` is `null`. The second's is `{"id": "ffffffff-…", "name": null, "role": "event_coordinator"}`, with the role kept from the entry.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_missing_people_are_shown_honestly; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTREQUESTS-122 — a service that does not answer is a 502

- **Scenario:** The history is never shown half-filled.
- **Pre-conditions:** As C2.
- **Steps / Test data / Expected:**
  | Failure | Response |
  | --- | --- |
  | Events history read returns `500` | `502` "Events service unavailable" |
  | Events history read times out | `502` "Events service unavailable" |
  | Users profiles returns `500` | `502` "Users service unavailable" |
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_a_service_that_does_not_answer_is_a_502; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## S-59 — Request Event Changes (confirmed specification)

Latest S-59 execution: 2026-10-30, rebased `S-59/request-event-changes` on `origin/sprint4` d1f6d8b. Full Python unit suite: 1,659 passed, 17 skipped; full TEST integration suite: 104 passed, 5 skipped.
Full Python unit run: 1,659 passed, 17 skipped; focused composite S-59 cases passed where marked below.

The composite authenticates through Users and coordinates Events and Equipment
over HTTP. The Events service owns proposal persistence; this service owns no
table and does not write accepted Equipment requirements.

## TC-EVENTREQUESTS-117 — trusted identity and ownership gate proposal submission

- **Scenario:** The public composite accepts only the event's real Organiser.
- **Pre-conditions:** Mock Users returns O as `event_organiser`; Events returns E owned by O; alternate responses represent U, a Coordinator, Lead, and no session.
- **Steps:** 1. POST a change as O. 2. Repeat with each alternate identity and a forged organiser ID. 3. Inspect outbound calls.
- **Test data:** E `11111111-1111-4111-8111-111111111111`; O `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`; U `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`; attendance 120→150.
- **Expected:** O reaches Events and gets `201`; unauthenticated gets `401`, other roles `403`, unrelated U `404`. Forged actor is rejected; the composite forwards only trusted O identity and makes no Equipment or Events write for denied callers.
- **Actual:** Trusted Organiser submission succeeded; other roles and an unrelated Organiser were denied.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/composite/event_requests/test_s59.py`.

## TC-EVENTREQUESTS-118 — equipment proposal is a snapshot, not an accepted write

- **Scenario:** Organiser can propose item quantities while Equipment remains authoritative for accepted requirements.
- **Pre-conditions:** E has accepted projector quantity 2 and microphone quantity 4 through Equipment; catalogue offers active projector and microphone. O owns E.
- **Steps:** 1. GET the form data. 2. Propose projector 3 and remove microphone. 3. Inspect the Events request body and Equipment calls. 4. Read the proposal again.
- **Test data:** Projector `22222222-2222-4222-8222-222222222222` 2→3; microphone `33333333-3333-4333-8333-333333333333` 4→0/removal.
- **Expected:** Proposal records item IDs and desired quantities, with accepted 2/4 baseline and explicit microphone removal; no Equipment PUT/DELETE occurs. GET returns the same snapshot for comparison, including a retired item in the accepted baseline if it already existed.
- **Actual:** Equipment quantities and removal were saved only as snapshots; no Equipment mutation occurred.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/composite/event_requests/test_s59.py`.

## TC-EVENTREQUESTS-119 — effective no-op and invalid equipment are refused

- **Scenario:** Composite compares all proposed fields after normalization and validates equipment selections.
- **Pre-conditions:** E has unchanged date, attendance and venue fields; Equipment has projector quantity 2 and retired microphone quantity 4.
- **Steps:** 1. Submit unchanged Events values and projector quantity 2. 2. Try an unknown item, retired item as a new selection, duplicate item ID, quantity -1, and a changed date with incompatible registration close. 3. Inspect Events writes.
- **Test data:** Projector quantity 2; unknown UUID `ffffffff-ffff-4fff-8fff-ffffffffffff`; quantity -1; registration closes 2026-11-18 09:00 with proposed event start 2026-11-18 08:00.
- **Expected:** Effective no-op and invalid values get `422`; none writes a request. Existing retired requirements may remain in the snapshot, but cannot be newly added. Date/time and existing registration settings remain internally consistent.
- **Actual:** Normalized no-op, unknown item and duplicate equipment IDs were rejected.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/composite/event_requests/test_s59.py`.

## TC-EVENTREQUESTS-120 — only the current Coordinator sees the comparison

- **Scenario:** The public Coordinator read is scoped to the event's current assignment.
- **Pre-conditions:** Pending R for E; C is assigned, D is unrelated; later S-84 reassigns E to D.
- **Steps:** 1. GET R as C, D, O, unrelated Organiser and anonymous. 2. Reassign via S-84. 3. GET as C and D again.
- **Test data:** E `11111111-1111-4111-8111-111111111111`; accepted attendance 120, proposed 150.
- **Expected:** C and O initially see current versus proposed values and pending status; D and unrelated Organiser get `404`, anonymous `401`. After reassignment D sees R and C gets `404`. Ordinary Lead supervisory scope is unchanged.
- **Actual:** The current Coordinator read used the assigned-event route; unrelated access returned 404.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/composite/event_requests/test_s59.py`.

## TC-EVENTREQUESTS-121 — downstream failures do not fake success

- **Scenario:** A broken Users, Equipment or Events call produces a controlled error without changing accepted values.
- **Pre-conditions:** O owns E; accepted attendance is 120; mock each dependency to time out or return an error in turn.
- **Steps:** 1. Submit attendance and equipment changes with each failure. 2. Inspect API response and outbound mutation calls. 3. Retry after recovery.
- **Test data:** Attendance 120→150; projector 2→3; `httpx.TimeoutException` and HTTP 503.
- **Expected:** The composite returns safe `502` for unavailable dependencies and never returns a created request without Events confirmation. Equipment is never mutated; E stays at 120. Retrying after recovery creates one pending request or reports an existing one, never two.
- **Actual:** Duplicate responses and dependency timeouts did not report success or mutate accepted services.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/composite/event_requests/test_s59.py`.

## TC-EVENTREQUESTS-122 — stale and concurrent submissions have one outcome

- **Scenario:** Two tabs cannot overwrite one another's pending proposal or the comparison baseline.
- **Pre-conditions:** O owns E at accepted attendance 120; two requests start from the same event state; C may meanwhile edit accepted data through S-18.
- **Steps:** 1. Send two different proposals concurrently. 2. Change accepted E between snapshot and submit; attempt a stale proposal. 3. Read E and R.
- **Test data:** Proposals 150 and 180; intervening S-18 accepted value 130.
- **Expected:** At most one proposal is pending; competing or stale submissions return `409` with reload guidance. The winner's baseline is the accepted version it compared against; E remains at its independently accepted value. No request silently treats stale equipment or event details as current.
- **Actual:** An observed Equipment race returned 409 in unit tests; two concurrent live submissions produced exactly one pending request and a 201/409 outcome.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/event_requests/test_s59.py`; `tests/integration/composite/event_requests/test_s59.py::test_two_concurrent_submissions_leave_one_pending_row`, 2026-10-30.

## TC-EVENTREQUESTS-123 — existing assignment and edit routes keep their scope

- **Scenario:** S-59 does not broaden S-83/S-84/S-85/S-88 visibility or perform S-60 acceptance.
- **Pre-conditions:** Lead L1 owns E's assignment to C, Lead L2 is unrelated, E has pending R, and E2 is an unrelated planning event.
- **Steps:** 1. Read S-85/S-88 as L1 and L2. 2. Reassign E through S-84. 3. Perform a permitted S-18 Coordinator edit on E2. 4. Read R and accepted E.
- **Test data:** L1/L2 distinct UUIDs; R attendance 120→150; E2 routine contact edit.
- **Expected:** Existing Lead scope, reassignment history and S-18 behaviour remain; R follows the current Coordinator for read access, stays pending, and never updates E's accepted attendance. No proposal creation invokes S-60 review or arrangement resolution.
- **Actual:** The full existing event-management unit regression suite passed with S-59 routes added.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/composite/event_requests/test_s59.py` plus existing S-83/S-84/S-85/S-88/S-18 cases.

## S-69 — Notify Attendee — Event Cancelled

Acceptance criteria (developer, 2026-10-30): a notification is sent to all
currently-registered Attendees when the event's status changes to Cancelled;
it identifies the event and states it has been cancelled; it is sent at the
time the cancellation is confirmed.

Developer's answers, 2026-10-30: Attendees on the waiting list -- including
one holding an offered place (S-55) -- are notified too. The message carries
no reason: approval records none, and the Organiser's request reason is
written for the Coordinator.

The cancellation is confirmed when the assigned Coordinator approves it
(S-61, `POST /event-requests/{id}/cancellation-decision`). After the events
service records it and the bookings are released, the composite reads the
event's places (`GET /registrations/events/{id}`) and waiting list
(`GET /registrations/waiting-list/events/{id}`) and posts one `event_cancelled`
notification per Attendee to `POST /internal/notifications`, in batches of at
most 20 (the service's limit). Each is deduplicated on
`event_cancelled:{event id}:{attendee id}`, so approving again -- how S-61
retries a failed step -- never notifies anyone twice.

Drafted 2026-10-30 on `S-69/notify-attendee-event-cancelled` (from
`origin/sprint4`). Confirmed by the developer 2026-10-30.

Event E (`22222222-2222-4222-8222-222222222222`) "Alumni networking evening",
`2026-11-20` 18:00–21:00. Coordinator C is assigned and E has a pending
cancellation request. Events fake answers the decision `200` with E
`cancelled`, `cancellation_decision` `approved`; bookings fake answers the
release `200` `{"deleted": []}`. Attendees A and B hold places; W is waiting;
O holds an offered place (waiting-list row with `offered_at` set).

## TC-EVENTREQUESTS-124 — approving a cancellation notifies everyone registered or waiting

- **Scenario:** Every Attendee holding a place, waiting, or holding an offer gets one notification naming the event and saying it is cancelled, as the cancellation is confirmed (S-69 AC1, AC2, AC3).
- **Pre-conditions:** As above. Registrations fake: places A, B; waiting list W, O. Notifications fake answers `201`.
- **Steps:** As C, `POST /event-requests/E/cancellation-decision` `{"decision": "approved"}`.
- **Test data:** As above.
- **Expected:** `200`, body includes `"status": "cancelled"` and `"notified_attendees": 4`. Notifications received one `POST /internal/notifications` with exactly four rows, recipients A, B, W, O, each:
  `{"recipient_id": <id>, "event_id": "E", "event_name": "Alumni networking evening", "kind": "event_cancelled", "message": "Event cancelled: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm. It will not take place.", "deduplication_key": "event_cancelled:E:<id>"}`.
  The bookings release ran before the notifications were sent.
- **Actual:** `200`, `cancelled`, `notified_attendees` 4; one batch with exactly the four rows for A, B, W, O; bookings released before notifying.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s69.py::test_approving_a_cancellation_notifies_everyone_registered_or_waiting; 2026-10-30, branch `S-69/notify-attendee-event-cancelled` (on sprint4 `58d6d9f`), pre-commit working tree; Python 3.12.5, pytest 9.1.1: 1712 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-125 — the message names an event ending on a later day in full

- **Scenario:** The event is identified by name, date and time, in the same wording as the S-49 confirmation (S-69 AC2).
- **Pre-conditions:** As TC-EVENTREQUESTS-124, but E ends `2026-11-21` 00:30; only A holds a place.
- **Steps:** Approve as C.
- **Test data:** As above.
- **Expected:** A's message is exactly "Event cancelled: Alumni networking evening, 20 Nov 2026, 6:00 pm – 21 Nov 2026, 12:30 am. It will not take place."
- **Actual:** "Event cancelled: Alumni networking evening, 20 Nov 2026, 6:00 pm – 21 Nov 2026, 12:30 am. It will not take place."
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s69.py::test_the_message_names_an_event_ending_on_a_later_day_in_full; 2026-10-30, branch `S-69/notify-attendee-event-cancelled` (on sprint4 `58d6d9f`), pre-commit working tree; Python 3.12.5, pytest 9.1.1: 1712 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-126 — large events are notified in batches of 20

- **Scenario:** Every Attendee is notified however many there are (S-69 AC1).
- **Pre-conditions:** As TC-EVENTREQUESTS-124, but 23 Attendees hold places and 2 are waiting.
- **Steps:** Approve as C.
- **Test data:** 25 distinct attendee ids.
- **Expected:** `200`, `"notified_attendees": 25`. Two `POST /internal/notifications` calls, of 20 and 5 rows; together each of the 25 recipients exactly once.
- **Actual:** `200`, `notified_attendees` 25; batches of 20 and 5 covering all 25 once.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s69.py::test_large_events_are_notified_in_batches_of_20; 2026-10-30, branch `S-69/notify-attendee-event-cancelled` (on sprint4 `58d6d9f`), pre-commit working tree; Python 3.12.5, pytest 9.1.1: 1712 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-127 — no one is notified unless a cancellation is confirmed

- **Scenario:** Declining leaves the event as it was, so no Attendee hears anything; an approved event with no one registered sends nothing (S-69 AC1, AC3).
- **Pre-conditions:** (a) The events fake answers the decision `200` with `cancellation_decision` `declined` and E still `confirmed`. (b) As TC-EVENTREQUESTS-124 but both registrations lists are `[]`. (c) The events fake answers `403`.
- **Steps:** `POST /event-requests/E/cancellation-decision` once per pre-condition, (a) with `{"decision": "declined", "reason": "Go ahead as planned"}`.
- **Test data:** As above.
- **Expected:** (a) `200`, registrations and notifications never called. (b) `200` with `"notified_attendees": 0`, notifications never called. (c) `403` passed through, registrations and notifications never called.
- **Actual:** (a) `200`, registrations and notifications not called; (b) `200`, `notified_attendees` 0, notifications not called; (c) `403`, neither called.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s69.py::test_no_one_is_notified_unless_a_cancellation_is_confirmed; 2026-10-30, branch `S-69/notify-attendee-event-cancelled` (on sprint4 `58d6d9f`), pre-commit working tree; Python 3.12.5, pytest 9.1.1: 1712 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-128 — a failed notification is retried by approving again

- **Scenario:** If the Attendees can't be told, the Coordinator is told so, and approving again sends the notifications without duplicating any (S-69 AC1, AC3; the S-61 retry pattern).
- **Pre-conditions:** As TC-EVENTREQUESTS-124. In turn: (a) the registrations fake raises `httpx.ConnectError`; (b) the notifications fake answers `500`. Then (c) both answer normally, and the events fake answers the repeated approval `200` with E unchanged (S-61: approving again is a no-op).
- **Steps:** Approve as C for (a), (b), then (c).
- **Test data:** As above.
- **Expected:** (a), (b) → `502` "The event is cancelled, but its attendees were not notified. Approve again to notify them." (c) → `200`, `"notified_attendees": 4`, with the same four `deduplication_key`s as TC-EVENTREQUESTS-124.
- **Actual:** (a), (b) `502` with the expected detail; (c) `200`, `notified_attendees` 4, the same four deduplication keys.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s69.py::test_a_failed_notification_is_retried_by_approving_again; 2026-10-30, branch `S-69/notify-attendee-event-cancelled` (on sprint4 `58d6d9f`), pre-commit working tree; Python 3.12.5, pytest 9.1.1: 1712 passed and 17 skipped across `tests/unit`

## S-63 — Notify Organiser — Event Decisions and Changes

Drafted and confirmed by the developer on 2026-10-31 before implementation.

## TC-EVENTREQUESTS-129 — every request decision tells its Organiser

- **Scenario:** Approving, rejecting, or returning a submitted request creates one persistent notice for its Organiser.
- **Pre-conditions:** The Coordinator is authorised; Events saves the selected outcome and returns event `33333333-3333-4333-8333-333333333333`, "Autumn Forum", owned by Organiser `11111111-1111-4111-8111-111111111111`.
- **Steps:** `POST /event-requests/{id}/decision` once per outcome.
- **Test data:** Approved; rejected with reason "Date unavailable"; returned with reason "Missing contact" and comment "Add a telephone number".
- **Expected:** The Events write succeeds first. Notifications receives one `event_request_decision` row naming the event and outcome. Rejected names the reason; returned tells the Organiser to amend and resubmit and includes both guidance fields.
- **Actual:** All three outcomes produced one Organiser row with the expected event, outcome, reason and action wording.
- **Status:** Pass
- **Evidence:** `test_s63.py::test_each_request_decision_notifies_the_organiser_with_its_action`; 2026-10-31, S-63 branch; full Python unit suite 1735 passed, 17 skipped.

## TC-EVENTREQUESTS-130 — assignment and reassignment still tell the Organiser once

- **Scenario:** S-63 preserves the existing assignment messages while adding the other outcomes.
- **Pre-conditions:** The existing S-83/S-84 assignment fixtures.
- **Steps:** Assign, then reassign the event.
- **Expected:** The Organiser receives exactly one row for each successful action, naming the new Coordinator; stable keys prevent duplicates.
- **Actual:** Existing assignment and reassignment tests retained one Organiser row per action and stable keys.
- **Status:** Pass
- **Evidence:** S-83/S-84 assignment and reassignment tests in the 2026-10-31 full Python unit run: 1735 passed, 17 skipped.

## TC-EVENTREQUESTS-131 — schedule changes distinguish rescheduling and postponement

- **Scenario:** A saved Coordinator date/time change tells the Organiser; a routine edit does not.
- **Pre-conditions:** The assigned event is editable with `edit_version` 3.
- **Steps:** Save (a) a different time on the same date, (b) a later date, and (c) contact details only through the composite information route.
- **Expected:** (a) one `event_schedule_changed` notice saying rescheduled, (b) one saying postponed, each with the old and new window and next-action wording; (c) no notice. The Events response remains authoritative.
- **Actual:** Same-day movement was labelled rescheduled, a later start was labelled postponed, both windows and the next action were present, and the contact-only edit sent nothing.
- **Status:** Pass
- **Evidence:** `test_s63.py::test_schedule_changes_name_the_old_and_new_time_and_required_attention` and `test_routine_information_edits_do_not_create_a_change_notification`; 2026-10-31 full Python unit run: 1735 passed, 17 skipped.

## TC-EVENTREQUESTS-132 — cancellation tells the Organiser as well as Attendees

- **Scenario:** An approved cancellation creates a separate Organiser notice without changing the existing Attendee count or messages.
- **Pre-conditions:** The assigned Coordinator approves a pending cancellation; booking release succeeds.
- **Steps:** `POST /event-requests/{id}/cancellation-decision` with `approved`.
- **Expected:** One `event_cancelled` row addressed to the Organiser names the event and states it is cancelled; existing Attendee rows remain unchanged and recipients are deduplicated.
- **Actual:** Approval sent the separate Organiser row, preserved Attendee counting, and reported `organiser_notified: true`.
- **Status:** Pass
- **Evidence:** `test_s69.py` cancellation notification cases; 2026-10-31 full Python unit run: 1735 passed, 17 skipped.

## TC-EVENTREQUESTS-133 — unsuccessful actions never announce an outcome

- **Scenario:** A refused or failed Events write cannot produce a misleading Organiser notice.
- **Pre-conditions:** Events answers `409`, then is unavailable.
- **Steps:** Attempt the decision and information routes in each state.
- **Expected:** The composite preserves the mapped error and never calls Notifications.
- **Actual:** Refused and unavailable Events calls preserved their error and made no Notifications request.
- **Status:** Pass
- **Evidence:** `test_s63.py` refused/failed action cases; 2026-10-31 full Python unit run: 1735 passed, 17 skipped.

## TC-EVENTREQUESTS-134 — notification failure never rewrites the saved event

- **Scenario:** Cross-service notification failure is reported without attempting to reverse an authoritative event action.
- **Pre-conditions:** Events saves successfully; Notifications times out or answers `500`.
- **Steps:** Save a request decision or schedule change.
- **Expected:** The response reports Notifications unavailable; Events is called once and no compensating event write occurs.
- **Actual:** A notification timeout or failure returned controlled `502`; the accepted Events write was made once and was not reversed.
- **Status:** Pass
- **Evidence:** `test_s63.py::test_a_notification_failure_is_reported_after_the_event_was_saved`; 2026-10-31 full Python unit run: 1735 passed, 17 skipped.

## S-89 — Coordinator Cancels Event Without Alternative Venue (draft specification)

Acceptance criteria (developer, 2026-11-01): (1) the system never cancels or
rejects an event affected by venue unavailability automatically; (2) after
working with the Event Organiser on alternatives, the assigned Coordinator
may cancel the event with a recorded reason; (3) cancelling releases all of
the event's venue bookings, tentative holds and equipment reservations;
(4) the Event Organiser is notified and currently registered Attendees are
notified as in S-69.

Drafted 2026-11-01 on `S-89/coordinator-cancels-event-without-alternative-venue`
(from `origin/sprint4` `ca5ff0d`). Confirmed by the developer 2026-11-01.
IDs 400–449 are reserved for S-89 unit cases (S-60 holds 3xx).

Changed after confirmation, by the developer's 2026-11-01 decisions: the 404
keeps this composite's existing wording (TC-EVENTREQUESTS-401); a retry
reports the event's total released bookings.

Revised 2026-11-01 at the developer's request:
- **Flag reuse.** Eligibility is read from the `venue_bookings` composite
  that owns S-77's rule (`GET /venue-bookings?event_id=`), instead of a
  duplicated copy. It therefore has S-77's own scope, including "from today
  on" -- S-89 adds no date restriction of its own. TC-EVENTREQUESTS-402/403
  now test the use of that flag; the rule itself is TC-VENUEBOOKINGS-067
  onward.
- **Closure before cancellation.** The bookings are closed to new active
  bookings before the event is cancelled, and reopened if it is not
  (TC-EVENTREQUESTS-404, 406, 417, 418).
- **Durable history.** The S-82 entry is its own retryable step, before the
  release; completion waits for it (TC-EVENTREQUESTS-416).

`POST /event-requests/{id}/venue-cancellation`, body
`{"reason", "alternatives_considered", "expected_version"}`. In order, with
one fresh `operation_id` per call:

1. Authenticate (`GET /users/me`), Coordinators only.
2. `GET /events/assigned/{id}` with the caller's cookies (404 if not theirs).
3. If the event is already venue-cancelled by S-89, resume from step 7.
4. `GET /venue-bookings?event_id={id}` on `venue_bookings` with the caller's
   cookies. The ids with `requires_alternative_arrangements: true` are the
   affected bookings; none → `409` (after withdrawing any abandoned closure).
5. `POST /internal/events/{id}/bookings/closure` with `operation_id`.
6. `POST /internal/events/{id}/venue-cancellation` (service token, the
   caller's cookies, `affected_booking_ids`). A definite non-`200` answer
   withdraws the closure (`.../closure/reopen`, same `operation_id`) and is
   passed on; no answer keeps the closure unless a re-read shows the event
   cancelled.
7. `POST /internal/events/{id}/venue-cancellation/history`.
8. `POST /internal/events/{id}/bookings/release` with `operation_id`, then
   `GET /bookings?event_id` checks nothing is still pending/held/confirmed;
   if something is, it releases once more.
9. Notify the Organiser (one row, with the reason).
10. Notify Attendees exactly as S-69 (places and waiting list, batches of
    20, the S-69 message).
11. `POST /internal/events/{id}/venue-cancellation/complete`.

Equipment needs no call. Requirement rows reserve stock only while the
event's status is committed (S-44 `/events/overlapping`), so `cancelled`
releases them. The rows stay, as history. This is the S-61 precedent.

Shared data. Today is `2026-11-01`. Event E `22222222-2222-4222-8222-222222222222`
"Alumni networking evening", `confirmed`, 2026-11-20 09:00–21:00,
`edit_version` 7, Organiser O `11111111-1111-4111-8111-111111111111`,
Coordinator C `cccccccc-cccc-4ccc-8ccc-cccccccccccc`. E's bookings: B1
`confirmed` V1 2026-11-20 18:00–21:00; B2 `confirmed` V2 09:00–12:00; H1
`held` V2 13:00–15:00; R1 `pending` at V3 18:00–21:00 replacing B1; J1
`rejected`. `venue_bookings` reports B1 (only) flagged. Attendees A1, A2
hold places; W1 is waiting. Body: reason "Hall A is closed for structural
repairs on the event date", alternatives "Discussed Hall B and Seminar Room 3
with the Organiser on 30 Oct; neither fits 180 guests", `expected_version` 7.

## TC-EVENTREQUESTS-400 — an affected multi-venue event is closed, cancelled, recorded, released and announced

- **Scenario:** The assigned Coordinator cancels with a recorded reason; every booking, hold and pending request is released through Bookings; the Organiser and Attendees are told (S-89 AC2, AC3, AC4).
- **Pre-conditions:** Every fake answers successfully.
- **Steps:** As C, `POST /event-requests/E/venue-cancellation` with the shared body.
- **Test data:** As above.
- **Expected:** `200` with E's fields plus `"released_bookings": 4, "organiser_notified": true, "notified_attendees": 3, "cancellation_completed": true`. Calls in order: users, events read, venue_bookings read, closure, cancel, history, release, bookings re-read, notifications, complete (last). The cancel carries the token, C's cookies and `affected_booking_ids` [B1]; closure and release carry the same `operation_id`; the closure ends `closed`; J1 stays rejected; Equipment is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_an_affected_multi_venue_event_is_cancelled_released_and_announced; tests/unit/composite/event_requests/test_s89.py::test_the_events_write_carries_the_callers_own_session; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-401 — only the assigned Coordinator can start it

- **Scenario:** Server-side authorisation; nothing is read or written for anyone else.
- **Pre-conditions:** As TC-EVENTREQUESTS-400.
- **Steps:** Call as (a) no session; (b) an Organiser; (c) Venue Staff; (d) a Lead; (e) Coordinator D, for whom `GET /events/assigned/E` is `404`.
- **Test data:** As above.
- **Expected:** (a) `401`; (b)–(d) `403`; (e) `404` "Event not found or not assigned to you". In every case Bookings, Notifications, Registrations and the events write routes are never called.
- **Actual:** (a) `401`; (b)–(d) `403`; (e) `404` "Event not found or not assigned to you". No write and no Bookings call in any case.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_without_a_session_nothing_is_read_or_written; tests/unit/composite/event_requests/test_s89.py::test_other_roles_are_refused; tests/unit/composite/event_requests/test_s89.py::test_a_coordinator_not_assigned_is_refused; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-402 — an event not affected by unavailability cannot be cancelled here

- **Scenario:** The route is for genuinely affected events only; every other cancellation goes through S-62/S-61.
- **Pre-conditions:** (a) `venue_bookings` reports no booking flagged; (b) E has no bookings.
- **Steps:** Cancel as C.
- **Test data:** As above.
- **Expected:** `409` "None of this event's venue bookings is affected by an unavailable venue, so it can't be cancelled here." No events write; the only bookings call is a closure reopen with a fresh `operation_id` (withdrawing an abandoned attempt's closure, never a live one); nothing is closed.
- **Actual:** As expected in both.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_an_event_not_affected_by_unavailability_cannot_be_cancelled_here; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-403 — eligibility is exactly venue_bookings' S-77 flag

- **Scenario:** No second copy of the rule: what `venue_bookings` flags is what is affected, read with this Coordinator's own session (developer's 2026-11-01 decision). The rule itself -- setup/turnaround, half-open periods, resolutions, today on -- is TC-VENUEBOOKINGS-067 onward.
- **Pre-conditions:** (a) `venue_bookings` flags B1 and H1. (b) It answers `404`. (c) It answers `401`.
- **Steps:** Cancel as C.
- **Test data:** As above.
- **Expected:** (a) `200`; the read was `GET /venue-bookings` with `event_id` E and C's cookies; `affected_booking_ids` [B1, H1]. (b) `404`; (c) `401`; no write in either.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_eligibility_is_exactly_the_venue_bookings_flag; tests/unit/composite/event_requests/test_s89.py::test_venue_bookings_refusals_are_passed_on; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-404 — a refused cancellation withdraws the closure and releases nothing

- **Scenario:** Status gate, pending Organiser request, stale screen and validation refusals leave the event and its bookings as they were -- including open to new bookings again.
- **Pre-conditions:** The events write answers in turn `409` (status), `409` (Organiser request), `409` (stale), `422`. Separately: `409`, and the reopen answers `500`.
- **Steps:** Cancel as C for each.
- **Test data:** As above.
- **Expected:** The same status and body are returned. Bookings calls are exactly closure then reopen, with the same `operation_id`; no closure remains; no notification; the only events write is the cancel. If the reopen fails: `502` "The event was not cancelled, but its venue bookings could not be unlocked. Try again."
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_a_refused_cancellation_withdraws_the_closure_and_releases_nothing; tests/unit/composite/event_requests/test_s89.py::test_if_the_closure_cannot_be_withdrawn_that_is_said; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-405 — a failed verification read changes nothing

- **Scenario:** If the flag or the event cannot be read, the system cannot know, so it changes nothing.
- **Pre-conditions:** In turn: `venue_bookings` raises `httpx.ConnectError`; answers `500`; `GET /events/assigned/E` answers `500`.
- **Steps:** Cancel as C for each.
- **Test data:** As above.
- **Expected:** `502` "Venue bookings service unavailable" (twice), "Events service unavailable". No write of any kind.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_a_failed_verification_read_changes_nothing; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-406 — the closure and the cancellation fail safely

- **Scenario:** Whatever fails between closing the bookings and cancelling the event, the result is never a cancelled event with open bookings, and never a closed event that is reported as untouched.
- **Pre-conditions:** (a) The closure raises `ConnectError`. (b) The events write answers `500`. (c) It raises `ReadTimeout` and a re-read shows E not cancelled. (d) It raises `ReadTimeout`, but the write landed. (e) It raises `ReadTimeout` and the re-read fails.
- **Steps:** Cancel as C.
- **Test data:** As above.
- **Expected:** (a) `502` "The event could not be cancelled. Nothing was changed. Try again."; no events write; the closure is withdrawn. (b) The same detail; the closure is withdrawn; no notification. (c), (e) `502` "We couldn't confirm whether the event was cancelled, so its venue bookings stay locked for now. …"; the closure is **kept** (no reopen); no notification. (d) `200`, completed, no reopen.
- **Actual:** As expected in all five.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_a_failed_closure_cancels_nothing; tests/unit/composite/event_requests/test_s89.py::test_an_events_error_answer_withdraws_the_closure; tests/unit/composite/event_requests/test_s89.py::test_no_answer_and_not_cancelled_keeps_the_bookings_closed; tests/unit/composite/event_requests/test_s89.py::test_no_answer_but_cancelled_after_all_carries_on; tests/unit/composite/event_requests/test_s89.py::test_no_answer_and_no_reread_keeps_the_bookings_closed; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-407 — a failed release is reported, and cancelling again finishes it

- **Scenario:** Partial failure is never reported as success; the retry completes without re-checking the flag (released bookings no longer carry it) and repeats nothing done.
- **Pre-conditions:** First call: the release answers `500`. Second call: everything succeeds, and `venue_bookings` would now report nothing flagged.
- **Steps:** Cancel as C, then again with a different reason.
- **Test data:** As above.
- **Expected:** First → `502` "The event is cancelled, but its venue bookings were not released. Cancel again to finish."; no notification, no complete; the closure is still in place (`closing`). Second → `200`, `released_bookings` 4, completed; no `venue_bookings` read, no closure call, no second cancel write; the Organiser is notified once.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_a_failed_release_is_reported_and_cancelling_again_finishes_it; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-408 — a booking that slips in during the release is caught

- **Scenario:** A booking created concurrently (e.g. a Venue Staff confirmation landing after the release) does not survive into a "completed" cancellation.
- **Pre-conditions:** (a) The verification read after the release still shows R1 `confirmed`, the second release returns `[R1]`, and the re-read shows none active. (b) R1 is still active after the second release too.
- **Steps:** Cancel as C.
- **Test data:** As above.
- **Expected:** (a) `200`, `released_bookings` 5, with exactly two release calls. (b) `502` "The event is cancelled, but its venue bookings were not released. Cancel again to finish.", with no notifications and no complete call.
- **Actual:** (a) `200`, `released_bookings` 4 after exactly two release calls; (b) `502` release detail, no notification, no complete.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_a_booking_that_slips_in_during_the_release_is_caught; tests/unit/composite/event_requests/test_s89.py::test_a_booking_that_stays_active_is_a_failure; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-409 — the Organiser is told why, with the recorded reason

- **Scenario:** AC4 for the Organiser. The message identifies the event, says the Coordinator cancelled it because no alternative venue was found, and gives the reason.
- **Pre-conditions:** As TC-EVENTREQUESTS-400.
- **Steps:** Cancel as C.
- **Test data:** As above.
- **Expected:** Exactly one Organiser row: `{"recipient_id": O, "event_id": E, "event_name": "Alumni networking evening", "kind": "event_cancelled", "message": "Event cancelled: Alumni networking evening, 20 Nov 2026, 9:00 am – 9:00 pm. Your Event Coordinator cancelled it because no alternative venue could be found. Reason: Hall A is closed for structural repairs on the event date", "deduplication_key": "event_cancelled:E:O"}`.
- **Actual:** Exactly the one expected Organiser row, message and key.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_the_organiser_is_told_why_with_the_recorded_reason; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-410 — Attendees get the S-69 notification, unchanged

- **Scenario:** AC4 for Attendees, "as in S-69". The same recipients (places and the waiting list, deduplicated), the same message, the same keys, and batches of 20.
- **Pre-conditions:** (a) As TC-EVENTREQUESTS-400. (b) 23 places and 2 waiting.
- **Steps:** Cancel as C.
- **Test data:** As above.
- **Expected:** (a) A1, A2 and W1 each get one row with the message "Event cancelled: Alumni networking evening, 20 Nov 2026, 9:00 am – 9:00 pm. It will not take place." and key `event_cancelled:E:<id>`. (b) Two posts of 20 and 5 rows, with `notified_attendees` 25. The Organiser row is sent before the Attendee batches.
- **Actual:** (a) A1, A2, W1 once each with the S-69 message and keys, Organiser first (an Attendee both registered and waiting counted once); (b) batches of 20 and 5, `notified_attendees` 25.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_attendees_get_the_s69_notification_unchanged; tests/unit/composite/event_requests/test_s89.py::test_large_events_are_notified_in_batches_of_20; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-411 — a failed notification is never reported as a finished cancellation

- **Scenario:** S-89 is not complete while a required notification is missing; cancelling again sends only what is missing, without duplicates.
- **Pre-conditions:** In turn: (a) the Organiser post answers `500`; (b) the Organiser post succeeds and `GET /registrations/events/E` raises; (c) the second Attendee batch answers `500`. Each is followed by a successful retry, in which the events write answers `200` unchanged.
- **Steps:** Cancel as C, then again.
- **Test data:** As TC-EVENTREQUESTS-410.
- **Expected:** (a) `502` "The event is cancelled and its venue bookings released, but the Organiser was not notified. Cancel again to finish." (b), (c) `502` "The event is cancelled, but its attendees were not notified. Cancel again to notify them." The complete route is not called in any of them. Each retry → `200`, re-sending with the same deduplication keys (the notifications service drops repeats).
- **Actual:** (a) Organiser detail, (b), (c) Attendee detail, all `502` with no complete call; each retry `200` with no duplicate deduplication key.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_a_failed_notification_is_never_reported_as_finished; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-412 — the completion marker is the last step

- **Scenario:** `cancellation_completed` is only true when the events service recorded it.
- **Pre-conditions:** Everything succeeds except the complete call, which answers `500` (first call) and then `200` (retry).
- **Steps:** Cancel as C, then again.
- **Test data:** As above.
- **Expected:** First call → `502` "Everyone was notified, but the cancellation could not be marked complete. Cancel again to finish." Retry → `200`, `cancellation_completed` true.
- **Actual:** First `502` with the completion detail; retry `200`, `cancellation_completed` true.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_the_completion_marker_is_the_last_step; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-413 — an event cancelled another way is not cancelled again

- **Scenario:** No duplicate cancellation, release or notification across S-61 and S-89.
- **Pre-conditions:** `GET /events/assigned/E` returns E `cancelled` with `cancellation_decision` `approved` and no `venue_cancelled_at`.
- **Steps:** Cancel as C.
- **Test data:** As above.
- **Expected:** `409` "This event is already cancelled." The events write, release and Notifications are never called.
- **Actual:** `409` "This event is already cancelled."; no write.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_an_event_cancelled_another_way_is_not_cancelled_again; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-414 — validation happens before any downstream call

- **Scenario:** A blank reason or alternatives, or a missing version, is refused at the composite too.
- **Pre-conditions:** As TC-EVENTREQUESTS-400.
- **Steps:** Send `reason` `"  "`; `alternatives_considered` missing; `expected_version` `"x"`.
- **Test data:** As listed.
- **Expected:** `422` "Please check the details you entered", with the field named under `errors`. Only `GET /users/me` may have been called.
- **Actual:** Each `422` naming the field; no downstream call at all.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_validation_happens_before_any_downstream_call; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-415 — S-61, S-63 and S-69 behaviour is unchanged

- **Scenario:** Regression. Approving an Organiser's request still behaves exactly as before, including S-61's booking delete.
- **Pre-conditions:** The existing `test_s61.py`, `test_s63.py` and `test_s69.py`.
- **Steps:** Run them unchanged.
- **Test data:** As in those files.
- **Expected:** All pass with no edits to their assertions.
- **Actual:** `test_s61.py`, `test_s63.py`, `test_s69.py` unchanged: 28 passed.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s61.py; test_s63.py; test_s69.py; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`
## TC-EVENTREQUESTS-416 — a missing history entry stops the operation, and is retried

- **Scenario:** The S-82 entry is required: the operation does not go on, or complete, without it (developer's 2026-11-01 requirement).
- **Pre-conditions:** First call: the history step answers `500`; then everything succeeds.
- **Steps:** Cancel as C, then again.
- **Test data:** As above.
- **Expected:** First → `502` "The event is cancelled, but the cancellation was not recorded in its history. Cancel again to finish."; no release, no notification, no complete. Second → `200`; the history step ran again (idempotent at the events service, TC-EVENTS-410) and is recorded.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_a_missing_history_entry_stops_the_operation_and_is_retried; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-417 — a losing concurrent attempt never unlocks the winner's closure

- **Scenario:** Two attempts (two tabs): the one that loses at the events service must not reopen bookings the other has closed and is cancelling.
- **Pre-conditions:** A closure from another operation already exists; this attempt's cancel is refused `409` (stale).
- **Steps:** Cancel as C.
- **Test data:** As above.
- **Expected:** `409` passed on. The reopen carries this attempt's own `operation_id`, so the other operation's closure is still in place.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_a_losing_concurrent_attempt_never_unlocks_the_winners_closure; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

## TC-EVENTREQUESTS-418 — the bookings are closed before the event is cancelled

- **Scenario:** No active booking can appear after the cancellation has started (developer's 2026-11-01 requirement): the closure always precedes the events write.
- **Pre-conditions:** The events fake fails any cancel that arrives before a closure exists, so every successful case also proves the order.
- **Steps:** Cancel as C.
- **Test data:** As above.
- **Expected:** `200`; the closure call precedes the cancel call.
- **Actual:** As expected; removing the closure step makes 25 of this file's 42 tests fail.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s89.py::test_the_bookings_are_closed_before_the_event_is_cancelled; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree, after the closure-intent and durable-history revision; Python 3.12.5, pytest 9.2.0, fastapi 0.116.1: 1883 passed and 17 skipped across `tests/unit`

---

## S-60 — Review Impact of Significant Changes (approved)

Source: Product Backlog row 63. Latest S-60 execution: 2026-11-01 on `S-60/review-impact-of-significant-changes` at `d5bab4c` (rebased onto `origin/sprint4` `ca5ff0d`) plus the follow-up S-18/S-63/S-82 route and registration-cleanup test updates committed on top. Python unit suite 1,783 passed, 17 skipped; frontend unit 219 passed; lint passes with 3 existing warnings; build passes; `git diff --check` clean. TEST Supabase and fresh `.env.test` stack for integration (119 passed, 5 skipped) and Chromium. See each case evidence.

## TC-EVENTREQUESTS-300 — only the assigned Coordinator can review

- **Scenario:** Current assignment determines access to the pending proposal and impact review.
- **Pre-conditions:** Users authenticates O/C/D; Events identifies C as the assigned Coordinator.
- **Steps:** 1. GET review as C, D, O and anonymous. 2. Reassign E to D via S-84. 3. Repeat.
- **Test data:** Shared E/O/C/D and one pending request R.
- **Expected:** C initially sees accepted/proposed values and differences; D gets scoped 404, O cannot use Coordinator review, anonymous gets 401. After transfer only D may act; denied reads reveal no arrangement details.
- **Actual:** Current Coordinator review succeeded; unrelated and anonymous access was denied and reassignment changed scope.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s60.py::test_review_follows_current_assignment_without_exposing_other_coordinator_data; test_review_requires_coordinator_authentication

## TC-EVENTREQUESTS-301 — time changes identify scheduling impacts

- **Scenario:** New date, time or duration is checked against bookings, setup/turnaround, equipment availability and T's schedule.
- **Pre-conditions:** B1/B2 booked for the old window; availability APIs return B1 setup clash, B2 free at the proposed time, projector shortage and T overlap.
- **Steps:** Preview R and inspect item identities/reasons; include an unrelated event's booking B3.
- **Test data:** 04 Dec 09:00–12:00 → 05 Dec 10:00–14:00; B1 clash, B2 free for the new slot but still booked at the old slot, projector short by 1.
- **Expected:** B1 flags its old-slot mismatch and setup clash; B2 flags the old-slot mismatch but is not falsely marked clashing. Projector and T have separate reasons; unrelated B3 is absent. An unavailable owner returns a controlled `502`, never a false clearance. Nothing is cancelled.
- **Actual:** Per-booking old-window and clash reasons were distinguished; live equipment and Technical Support schedules were checked.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s60.py::test_time_change_flags_each_old_booking_but_only_real_clash; test_time_change_revalidates_live_equipment_and_technical_schedule

## TC-EVENTREQUESTS-302 — attendance flags capacity and safety

- **Scenario:** A pax increase identifies affected venues and applicable safety limits.
- **Pre-conditions:** B1 capacity 130, B2 capacity 220; the safety-review rules require fresh consideration when attendance changes.
- **Steps:** Preview 120→150; inspect each impact.
- **Test data:** Capacities 130/220; proposed pax 150.
- **Expected:** B1 flags `130 < 150`, B2 has no capacity mismatch, and an independent attendance/safety review item explains why the prior safety decision cannot be reused. Existing approvals remain in history. No numeric safety limit is assumed without a source.
- **Actual:** Only the undersized booking received the capacity flag; safety review was separately identified.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s60.py::test_attendance_and_layout_impacts_are_booking_specific

## TC-EVENTREQUESTS-303 — venue suitability is booking-specific

- **Scenario:** Layout, access, facilities and restrictions are compared with each live booking's venue.
- **Pre-conditions:** B1 supports theatre only/no hearing loop; B2 supports banquet/hearing loop.
- **Steps:** Preview proposed banquet layout plus hearing loop; inspect B1/B2.
- **Test data:** B1/B2 above; proposed `banquet`, `hearing_loop`.
- **Expected:** B1 receives both explicit deficits; B2 is not incorrectly flagged. Missing venue metadata yields a controlled owner error, not a claimed compatibility result. Both bookings and primary selection remain untouched.
- **Actual:** Facilities, accessibility and layout were assessed for each booking, with no B2 false flag.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s60.py::test_facilities_and_access_are_assessed_for_each_booking; test_attendance_and_layout_impacts_are_booking_specific

## TC-EVENTREQUESTS-304 — live Equipment is revalidated

- **Scenario:** The proposal's equipment snapshot cannot overrule a later catalogue or availability change.
- **Pre-conditions:** R proposes projector 2→3; live item is retired or only 2 are available at review time.
- **Steps:** Preview R, alter fake live Equipment response, attempt acceptance, inspect owners.
- **Test data:** P quantity 2→3; status `retired` or available quantity 2.
- **Expected:** A retired changed item is rejected by Equipment with `409` and no accepted outcome. A live item with a quantity shortage is identified as an outstanding impact; acceptance may proceed with the flag, but the flag cannot be resolved until the owner-backed shortage is addressed and a fresh Technical Support decision is recorded. Unchanged grandfathered requirements keep S-59 behavior.
- **Actual:** Retired changed item was refused; a live quantity shortage remained an outstanding flag after acceptance.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s60.py::test_retired_changed_item_is_rejected_before_durable_prepare; test_live_equipment_shortage_can_be_accepted_with_outstanding_flag

## TC-EVENTREQUESTS-305 — equipment and Technical Support impacts are distinct

- **Scenario:** Changed requirement/preparation and old Technical Support sign-off are explained separately.
- **Pre-conditions:** P quantity 2 prepared; T approved P=2.
- **Steps:** Preview P 2→3, then unchanged P; read impacts and sign-off.
- **Test data:** P 2→3; T signed 2026-12-01T09:00Z.
- **Expected:** P has requirement/availability/preparation reason; T has its own old-sign-off review reason. Unchanged P is not flagged solely for existing. T's old approval remains visible and is never presented as approval for P=3.
- **Actual:** Equipment requirement and old Technical Support sign-off produced separate impacts; unchanged equipment did not gain a flag.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s60.py::test_time_change_revalidates_live_equipment_and_technical_schedule; test_unchanged_equipment_is_not_flagged_for_attendance_only

## TC-EVENTREQUESTS-306 — acceptance uses the owning services

- **Scenario:** Composite orchestration applies proposed values without direct cross-schema queries.
- **Pre-conditions:** C assigned; R pending/fresh; live checks pass; B1/B2/T exist.
- **Steps:** Accept R; inspect outbound calls and all owner records; retry same operation.
- **Test data:** Shared E/R; projector 2→3; idempotency key Q.
- **Expected:** Equipment's atomic batch changes P to 3; Events atomically finalises event fields, R, lifecycle, flags and history. B1/B2/T identities and authoritative sign-offs remain. The response reports accepted only after both owners' writes complete; retry returns one result.
- **Actual:** Composite used owner APIs; real acceptance changed Events and Equipment once while retaining bookings, sign-offs and attendee.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s60.py::test_acceptance_applies_equipment_before_events_and_never_reports_partial_success; tests/integration/composite/event_requests/test_s60.py::test_real_acceptance_preserves_arrangements

## TC-EVENTREQUESTS-307 — partial failure never looks successful

- **Scenario:** Failure before/after Equipment's write is durable and recoverable.
- **Pre-conditions:** R pending; Events or Equipment fake fails on a nominated call.
- **Steps:** 1. Fail Equipment before write. 2. Fail Events finalisation after Equipment batch. 3. Retry Q; try D replay.
- **Test data:** Q UUID, P 2→3, HTTP 503/timeout.
- **Expected:** No successful accepted response while incomplete; durable operation blocks conflicting edits/new requests, shows C recovery status, and safe retry commits once. D cannot replay. Compensation, if needed, uses saved Equipment version and cannot overwrite another actor's update.
- **Actual:** Failed finalisation/finish returned incomplete; persisted operation blocked new requests and same-key retry completed once.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s60.py::test_events_finalization_failure_keeps_operation_applying_until_same_retry_succeeds; test_equipment_finish_failure_returns_incomplete_until_idempotent_recovery; tests/integration/composite/event_requests/test_s60.py::test_real_concurrent_acceptance_and_recovery

## TC-EVENTREQUESTS-308 — resolution does not forge staff sign-off

- **Scenario:** C records actual venue/equipment re-review independently of Venue Staff/T's decisions.
- **Pre-conditions:** Accepted R has B1 and P flags, with old staff approvals preserved.
- **Steps:** 1. C sends a new booking request for the revised event and attempts clearance before approval. 2. Venue Staff approves B3 through the existing decision workflow. 3. C resolves B1 with B3 as evidence; T re-signs P before C resolves P.
- **Test data:** B1→B3, P=3, C note `Reviewed replacement`.
- **Expected:** Request/note alone cannot clear unmet flag; validated evidence references B3 or new T sign-off. Separate C reviewer/action/time are stored. B1 and P resolve independently; D cannot resolve.
- **Actual:** Coordinator could not forge staff approval; fresh Venue Staff and Technical Support actions supported independent durable resolution.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_requests/test_s60.py::test_impact_resolution_cannot_impersonate_technical_support; test_new_staff_approved_booking_resolves_old_booking_impact_with_trusted_evidence; tests/e2e/test_review_significant_event_changes.py::test_proposal_review_resolution_requires_fresh_safety_check[chromium]

## TC-EVENTREQUESTS-309 — rejection releases S-59's pending slot

- **Scenario:** C's reasoned rejection preserves history and allows O to revise.
- **Pre-conditions:** R pending; E accepted at 120 attendees.
- **Steps:** Reject R, submit R2, race another request while R2 is pending or applying.
- **Test data:** R 120→150 rejected; R2 120→130; blank reason invalid.
- **Expected:** R remains rejected with C/time/reason; E unchanged. One R2 can become pending only after R is terminal; concurrent duplicate gets 409; applying operation also occupies the one-outstanding slot.
- **Actual:** Rejection recorded the reason, kept accepted values, and released the one-pending slot only after persistence.
- **Status:** Pass
- **Evidence:** tests/integration/composite/event_requests/test_s60.py::test_rejection_releases_pending_slot_without_changing_accepted_event; test_real_concurrent_acceptance_and_recovery
