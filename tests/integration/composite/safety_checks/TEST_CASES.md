# S-86/S-87 Safety Checks — Integration Test Cases

Stories: S-86 Conduct Operational Safety Check and S-87 Return Event to
Planning After Safety Changes Requested. Specifications confirmed by the
developer on 2026-10-10. Latest execution: 2026-10-13, branch
`S-87/return-event-to-planning-after-safety-changes-requested`, working tree
based on commit `72886bb`; freshly recreated `.env.test` stack verified against
the test Supabase project. Both S-86/S-87 cases passed, and the combined
S-77/S-87 targeted integration regression run passed all 8 cases.

## TC-SAFETYCHECKS-101 — enriched review and atomic approval through Kong

- **Scenario:** A Safety Officer reviews a fully planned event and records the
  first Operational Safety Check decision.
- **Pre-conditions:** A fresh `.env.test` stack; Events S-86 SQL applied and
  exposed/granted; a `confirmed` undecided event with organiser, Coordinator,
  Technical Support, confirmed booking and venue, and equipment requirement.
- **Steps:** Sign in as `safety_officer`; list the queue; open the event; approve
  it; repeat with a different decision; inspect `events.events` through the
  test project admin client.
- **Test data:** 120 attendees; theatre venue capacity 200; wheelchair access;
  emergency-exit restriction; four microphones; approval followed by a stale
  rejection attempt.
- **Expected:** Queue and detail are enriched through Kong; approval stores
  `preparation`, `approved`, Safety Officer and server timestamp atomically;
  the repeated decision returns `409` and does not overwrite the approval.
- **Actual:** The enriched queue and detail were served through Kong; approval
  stored `preparation`, `approved`, the authenticated Safety Officer and a
  server timestamp. A second decision returned `409`, and the approval
  remained unchanged.
- **Status:** Pass
- **Evidence:** `test_app.py::test_safety_officer_reviews_enriched_event_and_approves`

## TC-SAFETYCHECKS-102 — changes, planning, resubmission and fresh approval

- **Scenario:** A real cross-service cycle returns an event for safety changes,
  preserves arrangements, resubmits it and records a fresh approval.
- **Pre-conditions:** Fresh `.env.test` stack with S-87 Events SQL; assigned
  Coordinator, Safety Officer, confirmed booking, equipment requirement and
  Technical Support assignment.
- **Steps:** Request changes; read feedback as the Coordinator; resubmit;
  inspect the S-86 queue; approve as Safety Officer; inspect Events, Bookings
  and Equipment storage.
- **Expected:** The path is `confirmed → planning → confirmed → preparation`.
  The first review remains in history, current feedback clears on resubmit,
  the event re-enters the queue, fresh approval appends review 2, and resource
  rows remain unchanged.
- **Actual:** The change request returned the event to `planning` with its
  feedback and first review intact. Resubmission changed it to `confirmed`,
  cleared the current blocking decision without deleting history, and put it
  back in the S-86 queue. Fresh approval produced `preparation` and review 2;
  the booking, equipment requirement and Technical Support assignment were
  unchanged.
- **Status:** Pass
- **Evidence:** `test_app.py::test_changes_return_to_planning_and_complete_a_fresh_review_cycle`

## TC-SAFETYCHECKS-103 — blocked, arranged, submitted, approved, Confirmed

> TC-SAFETYCHECKS-101 and -102 now start from `pending_safety_check` and end
> at `confirmed` (S-17); their path is `pending_safety_check → planning →
> pending_safety_check → confirmed`.

- **Scenario:** The whole S-17 stage across real services.
- **Pre-conditions:** Fresh `.env.test` stack with the S-17 SQL; Organiser,
  assigned Coordinator, Technical Support, Venue Staff and Safety Officer
  accounts; `E1` in `planning` with one equipment requirement and one
  `pending` booking.
- **Steps:** 1. Submit as the Coordinator. 2. Venue Staff confirm the
  booking; Technical Support approves and sets preparation `ready`.
  3. Submit again. 4. Read the S-86 queue as the Safety Officer. 5. Approve.
  6. Read `E1` as the Organiser. 7. Delete everything created.
- **Test data:** As above.
- **Expected:** 1 → `409` listing `venue_missing`, `venue_awaiting`,
  `technical_signoff_awaiting`, `equipment_preparation` (the booking is only
  pending, so no venue is confirmed yet -- TC-SAFETYCHECKS-012); storage still
  `planning`. 3 → `200`, stored `pending_safety_check`. 4 lists `E1`.
  5 → stored `confirmed`. 6 → `status: "confirmed"`.
- **Actual:** Passed on 2026-10-19 against a fresh `.env.test` stack with the S-17 SQL applied: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_submission_through_to_confirmed`

---

## S-82 — View Event Change History

## TC-SAFETYCHECKS-104 — the Safety Officer sees the safety review's history and nothing else

- **Scenario:** Through the real services, a safety decision and an attendance edit are visible to the Safety Officer; the submission, assignment and contact edit are not (S-82 AC1, AC3).
- **Pre-conditions:** Fresh `.env.test` stack; S-82 SQL applied. Through the admin client: Organiser O, Coordinator C, Safety Officer S; event E `planning`, assigned to C, ready for the safety check as in `test_s17.py`.
- **Steps:**
  1. As C, `PATCH /events/assigned/E` changing `contact_phone` to `91234567`.
  2. As C, `PATCH /events/assigned/E` changing `expected_attendance` 40→60, with `impact_accepted: true`.
  3. As C, `POST /safety-checks/coordinator/events/E/submit`.
  4. As S, `POST /safety-checks/E/decision` with `{"decision": "changes_requested", "reason": "Fire exit blocked"}`.
  5. As S, `GET /safety-checks/E/history`.
  6. Delete everything created.
- **Test data:** Emails `spm-test-*`.
- **Expected:** 5 → `200` with exactly three entries, newest first: `safety_changes_requested` by S (`details.reason` "Fire exit blocked"), `safety_submitted` by C, and `edited` by C with `details.changes` holding only `expected_attendance` `{from: 40, to: 60}`. The `contact_phone` edit is absent.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** tests/integration/composite/safety_checks/test_s82.py::test_the_safety_officer_sees_the_safety_history
