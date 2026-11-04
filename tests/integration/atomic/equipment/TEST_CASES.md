# Test cases — equipment service (integration)

Stories: S-39 Add Equipment Item; S-40 Record Required Equipment; S-41 Update
Equipment Item Details; S-42 Retire Equipment Item.

| | |
| --- | --- |
| Suite | `pytest tests/integration/atomic/equipment` |
| Last run | 2026-09-28, branch `S-42/retire-equipment-item`, pre-commit working tree |
| Environment | `.env.test`, Docker Compose, test Supabase project |
| Result | 4 passed |

## Shared pre-conditions

- `.env.test` targets the throwaway Supabase project.
- `backend/sql/equipment.sql` has been applied and the `equipment` schema is
  exposed and granted in that project.
- The complete stack was recreated immediately before the test.
- Email confirmation is disabled in the test project.

## TC-EQUIPMENT-101 — a created item is immediately available to catalogue consumers

- **Scenario:** Prove authentication, RBAC, persistence, schema ownership and
  selection visibility across the real boundary.
- **Pre-conditions:** Shared; a temporary Technical Support user and Event
  Coordinator user exist with trusted app-metadata roles and profile rows.
- **Steps:**
  1. Sign in as Technical Support.
  2. `POST /equipment` with the item below.
  3. `GET /equipment` and confirm it is in the management catalogue.
  4. Sign in as the Coordinator and `GET /equipment/selection`.
  5. Read the row directly from `equipment.equipment` with the admin client.
  6. As the Coordinator, attempt `POST /equipment`.
  7. Delete the row and both temporary users.
- **Test data:** Type `spm-test Wireless Microphone <hex>`, description
  `Integration microphone`, total quantity `12`.
- **Expected:** Creation returns `201`, generated id, Technical Support's id as
  `created_by`, `available`, and `active`. Both reads contain the same item.
  Direct inspection finds exactly one row in `equipment.equipment`, not
  `public`. Coordinator creation returns `403`. Cleanup leaves no row and the
  case passes twice consecutively.
- **Actual:** The item persisted in `equipment.equipment`, appeared in both
  catalogue surfaces, carried its server-owned defaults, and Coordinator
  creation was refused. Fixture cleanup removed the item and both users.
- **Status:** Pass
- **Evidence:** `test_app.py::test_created_item_is_immediately_available`

## TC-EQUIPMENT-102 — every S-39 operation routes through Kong

- **Scenario:** The browser-facing `/api/equipment` route preserves session
  cookies and path mapping.
- **Pre-conditions:** Shared; Kong is healthy on `KONG_PROXY_PORT` and a
  temporary Technical Support user exists.
- **Steps:** Through Kong, call `GET /api/equipment/health`, create the shared
  item, list `/api/equipment`, and read `/api/equipment/selection`; then clean
  up the row and user.
- **Test data:** Type `spm-test Gateway Microphone <hex>`, quantity `8`.
- **Expected:** Health and reads return `200`; create returns `201`; catalogue
  and selection both contain the new item.
