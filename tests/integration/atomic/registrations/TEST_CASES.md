# Test cases — registrations service (integration)

Covers `tests/integration/atomic/registrations/test_app.py`: the real service
on port 8007 against the test Supabase project.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/atomic/registrations` |
| Last run | 2026-10-25, branch `S-51/configure-registration-and-open-close-period`, pre-commit working tree |
| Environment | `.env.test` test Supabase project with the S-51 SQL applied, `registrations` exposed; full stack recreated with `--build` immediately before |
| Result | 1 passed in this suite |

## TC-REGISTRATIONS-101 — register, refuse a duplicate, read it back

- **Scenario:** The table, grants, exposure and unique constraint all work together (S-51 AC5).
- **Pre-conditions:** Fresh `.env.test` stack; `backend/sql/registrations.sql`
  applied, `registrations` exposed and granted.
- **Steps:**
  1. `POST /registrations` for a random event id and Attendee A.
  2. Repeat step 1.
  3. `GET /registrations/events/{event}/attendees/A`.
  4. Delete every row for the event through the admin client.
- **Expected:** 1 → `201`. 2 → `409` "You're already registered for this
  event.". 3 → `200`, the row from step 1. 4 leaves no rows.
- **Actual:** `201`, then `409` "You're already registered for this event.", then `200` with the same row; no rows remained.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/registrations/test_app.py::test_register_refuse_a_duplicate_and_read_it_back`; `.env.test` stack recreated with `--build` immediately before (events, users, registrations verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-51/configure-registration-and-open-close-period`; S-51 SQL applied to the test project
