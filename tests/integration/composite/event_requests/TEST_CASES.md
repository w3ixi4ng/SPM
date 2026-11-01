# Test cases — event_requests service (integration)

Covers `tests/integration/composite/event_requests/test_app.py` and `test_s93.py`: the real
composite service in Docker, calling the real `events`, `users`, and
`notifications` services,
against the test Supabase project. Proves the three services agree on shapes
the unit tests cannot check, because their fakes agree with everything.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/composite/event_requests` |
| Last run | 2026-10-25, uncommitted `S-93/reassign-active-events-before-deactivation` working tree based on `605e1e8` |
| Environment | `.env.test` test Supabase project; schemas applied, granted, and exposed; full stack recreated immediately before the run |
| Result | Event-request integration cases passed within the full integration run: 77 passed, 5 skipped. |

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
- **Actual:** `409` with the exact expected detail; the organiser's event list
  contained no event for the refused request. The blocking helper rechecked
  the shared coordinator pool until no newly created CI account remained
  unblocked.
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
  moves the assignment when the current coordinator no longer fits.
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
- **Expected:** Step 2 returns `201` assigned to A. Step 3 returns `200`,
  `start_time` updated to `13:00:00`, and `assigned_coordinator_id` changed
  from conflicted A to an existing eligible coordinator. In an isolated pool
  that is B; another free coordinator added to the shared project after the
  fixture's blocking snapshot is also a valid assignment.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_editing_the_datetime_reassigns_when_the_current_coordinator_now_conflicts`

## TC-EVENTREQUESTS-105 — a returned request is amended, resubmitted, and back with its coordinator

- **Scenario:** Against the real database, this proves S-13 AC2 to AC5 in one
  round trip: the amendment is saved, the same record is resubmitted, and it
  is back in the coordinator's queue.
- **Pre-conditions:** As TC-EVENTREQUESTS-101. The organiser has a submitted
  request assigned to coordinator A. The admin client then sets it to
  `status=returned`, `decision=returned`, with a reason, a comment and
  `decided_at`. Every other coordinator is blocked at the window, so A is the
  only candidate. A new fixture signs in as coordinator A.
- **Steps:** 1. As the organiser, count `GET /events`. 2. `POST
  /event-requests/{id}/submit` with the payload amended. 3. As the organiser,
  `GET /events/{id}` and count `GET /events` again. 4. As coordinator A,
  `GET /events/assigned`.
- **Test data:** Window `2026-11-12 09:00`–`11:00`; `expected_attendance`
  `120` → `80`; reason `"Expected attendance exceeds the venue's capacity"`;
  comment `"Reduce attendance to 80 or choose a larger venue"`.
- **Expected:** Step 2 returns `200` with the original `id`. Step 3 shows
  `status=submitted`, `expected_attendance=80`, `assigned_coordinator_id=A`,
  `decision`/`decision_reason`/`decision_comment`/`decided_at` all `null`, and
  the same count as step 1. Step 4 lists the event once, with
  `status=submitted` and `expected_attendance=80`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_returned_request_is_amended_resubmitted_and_back_with_its_coordinator`

## TC-EVENTREQUESTS-106 — a failed resubmission leaves the returned request exactly as it was

- **Scenario:** Against the real database, this proves S-13 AC6: a refused
  resubmission changes no stored field.
- **Pre-conditions:** As TC-EVENTREQUESTS-105 up to the return. Then
  coordinator A and every other coordinator get a covering booking at the
  amended window, so nobody is free there.
- **Steps:** 1. As the organiser, `GET /events/{id}` and keep the body. 2.
  `POST /event-requests/{id}/submit` moving the window to the blocked one and
  amending attendance. 3. `GET /events/{id}` again.
- **Test data:** Original window `2026-11-12 09:00`–`11:00`, attendance `120`;
  amended window `2026-11-12 13:00`–`15:00`, attendance `80`.
- **Expected:** Step 2 returns `409` with
  `"No event coordinator is available for the requested date and time"`.
  Step 3 equals step 1 field for field, including `updated_at`: still
  `returned`, `start_time=09:00:00`, attendance `120`, same coordinator, and
  the same reason, comment and `decided_at`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_failed_resubmission_leaves_the_returned_request_exactly_as_it_was`

## TC-EVENTREQUESTS-107 — support is assigned, persisted, and visible through the gateway

- **Scenario:** Prove S-43 across Kong, Auth trusted roles, the users and events
  services, the composite, and the real events schema.
- **Pre-conditions:** Shared test stack; a planning event assigned to the
  signed-in Coordinator; eligible Technical Support A and B; A has more live
  assignments, neither overlaps the target window.
- **Steps:** Through Kong, read the initial support state; POST the explicit
  assignment action with details; GET the state again; read the event directly
  from the events service and database; repeat the POST; clean up all rows and
  temporary users.
- **Test data:** Details `Wireless microphone setup and sound check`; target
  `2026-11-13 09:00`–`12:00`.
- **Expected:** Initial state is not required and unassigned. The action chooses
  least-busy B without a manually supplied id, persists required/details/B,
  assignment timestamp, and returns `assignment_state="assigned"` with B's
  name and email. GET and direct storage agree. A repeat with changed notes
  updates the details but preserves B and the assignment timestamp.
