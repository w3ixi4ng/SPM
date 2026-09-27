# Test cases — end-to-end journeys

Covers `test_sign_up.py`, `test_session.py`, `test_role_access.py`,
`test_add_venue.py`, `test_respond_to_return.py`, `test_rejected_tab.py` and `test_request_venue.py`. A real browser drives the built frontend through Kong,
against the services and a real (test) Supabase project. These are the only
tests that see the gateway's routing, the SPA fallback and a session cookie
surviving a page load.

| | |
| --- | --- |
| Suite | `pytest tests/e2e` |
| Last run | 2026-09-27, branch `S-36/submit-venue-booking-request` at `665c7b3` |
| Environment | `.env.test` test Supabase project; `users`, `events` (with every S-36 migration, including dropping the accessibility notes), `venues` and `bookings` (with the cabaret removal and the `special_requirements` rename) applied, granted and exposed; full stack recreated with `docker compose --env-file .env.test up -d --build --wait` immediately before, containers confirmed on the test project; Chromium; email confirmation off |
| Result | 8 passed, twice consecutively |

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

TC-E2E-203 is retired — `test_event_request.py` and its case are removed.
Post-S-12 it failed intermittently in CI on the final assertion (the
dashboard listing the submitted event) with no reproducible cause found in
either the frontend or the composite/atomic backend code; the id is not
reused. The unit suite still covers status rendering and the submission
contract without a browser.

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

## TC-E2E-205 — venue staff add a venue and see it listed

- **Scenario:** The S-27 main path — open the new-venue page, fill it, save,
  and find the venue on the dashboard after a reload.
- **Pre-conditions:** Stack running from `.env.test`. A seeded `venue_staff`
  account, signed in. The `venues` schema applied, exposed and granted.
- **Steps:**
  1. Open `/dashboard/venue-staff`.
  2. Click **Add venue**; the browser goes to `/venues/new`.
  3. Enter name, location, capacity and description.
  4. Tick facilities, accessibility and room layouts.
  5. Tick Monday and set its hours.
  6. Click **Save venue**.
  7. Reload the dashboard.
- **Test data:** name `spm-e2e Venue <random>`, location `1 Harbourfront
  Walk, Singapore 098585`, capacity `250`, description `Waterfront hall`,
  facilities Projector and Wi-Fi, accessibility Wheelchair access, layouts
  Theatre and Banquet, Monday `09:00`–`18:00`.
- **Expected:** Saving returns the browser to `/dashboard/venue-staff` with a
  "Venue saved." confirmation. After the reload the venue appears in the venue
  list with capacity `250` — so it was stored and read back through Kong, not
  just echoed.
- **Actual:** **Add venue** opened `/venues/new`; saving returned to the
  dashboard with "Venue saved.", and after a reload the venue was listed with
  Capacity 250.
- **Status:** Pass
- **Evidence:** `test_add_venue.py::test_venue_staff_add_a_venue_and_see_it_listed`

## TC-E2E-206 — an event coordinator can view venues but not add one

- **Scenario:** The frontend mirror in `access.js` and the backend policy in
  the venues service agree on who may add and who may only view.
- **Pre-conditions:** Stack running from `.env.test`. A seeded
  `event_coordinator` account. At least one venue exists, inserted into
  `venues.venues` by the test with the admin client and attributed to a seeded
  venue staff user.
- **Steps:**
  1. Sign in as the coordinator.
  2. Open `/dashboard/event-coordinator`.
  3. Navigate directly to `/venues/new`.
- **Test data:** The seeded coordinator; a venue named `spm-e2e Venue <random>`.
- **Expected:** The venue appears in the coordinator's venue list; there is no
  **Add venue** link; step 3 returns to `/dashboard/event-coordinator`.
- **Actual:** The venue appeared in the coordinator's list, no **Add venue**
  link was rendered, and `/venues/new` redirected to the coordinator dashboard.
- **Status:** Pass
- **Evidence:** `test_add_venue.py::test_event_coordinator_can_view_but_not_add_venues`

## TC-E2E-207 — an organiser responds to a returned request and resubmits it

- **Scenario:** Only a browser can prove the organiser sees the coordinator's
  request on the page, amends it and resubmits (S-13 AC1 to AC3). The data
  guarantees are TC-EVENTREQUESTS-105/106's job, not this test's.
- **Pre-conditions:** Stack and project as the header. An organiser and a
  coordinator are created with `make_user`. The admin client inserts one event
  for that organiser, assigned to the coordinator, with every submitted field
  filled in, `status=returned`, `decision=returned`, a reason, a comment and
  `decided_at`. The coordinator has no other bookings, so resubmitting at
  the same time keeps them (TC-EVENTREQUESTS-021) and no other coordinator
  needs blocking.
- **Steps:** 1. Sign in as the organiser. 2. On the dashboard, open the
  request marked **Action required**. 3. Read the banner. 4. Change
  **Expected attendance** to `80`. 5. Click **Resubmit request**.
- **Test data:** Attendance `120` → `80`; reason
  `"Expected attendance exceeds the venue's capacity"`; comment
  `"Reduce attendance to 80 or choose a larger venue"`.
