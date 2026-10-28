# Test cases — equipment service (unit)

Stories: S-39 Add Equipment Item; S-40 Record Required Equipment; S-41 Update
Equipment Item Details; S-42 Retire Equipment Item.

These cases specify the equipment catalogue before its implementation. Supabase
and Auth are mocked; this suite makes no network or database calls.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/equipment` |
| Last run | 2026-09-28, branch `S-42/retire-equipment-item`, pre-commit working tree |
| Environment | Unit test environment; Supabase and authentication mocked |
| Result | 77 passed |

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

## S-41 — update equipment item details

The management update is a complete replacement of the editable catalogue
fields through `PUT /equipment/{item_id}`. It never accepts lifecycle or audit
fields. `GET /equipment/{item_id}` supplies the current values to the editor.

## TC-EQUIPMENT-018 — update input normalizes every editable field

- **Scenario:** Technical Support can submit the four S-41 catalogue fields.
- **Pre-conditions:** None.
- **Steps:** Validate padded type and description, quantity `18`, and each of
  `available`, `unavailable`, and `maintenance`.
- **Expected:** Text is stripped, blank description becomes `null`, quantity
  remains a positive integer, and all three statuses are accepted.
- **Actual:** Text normalization, optional blank description, quantity, and all three statuses behaved as specified.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_valid_update_is_normalized`

## TC-EQUIPMENT-019 — invalid and protected update fields are rejected

- **Scenario:** Catalogue integrity and server-owned data cannot be bypassed.
- **Pre-conditions:** None.
- **Steps:** Validate, in turn, blank type; quantity `0`, `-1`, and `1.5`;
  unknown operational status; and payloads containing id, lifecycle status,
  creator, created timestamp, or updated timestamp.
- **Expected:** Every payload returns `422`; description remains optional and
  accepts `null` or blank-as-null.