- **Actual:** The least-busy eligible staff member was assigned through Kong;
  GET, the events service, and direct storage agreed. Updating the notes kept
  the staff id and parsed assignment instant unchanged.
- **Status:** Pass
- **Evidence:** `test_app.py::test_support_assignment_is_persisted_visible_and_idempotent`

---

## S-83 — Lead assignment journey

Story: S-83 Assign Event Requests from Unassigned Queue. Acceptance criteria
and notification recipients confirmed by the developer on 2026-10-08.

TC-EVENTREQUESTS-101 through TC-EVENTREQUESTS-104 specify the superseded
automatic-assignment rule from S-12. They are retained as historical IDs but
must no longer execute after S-83 replaces that workflow.

## TC-EVENTREQUESTS-108 — submission, Lead assignment, and both notifications cross real boundaries

- **Scenario:** Prove the complete S-83 workflow across Kong, trusted Auth
  roles, users, events, notifications, the composite, and real Supabase rows.
- **Pre-conditions:** Fresh `.env.test` stack; `users`, `events`, and
  `notifications` schemas applied, granted, and exposed; temporary organiser,
  Lead, coordinator A, and coordinator B exist. Coordinator A has an
  overlapping event to prove conflicts do not block manual choice.
- **Steps:** 1. Sign in as organiser and submit `Autumn Forum` through Kong.
  2. Verify it has no coordinator. 3. Sign in as Lead and read the queue and
  coordinator choices. 4. Assign conflicting coordinator A. 5. Read the queue
  again. 6. Inspect the two persisted recipient rows. 7. Repeat the same
  assignment with both rows present. 8. Reproduce the split-service failure
  state on another event by committing only the atomic assignment, then retry
  through the composite. 9. Delete one recipient row and retry again.
  10. Attempt assignment to B. 11. Inspect and clean up real rows/users.
- **Test data:** `Autumn Forum`, `2026-11-18 09:00`–`12:00`, attendance `120`;
  A's overlapping event `10:00`–`11:00`.
- **Expected:** Submission returns `201`, `submitted`, coordinator null and
  appears in the Lead queue with basic event and organiser information. A is
  offered and can be assigned despite overlap. The event leaves the queue and
  the queue no longer contains it. A and the organiser each retain one
  in-app assignment notification. Every
  retry preserves A, creates any missing notification, and ends with exactly
  one coordinator row and one organiser row; no duplicate is created when
  both already exist. Changing the target to B returns `409`. Cleanup succeeds
  and the case can run twice.
- **Actual:** The Lead assigned coordinator A despite the overlapping event;
  the event left the queue and both notifications persisted. Same-target
  retries kept the assignment and exactly two notification rows, recreated
  either missing row, and a different-target retry returned `409`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_lead_assignment_persists_notifications_and_repairs_missing_rows`;
  targeted local run against the freshly rebuilt `.env.test` stack: 1 passed.

## TC-EVENTREQUESTS-109 — versioned reassignment transfers access and repairs three notifications

- **Scenario:** Prove S-84 across Kong, Auth, users, events, notifications,
  and real Supabase rows.
- **Pre-conditions:** Fresh `.env.test` stack with the S-84 events and
  notifications SQL applied; organiser, Lead, coordinator A, and coordinator
  B. A owns an active event and B has an overlapping event.
- **Steps:** List active assignments; reassign A/v0 to B; verify both
  Coordinator queues and three notification rows; repeat; delete each row and
  retry; make a newer transition and retry the stale original request.
- **Expected:** Conflict does not block B. Access moves A→B. Exact retries
  preserve B and repair only missing notifications, always ending at exactly
  three. The stale request returns `409` and cannot revert the newer owner.
- **Actual:** The Lead reassigned the event to the overlapping Coordinator;
  access moved A→B and exactly three version-1 notifications persisted.
  Repeating created no duplicates, deleting the organiser row followed by a
  retry repaired it, and the stale A/v0→B request returned `409` after the
  newer B/v1→A transition without reverting version 2.
- **Status:** Pass
- **Evidence:** `test_app.py::test_reassignment_transfers_access_and_repairs_notifications`;
  local run against a freshly rebuilt `.env.test` stack on 2026-10-09: 1 passed.

## TC-EVENTREQUESTS-110 — oversight groups real assignments and follows reassignment

- **Scenario:** Prove the S-85 overview contract across Kong, Auth, Users,
  Events, and the real test database while preserving S-84 reassignment.
- **Pre-conditions:** Fresh `.env.test` stack; organiser, Lead, coordinators A
  and B; one submitted event assigned to A. B has no active assignment.
- **Steps:** Read overview as Lead; verify both Coordinator groups and counts;
  reassign A→B through S-84; read overview again; try the overview as an
  organiser.
- **Test data:** `Autumn Forum`, submitted, `2026-11-18 09:00`–`12:00`.
- **Expected:** The first overview places the enriched event under A with
  counts A=1/B=0. The second places it under B with A=0/B=1 and unchanged
  event summary fields. The organiser receives `403`; no S-85 notification or
  persistence state is created.
- **Actual:** The first real overview returned A=1/B=0 with the enriched
  submitted event. After S-84 moved it, the next returned A=0/B=1 with version
  1; both overview reads left notification counts unchanged, and the Organiser
  received `403`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_overview_groups_and_tracks_reassignment`

