# Test cases — venue_bookings service (integration)

Covers `tests/integration/composite/venue_bookings/test_app.py`: the real
composite in Docker, calling the real `users`, `events`, `venues` and
`bookings` services against the test Supabase project. The unit fakes agree
with every shape. These cases prove the five services actually agree: the
venue's `operating_hours` and `capacity` as the venues service really returns
them, the event's `planning` status passing the table's check constraint,
and the gateway route.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/composite/venue_bookings` |
| Last run | 2026-09-29, branch `S-37/approve-reject-booking-with-reason-or-alternative`, pre-commit working tree |
| Environment | `.env.test` test Supabase project with all repository SQL, including the S-37 decision columns and constraints, applied, granted and exposed; full stack recreated immediately before |
| Result | 4 venue-bookings integration cases passed; 33 passed across `tests/integration` |

**Story:** S-36 Submit venue booking request.

**Shared pre-conditions.**
- `.env.test` points at the throwaway project.
- The `users`, `events`, `venues` and `bookings` schemas are applied,
  granted and exposed, including the S-36 change to `events.sql` that allows
  `planning`.
- The stack was started with `--env-file .env.test` immediately before the
  run.
- For each case, the admin client creates:
  - a `event_coordinator` user, a `venue_staff` user and an organiser;
  - a venue `"spm-test Venue <hex>"`, capacity `150`, `projector`,
    `wheelchair_access`, layout `theatre`, open Thursday `08:00`–`20:00`;
  - an event `"spm-test Event <hex>"` owned by the organiser, assigned to the
    coordinator, `status=planning`, `2026-11-12 09:00`–`18:00`,
    `expected_attendance` `120`, `room_layout` `theatre`,
    `required_facilities` `["projector"]`, `required_accessibility`
    `["wheelchair_access"]`, no venue preference.
- Teardown deletes all of these, and any booking made, pass or fail.

## TC-VENUEBOOKINGS-101 — a Coordinator's request reaches Venue Staff's pending list and stays visible to the Coordinator

- **Scenario:** AC1 to AC4 together, across every real service.
- **Pre-conditions:** Shared.
- **Steps:**
  1. Sign in as the coordinator.
  2. `POST http://localhost:8000/api/venue-bookings` for the event and
     venue, `2026-11-12` `09:00`–`12:00`.
  3. Read `bookings.bookings` by the returned id with the admin client.
  4. Read the event with the admin client.
  5. As the coordinator,
     `GET http://localhost:8000/api/venue-bookings?event_id={event}`.
  6. Sign in as the venue staff user.
  7. `GET http://localhost:8000/api/venue-bookings/pending`.
- **Test data:** As above.
- **Expected:**
  - Step 2: `201`, `status: "pending"`.
  - Step 3: one row. `event_name`, `expected_attendance` (`120`) and
    `venue_name` match the seeded rows, `room_layout`,
    `required_facilities` and `required_accessibility` are the event's, and
    `coordinator_email` is the coordinator's.
  - Step 4: still `status=planning`.
  - Step 5: `200`, exactly one booking: the id from step 2, `status:
    "pending"`.
  - Step 7: `200`, and the list contains the booking id from step 2.
- **Actual:** `201` pending through Kong; the stored row carried the seeded event, venue and coordinator details and the event's layout, facilities and accessibility; the event stayed `planning`; the coordinator's list for the event held exactly that booking, `pending`; it was in Venue Staff's pending list.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_coordinators_request_reaches_venue_staff_and_stays_visible_to_the_coordinator`

## TC-VENUEBOOKINGS-102 — an unsuitable venue is refused against real venue data, and nothing is saved

- **Scenario:** Capacity and opening-hours checks read the venue exactly as
  the venues service returns it, not as a fake shapes it.
- **Pre-conditions:** Shared, with the event's `expected_attendance`
  updated to `200` by the admin client.
- **Steps:**
  1. Sign in as the coordinator.
  2. `POST http://localhost:8101/venue-bookings` for `2026-11-12`
     `07:00`–`10:00`.
  3. Count `bookings.bookings` rows for this event with the admin client.