- **Actual:** Health, create, catalogue, and selection all returned their
  expected successful responses through `/api/equipment`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_kong_routes_every_s39_operation`

## TC-EQUIPMENT-103 — an edit is immediately visible without changing its requirement

- **Scenario:** Prove the complete S-41 persistence, filtering, gateway, and
  S-40 relationship-preservation boundary.
- **Pre-conditions:** Shared; a temporary Technical Support user and Event
  Coordinator exist; one active available item and one requirement referencing
  it are stored.
- **Steps:** Record the requirement row; through Kong load the item detail and
  update its type, description, quantity, and status to `unavailable`; read the
  management catalogue and Coordinator selection; read the requirement row and
  embedded catalogue detail; update status to `maintenance` and check selection
  again; clean up all temporary data.
- **Test data:** Type changes from `spm-test S41 Microphone <hex>` to
  `spm-test S41 Radio Microphone <hex>`, description to `Updated by S-41`,
  quantity from `12` to `18`, and statuses `unavailable` then `maintenance`.
- **Expected:** Detail and catalogue immediately show every edit. Neither
  non-available status appears in selection. The requirement keeps exactly the
  same id, event id, equipment item id, and requested quantity, while its
  embedded catalogue data shows the current item details.
- **Actual:** Both edits appeared through Kong and the management catalogue; both statuses stayed out of selection; the same requirement row and quantity remained while its embedded catalogue fields updated.
- **Status:** Pass
- **Evidence:** `test_app.py::test_updated_item_is_immediate_and_preserves_requirement`

## TC-EQUIPMENT-104 — retirement persists, is idempotent, and preserves existing requirements

- **Scenario:** Prove S-42 through Kong, the real equipment schema, selection,
  and the internal S-40 relationship boundary.
- **Pre-conditions:** Shared; a temporary Technical Support user and Event
  Coordinator exist; one active available item and one existing requirement
  referencing it are stored.
- **Steps:** Record the complete item and requirement rows; retire the item
  through Kong; read detail and management catalogue; query Coordinator
  selection; attempt a new requirement for another event; read the existing
  requirement; inspect both tables directly; retire the item a second time.
- **Test data:** `spm-test S42 Microphone <hex>`, total quantity `12`, existing
  requested quantity `6`, two opaque event UUIDs.
- **Expected:** Retirement returns `200` and changes only lifecycle status and
  updated time. The item still exists and appears in catalogue/detail as
  retired, but not selection. New requirement creation returns `409`. The old
  requirement keeps the same id, event id, item id, and quantity and remains
  readable with retired catalogue detail. Repeated retirement returns the same
  retired row without changing unrelated fields or relationships.
- **Actual:** The first action persisted retirement and changed only lifecycle
  state and update time. Catalogue/detail retained the item, selection and new
  requirement creation excluded it, the original relationship remained
  unchanged, and the second action returned the exact first retired response.
- **Status:** Pass
- **Evidence:** `test_app.py::test_retirement_is_idempotent_and_preserves_existing_requirement`

## TC-EQUIPMENT-105 — storage location survives the real database boundary

- **Scenario:** S-92 works through Kong and the real test Supabase equipment schema.
- **Pre-conditions:** Fresh `.env.test` stack; S-92 migration applied, schema exposed and granted; authenticated Technical Support.
- **Steps:** Create at `Store B, Shelf 4`; edit to `AV Cage, Rack 2`; list the catalogue; clear the location; inspect the table directly.
- **Expected:** Every API read immediately reflects the current value and the final database value is null.
- **Status:** Pass (2026-10-28)
- **Evidence:** `test_app.py::test_storage_location_round_trips_and_can_be_cleared`

## TC-EQUIPMENT-302 — S-60 batch journal and event write lock persist

- **Scenario:** A TEST Equipment batch is atomic, retryable and protects its saved baseline from competing writes.
- **Pre-conditions:** Fresh `.env.test` stack; Equipment S-60 SQL applied in TEST, schema exposed and granted; trusted service credential configured.
- **Steps:** 1. Seed projector P=2 and microphone M=1 for opaque event E. 2. Apply operation Q proposing P=3 and M removal; retry Q. 3. Attempt ordinary direct P=4 while Q is applied. 4. Abort Q and inspect the restored rows. 5. Retry the aborted Q. 6. Apply and finalize a new operation, then make a newer P=4 edit and try to abort the finalized operation.
- **Test data:** Two temporary active items; P 2→3, M 1→removed, Q UUID.
- **Expected:** The first call writes P=3 and removes M with exactly one audit change per item; identical retry adds none. Direct P=4 gets `409` and does not overwrite Q. Conditional abort restores both original rows; the aborted Q cannot be reused. A finalized operation cannot abort over the newer P=4 edit. All test rows are removed.
- **Actual:** TEST journal and write lock persisted across requests; retry, abort, finalise and newer edit checks passed.
- **Status:** Pass
- **Evidence:** tests/integration/atomic/equipment/test_s60.py::test_versioned_batch_is_idempotent_and_blocks_competing_requirement_writes
