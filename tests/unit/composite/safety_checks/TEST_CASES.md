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

> **S-17 (2026-10-19):** the queue is `pending_safety_check` events — see TC-SAFETYCHECKS-025.

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

> **S-17 (2026-10-19):** approval yields `confirmed`, not `preparation` — see TC-SAFETYCHECKS-025.

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
Acceptance criteria and tests confirmed on 2026-10-10. Executed locally on
2026-10-13 at commit `72886bb` in the full Python unit run: 981 passed,
17 skipped.

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

> **S-17 (2026-10-19):** resubmission first runs the S-17 readiness check and succeeds as `pending_safety_check` — see TC-SAFETYCHECKS-023.

- **Steps:** Resubmit successfully; repeat with missing/stale Events responses
  and an Events transport failure.
- **Expected:** The composite forwards only the verified current Coordinator
  id. Success is `confirmed` with history retained; `404/409` are preserved;
  an upstream failure is `502` and the write is not retried.
- **Actual:** Verified Coordinator id was forwarded once; success retained
  history, identified errors passed through, and transport failure returned
  `502` without a retry.
- **Status:** Pass
- **Evidence:** `test_s87.py::test_resubmit_forwards_verified_current_coordinator_and_returns_pending`; `test_s87.py::test_return_and_resubmit_preserve_identified_atomic_errors`; `test_s87.py::test_upstream_failure_is_controlled_and_does_not_retry_a_write`

## S-17 — submit an event for the Operational Safety Check

`POST /safety-checks/coordinator/events/{event_id}/submit` checks every
mandatory arrangement and, only if none is outstanding, moves the event to
`pending_safety_check`. `GET .../readiness` returns the same check without
writing, so the page can list outstanding items before the Coordinator
tries. S-87's resubmit runs the identical check. Events, Bookings, Venues and
Equipment are faked; every case asserts whether the Events write was called.

**Venue approved:** at least one `confirmed` booking, and none `pending`,
`held`, or `rejected` (a rejected booking stops counting only once a
replacement is confirmed and it becomes `replaced`), and no `confirmed`
booking carries an unresolved S-77 unavailability flag.

**Equipment / technical support arranged** — only when the event has at least
one equipment requirement or `technical_support_required: true`: Technical
Support is assigned, the sign-off is `approved`, and
`equipment_preparation_status` is `ready`.

Each outstanding item is `{"code", "label", "booking_id"?}`:

| code | label |
| --- | --- |
| `venue_missing` | No venue booking has been confirmed yet |
| `venue_awaiting` | {venue} on {date} is waiting for Venue Staff |
| `venue_rejected` | {venue} on {date} was rejected — request a replacement venue |
| `venue_unavailable` | {venue} on {date} is affected by an unavailable period — replace it or record alternative arrangements |
| `technical_support_unassigned` | Technical Support has not been assigned |
| `technical_signoff_awaiting` | Technical Support has not approved the equipment arrangements |
| `technical_signoff_declined` | Technical Support declined: {reason} |
| `equipment_preparation` | Equipment preparation is {Not Started / In Progress} |

Shared test data: event `E1` (`planning`, assigned to Coordinator `C1`, date
`2026-11-20`); bookings `B1` Hall A, `B2` Studio 2, `B3` Room 5, all on
`2026-11-20`; one equipment requirement (2 × Projector) unless stated.

## TC-SAFETYCHECKS-010 — everything arranged: the event moves to Pending Safety Check

- **Scenario:** A fully arranged event is submitted.
- **Pre-conditions:** `B1` `confirmed`, no flag; no other bookings; Technical
  Support `T1` assigned; sign-off `approved`; preparation `ready`.
