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

### TC-BOOKINGS-104 — The database refuses a second overlapping confirmed booking

> **Rewritten for S-30 on 2026-09-30, at the developer's request.** The S-38
> version raced two approvals of overlapping pending requests, which S-30's
> exclusive holds make impossible to set up. This version checks the same S-38
> rule — the database never holds two overlapping confirmed bookings — at the
> database itself, going around the API.

- **Scenario:** Even a write that skips every application check cannot
  double-book a venue (S-38 AC1, AC2, AC3).
- **Pre-conditions:** Fresh `.env.test` stack; the S-38 and S-30 SQL applied,
  granted and exposed in the test project; one authenticated Venue Staff
  session; a venue id with no bookings.
- **Steps:**
  1. Create booking B1 through `POST /bookings` and approve it through
     `POST /bookings/{B1}/decision`.
  2. With the admin (service role) client, insert a `confirmed` row straight
     into `bookings.bookings` for the same venue and date, overlapping B1.
  3. Insert another `confirmed` row directly, starting exactly when B1 ends.
  4. Read the venue's rows from `bookings.bookings`.
- **Test data:** Studio B on `2026-11-12`: B1 `09:00`–`12:00`; overlapping
  row `11:00`–`13:00`; back-to-back row `12:00`–`14:00`.
- **Expected:** B1 is approved (`200`). The overlapping insert is refused
  with Postgres exclusion violation `23P01`. The back-to-back insert
  succeeds, since the range is `[start,end)`. The venue ends with exactly two
  confirmed rows, `09:00`–`12:00` and `12:00`–`14:00`, and never two that
  overlap. Cleanup deletes every row.
