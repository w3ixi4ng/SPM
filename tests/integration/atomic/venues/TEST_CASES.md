# Test cases — venues service (integration)

Covers `tests/integration/atomic/venues/test_app.py`: authenticated round
trips through the venues service directly and through Kong, against the test
Supabase project.

Story: S-27 Add Venue with Capacity and Facilities.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test down -v`, `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/atomic/venues` |
| Last run | 2026-09-26, branch `S-27/add-venue-with-capacity-and-facilities` at `b693360` |
| Environment | `.env.test` test Supabase project; `venues` schema applied, granted and exposed; users, venues and Kong healthy in Docker |
| Result | 2 passed (twice consecutively) |

## TC-VENUES-101 — venue staff save a venue and a coordinator reads it back

- **Scenario:** Prove authentication, RBAC, persistence, the case-insensitive
  name constraint, and the creator record against the real service and
  `venues.venues`.
- **Pre-conditions:** `.env.test` targets the throwaway project and the stack
  was started from it immediately before the run; `venues.sql` applied,
  granted, and `venues` exposed; the venues service on port 8003.
- **Steps:**
  1. Create and sign in a temporary `venue_staff` user and a temporary
     `event_coordinator` user.
  2. As venue staff, `POST /venues` with the test venue.
  3. As venue staff, `GET /venues/{id}` and `GET /venues`.
  4. As the coordinator, `GET /venues/{id}` and `GET /venues`.
  5. As the coordinator, `POST /venues` with a different name.
  6. As venue staff, `POST /venues` again with the same name in upper case.
  7. Read the row directly from `venues.venues` with the admin client.
  8. Delete the venue and both Auth users.
- **Test data:** Unique accounts `spm-test-venues-<hex>@example.com`. Venue:
  name `spm-test Venue <hex>`, location `1 Harbourfront Walk, Singapore
  098585`, capacity `250`, facilities `["projector", "wifi"]`, accessibility
  `["wheelchair_access"]`, room layouts `["theatre", "banquet"]`, hours
  `[{"day": "mon", "open": "09:00", "close": "18:00"}]`, description
  `Integration venue`.
- **Expected:** Step 2 `201` with `id`, `created_at`, and `created_by` equal
  to the venue staff user's id. Step 3 and step 4 `200`, the venue equal to
  what was sent, present in both lists. Step 5 `403`. Step 6 `409`. Step 7
  finds exactly one row with that name, in `venues.venues` (not `public`),
  with `created_by` set to the venue staff user. Cleanup leaves no rows; the
  suite passes twice in a row.
- **Actual:** Created `201` with `created_by` equal to the staff user; read back identically by staff and coordinator; coordinator POST `403`; upper-case duplicate `409`; exactly one row in `venues.venues`. Cleanup left no rows across two consecutive runs.
- **Status:** Pass
- **Evidence:** `test_app.py::test_venue_round_trip`

## TC-VENUES-102 — every venues operation routes through Kong

- **Scenario:** The browser-facing `/api/venues` route preserves the session
  cookie and reaches every venues operation.
- **Pre-conditions:** As TC-VENUES-101, plus Kong healthy on
  `KONG_PROXY_PORT`.
- **Steps:**
  1. Create and sign in a temporary `venue_staff` user.
  2. Through Kong: `GET /api/venues/health`, `GET /api/venues/options`,
     `POST /api/venues`, `GET /api/venues`, `GET /api/venues/{id}`.
  3. Delete the venue and the Auth user.
- **Test data:** A unique `spm-test-venues-<hex>@example.com` account; the
  minimal venue with name `spm-test Gateway <hex>`.
- **Expected:** Health `200`; options `200` with the four option sets;
  create `201`; list `200` containing the venue; read `200`. Cleanup removes
  every created record.
- **Actual:** Health, options, create, list and read all answered as expected through `/api/venues`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_kong_routes_every_venue_operation`


## S-28 approved coverage

Latest S-28 execution: 2026-09-27; base commit `0d27acc` plus uncommitted S-28 changes. Environment: Windows/Python 3.14/Node; integration uses freshly recreated `.env.test` Docker stack.

### TC-VENUES-103 ? Persist partial updates through Kong

- Scenario: Persist partial updates through Kong
- Pre-conditions: Approved .env.test stack; seed venue and two staff sessions plus coordinator.
- Steps: 1. Second staff PATCH location=Block B, capacity=100, facilities=[], accessibility=[]; read list/detail and database; coordinator attempts PATCH.
- Test data: Values specified above; existing shared fixtures supply remaining required fields.
- Expected: Updated values persisted; other fields identical; coordinator 403.
- Actual: All three venue integration tests passed against .env.test through Kong and Supabase.
- Status: Pass
- Evidence: `tests/integration/atomic/venues/test_app.py::test_staff_partial_update_persists_and_preserves_other_fields`; local execution, no CI run.