## TC-EVENTREQUESTS-111 — real Auth eligibility survives missing profiles and invalid owners

- **Scenario:** The real S-85 endpoint uses complete trusted Auth eligibility across Users, Events, Kong, and the test Supabase project.
- **Pre-conditions:** A freshly recreated `.env.test` stack; disposable test Auth Coordinators A/B, with A profiled and B profile-less; a disposable non-Coordinator N; active events for A and N; and a deleted test Auth owner D with an existing event. B has no active event initially. Fixtures must clean up every row and account they create.
- **Steps:** Read the Lead overview through Kong, inspect groups and `invalid_assignments`, then read S-83 candidates and attempt S-84 reassignment to B and N.
- **Test data:** A has one active event; B has zero before reassignment; N and D each own one active event; all fixture emails are unique per run.
- **Expected:** A and B are the only fixture Coordinator groups; B appears with its Auth email and count zero before reassignment. N/D events appear only as integrity diagnostics, not groups. B is an eligible S-83/S-84 candidate and N is rejected; a successful A→B reassignment yields updated counts without changing N/D ownership. Fixture cleanup leaves the project as it was.
- **Actual:** The real Auth pool included profile-less B in the overview and candidate list; wrong-role N and deleted D were diagnostics only. N was refused as a target, A→B succeeded, and the invalid assignments remained unchanged. The integration fixture event names were absent after cleanup.
- **Status:** Pass
- **Evidence:** `test_app.py::test_overview_uses_real_auth_pool_for_profileless_and_invalid_owners`; `.env.test` stack recreated and URL checked, 2026-10-18.

## S-61 — review and approve cancellation request

Story: S-61 Review and Approve Cancellation Request.
Confirmed by the developer on 2026-10-11.
The S-61 SQL was applied to dev and test on 2026-10-11. The criteria mapping and agreed decisions are in the S-61
section of `tests/unit/atomic/events/TEST_CASES.md`.

### TC-EVENTREQUESTS-112 — approving through Kong cancels the event and frees its venue and equipment

- **Scenario:** Real services agree that a cancelled event holds nothing, and
  a decline keeps everything (S-61 AC1–AC3).
- **Pre-conditions:** A fresh `.env.test` stack; the S-61 SQL applied.
  - Coordinator K, Organiser O, Venue Staff S, and a venue V open `thu`
    08:00–20:00.
  - An equipment item Q with quantity 1.
  - Event E1: `planning`, assigned to K, owned by O, `2026-11-12`
    09:00–18:00. It has a pending cancellation request, a `confirmed` booking
    of V 09:00–12:00, a `held` booking of V 13:00–15:00, and a requirement
    for 1 × Q.
  - Event E2: `planning`, assigned to K, with a pending request.
- **Steps:**
  1. K `POST /api/event-requests/E1/cancellation-decision` `{"decision": "approved"}`.
  2. S `GET /api/venue-bookings/availability?venue_id=V&from=2026-11-12&to=2026-11-12`.
  3. K checks equipment availability for Q on `2026-11-12` 09:00–18:00.
  4. K declines E2 with reason "Move the date instead".
  5. O `POST /api/events/E2/cancellation-request` `{"reason": "Still need to cancel"}`.
- **Expected:**
  1. `200`, `status` `cancelled`, `released_bookings` 2. In
     `events.events`, E1 is `cancelled` with decision `approved` by K and a
     decision time. `bookings.bookings` has no rows for E1.
  2. 12 Nov shows nothing booked or held at V.
  3. Q shows 1 available.
  4. `200`. E2 is still `planning`, with decision `declined` and the reason.
  5. `200`. E2's decision fields are cleared and the new reason is stored.
  Cleanup deletes every row created.
