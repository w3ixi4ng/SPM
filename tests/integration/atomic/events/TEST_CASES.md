# Test cases — events service (integration)

Covers `tests/integration/atomic/events/test_app.py`: authenticated round trips
through the events service directly and through Kong, against the test Supabase
project.

| | |
| --- | --- |
| Suite | Start the events service against `.env.test`, then `pytest tests/integration/atomic/events` |
| Last run | 2026-09-27, branch `S-40/record-required-equipment`, pre-commit working tree |
| Environment | `.env.test` test Supabase project with all repository SQL applied, granted and exposed; full stack recreated immediately before the run |
| Result | 4 passed in this suite; 24 passed across `tests/integration` |

## TC-EVENTS-101 — authenticated draft-to-submission round trip

- **Scenario:** Prove authentication, RBAC, ownership, persistence, draft update,
  and submission against the real service and `events.events`.
- **Pre-conditions:** `.env.test` targets the throwaway project; `events.sql` is
  applied and `events` exposed; the events service is running on port 8002.
- **Steps:** 1. Create and sign in a temporary Auth user whose trusted role is
  `event_organiser`. 2. Create a partial draft. 3. List the organiser's events
  and find the draft. 4. Read it back. 5. PATCH its purpose. 6. Submit it with
  complete fields. 7. Delete the event and Auth user.
- **Test data:** A unique `spm-events-<hex>@example.com` account; Alumni
  networking event on `2026-10-20`, `18:00`–`21:00`, attendance `120`.
- **Expected:** Create `201`; read and update `200`; final submission `200`;
  list contains the draft and only the authenticated organiser's rows;
  organiser id equals the authenticated user's id; status changes from `draft`
  to `submitted`; `submitted_at` is set on the submitted row, so the submitting
  user and the time of submission are both recoverable; cleanup removes every
  created record.
- **Actual:** Full round trip passed. The submitted row came back with
  `submitted_at` set and `organiser_id` equal to the authenticated user, so the
  submission is recoverable after the fact. Ran twice consecutively; cleanup
  left no rows behind.
- **Status:** Pass
- **Evidence:** `test_app.py::test_draft_to_submission_round_trip`

## TC-EVENTS-102 — every events operation routes through Kong

- **Scenario:** The browser-facing `/api/events` route preserves authentication
  and reaches every Sprint 1 events operation.
- **Pre-conditions:** `.env.test` targets the throwaway project; the users and
  events services and Kong are healthy; the `events` schema is applied, granted,
  and exposed.
- **Steps:** 1. Create and sign in a temporary organiser. 2. Call the routed
  health path. 3. Create an empty draft through Kong. 4. List the organiser's
  events through Kong. 5. Read and PATCH the draft. 6. Submit it. 7. Create an
  immediately submitted event. 8. Delete both events and the Auth user.
- **Test data:** A unique `spm-events-<hex>@example.com` account; Gateway
  integration event on `2026-11-12`, `09:00`–`11:00`, attendance `40`.
- **Expected:** Health returns `200`; draft and immediate submission return
  `201`; list, read, update, and draft submission return `200`; the list
  contains the draft and only rows owned by the cookie-authenticated user;
  cleanup removes all records.
- **Actual:** Not run this pass -- same blocker as TC-EVENTS-101: the schema
  in both Supabase projects has not been rebuilt with `start_date`/`end_date`.
- **Status:** Blocked
- **Evidence:** `test_app.py::test_kong_routes_every_event_operation`

## TC-EVENTS-103 — coordinator load and internal assignment round trip

- **Scenario:** Prove `POST /events/coordinator-load` and the internal
  create/submit-with-assignment routes against real Supabase rows, including
  that only submitted events count.
- **Pre-conditions:** `.env.test` targets the throwaway project; `events.sql`
  including `assigned_coordinator_id` is applied and `events` exposed; the
  events service is running on port 8002.
- **Steps:** 1. Create a coordinator id (no Auth account needed -- the events
  service does not validate it against `users`). 2. `POST /events/internal`
  twice for that coordinator: one submitted event `2026-11-05 09:00`–`11:00`,
  one draft `2026-11-05 13:00`–`14:00`. 3. `POST /events/coordinator-load`
  for that coordinator with an overlapping window (`10:00`–`12:00`), a
  back-to-back window (`11:00`–`12:00`), and the draft's window. 4. Delete
  both created events.