- **Actual:** Invalid business values and every protected field were rejected; nullable description remained valid.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_invalid_updates_are_rejected` and `test_app.py::test_invalid_update_never_calls_storage`

## TC-EQUIPMENT-020 — Technical Support reads and updates one item

- **Scenario:** The editor loads current values and persists changed details.
- **Pre-conditions:** Auth resolves to Technical Support; storage returns the
  existing row on read and the updated row on update.
- **Steps:** `GET /equipment/{id}`, then `PUT /equipment/{id}` with a renamed
  item, new description, quantity `18`, and `maintenance`.
- **Expected:** Read returns `200`. Update targets only
  `equipment.equipment`, filters by id, sets only the four editable fields plus
  a server-generated `updated_at`, and returns `200` with the updated row.
- **Actual:** Detail returned the stored row and update sent only the editable values plus server time through an id-filtered equipment-table query.
- **Status:** Pass
- **Evidence:** `test_app.py::test_technical_support_reads_and_updates_one_item`

## TC-EQUIPMENT-021 — a missing item returns 404

- **Scenario:** A stale editor URL cannot appear to save a nonexistent item.
- **Pre-conditions:** The filtered read or update returns no row.
- **Steps:** Read and update an unknown UUID.
- **Expected:** Both requests return `404 {"detail":"Equipment item not found"}`.
- **Actual:** Empty read and update results both returned the specified 404.
- **Status:** Pass
- **Evidence:** `test_app.py::test_missing_item_returns_404`

## TC-EQUIPMENT-022 — only Technical Support can read detail and update

- **Scenario:** Catalogue mutation remains restricted to the responsible role.
- **Pre-conditions:** Anonymous session, then each authenticated non-Technical
  Support role.
- **Steps:** Call both S-41 endpoints.
- **Expected:** Anonymous requests return `401`; Event Organiser, Event
  Coordinator, Venue Staff, and Attendee requests return `403`; storage is
  untouched.
- **Actual:** Anonymous callers received 401 and every non-Technical-Support role received 403 without storage access.
- **Status:** Pass
- **Evidence:** `test_app.py::test_s41_requires_a_session` and `test_app.py::test_only_technical_support_updates_equipment`

## TC-EQUIPMENT-023 — catalogue updates never mutate requirement relationships

- **Scenario:** S-41 edits catalogue data without deleting, recreating, or
  detaching S-40 requirements.
- **Pre-conditions:** One existing requirement references the item.
- **Steps:** Update the catalogue item.
- **Expected:** The service issues one filtered update against
  `equipment.equipment`; it never inserts, updates, or deletes from
  `equipment.requirements`.
- **Actual:** Update touched only `equipment.equipment`; no requirement mutation operation was called.
- **Status:** Pass
- **Evidence:** `test_app.py::test_catalogue_update_does_not_touch_requirements`

## TC-EQUIPMENT-024 — S-41 storage failures are safe

- **Scenario:** Detail and update failures reveal no database information.
- **Pre-conditions:** Each operation raises `database secret`.
- **Steps:** Read and update an item.
- **Expected:** Each returns `500 {"detail":"Equipment storage unavailable"}`
  without the underlying exception text.
- **Actual:** Both failures returned the safe storage message without the exception text.
- **Status:** Pass
- **Evidence:** `test_app.py::test_s41_storage_failures_are_safe`

## S-42 — retire equipment item

Retirement is a lifecycle action through
`POST /equipment/{equipment_item_id}/retire`. It is separate from S-41
operational status and is idempotent. There is no unretirement or hard-delete
operation in this story.

## TC-EQUIPMENT-025 — Technical Support retires an active item idempotently

- **Scenario:** Retirement changes lifecycle state without changing catalogue
  identity or business details.
- **Pre-conditions:** Auth resolves to Technical Support. Storage first returns
  an active item, then the same retired item on a repeated request.
- **Steps:** Retire the active item; record the response; retire it again.
- **Test data:** The shared microphone, operational status `maintenance`.
- **Expected:** The first request filters by item id and updates only
  `lifecycle_status="retired"` plus server-managed `updated_at`. Type,
  description, total quantity, operational status, creator, created timestamp,
  and id are unchanged. The second request returns `200` with the existing
  retired item and issues no second update or new record.
- **Actual:** The first request changed only lifecycle state and update time;
  the repeated request returned the identical retired row without a second
  update.
- **Status:** Pass
- **Evidence:** `test_app.py::test_technical_support_retires_an_item_idempotently`

## TC-EQUIPMENT-026 — only Technical Support can retire an item

- **Scenario:** Retirement is protected by trusted role metadata.
- **Pre-conditions:** Anonymous session, then each authenticated non-Technical
  Support role.
- **Steps:** Call the retirement endpoint.
- **Expected:** Anonymous requests return `401`; Event Organiser, Event
  Coordinator, Venue Staff, and Attendee requests return `403`; storage is
  untouched.
- **Actual:** Anonymous access returned `401`; all four non-Technical-Support
  roles returned `403`; no storage operation ran.
- **Status:** Pass
- **Evidence:** `test_app.py::test_retirement_requires_a_session` and `test_app.py::test_only_technical_support_retires_equipment`

## TC-EQUIPMENT-027 — retiring a missing item returns 404

- **Scenario:** A nonexistent item cannot be reported as retired.
- **Pre-conditions:** The id-filtered lookup returns no row.
- **Steps:** Retire an unknown UUID.
- **Expected:** `404 {"detail":"Equipment item not found"}` and no update.
- **Actual:** The missing lookup returned `404` and no update ran.
- **Status:** Pass
- **Evidence:** `test_app.py::test_retiring_missing_item_returns_404`

## TC-EQUIPMENT-028 — retired items are excluded from new requirements without losing old ones

- **Scenario:** Lifecycle retirement blocks future selection and requirement
  creation while preserving existing S-40 relationships.
- **Pre-conditions:** One existing requirement references an item that is now
  retired.
- **Steps:** Query selection; try to create a requirement for another event;
  list the pre-retirement requirement; inspect retirement storage operations.
- **Expected:** Selection still filters lifecycle to `active`; new requirement
  creation returns `409`; the existing requirement remains readable with its
  same id, event id, item id and quantity and may embed the retired item.
  Retirement never deletes the catalogue row or inserts, updates, or deletes a
  requirement relationship.
- **Actual:** Active-only selection and requirement validation excluded the
  retired item; the pre-existing relationship remained readable with the same
  identity and quantity, and retirement never touched requirement storage.
- **Status:** Pass
- **Evidence:** `test_app.py::test_retired_item_is_refused_for_new_requirements`, `test_app.py::test_existing_requirement_remains_readable_after_retirement`, and `test_app.py::test_retirement_never_deletes_or_mutates_requirements`

## TC-EQUIPMENT-029 — retirement storage failures are safe

- **Scenario:** Lookup or update failures reveal no database details and never
  report success.
- **Pre-conditions:** Each storage operation raises `database secret` in turn.
- **Steps:** Retire an item.
- **Expected:** Each failure returns
  `500 {"detail":"Equipment storage unavailable"}` without the underlying
  exception text.
- **Actual:** Both lookup and update failures returned the safe `500` response
  without exposing the simulated database detail.
- **Status:** Pass
- **Evidence:** `test_app.py::test_retirement_storage_failures_are_safe`

---

## S-44 — check equipment availability

Story: S-44 Check equipment availability.
Confirmed by the developer on 2026-09-30. Not yet executed.

## TC-EQUIPMENT-030 — requirements can be listed for a set of events

- **Scenario:** The availability check asks only for the overlapping events'
  requirements (S-44 AC2).
- **Steps:** `GET /internal/equipment-requirements?event_ids=<E1>&event_ids=<E2>`.
- **Expected:** `200`; the query uses `event_id in (E1, E2)`, each row with
  its equipment item, as the existing list returns. The existing `event_id`
  filter and the unfiltered list are unchanged. A malformed id → `422`.
- **Actual:** `200` with the requirement detail; the query used `event_id in (E1, E2)` and no single-event filter; a malformed id returned `422` without storage.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/equipment/test_app.py::test_requirements_can_be_listed_for_a_set_of_events`; `tests/unit/atomic/equipment/test_app.py::test_a_malformed_event_id_in_the_set_is_refused`

