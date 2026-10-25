# Test cases — event_registrations composite (integration)

Covers `tests/integration/composite/event_registrations/test_app.py`: the
composite on port 8104 and through Kong, calling the real events, bookings,
venues, users and registrations services against the test Supabase project.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/composite/event_registrations` |
| Last run | 2026-10-25, branch `S-48/register-for-event`, pre-commit working tree |
| Environment | `.env.test` test Supabase project with the S-51 SQL applied, `registrations` exposed; full stack recreated with `--build` immediately before |
| Result | 2 passed in this suite |

## TC-EVENTREGISTRATIONS-101 — public view, blocked attempt and a real registration through Kong

- **Scenario:** Every service and the gateway agree end to end (S-51 AC3, AC4, AC5).
- **Pre-conditions:** Fresh `.env.test` stack; `events.sql` (S-51 block) and
  `registrations.sql` applied, exposed and granted. Through the admin client:
  confirmed event P with registration open from yesterday to tomorrow (SGT);
  confirmed event Q whose registration opens in 7 days. A temporary Attendee
  account A.
- **Steps:**
  1. With no cookie, `GET /api/event-registrations/events/P`.
  2. As A, `POST /api/event-registrations/events/Q/registration`.
  3. As A, `POST /api/event-registrations/events/P/registration`.
  4. As A, `GET /api/event-registrations/events/P/registration`.
  5. Delete the events, registrations and account.
- **Expected:** 1 → `200` with P's public fields and period. 2 → `409`
  "Registration hasn't opened yet. It's open from {Q's opening} to {Q's closing}."
  (S-48 AC2). 3 → `201`. 4 → `200` with
  `"registered": true`. 5 leaves no rows.
- **Actual:** Public read `200` with the period and no `organiser_id`; the early attempt `409` "Registration hasn't opened yet. It's open from … to …"; registering `201`; the status read `registered: true`; no rows remained.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_registrations/test_app.py::test_public_view_blocked_attempt_and_a_real_registration`; `.env.test` stack recreated with `--build` immediately before (users, events, registrations verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-48/register-for-event`

## TC-EVENTREGISTRATIONS-102 — a registration shows for the Attendee and for the event's Organiser

- **Scenario:** One registration through Kong is recorded against both the Attendee and the event (S-48 AC3).
- **Pre-conditions:** Fresh `.env.test` stack, as TC-EVENTREGISTRATIONS-101.
  Through the admin client: temporary Organiser O and a second Organiser O2;
  confirmed event P owned by O with registration open from yesterday to
  tomorrow (SGT); temporary Attendee A with name "S-48 Test Attendee".
- **Steps:**
  1. As A, `POST /api/event-registrations/events/P/registration`.
  2. As A, `GET /api/event-registrations/me/registrations`.
  3. As O, `GET /api/event-registrations/events/P/attendees`.
  4. As O2, `GET /api/event-registrations/events/P/attendees`.
  5. Delete the event, registration and accounts.
- **Test data:** As above; emails `spm-test-*`.
- **Expected:** 1 → `201`. 2 → `200`, a list containing P with its name and
  a `registered_at`. 3 → `200`, `count` 1 and one attendee with A's id, name
  and email. 4 → `404`. 5 leaves no rows.
- **Actual:** `201`; A's list held P with its name and `registered_at`; O saw `count` 1 with A's id, name and email; O2 → `404`; no rows remained.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_registrations/test_app.py::test_a_registration_shows_for_the_attendee_and_for_the_events_organiser`; `.env.test` stack recreated with `--build` immediately before (users, events, registrations verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-48/register-for-event`

## TC-EVENTREGISTRATIONS-103 — a full event turns the next Attendee to the waiting list (S-50)

- **Scenario:** End to end through Kong: the cap is the event's expected attendance, the next Attendee joins the waiting list, and the Organiser sees them (S-50 AC1, AC2, AC3).
- **Pre-conditions:** Fresh `.env.test` stack; S-50 SQL (events and
  registrations) applied and `registrations` exposed. Through the admin
  client: Organiser O; confirmed event P owned by O with
  `expected_attendance` 1 and registration open from yesterday to tomorrow
  (SGT); Attendees A and B.
- **Steps:**
  1. As A, `POST /api/event-registrations/events/P/registration`.
  2. Anonymously, `GET /api/event-registrations/events/P`.
  3. As B, `POST /api/event-registrations/events/P/registration`.
  4. As B, `POST /api/event-registrations/events/P/waiting-list`.
  5. As B, `GET /api/event-registrations/events/P/registration`.
  6. As O, `GET /api/event-registrations/events/P/attendees`.
  7. As O, `PUT /api/events/P/registration-closure`; as B, `POST .../registration` again.
  8. Delete the rows and accounts.
- **Test data:** Emails `spm-test-*`.
- **Expected:** 1 → `201`. 2 → `"is_full": true`. 3 → `409` "This event is
  full. You can join the waiting list.". 4 → `201`. 5 → `"waitlisted": true`.
  6 → `count` 1 (A), `waiting_list` holding B. 7 → `200`, then `409` "The
  organiser has closed registration for this event.". 8 leaves no rows.
- **Actual:** `201`; `is_full` true; `409` full message; waiting list `201`; `waitlisted` true; O saw A as the one attendee and B on the waiting list; close `200` then `409` closed message; no rows remained.
- **Status:** Pass
- **Evidence:** tests/integration/composite/event_registrations/test_app.py::test_a_full_event_turns_the_next_attendee_to_the_waiting_list; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTREGISTRATIONS-104 — waitlisted Attendees see their place in line (S-52)

- **Scenario:** Through Kong against the test project: two Attendees join a full event's waiting list in turn, each sees their place, and the dashboard list tells waiting from confirmed (S-52 AC1, AC2, AC3).
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-103: fresh `.env.test` stack; Organiser O; confirmed event P owned by O with `expected_attendance` 1 and registration open yesterday to tomorrow (SGT); Attendees A, B and C. No SQL change for S-52.
- **Steps:**
  1. As A, `POST /api/event-registrations/events/P/registration`.
  2. As B, then as C, `POST /api/event-registrations/events/P/waiting-list`.
  3. As B, then as C, `GET /api/event-registrations/events/P/registration`.
  4. As C, `GET /api/event-registrations/me/registrations`.
  5. As A, `GET /api/event-registrations/me/registrations`.
- **Test data:** As above; accounts and rows removed afterwards.
- **Expected:** 1 → `201`. 2 → `201` with `"position": 1`, then `201` with `"position": 2`. 3 → B `"waitlisted": true, "position": 1`; C `"waitlisted": true, "position": 2`. 4 → one row for P, `"status": "waitlisted", "position": 2`. 5 → one row for P, `"status": "confirmed", "position": null`.
- **Actual:** A `201`; B and C joined with positions 1 and 2, and their status read back 1 and 2; C's dashboard list held P `waitlisted` at 2; A's held P `confirmed`, position null.
- **Status:** Pass
- **Evidence:** tests/integration/composite/event_registrations/test_app.py::test_waitlisted_attendees_see_their_place_in_line; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), 2026-10-26, branch `S-52/join-waiting-list` (on S-50 `a3011b3`), pre-commit working tree