- **Test data:** As above.
- **Expected:** The overlapping window reports `conflict: true`; the
  back-to-back window reports `conflict: false`; the draft's window reports
  `conflict: false`; `assigned_count` is `1` throughout (the draft is never
  counted).
- **Actual:** Not yet run.
- **Status:** Blocked — needs `events.sql` migrated with
  `assigned_coordinator_id` and the new internal routes built.
- **Evidence:** —

## TC-EVENTS-104 — an event with venue requirements and no venue preference is stored

- **Scenario:** Proves the S-36 columns, their check constraints, and that the
  submitted-fields constraint no longer needs `venue`.
- **Pre-conditions:** `.env.test`; the `events` schema with the S-36
  venue-requirements migration applied; stack started with
  `--env-file .env.test` immediately before.
- **Steps:** 1. Sign in as a fresh organiser. 2. `POST /events` with a complete
  payload, no `venue`, `room_layout: "theatre"`, `required_facilities:
  ["projector"]`, `required_accessibility: ["lift"]`. 3. Read the row with the
  admin client.
- **Test data:** As above.
- **Expected:** Step 2 `201`. Step 3: `venue` null and the three requirement
  columns as sent. The row is deleted on teardown.

- **Actual:** `201`; the row had `venue` null and the three requirement columns as sent.
- **Status:** Pass
- **Evidence:** `test_app.py::test_an_event_with_venue_requirements_and_no_venue_is_stored`

## S-44 — check equipment availability

Story: S-44 Check equipment availability.
Confirmed by the developer on 2026-09-30. Not yet executed.

### TC-EVENTS-108 — the overlapping-events query works against the real table

- **Pre-conditions:** A fresh `.env.test` stack. Events seeded directly on a
  date far from other tests' data (2031-03-04): `planning` 10:00–11:00,
  `confirmed` 11:30–13:00, `rejected` 10:00–11:00, `planning` 12:00–13:00.
- **Steps:** `POST /events/overlapping` for 2031-03-04 09:00–12:00.
- **Expected:** `200` with exactly the `planning` 10:00 and `confirmed` 11:30
  events among those seeded. Cleanup deletes every seeded event.
