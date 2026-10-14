# S-86 Safety Checks — Integration Test Cases

Story: S-86 Conduct Operational Safety Check. Specification confirmed by the
developer on 2026-10-10. Latest execution: 2026-10-10, branch
`S-86/conduct-operational-safety-check`, commit `49a0f8b`; freshly recreated
`.env.test` stack verified against the test Supabase project: 1 passed.

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
