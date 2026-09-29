# Test cases — end-to-end journeys

Covers `test_sign_up.py`, `test_session.py`, `test_role_access.py`,
`test_add_venue.py`, `test_respond_to_return.py`, `test_rejected_tab.py`,
`test_request_venue.py`, `test_capacity_warning.py`, `test_update_venue.py`,
`test_record_equipment.py`, `test_update_equipment.py`,
`test_retire_equipment.py`, `test_assign_technical_support.py`,
`test_prevent_overlapping_confirmation.py`, `test_filter_venues.py` and
`test_venue_availability.py`.
A real browser drives the built frontend through Kong,
against the services and a real (test) Supabase project. These are the only
tests that see the gateway's routing, the SPA fallback and a session cookie
surviving a page load.

| | |
| --- | --- |
| Suite | `pytest tests/e2e` |
| Last run | 2026-09-29, branch `S-38/prevent-overlapping-booking-confirmation`, pre-commit working tree |
| Environment | `.env.test` test Supabase project with all repository SQL applied, granted and exposed; full stack recreated immediately before; Chromium; email confirmation off |
| Result | 17 passed |

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
  Coordinator, organiser, planning event, and no requirement for the item.
- **Steps:** Technical Support adds `spm-e2e Wireless Microphone <hex>` with
  total `12`; Coordinator opens the planning event, records quantity `6`, and
  sees it after reload; sign out and back in as Technical Support.
- **Expected:** The new item needs no frontend code change, the Coordinator can
  record it only on the planning event, and Technical Support's requirement
  view shows the event id, item name, and quantity `6`.
- **Actual:** Technical Support added the item, the assigned Coordinator saved
  quantity 6 on the planning event, and Technical Support saw the item,
  quantity and event id after a fresh sign-in.
- **Status:** Pass
- **Evidence:** `test_record_equipment.py::test_coordinator_records_required_equipment_visible_to_technical_support`

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
- **Test data:** Studio B, 2026-11-12 09:00-12:00; alternative='Try Studio C at 14:00'; server-conflict fixture already decided by another staff.
- **Expected:** Saved Confirmed/Rejected outcome and alternative visible after reopen; no automatic booking of alternative. Failure/conflict gives safe feedback, not success. Nonstaff sees no decision controls. No reassignment exception is added; the existing assignment rule remains in force. Manual supplement: two staff tabs, keyboard operation, narrow screen and reason-plus-alternative display.
- **Actual:** Venue Staff approved one pending request without a reason and rejected another with an alternative; blank rejection was blocked. The pending list refreshed after each decision. After signing in as the requesting Coordinator and reopening the event, both saved outcomes and the alternative were visible and persisted after reload.
- **Status:** Pass
- **Evidence:** `test_decide_booking.py::test_staff_decisions_appear_to_requesting_coordinator[chromium]`; local Chromium execution against the freshly recreated `.env.test` stack.
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

> **Superseded by S-30.** Holds are exclusive now, so the second overlapping
> request is refused when it is sent, and there is nothing left to confirm.
> TC-E2E-221 covers the refusal. The last result is kept below as a record.

- **Scenario:** Venue Staff cannot confirm an overlapping request after the
  venue slot has been confirmed for another event (AC1, AC2, AC3).
- **Pre-conditions:** Fresh `.env.test` stack with S-38 SQL applied, granted
  and exposed; Chromium; one Venue Staff account; two planning events have
  pending requests for Studio B on the same date with overlapping times.
- **Steps:** Sign in as Venue Staff; confirm the first request; attempt to
  confirm the second request; reload the pending list and both Coordinators'
  event views.
- **Test data:** Event A requests Studio B on `2026-11-12`, `09:00`–`12:00`;
  Event B requests Studio B on `2026-11-12`, `11:00`–`13:00`.
- **Expected:** Event A becomes Confirmed and remains confirmed after reload.
  Event B is not confirmed; the page identifies Studio B, `12 Nov 2026`, and
  `09:00`–`12:00` as the conflict. Event B remains Pending after reload, and
  its Coordinator never sees a confirmed booking for that unavailable slot.
- **Actual:** The first request became Confirmed; the overlapping approval stayed Pending and displayed the venue/date/time conflict. Reload preserved both outcomes, and the two Coordinator event pages showed Confirmed and Pending respectively.
- **Status:** Pass
- **Evidence:** `test_prevent_overlapping_confirmation.py::test_confirmed_venue_time_becomes_unavailable_to_another_event[chromium]`; full Chromium suite: 17 passed.

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
Confirmed by the developer on 2026-09-30. Not yet executed.
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
- **Actual:** —
- **Status:** Blocked — The S-30 section of `backend/sql/bookings.sql` has not been applied to the test project yet, so this case cannot run.
- **Evidence:** `tests/e2e/test_venue_availability.py::test_a_coordinator_sees_booked_held_unavailable_and_past_days_apart` (not run)

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
- **Actual:** —
- **Status:** Blocked — The S-30 section of `backend/sql/bookings.sql` has not been applied to the test project yet, so this case cannot run.
- **Evidence:** `tests/e2e/test_venue_availability.py::test_a_new_hold_a_new_block_and_a_removed_block_all_show_up` (not run)