- **Expected:** Step 2 opens `/events/{id}`. Step 3 shows "This request was
  returned for amendment", "Reason: Expected attendance exceeds the venue's
  capacity" and "Note from the coordinator: Reduce attendance to 80 or choose
  a larger venue". After step 5, a "Request submitted." toast appears, the URL
  is still `/events/{id}`, the banner is gone, and the dashboard shows the
  request once, as **Under review**.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_respond_to_return.py::test_an_organiser_responds_to_a_returned_request_and_resubmits`

## TC-E2E-208 — rejected requests sit in their own tab and still open read-only

- **Scenario:** Only a browser can show the organiser dashboard's tabs
  rendering and switching, and a rejected row still opening the locked form.
  TC-FRONTEND-026/027 cover the grouping and labels.
- **Pre-conditions:** Stack and project as the header. An organiser is
  created with `make_user`. The admin client inserts two of their events:
  one `submitted`, and one `rejected` with reason
  `"The venue is closed for renovation that week"`.
- **Steps:** 1. Sign in as the organiser. 2. Look at the dashboard. 3. Select
  the **Rejected (1)** tab. 4. Open the rejected request.
- **Test data:** Submitted event `"spm-e2e Active <hex>"`; rejected event
  `"spm-e2e Rejected <hex>"`.
- **Expected:**
  - Step 2: **Active (1)** is the selected tab. It lists the submitted
    request as **Under review** and does not list the rejected one.
  - Step 3: the list shows only the rejected request, labelled **Rejected**.
  - Step 4: `/events/{id}` opens with "This request has been rejected and is
    closed." and "Reason: The venue is closed for renovation that week". Its
    form fields are disabled.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_rejected_tab.py::test_rejected_requests_sit_in_their_own_tab_and_open_read_only`

## TC-E2E-209 — a Coordinator's venue request stays on the event and shows up for Venue Staff

- **Scenario:** Revised for S-36: requirements come from the event; venues are chosen from a list. S-36, AC1, AC3 and AC4 in a real browser. Only this suite sees
  the Coordinator's request screen posting through Kong and the Venue Staff
  dashboard rendering the pending list after a fresh sign-in. The unit and
  integration suites cover the suitability rules; they are not restaged
  here.
- **Pre-conditions:** Stack and project as the header, with the `bookings`
  schema applied, exposed and granted as well. The test creates, and
  removes afterwards:
  - an `event_coordinator` and a `venue_staff` account with `make_user`;
  - a venue `"spm-e2e Venue <hex>"`, capacity `150`, layout `theatre`,
    facility `projector`, open Thursday `08:00`–`20:00`;
  - an event `"spm-e2e Event <hex>"` assigned to the coordinator,
    `status=planning`, `2026-11-12 09:00`–`18:00`, `expected_attendance`
    `120`, `room_layout` `theatre`, `required_facilities` `["projector"]`,
    no venue preference.
- **Steps:**
  1. Sign in as the coordinator and open `/coordinator/events/{id}`.
  2. Click **Request venue**.
  3. On the request screen, check the event's requirements are shown, choose
     the venue from the list, and set date `2026-11-12`, `09:00`–`12:00`.
  4. Click **Send request**.
  5. Reload the event page.
  6. Sign out, then sign in as the venue staff account.
  7. Look at **Pending booking requests** on `/dashboard/venue-staff`.
- **Test data:** As above.
- **Expected:**
  - Step 2: the browser is on `/coordinator/events/{id}/request-venue`.
  - Step 3: the screen shows the event's requirements, **Theatre** and
    **Projector**, as text, not inputs. The venue's row in the list is marked
    **Fits**.
  - Step 4: the browser returns to `/coordinator/events/{id}`, which says
    `"Venue request sent to Venue Staff."`
  - Step 5: the confirmation is gone, and **Venue requests** on the event
    page lists `"spm-e2e Venue <hex>"`, `12 Nov 2026`, `09:00–12:00`,
    labelled **Pending**.
  - Step 7: the list has a row for `"spm-e2e Event <hex>"` at
    `"spm-e2e Venue <hex>"`, showing `12 Nov 2026`, `09:00–12:00`,
    `120 expected`, `Theatre`, and the coordinator's name. The row is
    labelled **Pending**.
- **Actual:** The request screen showed Theatre and Projector as text with no inputs; the venue's row was marked Fits and chosen by its radio; the send returned to the event page with the confirmation; after a reload Venue requests listed the venue, 12 Nov 2026, 09:00–12:00, Pending; Venue Staff's pending list showed the full row.
- **Status:** Pass
- **Evidence:** `test_request_venue.py::test_a_coordinators_venue_request_stays_on_the_event_and_shows_up_for_venue_staff`

## TC-E2E-210 — a too-small venue is warned about and blocked, and a larger one can be sent

- **Scenario:** S-35, all three criteria in a real browser. Only a browser
  shows the warning appearing on selection and **Send request** being
  disabled and re-enabled; TC-FRONTEND-036 covers the wording.
- **Pre-conditions:** Stack and project as the header. The test creates, and
  removes afterwards: an `event_coordinator` with `make_user`; an event
  `"spm-e2e Event <hex>"` assigned to them, `status=planning`,
  `2026-11-12 09:00`–`18:00`, `expected_attendance` `100`, no venue
  requirements; two venues, both layout `theatre` and open Thursday
  `08:00`–`20:00`: `"spm-e2e Small <hex>"` capacity `80` and
  `"spm-e2e Large <hex>"` capacity `150`.
- **Steps:**
  1. Sign in as the coordinator and open
     `/coordinator/events/{id}/request-venue`.
  2. Look at **Send request** before choosing a venue.
  3. Choose the Small venue.
  4. Choose the Large venue.
  5. Set `09:00`–`12:00` and click **Send request**.
- **Test data:** As above.
- **Expected:**
  - Step 2: no warning; **Send request** is enabled.
  - Step 3: `"spm-e2e Small <hex> holds 80 people; this event expects 100.
    Choose a larger venue."` is shown, and **Send request** is disabled.
  - Step 4: the warning is gone and **Send request** is enabled.
  - Step 5: the browser returns to `/coordinator/events/{id}` with
    `"Venue request sent to Venue Staff."`

- **Actual:**
- **Status:** Not Executed
- **Evidence:**
