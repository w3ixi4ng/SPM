# Test cases — registrations service (integration)

Covers `tests/integration/atomic/registrations/test_app.py`: the real service
on port 8007 against the test Supabase project.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/atomic/registrations` |
| Last run | 2026-10-25, branch `S-48/register-for-event`, pre-commit working tree |
| Environment | `.env.test` test Supabase project with the S-51 SQL applied, `registrations` exposed; full stack recreated with `--build` immediately before |
| Result | 2 passed in this suite |

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

## TC-REGISTRATIONS-102 — a place reads back by event and by Attendee

- **Scenario:** The real table serves both new reads (S-48 AC3).
- **Pre-conditions:** As TC-REGISTRATIONS-101.
- **Steps:**
  1. `POST /registrations` for random event E1 and Attendee A, then E1 and
     Attendee B, then random event E2 and A.
  2. `GET /registrations/events/E1`.
  3. `GET /registrations/attendees/A`.
  4. Delete every row for E1 and E2 through the admin client.
- **Test data:** Random uuids for E1, E2, A, B.
- **Expected:** 1 → three `201`s. 2 → `200`, exactly A's and B's rows for E1,
  in that order. 3 → `200`, exactly A's rows for E1 and E2, in that order.
  4 leaves no rows.
- **Actual:** Three `201`s; by event E1 → A's and B's rows in order; by Attendee A → E1 then E2; no rows remained.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/registrations/test_app.py::test_a_place_reads_back_by_event_and_by_attendee`; `.env.test` stack recreated with `--build` immediately before (users, events, registrations verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-48/register-for-event`
