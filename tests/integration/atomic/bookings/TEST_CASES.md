# Test cases — bookings service (integration)

Covers `tests/integration/atomic/bookings/test_app.py`: the real bookings
service in Docker against the test Supabase project. The fake in the unit
tests agrees with everything, so this is the one save-then-read that proves
the table, the grants, the schema exposure and the connection all at once.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/atomic/bookings` |
| Last run | 2026-09-29, branch `S-38/prevent-overlapping-booking-confirmation`, pre-commit working tree |
| Environment | `.env.test` test Supabase project with all repository SQL, including the S-38 exclusion constraint, applied, granted and exposed; full stack recreated immediately before |
| Result | 5 booking integration cases passed; 35 passed across `tests/integration` |

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
- **Actual:** Approval and rejection persisted the expected final status, deciding staff and server timestamp; the alternative was preserved, original request fields were unchanged, decided rows left the pending list, repeated decisions returned 409, and non-staff mutation was denied.
- **Status:** Pass
- **Evidence:** `test_decision.py::test_decisions_persist_without_rewriting_requests`; local `.env.test` execution, 2 parameterized cases passed.

### TC-BOOKINGS-103 — Concurrent decisions on the same request have one winner

- **Scenario:** Concurrent decisions on the same request have one winner (AC1, AC2).
- **Pre-conditions:** Approved test environment and migrated schema; one pending fixture; two authenticated staff.
- **Steps:** 1. Send simultaneous approval and rejection.
  2. Read final row; attempt another decision.
- **Test data:** Same booking UUID; S1 approves; S2 rejects with reason='Repairs'.
- **Expected:** Exactly one 200 and one 409; stored metadata belongs entirely to the winner; later attempt 409. This proves same-request concurrency only, not S-38 overlap protection across different requests.
- **Actual:** The simultaneous requests produced exactly one 200 and one 409; the saved row contained only the winning decision, and a later attempt also returned 409.
- **Status:** Pass
- **Evidence:** `test_decision.py::test_concurrent_decisions_have_one_winner`; local `.env.test` execution.

## S-38 confirmed specifications

Story: S-38 Prevent Overlapping Booking Confirmation.
Confirmed by the developer on 2026-09-29. Back-to-back bookings are allowed.

### TC-BOOKINGS-104 — Concurrent overlapping confirmations have exactly one winner

> **Superseded by S-30.** Holds are exclusive now, so two overlapping pending
> requests can no longer exist, and this setup can't be created.
> TC-BOOKINGS-106 proves the same database guarantee at submission. The last
> result is kept below as a record.

- **Scenario:** The database-backed confirmation boundary prevents a race from
  double-booking one venue (AC1, AC2, AC3).
- **Pre-conditions:** Fresh `.env.test` stack; S-38 SQL applied, granted and
  exposed in the test project; two different pending bookings exist for the
  same venue and overlapping slot; two authenticated Venue Staff sessions.
- **Steps:** Send both approvals simultaneously; read both rows through the
  API and directly from `bookings.bookings`; then retry the blocked approval.
- **Test data:** Studio B on `2026-11-12`: B1 `09:00`–`12:00`, B2
  `11:00`–`13:00`.
- **Expected:** Exactly one request returns `200` and becomes `confirmed`.
  The other returns `409`, remains `pending`, and identifies the winning
  booking's venue/date/time as the conflict. The retry is also blocked. At no
  point do two overlapping confirmed rows exist.
- **Actual:** Simultaneous approvals produced one Confirmed row and one still-Pending row; the loser received an identified `409`, and retry remained blocked.
- **Status:** Pass
- **Evidence:** `test_decision.py::test_concurrent_overlapping_confirmations_have_one_winner`; full `.env.test` integration suite: 35 passed.

## S-30 — view venue availability calendar

Story: S-30 View venue availability calendar.
Confirmed by the developer on 2026-09-30. Not yet executed.
All three cases are **Blocked** until the S-30 section of
`backend/sql/bookings.sql` has been run in the test project. It widens the
exclusion constraint to cover pending rows and adds `bookings.blocks` with
its grants.

### TC-BOOKINGS-105 — A block saved through the service can be read back and removed

- **Scenario:** Proves `bookings.blocks` exists, is granted and exposed, and
  is reachable with the service key.
- **Pre-conditions:** A fresh `.env.test` stack and one Venue Staff session.
- **Steps:** As staff, `POST /blocks` for a random venue id, `2026-11-13`–`2026-11-16`,
  reason `renovation`. Then `GET /blocks?venue_id=…&from=2026-11-11&to=2026-11-30`.
  Then `DELETE /blocks/{id}`. Finally read `bookings.blocks` with the admin
  client.
- **Expected:** `201`, then a list containing the block, then `204`, and the
  row is gone. Cleanup removes anything left over.
- **Actual:** —
- **Status:** Not Executed
- **Evidence:** —

### TC-BOOKINGS-106 — Two simultaneous overlapping requests produce exactly one hold

- **Scenario:** The database constraint, not only the application check,
  keeps holds exclusive.
- **Pre-conditions:** A fresh `.env.test` stack. A random venue id with no
  bookings.
- **Steps:** Send two `POST /bookings` at the same moment with different event
  ids. Then read `bookings.bookings` directly.
- **Test data:** `2026-11-12`, B1 `09:00`–`12:00`, B2 `11:00`–`13:00`.
- **Expected:** One returns `201`. The other returns `409`, saying the winner
  is "already tentatively held on 12 Nov 2026 from …". Exactly one row exists
  for that venue and date.
- **Actual:** —
- **Status:** Not Executed
- **Evidence:** —

### TC-BOOKINGS-107 — Rejecting a hold releases the slot

- **Scenario:** A hold is released when its request is rejected.
- **Pre-conditions:** A fresh `.env.test` stack and one Venue Staff session.
- **Steps:** Create pending B1 (`2026-11-12` `09:00`–`12:00`). Reject it with
  a reason. Then `POST /bookings` for another event at the same venue and time.
- **Expected:** The reject returns `200` and the new request returns `201`
  `pending`.
- **Actual:** —
- **Status:** Not Executed
- **Evidence:** —