- **Test data:** As above.
- **Expected:**
  - Step 2: `422`, with `booking_date`, `operating_hours` and
    `expected_attendance` in `errors`.
  - Step 3: `0`.
- **Actual:** `422` with `booking_date`, `operating_hours` and `expected_attendance` in `errors`; no row saved.
- **Status:** Pass
- **Evidence:** `test_app.py::test_an_unsuitable_venue_is_refused_against_real_venue_data`

## S-28 approved coverage

Latest S-28 execution: 2026-09-27; base `0d27acc` plus S-28 working changes; freshly recreated Docker stack using approved `.env.test`. Existing TC-VENUEBOOKINGS-101 also hit the same schema-cache blocker; TC-VENUEBOOKINGS-102 passed.

### TC-VENUEBOOKINGS-103 ? Venue edits preserve history and affect new requests

- Scenario: Venue edits preserve history and affect new requests
- Pre-conditions: Approved test stack; event attendance 120 requiring projector and wheelchair_access; suitable venue capacity 150.
- Steps: 1. Submit booking; PATCH venue capacity=100, facilities=[], accessibility=[]; submit again; read old booking.
- Test data: Values specified above; existing shared fixtures supply remaining required fields.
- Expected: Edit succeeds; new request 422 for all three mismatches; original booking identical and remains listed.
- Actual: Initial booking creation returned 502. Bookings logs report PGRST204: accessibility_requirements column missing from schema cache. History assertions could not execute.
- Status: Blocked
- Evidence: `tests/integration/composite/venue_bookings/test_app.py::test_venue_edit_preserves_history_and_new_requests_use_saved_values`; local pytest and bookings container logs.


### TC-VENUEBOOKINGS-104 ? updated venue values govern new requests

- Scenario: Verify existing suitability without requiring a successful booking insert.
- Pre-conditions: Approved test stack; world fixture event expects 120, projector and wheelchair_access.
- Steps: 1. Staff PATCH capacity=100, facilities=[], accessibility=[]. 2. Coordinator submits for 2026-11-12 09:00-12:00.
- Test data: World fixture venue starts with capacity 150 and both required features.
- Expected: Update 200; submission 422 naming all three conflicts; no booking stored.
- Actual: PATCH succeeded; new submission returned 422 for capacity, facilities and accessibility; no booking was stored.
- Status: Pass
- Evidence: `tests/integration/composite/venue_bookings/test_app.py::test_new_request_uses_updated_venue_values`; local .env.test execution.

## S-37 confirmed specifications

Confirmed by the developer on 2026-09-28, with no reassignment exception.
S-37 execution: 2026-09-29; base c4934e9 merged with S-37 plus conflict-resolution changes on
S-37/approve-reject-booking-with-reason-or-alternative.
Windows, Python 3.14, Node.js; existing results above describe earlier coverage.
Approval stores `status=confirmed`; rejection stores `status=rejected`.
Decision metadata: `decision_reason`, `decision_alternative`, `decided_by`, `decided_at`.
B means the saved booking fixture; S means the authenticated deciding staff UUID.
No S-33 hold behaviour or S-38 cross-request overlap guarantee is included.

### TC-VENUEBOOKINGS-105 — Saved decisions reach the permitted Coordinator through real services

- **Scenario:** Saved decisions reach the permitted Coordinator through real services (AC1, AC2, AC3).
- **Pre-conditions:** Fresh approved test stack with additive SQL; real test users/events/venues/bookings, isolated fixture cleanup.
- **Steps:** 1. Submit two requests as C1.
  2. Decide as staff: approve one, reject one with reason and alternative.
  3. Reload pending and event requests through gateway.
  4. Reassign test event to C2 using controlled fixture setup; read as C1,C2,C3.
