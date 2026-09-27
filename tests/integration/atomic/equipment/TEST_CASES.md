# Test cases — equipment service (integration)

Story: S-39 Add Equipment Item.

| | |
| --- | --- |
| Suite | `pytest tests/integration/atomic/equipment` |
| Last run | Not run — awaiting developer database setup |
| Environment | `.env.test`, Docker Compose, test Supabase project |
| Result | Blocked pending database setup |

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
- **Actual:** Not executed.
- **Status:** Blocked — `equipment.sql` must be applied and the schema exposed in the test project
- **Evidence:** —

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
- **Actual:** Not executed.
- **Status:** Blocked — `equipment.sql` must be applied and the schema exposed in the test project
- **Evidence:** —
