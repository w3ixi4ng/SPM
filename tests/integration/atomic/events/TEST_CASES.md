# Test cases — events service (integration)

Covers `tests/integration/atomic/events/test_app.py`: authenticated round trips
through the events service directly and through Kong, against the test Supabase
project.

| | |
| --- | --- |
| Suite | Start the events service against `.env.test`, then `pytest tests/integration/atomic/events` |
| Last run | 2026-09-16, working tree of branch `S-07.T-01/event-request-form` |
| Environment | `.env.test` test Supabase project; `events` schema applied, granted and exposed; users, events, and Kong healthy in Docker |
| Result | Blocked -- `backend/sql/events.sql` now defines `start_date`/`end_date` in place of `event_date`; the dev and test Supabase projects still have the old column and need the schema rebuilt (see the file's rebuild instructions) before this suite can run again |

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
  to `submitted`; cleanup removes every created record.
- **Actual:** Not run this pass -- the test now submits `start_date`/`end_date`
  (see `backend/sql/events.sql`), which does not exist in either Supabase
  project's `events.events` table yet.
- **Status:** Blocked
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
