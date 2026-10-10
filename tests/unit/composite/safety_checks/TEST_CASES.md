# S-86 Safety Checks — Unit Test Cases

Story: S-86 Conduct Operational Safety Check. Acceptance criteria and cases
confirmed by the developer on 2026-10-10. Executed locally on 2026-10-10.

## TC-SAFETYCHECKS-001 — Safety Officer authorization

- **Pre-conditions:** Users returns an authenticated `safety_officer`, another
  recognized role, or `401`.
- **Steps:** Request the queue and submit a decision for each identity.
- **Expected:** Safety Officer proceeds; anonymous gets `401`; every other role
  gets `403`; denied requests make no Events call.
- **Actual:** Queue and decision both accepted only Safety Officer; anonymous
  returned `401`, other roles `403`, with no Events call.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_safety_officers_can_access_queue`; `test_app.py::test_only_safety_officers_can_submit_decisions`

## TC-SAFETYCHECKS-002 — confirmed undecided queue and empty state

- **Pre-conditions:** Events returns its atomic safety-review source, then an
  empty source; Users supplies organiser profiles when needed.
- **Steps:** List safety checks in both states.
- **Test data:** One `confirmed` event with null safety decision.
- **Expected:** The enriched summary is returned; empty storage becomes `[]`.
- **Actual:** The confirmed undecided source was enriched with organiser; an
  empty source returned `[]` without profile lookup.
- **Status:** Pass
- **Evidence:** `test_app.py::test_queue_returns_only_events_selected_by_confirmed_undecided_source`; `test_app.py::test_empty_queue_is_an_empty_list`

## TC-SAFETYCHECKS-003 — complete operational-safety evidence

- **Pre-conditions:** Events, profiles, Bookings, Venues and Equipment return
  one complete planned event.
- **Steps:** Open its safety-check detail.
- **Expected:** Identity, organiser, attendance, schedule, confirmed venue,
  capacity, layout, accessibility, restrictions, technical assignment/notes,
  equipment requirements and special requirements are exposed.
- **Actual:** Detail contained every confirmed evidence group and mapped venue
  description to the explicit restrictions field.
- **Status:** Pass
- **Evidence:** `test_app.py::test_detail_enriches_event_organiser_venues_technical_support_and_equipment`

## TC-SAFETYCHECKS-004 — verified Safety Officer and all three transitions

- **Pre-conditions:** The authenticated profile has id D; Events accepts each
  decision.
- **Steps:** Submit approval, rejection with reason and changes requested with
  reason.
- **Expected:** The browser cannot choose the officer id; the composite sends
  verified D. Results are `preparation`, `safety_rejected`, and
  after the S-87 clarification, `planning` respectively.
- **Actual:** All outcomes forwarded verified D; requested changes returned
  `planning`, while approval/rejection retained their S-86 outcomes.
- **Status:** Pass
- **Evidence:** `test_app.py::test_decision_forwards_verified_officer_and_returns_transition`

## TC-SAFETYCHECKS-005 — identified and upstream failures remain controlled

- **Pre-conditions:** Events returns `404`, `409`, or `422`; each enrichment
  dependency fails in turn.
- **Steps:** Submit/open the affected review.
- **Expected:** Identified statuses and details are preserved; dependency
  failures return `502`; a failed read never calls the decision write.
- **Actual:** `404`/`409`/`422` were preserved; each dependency outage returned
  controlled `502`; failed enrichment made no write.
- **Status:** Pass
- **Evidence:** `test_app.py::test_identified_event_errors_are_preserved`; `test_app.py::test_detail_dependency_failures_are_controlled_and_never_write`

---

## S-87 — Coordinator return and safety resubmission

Story: S-87 Return Event to Planning After Safety Changes Requested.
Acceptance criteria and tests confirmed on 2026-10-10. Executed locally in
the full Python unit run: 876 passed, 17 skipped.

## TC-SAFETYCHECKS-007 — Coordinator-only returned-safety access

- **Steps:** Open returned detail and resubmit anonymously, as Organiser, as
  Safety Officer, as the assigned Coordinator, and as another Coordinator.
- **Expected:** Only `event_coordinator` passes role authorization, and the
  Events owner additionally limits the event to its current assignee. Other
  roles receive `401/403`; another Coordinator receives `404`.
- **Actual:** Anonymous and non-Coordinator roles were rejected before Events;
  the atomic owner hid another Coordinator's event with `404`.
- **Status:** Pass
- **Evidence:** `test_s87.py::test_only_event_coordinators_can_open_or_resubmit_returned_work`; `test_s87.py::test_other_coordinator_cannot_manage_event_not_assigned_to_them`

## TC-SAFETYCHECKS-008 — returned detail enriches immutable feedback

- **Pre-conditions:** The Events service returns a planning event with current
  `changes_requested` feedback and one history record.
- **Steps:** Open the Coordinator safety-return detail.
- **Expected:** It contains planning state, reason, decision time, complete
  history, and the Safety Officer profile resolved by Users.
- **Actual:** Returned detail contained planning state, feedback/time, full
  history and the resolved Safety Officer profile.
- **Status:** Pass
- **Evidence:** `test_s87.py::test_returned_detail_exposes_feedback_with_officer_identity`

## TC-SAFETYCHECKS-009 — verified Coordinator resubmits without partial orchestration

- **Steps:** Resubmit successfully; repeat with missing/stale Events responses
  and an Events transport failure.
- **Expected:** The composite forwards only the verified current Coordinator
  id. Success is `confirmed` with history retained; `404/409` are preserved;
  an upstream failure is `502` and the write is not retried.
- **Actual:** Verified Coordinator id was forwarded once; success retained
  history, identified errors passed through, and transport failure returned
  `502` without a retry.
- **Status:** Pass
- **Evidence:** `test_s87.py::test_resubmit_forwards_verified_current_coordinator_and_returns_confirmed`; `test_s87.py::test_return_and_resubmit_preserve_identified_atomic_errors`; `test_s87.py::test_upstream_failure_is_controlled_and_does_not_retry_a_write`
