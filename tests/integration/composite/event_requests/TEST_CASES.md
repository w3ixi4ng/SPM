# Test cases — event_requests service (integration)

Covers `tests/integration/composite/event_requests/test_app.py`: the real
composite service in Docker, calling the real `events` and `users` services,
against the test Supabase project. Proves the three services agree on shapes
the unit tests cannot check, because their fakes agree with everything.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/composite/event_requests` |
| Last run | 2026-09-24, developer's local stack |
| Environment | `.env.test` test Supabase project; `events` and `users` schemas applied, granted, and exposed; full stack up via docker compose |
| Result | 12 passed |

Two real bugs surfaced and were fixed getting to a clean run, neither in the
feature itself:

1. **The pool of coordinators is whatever currently exists in the project**,
   not only the accounts a given test creates — a coordinator left over from
   manual testing or an earlier run was still "free" and won the assignment
   instead of the request being rejected (first hit on TC-EVENTREQUESTS-102).
   Fixed by having every case account for the *whole* pool — blocking or
   exempting every coordinator that exists, not only its own fixtures — via
   `conftest.py`'s `all_coordinator_ids`/`block_other_coordinators`.
2. **`block_other_coordinators` itself had a dict-merge bug**: its insert
   dict set `name`/`purpose`/`expected_attendance`/`venue` explicitly, then
   spread `**window` last — and a real caller's `window` (`SUBMITTED`) has
   its own `name` key too, so the spread silently clobbered the explicit
   ones. Every "blocking" event ended up named after the request itself
   instead of "Blocking booking for ...", which TC-EVENTREQUESTS-102's own
   final assertion caught. Fixed by pulling only the four date/time keys out
   of `window` instead of spreading the whole dict.

Also needed a local fix unrelated to test code: `.env.test` was missing
`EVENT_REQUESTS_SERVICE_PORT`, so Docker published the container on a random
host port instead of `8100` — every test hitting `BASE_URL` directly (not
through Kong) got `ConnectionRefused` until that was added.

Verified runnable twice in a row.

## TC-EVENTREQUESTS-101 — a free coordinator is assigned and visible on the event

- **Scenario:** End-to-end: one seeded coordinator with no assigned events,
  one organiser submitting a request, against real Supabase rows.
- **Pre-conditions:** `.env.test` targets the throwaway project; `events` and
  `users` schemas applied, granted and exposed; a temporary Auth user with
  role `event_coordinator` and one with role `event_organiser` are created for
  the test and removed afterwards; the event_requests, events, and users
  services are running; every *other* coordinator that already exists in the
  project is given a covering booking so only the seeded one is free.
- **Steps:** 1. Sign in as the organiser. 2. `POST /event-requests` with a
  complete submitted payload for a window with no existing events. 3.
  `GET /events/{id}` on the events service directly, authenticated as the
  organiser.
- **Test data:** Window `2026-11-05 09:00`–`11:00`.
- **Expected:** Step 2 returns `201` with `assigned_coordinator_id` set to the
  seeded coordinator's id; step 3's row carries the same
  `assigned_coordinator_id`.
- **Actual:** `201`, assigned to the seeded coordinator; step 3 matched.
- **Status:** Pass
- **Evidence:** `test_app.py::test_free_coordinator_is_assigned_and_visible_on_the_event`

## TC-EVENTREQUESTS-102 — a fully booked coordinator pool rejects the submission

- **Scenario:** Every coordinator that exists in the project — not only the
  one this test seeds — already has a submitted event covering the requested
  window, so the request is refused and nothing is written.
- **Pre-conditions:** As TC-EVENTREQUESTS-101, except every coordinator
  currently in the project (found via the Auth admin listing, the same set
  `GET /users/coordinators` would return) is given a covering booking,
  including the seeded one.
- **Steps:** 1. Sign in as the organiser. 2. `POST /event-requests` with a
  payload whose window overlaps every coordinator's existing event. 3.
  `GET /events` on the events service, authenticated as the organiser.
- **Test data:** Window `2026-11-05 09:00`–`11:00`.
- **Expected:** Step 2 returns `409`; step 3's list contains no event for
  this attempt — the request was never created.
- **Actual:** First run: `201` — a coordinator account left over from earlier
  manual testing was not blocked. Second run, after blocking the whole pool:
  `409` correctly, but the final assertion still failed — the blocking
  events were all misnamed after `SUBMITTED` itself by the `**window`
  dict-merge bug (see the header). Third run, after fixing that: as
  expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_fully_booked_coordinator_pool_rejects_the_submission`

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
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_every_event_requests_operation_routes_through_kong`

## TC-EVENTREQUESTS-104 — editing the date/time reassigns to a free coordinator

- **Scenario:** End-to-end proof that editing a submitted event's date/time
  moves the assignment when the current coordinator no longer fits, using
  two coordinators each blocked at a different window so the pick at every
  step is forced rather than left to the random tie-break.
- **Pre-conditions:** As TC-EVENTREQUESTS-101, plus a second seeded
  coordinator; coordinator B has an existing submitted event covering the
  window the request will initially be submitted for; coordinator A has one
  covering the window the request will later be edited into; every other
  coordinator already in the project is given a covering booking at *both*
  windows, so a third, unrelated account can never be the one picked.
- **Steps:** 1. Sign in as the organiser. 2. `POST /event-requests` for the
  initial window. 3. `PATCH /event-requests/{id}` moving the window to the
  one A is blocked at.
- **Test data:** Initial window `2026-11-05 09:00`–`11:00` (B blocked here);
  edited window `13:00`–`15:00` (A blocked here).
- **Expected:** Step 2 returns `201` assigned to A (the only one free
  initially). Step 3 returns `200`, `start_time` updated to `13:00:00`, and
  `assigned_coordinator_id` now B (the only one free at the new window).
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_editing_the_datetime_reassigns_when_the_current_coordinator_now_conflicts`