- **Actual:** `200`; of the seeded events, exactly the planning 10:00 and confirmed 11:30 events were returned; rejected and back-to-back were not.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/events/test_overlapping.py::test_the_overlapping_events_query_works_against_the_real_table`; `.env.test` stack recreated immediately before; events container verified on the test project's `SUPABASE_URL`; 4 passed across the S-44 integration run.

## S-62 — request event cancellation

Story: S-62 Request Event Cancellation.
Confirmed by the developer on 2026-10-11.
The S-62 SQL was applied to dev and test on 2026-10-11. For the criteria mapping and the agreed decisions, see the
S-62 section of `tests/unit/atomic/events/TEST_CASES.md`.

## TC-EVENTS-130 — a cancellation request is stored with the event through Kong

- **Scenario:** The columns, grants and gateway route work together, and the
  status is unchanged (AC3, AC5).
- **Pre-conditions:** A fresh `.env.test` stack; the S-62 SQL applied. An
  Organiser O who owns a `planning` event E (inserted by the admin client).
- **Steps:** As O, through `/api/events`:
  1. `POST /api/events/E/cancellation-request` `{"reason": "Keynote speaker withdrew"}`.
  2. `GET /api/events/E`.
  3. Repeat step 1.
- **Expected:**
  1. `200`.
  2. `status` `planning`; `cancellation_reason` "Keynote speaker withdrew";
     `cancellation_requested_by` O; `cancellation_requested_at` set.
  3. `409`.
  `events.events` read with the admin client agrees with step 2. Cleanup
  deletes E and O.
- **Actual:** Through Kong: the request returned `200`; `GET` showed status `planning` with the reason, requester and time; the second request returned `409`. `events.events` agreed.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/events/test_cancellation_request.py::test_a_cancellation_request_is_stored_with_the_event_through_kong`; `.env.test` stack recreated immediately before (events container verified on the test project's `SUPABASE_URL`), 2026-10-11, branch `S-62/request-event-cancellation` at `cb446d3`; S-62 SQL applied to dev and test. `pytest tests/integration/atomic/events`: 6 passed.
## S-26 — Update Equipment Preparation Status

### TC-EVENTS-126 — equipment preparation persists through the real Events boundary

- **Scenario:** The committed Events schema and authenticated HTTP route store and return S-26 state together.
- **Pre-conditions:** Fresh `.env.test` Docker stack; `backend/sql/events.sql` applied, exposed, and granted in the test project; assigned Technical Support and Coordinator accounts; one eligible event.
- **Steps:** Verify the database default; update through Kong as assigned Technical Support; load through both the support and Coordinator event views; attempt the same write as an unassigned worker.
- **Test data:** `not_started` → `in_progress` → `ready` on one planning event.
- **Expected:** The default, current value, updater, and timestamp persist in `events.events`; both authorised reads agree; the unassigned write is denied and leaves the row unchanged. The test deletes every row and account it creates.
- **Actual:** Not run.
- **Status:** Approved
- **Evidence:** `test_equipment_preparation.py::test_equipment_preparation_round_trip`

---

## S-18 — Update Event Information

Story: S-18 Update Event Information. Specification confirmed by the
developer on 2026-10-19. Not yet implemented or executed.

## TC-EVENTS-153 — Coordinator edits, lifecycle rollback, and audit persist through Kong

- **Scenario:** Authentication, gateway routing, Events storage constraints,
  lifecycle state, and edit history agree at the real boundary.
- **Pre-conditions:** Fresh `.env.test` stack with the S-18 Events SQL applied,
  exposed, and granted; Coordinator A and B; A's preparation event with a
  current safety approval, safety history, equipment preparation `ready`, and
  existing venue/equipment arrangements.
- **Steps:** Through Kong, A saves a routine contact/note edit, previews and
  accepts a significant attendance/time edit, and reloads E. B attempts an
  edit. Inspect Events and history storage
  with the admin client.
- **Expected:** Routine values persist without changing status. Significant
  values do not persist before acceptance; after acceptance they persist and
  E is `planning` with current safety fields cleared. Prior safety history and
  arrangements remain. History contains exact before/after values, A and
  server times for both saves. E remains `planning` and marked for a fresh
  safety check; S-17 owns the checked transition to `pending_safety_check`.
  B receives `404`. Cleanup removes all created rows
  and users.
- **Actual:** Routine and accepted significant edits persisted through Kong;
  assignment isolation, lifecycle restart, preserved
  safety history/preparation state, and ordered audit entries all matched the
  specification.
- **Status:** Pass
- **Evidence:** `test_s18.py::test_coordinator_edit_lifecycle_and_audit_round_trip`; focused `.env.test` run, 2026-10-19.
## TC-EVENTS-147 — the new status and sign-off columns exist and are constrained

- **Scenario:** The S-17 SQL is applied, exposed and granted.
- **Pre-conditions:** Fresh `.env.test` stack; S-17 block of
  `backend/sql/events.sql` applied to the test project.
- **Steps:** 1. Create an event, drive it to `planning`, then via the admin
  client set `status: "pending_safety_check"`. 2. Try `status:
  "pending_safety_check", decision: null`. 3. Record a declined sign-off
  through `PUT /internal/events/{id}/technical-signoff`, read it back.
  4. Try writing `technical_signoff_decision: "declined"` with a null reason
  through the admin client. 5. Delete the event.
- **Test data:** Reason "Only one sound desk exists".
- **Expected:** 1 succeeds. 2 is refused (`23514`). 3 reads back decision,
  reason, Technical Support id and timestamp. 4 is refused (`23514`).
  5 leaves no row.
- **Actual:** Passed on 2026-10-19 against a fresh `.env.test` stack with the S-17 SQL applied: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_status_and_signoff_columns`

## TC-EVENTS-175 — the registration columns exist, round-trip and are constrained

- **Scenario:** The S-51 SQL is applied, exposed and granted (S-51 AC1, AC2).
- **Pre-conditions:** Fresh `.env.test` stack; S-51 block of
  `backend/sql/events.sql` applied to the test project.
- **Steps:**
  1. As a temporary Organiser, create a draft with registration on, opens
     `2026-11-01T09:00`, closes `2026-11-15T18:00`; read it back.
  2. Through the admin client, write closes `2026-11-01T08:00` (before opens).
  3. Submit it, drive it to `confirmed` through the admin client, then
     `GET /internal/events/published/{id}`.
  4. `PATCH /events/{id}` `{"registration_required": false}`.
  5. Delete the event.
- **Expected:** 1 reads back all three values unchanged (no timezone shift).
  2 is refused (`23514`). 3 → `200` with the period. 4 → `409`. 5 leaves no row.
- **Actual:** All three values read back unchanged; the reversed period was refused with `23514`; the published read returned the period without `organiser_id`; the PATCH was refused with `409`; no row remained.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/events/test_s51.py::test_registration_columns_round_trip_and_are_constrained`; `.env.test` stack recreated with `--build` immediately before (events, users, registrations verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-51/configure-registration-and-open-close-period`; S-51 SQL applied to the test project

## TC-EVENTS-184 — closing and reopening registration is saved (S-50)

- **Scenario:** The `registration_closed_at` column exists, is granted, and round-trips (S-50 AC4).
- **Pre-conditions:** Fresh `.env.test` stack; the S-50 line of `backend/sql/events.sql` applied to the test project.
- **Steps:**
  1. Through the admin client, create Organiser O and a confirmed event C owned by O with registration on.
  2. As O, `PUT /events/C/registration-closure`.
  3. `GET /internal/events/published/C`.
  4. As O, `DELETE /events/C/registration-closure`; repeat step 3.
  5. Delete C and O.
- **Test data:** Email `spm-test-*`; C's period opens yesterday, closes tomorrow (SGT).
- **Expected:** 2 → `200`. 3 → `registration_closed_at` not null. 4 → `200`,
  then `registration_closed_at` null. 5 leaves no rows.
- **Actual:** `200`; published read showed `registration_closed_at` set and `expected_attendance` 40; reopen `200`, then null; no rows remained.
- **Status:** Pass
- **Evidence:** tests/integration/atomic/events/test_s50.py::test_closing_and_reopening_registration_is_saved; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

---

## S-82 — View Event Change History

`test_s82.py`. Needs the S-82 block of `backend/sql/events.sql` applied to the
test project: the `events.event_history` table, its grants, its trigger, and
the `events.backfill_event_history` function.

## TC-EVENTS-203 — an appended entry is stored and read back

- **Scenario:** The table exists, is granted, and round-trips through the service.
- **Pre-conditions:** Fresh `.env.test` stack; S-82 SQL applied and `events` exposed.
- **Steps:**
  1. Through the admin client, create Organiser O, Coordinator C and a `planning` event E owned by O, assigned to C.
  2. `POST http://localhost:8002/internal/events/E/history` with `{"actor_id": C, "actor_role": "event_coordinator", "action": "venue_requested", "details": {"venue_name": "Hall One"}}`.
  3. `GET http://localhost:8002/internal/events/E/history`.
  4. Delete E, C and O.
- **Test data:** Emails `spm-test-*`.
- **Expected:** 2 → `201` with an `id` and an `occurred_at` within 60 s of now. 3 → `200` with that one entry, `category: "venue"`. After 4, no `event_history` row for E remains: deleting the event removes its entries.
- **Actual:** `201` with an id and a server `occurred_at` within a minute; read back as one `venue` entry; deleting the event left no history rows.
- **Status:** Pass
- **Evidence:** tests/integration/atomic/events/test_s82.py::test_an_appended_entry_is_stored_and_read_back; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), S-82 SQL applied to both projects; full integration run 96 passed, 5 skipped; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-204 — the database refuses to change or delete an entry

- **Scenario:** History entries cannot be edited or deleted, even with the service key (S-82 AC4).
- **Pre-conditions:** As TC-EVENTS-203, with one entry for E appended.
- **Steps:**
  1. Admin client: `update` that entry's `action` to `"request_rejected"`.
  2. Admin client: `delete` that entry by `id`.
  3. Read the entry back.
  4. Delete E (cleanup).
- **Test data:** As above.
- **Expected:** 1 and 2 each raise an API error (Postgres `42501` permission denied); 3 shows the entry unchanged; 4 succeeds and removes the entry with E.
- **Actual:** Both the update and the delete through the service key raised `42501`; the entry read back unchanged.
- **Status:** Pass
- **Evidence:** tests/integration/atomic/events/test_s82.py::test_the_database_refuses_to_change_or_delete_an_entry; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), S-82 SQL applied to both projects; full integration run 96 passed, 5 skipped; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-205 — backfill rebuilds what existing events already record, once

