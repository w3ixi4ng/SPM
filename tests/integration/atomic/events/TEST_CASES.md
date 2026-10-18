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
- **Actual:** Not run: the S-17 SQL (events.sql, and the S-78 block of bookings.sql) is not yet applied to the test Supabase project.
- **Status:** Blocked
- **Evidence:** `test_s17.py::test_status_and_signoff_columns`
