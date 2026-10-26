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

- **Scenario:** The table, grants, exposure and unique constraint all work together (S-51 AC5). Revised for S-50: every registration carries `"capacity": 50`.
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

- **Scenario:** The real table serves both new reads (S-48 AC3). Revised for S-50: every registration carries `"capacity": 50`.
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

## S-50 — Cap Registration at Capacity

Needs the S-50 additions to `backend/sql/registrations.sql` (the
`waiting_list` table and the `register` function) applied to the test
project. Blocked until they are.

## TC-REGISTRATIONS-103 — the cap holds, even under simultaneous registrations

- **Scenario:** The database gives out exactly `capacity` places, never one more (S-50 AC1).
- **Pre-conditions:** Fresh `.env.test` stack; S-50 SQL applied and `registrations` exposed and granted.
- **Steps:**
  1. `POST /registrations` for event E1 and attendees A1, A2, A3 in turn, each with `"capacity": 2`.
  2. For event E2, send 6 `POST /registrations` at once (6 distinct attendee ids, `"capacity": 3`).
  3. Read both events' rows through the admin client; delete them.
- **Test data:** Random uuids for E1, E2 and every attendee.
- **Expected:** 1 → `201`, `201`, `409` "This event is full.". 2 → exactly 3
  `201` and 3 `409`. 3 → E1 has 2 rows, E2 has 3.
- **Actual:** In turn: `201`, `201`, `409` "This event is full."; 6 at once: three `201`, three `409`; E1 held 2 rows, E2 held 3; rows removed.
- **Status:** Pass
- **Evidence:** tests/integration/atomic/registrations/test_app.py::test_the_cap_holds_even_under_simultaneous_registrations; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-REGISTRATIONS-104 — a waiting-list entry is saved and read back

- **Scenario:** The waiting list table, its grants and its uniqueness work for real (S-50 AC2).
- **Pre-conditions:** As TC-REGISTRATIONS-103.
- **Steps:**
  1. `POST /registrations/waiting-list` for E and B; repeat it.
  2. `GET /registrations/waiting-list/events/E`.
  3. `GET /registrations/waiting-list/events/E/attendees/B`.
  4. Delete the row through the admin client.
- **Test data:** Random uuids for E and B.
- **Expected:** 1 → `201`, then `409`. 2 → one row for B. 3 → `200`. 4 leaves no rows.
- **Actual:** `201`, then `409`; the list held B; the single read `200`; no rows remained.
- **Status:** Pass
- **Evidence:** tests/integration/atomic/registrations/test_app.py::test_a_waiting_list_entry_is_saved_and_read_back; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-REGISTRATIONS-105 — waiting-list order and an Attendee's entries, for real (S-52)

- **Scenario:** Join order holds against the real table, and an Attendee's entries across events can be read back (S-52 AC2, AC3).
- **Pre-conditions:** As TC-REGISTRATIONS-103. No SQL change for S-52; the S-50 `registrations.waiting_list` table is enough.
- **Steps:**
  1. `POST /registrations/waiting-list` for E and B, then for E and C, then for F and B.
  2. `GET /registrations/waiting-list/events/E`.
  3. `GET /registrations/waiting-list/attendees/B`.
  4. Delete the rows through the admin client.
- **Test data:** Random uuids for E, F, B and C.
- **Expected:** 1 → three `201`s. 2 → B's row, then C's. 3 → B's two rows, E's then F's. 4 leaves no rows.
- **Actual:** Three `201`s; E's list read B then C; B's entries read E then F; no rows remained.
- **Status:** Pass
- **Evidence:** tests/integration/atomic/registrations/test_app.py::test_waiting_list_order_and_an_attendees_entries; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), 2026-10-26, branch `S-52/join-waiting-list` (on S-50 `a3011b3`), pre-commit working tree

## TC-REGISTRATIONS-106 — withdrawing promotes the first in line, for real (S-53)

- **Scenario:** Against the real table and function: a withdrawal frees the place, the first Attendee waiting takes it, the rest move up, and no one is promoted while no place is free (S-53 AC1–AC4).
- **Pre-conditions:** As TC-REGISTRATIONS-103, plus the S-53 block of `backend/sql/registrations.sql` applied to the test project (the `registrations.withdraw` function and its grant).
- **Steps:**
  1. `POST /registrations` for E and A, capacity 1.
  2. `POST /registrations/waiting-list` for E and B, then for E and C.
  3. `POST /registrations/withdrawals` `{E, A, capacity 1}`.
  4. `GET /registrations/events/E`; `GET /registrations/waiting-list/events/E`.
  5. `POST /registrations/withdrawals` `{E, A, capacity 1}` again.
  6. `POST /registrations/withdrawals` `{E, B, capacity 0}`.
  7. `GET /registrations/waiting-list/events/E`.
  8. Delete the rows through the admin client.
- **Test data:** Random uuids for E, A, B and C.
- **Expected:** 1 → `201`. 2 → two `201`s. 3 → `200`, `withdrawn.attendee_id` A, `promoted.attendee_id` B. 4 → the places list holds only B; the waiting list holds only C. 5 → `404` "You're not registered for this event.". 6 → `200`, `promoted` `null`. 7 → still only C. 8 leaves no rows.
- **Actual:** `201`; two `201`s; withdrawal `200` with A withdrawn and B promoted; places held only B, waiting list only C; second withdrawal `404` "You're not registered for this event."; B with capacity 0 → `200`, `promoted` null, C still waiting; no rows remained.
- **Status:** Pass
- **Evidence:** tests/integration/atomic/registrations/test_app.py::test_withdrawing_promotes_the_first_in_line; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`); S-53 SQL applied to dev and test; 2026-10-26, branch `S-53/withdraw-registration` (on S-52 + S-49 `fde7b1f`), pre-commit working tree
