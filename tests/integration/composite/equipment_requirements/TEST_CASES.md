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