- **Steps:** `POST /safety-checks/coordinator/events/E1/submit` as `C1`.
- **Test data:** As above.
- **Expected:** `200`, body `status == "pending_safety_check"`. Events
  `POST /internal/events/E1/safety-submission` called once with
  `{"coordinator_id": C1}`. No call writes to Bookings or Equipment.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_fully_arranged_event_moves_to_pending_safety_check`

## TC-SAFETYCHECKS-011 — no equipment and no support required: venue alone is enough

- **Scenario:** An event that needs no technical sign-off is submitted on its venue alone.
- **Pre-conditions:** `B1` `confirmed`; no equipment requirements;
  `technical_support_required: false`; no Technical Support assigned;
  sign-off null; preparation `not_started`.
- **Steps:** Submit as `C1`.
- **Test data:** As above.
- **Expected:** `200`, `pending_safety_check`; the Technical Support items are
  not checked.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_venue_only_event_needs_no_technical_signoff`

## TC-SAFETYCHECKS-012 — no confirmed venue

- **Scenario:** An event with no confirmed booking cannot be submitted.
- **Pre-conditions:** Technical side complete; bookings: none.
- **Steps:** Submit as `C1`.
- **Test data:** As above.
- **Expected:** `409`, body `{"detail": "This event has outstanding
  arrangements", "outstanding": [{"code": "venue_missing", ...}]}`. Events
  write not called.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_no_confirmed_venue_is_outstanding`

## TC-SAFETYCHECKS-013 — a booking still with Venue Staff is outstanding

- **Scenario:** A booking still with Venue Staff blocks submission.
- **Pre-conditions:** Technical side complete; `B1` `confirmed`, `B2`
  `pending`, `B3` `held`.
- **Steps:** Submit as `C1`.
- **Test data:** As above.
- **Expected:** `409`; `outstanding` is exactly two `venue_awaiting` items
  with `booking_id` `B2` and `B3`, labels "Studio 2 on 20 Nov 2026 is waiting
  for Venue Staff" and "Room 5 on 20 Nov 2026 is waiting for Venue Staff".
  No write.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_pending_and_held_bookings_are_outstanding`

## TC-SAFETYCHECKS-014 — one rejected booking keeps the event in Planning

- **Scenario:** A rejection blocks submission without disturbing anything else.
- **Pre-conditions:** Technical side complete; `B1` `confirmed`; `B2`
  `rejected` with reason "Double-booked".
- **Steps:** 1. Submit as `C1`. 2. Read the event and the bookings.
- **Test data:** As above.
- **Expected:** 1 → `409`, `outstanding` is one `venue_rejected` item with
  `booking_id: B2`. 2 → no Events, Bookings or Equipment write was made: the
  event is still `planning` and `B1` is still `confirmed` on `E1`.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_rejected_booking_keeps_event_in_planning`

## TC-SAFETYCHECKS-015 — a rejected booking stops counting once replaced

- **Scenario:** A rejection stops blocking once its replacement is confirmed.
- **Pre-conditions:** Technical side complete; `B1` `confirmed`.
- **Steps:** Submit as `C1` with each booking set:
  (a) `B2` `rejected`, replacement `B3` `pending` with
  `replaces_booking_id: B2`;
  (b) `B2` `replaced` (`replaced_by_booking_id: B3`), `B3` `confirmed`.
- **Test data:** As above.
- **Expected:** (a) `409`, outstanding is `venue_rejected` for `B2` **and**
  `venue_awaiting` for `B3`. (b) `200`, `pending_safety_check`.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_rejected_booking_cleared_by_confirmed_replacement`

## TC-SAFETYCHECKS-026 — a rejected replacement request is not counted twice

> Added during implementation and confirmed by the developer (2026-10-19):
> without it, a replacement request Venue Staff reject would block
> submission for good, since a replacement request cannot itself be
> replaced. The original rejection still blocks until a replacement for it
> is confirmed.

- **Scenario:** Only the booking a rejected replacement was for stays outstanding.
- **Pre-conditions:** Technical side complete; `B1` `confirmed`; `B2`
  `rejected`; `B3` `rejected` with `replaces_booking_id: B2`.
- **Steps:** 1. Submit as `C1`. 2. Set `B2` to `replaced` (a later
  replacement was confirmed), `B3` unchanged; submit again.
