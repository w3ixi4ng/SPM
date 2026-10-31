# Test cases — end-to-end journeys

Covers `test_sign_up.py`, `test_session.py`, `test_role_access.py`,
`test_add_venue.py`, `test_respond_to_return.py`, `test_rejected_tab.py`,
`test_request_venue.py`, `test_capacity_warning.py`, `test_update_venue.py`,
`test_record_equipment.py`, `test_update_equipment.py`,
`test_retire_equipment.py`, `test_assign_technical_support.py`,
`test_prevent_overlapping_confirmation.py`, `test_filter_venues.py`,
`test_venue_availability.py`, `test_assign_event_request.py`, and
`test_reassign_event_coordinator.py`, `test_coordinator_overview.py`, and
`test_operational_safety_check.py`, and `test_book_multiple_venues.py`,
and S-51's `test_set_registration_period.py` and `test_register_for_event.py`,
plus S-93's `test_reassign_before_deactivation.py`.
A real browser drives the built frontend through Kong,
against the services and a real (test) Supabase project. These are the only
tests that see the gateway's routing, the SPA fallback and a session cookie
surviving a page load.

| | |
| --- | --- |
| Suite | `pytest tests/e2e` |
| Last run | 2026-10-27, CI on S-93 commit `17f60bc` |
| Environment | `.env.test` test Supabase project with all repository SQL applied, granted and exposed; full stack recreated immediately before; Chromium; email confirmation off |
| Result | Full Chromium regression: 58 passed. |

## TC-E2E-201 — sign-up lands on the dashboard for the assigned role

- **Scenario:** A new account created through the real sign-up form is given
  the organiser role and routed to the organiser dashboard.
- **Pre-conditions:** Stack running. No account exists for the address. The
  test project has **Confirm email off** — with it on, sign-up returns no
  session and the case reports Blocked (see below).
- **Steps:**
  1. Open `/signup` through Kong.
  2. Fill first name, last name, email, password, confirm password, and choose
     **Event Organiser** (S-01).
  3. Submit the form.
  4. Wait for the browser to leave `/signup`.
- **Test data:** `Ada` / `Lovelace` / `spm-e2e-<random>@example.com` /
  `correct-horse-battery-staple`.
- **Expected:** The browser ends on `/dashboard/event-organiser`. Reaching it
  requires the service to have stamped `app_metadata.role=event_organiser`,
  `/users/me` to have returned it, and the route guard to have resolved it.
