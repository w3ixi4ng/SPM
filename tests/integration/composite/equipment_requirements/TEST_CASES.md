# Test cases — equipment_requirements composite (integration)

Story: S-40 Record Required Equipment.

| | |
| --- | --- |
| Suite | `pytest tests/integration/composite/equipment_requirements` |
| Last run | 2026-09-27, branch `S-40/record-required-equipment`, pre-commit working tree |
| Environment | `.env.test`, complete Docker stack, test Supabase project |
| Result | 2 passed, twice consecutively; 24 passed across full integration suite |

## TC-EQUIPMENTREQUIREMENTS-101 — assigned Coordinator records and edits; Technical Support reads

- **Pre-conditions:** `equipment.requirements` exists, is granted and exposed;
  a planning event is assigned to Coordinator A; an active available equipment
  item exists; Technical Support and Coordinator B also exist.
- **Steps:** Through Kong, Coordinator A records quantity `2`, changes it to
  `4`; inspect the table directly; Technical Support reads it; Coordinator A
  deletes it; verify cleanup.
- **Expected:** One relationship is created and updated in place. Its audit id
  is Coordinator A, Technical Support sees it, and deletion removes only that
  relationship.
- **Actual:** One row was created, updated from 2 to 4, visible with catalogue
  details to Technical Support, then deleted cleanly.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_records_edits_and_deletes_requirement_visible_to_support`

## TC-EQUIPMENTREQUIREMENTS-102 — reassignment ignores historical recorded-by audit data

- **Pre-conditions:** A requirement was recorded by Coordinator A, then the
  event's current assignment changes to Coordinator B while still planning.
- **Steps:** A attempts to edit; B edits through Kong; inspect the stored row.
- **Expected:** A receives `404`; B succeeds; quantity changes and
  `recorded_by_coordinator_id` becomes B. Authorization was based on Events,
  not the previous audit id.
- **Actual:** The former Coordinator received 404 after reassignment; the new
  Coordinator updated the row to 5 and replaced the audit id.
- **Status:** Pass
- **Evidence:** `test_app.py::test_reassignment_uses_current_assignment_not_recorded_by_audit`

## S-44 — check equipment availability

Story: S-44 Check equipment availability.
Confirmed by the developer on 2026-09-30. Not yet executed.

### TC-EQUIPMENTREQUIREMENTS-103 — the availability check through Kong reflects live events and requirements

- **Scenario:** The real services, the new events query and the gateway agree
  (AC2, AC3).
- **Pre-conditions:** A fresh `.env.test` stack. A Technical Support session.
  A new active, `available` item "spm-test S44 Mic {suffix}" with total 10.
  Events seeded directly: P `planning` 2026-11-12 10:00–11:00; C `confirmed`
  11:30–13:00; R `rejected` 10:00–11:00; B `planning` 12:00–13:00
  (back-to-back); requirements on the item: P 3, C 2, R 4, B 5.
- **Steps:**
  1. `GET /api/equipment-requirements/availability` for 2026-11-12
     09:00–12:00, `type=spm-test S44 Mic {suffix}`, `quantity=5`.
  2. Record a 1-unit requirement for a new `planning` event 09:00–10:00, then
     check again.
- **Expected:** Step 1: `reserved 5` (P + C; R rejected and B back-to-back are
  left out), `available 5`, `sufficient true`, reservations P and C only.
  Step 2: `reserved 6`, `available 4`, `sufficient false`. Cleanup deletes
  every event, requirement and item created.
- **Actual:** Through Kong: reserved 5 (planning + confirmed), available 5, sufficient true, reservations P and C only; after the extra 1-unit hold, reserved 6, available 4, sufficient false.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/equipment_requirements/test_availability.py::test_the_availability_check_through_kong_reflects_live_events_and_requirements`; `.env.test` stack recreated immediately before; events container verified on the test project's `SUPABASE_URL`; `pytest tests/integration/atomic/events/test_overlapping.py tests/integration/composite/equipment_requirements`: 4 passed.
