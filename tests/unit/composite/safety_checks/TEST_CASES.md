# S-86 Safety Checks — Unit Test Cases

Story: S-86 Conduct Operational Safety Check. Acceptance criteria and cases
confirmed by the developer on 2026-10-10. Latest execution: not yet executed.

## TC-SAFETYCHECKS-001 — Safety Officer authorization

- **Pre-conditions:** Users returns an authenticated `safety_officer`, another
  recognized role, or `401`.
- **Steps:** Request the queue for each identity.
- **Expected:** Safety Officer proceeds; anonymous gets `401`; every other role
  gets `403`; denied requests make no Events call.
- **Actual:** Not executed.
- **Status:** Not Executed
- **Evidence:** `test_app.py::test_only_safety_officers_can_access_queue`

## TC-SAFETYCHECKS-002 — confirmed undecided queue and empty state

- **Pre-conditions:** Events returns its atomic safety-review source, then an
  empty source; Users supplies organiser profiles when needed.
- **Steps:** List safety checks in both states.
- **Test data:** One `confirmed` event with null safety decision.
- **Expected:** The enriched summary is returned; empty storage becomes `[]`.
- **Actual:** Not executed.
- **Status:** Not Executed
- **Evidence:** `test_app.py::test_queue_returns_only_events_selected_by_confirmed_undecided_source`; `test_app.py::test_empty_queue_is_an_empty_list`

## TC-SAFETYCHECKS-003 — complete operational-safety evidence

- **Pre-conditions:** Events, profiles, Bookings, Venues and Equipment return
  one complete planned event.
- **Steps:** Open its safety-check detail.
- **Expected:** Identity, organiser, attendance, schedule, confirmed venue,
  capacity, layout, accessibility, restrictions, technical assignment/notes,
  equipment requirements and special requirements are exposed.
- **Actual:** Not executed.
- **Status:** Not Executed
- **Evidence:** `test_app.py::test_detail_enriches_event_organiser_venues_technical_support_and_equipment`

## TC-SAFETYCHECKS-004 — verified Safety Officer and all three transitions

- **Pre-conditions:** The authenticated profile has id D; Events accepts each
  decision.
- **Steps:** Submit approval, rejection with reason and changes requested with
  reason.
- **Expected:** The browser cannot choose the officer id; the composite sends
  verified D. Results are `preparation`, `safety_rejected`, and
  `safety_changes_requested` respectively.
- **Actual:** Not executed.
- **Status:** Not Executed
- **Evidence:** `test_app.py::test_decision_forwards_verified_officer_and_returns_transition`

## TC-SAFETYCHECKS-005 — identified and upstream failures remain controlled

- **Pre-conditions:** Events returns `404`, `409`, or `422`; each enrichment
  dependency fails in turn.
- **Steps:** Submit/open the affected review.
- **Expected:** Identified statuses and details are preserved; dependency
  failures return `502`; a failed read never calls the decision write.
- **Actual:** Not executed.
- **Status:** Not Executed
- **Evidence:** `test_app.py::test_identified_event_errors_are_preserved`; `test_app.py::test_detail_dependency_failures_are_controlled_and_never_write`

