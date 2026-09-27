# Test cases — equipment service (unit)

Stories: S-39 Add Equipment Item; S-40 Record Required Equipment.

These cases specify the equipment catalogue before its implementation. Supabase
and Auth are mocked; this suite makes no network or database calls.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/equipment` |
| Last run | 2026-09-27, branch `S-40/record-required-equipment`, pre-commit working tree |
| Environment | Unit test environment; Supabase and authentication mocked |
| Result | 40 passed |

## Shared test data

**Complete item:**

```json
{
  "type": "Wireless Microphone",
  "description": "Handheld wireless microphone with receiver",
  "total_quantity": 12
}
```

The authenticated creator is user
`11111111-1111-4111-8111-111111111111` with trusted
`app_metadata.role=technical_support`. The stored item id is
`22222222-2222-4222-8222-222222222222`.

## TC-EQUIPMENT-001 — valid catalogue input is normalized

- **Scenario:** Required and optional text is normalized before storage.
- **Pre-conditions:** None.
- **Steps:** Validate the complete item with surrounding whitespace in both
  text fields.
- **Test data:** Complete item; `type="  Wireless Microphone  "` and a padded
  description.
- **Expected:** Whitespace is stripped, quantity remains `12`, and no status,
  id, creator or timestamp can be supplied by the client.
- **Actual:** Text was normalized and protected fields were rejected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_valid_item_is_normalized_and_server_fields_are_forbidden`

## TC-EQUIPMENT-002 — required fields and positive whole quantity are enforced

- **Scenario:** An unusable catalogue item never reaches storage.
- **Pre-conditions:** None.
- **Steps:** Submit, in turn, an omitted type, a blank type, an omitted
  quantity, `0`, `-1`, and `1.5`.
- **Test data:** The complete item with each invalid value above.
- **Expected:** Every request returns `422`, identifying `type` or
  `total_quantity`; Supabase is never called.
- **Actual:** Every invalid value returned `422`; storage was not called.
- **Status:** Pass
- **Evidence:** `test_app.py::test_invalid_create_never_calls_storage` and the invalid-input cases in `test_schemas.py`

## TC-EQUIPMENT-003 — Technical Support creates an active, available item

- **Scenario:** A valid item is added to the catalogue with server-owned
  defaults.
- **Pre-conditions:** Auth resolves to the shared Technical Support user; the
  insert returns the stored row.
- **Steps:** `POST /equipment` with the complete item.
- **Test data:** Complete item.
- **Expected:** `201`; insert targets `equipment.equipment`, derives
  `created_by` from the session, sets `operational_status="available"` and
  `lifecycle_status="active"`, and returns the generated id and timestamps.
- **Actual:** Creation returned `201` with the derived creator and both defaults.
- **Status:** Pass
- **Evidence:** `test_app.py::test_technical_support_creates_an_active_available_item`

## TC-EQUIPMENT-004 — only Technical Support can create catalogue items

- **Scenario:** Trusted role metadata protects catalogue mutation.
- **Pre-conditions:** One authenticated user for each other recognized role.
- **Steps:** As each user, `POST /equipment` with the complete item.
- **Test data:** `event_organiser`, `event_coordinator`, `venue_staff`, and
  `attendee`.
- **Expected:** Every request returns `403`; Supabase is never called.
- **Actual:** All four non-Technical-Support roles received `403`; storage was untouched.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_technical_support_can_create`

## TC-EQUIPMENT-005 — creation requires a valid session

- **Scenario:** An anonymous or expired browser cannot add equipment.
- **Pre-conditions:** No usable access or refresh cookie.
- **Steps:** `POST /equipment` with the complete item.
- **Test data:** Complete item.
- **Expected:** `401 {"detail":"Not authenticated"}`; Supabase is not called.
- **Actual:** The anonymous request returned the specified `401`; storage was untouched.
- **Status:** Pass
- **Evidence:** `test_app.py::test_create_requires_a_session`

## TC-EQUIPMENT-006 — Technical Support sees the complete catalogue

- **Scenario:** Catalogue management includes every current item, ready for
  later update and retirement stories.
- **Pre-conditions:** Storage returns an active available microphone and an
  active maintenance projector.
- **Steps:** As Technical Support, `GET /equipment`.
- **Test data:** The two rows above.
- **Expected:** `200`; both rows are returned ordered by type.
- **Actual:** Both records were returned from an ordered catalogue query.
- **Status:** Pass
- **Evidence:** `test_app.py::test_technical_support_lists_the_complete_catalogue`

## TC-EQUIPMENT-007 — selection data contains only active, available items

- **Scenario:** Requirement forms receive usable options rather than the
  management catalogue.
- **Pre-conditions:** Storage returns the active available microphone when
  filtered by both statuses.
- **Steps:** As Event Coordinator, `GET /equipment/selection`.
- **Test data:** `operational_status="available"`,
  `lifecycle_status="active"`.
- **Expected:** `200`; the service queries both filters, orders by type, and
  returns the microphone.
- **Actual:** Selection queried both status filters and returned the usable item.
- **Status:** Pass
- **Evidence:** `test_app.py::test_workflow_roles_list_active_available_selection`

## TC-EQUIPMENT-008 — only equipment-workflow roles can read catalogue data

- **Scenario:** Each read surface has the minimum role access needed.
- **Pre-conditions:** Authenticated recognized roles.
- **Steps:** Try `GET /equipment` and `GET /equipment/selection` as each role.
- **Test data:** Technical Support, Event Coordinator, Event Organiser, Venue
  Staff, and Attendee.
- **Expected:** Only Technical Support can read `/equipment`. Technical
  Support, Event Coordinator, and Event Organiser can read `/selection` while
  Venue Staff and Attendee receive `403`.
- **Actual:** Catalogue and selection access matched the specified role matrix.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_technical_support_reads_management_catalogue`, `test_app.py::test_unrelated_roles_cannot_read_selection`

