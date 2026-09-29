# Test cases — event_requests service (unit)

Covers `tests/unit/composite/event_requests/test_app.py`: the composite
service that stands between an event organiser and the `events`/`users`
atomic services for the one workflow that spans both entities — turning a
submission into an assigned event coordinator. Both outbound HTTP clients
(`get_events_client`, `get_users_client`) are faked; no network, database, or
Docker.

| | |
| --- | --- |
| Suite | `pytest tests/unit/composite/event_requests` |
| Last run | 2026-09-29, branch `S-43/auto-assign-technical-support`, pre-commit working tree |
| Environment | Python 3.12.4, pytest 9.1.1, FastAPI 0.141.1, Pydantic 2.13.5, httpx 0.28.1, supabase-py 2.31.0; no network, database, or Docker |
| Result | 47 passed in this suite; 509 passed across `tests/unit` |

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
