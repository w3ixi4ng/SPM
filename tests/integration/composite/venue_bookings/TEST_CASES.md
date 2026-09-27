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
| Last run | 2026-09-27, branch `S-36/submit-venue-booking-request` at `665c7b3` |
| Environment | `.env.test` test Supabase project; `users`, `events` (with every S-36 migration, including dropping the accessibility notes), `venues` and `bookings` (with the cabaret removal and the `special_requirements` rename) applied, granted and exposed; full stack recreated with `docker compose --env-file .env.test up -d --build --wait` immediately before, containers confirmed on the test project |
| Result | 2 passed (20 across `tests/integration`), twice consecutively |

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