- **Scenario:** Events created before S-82 get the history their own columns can prove (developer decision 3b).
- **Pre-conditions:** Fresh `.env.test` stack, S-82 SQL applied. Through the admin client: O, C, Safety Officer S, Lead L; event E owned by O, assigned to C by L, with:
  - `submitted_at` `2026-10-01T01:00:00Z`
  - `decision` `approved`, `decided_at` `2026-10-02T01:00:00Z`
  - one `edit_history` record by C at `2026-10-03T01:00:00Z` changing `expected_attendance` 120→150
  - one `safety_review_history` record by S at `2026-10-04T01:00:00Z`, `changes_requested`, reason `Fire exit blocked`
  - one reassignment request by C at `2026-10-05T01:00:00Z`, reason `Leaving the team`
  - no `event_history` rows
- **Steps:**
  1. `rpc("backfill_event_history", {"p_event_id": E})` on the `events` schema.
  2. Run step 1 again.
  3. `GET /internal/events/E/history`.
  4. Delete everything created.
- **Test data:** As above.
- **Expected:** 3 → exactly five entries, every one with `details.backfilled: true`, newest first:
  | `action` | `actor_id` | `occurred_at` |
  | --- | --- | --- |
  | `reassignment_requested` | C | `2026-10-05T01:00:00Z` |
  | `safety_changes_requested` | S | `2026-10-04T01:00:00Z` |
  | `edited` | C | `2026-10-03T01:00:00Z` |
  | `request_approved` | null (who decided was never stored) | `2026-10-02T01:00:00Z` |
  | `submitted` | O | `2026-10-01T01:00:00Z` |

  Step 2 adds nothing.
