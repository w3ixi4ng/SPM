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

## TC-EVENTREGISTRATIONS-103 — registering puts one confirmation in the Attendee's notifications

- **Scenario:** A registration through Kong stores a confirmation the
  Attendee can read, and a refused second attempt adds none (S-49 AC1–AC3).
  Also proves the `registration_confirmation` kind is allowed by the real
  `notifications.notifications` constraint.
- **Pre-conditions:** Fresh `.env.test` stack, as TC-EVENTREGISTRATIONS-101,
  with the S-49 `backend/sql/notifications.sql` applied to the test project.
  Through the admin client: temporary Organiser O; confirmed event P owned by
  O, registration open from yesterday to tomorrow (SGT), no confirmed venue;
  temporary Attendee A with name "S-49 Test Attendee".
- **Steps:**
  1. As A, `POST /api/event-registrations/events/P/registration`.
  2. As A, `POST` the same again.
  3. As A, `GET /api/notifications`.
  4. Delete the notification, registration, event and accounts.
- **Test data:** As above; emails `spm-test-*`.
- **Expected:** 1 → `201`. 2 → `409` "You're already registered for this
  event." 3 → `200`, exactly one row with `kind`
  `registration_confirmation`, `event_id` P, and a `message` starting
  "Registration confirmed: {P's name}," and containing "venue to be
  confirmed", "Name: S-49 Test Attendee." and "Email: {A's email}.". 4 leaves
  no rows.
- **Actual:** `201`; second attempt `409` "You're already registered for this event."; the inbox held exactly one `registration_confirmation` for P, starting "Registration confirmed: {P's name}, " with "venue to be confirmed", A's name and email; no rows remained.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_registrations/test_app.py::test_registering_puts_one_confirmation_in_the_attendees_notifications`; `.env.test` stack recreated with `--build` immediately before (users, events, registrations, notifications verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-49/registration-confirmation-notification`; S-49 SQL applied to dev and test; full `tests/integration`: 79 passed, 5 skipped