- **Actual:** Through Kong: approving E1 returned `200` `cancelled` with `released_bookings` 2; E1 stored `cancelled`, approved by K with a time; no booking rows left for E1; the calendar for 12 Nov had no entries; the projector showed 0 reserved, 1 available. Declining E2 kept it `planning` with the reason; the Organiser's new request returned `200` and cleared all four decision fields.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_cancellation_decision.py::test_approving_through_kong_cancels_the_event_and_frees_its_venue_and_equipment`; `.env.test` stack recreated immediately before (events and bookings containers verified on the test project's `SUPABASE_URL`), 2026-10-11, branch `S-61/review-and-approve-cancellation-request`; S-61 SQL applied to dev and test. `pytest tests/integration/composite/event_requests tests/integration/atomic/events tests/integration/atomic/bookings`: 21 passed, 5 skipped (pre-existing S-83 supersessions). Re-verified 2026-10-21 after merging sprint3 (S-17, S-18, S-24, S-78, S-80, S-87) into this branch and re-applying the S-61 `events_decision_matches_status` rule (with S-87's `pending_safety_check`) to dev and test: the seeded hold now sets `hold_expires_at` (S-24); `pytest tests/integration/composite/event_requests tests/integration/atomic/events tests/integration/atomic/bookings`: 32 passed, 5 skipped, 1 failed (`test_decision.py`, an unrelated one-off 401 from session verification; 4 passed twice on rerun).

## S-88 confirmed specification — real boundary checks

Confirmed by the developer on 2026-10-25. Latest execution: S-88 branch,
uncommitted, fresh `.env.test` stack. The developer confirmed that the updated
`backend/sql/events.sql` was applied to **both** dev and test Supabase projects
and `events` was exposed and granted in each. The test recreated the `.env.test`
stack and deleted its created rows.

## TC-EVENTREQUESTS-113 — persisted request and scoped review

- **Scenario:** A submitted request survives refresh and reaches only its assigning Lead.
- **Pre-conditions:** Fresh test stack and schema; two Lead accounts, two Coordinator accounts, and an event assigned by Lead A to Coordinator A.
- **Steps:** Coordinator A submits a reason; reread their history in a new HTTP request; read Lead A and Lead B queues; reread the event.
- **Test data:** Reason `Cannot cover the November event`; Lead A and Lead B have distinct user IDs.
- **Expected:** `201` request remains `pending` on refresh; Lead A sees requester, event and reason; Lead B sees no row; event remains owned by Coordinator A.
- **Actual:** The request persisted across HTTP reads. The assigning Lead saw it, the unrelated Lead did not, and event ownership remained with the requester.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s88.py::test_request_survives_refresh_is_scoped_and_actions_after_s84`; 2026-10-25.

## TC-EVENTREQUESTS-114 — existing S-84 actions request and preserves history

- **Scenario:** The Lead's existing reassignment changes ownership and reports the result to the requester.
- **Pre-conditions:** TC-EVENTREQUESTS-113 setup with pending request and valid Coordinator B.
- **Steps:** Lead A calls S-84; fetch event and request from fresh HTTP requests as former Coordinator A; verify older actioned rows remain after a later request cycle.
- **Test data:** Coordinator B, expected Coordinator A and captured assignment version.
- **Expected:** S-84 succeeds, event owner is B, request is `actioned` with timestamp, A can still read it, and audit rows remain. A stale retry cannot transfer ownership again.
- **Actual:** S-84 changed ownership and actioned the matching request. The former Coordinator could still read its history, while the stale retry was rejected and did not alter ownership.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s88.py::test_request_survives_refresh_is_scoped_and_actions_after_s84`; 2026-10-25.
## S-93 confirmed specification — real Users/Events boundary

Drafted 2026-10-25 on `S-93/reassign-active-events-before-deactivation` at
`605e1e8`. Confirmed by developer on 2026-10-25. Run only after recreating the
stack from `.env.test`; use throwaway Supabase Auth users and remove every
created event, request and user. Existing `users` and `events` schemas must be
applied, exposed and granted in the test project. No S-93 SQL is proposed if
trusted Auth metadata holds Coordinator availability.

## TC-EVENTREQUESTS-115 — real status excludes inactive assignment targets

- **Scenario:** A persisted inactive flag is honoured across Users, Events, composite HTTP and Kong.
- **Pre-conditions:** Fresh `.env.test` stack; temporary Lead L1, active Coordinator C and Coordinator A, plus an unassigned submitted event, an L1 active event owned by A, and an L1 active event owned by C. Test admin marks A inactive in Auth metadata and cleans up afterward.
- **Steps:** 1. Read A's status in a fresh Users HTTP request. 2. Read S-93 inventory and S-83/S-84 candidate lists through Kong. 3. POST direct S-83 assignment of the unassigned event to A and S-84 reassignment of C's event to A through Kong. 4. Call both atomic Events mutation ports with a valid Lead cookie but missing and forged service credentials. 5. Read all three events and clean up.
- **Test data:** Temporary `spm-test-s93-<hex>@example.com` accounts; `Autumn Forum` submitted, `Winter Fair` planning owned by A at version 2, `Spring Fair` planning owned by C at version 1.
- **Expected:** A remains a login-capable Coordinator but is marked inactive and flagged as owner of `Winter Fair`; A is absent from new-target lists. Both direct composite assignment attempts return `422`; atomic-port attempts return `403` before storage access. None of the three event owners/versions or event-linked data changes. C remains an eligible replacement.
- **Actual:** Real Auth metadata excluded inactive targets through Kong; missing and forged direct atomic credentials returned 403; valid active assignment still worked.
- **Status:** Pass
- **Evidence:** test_s93.py::test_inactive_target_is_rejected_but_existing_work_can_be_transferred

## TC-EVENTREQUESTS-116 — S-84 transfer preserves linked records and scope

- **Scenario:** Real S-84 transfers one inactive owner's event and preserves every event-linked record.
- **Pre-conditions:** Fresh `.env.test` stack; L1/L2, inactive A, active C; two active A events, one in each Lead scope. The L1 event has a venue booking, equipment requirement, technical assignment, comment/history and pending S-88 request. All rows are cleaned up.
- **Steps:** 1. Snapshot linked records and both Leads' views. 2. Try L2 action on L1's event and a stale version as L1. 3. Reassign that event A→C as L1 through S-84. 4. Read Users/Events and linked services again; read A's S-88 history.
- **Test data:** `Autumn Forum` planning, expected owner A/version 2; `Winter Fair` preparation under L2; S-88 reason `Leaving the team`.
- **Expected:** Cross-Lead action is scoped `404` and stale action `409`, leaving owner and warning intact. Successful L1 action changes only `Autumn Forum` owner/version, removes its inactive-owner warning and decrements A's count by one; `Winter Fair` stays warned. Venue, equipment, technical, comment and history rows keep their event IDs/content, and A's S-88 request becomes actioned and remains readable by A.
- **Actual:** The real S-84 transfer incremented the version, actioned the pending S-88 request, cleared the inactive-owner count, and preserved linked booking, equipment, technical and edit-history data.
- **Status:** Pass
- **Evidence:** test_s93.py::test_inactive_target_is_rejected_but_existing_work_can_be_transferred; tests/e2e/test_reassign_before_deactivation.py::test_leads_clear_only_their_inactive_coordinator_assignments[chromium]

---

## S-82 — View Event Change History

## TC-EVENTREQUESTS-123 — real actions show up in the Coordinator's and Lead's history

- **Scenario:** Actions taken through the real services are recorded and read back with names, through Kong (S-82 AC1, AC2).
- **Pre-conditions:** Fresh `.env.test` stack; S-82 SQL applied and `events` exposed. Fixtures: Organiser O, Lead L, Coordinators C and C2, all with `spm-event-requests-*` emails. (Since S-83 a Lead assigns explicitly, so no other Coordinator has to be blocked.)
- **Steps:**
  1. As O, `POST /api/event-requests` with a valid submitted body.
  2. As L, `POST /api/event-requests/E/assignment` assigning C.
  3. As C, `POST /api/events/E/decision` with `{"decision": "approved"}`.
  4. As C, `GET /api/event-requests/E/history`.
  5. As L, the same.
  6. As C2, the same.
  7. Delete everything created.
- **Test data:** Event name `S-82 History <6 hex>`, 2026-11-18 09:00–12:00, 40 attendees.
- **Expected:**
  - 4 → `200` with three entries, newest first: `request_approved` by C, `coordinator_assigned` by L, and `submitted` by O.
  - Each actor's `name` is the name stored in `users.users`.
  - `people` names C.
  - 5 → the same three entries.
  - 6 → `404`.
- **Actual:** Through Kong: three entries newest first (`request_approved` by C, `coordinator_assigned` by L, `submitted` by O) with their stored names; the Lead saw the same entries; C2 got `404`.
- **Status:** Pass
- **Evidence:** tests/integration/composite/event_requests/test_s82.py::test_real_actions_show_up_in_the_history; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`), S-82 SQL applied to both projects; full integration run 96 passed, 5 skipped; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## S-59 — Request Event Changes (confirmed specification)

Latest S-59 execution: 2026-10-30, rebased `S-59/request-event-changes` on `origin/sprint4` d1f6d8b. Developer confirmed SQL applied in DEV and TEST. Fresh `.env.test` stack matched TEST Supabase; full integration suite: 104 passed, 5 skipped.

## TC-EVENTREQUESTS-201 — proposal crosses Users, Events and Equipment without changing arrangements

- **Scenario:** The public composite stores a mixed event/equipment proposal through real service boundaries.
- **Pre-conditions:** Fresh `.env.test` stack with S-59 Events SQL applied, exposed and granted; O, assigned C and unrelated D; confirmed E with accepted attendance 120, projector requirement quantity 2, venue booking, Technical Support sign-off and one attendee. All rows/accounts are temporary and cleaned up.
- **Steps:** 1. As O, GET current form data and POST attendance 150 plus projector quantity 3 through Kong. 2. Read proposal as O and C and attempt as D. 3. Read E and each linked service record. 4. Reload O/C views. 5. Clean up.
- **Test data:** E `Autumn Forum`; attendance 120→150; projector quantity 2→3; temporary `spm-test-*` accounts.
- **Expected:** POST `201`; O and C see one pending comparison with trusted O ID and server timestamp after reload, D gets `404`. E stays confirmed at 120; Equipment still holds quantity 2; booking, sign-off and attendee remain. The proposal explicitly says these accepted arrangements have not been reviewed for the proposed details; cleanup leaves no rows.
- **Actual:** A mixed attendance, layout and equipment proposal was visible to its owner and assigned Coordinator, hidden from an unrelated Coordinator, and left the accepted event, booking, equipment requirement, Technical Support sign-off and attendee registration unchanged.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s59.py::test_mixed_proposal_preserves_accepted_arrangements`; full integration suite 104 passed, 5 skipped on 2026-10-30.

## TC-EVENTREQUESTS-202 — failed, duplicate and stale submissions remain safe

- **Scenario:** Real HTTP and database boundaries enforce one pending request and leave accepted state intact.
- **Pre-conditions:** Fresh `.env.test` stack and S-59 SQL as TC-EVENTREQUESTS-201; O owns submitted E with attendance 120; C is assigned.
- **Steps:** 1. Send an invalid empty proposal. 2. Send two attendance proposals concurrently. 3. Retry the losing payload and an old baseline after an accepted S-18 Coordinator edit. 4. Read E and request storage. 5. Clean up.
- **Test data:** Empty `{}`; attendance proposals 150/180; intervening accepted attendance 130.
- **Expected:** Empty request `422`; exactly one concurrent proposal `201`, the other `409`; duplicate and stale attempts `409`. The winning request is unchanged, no partial row remains, and E's accepted attendance reflects only the separate S-18 edit (130), never the proposals.
- **Actual:** Invalid submission was rejected; concurrent submissions produced one pending request; an atomic Events submission with an old event baseline returned 409 after an accepted edit, leaving the accepted value and request rows unchanged.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s59.py::test_two_concurrent_submissions_leave_one_pending_row`; `tests/integration/atomic/events/test_s59.py::test_stale_event_baseline_cannot_be_stored_as_a_change_request`; 2026-10-30.

## S-69 specification — Notify Attendee — Event Cancelled

Drafted 2026-10-30 on `S-69/notify-attendee-event-cancelled` (from
`origin/sprint4`). Confirmed by the developer 2026-10-30. Needs the S-69
blocks of `backend/sql/notifications.sql` (the `event_cancelled` kind) and
`backend/sql/events.sql` (a safety-checked event may be cancelled) applied to
the test project. The second was found by this case's first run: approving
the cancellation of a confirmed event failed with `23514` on
`events_safety_state_consistent`, so no registered Attendee could ever be
notified.

## TC-EVENTREQUESTS-203 — approving a cancellation notifies registered and waiting Attendees once

- **Scenario:** Through Kong against the test project: when the Coordinator approves a cancellation, every Attendee holding a place or on the waiting list finds one notification naming the event as cancelled, no one else does, and approving again adds none (S-69 AC1–AC3). Also proves the real `notifications.notifications` constraint allows the `event_cancelled` kind, and that the composite reaches the registrations service inside the compose network.
- **Pre-conditions:** Fresh `.env.test` stack, started immediately before. Through the admin client: Organiser O; Coordinator C; confirmed event P owned by O, assigned to C, named "spm-test S-69 <hex>", starting ten days out 18:00–21:00, `expected_attendance` 1, registration open yesterday to tomorrow (SGT), with a pending cancellation request from O (reason "Speaker unavailable"); Attendees A, W and X.
- **Steps:**
  1. As A, `POST /api/event-registrations/events/P/registration`.
  2. As W, `POST /api/event-registrations/events/P/waiting-list`.
  3. As C, `POST /api/event-requests/P/cancellation-decision` `{"decision": "approved"}`.
  4. As A, W and X in turn, `GET /api/notifications`.
  5. As C, approve again; as A, `GET /api/notifications`.
  6. Delete the rows and accounts.
- **Test data:** Emails `spm-test-*`.
- **Expected:** 1 → `201`. 2 → `201`. 3 → `200`, `"status": "cancelled"`, `"notified_attendees": 2`. 4 → A and W each have exactly one `event_cancelled` row for P, message "Event cancelled: {P's name}, {date}, 6:00 pm – 9:00 pm. It will not take place."; X has none. Neither message contains "Speaker unavailable". 5 → `200`; A still has exactly one. 6 leaves no rows.
- **Actual:** First run: approval `502` -- the events service hit `23514` on `events_safety_state_consistent`; fixed by the S-69 block of `events.sql`. After it was applied: `201`, `201`; approval `200`, `cancelled`, `notified_attendees` 2; A and W each had exactly one `event_cancelled` row with the expected message and no reason; X none; approving again `200`, A still one; no rows remained. Passed again on a second run.
- **Status:** Pass
- **Evidence:** tests/integration/composite/event_requests/test_s69.py::test_approving_a_cancellation_notifies_registered_and_waiting_attendees_once; `.env.test` stack recreated with `--build` immediately before (users container verified on the test project's `SUPABASE_URL`); S-69 blocks of `notifications.sql` and `events.sql` applied to dev and test; 2026-10-30, branch `S-69/notify-attendee-event-cancelled` (on sprint4 `58d6d9f`), pre-commit working tree; with `tests/integration/composite/event_requests`, `tests/integration/atomic/notifications` and `tests/integration/atomic/events`: 32 passed, 5 skipped; e2e `test_approve_cancellation.py` and `test_request_event_cancellation.py`: 2 passed

## S-63 — Notify Organiser — Event Decisions and Changes

Drafted and confirmed by the developer on 2026-10-31 before implementation.

## TC-EVENTREQUESTS-204 — a real request outcome reaches the Organiser inbox

- **Scenario:** The decision crosses Users, Events and Notifications through Kong and persists for the owning Organiser.
- **Pre-conditions:** Fresh `.env.test` stack; schemas applied, exposed and granted; one submitted event assigned to a Coordinator.
- **Steps:** The Coordinator returns it with reason and amendment comment, then the Organiser lists `/api/notifications`.
- **Expected:** The saved event is returned and the inbox has exactly one `event_request_decision` row naming the event, reason, comment and resubmission action.
- **Actual:** The returned event persisted and the owning Organiser received exactly one actionable notification with the event name, reason, amendment comment and resubmission instruction.
- **Status:** Pass
- **Evidence:** `test_s63.py::test_a_real_returned_outcome_reaches_the_organiser_inbox`; 2026-11-01, branch `S-63/notify-organiser-event-decisions-and-changes` merged with `origin/sprint4` `92b230c`; fresh verified `.env.test` stack; full integration suite: 112 passed, 5 skipped.

## TC-EVENTREQUESTS-205 — a real schedule change reaches the Organiser once

- **Scenario:** A significant Coordinator edit and notification persist across the Events/Notifications boundary.
- **Pre-conditions:** As TC-EVENTREQUESTS-204, with an editable planning event.
- **Steps:** Move the event to a later date through `/api/event-requests/{id}/information`, then repeat the same request.
- **Expected:** The first response saves the new date and one postponed notice; the stale repeat is refused and creates no second row.
- **Actual:** The first edit saved the later date and one postponed notice; the stale retry was refused and the Organiser still had one notice.
- **Status:** Pass
- **Evidence:** `test_s63.py::test_a_real_postponement_reaches_the_organiser_once`; 2026-11-01, branch `S-63/notify-organiser-event-decisions-and-changes` merged with `origin/sprint4` `92b230c`; fresh verified `.env.test` stack; full integration suite: 112 passed, 5 skipped.

## S-89 — Coordinator Cancels Event Without Alternative Venue (draft specification)

Drafted and confirmed 2026-11-01. IDs 450–499
reserved for S-89 integration cases. Needs the S-89 blocks of
`backend/sql/events.sql` and `backend/sql/bookings.sql` applied to the test
project; `event_requests` reaches `venue_bookings` through
`VENUE_BOOKINGS_SERVICE_URL` (defaulted in `docker-compose.yml`). Blocked
until the SQL is applied.

## TC-EVENTREQUESTS-450 — an affected two-venue event is cancelled through Kong with everything closed, recorded, released and announced

- **Scenario:** Across real Events, Bookings, Venue Bookings, Registrations, Notifications and Equipment: nothing happens automatically, then the Coordinator's cancellation reaches a consistent final state (S-89 AC1–AC4).
- **Pre-conditions:** Fresh `.env.test` stack. A `confirmed` event E (21 days ahead) with Coordinator K and Organiser O; confirmed bookings at V1 and V2 and a pending replacement for V1 at V3; two registered Attendees and one waiting; a requirement for 4 of item Q (total 10).
- **Steps:** 1. As Venue Staff, `POST /api/venue-bookings/blocks` over V1's booking. 2. Read E and its bookings. 3. As K, `POST /api/event-requests/E/venue-cancellation`. 4. Read E, its bookings, its closure, its history, the notifications, and (as Technical Support) Q's availability. 5. Repeat step 3.
- **Test data:** `spm-test-*` rows, deleted afterwards.
- **Expected:** 2 → E and its bookings unchanged (AC1). 3 → `200`, `released_bookings` 3, `notified_attendees` 3, `cancellation_completed` true. 4 → E `cancelled` with the reason and `venue_cancellation_completed_at`; all three bookings `released`; the closure `closed`; one `cancelled_venue_unavailable` entry by K with the reason; O one `event_cancelled` notification with the reason; each Attendee exactly one ending "It will not take place."; Q 10 available. 5 → `200`, no new notification rows.
- **Actual:** Before cancelling, E and its bookings unchanged. `200`, `released_bookings` 3, `notified_attendees` 3, completed. E `cancelled` with reason and completion time; three bookings `released`; closure `closed`; one history entry by K with the reason; Organiser one notification with the reason; each Attendee exactly one; Q 10 available. The repeat `200` with no new notifications.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s89.py::test_an_affected_two_venue_event_is_cancelled_with_everything_released_and_announced`; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree after the closure-intent and durable-history revision; revised S-89 SQL applied to dev and test by the developer; isolated `spm-s89` compose project recreated with `--env-file .env.test --build` immediately before (published ports +10000, users container verified on the test project's `SUPABASE_URL`); Python 3.12.5, pytest 9.2.0: S-89 integration 8 passed (2:42); full `tests/integration` 120 passed, 5 skipped (the existing S-83 supersessions), 0 failed (22:35)

## TC-EVENTREQUESTS-451 — unaffected or unassigned events stay untouched and unlocked

- **Scenario:** The verification uses the real flag and assignments, and a refused attempt leaves no closure behind.
- **Pre-conditions:** As TC-EVENTREQUESTS-450, with a planning event G whose booking nothing affects, and a second Coordinator D.
- **Steps:** 1. Mark V1 unavailable. 2. As K, cancel G. 3. As D, cancel E.
- **Test data:** As above.
- **Expected:** 2 → `409` "None of this event's venue bookings is affected by an unavailable venue, so it can't be cancelled here." 3 → `404`. Afterwards both events and their bookings unchanged, no `closed_events` row for either, no `event_cancelled` notification.
- **Actual:** G `409` with the not-affected detail; D `404`; both events and bookings unchanged, no `closed_events` row and no `event_cancelled` notification for either.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s89.py::test_unaffected_or_unassigned_events_stay_untouched`; 2026-11-01, branch `S-89/coordinator-cancels-event-without-alternative-venue` (on sprint4 `ca5ff0d`), pre-commit working tree after the closure-intent and durable-history revision; revised S-89 SQL applied to dev and test by the developer; isolated `spm-s89` compose project recreated with `--env-file .env.test --build` immediately before (published ports +10000, users container verified on the test project's `SUPABASE_URL`); Python 3.12.5, pytest 9.2.0: S-89 integration 8 passed (2:42); full `tests/integration` 120 passed, 5 skipped (the existing S-83 supersessions), 0 failed (22:35)

---

## S-60 — Review Impact of Significant Changes (approved)

Source: Product Backlog row 63. Latest S-60 execution: 2026-11-01 on `S-60/review-impact-of-significant-changes` at `d5bab4c` (rebased onto `origin/sprint4` `ca5ff0d`) plus the follow-up S-18/S-63/S-82 route and registration-cleanup test updates committed on top. Fresh `.env.test` stack and TEST Supabase. Full integration suite: 119 passed, 5 skipped, 0 failed. Significant S-18 edits now go through `PATCH .../information/significant`; routine edits stay on `PATCH .../information`. S-55's withdrawal workflow is integrated; do not reapply S-53 SQL. See each case evidence.

## TC-EVENTREQUESTS-310 — real acceptance persists across service boundaries

- **Scenario:** Accepted proposal, per-booking flags and old sign-offs survive reload through Kong.
- **Pre-conditions:** Shared; E confirmed with B1/B2, P quantity 2, T sign-off and attendee record; R pending.
- **Steps:** 1. O submits attendance 120→150 and P 2→3. 2. C opens review and accepts. 3. Reload Events, Equipment, Bookings, Safety readiness and history through HTTP. 4. D attempts review.
- **Test data:** B1 capacity 130, B2 capacity 220; P 2→3; temporary `spm-test-s60-*` users.
- **Expected:** E is planning at 150; P=3; R accepted with C/time and retained snapshots; B1/P/T flags have reasons, B2 has no false capacity flag. Both bookings, old sign-offs, T assignment, attendee and history remain. Readiness blocks until resolution; D gets scoped denial.
- **Actual:** Real Kong acceptance persisted 150 attendees and P=3, preserved linked rows, and left scoped re-review flags blocking safety.
- **Status:** Pass
- **Evidence:** tests/integration/composite/event_requests/test_s60.py::test_real_acceptance_preserves_arrangements

## TC-EVENTREQUESTS-311 — persisted flags resolve one by one

- **Scenario:** Venue and equipment re-review outcomes remain durable and only clear with owner-backed evidence.
- **Pre-conditions:** Shared; accepted R has B1 and P flags; replacement booking B3 and new T sign-off can be created.
- **Steps:** 1. Try clearance without evidence. 2. Approve B3, resolve B1. 3. Reload; verify P still blocks. 4. Revalidate P live, have T sign, resolve P. 5. Read readiness/history.
- **Test data:** B1→B3; P=3.
- **Expected:** Invalid clearance gets 409; B1 resolution persists with action/time; P remains until its own valid resolution. Old approvals remain in their owner records. Only after both flags resolve and other S-17 items pass is readiness true.
- **Actual:** Browser reloaded each venue/equipment resolution; owner-backed staff decisions cleared flags one at a time and only then allowed safety submission.
- **Status:** Pass
- **Evidence:** tests/e2e/test_review_significant_event_changes.py::test_proposal_review_resolution_requires_fresh_safety_check[chromium]; tests/unit/composite/event_requests/test_s60.py::test_impact_resolution_cannot_impersonate_technical_support

## TC-EVENTREQUESTS-312 — races and failure do not create false acceptance

- **Scenario:** Real Events/Equipment persistence keeps one decision and one outstanding request, including recoverable interruption.
- **Pre-conditions:** Shared; R pending; test harness can pause or fail one owner call in a controlled way.
- **Steps:** 1. Race two acceptances and an Equipment edit. 2. Simulate Events finalisation failure after Equipment batch. 3. Read R/E/P; retry operation; submit R2.
- **Test data:** R P 2→3; competing P→4; R2 attendance 120→130.
- **Expected:** One outcome wins; stale callers get 409. Incomplete operation never returns accepted and keeps R2 blocked; retry or conditional abort preserves a coherent accepted state. No duplicate history or lost Equipment edit. A terminal rejection/acceptance permits a later pending R2.
- **Actual:** Competing prepares yielded one operation; failed completion kept applying and blocked R2, then retry accepted once and reopened the slot.
- **Status:** Pass
- **Evidence:** tests/integration/composite/event_requests/test_s60.py::test_real_concurrent_acceptance_and_recovery
