# Test cases — event_registrations composite (integration)

Covers `tests/integration/composite/event_registrations/test_app.py`: the
composite on port 8104 and through Kong, calling the real events, bookings,
venues, users and registrations services against the test Supabase project.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/composite/event_registrations` |
| Last run | 2026-10-25, branch `S-51/configure-registration-and-open-close-period`, pre-commit working tree |
| Environment | `.env.test` test Supabase project with the S-51 SQL applied, `registrations` exposed; full stack recreated with `--build` immediately before |
| Result | 1 passed in this suite |

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
  "Registration opens on …" naming Q's opening. 3 → `201`. 4 → `200` with
  `"registered": true`. 5 leaves no rows.
- **Actual:** Public read `200` with the period and no `organiser_id`; the early attempt `409` "Registration opens on …"; registering `201`; the status read `registered: true`; no rows remained.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_registrations/test_app.py::test_public_view_blocked_attempt_and_a_real_registration`; `.env.test` stack recreated with `--build` immediately before (events, users, registrations verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-51/configure-registration-and-open-close-period`; S-51 SQL applied to the test project
