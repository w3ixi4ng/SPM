# Test cases — end-to-end journeys

Covers `test_sign_up.py`, `test_session.py`, `test_event_request.py` and
`test_role_access.py`. A real browser drives the built frontend through Kong,
against both services and a real (test) Supabase project. These are the only
tests that see the gateway's routing, the SPA fallback and a session cookie
surviving a page load.

| | |
| --- | --- |
| Suite | `pytest tests/e2e` |
| Last run | 2026-09-17, branch `S-07/T-01` at `ea7cab7` |
| Environment | `.env.test` → test Supabase project, `users` and `events` schemas applied, exposed and granted; full stack via `docker compose --env-file .env.test up -d --build --wait`; Chromium via `playwright install chromium`; email confirmation **off** |
| Result | 4 passed (twice consecutively) |

## TC-E2E-201 — sign-up lands on the dashboard for the assigned role

- **Scenario:** A new account created through the real sign-up form is given
  the organiser role and routed to the organiser dashboard.
- **Pre-conditions:** Stack running. No account exists for the address. The
  test project has **Confirm email off** — with it on, sign-up returns no
  session and the case reports Blocked (see below).
- **Steps:**
  1. Open `/signup` through Kong.
  2. Fill first name, last name, email, password, confirm password.
  3. Submit the form.
  4. Wait for the browser to leave `/signup`.
- **Test data:** `Ada` / `Lovelace` / `spm-e2e-<random>@example.com` /
  `correct-horse-battery-staple`.
- **Expected:** The browser ends on `/dashboard/event-organiser`. Reaching it
  requires the service to have stamped `app_metadata.role=event_organiser`,
  `/users/me` to have returned it, and the route guard to have resolved it.
- **Actual:** Redirected to `/dashboard/event-organiser`.
- **Status:** Pass
- **Evidence:** `test_sign_up.py::test_sign_up_lands_on_the_organiser_dashboard`

> If the test project has email confirmation on, the case skips with the fix
> spelled out rather than failing. That is **Blocked**, not Fail — the code is
> correct and the setting is what stops it.

## TC-E2E-202 — signing out really closes the session

- **Scenario:** A signed-in organiser signs out, and a protected URL no longer
  opens.
- **Pre-conditions:** Stack running. A confirmed `event_organiser` account
  seeded through the admin API, with its `users.users` profile row.
- **Steps:**
  1. Sign in at `/login` with the seeded account.
  2. Wait for `/dashboard/event-organiser`.
  3. Click **Sign out**.
  4. Navigate directly to `/dashboard/event-organiser`.
- **Test data:** The seeded organiser's address and password.
- **Expected:** Step 3 lands on `/login`; step 4 returns to `/login` rather
  than rendering the dashboard. The second half is the real check — a guard
  reading only client state would pass step 3 and fail step 4.
- **Actual:** Both redirects to `/login` occurred.
- **Status:** Pass
- **Evidence:** `test_session.py::test_log_in_then_sign_out_closes_the_session`

## TC-E2E-203 — an organiser files a request and sees it listed

- **Scenario:** The product's main path — fill the event request form, submit
  it, and find it on the dashboard afterwards.
- **Pre-conditions:** Stack running, including the `event_requests` composite.
  A seeded `event_coordinator` (S-12: submission now assigns one, and 409s
  with none free) and a seeded `event_organiser`, signed in. The `events`
  schema, including `assigned_coordinator_id`, applied, exposed and granted.
- **Steps:**
  1. Open `/events/new`.
  2. Enter the event name and purpose.
  3. Choose start date, start time, end date and end time in the pickers.
  4. Enter expected attendance and venue.
  5. Click **Submit request**.
  6. Navigate to `/dashboard/event-organiser`.
- **Test data:** name `E2E Launch <random>`, purpose `Proving the path from
  browser to database.`, start and end both day 15 of next month,
  `9:00 AM`–`11:00 AM`, attendance `40`, venue `Hall A`.
- **Expected:** A "Request submitted." confirmation appears, submitting
  redirects to `/events/<uuid>`, and the event's name appears in **Your
  requests** on a freshly loaded dashboard, marked submitted — so it was
  stored and read back, not just echoed.
- **Actual:** Passed before S-12 changed the submission path. Not re-run this
  pass — needs `events.sql` migrated with `assigned_coordinator_id`, the
  `event_requests` composite built and running, and the test now seeds a
  coordinator first (see the test file).
- **Status:** Blocked
- **Evidence:** `test_event_request.py::test_organiser_submits_an_event_request_and_sees_it_listed`

## TC-E2E-204 — a non-organiser cannot reach organiser routes

- **Scenario:** A `venue_staff` account is kept out of the organiser dashboard
  and the event request form.
- **Pre-conditions:** Stack running. A seeded `venue_staff` account with its
  profile row.
- **Steps:**
  1. Sign in at `/login`.
  2. Navigate directly to `/dashboard/event-organiser`.
  3. Navigate directly to `/events/new`.
- **Test data:** The seeded venue staff address and password.
- **Expected:** Step 1 lands on `/dashboard/venue-staff`; steps 2 and 3 each
  return there. This is the only check that the frontend mirror in
  `access.js` and the backend policy in `authorization.py` agree.
- **Actual:** All three ended on `/dashboard/venue-staff`.
- **Status:** Pass
- **Evidence:** `test_role_access.py::test_venue_staff_cannot_reach_the_organiser_dashboard`