- **Test data:** reason='Room needs repairs'; alternative='Try Studio C on Friday'; C1 original, C2 new assigned, C3 unrelated.
- **Expected:** Decided rows leave pending list; Coordinator reads Confirmed/Rejected with exact saved explanation. The original requester loses access after reassignment, as before; currently assigned Coordinators retain access; unrelated Coordinators are denied. Requester access after reassignment remains an open team requirement. Requests and event/venue records are not rewritten by decision.
  *Clarified 2026-10-09:* "not rewritten" means every field the event and
  venue rows had before keeps its value. A column added to the shared test
  project mid-run (CI on S-76 failed when `events.events` gained
  `previous_coordinator_id` and `coordinator_assignment_version` outside the
  repo's SQL) is not a rewrite.
- **Actual:** Approval and rejection passed through Kong and the real services; decided requests left the pending list; the permitted Coordinator saw Confirmed and Rejected with the exact saved explanation. Existing reassignment access remained unchanged, and event and venue records were not rewritten.
- **Status:** Pass
- **Evidence:** `test_decision.py::test_saved_decisions_visible_only_under_existing_event_access`; local `.env.test` execution.

## S-30 — view venue availability calendar

Story: S-30 View venue availability calendar.
Confirmed by the developer on 2026-09-30. Not yet executed.
**Blocked** until the S-30 section of `backend/sql/bookings.sql` has been run
in the test project.

### TC-VENUEBOOKINGS-106 — The calendar reflects a hold, a confirmed booking and a block through Kong

- **Scenario:** The real services and the gateway route agree on the
  calendar (AC1, AC2, AC3).
- **Pre-conditions:** A fresh `.env.test` stack. A Coordinator with three
  planning events whose windows cover `2026-11-12` `08:00`–`18:00`. A Venue
  Staff account. A test venue open `mon`–`fri` `08:00`–`18:00`.
- **Steps:**
  1. As the Coordinator, `GET /api/venue-bookings/availability` for
     `2026-11-11`–`2026-11-30`. It returns no entries.
  2. Submit A (`2026-11-12` `09:00`–`12:00`) and B (`14:00`–`16:00`). Staff
     confirm A.
  3. Submit C (`15:00`–`17:00`). Staff reject B, then C is submitted again.
  4. Staff `POST /api/venue-bookings/blocks` for `2026-11-13`–`2026-11-16`,
     reason `safety`.
  5. Call the availability endpoint again after each step.
- **Expected:**
  - After step 2: one `confirmed` and one `held` entry.
  - Step 3: C first gets `409` "… is already tentatively held on 12 Nov 2026
    from 14:00 to 16:00." After B is rejected, C returns `201`, and the
    calendar shows `confirmed` A and `held` C.
  - After step 4: a `blocked` entry with reason `safety` as well.
  - No response includes an event name.
  - Cleanup deletes every row created.
- **Actual:** Through Kong: empty calendar, then confirmed + held; C refused `409` while B held and accepted after B was rejected; the safety block appeared with no id or note; no event name in any response.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/venue_bookings/test_availability.py::test_the_calendar_reflects_a_hold_a_confirmed_booking_and_a_block_through_kong`; `.env.test` stack recreated immediately before; bookings container verified on the test project's `SUPABASE_URL`; `pytest tests/integration/atomic/bookings tests/integration/composite/venue_bookings`: 14 passed, 0 skipped.

## S-75 — configure venue setup and turnaround time

Story: S-75 Configure Venue Setup and Turnaround Time.
Confirmed by the developer on 2026-10-07. Not yet executed.
**Blocked** until the S-75 section of `backend/sql/venues.sql` has been run
in the test project.

### TC-VENUEBOOKINGS-107 — changing a venue's times flags the new clash and is used for the next request

- **Scenario:** Real services and Kong agree (AC3, AC4).
- **Pre-conditions:** A fresh `.env.test` stack. A Coordinator, Venue Staff,
  a test venue open `thu` 08:00–20:00 with setup and turnaround 0, and two
  planning events. Booking A confirmed 10:00–12:00 and B held 12:30–14:00 on
  2026-11-12.
- **Steps:**
  1. Staff `GET /api/venue-bookings/clashes` for the venue: none.
  2. Staff `PATCH /api/venues/{id}` with `setup_minutes: 30`, `turnaround_minutes: 45`.
  3. Staff list clashes again; the Coordinator lists B's event requests.
  4. The Coordinator requests 12:00–12:30 for another planning event.
- **Expected:** Step 3: the A–B pair is listed, and B carries the clash
  warning. A and B are unchanged in `bookings.bookings`. Step 4: `409` "…in
  use until 12:45." Cleanup deletes every row created.
- **Actual:** Through Kong: no clashes at 0/0; after Staff saved 30/45 the A–B pair was listed and B carried the 10:00 clash; both bookings unchanged; 12:00–12:30 refused "…in use until 12:45."
- **Status:** Pass
- **Evidence:** `tests/integration/composite/venue_bookings/test_setup_turnaround.py::test_new_times_flag_the_clash_and_govern_the_next_request`; `.env.test` stack rebuilt immediately before (venues container on the test project's `SUPABASE_URL`), 2026-10-08; 20 passed.

## S-76 — detect booking conflicts incl. setup and turnaround

Story: S-76 Detect Booking Conflicts incl. Setup and Turnaround.
Confirmed by the developer on 2026-10-09. Executed 2026-10-09.
No schema change: S-76 needs only the S-75 SQL already in `backend/sql/`.

### TC-VENUEBOOKINGS-108 — an overlapping approval is refused by name, and a confirmed clash stays listed for review

- **Scenario:** Real services and Kong agree on the refusal and the review
  list (S-76 AC3, AC5).
- **Pre-conditions:** A fresh `.env.test` stack. Venue Staff, a Coordinator,
  a test venue open `thu` 08:00–20:00 at setup and turnaround 0, three
  planning events. On 2026-11-12: A confirmed 10:00–12:00 ("Alumni talk"),
  C confirmed 13:00–14:00, B pending 12:00–12:45 (none overlapping
  at 0/0, so the rows are valid before step 1).
- **Steps:**
  1. Staff `PATCH /api/venues/{id}` with `setup_minutes: 30`,
     `turnaround_minutes: 45`.
  2. Staff approve B through `/api/venue-bookings/{B}/decision`.
  3. Staff `GET /api/venue-bookings/clashes` (no `venue_id`).
- **Expected:**
  - Step 2: `409` "Can't confirm this booking: it overlaps Alumni talk
    (confirmed), which occupies <venue> on 12 Nov 2026 from 09:30 to 12:45
    (event 10:00–12:00, 30 min setup, 45 min turnaround)." B is still
    pending in `bookings.bookings`.
  - Step 3: the test venue is listed with the A–C pair (both confirmed).
  - A and C are unchanged in `bookings.bookings`. Cleanup deletes every row
    created.
- **Actual:** Through Kong: after Staff saved 30/45, approving B was refused naming A with 09:30–12:45 (venue name as saved on the booking); the A–C confirmed pair was listed with no `venue_id`; A, C confirmed and B pending in `bookings.bookings`.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/venue_bookings/test_booking_conflicts.py::test_an_overlapping_approval_is_refused_by_name_and_the_clash_stays_listed`; `.env.test` stack rebuilt from branch `S-76/detect-booking-conflicts-incl-setup-and-turnaround` at `8e7c69d` immediately before (bookings container on the test project's `SUPABASE_URL`), 2026-10-09. Full suite: 42 passed, 1 failed (this test expected the venue's current name rather than the one saved on the booking; test fixed and rerun: pass), 5 skipped (S-83).

## S-79 — book multiple venues for one event

Story: S-79 Book Multiple Venues for One Event.
Confirmed by the developer on 2026-10-11. Executed 2026-10-11 on branch `S-79/book-multiple-venues-for-one-event` (on top of `43b91d1`).
No schema change: S-79 needs only the SQL already in `backend/sql/`.
For the criteria mapping and the agreed decisions, see the S-79 section of
`tests/unit/composite/venue_bookings/TEST_CASES.md`.

### TC-VENUEBOOKINGS-109 — one event holds bookings at several venues through Kong

- **Scenario:** With real services behind Kong, one event keeps several
  bookings, each is checked on its own, and all are listed with their
  statuses (AC1, AC2, AC3).
- **Pre-conditions:** A fresh `.env.test` stack. A Coordinator assigned to a
  planning event E (`2026-11-12` 09:00–18:00, attendance 120), and Venue
  Staff. Three test venues, all open `thu` 08:00–20:00 with setup and
  turnaround 0: Main Hall (capacity 300), Studio (150) and Seminar Room (40).
  Only held and confirmed rows reserve time (S-33), so Venue Staff hold
  booking 1 before the rest.
- **Steps:** As the Coordinator, through `/api/venue-bookings`:
  1. Request Main Hall, 09:00–17:00; Venue Staff hold it.
  2. Request Studio, 13:00–15:00 (same time, different venue).
  3. Request Seminar Room, 13:00–15:00.
  4. Request Main Hall, 16:00–18:00.
  5. `GET /api/venue-bookings?event_id=E`.
- **Expected:**
  1. `201`, then `200` for the hold.
  2. `201`. In `bookings.bookings`, booking 1 is still `held` with no
     `hold_release_reason`.
  3. `422`, naming capacity (40 < 120).
  4. `409` "… is already tentatively held on …", because the event's own
     booking 1 holds Main Hall.
  5. `200` with exactly bookings 1 (`held`) and 2 (`pending`), both with
     `event_id` E.
  `bookings.bookings` holds exactly two rows for E. Cleanup deletes every
  row created.
- **Actual:** Through Kong: Main Hall `201` and held; Studio at the same time `201` with Main Hall still `held`, no release reason; Seminar Room `422` (40 < 120); Main Hall 16:00–18:00 `409` "…already tentatively held on…"; the list returned exactly the two, held and pending; two rows stored for E.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/venue_bookings/test_multiple_venues.py::test_one_event_holds_bookings_at_several_venues`; `.env.test` stack recreated immediately before (bookings container verified on the test project's `SUPABASE_URL`), 2026-10-11; `pytest tests/integration/atomic/bookings tests/integration/composite/venue_bookings`: 18 passed.

## S-77 — mark venue temporarily unavailable

Story: S-77 Mark Venue Temporarily Unavailable. Confirmed by the developer on 2026-10-12.

Executed 2026-10-12 on branch `S-77/mark-venue-temporarily-unavailable`. Needs, in the test project:
- the S-77 blocks in `backend/sql/bookings.sql`;
- the S-77 change to `backend/sql/notifications.sql` (kind `venue_unavailable`).

For the criteria mapping and the agreed decisions, see the S-77 section of
`tests/unit/composite/venue_bookings/TEST_CASES.md`.

**Changes to existing cases.** TC-VENUEBOOKINGS-106's block gains times. Its
Status resets to Not Executed until re-run.

### TC-VENUEBOOKINGS-110 — marking a period through Kong flags and notifies, and changes nothing else

- **Scenario:** With real services behind Kong, a period over a confirmed
  booking is saved. The booking is identified and flagged, and the event's
  Coordinator gets a persistent notification. The event and the booking are
  unchanged (AC1, AC3, AC4, AC5).
- **Pre-conditions:** The shared pre-conditions. The venue has setup and
  turnaround 0. A confirmed booking K for the event, `2026-11-12`
  `10:00`–`12:00`, created through the service and approved by Venue Staff.
  Snapshot K's row in `bookings.bookings` and the event's row in
  `events.events` with the admin client.
- **Steps:**
  1. As Venue Staff, `POST /api/venue-bookings/blocks`: `2026-11-12` `09:00`
     to `2026-11-12` `13:00`, reason `safety`.
  2. As the Coordinator, `GET /api/notifications`.
  3. As the Coordinator, `GET /api/venue-bookings?event_id=<event>`.
  4. Read K and the event with the admin client again.
- **Expected:**
  1. `201`. `affected_bookings` has exactly K, and
     `"coordinators_notified": true`.
  2. Exactly one notification with `kind` `"venue_unavailable"` and the
     event's id. Its message names the venue, the period and K's date and
     times, ending "needs alternative arrangements."
  3. K with `"requires_alternative_arrangements": true` and the period in
     `unavailable_periods`.
  4. K's row is identical to the snapshot, still `confirmed`. The event's
     row is identical, still `planning`.
  Cleanup deletes the block, K, the notification and the shared fixtures.
- **Actual:** Through Kong: period `201` with exactly K affected and notified true; the Coordinator's inbox had one `venue_unavailable` notification naming the period and K's times; K flagged with the period; K and the event rows identical to their snapshots, still `confirmed` and `planning`.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/venue_bookings/test_unavailable_periods.py::test_marking_a_period_through_kong_flags_and_notifies_and_changes_nothing_else`; `.env.test` stack recreated immediately before (bookings container verified on the test project's `SUPABASE_URL`), 2026-10-12; `pytest tests/integration`: 52 passed, 5 skipped, plus the 2 S-75 helper fixes re-run and passed

### TC-VENUEBOOKINGS-111 — through Kong, a request and a hold inside the period are refused

- **Scenario:** The real services refuse new bookings and holds that overlap
  the period, with the venue's real setup time counted (AC2).
- **Pre-conditions:** The shared pre-conditions. The venue's
  `setup_minutes` is 30. A period on `2026-11-12` from `13:00` to `15:00`,
  saved by Venue Staff. A pending request Q for the event on `2026-11-12`
  `10:00`–`12:00`, made before the period.
- **Steps:**
  1. As the Coordinator, `POST /api/venue-bookings` on `2026-11-12`
     `15:00`–`16:00` (occupied from `14:30`).
  2. As the Coordinator, the same on `2026-11-12` `15:30`–`16:30` (occupied
     from exactly `15:00`).
  3. As Venue Staff, `DELETE` the period, re-create it from `2026-11-12`
     `11:00` to `13:00`, then `POST /api/venue-bookings/{Q}/hold`.
- **Expected:**
  1. `409` "… is unavailable from 12 Nov 2026 13:00 to 12 Nov 2026 15:00."; nothing stored.
  2. `201`.
  3. The hold returns `409` with the period's detail. Q stays `pending` in
     `bookings.bookings`.
  Cleanup deletes everything created.
- **Actual:** Through Kong: `15:00`–`16:00` refused `409` with the period's detail and nothing stored; `15:30`–`16:30` `201`; after re-marking `11:00`–`13:00`, holding Q `409` with that detail and Q still `pending`.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/venue_bookings/test_unavailable_periods.py::test_through_kong_a_request_and_a_hold_inside_the_period_are_refused`; `.env.test` stack recreated immediately before (bookings container verified on the test project's `SUPABASE_URL`), 2026-10-12; `pytest tests/integration`: 52 passed, 5 skipped, plus the 2 S-75 helper fixes re-run and passed

### TC-VENUEBOOKINGS-112 — hold expiry is notified and released through Kong

- **Scenario:** The complete S-81 service path stores a required expiry, informs the Coordinator before it occurs, and removes the expired hold from availability.
- **Pre-conditions:** `.env.test` stack; S-81 bookings and notifications migrations applied in the test project.
- **Steps:** Request a venue through Kong; place a hold with an expiry as Venue Staff; read the Coordinator inbox; move the expiry into the past; load availability through Kong.
- **Test data:** 12 Nov 2026, 09:00–12:00; expiry one hour ahead and then one second behind the current time.
- **Expected:** The hold contains its expiry; exactly one `venue_hold_expiry` notification names the tentative hold; availability has no live booking after expiry; storage retains the row as pending with release reason `expired` and a release timestamp.
- **Actual:** Kong stored the expiry and one Coordinator notice; after expiry,
  the calendar had no live entry and storage retained `pending/expired` audit data.
- **Status:** Pass
- **Evidence:** `test_hold_expiry.py::test_hold_expiry_is_notified_and_released_through_kong`; `.env.test` stack recreated immediately before, 2026-10-13; full `pytest tests/integration`: 56 passed, 5 skipped.