- **Test data:** As above.
- **Expected:** 1 → `409`, outstanding is exactly `venue_rejected` for `B2`.
  2 → `200`, `pending_safety_check`.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_rejected_replacement_request_does_not_count_again`

## TC-SAFETYCHECKS-016 — an unresolved unavailability flag blocks; a resolved one doesn't

- **Scenario:** An S-77 flag on a confirmed booking blocks until it is replaced or resolved.
- **Pre-conditions:** Technical side complete; `B1` `confirmed`. Block `K1`
  on Hall A, `2026-11-20 09:00–17:00`, created `2026-11-01T10:00Z`.
- **Steps:** Submit as `C1` with (a) `B1` overlapping `K1`, no resolution;
  (b) same with `alternative_resolved_at: 2026-11-02T09:00Z`; (c) as (b) plus
  a second block `K2` created `2026-11-03T10:00Z` overlapping `B1`.
- **Test data:** As above.
- **Expected:** (a) `409`, one `venue_unavailable` item for `B1`. (b) `200`.
  (c) `409`, `venue_unavailable` for `B1` — a period created after the
  resolution flags it again (S-78's rule).
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_unavailability_flag_blocks_until_resolved`

## TC-SAFETYCHECKS-017 — sign-off needed but nobody assigned

- **Scenario:** An event needing sign-off with no Technical Support assigned is blocked.
- **Pre-conditions:** `B1` `confirmed`; one equipment requirement; no
  Technical Support assigned; sign-off null; preparation `not_started`.
- **Steps:** Submit as `C1`. Repeat with no requirements but
  `technical_support_required: true`.