---

## S-92 — Record Equipment Storage Location

Story: S-92 Record Equipment Storage Location. Test cases confirmed by the
developer on 2026-10-28.

## TC-EQUIPMENT-031 — storage location is optional, normalized and bounded

- **Scenario:** Technical Support may record a useful free-text location without storing whitespace-only or excessive input.
- **Pre-conditions:** An otherwise valid new equipment payload.
- **Steps:** Validate locations `"  Store A, Bay 9  "`, whitespace only, and 201 characters.
- **Test data:** `Store A, Bay 9`; `   `; 201 `x` characters.
- **Expected:** The first becomes `Store A, Bay 9`, blank becomes null, and 201 characters returns a validation error.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_storage_location_is_optional_trimmed_and_limited`

## TC-EQUIPMENT-032 — Technical Support records, edits and clears a location

- **Scenario:** The existing protected catalogue writes persist S-92 metadata.
- **Pre-conditions:** Authenticated Technical Support and fake equipment storage.
- **Steps:** Create with `Store B, Shelf 4`; update with an empty location.
- **Expected:** Create stores and returns the location; update sends null and returns no location. Existing permission tests continue to deny other roles.
- **Status:** Pass
- **Evidence:** `test_app.py::test_storage_location_is_created_edited_and_cleared_by_technical_support`

## TC-EQUIPMENT-033 — catalogue consumers receive the location

- **Scenario:** Catalogue and selection responses expose the current storage location.
- **Pre-conditions:** An item stored at `Loading Dock Cabinet 2`.
- **Steps:** List management catalogue and active selection.
- **Expected:** Both responses contain the same location as descriptive metadata.
- **Status:** Pass
- **Evidence:** `test_app.py::test_catalogue_and_selection_expose_storage_location`