## TC-EQUIPMENT-009 — unknown roles fail closed

- **Scenario:** Missing or unrecognized trusted roles receive no equipment
  permission.
- **Pre-conditions:** Auth succeeds with no role, then with role `admin`.
- **Steps:** Call both catalogue endpoints and creation.
- **Test data:** `null` and `admin` roles.
- **Expected:** Every request returns `403 {"detail":"Recognized role required"}`;
  storage is untouched.
- **Actual:** Both missing and unknown roles received the safe `403`; storage was untouched.
- **Status:** Pass
- **Evidence:** `test_app.py::test_unknown_roles_fail_closed`

## TC-EQUIPMENT-010 — storage failures are safe

- **Scenario:** Database details never leak to callers.
- **Pre-conditions:** Insert and list execution raise `connection refused`.
- **Steps:** Create and list equipment.
- **Test data:** Complete item.
- **Expected:** Each operation returns `500` with
  `{"detail":"Equipment storage unavailable"}` and does not expose the
  underlying exception.
- **Actual:** Both failures returned the safe storage message without exception details.
- **Status:** Pass
- **Evidence:** `test_app.py::test_storage_failures_are_safe`

## TC-EQUIPMENT-011 — health is independent of storage and authentication

- **Scenario:** Compose can determine whether the process is alive.
- **Pre-conditions:** None.
- **Steps:** `GET /health`.
- **Test data:** None.
- **Expected:** `200 {"status":"ok"}` without authentication or Supabase.
- **Actual:** Health returned the specified response without storage access.
- **Status:** Pass
- **Evidence:** `test_app.py::test_health_needs_no_storage_or_session`

## S-40 — equipment requirement storage

## TC-EQUIPMENT-012 — requirement input requires identifiers and positive quantity

- **Scenario:** Invalid relationships never reach Supabase.
- **Test data:** Missing/malformed event or item UUID; quantity missing, `0`,
  `-1`, or `1.5`; unknown fields.
- **Expected:** Schema validation fails with the relevant field.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py` / `test_schemas.py`

## TC-EQUIPMENT-013 — upsert creates or edits one event-item relationship

- **Scenario:** The same item is recorded once per event and later edits do
  not duplicate it.
- **Pre-conditions:** Storage returns the upserted row with catalogue details.
- **Steps:** Upsert quantity `6`, then `9`, for the same event and item.
- **Expected:** Storage targets `equipment.requirements` with conflict key
  `(event_id,equipment_item_id)` and returns the relationship.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py` / `test_schemas.py`

## TC-EQUIPMENT-014 — recorded-by is mutable audit information

- **Scenario:** A new authorized write updates who last recorded the value.
- **Pre-conditions:** Existing row says Coordinator A; request body says B.
- **Steps:** Upsert a new quantity as B.
- **Expected:** The row's `recorded_by_coordinator_id` becomes B; this atomic
  service does not use that field to decide authorization.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py` / `test_schemas.py`

## TC-EQUIPMENT-015 — requirements list carries catalogue details

- **Scenario:** Consumers can show type, description, quantity, and statuses
  without querying another service or schema.
- **Steps:** List all requirements, then filter by event id.
- **Expected:** Results are ordered by creation time and embed the referenced
  row from `equipment.equipment`; the event filter is applied when provided.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py` / `test_schemas.py`

## TC-EQUIPMENT-016 — deleting one requirement preserves every other relationship

- **Pre-conditions:** One matching relationship exists.
- **Steps:** Delete by event and equipment item.
- **Expected:** `204`; both identifiers constrain the delete. Missing row is
  `404`; no catalogue item or unrelated requirement is deleted.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py` / `test_schemas.py`

## TC-EQUIPMENT-017 — requirement storage failures are safe

- **Pre-conditions:** Upsert, list, and delete execution each raise a database
  exception in turn.
- **Expected:** `500 {"detail":"Equipment storage unavailable"}` without
  database details.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py` / `test_schemas.py`