- **Test data:** As above.
- **Expected:** Both → `409`; outstanding is `technical_support_unassigned`,
  `technical_signoff_awaiting`, `equipment_preparation` (label "Equipment
  preparation is Not Started"), in that order. No write.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_signoff_needed_without_support_assigned`

## TC-SAFETYCHECKS-018 — sign-off awaiting or declined

- **Scenario:** Only an approved sign-off counts; an override comment does not weaken it.
- **Pre-conditions:** `B1` `confirmed`; `T1` assigned; preparation `ready`.
- **Steps:** Submit as `C1` with sign-off (a) null; (b) `declined`, reason
  "Only one sound desk exists"; (c) `approved` with override comment
  "Borrowing 2 projectors from Library".
- **Test data:** As above.
- **Expected:** (a) `409`, `technical_signoff_awaiting`. (b) `409`,
  `technical_signoff_declined` labelled "Technical Support declined: Only one
  sound desk exists". (c) `200` — an overridden approval is an approval.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_signoff_awaiting_or_declined_is_outstanding`

## TC-SAFETYCHECKS-019 — equipment preparation must be Ready

- **Scenario:** Preparation must be Ready when sign-off is needed.
- **Pre-conditions:** `B1` `confirmed`; `T1` assigned; sign-off `approved`.
- **Steps:** Submit with preparation `not_started`, then `in_progress`.
- **Test data:** As above.
- **Expected:** `409` each, one `equipment_preparation` item labelled
  "Equipment preparation is Not Started" / "… In Progress".
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_equipment_preparation_must_be_ready`

## TC-SAFETYCHECKS-020 — every outstanding item is listed at once

- **Scenario:** The Coordinator sees the whole list, not the first failure.
- **Pre-conditions:** `B2` `pending`, `B3` `rejected`, no confirmed booking;
  one equipment requirement; no Technical Support assigned.
- **Steps:** Submit as `C1`; then `GET
  /safety-checks/coordinator/events/E1/readiness`.
- **Test data:** As above.
- **Expected:** Submit → `409` with exactly six items: `venue_missing`,
  `venue_awaiting` (`B2`), `venue_rejected` (`B3`),
  `technical_support_unassigned`, `technical_signoff_awaiting`,
  `equipment_preparation`. Readiness → `200` `{"ready": false, "outstanding":
  [the same six]}`. Neither writes.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_every_outstanding_item_listed`; `test_s17.py::test_readiness_of_a_ready_event`

## TC-SAFETYCHECKS-021 — there is no override

- **Scenario:** Nothing a Coordinator sends bypasses the check.
- **Pre-conditions:** As TC-SAFETYCHECKS-014 (one rejected booking).
- **Steps:** Submit as `C1` with body `{"override": true}`, then
  `{"force": true, "outstanding": []}`.
- **Test data:** As above.
- **Expected:** `422` for any body (the route takes none); no Events write.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_submission_cannot_be_overridden`

## TC-SAFETYCHECKS-022 — only the assigned Coordinator, only from Planning

- **Scenario:** Nobody but the assigned Coordinator can submit, and only from Planning.
- **Pre-conditions:** `E1` assigned to `C1`, fully arranged.
- **Steps:** 1. Submit as Coordinator `C2` (not assigned). 2. Submit as an
  Event Organiser, a Technical Support user and a Safety Officer. 3. Submit as
  `C1` with `E1` `submitted`, `pending_safety_check`, `confirmed`.
  4. Submit with no session.
- **Test data:** `E1` otherwise fully arranged.
- **Expected:** 1 → `404`. 2 → `403`. 3 → `409` "This event is not in
  planning" before any readiness reads. 4 → `401`. No Events write in any.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_submission_limited_to_assigned_coordinator_in_planning`

## TC-SAFETYCHECKS-023 — S-87 resubmission runs the same check

- **Scenario:** A safety-returned event cannot skip the readiness check.
- **Pre-conditions:** `E1` `planning`, `safety_decision:
  "changes_requested"`.
- **Steps:** `POST /safety-checks/coordinator/events/E1/resubmit` as `C1` with
  (a) `B2` `rejected`, otherwise complete; (b) everything complete.
- **Test data:** As above.
- **Expected:** (a) `409` with the same body shape as TC-SAFETYCHECKS-014; the
  Events resubmit is not called. (b) `200`, `status ==
  "pending_safety_check"`, history retained.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_safety_resubmit_runs_the_same_check`

## TC-SAFETYCHECKS-024 — a failing dependency never submits

- **Scenario:** A dependency failure never results in a partial or unchecked submission.
- **Pre-conditions:** As TC-SAFETYCHECKS-010.
- **Steps:** Submit a fully arranged `E1` while each of Bookings, Venues,
  Equipment, Events (read) in turn returns `500` or times out.
- **Test data:** As TC-SAFETYCHECKS-010.
- **Expected:** `502` naming the service; the Events write is never called.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_dependency_failure_never_submits`

## TC-SAFETYCHECKS-025 — the queue and decisions follow the new stage

- **Scenario:** The S-86 queue and approval use `pending_safety_check` and `confirmed`.
- **Pre-conditions:** Events fake as described in Steps.
> Amends TC-SAFETYCHECKS-002, -004 and -009 for S-17.

- **Steps:** 1. List the queue with Events returning one
  `pending_safety_check` event. 2. Approve it as Safety Officer `S1`.
- **Test data:** As above.
- **Expected:** 1 lists it. 2 returns `status == "confirmed"` (not
  `preparation`).
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_queue_and_approval_use_new_stage`

---

## S-82 — View Event Change History

`test_s82.py`. `GET /safety-checks/{event_id}/history` returns the safety view
of an event's history (`scope=safety` from Events, TC-EVENTS-201) to any
Safety Officer, once the event has entered the Operational Safety Check
(developer decision 7a). An event has entered it when its status is
`pending_safety_check`, `safety_changes_requested`, `safety_rejected`,
`confirmed` or `preparation`, or when it has any `safety_review_history`. The
last case covers an event sent back to `planning` after a significant change.

**Shared test data.** Event E `11111111-1111-4111-8111-111111111111`
"Autumn Forum"; Safety Officer S `55555555-5555-4555-8555-555555555555`
"Sam Safety"; Coordinator C `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa` "Alex
Coordinator".

## TC-SAFETYCHECKS-027 — a Safety Officer reads the safety view

- **Scenario:** The Safety Officer sees attendance, venue, access and equipment changes and the safety decisions, with names (S-82 AC3).
- **Pre-conditions:** Signed in as S. E is `pending_safety_check`. Events `scope=safety` returns two entries: `edited` by C, changes `{"expected_attendance": {"before": 120, "after": 150}}`; `venue_confirmed` by Venue Staff `77777777-7777-4777-8777-777777777777` "Val Venue".
- **Steps:** `GET /safety-checks/E/history`.
- **Test data:** As above.
- **Expected:** `200` with `event_id`, `event_name: "Autumn Forum"`, both entries in order with `actor` `{id, name, role}` filled in, and `people`, the same shape as TC-EVENTREQUESTS-117. Events was called with `scope=safety`, never without it.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_a_safety_officer_reads_the_safety_view; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-SAFETYCHECKS-028 — only events that entered the safety check are shown

- **Scenario:** A Safety Officer cannot read the history of an event that has never reached them.
- **Pre-conditions:** Signed in as S.
- **Steps:** `GET /safety-checks/E/history` with E in each state below.
- **Test data / Expected:**
  | E | Response |
  | --- | --- |
  | `pending_safety_check`, `safety_changes_requested`, `safety_rejected`, `confirmed`, `preparation` | `200` |
  | `planning` with one `safety_review_history` record | `200` |
  | `planning` with none; `submitted`; `draft`; `rejected` | `404` "Event not found" |
  | No such event | `404` "Event not found" |

  The Events history read is never called on a `404`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_only_events_that_entered_the_safety_check_are_shown; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-SAFETYCHECKS-029 — only Safety Officers use this route

- **Scenario:** Other roles are turned away.
- **Pre-conditions:** E is `pending_safety_check`.
- **Steps / Test data / Expected:** No session → `401`. `event_coordinator`, `event_coordinator_lead`, `event_organiser`, `technical_support`, `venue_staff`, `attendee` → `403`. The Events history read is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_only_safety_officers_use_this_route; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-SAFETYCHECKS-030 — a service that does not answer is a 502

- **Scenario:** The safety view is never shown half-filled.
- **Pre-conditions:** As S; E `pending_safety_check`.
- **Steps / Test data / Expected:** Events history `500` or timeout → `502` "Events service unavailable"; Users profiles `500` → `502` "Users service unavailable".
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_a_service_that_does_not_answer_is_a_502; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## S-63 — Notify Organiser — Event Decisions and Changes

Drafted and confirmed by the developer on 2026-10-31 before implementation.

## TC-SAFETYCHECKS-031 — approval sends one combined safety-and-confirmation notice

- **Scenario:** Safety approval, which makes the event confirmed, is reported once rather than as two duplicate notices.
- **Pre-conditions:** An authorised Safety Officer; Events saves `approved` and returns the confirmed event and its Organiser.
- **Steps:** `POST /safety-checks/{id}/decision` with `approved`.
- **Expected:** One `safety_check_outcome` row says the Operational Safety Check was approved and the event is confirmed.
- **Actual:** Approval sent one combined outcome row stating that safety passed and the event is confirmed.
- **Status:** Pass
- **Evidence:** `test_app.py::test_decision_forwards_verified_officer_and_returns_transition`; 2026-10-31 full Python unit suite: 1735 passed, 17 skipped.

## TC-SAFETYCHECKS-032 — rejected and returned safety outcomes carry actionable comments

- **Scenario:** The Organiser can tell why the check failed and what needs attention.
- **Pre-conditions:** As TC-SAFETYCHECKS-031.
- **Steps:** Decide once as `rejected` and once as `changes_requested`, each with reason "Move emergency access equipment".
- **Expected:** One row per successful decision names the event and outcome, repeats the reason, and gives the appropriate action; stable decision data forms the deduplication key.
- **Actual:** Rejected and changes-requested outcomes included the saved reason, event, decision type and next action with a stable key.
- **Status:** Pass
- **Evidence:** `test_app.py::test_decision_forwards_verified_officer_and_returns_transition`; 2026-10-31 full Python unit suite: 1735 passed, 17 skipped.

## TC-SAFETYCHECKS-033 — no saved safety outcome means no notification

- **Scenario:** A refused or unavailable Events write cannot tell the Organiser that an outcome occurred.
- **Pre-conditions:** Events answers `409` or is unavailable.
- **Steps:** Attempt the decision.
- **Expected:** Existing error handling is preserved and Notifications is not called.
- **Actual:** Refused Events outcomes preserved their status and made no notification write; notification failures after a save returned controlled `502`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_identified_event_errors_are_preserved` and `test_a_notification_failure_is_controlled_after_the_safety_outcome_is_saved`; 2026-10-31 full Python unit suite: 1735 passed, 17 skipped.
---

## S-60 — Review Impact of Significant Changes (approved)

Source: Product Backlog row 63. Latest S-60 execution: 2026-11-01, `S-60/review-impact-of-significant-changes`, TEST Supabase and fresh `.env.test` Docker stack for integration/Chromium; local Python and frontend unit suites. See each case evidence. Full regression still has separate S-53 TEST SQL drift.

## TC-SAFETYCHECKS-300 — unresolved impacts block readiness and submission

- **Scenario:** An existing booking/sign-off cannot make a changed event ready while its re-review flags remain outstanding.
- **Pre-conditions:** E is planning after significant acceptance; ordinary venue/equipment/technical checks pass; Events returns unresolved B1 and P flags.
- **Steps:** 1. GET readiness. 2. POST first submission and S-87 resubmission. 3. Resolve B1 only; repeat. 4. Resolve P; repeat.
- **Test data:** B1 `capacity 130 < 150`, P `quantity 2→3`.
- **Expected:** Readiness names both flags; submit/resubmit get 409 with the same items. Resolving only B1 leaves P blocking. Once all flags and ordinary readiness checks clear, normal S-17/S-87 submission works. An Events flag-service error fails closed, never reports ready.
- **Actual:** Two outstanding impacts blocked readiness and submission; one remaining flag still blocked, and owner failure returned 502.
- **Status:** Pass
- **Evidence:** tests/unit/composite/safety_checks/test_s17.py::test_s60_unresolved_impact_blocks_both_readiness_and_submission; test_s60_impact_owner_failure_never_reports_ready; tests/e2e/test_review_significant_event_changes.py::test_proposal_review_resolution_requires_fresh_safety_check[chromium]

## TC-SAFETYCHECKS-301 — a stale Safety Officer decision cannot reconfirm

- **Scenario:** Acceptance during `pending_safety_check` invalidates the Safety Officer's old review.
- **Pre-conditions:** E pending at version 4; officer opened its old review; S-60 accepts a significant date change.
- **Steps:** Submit old approval, inspect E and safety history.
- **Test data:** 04 Dec→05 Dec; old expected review version 4.
- **Expected:** Old approval gets 409; E stays planning with recheck required and preserved historical decision entries. A fresh submission is possible only after outstanding impacts resolve.
- **Actual:** Pending review was superseded by acceptance; old event-version approval returned 409 and fresh safety required resolved impacts.
- **Status:** Pass
- **Evidence:** tests/integration/composite/event_requests/test_s60.py::test_significant_acceptance_requires_fresh_safety_for_each_lifecycle_state[pending_safety_check]; tests/unit/atomic/events/test_s86.py::test_old_safety_review_cannot_decide_new_event_version

## TC-SAFETYCHECKS-302 — routine S-18 edits retain existing readiness

- **Scenario:** Non-significant contact and note edits do not add S-60 items or reset safety state.
- **Pre-conditions:** E planning/confirmed with ordinary readiness satisfied, no S-60 flags.
- **Steps:** Apply S-18 phone/note edit; query readiness and decision state.
- **Test data:** Phone `+65 6123 4567`, note `Use east entrance`.
- **Expected:** No S-60 outstanding item and no new safety check; the existing S-17/S-86/S-87 rules remain unchanged.
- **Actual:** Routine S-18 edit added no S-60 flag; significant S-18 edit left safety blocked until re-review.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s60.py::test_routine_s18_edit_stays_available_without_service_token; tests/e2e/test_update_event_information.py::test_coordinator_updates_event_and_restarts_safety_lifecycle[chromium]
