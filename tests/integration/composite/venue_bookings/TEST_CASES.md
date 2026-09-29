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
- **Actual:** —
- **Status:** Blocked — The S-30 section of `backend/sql/bookings.sql` has not been applied to the test project yet, so this case cannot run.
- **Evidence:** `tests/integration/composite/venue_bookings/test_availability.py::test_the_calendar_reflects_a_hold_a_confirmed_booking_and_a_block_through_kong` (not run)
