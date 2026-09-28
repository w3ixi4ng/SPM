# Test cases — bookings service (integration)

Covers `tests/integration/atomic/bookings/test_app.py`: the real bookings
service in Docker against the test Supabase project. The fake in the unit
tests agrees with everything, so this is the one save-then-read that proves
the table, the grants, the schema exposure and the connection all at once.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/atomic/bookings` |
| Last run | 2026-09-27, branch `S-36/submit-venue-booking-request` at `665c7b3` |
| Environment | `.env.test` test Supabase project; `users`, `events` (with every S-36 migration, including dropping the accessibility notes), `venues` and `bookings` (with the cabaret removal and the `special_requirements` rename) applied, granted and exposed; full stack recreated with `docker compose --env-file .env.test up -d --build --wait` immediately before, containers confirmed on the test project |
| Result | 1 passed (20 across `tests/integration`), twice consecutively |

**Story:** S-36 Submit venue booking request.

## TC-BOOKINGS-101 — a booking saved through the service is listed as pending

- **Scenario:** Save, read back through the pending list, and confirm in the
  table.
- **Pre-conditions:** `.env.test` points at the throwaway project.
  `backend/sql/bookings.sql` has been applied, and `bookings` is under
  Exposed schemas. The stack was started with `--env-file .env.test`
  immediately before the run. The bookings service answers on
  `http://localhost:8004`.
- **Steps:**
  1. `POST /bookings` with the unit suite's shared body, using fresh random
     UUIDs for `event_id`, `venue_id` and `coordinator_id`, and
     `event_name` set to `"spm-test booking <hex>"`.
  2. `GET /bookings?status=pending`.
  3. Read `bookings.bookings` by the new id with the admin client.
- **Test data:** As above.
- **Expected:**
  - Step 1: `201`, `status: "pending"`, `submitted_at` set.
  - Step 2: the list contains the new id.
  - Step 3: exactly one row, with `required_facilities`,
    `required_accessibility` and `room_layout` as sent.
  - Teardown deletes the row with the admin client, pass or fail, so the
    suite can run twice in a row.
- **Actual:** `201` pending with `submitted_at`; listed as pending; one row in `bookings.bookings` with the options as sent; removed on teardown.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_booking_saved_through_the_service_is_listed_as_pending`

## S-37 confirmed specifications

Confirmed by the developer on 2026-09-28, with no reassignment exception.
S-37 execution: 2026-09-29; base c4934e9 merged with S-37 plus conflict-resolution changes on
S-37/approve-reject-booking-with-reason-or-alternative.
Windows, Python 3.14, Node.js; existing results above describe earlier coverage.
Approval stores `status=confirmed`; rejection stores `status=rejected`.
Decision metadata: `decision_reason`, `decision_alternative`, `decided_by`, `decided_at`.
B means the saved booking fixture; S means the authenticated deciding staff UUID.
No S-33 hold behaviour or S-38 cross-request overlap guarantee is included.

### TC-BOOKINGS-102 — Decisions persist while original requests remain intact

- **Scenario:** Decisions persist while original requests remain intact (AC1, AC2).
- **Pre-conditions:** Fresh .env.test stack only; additive SQL applied by developer; test staff and two pending fixtures exist. Cleanup removes only test-created rows.
- **Steps:** 1. Capture both requests.
  2. Approve one and reject the other with alternative only.
  3. Read through API and test database; repeat decision; call directly as nonstaff.
- **Test data:** Venue Studio B; date 2026-11-12; 09:00-12:00; capacity snapshot 100; alternative='Try Studio C at 14:00'.
- **Expected:** Confirmed/rejected status and correct staff/server timestamp persist; explanations persist; every original field unchanged; no extra booking created; no decided row in pending list. Repeat=409; direct nonstaff mutation denied.
- **Actual:** Not run; developer confirmation of S-37 SQL on dev and test is pending.
- **Status:** Blocked
- **Evidence:** Test code added; real execution pending database confirmation and fresh .env.test stack.

### TC-BOOKINGS-103 — Concurrent decisions on the same request have one winner

- **Scenario:** Concurrent decisions on the same request have one winner (AC1, AC2).
- **Pre-conditions:** Approved test environment and migrated schema; one pending fixture; two authenticated staff.
- **Steps:** 1. Send simultaneous approval and rejection.
  2. Read final row; attempt another decision.
- **Test data:** Same booking UUID; S1 approves; S2 rejects with reason='Repairs'.
- **Expected:** Exactly one 200 and one 409; stored metadata belongs entirely to the winner; later attempt 409. This proves same-request concurrency only, not S-38 overlap protection across different requests.
- **Actual:** Not run; developer confirmation of S-37 SQL on dev and test is pending.
- **Status:** Blocked
- **Evidence:** Test code added; real execution pending database confirmation and fresh .env.test stack.
