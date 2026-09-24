# Test cases — event_requests service (integration)

Covers `tests/integration/composite/event_requests/test_app.py`: the real
composite service in Docker, calling the real `events` and `users` services,
against the test Supabase project. Proves the three services agree on shapes
the unit tests cannot check, because their fakes agree with everything.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/composite/event_requests` |
| Last run | Not yet run |
| Environment | Not yet run |
| Result | Not yet run |

## TC-EVENTREQUESTS-101 — a free coordinator is assigned and visible on the event

- **Scenario:** End-to-end: one seeded coordinator with no assigned events,
  one organiser submitting a request, against real Supabase rows.
- **Pre-conditions:** `.env.test` targets the throwaway project; `events` and
  `users` schemas applied, granted and exposed; a temporary Auth user with
  role `event_coordinator` and one with role `event_organiser` are created for
  the test and removed afterwards; the event_requests, events, and users
  services are running.
- **Steps:** 1. Sign in as the organiser. 2. `POST /event-requests` with a
  complete submitted payload for a window with no existing events. 3.
  `GET /events/{id}` on the events service directly, authenticated as the
  organiser.
- **Test data:** Window `2026-11-05 09:00`–`11:00`.
- **Expected:** Step 2 returns `201` with `assigned_coordinator_id` set to the
  seeded coordinator's id; step 3's row carries the same
  `assigned_coordinator_id`.
- **Actual:** Not yet run.
- **Status:** Blocked — needs `events.sql` and `users.sql` applied, granted,
  and exposed in the test project, plus the new internal endpoints built.
- **Evidence:** —

## TC-EVENTREQUESTS-102 — a fully booked coordinator pool rejects the submission

- **Scenario:** Every seeded coordinator already has a submitted event
  covering the requested window, so the request is refused and nothing is
  written.
- **Pre-conditions:** As TC-EVENTREQUESTS-101, plus the seeded coordinator has
  an existing submitted event covering the requested window.
- **Steps:** 1. Sign in as the organiser. 2. `POST /event-requests` with a
  payload whose window overlaps the coordinator's existing event. 3.
  `GET /events` on the events service, authenticated as the organiser.
- **Test data:** The coordinator's existing event window and an overlapping
  request window.
- **Expected:** Step 2 returns `409`; step 3's list contains no event for
  this attempt — the request was never created.
- **Actual:** Not yet run.
- **Status:** Blocked — same as TC-EVENTREQUESTS-101.
- **Evidence:** —

## TC-EVENTREQUESTS-103 — every event-requests operation routes through Kong

- **Scenario:** The browser-facing path works the same as calling the service
  directly.
- **Pre-conditions:** As TC-EVENTREQUESTS-101; Kong running with the
  `/api/event-requests` route configured.
- **Steps:** Repeat TC-EVENTREQUESTS-101's step 2 against
  `http://localhost:8000/api/event-requests` instead of the service's own
  port.
- **Test data:** As TC-EVENTREQUESTS-101.
- **Expected:** Same `201` and `assigned_coordinator_id` as calling the
  service directly.
- **Actual:** Not yet run.
- **Status:** Blocked — same as TC-EVENTREQUESTS-101, plus the Kong route
  needs adding.
- **Evidence:** —

## TC-EVENTREQUESTS-104 — editing the date/time reassigns to a free coordinator

- **Scenario:** End-to-end proof that editing a submitted event's date/time
  moves the assignment when the current coordinator no longer fits, using
  two coordinators each blocked at a different window so the pick at every
  step is forced rather than left to the random tie-break.
- **Pre-conditions:** As TC-EVENTREQUESTS-101, plus a second seeded
  coordinator; coordinator B has an existing submitted event covering the
  window the request will initially be submitted for; coordinator A has one
  covering the window the request will later be edited into.
- **Steps:** 1. Sign in as the organiser. 2. `POST /event-requests` for the
  initial window. 3. `PATCH /event-requests/{id}` moving the window to the
  one A is blocked at.
- **Test data:** Initial window `2026-11-05 09:00`–`11:00` (B blocked here);
  edited window `13:00`–`15:00` (A blocked here).
- **Expected:** Step 2 returns `201` assigned to A (the only one free
  initially). Step 3 returns `200`, `start_time` updated to `13:00:00`, and
  `assigned_coordinator_id` now B (the only one free at the new window).
- **Actual:** Not yet run.
- **Status:** Blocked — same as TC-EVENTREQUESTS-101, plus the recheck-on-edit
  logic and the internal PATCH route.
- **Evidence:** —