- **Actual:** The first backfill added 5 entries, the second 0; the five came back newest first with the expected actors and times, all `backfilled`.
- **Status:** Pass
- **Evidence:** tests/integration/atomic/events/test_s82.py::test_backfill_rebuilds_existing_history_once; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), S-82 SQL applied to both projects; full integration run 96 passed, 5 skipped; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## S-59 — Request Event Changes (confirmed specification)

Latest S-59 execution: 2026-10-30, rebased `S-59/request-event-changes` on `origin/sprint4` d1f6d8b. Developer confirmed SQL applied in DEV and TEST. Fresh `.env.test` stack matched TEST Supabase; full integration suite: 104 passed, 5 skipped.

## TC-EVENTS-201 — proposal SQL persists separately and enforces one pending row

- **Scenario:** The Events-owned table, grants and unique pending constraint work against real Supabase.
- **Pre-conditions:** Fresh `.env.test` stack; S-59 addition to `backend/sql/events.sql` applied to the test project, `events` exposed and granted; temporary O and C accounts; submitted E owned by O and assigned to C.
- **Steps:** 1. Through Kong, O proposes attendance 120→150. 2. Read E and the request as O and C. 3. Attempt a second pending proposal and direct concurrent inserts. 4. Inspect the stored actor, timestamp, baseline and status. 5. Delete request, E and accounts.
- **Test data:** E `Autumn Forum`; attendance 120→150; O/C are `spm-test-*` users.
- **Expected:** First POST `201`; E stays at 120 and its status/assignment are unchanged. Proposal persists after reload with O's Auth ID, server timestamp, baseline 120, proposed 150, pending status. A second/concurrent insert fails safely with one pending row; cleanup leaves no rows.
- **Actual:** Proposal persisted separately from the unchanged event; the duplicate and concurrent insert checks left one pending row and cleanup completed.
- **Status:** Pass
- **Evidence:** `tests/integration/atomic/events/test_s59.py::test_change_request_is_stored_separately_and_one_pending_is_enforced` and `::test_stale_event_baseline_cannot_be_stored_as_a_change_request`; full integration suite 104 passed, 5 skipped on 2026-10-30.