- **Actual:** Redirected to `/dashboard/event-organiser`.
- **Status:** Pass
- **Evidence:** `test_sign_up.py::test_sign_up_lands_on_the_organiser_dashboard[chromium]`; `.env.test` stack recreated with `--build` immediately before (users container's `SUPABASE_URL` matched `.env.test`); 2026-10-26, branch `S-01/user-accounts` on `4e15f2a` + working tree

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

## TC-E2E-210 — a venue that doesn't suit the event is warned about and blocked, and one that fits can be sent

- **Scenario:** Revised for S-34, twice: **Clear filters** now shows every venue, including one closed at the booking's time, which is marked and blocked like any other mismatch. Before that: the list now opens filtered to the event, so the unsuitable venues are reached through **Clear filters**. S-35 in a real browser. Only a browser shows the warning
  appearing on selection and **Send request** being disabled and re-enabled;
  TC-FRONTEND-039 covers the wording.
- **Pre-conditions:** Stack and project as the header. The test creates, and
  removes afterwards: an `event_coordinator` with `make_user`; an event
  `"spm-e2e Event <hex>"` assigned to them, `status=planning`,
  `2026-11-12 09:00`–`18:00`, `expected_attendance` `100`,
  `required_facilities` `["projector"]`; three venues, all layout `theatre`
  and open Thursday `08:00`–`20:00`:
  - `"spm-e2e Small <hex>"`: capacity `80`, facility `projector`;
  - `"spm-e2e Bare <hex>"`: capacity `150`, no facilities;
  - `"spm-e2e Large <hex>"`: capacity `150`, facility `projector`;
  - `"spm-e2e Weekend <hex>"`: capacity `150`, facility `projector`, open
    Saturday `10:00`–`16:00` only.
- **Steps:**
  1. Sign in as the coordinator and open
     `/coordinator/events/{id}/request-venue`.
  2. Look at the list and **Send request** before choosing a venue, then
     open **Filters** (collapsed to start), click **Clear filters**, then tick
     **Only venues open at the booking's
     date and time** again, then click **Clear filters** once more.
  3. Choose the Small venue.
  4. Choose the Bare venue.
  5. Choose the Weekend venue.
  6. Choose the Large venue.
  7. Set `09:00`–`12:00` and click **Send request**.
- **Test data:** As above.
- **Expected:**
  - Step 2: the list opens filtered to the event, so only the Large venue
    shows; no warning; **Send request** is enabled. After **Clear filters**
    all four venues show, the Weekend venue marked `"Closed on Thursdays"`
    under its name, and the checkbox is unticked. Ticking it hides the
    Weekend venue again; clearing once more shows all four.
  - Step 3: a warning naming the Small venue and `"Too small: holds 80, event
    expects 100"` is shown, and **Send request** is disabled.
  - Step 4: the warning names the Bare venue and `"Missing: Projector"`;
    **Send request** is still disabled.
  - Step 5: the warning names the Weekend venue and `"Closed on
    Thursdays"`; **Send request** is still disabled.
  - Step 6: no warning, and **Send request** is enabled.
  - Step 7: the browser returns to `/coordinator/events/{id}` with
    `"Venue request sent to Venue Staff."`
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_capacity_warning.py::test_a_venue_that_does_not_suit_the_event_is_warned_about_and_blocked`

## TC-E2E-211 — equipment moves from catalogue to planning requirement to Technical Support view

- **Scenario:** Combined S-39/S-40 browser journey proving the gateway,
  role-specific screens, session cookies, orchestration, and persistence.
- **Pre-conditions:** Complete test stack; a Technical Support user, assigned
  Coordinator, organiser, planning event assigned to that Technical Support
  user, and no requirement for the item.
- **Steps:** Technical Support adds `spm-e2e Wireless Microphone <hex>` with
  total `12`; Coordinator opens the planning event, records quantity `6`, and
  sees it after reload; sign out and back in as Technical Support.
- **Expected:** The new item remains in the shared catalogue, the Coordinator
  can record it only on the planning event, and the assigned Technical Support
  user sees the event name, item name, and quantity `6` under Assigned events.
  The requirement is verified in storage immediately after the save response.
- **Actual:** Technical Support added the shared catalogue item; the assigned
  Coordinator saved quantity 6; storage contained the saved requirement; and
  after a fresh sign-in the assigned Technical Support user saw the event and
  microphone ×6 under Assigned events.
- **Status:** Pass
- **Evidence:** `test_record_equipment.py::test_coordinator_records_required_equipment_visible_to_technical_support[chromium]`; freshly rebuilt S-43 `.env.test` stack; 1 passed on 2026-10-05.

## TC-E2E-212 — Technical Support edits an item and immediately sees the catalogue update

- **Scenario:** S-41 browser journey proving the protected editor, populated
  controls, update request, navigation, and refreshed management catalogue.
- **Pre-conditions:** Complete test stack; a Technical Support user and active
  available item exist.
- **Steps:** Sign in as Technical Support; open the item's Edit action; change
  its type, description, quantity, and operational status to `maintenance`;
  save; return to the catalogue.
- **Test data:** Existing `spm-e2e S41 Microphone <hex>` becomes
  `spm-e2e S41 Radio Microphone <hex>`, description `Updated in browser`,
  total `18`, status `maintenance`.
- **Expected:** The editor starts with stored values. Saving returns to the
  Technical Support dashboard with a success notice, and the catalogue row
  immediately shows the new type, description, quantity, and Maintenance
  status while the item remains visible.
- **Actual:** The editor loaded every stored value; saving returned to the dashboard with confirmation and immediately showed the updated name, description, quantity, and Maintenance · Active label. Direct storage inspection matched.
- **Status:** Pass
- **Evidence:** `test_update_equipment.py::test_technical_support_updates_equipment_and_sees_it_immediately`

## S-28 approved coverage

ID reconciliation: main retains TC-E2E-210 (S-35 capacity warning),
TC-E2E-211 (S-39/S-40 equipment journey), and TC-E2E-212 (S-41 equipment edit).
The S-28 staff-edit case is now TC-E2E-213 (originally TC-E2E-210,
then TC-E2E-212 on the S-28 branch). The S-28 access-control case is
now TC-E2E-214 (previously TC-E2E-211 on the S-28 branch).
Earlier S-28 references retain those meanings; no case was removed. The S-28
results below retain their original evidence, and the combined suite was rerun
successfully on S-42 as recorded in the header.

Latest S-28 execution: 2026-09-27; base `0d27acc` plus S-28 working changes; Chromium against freshly recreated `.env.test` Docker stack. Existing add-venue and coordinator read-only journeys also passed.

### TC-E2E-213 - Staff edit refreshes catalogue and persists

- Scenario: Staff edit refreshes catalogue and persists
- Pre-conditions: Approved test stack and Chromium; venue created by another staff member.
- Steps: 1. Open Edit; change location to Block B, capacity to 100, facilities/accessibility; save; inspect list without reload then reload.
- Test data: Values specified above; existing shared fixtures supply remaining required fields.
- Expected: Only four edit fields shown; updated catalogue immediately and after reload; Cancel leaves saved values unchanged.
- Actual: Another staff member edited all four fields; catalogue refreshed without manual reload; reload/reopen preserved values; invalid capacity showed error; Cancel discarded unsaved edits.
- Status: Pass
- Evidence: `tests/e2e/test_update_venue.py::test_staff_edit_refreshes_catalogue_and_persists[chromium]`; local browser execution.

### TC-E2E-214 - Non-staff cannot edit venues

- Scenario: Non-staff cannot edit venues
- Pre-conditions: Approved test stack; coordinator account and existing venue.
- Steps: 1. Open dashboard then navigate directly to venue edit URL.
- Test data: Values specified above; existing shared fixtures supply remaining required fields.
- Expected: No Edit action; redirect to coordinator dashboard.
- Actual: Coordinator saw no Edit action; direct edit URL redirected to coordinator dashboard. Passed on targeted rerun after an initial session-expired response during catalogue loading.
- Status: Pass
- Evidence: `tests/e2e/test_update_venue.py::test_coordinator_cannot_open_edit[chromium]`; local Chromium rerun, 1 passed.

## S-42 — retire equipment item

S-28 owns `TC-E2E-213` and `TC-E2E-214` on current `main`, so the S-42 journey
uses the next unused E2E id.

## TC-E2E-215 — retired equipment remains managed but disappears from new selection

- **Scenario:** S-42 browser journey across Technical Support management and
  the Event Coordinator's new-requirement editor.
- **Pre-conditions:** Complete test stack; Technical Support, Coordinator, and
  Organiser users; one active available item; one planning event assigned to
  the Coordinator; no requirement yet exists for the item.
- **Steps:** Sign in as Technical Support; retire the item from its catalogue
  row and confirm the action; observe the refreshed row; sign out and sign in
  as the Coordinator; open the planning event's equipment-requirement editor.
- **Test data:** `spm-e2e S42 Microphone <hex>`, quantity `12`.
- **Expected:** Retirement returns to or refreshes the Technical Support
  catalogue with a success notice. The same item row remains visible and says
  `Retired`. In the Coordinator editor, the retired item is absent from new
  selection and no requirement can be entered for it.
- **Actual:** Technical Support retired the active item and immediately saw the
  same row labelled `Available · Retired` with no further Retire action. After
  signing in as the assigned Coordinator, the planning event offered no
  quantity input for that item.
- **Status:** Pass
- **Evidence:** `test_retire_equipment.py::test_retired_equipment_remains_managed_but_disappears_from_selection`

S-37 IDs reconciled after merging S-42 and S-43: TC-E2E-215 -> TC-E2E-216 -> TC-E2E-217. Earlier S-37 references identify the same case.

## S-37 confirmed specifications

Confirmed by the developer on 2026-09-28, with no reassignment exception.
S-37 execution: 2026-09-29; base c4934e9 merged with S-37 plus conflict-resolution changes on
S-37/approve-reject-booking-with-reason-or-alternative.
Windows, Python 3.14, Node.js; existing results above describe earlier coverage.
Approval stores `status=confirmed`; rejection stores `status=rejected`.
Decision metadata: `decision_reason`, `decision_alternative`, `decided_by`, `decided_at`.
B means the saved booking fixture; S means the authenticated deciding staff UUID.
No S-33 hold behaviour or S-38 cross-request overlap guarantee is included.

### TC-E2E-217 — Staff decide requests and Coordinators see the saved results

- **Scenario:** Staff decide requests and Coordinators see the saved results (AC1, AC2, AC3).
- **Pre-conditions:** Fresh .env.test stack, developer-applied SQL and Chromium; isolated staff/coordinator fixtures with pending requests.
- **Steps:** 1. Sign in as staff; approve without reason.
  2. Reject another with alternative only; verify blank rejection blocked.
  3. Confirm successful decisions disappear from pending without refresh.
  4. Sign in as requester; reopen event and read both decisions.
  5. Exercise failed/conflicting save and a nonstaff dashboard.
  6. Reload the Coordinator event page and verify the saved result persists.
- **Test data:** Studio B, 2026-11-12, three requests at 09:00-12:00, 12:00-15:00 and 15:00-18:00 (separate slots since S-30 made pending requests exclusive holds); alternative='Try Studio C at 14:00'; server-conflict fixture already decided by another staff.
- **Expected:** Saved Confirmed/Rejected outcome and alternative visible after reopen; no automatic booking of alternative. Failure/conflict gives safe feedback, not success. Nonstaff sees no decision controls. No reassignment exception is added; the existing assignment rule remains in force. Manual supplement: two staff tabs, keyboard operation, narrow screen and reason-plus-alternative display.
- **Actual:** Venue Staff approved one pending request without a reason and rejected another with an alternative; blank rejection was blocked. The pending list refreshed after each decision. After signing in as the requesting Coordinator and reopening the event, both saved outcomes and the alternative were visible and persisted after reload.
- **Status:** Pass
- **Evidence:** `test_decide_booking.py::test_staff_decisions_appear_to_requesting_coordinator[chromium]`; rerun 2026-09-30 on branch `S-30/view-venue-availability-calendar` after giving the three requests separate slots; local Chromium against a freshly recreated `.env.test` stack: 1 passed.
## S-43 — Auto-Assign Technical Support

## TC-E2E-216 — Coordinator explicitly requests support and sees the automatic assignment

- **Scenario:** S-43's complete browser journey without manual staff selection.
- **Pre-conditions:** Complete test stack; a planning event assigned to the
  signed-in Coordinator; two eligible Technical Support Staff users; neither
  overlaps the event and one is deterministically least busy.
- **Steps:** Open the assigned planning event; confirm no assignment exists;
  choose the explicit Technical Support required action; enter support details;
  submit; observe the assigned staff; reload the page.
- **Test data:** Details `Wireless microphone setup and sound check` and a
  target window `2026-11-13 09:00`–`12:00`.
- **Expected:** The UI offers no staff picker. Submission shows the selected
  staff member's name and email and the saved details. The same assignment is
  visible after reload, proving it is persisted rather than local UI state.
- **Actual:** No staff picker was shown. Submitting the optional details
  displayed the deterministically selected staff member's name and email, and
  both the assignment and details remained visible after a page reload.
- **Status:** Pass
- **Evidence:** `test_assign_technical_support.py::test_coordinator_requests_support_and_sees_the_assignment[chromium]`

## S-38 confirmed specifications

Story: S-38 Prevent Overlapping Booking Confirmation.
Confirmed by the developer on 2026-09-29. Back-to-back bookings are allowed.

## TC-E2E-218 — Confirmed venue time becomes unavailable to another event

S-33 restored `pending` as an unheld request state, so two overlapping pending
requests can exist until Venue Staff place a hold or confirm one. This case is
active again and proves S-38 at the confirmation boundary.

- **Scenario:** Venue Staff cannot confirm an overlapping request after the
  venue slot has been confirmed for another event (AC1, AC2, AC3).
- **Pre-conditions:** Fresh `.env.test` stack with all repository SQL through
  S-33 applied, granted and exposed; Chromium; one Venue Staff account; two
  planning events have pending requests for Studio B on the same date with
  overlapping times.
- **Steps:** Sign in as Venue Staff; confirm the first request; attempt to
  confirm the second request; reload the pending list and both Coordinators'
  event views.
- **Test data:** Event A requests Studio B on `2026-11-12`, `09:00`–`12:00`;
  Event B requests Studio B on `2026-11-12`, `11:00`–`13:00`.
- **Expected:** Event A becomes Confirmed and remains confirmed after reload.
  Event B is not confirmed; the page identifies Studio B, `12 Nov 2026`, and
  `09:00`–`12:00` as the conflict. Event B remains Pending after reload, and
  its Coordinator never sees a confirmed booking for that unavailable slot.
  *S-76 (2026-10-09), which supersedes S-38 where they differ:* the alert
  now reads "Can't confirm this booking: it overlaps <Event A> (confirmed),
  which occupies <venue> on 12 Nov 2026 from 09:00 to 12:00." Re-run 2026-10-09
  on the S-76 branch: pass (full e2e suite 29 passed).
- **Actual:** The first request became Confirmed; the overlapping approval stayed Pending and displayed the venue/date/time conflict. Reload preserved both outcomes, and the two Coordinator event pages showed Confirmed and Pending respectively.
- **Status:** Pass
- **Evidence:** `test_prevent_overlapping_confirmation.py::test_confirmed_venue_time_becomes_unavailable_to_another_event[chromium]`; rerun 2026-10-25 on the S-88 branch against a freshly rebuilt `.env.test` stack: 1 passed. The test now waits for the previous user's sign-out to finish before the Coordinator signs in.

## TC-E2E-219 — a Coordinator narrows the Venues tab with filters, and results follow each change

- **Scenario:** S-34, AC1–AC3 in a real browser. The matching rules are
  TC-FRONTEND-057 to 062; this proves the filters are wired to the list on
  the dashboard, update it on every change, and can be cleared.
- **Pre-conditions:** Stack and project as the header. The test creates, and
  removes afterwards, an `event_coordinator` with `make_user` and the three
  venues from the frontend cases' shared data, each name suffixed with
  `<hex>` so other venues in the project can be told apart.
- **Steps:**
  1. Sign in as the coordinator, open the **Venues** tab, and open
     **Filters**.
  2. Type `anson` in **Search by name or location**.
  3. Set **Holds at least** to `100`.
  4. Tick **Stage** under facilities.
  5. Set the date to `2026-11-12`.
  6. Click **Clear filters**.
- **Test data:** As above.
- **Expected:**
  - Step 1: before opening, the collapsed panel reads **Filters · none
    applied**.
  - Step 2: of the three, Studio B and Anson Suite are listed.
  - Step 3: Anson Suite only, and the panel reads **2 applied**.
  - Step 4: Anson Suite only.
  - Step 5: none of the three, and `"No venues match these filters."`
  - Step 6: all three listed again, and the search box is empty.

- **Actual:**
- **Status:** Not Executed
- **Evidence:**

## S-30 — view venue availability calendar

Story: S-30 View venue availability calendar.
Confirmed by the developer on 2026-09-30. Executed locally on 2026-09-30.
Both cases are **Blocked** until the S-30 section of `backend/sql/bookings.sql`
has been run in the test project. Dates are relative to the day of the run:
`D+n` means n days after the browser's today, so the suite keeps working as
time passes.

## TC-E2E-220 — a Coordinator opens a venue's calendar and sees booked, held, unavailable and past days apart

- **Scenario:** Kong, the SPA route and the calendar render every state
  (AC1, AC2).
- **Pre-conditions:** A fresh `.env.test` stack and Chromium. A test venue
  open every day `08:00`–`18:00`. Seeded through the API: a confirmed request
  on `D+2` `09:00`–`12:00`, a pending request on `D+2` `14:00`–`16:00`, and a
  block on `D+3`–`D+4`, `maintenance`.
- **Steps:**
  1. Sign in as the Coordinator. Open the Venues tab and choose **Availability**
     on the test venue's row, next to where Venue Staff see **Edit**.
  2. Reload on `/venues/:id/availability`.
  3. Move to each seeded day's month with the Month and Year dropdowns, and
     try ◀ on the first month. (Changed by the developer on 2026-09-30: one month at a time with arrows and Month/Year dropdowns, replacing the From/To range.)
- **Expected:**
  - The page has a "Back to dashboard" link. It opens on the month `D+1` is
    in, and ◀ is disabled there.
  - `D+2` shows "Booked 09:00–12:00" and "Tentatively held 14:00–16:00".
    `D+3` and `D+4` show "Unavailable — Maintenance". Other days show
    "Available".
  - A legend names each state. No event name appears on the page.
  - In the grid, today and earlier are greyed out and cannot be clicked.
  - The page survives the reload, which proves the SPA fallback and the
    session. **Mark unavailable** is not shown to a Coordinator.
- **Actual:** Opened from the Venues tab and survived a reload; opened on tomorrow's month with Previous disabled and today greyed out; D+2 showed Booked and Tentatively held, D+3 and D+4 Unavailable — Maintenance, D+5 Available; legend complete; no event name or note; no Mark unavailable for the Coordinator.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_venue_availability.py::test_a_coordinator_sees_booked_held_unavailable_and_past_days_apart`; `.env.test` stack recreated immediately before; bookings container verified on the test project's `SUPABASE_URL`; `pytest tests/e2e/test_venue_availability.py`: 2 passed.

## TC-E2E-221 — a new hold, a new block and a removed block all show up on the calendar

- **Scenario:** Changes made elsewhere appear on the next open or Refresh
  (AC3).
- **Pre-conditions:** As TC-E2E-220, with nothing on the venue. A Venue
  Staff account. Two planning events assigned to the Coordinator.
- **Steps:**
  1. The Coordinator opens the calendar, moving to `D+5`'s month with ▶ if
     it is not the first month shown. `D+5` shows "Available".
  2. The Coordinator sends a request for `D+5` `10:00`–`11:00` from the first
     event. They reopen the calendar, then try the second event on `D+5`
     `10:30`–`11:30`.
  3. Venue Staff open the same venue's **Availability** and choose **Mark
     unavailable**. In the slide-over they block `D+6`–`D+6`, reason
     "Renovation".
  4. The Coordinator presses **Refresh**.
  5. Staff press **Remove** on the block. The Coordinator presses **Refresh**.
- **Expected:**
  - Step 2: `D+5` shows "Tentatively held 10:00–11:00". The second request
    shows "… is already tentatively held on … from 10:00 to 11:00."
  - Step 3: staff see the block on their calendar straight away.
  - Step 4: `D+6` shows "Unavailable — Renovation".
  - Step 5: `D+6` is "Available" again.
  - Cleanup removes every row created.
- **Actual:** D+5 went from Available to Tentatively held 10:00–11:00; the second event was refused as already tentatively held; the staff block showed for staff at once and for the Coordinator on Refresh; after Remove, Refresh showed D+6 Available.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_venue_availability.py::test_a_new_hold_a_new_block_and_a_removed_block_all_show_up`; `.env.test` stack recreated immediately before; bookings container verified on the test project's `SUPABASE_URL`; `pytest tests/e2e/test_venue_availability.py`: 2 passed.

## S-44 — check equipment availability

Story: S-44 Check equipment availability.
Confirmed by the developer on 2026-09-30. Not yet executed.

## TC-E2E-222 — Technical Support checks a window, sees what is reserved, and re-checks after a change

- **Scenario:** Kong, the SPA route and the page work end to end (AC1, AC2,
  AC3).
- **Pre-conditions:** A fresh `.env.test` stack and Chromium. A Technical
  Support account. A new active item "spm-e2e S44 Mic {suffix}", total 10.
  A `planning` event on `D+3` 10:00–11:00 with a 7-unit requirement for it.
  `D+n` is n days after the browser's today.
- **Steps:**
  1. Sign in as Technical Support and choose **Check availability** on the
     dashboard. Reload the page on `/equipment/availability`.
  2. Enter `D+3` 09:00 to `D+3` 12:00, type "spm-e2e S44 Mic {suffix}",
     quantity 4, and press **Check availability**.
  3. Expand the item.
  4. Add a 2-unit requirement for another `planning` event at the same time,
     directly, then press **Check availability** again.
- **Expected:**
  - The page has "Back to dashboard"; the date pickers don't allow dates
    before today; the reload keeps the page.
  - Step 2: "3 of 10 available", "7 reserved", "Not enough — 3 available",
    and "Checked at …".
  - Step 3: the event's name, `D+3` 10:00–11:00, "Planning", and 7.
  - Step 4: "1 of 10 available", "9 reserved", and a checked-at time no
    earlier than before.
  - Cleanup removes every row created.
- **Actual:** Reached from the dashboard and survived a reload; Start date min was today; "3 of 10 available", "7 reserved", "Not enough — 3 available" and "Checked at …"; the expanded list showed the event, 10:00–11:00 and Planning; after the second hold, "1 of 10 available" and "9 reserved".
- **Status:** Pass
- **Evidence:** `tests/e2e/test_check_equipment_availability.py::test_technical_support_checks_a_window_and_rechecks_after_a_change[chromium]`; `.env.test` stack recreated immediately before; events container verified on the test project's `SUPABASE_URL`; 1 passed.

## S-33 — place tentative venue hold

Story: S-33 Place Tentative Venue Hold.
Confirmed by the developer on 2026-09-30. Not yet executed.

## TC-E2E-223 — Tentative hold appears distinctly and releases for a replacement request

> **S-79 (2026-10-11):** a second request no longer replaces the first. The
> test (`test_tentative_hold_is_distinct_and_a_second_request_keeps_it`) now
> expects the original to stay `held` with no release reason. Run 2026-10-11:
> failed once in a three-file run and did not reproduce; passed alone and in
> a rerun of `test_tentative_hold.py` with `test_book_multiple_venues.py`.

- **Scenario:** Venue Staff place and observe a hold, then the Coordinator's changed request frees the old slot immediately (AC1–AC4).
- **Pre-conditions:** Fresh `.env.test` stack with S-33 SQL applied, granted and exposed; Chromium; one Venue Staff member; assigned Coordinator; planning event with a Pending Studio B request.
- **Steps:** Sign in as Venue Staff; place the hold; inspect availability; verify an overlapping request is blocked; sign in as the Coordinator and submit a replacement at a different time; return as Venue Staff and inspect availability without a full page reload; place a hold in the freed old slot.
- **Test data:** Original Studio B `2026-11-12` `09:00`–`12:00`; replacement `13:00`–`16:00`; competing request `10:00`–`11:00`.
- **Expected:** Original request stays actionable and is labelled Held. Calendar shows `Tentative hold` distinctly from a Confirmed fixture. Overlap is blocked with the identified held slot. Replacement removes the old calendar entry immediately and permits another hold at `09:00`–`12:00`; the replacement remains Pending until staff place its hold.
- **Actual:** Venue Staff placed the hold and saw Tentatively held in the dashboard/calendar; the Coordinator's changed request released the original row with `booking_replaced`.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_tentative_hold.py::test_tentative_hold_is_distinct_and_replacement_releases_it[chromium]`.

## TC-E2E-224 — Rejected or cancelled event releases its tentative hold

- **Scenario:** Closed event states never leave a venue slot reserved (AC3, AC4).
- **Pre-conditions:** Same approved stack; separate Held requests whose authoritative events can be moved to `rejected` and `cancelled` by the test fixture. S-33 adds no Cancel Event UI.
- **Steps:** Open availability; trigger each authoritative event-state change through the supported service boundary; refresh/synchronise the workspace; inspect availability and attempt an overlapping hold.
- **Test data:** Studio B `2026-11-12` `09:00`–`12:00`; release states `rejected`, `cancelled`.
- **Expected:** Each state releases its hold with the matching reason, removes Tentative from the calendar immediately after the state is observed, and allows another event to hold the same slot. No cancellation button is introduced by S-33.
- **Actual:** Both rejected and cancelled event states released the held booking with the matching audit reason; the request disappeared and its calendar day returned to Available.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_tentative_hold.py::test_terminal_event_releases_hold_when_staff_refreshes[chromium-rejected]` and `[chromium-cancelled]`.

## S-43 — Technical Support assigned-event visibility

Story: S-43 Auto-Assign Technical Support.
Specification updated by the developer on 2026-10-05. TC-E2E-225 is already
allocated to the S-40 resource-panel fix, so this case uses the next id.

## TC-E2E-226 — Technical Support sees only its active events and their requirements

- **Scenario:** The complete browser flow reflects the persisted staff
  assignment and never exposes another staff member's work.
- **Pre-conditions:** Fresh `.env.test` stack and Chromium; Technical Support
  A and B; A's planning event, A's cancelled historical assignment, and B's
  planning event; one distinct equipment requirement per event; shared
  catalogue items exist for all three requirements.
- **Steps:** Sign in as A; inspect the Equipment Catalogue and Assigned events
  area; inspect A's event details and equipment; verify absent events and
  requirements; sign out and sign in as B; repeat.
- **Test data:** Events `A active`, `A cancelled`, `B active`; support notes
  unique to each; equipment `A microphone ×2`, `A old speaker ×3`, and
  `B projector ×4`.
- **Expected:** The shared catalogue remains visible to both staff members. A
  sees only `A active`, its support notes, and `A microphone ×2`; neither
  cancelled nor B data appears. B sees only `B active` and `B projector ×4`.
  Empty/unrelated event requirements never appear, and the result survives a
  page reload.
- **Actual:** Both accounts retained the complete three-item catalogue. A's
  Assigned events list contained only A active, A's notes and microphone ×2,
  including after reload. After signing out and into B, it contained only B
  active, B's notes and projector ×4; the cancelled event and unrelated
  equipment did not appear in either assigned-work list.
- **Status:** Pass
- **Evidence:** `test_assign_technical_support.py::test_support_staff_see_only_their_active_assigned_events_and_equipment[chromium]`; fresh `.env.test` stack; 2 tests in the S-43 browser file passed.
## S-40 — resource-panel contrast and grouping fix

Story: S-40 Record Required Equipment.
Confirmed by the developer on 2026-10-05.

## TC-E2E-225 — equipment quantities contrast with one grouped resource panel

- **Scenario:** A Coordinator can distinguish the equipment quantity control
  from the page and understands equipment and Technical Support as one
  resource-planning area.
- **Pre-conditions:** A fresh `.env.test` stack and Chromium; a planning event
  assigned to the signed-in Coordinator; one active equipment item; no
  Technical Support request yet exists.
- **Steps:**
  1. Open the assigned planning event.
  2. Inspect the equipment quantity input at rest, hover it, and focus it.
  3. Inspect the closest resource-planning card around the **Required
     equipment** and **Technical support** headings.
  4. Enter quantity `6` and save it.
  5. Run the existing Technical Support request journey.
- **Test data:** The TC-E2E-211 equipment item and planning event; quantity
  `6`; TC-E2E-216 support details.
- **Expected:** The quantity input background is white (`rgb(255, 255, 255)`)
  at rest, on hover, and while focused. Both headings are inside one shared
  bordered resource card, while remaining separately labelled sections.
  Quantity saving and Technical Support requesting continue to succeed.
- **Actual:** The quantity input computed to white at rest, on hover, and
  while focused. Both headings were found inside the same Event resources
  group. Quantity `6` saved and remained visible to Technical Support; the
  separate support-assignment journey still assigned staff and persisted its
  details after reload.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_record_equipment.py::test_coordinator_records_required_equipment_visible_to_technical_support[chromium]`; `tests/e2e/test_assign_technical_support.py::test_coordinator_requests_support_and_sees_the_assignment[chromium]`; local run on 2026-10-05, branch `S-40/record-required-equipment`, freshly rebuilt `.env.test` stack: 2 passed.

## S-75 — configure venue setup and turnaround time

Story: S-75 Configure Venue Setup and Turnaround Time.

> **Renumbered 2026-10-08:** TC-FRONTEND-081–084 and TC-E2E-226 were
> already in use (S-43 on `main`, S-83 on `sprint3`). S-75's cases with
> those numbers are now TC-FRONTEND-088–091 and TC-E2E-228; the rest keep
> theirs.
Confirmed by the developer on 2026-10-07. Not yet executed.
**Blocked** until the S-75 SQL has been run in the test project.

## TC-E2E-228 — Venue Staff set setup and turnaround times, see the new clash, and the Coordinator is warned

- **Pre-conditions:** A fresh `.env.test` stack and Chromium. Venue Staff, a
  Coordinator, a test venue open every day 08:00–20:00 with 0/0, and on
  `D+3`: A confirmed 10:00–12:00 and B held 12:30–14:00 (B's event assigned
  to the Coordinator).
- **Steps:**
  1. Staff edit the venue: setup 0 h 30 min, turnaround 0 h 45 min; save.
     (Hours and minutes boxes since the developer's change of 2026-10-08.)
  2. The Coordinator opens B's event, then the venue's calendar on `D+3`.
- **Expected:**
  - Step 1: the times are saved, and the page lists A and B as clashing.
  - Neither booking is removed.
  - Step 2: B shows the clash warning.
  - The calendar shows "Setup 30 min · Turnaround 45 min" and "Booked
    10:00–12:00 · venue in use 09:30–12:45".
- **Actual:** Staff saved 30/45 on the venue form and saw A and B listed as clashing; both bookings kept; the Coordinator saw the warning with "venue in use 09:30–12:45"; the calendar showed "Setup 30 min · Turnaround 45 min" and "Booked 10:00–12:00 · venue in use 09:30–12:45".
- **Status:** Pass
- **Evidence:** `tests/e2e/test_setup_turnaround.py::test_staff_set_setup_and_turnaround_see_the_clash_and_the_coordinator_is_warned[chromium]`; rerun 2026-10-08 with the hours/minutes boxes on a stack rebuilt from `.env.test`; full e2e suite: 26 passed.

## TC-E2E-227 — Venue Staff open a request from a compact list and decide it on its own page

- **Scenario:** The list stays short; the work happens on the request's page.
- **Pre-conditions:** As TC-E2E-228, plus a pending request P.
- **Steps:**
  1. Staff open their dashboard.
  2. Click P's row; reload the page.
  3. Place a hold, then approve P.
- **Expected:**
  - Step 1: each request is one row (event, venue, date and time, status);
    the list has no hold button or decision form.
  - Step 2: `/venue-bookings/{P}` shows P's details, a "Back to dashboard"
    link, Place hold and the decision form, and survives the reload.
  - Step 3: P shows "Held"; after approving, Staff return to the dashboard,
    see "Booking for … confirmed." once, and P is no longer listed.

  Existing journeys updated for this change: TC-E2E-209, 217, 218, 221, 223
  and 224 decided or held requests from the inline forms. Their steps now
  open the request's page from the dashboard row first; what each proves is
  unchanged.
- **Actual:** The list showed one compact row with no hold or decision controls; the request page loaded and survived a reload; hold then approval returned to the dashboard with "Booking for … confirmed." once, and the request left the list. TC-E2E-209, 217, 218, 221, 223 and 224, updated to open the request page, all passed in the same run.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_setup_turnaround.py::test_staff_open_a_request_from_a_compact_list_and_decide_it_on_its_page[chromium]`; `.env.test` stack rebuilt immediately before (venues container on the test project's `SUPABASE_URL`), 2026-10-08; 10 passed.

## TC-E2E-229 — Lead assigns an unassigned request and both recipients are notified

> **Renumbered 2026-10-08 from TC-E2E-226, which S-43 had already used on `main`.**

- **Scenario:** A real browser proves the S-83 role routing, Kong routes,
  queue UI, assignment controls, coordinator visibility, and persistent
  notifications that lower-level suites cannot prove together.
- **Pre-conditions:** Fresh `.env.test` stack and Chromium; the new
  `notifications` schema applied, granted, and exposed; temporary
  organiser, Event Coordinator Lead, coordinator, and unrelated accounts.
- **Steps:**
  1. Sign in as the organiser and submit `Autumn Forum`.
  2. Reload the organiser dashboard and confirm the request is under review
     but unassigned.
  3. Sign out, sign in as the Lead, and open the unassigned queue.
  4. Inspect the event information, choose the coordinator, and assign.
  5. Confirm the card leaves the queue.
  6. Sign in as the coordinator, confirm the event is in their assigned list
     and the assignment notification is visible, then reload and check again.
  7. Sign in as the organiser, confirm their assignment notification is
     visible, then reload and check again.
  8. Sign in as the unrelated user and confirm neither notification appears.
- **Test data:** `Autumn Forum`, `2026-11-18 09:00`–`12:00`, attendance `120`;
  generated test-user addresses.
- **Expected:** The Lead alone can complete assignment; the selected
  coordinator receives the event; the queue no longer contains it; organiser
  and coordinator each see their persistent in-app notification before and
  after reload; the unrelated user sees neither. No email/external action is
  performed.
- **Actual:** The organiser submitted the request, the Lead assigned it from
  the queue, and the card disappeared. The coordinator saw the assigned event
  and both recipients saw their own in-app notification before and after
  reload; the unrelated user saw neither.
- **Status:** Pass
- **Evidence:** `test_assign_event_request.py::test_lead_assigns_request_and_both_recipients_are_notified[chromium]`;
  local Chromium run against the freshly rebuilt `.env.test` stack: 1 passed.

## S-76 — detect booking conflicts incl. setup and turnaround

Story: S-76 Detect Booking Conflicts incl. Setup and Turnaround.
Confirmed by the developer on 2026-10-09. Executed 2026-10-09.

## TC-E2E-230 — Venue Staff are told which booking blocks an approval, and a confirmed clash stays on the dashboard

- **Scenario:** The refusal and the standing review list as Venue Staff see
  them, across a reload (S-76 AC3, AC5).
- **Pre-conditions:** A fresh `.env.test` stack and Chromium. Venue Staff, a
  test venue open every day 08:00–20:00 at setup 30, turnaround 45. On
  `D+3`: A confirmed 10:00–12:00 ("Alumni talk") and B pending 12:30–14:00;
  C confirmed 15:00–16:00 and E confirmed 16:30–17:00, both confirmed when
  the venue was 0/0.
- **Steps:**
  1. Staff open B from the request list and approve it.
  2. Staff open the dashboard, then reload it.
- **Expected:**
  - Step 1: an alert reads "Can't confirm this booking: it overlaps Alumni
    talk (confirmed), which occupies <venue> on <D+3> from 09:30 to 12:45
    (event 10:00–12:00, 30 min setup, 45 min turnaround)." B stays pending.
  - Step 2: "Clashes to review" lists the venue with the C–E pair, before
    and after the reload, with no Dismiss button. Nothing is removed.
- **Actual:** Approving B showed the specified alert naming Event A with 09:30–12:45; B stayed pending; "Clashes to review" listed the venue with C and E before and after reload, with no Dismiss; no booking removed.
- **Status:** Pass
- **Evidence:** `test_reassign_event_coordinator.py::test_lead_reassigns_event_and_transfers_access[chromium]`;
  local Chromium against a freshly rebuilt `.env.test` stack on 2026-10-09:
  1 passed.

## TC-E2E-238 — Lead oversees every Coordinator and sees reassignment move work

- **Scenario:** A real browser proves the S-85 grouped oversight view, idle
  Coordinator visibility, event summary, and S-84 refresh/update behaviour.
- **Pre-conditions:** Fresh `.env.test` stack; organiser, Lead, coordinators A
  and B; one submitted event assigned to A while B has no active assignment.
- **Steps:** Sign in as Lead; inspect both Coordinator groups, counts, and the
  event summary; reassign A→B with the existing control; inspect both groups
  and counts without reloading, then reload and inspect again.
- **Test data:** `Autumn Forum`, submitted, organiser Ada,
  `2026-11-18 09:00`–`12:00`.
- **Expected:** A initially contains the event with count 1 and B is visible
  with count 0. The summary shows name, status, organiser, date/time, and
  current Coordinator. After reassignment the event appears only under B,
  counts are A=0/B=1 immediately and after reload, and the S-83 queue remains
  present. The test identifies A and B by their unique account ID as well as their
  display name, so another account with the same name does not change which
  card is checked. Non-Lead access remains denied by the existing role journey.
- **Actual:** Chromium showed Alex at 1 and idle Blair at 0 with the complete
  event summary. Reassignment moved the card to Blair and changed the counts
  to 0/1 immediately; the same grouping survived reload and the queue remained
  visible. The account-ID locator selected the intended Blair card despite
  another account in the test project having the same display name.
- **Status:** Pass
- **Evidence:** `test_coordinator_overview.py::test_lead_overview_tracks_reassignment[chromium]`; [CI Chromium job](https://github.com/w3ixi4ng/SPM/actions/runs/40444107637/job/121995463408), 2026-10-27.

## TC-E2E-231 — Safety Officer completes an Operational Safety Check

> **S-17 (2026-10-19):** the event starts `pending_safety_check` and approval stores `confirmed`.

- **Scenario:** A Safety Officer reviews the cross-service safety evidence and
  approves a confirmed event through the browser.
- **Pre-conditions:** Fresh `.env.test` stack with S-86 Events SQL; confirmed
  undecided event; organiser, Coordinator, Technical Support, venue staff and
  Safety Officer accounts; confirmed venue and equipment requirement.
- **Steps:** Sign in as Safety Officer; open the queue event; inspect attendance,
  venue restriction/capacity, technical notes and equipment; approve; inspect
  the stored Events row.
- **Test data:** 120 attendees, capacity 200 theatre, wheelchair access, north
  exit restriction, speaker placement note and four wireless microphones.
- **Expected:** All evidence is visible; approval shows a success state and
  stores `preparation`, `approved`, and the authenticated Safety Officer id.
- **Actual:** Chromium showed the organiser, attendance, schedule, venue
  capacity/layout/accessibility/restriction, Technical Support assignment and
  notes, equipment, and special requirements. Approval showed the success
  state and stored `preparation`, `approved`, the authenticated Safety Officer
  id and a server timestamp.
- **Status:** Pass
- **Evidence:** `test_operational_safety_check.py::test_safety_officer_approves_an_enriched_pending_event[chromium]`;
  local run at commit `72886bb` on 2026-10-13 against the freshly recreated
  `.env.test` stack: combined S-77/S-87 browser regression, 5 passed.

## S-79 — book multiple venues for one event

Story: S-79 Book Multiple Venues for One Event.
Confirmed by the developer on 2026-10-11. Executed 2026-10-11 on branch `S-79/book-multiple-venues-for-one-event` (on top of `43b91d1`).

## TC-E2E-232 — Coordinator adds a second venue to an event and sees both with their status

- **Scenario:** The "Add another venue" journey works through Kong, and both
  bookings are still on the event page after a reload (S-79 AC1, AC3).
- **Pre-conditions:** The whole `.env.test` stack recreated immediately
  before; Chromium. A Coordinator assigned to a planning event E
  (`2026-11-12` 08:00–18:00, attendance 120). Two test venues, both open
  `thu` 08:00–20:00, with capacity 300 and 150.
- **Steps:**
  1. Sign in and open E. The link reads "Request venue".
  2. Request the 300-seat venue for `2026-11-12` 09:00–17:00, then land back on E.
  3. The link now reads "Add another venue". Follow it, request the 150-seat
     venue for `2026-11-12` 13:00–15:00, then land back on E.
  4. Reload the page.
- **Test data:** As above.
- **Expected:** After step 4, the "Venue requests" list for E shows both
  venues, each with its date, times and the status label "Pending". Cleanup
  deletes every row created.
- **Actual:** Chromium through Kong: "Request venue" sent the Hall request; "Add another venue" reached the request screen and sent the Studio request; after a reload both rows showed 12 Nov 2026, their times and "Pending".
- **Status:** Pass
- **Evidence:** `test_book_multiple_venues.py::test_a_coordinator_adds_a_second_venue_and_sees_both_with_their_status[chromium]`; `.env.test` stack recreated immediately before, 2026-10-11. With `test_tentative_hold.py` and `test_request_venue.py`: 4 passed, 1 failed (TC-E2E-223, did not reproduce); rerun of the S-79 and S-33 files: 4 passed.

## S-62 — request event cancellation

Story: S-62 Request Event Cancellation.
Confirmed by the developer on 2026-10-11.
TC-E2E-232 is skipped because S-79's unmerged branch uses it.

## TC-E2E-233 — Organiser confirms a cancellation request and the event is not shown as cancelled

- **Scenario:** The confirm step, the success message and the unchanged
  status all work in a real browser through Kong (S-62 AC1, AC2, AC4, AC5).
- **Pre-conditions:** The whole `.env.test` stack recreated immediately
  before; the S-62 SQL applied; Chromium. An Organiser who owns a `planning`
  event E.
- **Steps:**
  1. Sign in and open E. Click **Request cancellation**; a panel opens.
  2. Enter the reason and click **Review request**. The panel asks "Cancel
     this event?" and quotes the reason. Click **Keep event**.
  3. Open the panel again, enter the reason, click **Review request**, then
     **Send cancellation request**.
  4. Reload the page.
  5. Go back to the dashboard (added 2026-10-11).
- **Test data:** Reason `"Keynote speaker withdrew"`.
- **Expected:**
  - After step 2, the panel is closed and `events.events` has no
    cancellation request for E.
  - After step 3, the page says "Cancellation request sent. Your event stays
    in planning until it has been reviewed."
  - After step 4, the status badge still reads "Planning", the page shows
    "Cancellation requested on <today>" with the reason, and **Request
    cancellation** is gone. `events.events` has E still `planning`, with the
    reason stored.
  - After step 5, E's row on the dashboard shows "Planning" and, beside
    it, "Cancellation requested".
  Cleanup deletes every row created.
- **Actual:** Chromium: **Keep event** closed the panel with nothing stored; confirming showed "Cancellation request sent. Your event stays in planning until it has been reviewed."; after a reload the badge read "Planning", the marker and reason were shown, the button was gone, and `events.events` had E `planning` with the reason. On the dashboard, E's row showed "Planning" with "Cancellation requested" beside it.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_request_event_cancellation.py::test_an_organiser_confirms_a_cancellation_request_and_the_event_is_not_cancelled[chromium]`; `.env.test` stack recreated immediately before (events container verified on the test project's `SUPABASE_URL`), 2026-10-11, with the dashboard tag. With `test_rejected_tab.py`: 2 passed.
## S-77 — mark venue temporarily unavailable

Story: S-77 Mark Venue Temporarily Unavailable. Confirmed by the developer on 2026-10-12.

Executed 2026-10-12 on branch `S-77/mark-venue-temporarily-unavailable`. Needs:
- the S-77 SQL for `bookings` and `notifications` in the test project;
- the whole `.env.test` stack, recreated immediately before.

Validation, overlap rules and status codes are covered by the unit and
integration cases. This journey proves only what a browser can: the panel,
the affected-bookings summary, and the flag and notification reaching the
Coordinator.

## TC-E2E-234 — Venue Staff mark a period over a confirmed booking, and its Coordinator sees the notification and the flag

- **Scenario:** In a real browser through Kong, a timed period is marked
  with a reason. The confirmed booking under it is shown to Venue Staff as
  affected, and its Coordinator is notified and sees the booking flagged. The
  event and booking stay as they were (AC1, AC3, AC4, AC5).
- **Pre-conditions:** The whole `.env.test` stack recreated immediately
  before. The S-77 SQL applied. Chromium. Created with the admin client:
  - a Venue Staff user and a Coordinator;
  - a venue `"spm-e2e Venue <hex>"`, open every day `08:00`–`20:00`, setup
    and turnaround 0;
  - a `planning` event E `"spm-e2e Event <hex>"` assigned to the
    Coordinator;
  - a confirmed booking K for E at the venue, `2026-11-12` `10:00`–`12:00`.
- **Steps:**
  1. Sign in as Venue Staff. Open the venue's availability calendar and
     click **Mark unavailable**.
  2. Enter `2026-11-12` `09:00` to `2026-11-12` `13:00`. Choose "Other
     operational reason", leave the description empty, and click **Mark
     unavailable**.
  3. Enter the description `"Water leak in ceiling"` and click **Mark
     unavailable** again.
  4. Sign out and sign in as the Coordinator.
  5. Open E.
- **Expected:**
  - After step 2, the panel says "Describe the operational reason." and
    nothing is stored in `bookings.blocks`.
  - After step 3, the panel says "1 booking needs alternative arrangements.
    Their Coordinators have been notified." and lists E's name with
    "12 Nov 2026 · 10:00–12:00 · Booked".
  - After step 4, the dashboard's notifications list a message naming the
    venue and ending "needs alternative arrangements."
  - After step 5, K's row shows "Needs alternative arrangements" with the
    period and "Other operational reason: Water leak in ceiling". It still
    reads "Confirmed" (the event page's word for it; the panel in step 3
    uses the calendar's "Booked"), and E's status still reads "Planning".
    Corrected 2026-10-12 while writing the test.
  - With the admin client, K is still `confirmed` and E still `planning`.
  Cleanup deletes the block, K, the notification, E, the venue and both users.
- **Actual:** In Chromium through Kong: the empty description was refused with "Describe the operational reason." and nothing stored; the saved panel said "1 booking needs alternative arrangements. Their Coordinators have been notified." and listed E as Booked; the Coordinator's dashboard showed the notification; E's page flagged K with the period and "Other operational reason: Water leak in ceiling", still Confirmed and Planning; K `confirmed` and E `planning` in the database.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_mark_venue_unavailable.py::test_staff_mark_a_period_over_a_confirmed_booking_and_its_coordinator_is_told`; `.env.test` stack recreated immediately before, 2026-10-12; `pytest tests/e2e`: 35 passed

## S-78 — request replacement venue for affected booking

Story: S-78 Request Replacement Venue for Affected Booking. Confirmed by the
developer on 2026-10-14. Test in `test_replace_affected_booking.py`. Executed 2026-10-14 after the S-78
SQL for `bookings` was run in the test project. Needs the whole `.env.test`
stack, recreated immediately before.

The search rules, the one-at-a-time rule and the resolution rules are covered
by the unit and integration cases. This journey proves only what a browser
can: the way in from the flagged booking, the replacement screen, and the
original's state after Venue Staff approve.

## TC-E2E-242 — a Coordinator replaces a flagged booking without re-entering the event, and approval clears the flag

- **Scenario:** In a real browser through Kong, from the flagged booking to
  a confirmed replacement (AC1–AC4).
- **Pre-conditions:** The whole `.env.test` stack recreated immediately
  before. The S-78 SQL applied. Chromium. Created with the admin client:
  - a Venue Staff user and a Coordinator;
  - venues `"spm-e2e Venue A <hex>"` and `"spm-e2e Venue B <hex>"`, both
    open every day `08:00`–`20:00`, both suitable for E, with setup and
    turnaround 0;
  - a `planning` event E assigned to the Coordinator;
  - a confirmed booking K for E at Venue A, `2026-11-12` `10:00`–`12:00`;
  - a period on Venue A from `2026-11-12` `09:00` to `13:00`.
- **Steps:**
  1. Sign in as the Coordinator, open E, and click **Find a replacement venue** on K's row.
  2. On the replacement screen, choose Venue B and click **Send replacement request**.
  3. Sign out and sign in as Venue Staff. Open the new request and approve it.
  4. Sign out, sign in as the Coordinator, and open E.
- **Expected:**
  - Step 1 opens `/coordinator/events/<E>/bookings/<K>/replacement`, which
    shows E's name, "12 Nov 2026 · 10:00–12:00" and E's requirements as
    read-only text. Venue B is listed and Venue A is not. There are no
    inputs for date, time, attendance or requirements.
  - After step 2 the page returns to E with "Replacement request sent to
    Venue B." K's row still says "Needs alternative arrangements" and
    "Replacement requested: Venue B, waiting for Venue Staff".
  - In step 3, Venue Staff's request page shows "Replacement for Venue A".
  - After step 4, K's row reads "Replaced by Venue B" with no flag. Venue
    B's row reads "Confirmed".
  - With the admin client, K is `replaced` and the new row is `confirmed`
    with `replaces_booking_id` K.
  Cleanup deletes the period, both bookings, E, both venues and both users.
- **Actual:** In Chromium through Kong: the link opened the replacement screen with the event, date, times and requirements read-only and no date, time or number inputs; Venue B listed, Venue A not. After sending, K was still flagged with "Replacement requested: Venue B, waiting for Venue Staff". Venue Staff's page said "Replacement for Venue A". After approval K read "Replaced by Venue B" with no flag and Venue B's row read Confirmed; in the database K `replaced`, the new row `confirmed` with `replaces_booking_id` K.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_replace_affected_booking.py::test_a_coordinator_replaces_a_flagged_booking_and_approval_clears_the_flag`; `.env.test` stack recreated immediately before (bookings container verified on the test project's `SUPABASE_URL`), 2026-10-14
## TC-E2E-235 — requested safety changes complete a fresh review cycle

> **S-17 (2026-10-19):** the path is `pending_safety_check → planning → pending_safety_check → confirmed`, and resubmission needs every arrangement complete.

- **Scenario:** The browser proves S-87 across both roles and the existing
  arrangement workflow.
- **Pre-conditions:** Fresh `.env.test` stack with S-87 Events SQL; confirmed
  event with assigned Coordinator, Safety Officer, confirmed venue, equipment
  requirement and Technical Support assignment.
- **Steps:** Safety Officer requests changes; Coordinator sees the returned
  marker and feedback; revises Technical Support notes; resubmits; Safety
  Officer sees the event reappear and approves it; inspect storage.
- **Test data:** Feedback `Move speakers away from the east emergency exit`;
  revised notes `Speakers moved to the west wall away from emergency exits`.
- **Expected:** The journey is `changes_requested → planning → revise/resubmit
  → confirmed → Safety Officer queue → fresh approval → preparation`.
  History contains both reviews, and the confirmed venue remains untouched.
- **Actual:** Chromium showed the returned marker, Safety Officer feedback and
  `planning` state to the assigned Coordinator. The revised Technical Support
  notes were saved before resubmission; the event reappeared in the Safety
  Officer queue and fresh approval produced `preparation`. Storage retained
  both reviews, the revised notes and the original confirmed booking.
- **Status:** Pass
- **Evidence:** `test_operational_safety_check.py::test_safety_changes_return_to_coordinator_and_receive_a_fresh_approval[chromium]`;
  local run at commit `72886bb` on 2026-10-13 against the freshly recreated
  `.env.test` stack: combined S-77/S-87 browser regression, 5 passed.

## S-80 — change or cancel an individual venue booking

Story: S-80 Change or Cancel an Individual Venue Booking.
Confirmed by the developer on 2026-10-14.

## TC-E2E-236 — Coordinator changes one venue booking and cancels another; the third is untouched

- **Scenario:** The change screen and the cancel panel work through Kong,
  and the event's other bookings stay as they were (S-80 AC1, AC2).
- **Pre-conditions:** The whole `.env.test` stack recreated immediately
  before; Chromium. K assigned to planning E with two `confirmed` bookings:
  Hall 09:00–12:00 and Studio 13:00–15:00, both on `2026-11-12`.
- **Steps:**
  1. K opens E. Click **Change** on the Studio booking; the change screen
     opens with Studio, 12 Nov, 13:00–15:00 filled in.
  2. Set 15:00–17:00 and click **Save changes**.
  3. Click **Cancel** on the Hall booking; the panel names it. Click
     **Keep booking**.
  4. Click **Cancel** on the Hall booking again, then **Cancel booking**.
  5. Reload.
- **Expected:**
  - After 2: back on E with "Venue booking changed. It's pending until
    Venue Staff review it again."; the Studio row reads 15:00–17:00
    "Pending"; the Hall row still reads 09:00–12:00 "Confirmed".
  - After 3: nothing changed.
  - After 4 and 5: "Venue booking cancelled. Its time is free for other
    events." (after 4); only the Studio row remains, 15:00–17:00 Pending.
  Cleanup deletes every row created.
- **Actual:** Chromium: Change opened the screen pre-filled 13:00; saving 15:00–17:00 returned to E with the changed notice, the Studio row Pending 15:00–17:00 and the Hall row still Confirmed 09:00–12:00; Keep booking changed nothing; Cancel booking showed the cancelled notice; after a reload only the Studio row remained.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_change_cancel_booking.py::test_a_coordinator_changes_one_booking_and_cancels_another[chromium]` `.env.test` stack recreated immediately before (bookings container verified on the test project's `SUPABASE_URL`), 2026-10-15, after merging sprint3 (S-78, S-87) into this branch, re-applying S-77's SQL and relaxing S-24's unmerged `bookings_hold_valid` back to sprint3's rule on the test project. With the S-77, S-78, S-30, S-33 and S-79 venue journeys: 8 passed, 1 failed (S-78's replacement journey: its venue search makes two sequential reads per venue, about 80 for the 41 venues on the test project, and outlasts the 20 s wait; S-80 changes nothing on that path). A first run had failed on a DNS outage and was rerun.

## TC-E2E-237 — Lead sees profile-less Coordinators but not invalid owners

- **Scenario:** The S-85 browser view distinguishes eligible Coordinators from active events with invalid owners, while preserving S-83 and S-84 controls.
- **Pre-conditions:** Fresh `.env.test` stack and disposable fixtures: a profiled Coordinator with one event, a profile-less trusted Coordinator with zero events, and an active event whose Auth owner has been deleted. All fixture changes are cleaned up.
- **Steps:** Sign in as Lead; inspect the oversight groups and separate integrity warning; use S-84 to reassign the valid event to the profile-less Coordinator; reload; inspect the S-83 assignment queue.
- **Test data:** Profiled `Alex <alex@example.com>`; profile-less Auth identity `blair@example.com`; deleted owner D; one event for Alex and one orphaned event for D.
- **Expected:** Blair appears as a zero-assignment Coordinator using Auth identity display. D never appears as a Coordinator group; its event is reported only in the integrity warning. Reassignment moves the valid event to Blair and updates counts both immediately and after reload. The S-83 queue remains available; the orphan's assignment is not changed.
- **Actual:** Chromium showed the profile-less Coordinator under its Auth email with count 0 and the deleted owner's event only in the integrity warning. The email-labelled S-84 choice moved the valid event and updated counts before and after reload; the S-83 queue remained visible.
- **Status:** Pass
- **Evidence:** `test_coordinator_overview.py::test_lead_sees_profileless_coordinator_and_invalid_assignment_separately[chromium]`; freshly recreated `.env.test` stack, 2026-10-18, after merging `sprint3`; four targeted browser journeys passed.

## Merged-branch ID reconciliation

The earliest allocation of each test ID remains canonical. Later cases from
parallel story branches were renumbered when those branches met: S-85
overview `230` -> `238`, S-26 preparation `232` -> `239`, S-81 hold expiry
`235` -> `240`, S-24 readiness `233` -> `241`, and S-78 replacement `235` ->
`242`. Earlier branch references to those old IDs identify the same cases.

## S-26 — Update Equipment Preparation Status

### TC-E2E-239 — assigned Technical Support updates preparation and the Coordinator sees it

- **Scenario:** A browser proves the protected S-26 write, persistence, and read-only Coordinator visibility.
- **Pre-conditions:** Fresh `.env.test` stack with S-26 Events SQL; planning event assigned to a Coordinator and Technical Support A.
- **Steps:** Sign in as A; observe Not Started; change to In Progress and then Ready; reload; sign in as the assigned Coordinator and open the event.
- **Test data:** One event requiring equipment and assigned support.
- **Expected:** Each save confirms the server response. Ready survives reload. The Coordinator sees Ready on the event readiness view and no preparation edit control. Direct storage inspection shows Ready, A's id, and a non-null server timestamp.
- **Actual:** Not run.
- **Status:** Approved
- **Evidence:** `test_equipment_preparation.py::test_support_updates_preparation_and_coordinator_sees_it`

## S-24 — Track Event Readiness

### TC-E2E-241 — Coordinator readiness follows current venue, equipment, and preparation data

- **Scenario:** The assigned Coordinator sees all five readiness areas on the event view.
- **Pre-conditions:** Fresh `.env.test` stack; an assigned planning event with a confirmed venue, recorded equipment requirement, and preparation Ready.
- **Steps:** Sign in as the Coordinator; open the event; inspect readiness; change the server-owned preparation status to In Progress; reload.
- **Expected:** Initially Venue, Equipment, and Technical support are Complete and the total is 3 of 3. Programme and Registration are visible as Not available yet. After the underlying change and reload, Technical support becomes Outstanding and the total becomes 2 of 3 without a duplicate readiness record being edited.
- **Actual:** The Coordinator saw all five indicators, three implemented areas complete, and two future areas unavailable. After preparation changed to In Progress and the page reloaded, the total changed to 2 of 3 and Technical support became Outstanding.
- **Status:** Pass
- **Evidence:** `test_event_readiness.py::test_coordinator_readiness_tracks_current_underlying_data`

## TC-E2E-240 — a tentative hold expires and releases its slot

- **Scenario:** Venue Staff place a visibly tentative hold with a required
  expiry; its Coordinator is informed before it expires and the same
  venue/time becomes available again.
- **Expected:** Blank expiry is refused; the request and calendar show the
  hold and expiry distinctly; the Coordinator receives an expiry notice; the
  calendar removes the hold after expiry without manual release and storage
  records `expired`.
- **Actual:** Chromium refused a blank expiry, displayed the active hold and
  expiry, showed the Coordinator notice, and showed the slot as available
  after automatic expiry; storage recorded `pending/expired`.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_tentative_hold_expiry.py::test_tentative_hold_expiry_is_visible_notified_and_releases_the_slot`; `.env.test` stack recreated immediately before, 2026-10-13; full suite reached 35 passed with only this new assertion pending, then the corrected S-81 journey passed on its complete focused rerun (all 36 journeys passed).

---

## S-18 — Update Event Information

Story: S-18 Update Event Information. Specification confirmed by the
developer on 2026-10-19. S-18 records history for future S-82 display; the
S-82 history screen itself is outside this journey because that story is not
yet present.

## TC-E2E-244 — Coordinator saves routine and significant edits without losing arrangements

- **Scenario:** A browser proves the complete assigned-Coordinator editing and
  re-review journey through Kong.
- **Pre-conditions:** Fresh `.env.test` stack with S-18 SQL; Coordinator A;
  A's preparation event E with contact information, confirmed venue booking,
  equipment requirement, equipment preparation Ready, Technical Support
  assignment, and one completed safety-review history entry.
- **Steps:**
  1. Sign in as A, open E, edit the contact phone and internal note, save and
     reload.
  2. Change attendance and end time. Review the impact summary and cancel.
  3. Repeat the significant edit and accept it.
  4. Confirm existing arrangements remain visible, then submit E for a fresh
     Operational Safety Check and reload.
- **Expected:** Step 1 persists immediately without changing Preparation or
  asking for re-review. Step 2 changes nothing. Step 3 shows the new values and
  Planning with a clear fresh-safety-check message. The confirmed booking,
  requirement, Ready state, assignment, and prior safety history remain.
  Step 4 passes S-17 readiness and leaves E Pending Safety Check. Only a
  Safety Officer can later confirm it. Direct storage
  contains ordered audit entries naming only the fields changed, A's UUID and
  server times. Cleanup removes all fixtures.
- **Actual:** The browser saved routine contact/notes, cancelled an impact
  review without changing storage, accepted attendance/time changes, retained
  the confirmed venue and equipment requirement, and submitted the revised
  event for a fresh safety decision. Direct storage contained two ordered
  Coordinator audit entries and preserved preparation, assignment, and prior
  safety history.
- **Status:** Pass
- **Evidence:** `test_update_event_information.py::test_coordinator_updates_event_and_restarts_safety_lifecycle`; focused Chromium run through Kong against a freshly recreated `.env.test` stack, 2026-10-19.
## TC-E2E-243 — Coordinator submits for the safety check; the Organiser sees Confirmed

- **Scenario:** The journey only a browser can prove: the outstanding list,
  the gateway routes and each role's view of the new stage.
- **Pre-conditions:** Full stack on `.env.test` with the S-17 SQL; Chromium;
  an event in `planning` with one `pending` booking and one equipment
  requirement, Technical Support assigned.
- **Steps:** 1. As the Coordinator, open the event; click "Submit for safety
  check". 2. As Venue Staff, confirm the booking; as Technical Support,
  approve and set preparation Ready. 3. As the Coordinator, reload and submit.
  4. As the Organiser, open the event. 5. As the Safety Officer, approve it.
  6. As the Organiser, reload.
- **Test data:** As above.
- **Expected:** 1 lists "Hall A on 20 Nov 2026 is waiting for Venue Staff",
  "Technical Support has not approved the equipment arrangements",
  "Equipment preparation is Not Started"; no override control is on the
  page; status still "Planning". 3 shows "Pending Safety Check". 4 shows
  "Pending Safety Check". 6 shows "Confirmed".
- **Actual:** Passed on 2026-10-19 against a fresh `.env.test` stack with the S-17 SQL applied: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_confirm_event.py::test_submit_for_safety_check_to_confirmed`


## S-61 — review and approve cancellation request

Story: S-61 Review and Approve Cancellation Request.
Confirmed by the developer on 2026-10-11.

## TC-E2E-245 — Coordinator approves a cancellation and the event shows as Cancelled for both sides

- **Scenario:** The Coordinator's review journey works through Kong, the
  venue booking disappears, and the Organiser sees the result (S-61 AC1, AC2).
- **Pre-conditions:** The whole `.env.test` stack recreated immediately
  before; the S-61 SQL applied; Chromium. Coordinator K assigned to
  `planning` event E, owned by Organiser O. E has a pending cancellation
  request ("Keynote speaker withdrew") and one `confirmed` booking of a test
  venue.
- **Steps:**
  1. K signs in. E's row on the dashboard shows "Cancellation requested".
     K opens E.
  2. The page shows the Organiser's reason. K clicks **Approve
     cancellation**. The panel says "1 venue booking will be removed and its
     time freed." K clicks **Keep event**.
  3. K clicks **Approve cancellation** again, then **Cancel event**.
  4. K reloads the page.
  5. O signs in and opens the dashboard.
- **Expected:**
  - After step 2, nothing has changed in `events.events` or
    `bookings.bookings`.
  - After step 3, the page says "Event cancelled. 1 venue booking was
    released."
  - After step 4, the badge reads "Cancelled", the venue requests list is
    empty, and no decision buttons remain. `bookings.bookings` has no rows
    for E.
  - After step 5, E's row reads "Cancelled" with no tag beside it.
  - Opening E then shows "Your cancellation request was approved. This event
    is cancelled.", with no empty decision banner, and the form is read-only
    (added 2026-10-11 after a manual check found both).
  Cleanup deletes every row created.
- **Actual:** Chromium: the Events tab showed "Cancellation requested" on E; the reason was shown; the panel said "1 venue booking will be removed and its time freed."; Keep event changed nothing; Cancel event showed "Event cancelled. 1 venue booking was released."; after a reload the badge read "Cancelled", the venue requests list was empty and no decision buttons remained, with E `cancelled` and no bookings stored; the Organiser's row read "Cancelled" with no tag.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_approve_cancellation.py::test_a_coordinator_approves_a_cancellation_and_both_sides_see_cancelled[chromium]`; `.env.test` stack recreated immediately before (events and bookings containers verified on the test project's `SUPABASE_URL`), 2026-10-11, branch `S-61/review-and-approve-cancellation-request`; S-61 SQL applied to dev and test. The first run failed in the test, not the feature: the Coordinator dashboard opens on its Venues tab, so the test now selects Events first. Rerun with `test_request_event_cancellation.py` and `test_coordinator_overview.py`: 3 passed. Rerun 2026-10-11 after fixing the empty banner and the editable form on a cancelled event: one run failed waiting 5 s for the venue list to load (now 20 s, as every other wait in the test); then, with `test_request_event_cancellation.py` and `test_respond_to_return.py`, 3 passed. Re-verified 2026-10-21 after merging sprint3 (S-17, S-18, S-24, S-78, S-80, S-87) into this branch and re-applying the S-61 `events_decision_matches_status` rule (with S-87's `pending_safety_check`) to dev and test: with the S-62, S-80 and safety-check journeys, 5 passed. An earlier batch run timed out waiting for S-62's Request cancellation button under load; it passed alone in 30 s and in the full rerun.

## TC-E2E-246 — Organiser sets a registration period, and it's fixed once submitted

- **Scenario:** The Organiser can turn registration on and set the period while creating the request, and can't change it after submitting (S-51 AC1, AC2).
- **Pre-conditions:** The whole `.env.test` stack recreated immediately
  before; S-51 SQL applied; Chromium. Organiser O; at least one Coordinator.
- **Steps:**
  1. O signs in, starts a new event request starting `2026-12-10 18:00`,
     turns **Registration** on.
  2. Sets closing `2026-12-10 19:00` and opening `2026-11-01 09:00`; clicks
     **Submit request**.
  3. Changes closing to `2026-12-05 18:00`; submits.
  4. Opens the submitted request.
- **Expected:** 2 shows "Registration must close before the event starts." and
  nothing is submitted. 3 submits. 4 shows "Registration opens 1 Nov 2026,
  9:00 am and closes 5 Dec 2026, 6:00 pm." with no control to change it.
- **Actual:** Chromium: closing at 7:00 pm on the start day showed "Registration must close before the event starts." and stayed on `/events/new`; closing 5 Dec submitted; after a reload the period read "Registration opens 1 Nov 2026, 9:00 am and closes 5 Dec 2026, 6:00 pm." with no toggle or pickers.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_set_registration_period.py::test_organiser_sets_a_registration_period_fixed_once_submitted`; `.env.test` stack recreated with `--build` immediately before (events, users, registrations verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-51/configure-registration-and-open-close-period`; S-51 SQL applied to the test project; run headed with `--slowmo 400`: 3 passed in 70 s

## TC-E2E-247 — a visitor reads a confirmed event, then registers as an Attendee

- **Scenario:** Public details without signing in; a place only once registered (S-51 AC4, AC5).
- **Pre-conditions:** As TC-E2E-246. Through the admin client: confirmed event
  P with a confirmed booking, registration open from yesterday to next week;
  Attendee account A.
- **Steps:**
  1. Signed out, open `/public/events/P`.
  2. Click **Register**.
  3. Sign in as A; open `/public/events/P` again, click **Register**.
  4. Reload the page.
- **Expected:** 1 shows P's name, purpose, dates and times, venue, and its
  registration period. 2 goes to sign-in. 3 shows "You're registered for
  this event." 4 still shows it.
- **Actual:** Chromium: signed out, the page showed the name, purpose, booked venue and period; Register went to `/login`; as the Attendee, Register showed "You're registered for this event.", which survived a reload with no Register button.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_register_for_event.py::test_a_visitor_reads_a_confirmed_event_then_registers_as_an_attendee`; `.env.test` stack recreated with `--build` immediately before (events, users, registrations verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-51/configure-registration-and-open-close-period`; S-51 SQL applied to the test project; run headed with `--slowmo 400`: 3 passed in 70 s

## TC-E2E-248 — an Attendee is told registration hasn't opened yet

- **Scenario:** Attempts outside the period are blocked with a message (S-51 AC3; S-48 AC1, AC2).
- **Pre-conditions:** As TC-E2E-247, plus confirmed event Q whose registration
  opens in 7 days.
- **Steps:** As A, open `/public/events/Q`.
- **Expected:** "Registration hasn't opened yet. It's open from {Q's opening} to {Q's closing}."
  (e.g. "… from 1 Nov 2026, 9:00 am to 10 Nov 2026, 5:00 pm.")
  is shown and there is no enabled **Register** button.
- **Actual:** Chromium: the page showed "Registration hasn't opened yet. It's open from {opening} to {closing}." and no Register button.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_register_for_event.py::test_an_attendee_is_told_registration_hasnt_opened_yet[chromium]`; `.env.test` stack recreated with `--build` immediately before (users, events, registrations verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-48/register-for-event`; with `test_set_registration_period.py`: 4 passed in 58 s; rerun headed with `--slowmo 400` on a freshly recreated `.env.test` stack: 3 passed in 50 s

## S-88 confirmed specification — Coordinator request to Lead action

Confirmed by the developer on 2026-10-25. Latest execution: S-88 branch, uncommitted, Chromium against fresh `.env.test` stack.

## TC-E2E-249 — requester sees the Lead's completed reassignment

- **Scenario:** The whole browser journey carries a request through Lead review to an actioned outcome.
- **Pre-conditions:** Fresh `.env.test` stack through Kong and Chromium; an Organiser's event is assigned by Lead A to Coordinator A; Coordinator B is eligible.
- **Steps:** Sign in as A and request reassignment from the event; refresh and check pending; sign in as Lead A and review the request; reassign using the existing S-84 control; sign in again as A and check request history after event access moves to B.
- **Test data:** Event `November Forum`; reason `Cannot cover the November event`; Lead A, Coordinator A and B test accounts.
- **Expected:** Lead A sees requester, event, reason and pending status; A stays owner until Lead A reassigns; after S-84, B owns the event and A sees `actioned` despite no longer owning it.
- **Actual:** Chromium showed Lead A the pending request and unchanged owner; S-84 moved the event to B, then A saw the actioned request in their history.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_request_reassignment_from_lead.py::test_coordinator_request_is_actioned_after_lead_reassignment[chromium]`; 2026-10-25.

## TC-E2E-250 — Lead request empty, error, and retry states

- **Scenario:** The Lead request view explains an empty queue and recovers from a failed read.
- **Pre-conditions:** Fresh `.env.test` stack and a Lead account with no reassignment requests.
- **Steps:** Open the Lead dashboard; observe the empty state; make the list API return `502` and reload; restore the API and choose Try again.
- **Test data:** `GET /api/event-requests/reassignment-requests/lead`; injected `{"detail":"Events service unavailable"}`.
- **Expected:** Empty message is visible initially; a safe error appears on failure with a retry button; retry restores the empty message.
- **Actual:** Chromium showed the empty state, then a safe read error and retry control; retry restored the empty state.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_request_reassignment_from_lead.py::test_lead_request_empty_error_and_retry_states[chromium]`; 2026-10-25.

## TC-E2E-251 - Venue Staff prepare two venues and readiness updates
- **Scenario:** Venue Staff update two confirmed bookings and the Coordinator sees both states.
- **Expected:** Both per-venue states are visible; the venue indicator completes only after both are Ready.
- **Actual:** Venue Staff moved the first venue through In Progress to Ready and the second to Ready; after switching accounts, the Coordinator saw both venue names and `2 of 2 confirmed venues Ready`.
- **Status:** Pass.
- **Evidence:** `tests/e2e/test_venue_preparation.py::test_staff_prepare_each_venue_and_coordinator_sees_readiness[chromium]`; `.env.test` stack recreated with `--build` immediately before; 1 passed on 2026-10-25.

## S-48 — Register for Event

## TC-E2E-252 — an Attendee's registration shows on their dashboard and on the Organiser's event

- **Scenario:** One registration in the browser is recorded against both the Attendee and the event (S-48 AC3).
- **Pre-conditions:** As TC-E2E-247, plus Organiser O who owns P. A has the
  name "S-48 E2E Attendee".
- **Steps:**
  1. As A, open `/dashboard`.
  2. Open `/public/events/P`, click **Register**.
  3. Open `/dashboard` again.
  4. Sign out; sign in as O; open `/events/P`.
- **Test data:** As above; emails `spm-e2e-*`.
- **Expected:** 1 shows "Your registrations" with "You haven't registered for
  any events yet." 3 lists P by name, with its date and a link to
  `/public/events/P`. 4 shows "Registered attendees" with "1 attendee
  registered" and a row with A's name and email.
- **Actual:** Chromium: the dashboard first said "You haven't registered for any events yet."; after registering it linked the event to `/public/events/P` with its date; the Organiser's `/events/P` showed "1 attendee registered" with A's name and email.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_register_for_event.py::test_a_registration_shows_on_the_attendees_dashboard_and_the_organisers_event[chromium]`; `.env.test` stack recreated with `--build` immediately before (users, events, registrations verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-48/register-for-event`; with `test_set_registration_period.py`: 4 passed in 58 s; rerun headed with `--slowmo 400` on a freshly recreated `.env.test` stack: 3 passed in 50 s

## S-50 — Cap Registration at Capacity

## TC-E2E-253 — a full event turns the next Attendee to the waiting list

- **Scenario:** In a real browser: the event fills, the next Attendee joins the waiting list, and the Organiser sees them (S-50 AC1, AC2).
- **Pre-conditions:** Fresh `.env.test` stack, Chromium. Through the admin
  client: Organiser O; confirmed event P owned by O, `expected_attendance` 1,
  registration open yesterday to tomorrow (SGT); Attendees A and B.
- **Steps:**
  1. As A, open `/public/events/P` and click **Register**.
  2. As B, open `/public/events/P`.
  3. Click **Join the waiting list**; reload.
  4. As O, open `/events/P`.
- **Expected:** 1 → "You're registered for this event.". 2 → the status
  reads "This event is full. You can join the waiting list.", there is no
  **Register** button, and a **Join the waiting list** button is shown. 3 →
  "You're on the waiting list." both before and after the reload. 4 → the
  Registered attendees section lists A and the Waiting list section lists B.
- **Actual:** A registered; B saw the full message, no Register, joined and stayed on the waiting list after reload; O saw A registered and B on the waiting list.
- **Status:** Pass
- **Evidence:** tests/e2e/test_cap_registration.py::test_a_full_event_turns_the_next_attendee_to_the_waiting_list; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-E2E-254 — the Organiser closes registration early and reopens it

- **Scenario:** The close decision is the Organiser's and takes effect for Attendees at once (S-50 AC4).
- **Pre-conditions:** As TC-E2E-253, but `expected_attendance` 50 and only Attendee A.
- **Steps:**
  1. As O, open `/events/P`, click **Close registration**, then confirm with **Close registration** in the confirmation that appears.
  2. As A, open `/public/events/P`.
  3. As O, click **Reopen registration**.
  4. As A, reload `/public/events/P`.
- **Expected:** 1 → "You closed registration on {today}, {time}. Attendees
  can't register until you reopen it." and a **Reopen registration** button.
  2 → "The organiser has closed registration for this event.", no
  **Register** and no **Join the waiting list**. 4 → **Register** is back.
- **Actual:** O closed after confirming and saw the closed line with Reopen; A saw the closed message with no Register or waiting list; after reopening A saw Register.
- **Status:** Pass
- **Evidence:** tests/e2e/test_cap_registration.py::test_the_organiser_closes_registration_early_and_reopens_it; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-E2E-255 — a waitlisted Attendee sees their place in line, not a confirmation

- **Scenario:** In a real browser: an Attendee joins a full event's waiting list behind someone else, sees their place on the event page, and their dashboard marks the event as waiting, not confirmed (S-52 AC1, AC2, AC3).
- **Pre-conditions:** Fresh `.env.test` stack, Chromium. Through the admin client: Organiser O; confirmed event P owned by O, `expected_attendance` 1, registration open yesterday to tomorrow (SGT); Attendees A, B and C; A holds P's one place; B is on P's waiting list.
- **Steps:**
  1. As C, open `/public/events/P` and click **Join the waiting list**; reload.
  2. As C, open the dashboard.
  3. As A, open the dashboard.
- **Expected:** 1 → "You're on the waiting list. You're 2nd in line." both before and after the reload, and no **Register** or "You're registered for this event.". 2 → the "Your registrations" row for P reads "Waiting list · 2nd in line" and not "Confirmed". 3 → the row for P reads "Confirmed".
- **Actual:** C joined and saw "You're on the waiting list. You're 2nd in line." before and after reload, with no Register or registered line; C's dashboard row read "Waiting list · 2nd in line" with no "Confirmed"; A's row read "Confirmed".
- **Status:** Pass
- **Evidence:** tests/e2e/test_join_waiting_list.py::test_a_waitlisted_attendee_sees_their_place_in_line; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), 2026-10-26, branch `S-52/join-waiting-list` (on S-50 `a3011b3`), pre-commit working tree

## S-01 — User accounts: choose Attendee or Event Organiser at sign-up

## TC-E2E-260 — an Attendee sign-up lands on the Attendee dashboard

- **Scenario:** Choosing Attendee on the real form ends on the Attendee
  dashboard, and the page will not submit until a role is chosen (AC1, AC3).
- **Pre-conditions:** As TC-E2E-201.
- **Steps:**
  1. Open `/signup` through Kong; check neither **Attendee** nor **Event
     Organiser** is selected.
  2. Fill every other field and submit.
  3. Choose **Attendee** and submit again.
- **Test data:** As TC-E2E-201, with a fresh `spm-e2e-*` address.
- **Expected:** 1: both role buttons report not pressed. 2: the page stays on
  `/signup` showing "Choose whether you're signing up as an Attendee or an
  Event Organiser." 3: the browser ends on `/dashboard/attendee`.
- **Actual:** Chromium: both buttons started `aria-pressed="false"`; submitting without a role stayed on `/signup` with the role message; after choosing Attendee the browser ended on `/dashboard/attendee`.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_sign_up.py::test_an_attendee_sign_up_lands_on_the_attendee_dashboard[chromium]`; `.env.test` stack recreated with `--build` immediately before (users container's `SUPABASE_URL` matched `.env.test`); 2026-10-26, branch `S-01/user-accounts` on `4e15f2a` + working tree
## S-49 — Registration Confirmation Notification

## TC-E2E-256 — an Attendee sees the confirmation on their dashboard after registering

- **Scenario:** Registering in the browser leaves a confirmation on the
  Attendee dashboard with the event and entry details (S-49 AC1, AC2).
- **Pre-conditions:** As TC-E2E-252, with the S-49 `notifications.sql`
  applied to the test project. A has the name "S-49 E2E Attendee".
- **Steps:**
  1. As A, open `/dashboard`.
  2. Open `/public/events/P`, click **Register**.
  3. Open `/dashboard` again.
- **Test data:** As above; emails `spm-e2e-*`.
- **Expected:** 1 shows a "Notifications" section with "No notifications
  yet." 3 shows one notification reading "Registration confirmed: {P's
  name}, {P's date and time}, venue to be confirmed. Name: S-49 E2E Attendee.
  Email: {A's email}."
- **Actual:** Chromium: the dashboard first showed "No notifications yet."; after registering it showed the confirmation with P's name, date and time, "venue to be confirmed", A's name and email.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_register_for_event.py::test_an_attendee_sees_the_confirmation_on_their_dashboard_after_registering[chromium]`; `.env.test` stack recreated with `--build` immediately before (users, events, registrations, notifications verified on the test project's `SUPABASE_URL`), 2026-10-25, branch `S-49/registration-confirmation-notification`; with the rest of `test_register_for_event.py`: 4 passed in 62 s

## S-53 — Withdraw Registration

## TC-E2E-257 — an Attendee withdraws from the event page

- **Scenario:** In a real browser: a registered Attendee withdraws from the event page after confirming, and is no longer registered (S-53 AC1, AC2). Amended by S-55 (2026-10-30): what happens to the next in line moved to TC-E2E-264, because the place is now offered, not given. The old steps 5–6 are dropped.
- **Pre-conditions:** Fresh `.env.test` stack, Chromium, the S-53 SQL applied to the test project. Through the admin client: Organiser O; confirmed event P owned by O, `expected_attendance` 1, registration open from yesterday to a week out (SGT), starting 14 days out; Attendees A, B ("S-53 E2E Attendee B") and C; A holds P's one place; B, then C, are on P's waiting list.
- **Steps:**
  1. As A, open `/public/events/P` and click **Withdraw registration**.
  2. Click **Keep my place**.
  3. Click **Withdraw registration**, then **Withdraw**.
  4. Reload; open the dashboard.
- **Expected:** 1 → "Withdraw from {P's name}? Your place will be offered to the next person on the waiting list." with **Withdraw** and **Keep my place**. 2 → the prompt closes and "You're registered for this event." is still shown. 3 → "You've withdrawn from this event.", with no "You're registered for this event.". The event is full again (the place is held for B), so **Join the waiting list** is shown. 4 → after the reload, no withdrawn message, no "You're registered" and no **Withdraw registration**. The dashboard has no row for P.
- **Actual:** Chromium: the prompt showed the S-55 wording with Withdraw and Keep my place; Keep my place closed it with A still registered; Withdraw showed "You've withdrawn from this event." and Join the waiting list; after reload no withdrawn message, no registered line, no Withdraw button, and no row for P on A's dashboard.
- **Status:** Pass
- **Evidence:** tests/e2e/test_withdraw_registration.py::test_an_attendee_withdraws_from_the_event_page[chromium]; full `tests/e2e`: 67 passed; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`); S-55 SQL applied to dev and test; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## S-93 confirmed specification — inactive Coordinator handoff in Chromium

Drafted 2026-10-25 on `S-93/reassign-active-events-before-deactivation` at
`605e1e8`. Confirmed by developer on 2026-10-25. Run through Kong and Chromium
with a freshly rebuilt `.env.test` stack; temporary Auth users and records
are removed during teardown. The test fixture marks only its throwaway
Coordinator inactive through trusted Auth metadata.

## TC-E2E-258 — Leads clear an inactive Coordinator's active-event warnings

- **Scenario:** The existing Lead dashboard identifies an inactive Coordinator and uses S-84 to clear the correct warnings.
- **Pre-conditions:** Test Auth has Leads L1/L2, inactive Coordinator A and active replacement C; A owns `Autumn Forum` in L1 scope and `Winter Fair` in L2 scope. Both events are active. The test creates and later removes all accounts and records.
- **Steps:** 1. Sign in as L1, select A and inspect both events and count. 2. Verify L2's event is read-only; reassign `Autumn Forum` to C using the existing S-84 control. 3. Confirm A's count/warning is reduced but `Winter Fair` remains flagged. 4. Sign in as L2, reassign `Winter Fair` to C, then confirm A's empty state.
- **Test data:** `Autumn Forum` pending safety check on `2026-11-18 09:00–12:00`; `Winter Fair` preparation on `2026-11-20 14:00–17:00`; reason for A's inactive state `leaving team` is not stored on the event.
- **Expected:** L1 sees A marked inactive, both summaries and count 2, but can act only on `Autumn Forum`. The first S-84 success moves that event to C, leaves `Winter Fair` with A, and reduces A's count to 1 without an L2 scope leak in ordinary oversight. L2's S-84 success clears the last warning and shows A with 0 active events; C owns both and linked data remains available through the existing event views.
- **Actual:** L1 saw both active event summaries and an inactive-owner count of two, transferred only its own event and saw the count fall to one. L2 then transferred its event, leaving A with zero active events. Cross-Lead rows remained read-only and ordinary oversight stayed scoped.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_reassign_before_deactivation.py::test_leads_clear_only_their_inactive_coordinator_assignments[chromium]`; final rebuilt `.env.test` stack, 2026-10-25 (1 passed). Full Chromium regression before the final UI selection-race fix: 51 passed.

## S-56 — View Confirmed Event Details

## TC-E2E-259 — an Attendee sees when and where their event is, and "to be confirmed" while it is re-checked

- **Scenario:** In a real browser: a registered Attendee's dashboard shows the confirmed date, time and primary venue, hides them while the event is re-checked, and shows them again once it is confirmed (S-56 AC1–AC5).
- **Pre-conditions:** Fresh `.env.test` stack, Chromium, no new SQL. Through the admin client: Organiser O; confirmed event P owned by O, starting `2026-12-04 18:00`, ending `2026-12-04 21:00`, registration open from yesterday to a week out (SGT); venues V1 and V2; confirmed bookings of V1 (submitted first) and V2 for P; Attendee A holding a place at P.
- **Steps:**
  1. As A, open the dashboard.
  2. Through the admin client, set P to `planning`; reload.
  3. Set P to `confirmed` again; reload.
- **Expected:** 1 → P's card in "Your registrations" shows "4 Dec 2026, 6:00 pm to 9:00 pm" and V1's name, and not V2's name. It shows none of P's purpose, expected attendance, organiser or coordinator. 2 → P's card is still there and reads "Details to be confirmed. The date, time and venue will show here once the event is confirmed again.", with no date and neither venue's name. 3 → the date, time and V1's name are back.
- **Actual:** Chromium: the card showed "4 Dec 2026, 6:00 pm to 9:00 pm" and Hall One, not Room Two, with no purpose, attendance, organiser or coordinator; after `planning` and a reload it read the "Details to be confirmed…" line with no date or venue; after re-confirming, the date and Hall One were back.
- **Status:** Pass
- **Evidence:** tests/e2e/test_view_confirmed_event_details.py::test_an_attendee_sees_when_and_where_and_to_be_confirmed_while_rechecked[chromium]; with the S-48/50/51/52/53 registration journeys: 9 passed (S-52 and S-53's `Confirmed` locators made exact, since a held card now also reads "Venue to be confirmed"); `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`); no new SQL; 2026-10-27, branch `S-56/view-confirmed-event-details` (on sprint4 `0d143d7`), pre-commit working tree

## S-92 — Record Equipment Storage Location

## TC-E2E-261 — Technical Support records, edits and finds an equipment location

## TC-E2E-262 — a Coordinator designates the attendee-facing primary venue

- **Pre-conditions:** The fresh `.env.test` stack has an assigned Coordinator, its Organiser and an Attendee. Their event has two confirmed venue bookings.
- **Steps:** The Coordinator opens the event, marks the second venue primary, and the Organiser confirms both venues remain visible. The Attendee opens the published event. The primary booking is then cancelled/replaced and the Coordinator returns to the event.
- **Expected:** The Coordinator and Organiser see both venues and the Primary label. The Attendee sees only the selected primary. After it is removed, the Coordinator is prompted to choose a new primary and the Attendee sees `Venue to be confirmed` until that choice is made.

- **Scenario:** The full browser journey shows the same storage location in the catalogue and live availability results.
- **Pre-conditions:** Fresh `.env.test` stack, S-92 SQL applied, Chromium, temporary Technical Support account.
- **Steps:** Add a projector at `Store B, Shelf 4`; confirm the catalogue; edit it to `AV Cage, Rack 2`; check a future availability window.
- **Expected:** Both catalogue states show the saved value; availability shows the updated location and still reports all 3 projectors available, proving the location does not reserve anything.
- **Status:** Pass (2026-10-28)
- **Evidence:** `tests/e2e/test_equipment_storage_location.py::test_storage_location_is_recorded_edited_and_shown_in_availability[chromium]`

## S-82 — View Event Change History

`test_view_event_change_history.py`. The history has its own screen,
`/events/:id/history` (developer decision 9b), with a "Back to …" link in the
header.

## TC-E2E-262 — a Coordinator's edit shows in their and a Lead's change history

- **Scenario:** In a real browser, through Kong: an edit made in the UI is recorded and both the assigned Coordinator and a Lead can read who changed what and when; nothing on the screen can change an entry (S-82 AC1, AC2, AC4).
- **Pre-conditions:** Fresh `.env.test` stack, Chromium, S-82 SQL applied. Through the admin client:
  - Organiser O, named "Ada Organiser".
  - Lead L. L assigned nothing.
  - Coordinator C, named "Alex Coordinator".
  - Event E "History Forum <6 hex>", `planning`, owned by O, assigned to C by a different Lead, `expected_attendance` 120.
- **Steps:**
  1. As C, open `/coordinator/events/E` and change Expected attendance to 150; save.
  2. Select "View change history".
  3. Sign in as L; under "Coordinator active events" choose C, then select "Change history" on E. (L did not assign E, so it is not in L's own oversight.)
  4. Open `/events/E/history` as Organiser O.
- **Expected:**
  1. The edit saves.
  2. The URL is `/events/E/history`. The newest entry reads "Edited the event" with "Expected attendance: 120 → 150", "Alex Coordinator, Event Coordinator", and today's date in Singapore time. The screen has a "Back to event" link, and no button or field that edits or deletes an entry.
  3. The same entry.
  4. The Organiser is sent back to their dashboard; no history is shown.
- **Actual:** Chromium: the Coordinator's edit saved; the history's newest entry read "Edited the event", "Expected attendance: 120 → 150", "Alex Coordinator, Event Coordinator" and today's date, with a "Back to event" link and no buttons or text fields; the Lead reached the same entry from "Coordinator active events"; the Organiser was sent back to their dashboard.
- **Status:** Pass
- **Evidence:** tests/e2e/test_view_event_change_history.py::test_coordinator_and_lead_see_an_edit_in_the_history[chromium]; full e2e suite 61 passed on a `.env.test` stack recreated with `--build` (users container verified on the test project's `SUPABASE_URL`), S-82 SQL applied; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-E2E-263 — a Safety Officer sees only the safety review's history

- **Scenario:** In a real browser, the Safety Officer reaches the history from the safety check and sees attendance changes and safety decisions, not contact edits or assignments (S-82 AC3).
- **Pre-conditions:** As TC-E2E-262, plus Safety Officer S, named "Sam Safety". E is `pending_safety_check`. Its history holds, through the internal route and the admin client:
  - `coordinator_assigned`
  - an `edited` entry changing `contact_phone`
  - an `edited` entry changing `expected_attendance` 120→150
- **Steps:**
  1. As S, open `/safety-checks/E` and request changes with reason "Fire exit blocked".
  2. Select "View change history" on the same page.
- **Expected:**
  - 2 → `/events/E/history` lists, newest first, "Requested safety changes: Fire exit blocked" by "Sam Safety, Safety Officer", then "Expected attendance: 120 → 150".
  - No contact phone change and no "Assigned …" entry is shown.
  - The back link reads "Back to safety checks" and leads to the Safety Officer's dashboard. A decided event's safety check page no longer opens, so the link can't go back to it.
- **Actual:** Chromium: after requesting changes, the history listed exactly two entries: "Requested safety changes: Fire exit blocked" by "Sam Safety, Safety Officer", then "Expected attendance: 120 → 150". No contact phone or assignment entry; back link "Back to safety checks".
- **Status:** Pass
- **Evidence:** tests/e2e/test_view_event_change_history.py::test_safety_officer_sees_only_the_safety_history[chromium]; full e2e suite 61 passed on a `.env.test` stack recreated with `--build` (users container verified on the test project's `SUPABASE_URL`), S-82 SQL applied; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

---

## S-59 — Request Event Changes (confirmed specification)

Latest S-59 execution: 2026-10-30, rebased `S-59/request-event-changes` on `origin/sprint4` d1f6d8b. Developer confirmed SQL applied in DEV and TEST. Fresh `.env.test` stack matched TEST Supabase; full Chromium regression: 66 passed.

## TC-E2E-259 — Organiser proposal persists and assigned Coordinator sees it

- **Scenario:** Chromium proves the Organiser and assigned Coordinator see one unapproved proposal through Kong after reload.
- **Pre-conditions:** Fresh `.env.test` stack with S-59 Events SQL applied, exposed and granted; temporary Organiser O, assigned Coordinator C and unrelated Coordinator D; confirmed `Autumn Forum` accepted for 2026-11-18 09:00–12:00, attendance 120, theatre layout, projector quantity 2, with an existing venue booking and Technical Support sign-off. The test removes all created rows and accounts.
- **Steps:** 1. O opens E's detail and selects Request Changes. 2. Propose attendance 150, banquet layout and projector quantity 3; inspect changed-field comparison and submit. 3. Reload O's page and verify pending status, accepted-versus-proposed values, timestamp and arrangement warning. 4. Sign in as C, open E, and verify the same pending comparison. 5. Sign in as D and attempt E's proposal URL. 6. Verify accepted event/booking/equipment/sign-off values and clean up.
- **Test data:** O/C/D distinct `spm-e2e-*` accounts; accepted 120/theatre/2, proposed 150/banquet/3.
- **Expected:** Request Changes starts with accepted values; submitting yields a pending proposal and no event mutation. O and C see accepted 120/theatre/2 beside proposed 150/banquet/3 after reload, with a server time and a statement that existing arrangements apply to accepted details only. D sees no proposal. E remains confirmed at 120, the booking and sign-off remain, and Equipment still records projector quantity 2. No S-60 Accept action appears.
- **Actual:** The Organiser submitted and reloaded a mixed proposal; the assigned Coordinator saw it, the unrelated Coordinator did not, and accepted event and linked arrangements stayed unchanged.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_request_event_changes.py::test_organiser_proposes_changes_and_coordinator_sees_them[chromium]`; both S-59 Chromium cases passed on 2026-10-30 after the frontend guard fix.

## S-55 — Notify Waitlisted Attendee of Opening

## TC-E2E-264 — a freed place is offered to the first in line, who must accept it

- **Scenario:** In a real browser: when a place frees up, the Attendee first on the waiting list is invited and finds the offer from their notification and dashboard. Declining passes it to the next in line, who is registered only once they accept (S-55 AC1, AC2).
- **Pre-conditions:** Fresh `.env.test` stack, Chromium, the S-55 SQL applied to the test project. Through the admin client: Organiser O; confirmed event P owned by O, `expected_attendance` 1, registration open from yesterday to a week out (SGT), starting 14 days out; Attendees A, B and C; A holds P's one place; B, then C, are on P's waiting list.
- **Steps:**
  1. As A, open `/public/events/P`, click **Withdraw registration**, then **Withdraw**.
  2. As B, open the dashboard.
  3. Click **View event** on the invitation.
  4. Click **Decline**, then **Keep my offer**.
  5. Click **Decline**, then **Decline** in the confirmation.
  6. As C, open the dashboard, then `/public/events/P`.
  7. Click **Accept place**.
  8. Open the dashboard.
- **Test data:** Emails `spm-e2e-*`.
- **Expected:** 1 → "You've withdrawn from this event." 2 → P's row reads "Place offered", not "Confirmed". Notifications shows "A place opened up at {P's name}, …It's held for you: accept it on the event page to register." with a **View event** link. 3 → `/public/events/P` shows "A place is being held for you. Accept it to register, or decline to pass it to the next person." with **Accept place** and **Decline**, and no "You're registered for this event.". 4 → "Decline this place? You'll leave the waiting list." with **Decline** and **Keep my offer**. Keep my offer closes it, and the held message is still shown. 5 → "You've declined the place and left the waiting list.", and **Join the waiting list** is shown (the place is now held for C). 6 → C's row reads "Place offered" and C's Notifications shows the same invitation. The event page shows the held message and **Accept place**. 7 → "You're registered for this event." 8 → P's row reads "Confirmed", and Notifications shows "Registration confirmed: {P's name}, …".
- **Actual:** Chromium: A withdrew; B's row read "Place offered" (not Confirmed) with the invitation and View event link; the link opened P's page with the held message and Accept place, no registered line; Keep my offer kept the offer; Decline showed the declined message and Join the waiting list; C's row read "Place offered" with the invitation; Accept place showed "You're registered for this event."; C's dashboard read Confirmed with "Registration confirmed: {P}, …".
- **Status:** Pass
- **Evidence:** tests/e2e/test_waiting_list_offer.py::test_a_freed_place_is_offered_to_the_first_in_line_who_must_accept_it[chromium]; full `tests/e2e`: 67 passed; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`); S-55 SQL applied to dev and test; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## S-57 — View Event Registration List (specification)

Drafted 2026-10-30 on `S-57/view-event-registration-list`. Confirmed by the
developer 2026-10-30. Only what a browser can prove: the **Refresh list** button
re-reads without a page load, and the Coordinator's page shows the list and
agrees with the service about who may see it. Access rules, ordering and
withdrawals are covered by TC-EVENTREGISTRATIONS-062 to -065 and -109.

## TC-E2E-265 — the Organiser refreshes the list after withdrawals

- **Scenario:** In a real browser, with the event page left open, the Organiser sees withdrawals after clicking **Refresh list**, and is told when no one is left (S-57 AC2–AC5).
- **Pre-conditions:** Fresh `.env.test` stack, Chromium. Through the admin client: Organiser O; confirmed event P owned by O, `expected_attendance` 5, registration open yesterday to tomorrow (SGT), starting ten days out; Attendees A ("S-57 E2E Attendee A") and B ("S-57 E2E Attendee B"), both holding a place at P.
- **Steps:**
  1. As O, open `/events/P`.
  2. Without leaving the page, A withdraws through the API (`DELETE /api/event-registrations/events/P/registration` with A's session).
  3. Click **Refresh list**.
  4. B withdraws the same way; click **Refresh list**.
- **Test data:** Emails `spm-e2e-*`; names as above.
- **Expected:** 1 → "Registered attendees" shows "2 attendees registered" with A's and B's names and emails. 3 → "1 attendee registered", B listed, A's name not on the page; the URL did not change and no navigation occurred. 4 → "No one is currently registered for this event." and no attendee rows.
- **Actual:** Chromium: "2 attendees registered" with both names and emails; after A withdrew in a separate session and Refresh list, "1 attendee registered" with B only; after B withdrew and Refresh list, "No one is currently registered for this event."; same URL, and a page-load marker set before the first refresh survived both.
- **Status:** Pass
- **Evidence:** tests/e2e/test_view_registration_list.py::test_the_organiser_refreshes_the_list_after_withdrawals[chromium]; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`); no new SQL; 2026-10-30, branch `S-57/view-event-registration-list` (on sprint4 `44701d3`), pre-commit working tree; with `test_register_for_event.py`, `test_cap_registration.py` and `test_withdraw_registration.py`: 9 passed

## TC-E2E-266 — the assigned Coordinator sees the registration list

- **Scenario:** The Coordinator assigned to the event sees who is registered on their event page, without the Organiser's close/reopen control (S-57 AC1, AC2).
- **Pre-conditions:** As TC-E2E-265, plus Coordinator C as P's `assigned_coordinator_id`; only A holds a place.
- **Steps:**
  1. As C, open `/coordinator/events/P`.
- **Test data:** Emails `spm-e2e-*`.
- **Expected:** A "Registered attendees" section shows "1 attendee registered" with A's name and email, a **Refresh list** button, and no **Close registration** button.
- **Actual:** Chromium: Registered attendees showed "1 attendee registered", A's name and email and Refresh list; no Close registration button on the page.
- **Status:** Pass
- **Evidence:** tests/e2e/test_view_registration_list.py::test_the_assigned_coordinator_sees_the_registration_list[chromium]; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`); no new SQL; 2026-10-30, branch `S-57/view-event-registration-list` (on sprint4 `44701d3`), pre-commit working tree; with `test_register_for_event.py`, `test_cap_registration.py` and `test_withdraw_registration.py`: 9 passed

## S-71 — Notify Coordinator — Availability Change

## TC-E2E-267 — Technical Support makes equipment unavailable and the Coordinator is told

- **Scenario:** The full browser journey lets a Coordinator react before the event when catalogue availability changes.
- **Pre-conditions:** Fresh `.env.test` stack with S-71 SQL, Chromium, Technical Support T, Coordinator C, confirmed event E assigned to C, and available equipment P required by E.
- **Steps:** As T, edit P to Unavailable. Sign in as C and open Notifications.
- **Expected:** T sees the saved catalogue status. C sees one notification naming E and P and telling them to arrange replacement equipment before the event.
- **Actual:** Chromium showed the saved Unavailable status and one Coordinator notification naming the event and equipment and directing replacement before the event.
- **Status:** Pass
- **Evidence:** `tests/e2e/test_equipment_availability_notification.py::test_support_makes_equipment_unavailable_and_the_coordinator_is_told[chromium]`;
  fresh `.env.test` stack; 2026-10-31, branch
  `S-71/notify-coordinator-availability-change` on Sprint 4 `95f29c6`: 1 passed.