- **Actual:** B1 approved; the direct overlapping insert raised `23P01`; the back-to-back insert was stored; the venue held exactly the two expected confirmed rows.
- **Status:** Pass
- **Evidence:** `test_decision.py::test_the_database_refuses_a_second_overlapping_confirmed_booking`; `.env.test` stack recreated immediately before (bookings container on the test project's `SUPABASE_URL`); `pytest tests/integration/atomic/bookings`: 8 passed, 0 skipped.

## S-30 — view venue availability calendar

Story: S-30 View venue availability calendar.
Confirmed by the developer on 2026-09-30. Executed locally on 2026-09-30.
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
- **Actual:** Block created `201` with the staff id, listed for the range, deleted `204`, and gone from `bookings.blocks`.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/bookings/test_availability.py::test_a_block_can_be_saved_read_back_and_removed`; `.env.test` stack recreated immediately before; bookings container verified on the test project's `SUPABASE_URL`; `pytest tests/integration/atomic/bookings tests/integration/composite/venue_bookings`: 14 passed, 0 skipped.

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
  *Changed by S-76 (2026-10-09), which supersedes S-38/S-33 wording:* the
  refused hold reads "Can't hold this booking: it overlaps spm-test
  availability (tentatively held), which occupies Studio B on 12 Nov 2026
  from …". Re-run 2026-10-09 on the S-76 branch: pass.
- **Actual:** Of two simultaneous overlapping requests one returned `201` and one `409` "already tentatively held"; exactly one row stored.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/bookings/test_availability.py::test_two_simultaneous_overlapping_requests_produce_exactly_one_hold`; `.env.test` stack recreated immediately before; bookings container verified on the test project's `SUPABASE_URL`; `pytest tests/integration/atomic/bookings tests/integration/composite/venue_bookings`: 14 passed, 0 skipped.

### TC-BOOKINGS-107 — Rejecting a hold releases the slot

- **Scenario:** A hold is released when its request is rejected.
- **Pre-conditions:** A fresh `.env.test` stack and one Venue Staff session.
- **Steps:** Create pending B1 (`2026-11-12` `09:00`–`12:00`). Reject it with
  a reason. Then `POST /bookings` for another event at the same venue and time.
- **Expected:** The reject returns `200` and the new request returns `201`
  `pending`.
- **Actual:** Rejecting the hold returned `200`; the same slot then returned `201` pending.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/bookings/test_availability.py::test_rejecting_a_hold_releases_the_slot`; `.env.test` stack recreated immediately before; bookings container verified on the test project's `SUPABASE_URL`; `pytest tests/integration/atomic/bookings tests/integration/composite/venue_bookings`: 14 passed, 0 skipped.

### TC-BOOKINGS-114 — an expired hold releases its slot before another hold

- **Scenario:** S-81 expiry is enforced by the real bookings database and service.
- **Pre-conditions:** `.env.test` stack; S-81 bookings migration applied, exposed and granted.
- **Steps:** Create and hold request A; move its expiry into the past; list venue availability; create and hold overlapping request B.
- **Test data:** Same venue and 12 Nov 2026, 09:00–12:00; A expiry one second in the past; B expiry 1 Jan 2099 12:00 Singapore time.
- **Expected:** Listing invokes expiry and returns A as a retained pending audit row; live availability omits it, storage records `expired` and a release timestamp, and B can hold the same slot.
- **Actual:** The expired row became a retained pending audit row with
  `expired`; an overlapping request then acquired a new hold.
- **Status:** Pass
- **Evidence:** `test_availability.py::test_an_expired_hold_is_released_before_the_slot_is_claimed_again`; `.env.test` stack recreated immediately before, 2026-10-13; full `pytest tests/integration`: 56 passed, 5 skipped.

## S-33 — place tentative venue hold

Story: S-33 Place Tentative Venue Hold.
Confirmed by the developer on 2026-09-30. Not yet executed.

### TC-BOOKINGS-108 — Concurrent slot claims have one database-backed winner and release restores availability

- **Scenario:** Real storage prevents simultaneous Held/Confirmed overlap and frees the range after release (AC1–AC4).
- **Pre-conditions:** Fresh `.env.test` stack with S-33 SQL applied, granted and exposed; two overlapping pending requests; two authenticated Venue Staff sessions.
- **Steps:** Attempt simultaneous holds; verify availability; confirm the winner while attempting to hold/confirm the loser; release the winner with `booking_replaced`; hold the loser; read storage directly after each step.
- **Test data:** Studio B on `2026-11-12`: B1 `09:00`–`12:00`, B2 `11:00`–`13:00`.
- **Expected:** Exactly one simultaneous claim succeeds. Availability shows one Tentative entry, then one Confirmed entry after converting that same request. Competing overlap stays Pending with identified `409`. Release removes the active range immediately and allows B2 to become Held. At no point do overlapping active Held/Confirmed rows exist.
- **Actual:** Concurrent overlapping hold requests produced exactly one Held winner and one identified `409`; release allowed the range to be claimed again. No overlapping live rows were stored.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/bookings/test_availability.py`; complete integration suite, 41 passed.

## S-75 — configure venue setup and turnaround time

Story: S-75 Configure Venue Setup and Turnaround Time.
Confirmed by the developer on 2026-10-07. Not yet executed.

### TC-BOOKINGS-109 — the setup/turnaround gap is enforced against real rows

- **Pre-conditions:** A fresh `.env.test` stack; Venue Staff session; a
  random venue id.
- **Steps:** Create and approve A 10:00–12:00. Request 12:30–13:00 with
  `setup_minutes=30&turnaround_minutes=45`, then 13:15–14:00 with the same.
- **Expected:** `409` "…in use until 12:45.", then `201`. Cleanup deletes
  every row.
- **Actual:** 12:30–13:00 was 409 ending "…it is in use until 12:45."; 13:15–14:00 was 201.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/bookings/test_setup_turnaround.py::test_the_setup_turnaround_gap_is_enforced_against_real_rows`; `.env.test` stack rebuilt immediately before (venues container on the test project's `SUPABASE_URL`), 2026-10-08; 20 passed.

## S-77 — mark venue temporarily unavailable

**Story:** S-77 Mark Venue Temporarily Unavailable. Confirmed by the
developer on 2026-10-12. Executed 2026-10-12 on branch
`S-77/mark-venue-temporarily-unavailable`, after the S-77 block in
`backend/sql/bookings.sql` was run in the test project.

**Changes to existing cases.** TC-BOOKINGS-105's block gains times
(`2026-11-13` `00:00` to `2026-11-17` `00:00`). Its Status resets to Not
Executed until re-run.

### TC-BOOKINGS-110 — a timed period saved through the service refuses an overlapping request and allows a back-to-back one

- **Scenario:** Proves the new time columns exist, are granted, and are
  used by the real overlap check (S-77 AC1, AC2).
- **Pre-conditions:** `.env.test` stack recreated immediately before. The
  S-77 SQL applied in the test project. One Venue Staff session. A random
  venue id with no bookings.
- **Steps:**
  1. As staff, `POST /blocks` for the venue: `2026-11-13` `09:00` to
     `2026-11-13` `12:00`, reason `equipment_failure`, note
     `"spm-test projector fault"`.
  2. `GET /blocks?venue_id=…&from=2026-11-13&to=2026-11-13`.
  3. `POST /bookings` for the venue on `2026-11-13` `11:00`–`13:00`.
  4. `POST /bookings` for the venue on `2026-11-13` `12:00`–`14:00`.
  5. Read `bookings.blocks` by the new id with the admin client.
- **Expected:**
  1. `201`, `start_time` `"09:00:00"`, `end_time` `"12:00:00"`.
  2. A list containing the period, with its times.
  3. `409`, detail starting `"<venue name> is unavailable from 13 Nov 2026 09:00 to 13 Nov 2026 12:00."`; no row stored.
  4. `201`.
  5. One row, reason `equipment_failure`, `created_by` the staff id.
  Cleanup removes the block and the booking.
- **Actual:** Period saved `201` with `09:00:00`/`12:00:00` and listed with its times; `11:00`–`13:00` refused `409` with the exact detail and nothing stored; `12:00`–`14:00` `201`; one row with reason `equipment_failure` and the staff id.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/bookings/test_unavailable_periods.py::test_a_timed_period_refuses_an_overlapping_request_and_allows_a_back_to_back_one`; `.env.test` stack recreated immediately before (bookings container verified on the test project's `SUPABASE_URL`), 2026-10-12; `pytest tests/integration`: 52 passed, 5 skipped, plus the 2 S-75 helper fixes re-run and passed

### TC-BOOKINGS-111 — the database accepts only the story's reasons

- **Scenario:** The check constraint, not only the API, holds the reason
  list. An insert that bypasses the service can't store a dropped reason.
- **Pre-conditions:** As TC-BOOKINGS-110.
- **Steps:** With the admin client, insert into `bookings.blocks` a row for
  a random venue, `2026-11-13` `09:00` to `2026-11-13` `12:00`:
  1. with reason `equipment_failure`;
  2. with reason `internal_activity`;
  3. with reason `other` and no note;
  4. with `end` before `start` (`2026-11-13` `12:00` to `2026-11-13` `09:00`).
- **Expected:** 1 is stored. 2, 3 and 4 are each refused with Postgres error
  `23514` (check violation). Cleanup removes row 1.
- **Actual:** `equipment_failure` stored; `internal_activity`, `other` with no note, and end before start each refused with `23514`.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/bookings/test_unavailable_periods.py::test_the_database_accepts_only_the_storys_periods`; `.env.test` stack recreated immediately before (bookings container verified on the test project's `SUPABASE_URL`), 2026-10-12; `pytest tests/integration`: 52 passed, 5 skipped, plus the 2 S-75 helper fixes re-run and passed

## S-78 — request replacement venue for affected booking

**Story:** S-78 Request Replacement Venue for Affected Booking. Confirmed by the
developer on 2026-10-14. Tests in `test_replacement_venue.py`. Executed 2026-10-14 after the S-78
block in `backend/sql/bookings.sql` was run in the test project. The criteria
mapping is in `tests/unit/composite/venue_bookings/TEST_CASES.md`.

### TC-BOOKINGS-112 — approving a real replacement replaces the original row and frees its slot

- **Scenario:** Against real rows, the link column, the `replaced` status,
  the approval write and the exclusion constraint all agree (AC2, AC4).
- **Pre-conditions:** The `.env.test` stack recreated immediately before.
  The S-78 SQL applied. Two venues V1 and V2. A booking A for event E at V1,
  `2026-11-12` `10:00`–`12:00`, held and then approved by Venue Staff.
- **Steps:**
  1. `POST /bookings` for E at V2, at the same date and times, with `replaces_booking_id` A.
  2. As Venue Staff, approve it.
  3. Read A and the new row with the admin client.
  4. `POST /bookings` for another event at V1, `2026-11-12` `10:00`–`12:00`.
- **Expected:**
  1. `201`, stored with `replaces_booking_id` A.
  2. `200` `confirmed`.
  3. A is `replaced` with `replaced_by_booking_id` set to the new row and
     `replaced_at` set. Its other columns are unchanged.
  4. `201`: A no longer holds V1.
  Cleanup deletes every row created.
- **Actual:** Replacement stored with `replaces_booking_id`; approval `200` confirmed; the original became `replaced` with `replaced_by_booking_id` and `replaced_at`, every other column unchanged; a new request at V1 for the same slot `201`.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/bookings/test_replacement_venue.py::test_approving_a_real_replacement_replaces_the_original_and_frees_its_slot`; `.env.test` stack recreated immediately before (bookings container verified on the test project's `SUPABASE_URL`), 2026-10-14

### TC-BOOKINGS-113 — a resolution note is saved and read back

- **Scenario:** The three resolution columns exist, are granted, and
  round-trip (AC4).
- **Pre-conditions:** As TC-BOOKINGS-112 steps up to A confirmed. A real
  Coordinator session.
- **Steps:** `POST /bookings/{A}/alternative-resolution` with
  `{"note": "Moved online"}`, then `GET /bookings/{A}`.
- **Expected:** `200` both times. `alternative_resolution_note` is
  `"Moved online"`, `alternative_resolved_by` is the Coordinator, and
  `alternative_resolved_at` is set. `status` is still `confirmed`.
- **Actual:** Resolution `200`; the write and `GET /bookings/{id}` both carried note "Moved online", the Coordinator as resolver and a time; status still `confirmed`.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/bookings/test_replacement_venue.py::test_a_resolution_note_is_saved_and_read_back`; `.env.test` stack recreated immediately before (bookings container verified on the test project's `SUPABASE_URL`), 2026-10-14

## TC-BOOKINGS-115 — confirming a replacement retires the rejected original

- **Scenario:** The S-78 trigger also replaces a rejected original.
- **Pre-conditions:** Fresh `.env.test` stack; S-17 block of
  `backend/sql/bookings.sql` applied.
- **Steps:** 1. Create booking `B2`, reject it. 2. Create `B4` with
  `replaces_booking_id: B2`. 3. Confirm `B4`. 4. Read `B2`. 5. Delete both.
- **Test data:** Any free venue, `2026-11-20 09:00–17:00`.
- **Expected:** 2 → `201`. 4 → `status: "replaced"`,
  `replaced_by_booking_id: B4`, `replaced_at` set; its rejection reason is
  kept.
- **Actual:** Not run: the S-17 SQL (events.sql, and the S-78 block of bookings.sql) is not yet applied to the test Supabase project.
- **Status:** Blocked
- **Evidence:** `test_s17.py::test_confirmed_replacement_retires_rejected_original`
