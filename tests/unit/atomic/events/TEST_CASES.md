# Test cases — events service schemas (unit)

Covers `tests/unit/atomic/events/test_schemas.py` and `test_app.py`: validation,
normalization, authentication, RBAC, ownership, and endpoint behaviour with both
Supabase clients mocked. They use no network, database, or Docker.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/events` |
| Last run | 2026-10-09, branch `S-85/view-coordinator-assignments-and-active-events`, commit `628e09b` |
| Environment | Python 3.14.8, pytest 9.1.1; no network, database, or Docker |
| Result | 151 passed in this suite; 832 passed, 17 skipped across `tests/unit` |

## TC-EVENTS-001 — valid partial draft

- **Scenario:** Revised for S-36: the free-text accessibility notes are gone; `special_requirements` (Other requirements) is the one free-text field. A draft accepts valid supplied values without requiring the full submission.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` with a padded name, attendance,
  start/end times, one equipment quantity, and blank other-requirements text.
- **Test data:** Name `"  Alumni networking evening  "`, attendance `120`,
  times `18:00`–`21:00`, equipment `{"projector": 1}`, special requirements `"   "`.
- **Expected:** The model is valid; text is trimmed; blank optional
  `special_requirements` becomes `None`; attendance and equipment are retained.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_valid_draft_accepts_and_normalises_supplied_values`

## TC-EVENTS-002 — empty draft

- **Scenario:** A user can save a draft before filling in any business field.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` without arguments.
- **Test data:** `{}`.
- **Expected:** The model is valid; optional scalar fields are `None` and
  venue requirement lists are empty.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_empty_draft_is_valid`

## TC-EVENTS-003 — invalid draft attendance

- **Scenario:** A supplied draft attendance must be positive.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` with attendance zero.
- **Test data:** `{"expected_attendance": 0}`.
- **Expected:** Pydantic raises `ValidationError`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_draft_rejects_non_positive_attendance`

## TC-EVENTS-004 — legacy organiser equipment field is refused

- **Scenario:** Equipment requirements cannot be written through an organiser event payload.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` with the removed legacy field.
- **Test data:** `{"equipment_requests": {"projector": 1}}`.
- **Expected:** Pydantic raises `ValidationError`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_draft_rejects_legacy_organiser_equipment_requests`

## TC-EVENTS-005 — invalid draft time ordering

- **Scenario:** A draft with both times supplied requires end after start.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` with start `21:00` and end `18:00`.
- **Test data:** `{"start_time": "21:00", "end_time": "18:00"}`.
- **Expected:** `ValidationError` containing `end_time must be after start_time`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_draft_rejects_invalid_time_ordering`

## TC-EVENTS-006 — valid submitted request

- **Scenario:** A complete submitted request is accepted.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventSubmittedCreate` with every required field and
  both optional fields.
- **Test data:** Alumni networking event on `2026-10-20`, `18:00`–`21:00`,
  attendance `120`, Main auditorium, two equipment entries, wheelchair access.
- **Expected:** The model is valid and retains the normalized values.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_valid_submitted_request_is_accepted`

## TC-EVENTS-007 — missing submitted-required field

- **Scenario:** Revised for S-36: `venue` is now an optional preference, so `name` stands in as the required field. A submitted request cannot omit a required field.
- **Pre-conditions:** The otherwise-valid submitted payload from TC-EVENTS-006.
- **Steps:** Remove `name` and instantiate `EventSubmittedCreate`.
- **Test data:** Valid submitted payload without `name`.
- **Expected:** `ValidationError` identifies `name`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_submitted_request_rejects_missing_required_field`

## TC-EVENTS-008 — blank submitted-required text

- **Scenario:** Whitespace is not a valid submitted event name.
- **Pre-conditions:** The otherwise-valid submitted payload from TC-EVENTS-006.
- **Steps:** Replace `name` with whitespace and instantiate `EventSubmittedCreate`.
- **Test data:** `"name": "   "`.
- **Expected:** Blank text normalizes to `None`, which produces a
  `ValidationError` on `name`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_submitted_request_rejects_blank_required_text`

## TC-EVENTS-009 — invalid submitted attendance

- **Scenario:** Submitted attendance must be positive.
- **Pre-conditions:** The otherwise-valid submitted payload from TC-EVENTS-006.
- **Steps:** Set attendance to `-1` and instantiate `EventSubmittedCreate`.
- **Test data:** `"expected_attendance": -1`.
- **Expected:** Pydantic raises `ValidationError`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_submitted_request_rejects_non_positive_attendance`

## TC-EVENTS-010 — invalid submitted time ordering

- **Scenario:** A submitted end time must be later than its start time.
- **Pre-conditions:** The otherwise-valid submitted payload from TC-EVENTS-006.
- **Steps:** Make start and end both `18:00` and instantiate
  `EventSubmittedCreate`.
- **Test data:** `"start_time": "18:00", "end_time": "18:00"`.
- **Expected:** `ValidationError` containing `end_time must be after start_time`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_submitted_request_rejects_invalid_time_ordering`

## TC-EVENTS-011 — server-managed fields are forbidden

- **Scenario:** A client cannot assign identity, ownership, status, or timestamps.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftUpdate` with all five server-managed fields.
- **Test data:** `id`, `organiser_id`, `status`, `created_at`, and `updated_at`.
- **Expected:** Pydantic raises `ValidationError` with `extra_forbidden` entries
  for exactly those five fields.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_request_schemas_reject_server_managed_fields`

## TC-EVENTS-012 — health check

- **Scenario:** The service reports that it is alive without touching Supabase.
- **Pre-conditions:** Both Supabase dependencies are mocked.
- **Steps:** `GET /health`.
- **Test data:** None.
- **Expected:** `200` with `{"status": "ok"}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_health_reports_ok`

## TC-EVENTS-013 — create a valid draft

- **Scenario:** An event organiser creates a partial draft.
- **Pre-conditions:** A valid access cookie resolves to an `event_organiser`;
  the insert returns the stored draft.
- **Steps:** `POST /events/drafts` with a name only.
- **Test data:** `{"name": "Planning draft"}`.
- **Expected:** `201` and a response whose status is `draft`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_create_valid_draft`

## TC-EVENTS-014 — create a submitted event

- **Scenario:** An event organiser creates an immediately submitted request.
- **Pre-conditions:** A valid organiser session; the insert returns the event.
- **Steps:** `POST /events` with all submitted-required fields.
- **Test data:** Alumni networking event, `2026-10-20`, `18:00`–`21:00`,
  attendance `120`, Main auditorium.
- **Expected:** `201` and status `submitted`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_create_submitted_event`

## TC-EVENTS-015 — ownership and status come from the server

- **Scenario:** Draft creation uses the verified user's id and a server-assigned status.
- **Pre-conditions:** The access cookie resolves to organiser
  `11111111-1111-4111-8111-111111111111`.
- **Steps:** `POST /events/drafts` with an empty body; inspect the insert call.
- **Test data:** `{}`.
- **Expected:** The inserted row contains that organiser id and `status=draft`;
  neither value came from the request body.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_create_derives_organiser_and_status_from_session`

## TC-EVENTS-016 — wrong role is forbidden

- **Scenario:** An authenticated internal role cannot create event requests.
- **Pre-conditions:** The verified user's `app_metadata.role` is `event_coordinator`.
- **Steps:** `POST /events/drafts`.
- **Test data:** `{}`.
- **Expected:** `403`; no database call.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_create_rejects_wrong_role`

## TC-EVENTS-017 — missing role is forbidden

- **Scenario:** Authentication alone is insufficient for organiser writes.
- **Pre-conditions:** The verified user's app metadata has no role.
- **Steps:** `POST /events` with a valid submitted body.
- **Test data:** The valid submitted event from TC-EVENTS-014.
- **Expected:** `403`; no database call.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_create_rejects_missing_role`

## TC-EVENTS-018 — retrieve an owned event

- **Scenario:** An authenticated owner can retrieve their event.
- **Pre-conditions:** The ownership-filtered select returns one draft.
- **Steps:** `GET /events/33333333-3333-4333-8333-333333333333`; inspect filters.
- **Test data:** The event and authenticated organiser UUIDs.
- **Expected:** `200`; query filters by both event id and organiser id.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_retrieve_owned_event`

## TC-EVENTS-019 — another user's event is hidden

- **Scenario:** Knowing another event's UUID does not expose it.
- **Pre-conditions:** The ownership-filtered select returns no rows.
- **Steps:** `GET` the event UUID as the authenticated caller.
- **Test data:** Event UUID above and a non-owning session.
- **Expected:** `404` with `Event not found`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_cannot_retrieve_another_users_event`

## TC-EVENTS-020 — update an owned draft

- **Scenario:** PATCH changes only explicitly supplied draft fields.
- **Pre-conditions:** The owned record is a draft; update returns the changed row.
- **Steps:** `PATCH` the event with a new name; inspect the update payload.
- **Test data:** `{"name": "New name"}`.
- **Expected:** `200`; update payload contains only `name`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_update_owned_draft_uses_only_supplied_fields`

## TC-EVENTS-021 — a submitted event can still be edited

- **Scenario:** Submitting a request does not lock it — the organiser can keep
  changing it afterwards. The update endpoint no longer gates on status; the
  event stays `submitted` after the edit.
- **Pre-conditions:** The owned lookup returns status `submitted`.
- **Steps:** `PATCH` the event with a new name.
- **Test data:** `{"name": "Changed"}`.
- **Expected:** `200`; the response has the new name and status `submitted`;
  the update payload contains only `name`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_can_update_submitted_event`

## TC-EVENTS-022 — submit an existing draft

- **Scenario:** An organiser atomically replaces draft fields and submits it.
- **Pre-conditions:** The owned lookup returns a draft; update returns a submitted row.
- **Steps:** `POST /events/{id}/submit` with a complete submitted payload.
- **Test data:** The valid submitted event from TC-EVENTS-014.
- **Expected:** `200`; update includes all validated fields and server-assigned
  `status=submitted` while filtering the existing row as a draft.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submit_existing_draft`

## TC-EVENTS-023 — submitted event cannot be resubmitted

- **Scenario:** Submission is not repeatable after the status transition.
- **Pre-conditions:** The owned lookup returns status `submitted`.
- **Steps:** `POST /events/{id}/submit` again.
- **Test data:** The valid submitted payload.
- **Expected:** `409`; update is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_cannot_resubmit_submitted_event`

## TC-EVENTS-024 — database failure is safe

- **Scenario:** Internal storage details are not returned to callers.
- **Pre-conditions:** The insert raises an exception containing sensitive text.
- **Steps:** `POST /events/drafts`.
- **Test data:** Empty draft; exception text `database credentials leaked here`.
- **Expected:** `500` with only `{"detail": "Event storage unavailable"}`.
- **Actual:** As expected; exception text was absent.
- **Status:** Pass
- **Evidence:** `test_app.py::test_database_failure_returns_safe_500`

## TC-EVENTS-025 — authentication is required

- **Scenario:** A caller without session cookies cannot create a draft.
- **Pre-conditions:** No cookies.
- **Steps:** `POST /events/drafts`.
- **Test data:** `{}`.
- **Expected:** `401` with `Not authenticated`; no database call.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_create_requires_authentication`

## TC-EVENTS-026 — PATCH validates the resulting draft

- **Scenario:** A partial time update cannot conflict with a time already stored.
- **Pre-conditions:** The owned draft already has `start_time=18:00`.
- **Steps:** PATCH only `end_time=17:00`.
- **Test data:** Existing start `18:00`; body `{"end_time": "17:00"}`.
- **Expected:** `422` containing `end_time must be after start_time`; update is
  never sent to Supabase.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_update_validates_time_order_against_existing_draft`

## TC-EVENTS-027 — Event Organiser permissions

> **S-62 (2026-10-11):** the expected set now also includes `events:request_cancellation`.

- **Scenario:** The public organiser role has exactly the supported Sprint 1 permissions.
- **Pre-conditions:** The centralized role policy is loaded.
- **Steps:** Read the `event_organiser` permission set.
- **Test data:** `event_organiser`.
- **Expected:** Dashboard access plus exactly create, save draft, view own,
  update own draft, and submit own.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_event_organiser_has_the_sprint_one_permissions`

## TC-EVENTS-028 — other roles only receive dashboard access

- **Scenario:** Roles with no defined workflow gain no unimplemented event
  powers. `event_coordinator` moved to its own case (TC-EVENTS-057) once it
  gained `events:view_assigned`.
- **Pre-conditions:** The centralized role policy is loaded.
- **Steps:** Read the permission set for every other known role.
- **Test data:** `venue_staff`, `technical_support`, `attendee`.
- **Expected:** Each role has exactly `dashboard:view` and no `events:*` permission.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_other_known_roles_only_have_dashboard_permission`

## TC-EVENTS-029 — unknown role is rejected

- **Scenario:** An unrecognized app-metadata role cannot use a protected route.
- **Pre-conditions:** The verified user's trusted role is `invented_role`.
- **Steps:** `POST /events/drafts`.
- **Test data:** `{}`.
- **Expected:** `403` with `Recognized role required`; no database call.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_unknown_role_is_rejected`

## TC-EVENTS-030 — user metadata cannot grant permission

- **Scenario:** User-controlled metadata cannot override trusted app metadata.
- **Pre-conditions:** `app_metadata.role=attendee` while
  `user_metadata.role=event_organiser`.
- **Steps:** `POST /events/drafts`.
- **Test data:** `{}`.
- **Expected:** `403` with `Permission denied`; no database call.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_user_metadata_role_is_not_trusted`

## TC-EVENTS-031 — gateway-compatible health path

- **Scenario:** Kong can check and expose service health beneath the events
  route prefix without changing the standard atomic-service health endpoint.
- **Pre-conditions:** Both Supabase dependencies are mocked.
- **Steps:** `GET /events/health`.
- **Test data:** None.
- **Expected:** `200` with `{"status": "ok"}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_prefixed_health_reports_ok_for_gateway`

## TC-EVENTS-032 — list only the authenticated organiser's events

- **Scenario:** An organiser can list their saved requests without exposing
  another organiser's rows.
- **Pre-conditions:** The verified user is an Event Organiser; the mocked
  owner-filtered query returns one draft and one submitted request.
- **Steps:** `GET /events`; inspect the Supabase query.
- **Test data:** Organiser `11111111-1111-4111-8111-111111111111` and two event
  rows.
- **Expected:** `200` with both events; the query filters `organiser_id` to the
  verified user's id and orders by `updated_at` descending.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_list_returns_only_authenticated_organisers_events`

## TC-EVENTS-033 — empty organiser event list

- **Scenario:** A valid organiser with no saved requests receives an empty list.
- **Pre-conditions:** The owner-filtered query returns no rows.
- **Steps:** `GET /events`.
- **Test data:** Organiser `11111111-1111-4111-8111-111111111111`.
- **Expected:** `200` with `[]` rather than `404`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_list_returns_empty_array_when_organiser_has_no_events`

## TC-EVENTS-034 — event list requires view permission

- **Scenario:** A role without `events:view_own` cannot enumerate event rows.
- **Pre-conditions:** The verified user's trusted role is `attendee`.
- **Steps:** `GET /events`.
- **Test data:** Authenticated attendee session.
- **Expected:** `403` with `Permission denied`; Supabase is never queried.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_list_rejects_role_without_view_permission`

## TC-EVENTS-035 — PATCH validates the resulting date order

- **Scenario:** A partial date update cannot leave a stored end date before the
  stored start date.
- **Pre-conditions:** The owned draft already has `start_date=2026-10-20`.
- **Steps:** PATCH only `end_date=2026-10-19`.
- **Test data:** Existing start `2026-10-20`; body `{"end_date": "2026-10-19"}`.
- **Expected:** `422` containing `end_date must be on or after start_date`;
  update is never sent to Supabase.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_update_validates_date_order_against_existing_draft`

## TC-EVENTS-036 — multi-day event may end earlier in the clock than it starts

- **Scenario:** An event that spans midnight is not held to the single-day
  `end_time` > `start_time` rule.
- **Pre-conditions:** A valid organiser session; the insert returns the stored
  event.
- **Steps:** `POST /events` with `start_date` one day before `end_date` and
  `end_time` earlier in the clock than `start_time`.
- **Test data:** `start_date=2026-10-20`, `start_time=22:00`,
  `end_date=2026-10-21`, `end_time=02:00`.
- **Expected:** `201` and status `submitted`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_create_accepts_multi_day_event_with_end_time_before_start_time`

## TC-EVENTS-037 — invalid draft date ordering

- **Scenario:** A draft with both dates supplied requires end on or after start.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` with start `2026-10-20` and end
  `2026-10-19`.
- **Test data:** `{"start_date": "2026-10-20", "end_date": "2026-10-19"}`.
- **Expected:** `ValidationError` containing `end_date must be on or after start_date`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_draft_rejects_end_date_before_start_date`

## TC-EVENTS-038 — invalid submitted date ordering

- **Scenario:** A submitted end date must be on or after its start date.
- **Pre-conditions:** The otherwise-valid submitted payload from TC-EVENTS-006.
- **Steps:** Set `end_date` earlier than `start_date` and instantiate
  `EventSubmittedCreate`.
- **Test data:** `"start_date": "2026-10-20", "end_date": "2026-10-19"`.
- **Expected:** `ValidationError` containing `end_date must be on or after start_date`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_submitted_request_rejects_end_date_before_start_date`

## TC-EVENTS-039 — submitted multi-day event allows an earlier end clock time

- **Scenario:** A submitted request spanning two calendar days is not held to
  the single-day `end_time` > `start_time` rule.
- **Pre-conditions:** The otherwise-valid submitted payload from TC-EVENTS-006.
- **Steps:** Set `start_date`/`end_date` one day apart and `end_time` earlier
  than `start_time`, then instantiate `EventSubmittedCreate`.
- **Test data:** `start_date=2026-10-20`, `start_time=22:00`,
  `end_date=2026-10-21`, `end_time=02:00`.
- **Expected:** The model is valid.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_submitted_request_allows_end_time_before_start_time_across_days`

## TC-EVENTS-040 — editing a submitted event still enforces submitted-required fields

- **Scenario:** Revised for S-36: `venue` is now an optional preference, so `name` stands in as the required field. PATCH on a submitted event is validated against the
  submitted-required rules, not the draft's permissive ones, so it cannot
  null out a field the database's own constraint requires.
- **Pre-conditions:** The owned lookup returns the submitted payload from
  TC-EVENTS-014.
- **Steps:** `PATCH` the event, clearing `name`.
- **Test data:** `{"name": ""}`.
- **Expected:** `422` identifying `name`; update is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_updating_submitted_event_still_requires_submitted_fields`

## TC-EVENTS-041 — a draft accepts other requirements

- **Scenario:** Free-text requirements outside the fixed fields are kept on a draft.
- **Pre-conditions:** None — schema validation only.
- **Steps:** Build an `EventDraftCreate` with `special_requirements` set.
- **Test data:** `"  Sign-up sheet on the door  "`.
- **Expected:** Accepted, stored trimmed as `"Sign-up sheet on the door"`.
- **Actual:** Trimmed and retained.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_draft_accepts_special_requirements`

## TC-EVENTS-042 — a submitted request accepts other requirements

- **Scenario:** The same field survives on a submitted request, not just a draft.
- **Pre-conditions:** None.
- **Steps:** Build an `EventSubmittedCreate` from a valid payload plus `special_requirements`.
- **Test data:** `"Registration closes a week before"`.
- **Expected:** Accepted and retained.
- **Actual:** Retained.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_submitted_request_accepts_special_requirements`

## TC-EVENTS-043 — other requirements are optional for submission

- **Scenario:** The field is a place to say something, not something that must be said.
- **Pre-conditions:** None.
- **Steps:** Build a valid submitted payload (1) omitting the field, (2) with only whitespace.
- **Test data:** field absent; field `"   "`.
- **Expected:** Both valid; both normalise to `None`. No validation error.
- **Actual:** Both accepted as `None`.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_special_requirements_is_optional_for_submission`

## TC-EVENTS-044 — creating a submitted event records the submission time

- **Scenario:** Submitting records when it happened, so the action is auditable.
- **Pre-conditions:** Authenticated organiser; fake Supabase.
- **Steps:** `POST /events` with a valid submitted payload; inspect the insert sent to the database.
- **Test data:** The standard valid submitted payload.
- **Expected:** `201`, and the inserted row carries a non-null `submitted_at`. Checked on the write, not the response — a client must not be able to choose its own submission time.
- **Actual:** `submitted_at` present on the insert.
- **Status:** Pass
- **Evidence:** `test_app.py::test_creating_a_submitted_event_records_the_submission_time`

## TC-EVENTS-045 — creating a draft records no submission time

- **Scenario:** A draft has not been submitted, so the column stays empty.
- **Pre-conditions:** Authenticated organiser; fake Supabase.
- **Steps:** `POST /events/drafts`; inspect the insert.
- **Test data:** `{"name": "Planning draft"}`.
- **Expected:** `201`, and `submitted_at` is explicitly `None` — so the column always means "submitted at this time", never "last touched".
- **Actual:** `submitted_at` was `None`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_creating_a_draft_records_no_submission_time`

## TC-EVENTS-046 — submitting an existing draft records the submission time

- **Scenario:** The draft-then-submit path records the time as well as the create-submitted path.
- **Pre-conditions:** Authenticated organiser owning a draft.
- **Steps:** `POST /events/{id}/submit` with a valid payload; inspect the update.
- **Test data:** The standard valid submitted payload.
- **Expected:** `200`, and the update carries a non-null `submitted_at`.
- **Actual:** `submitted_at` present on the update.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submitting_a_draft_records_the_submission_time`

## TC-EVENTS-047 — another organiser's draft cannot be edited

- **Scenario:** Ownership is enforced on writes, not only on reads.
- **Pre-conditions:** Authenticated organiser; the owned lookup returns nothing, which is what another user's event looks like.
- **Steps:** `PATCH /events/{id}` with a change.
- **Test data:** `{"name": "Changed"}`.
- **Expected:** `404` `"Event not found"`, and **no update is issued at all** — the request must not reach the table.
- **Actual:** `404`; update never called.
- **Status:** Pass
- **Evidence:** `test_app.py::test_cannot_update_another_users_draft`

## TC-EVENTS-048 — another organiser's draft cannot be submitted

- **Scenario:** The same ownership rule on the submit route.
- **Pre-conditions:** As above.
- **Steps:** `POST /events/{id}/submit` with a valid payload.
- **Test data:** The standard valid submitted payload.
- **Expected:** `404` `"Event not found"`, and no update issued.
- **Actual:** `404`; update never called.
- **Status:** Pass
- **Evidence:** `test_app.py::test_cannot_submit_another_users_draft`

---

**S-12 additions.** The `event_requests` composite needs the events service
to report, for a set of coordinators and a requested window, who is free and
how busy they are, and needs a trusted way to create or submit an event with
an already-decided `assigned_coordinator_id` — a field an organiser's own
request can never set. Both new routes are internal: no Kong entry, called
only by `event_requests` over the Docker network, never by a browser.

## TC-EVENTS-049 — coordinator load reports no conflict with an empty schedule

- **Scenario:** A coordinator with nothing assigned is free for any window.
- **Pre-conditions:** The assignment-filtered select for that coordinator
  returns no rows.
- **Steps:** `POST /events/coordinator-load` with one coordinator id and a
  window.
- **Test data:** Coordinator id above; window `2026-10-20 18:00`–`21:00`.
- **Expected:** `200`; that coordinator's entry has `conflict: false,
  assigned_count: 0`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_load_reports_no_conflict_with_empty_schedule`

## TC-EVENTS-050 — coordinator load reports a conflict on any overlap

- **Scenario:** The requested window intersects an assigned event's window at
  all, not only when the two match exactly.
- **Pre-conditions:** The coordinator has one assigned submitted event
  `18:00`–`21:00` on `2026-10-20`.
- **Steps:** `POST /events/coordinator-load` with a request window that
  overlaps only partially: `20:00`–`22:00` the same day.
- **Test data:** As above.
- **Expected:** `200`; `conflict: true`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_load_reports_a_conflict_on_any_overlap`

## TC-EVENTS-051 — back-to-back events do not conflict

- **Scenario:** A request starting exactly when an existing assigned event
  ends (or ending exactly when one starts) does not count as an overlap.
- **Pre-conditions:** The coordinator has one assigned submitted event
  `18:00`–`21:00` on `2026-10-20`.
- **Steps:** `POST /events/coordinator-load` with a request window
  `21:00`–`22:00` the same day.
- **Test data:** As above.
- **Expected:** `200`; `conflict: false`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_load_back_to_back_events_do_not_conflict`

## TC-EVENTS-052 — only live commitments count toward load or conflict

- **Scenario:** Only submitted (awaiting decision) and planning (accepted,
  arrangements underway) events are committed time on a coordinator's
  schedule. Drafts never counted. Returned and rejected don't either, since
  neither is a live commitment. Revised for S-36: `planning` replaces
  `approved`, which no longer exists.
- **Pre-conditions:** None beyond the shared fakes.
- **Steps:** `POST /events/coordinator-load`; inspect the Supabase query sent.
- **Test data:** One coordinator id, any window.
- **Expected:** The query filters on `status in ("submitted", "planning")`.
  Every other status is excluded in the query itself, not filtered out
  afterwards, so it can never reach the conflict check or the count.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_load_query_only_counts_submitted_and_planning_events`

## TC-EVENTS-053 — internal create trusts the caller's organiser and coordinator ids

- **Scenario:** Unlike the public `POST /events`, this route does not derive
  `organiser_id` from a session — the caller (the composite) has already
  verified it and supplies it directly, along with the assignment.
- **Pre-conditions:** None.
- **Steps:** `POST /events/internal` with a complete submitted payload plus
  `organiser_id` and `assigned_coordinator_id`; inspect the insert.
- **Test data:** The standard valid submitted payload, an organiser id, and a
  coordinator id.
- **Expected:** `201`; the inserted row's `organiser_id` and
  `assigned_coordinator_id` are exactly the ones supplied; `status=submitted`
  and `submitted_at` set, same as the public route.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_create_trusts_caller_organiser_and_coordinator_ids`

## TC-EVENTS-054 — internal submit sets the assignment and enforces ownership

- **Scenario:** The draft-to-submission internal route applies the same
  ownership and draft-status filter as the public one, plus the assignment.
- **Pre-conditions:** A draft owned by the given organiser id exists.
- **Steps:** `POST /events/{event_id}/submit/internal` with the standard
  submitted payload, that organiser id, and a coordinator id.
- **Test data:** As above.
- **Expected:** `200`; the update is filtered by both `id` and
  `organiser_id`, sets `status=submitted`, `submitted_at`, and
  `assigned_coordinator_id` to the supplied coordinator.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_submit_sets_the_assignment`

## TC-EVENTS-055 — internal submit still enforces ownership

- **Scenario:** Supplying a coordinator id does not bypass the ownership
  check — the row must still belong to the given organiser and still be a
  draft.
- **Pre-conditions:** The owned-and-draft-filtered update matches no row.
- **Steps:** `POST /events/{event_id}/submit/internal` with an organiser id
  that does not own the draft.
- **Test data:** As TC-EVENTS-054, different organiser id.
- **Expected:** `404`; no assignment applied.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_submit_still_enforces_ownership`

## TC-EVENTS-056 — assigned_coordinator_id is null until assigned

- **Scenario:** A plain draft or an event created through the public routes
  carries no coordinator until the internal route sets one.
- **Pre-conditions:** A draft created through `POST /events/drafts`.
- **Steps:** `GET /events/{id}` for that draft.
- **Test data:** `{"name": "Planning draft"}`.
- **Expected:** `201`; `assigned_coordinator_id` is `null`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_assigned_coordinator_id_is_null_until_assigned`

---

**Follow-up (same session).** Assignment alone was not the whole story: a
coordinator had no way to see what was routed to them. `event_coordinator`
gains a first, read-only permission — `events:view_assigned` — and two
browser-facing routes.

## TC-EVENTS-057 — event_coordinator has the view and decide permissions

- **Scenario:** S-14 adds a second coordinator workflow: deciding a request,
  on top of viewing it.
- **Pre-conditions:** The centralized role policy is loaded.
- **Steps:** Read the `event_coordinator` permission set.
- **Test data:** `event_coordinator`.
- **Expected:** Exactly `dashboard:view`, `events:view_assigned`, and
  `events:decide`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_event_coordinator_has_the_view_and_decide_permissions`

## TC-EVENTS-058 — coordinator lists only their assigned events

- **Scenario:** `GET /events/assigned` is scoped to the authenticated
  coordinator, the same shape as the organiser's `GET /events`.
- **Pre-conditions:** A verified `event_coordinator` session; the
  assignment-filtered query returns one submitted event assigned to them.
- **Steps:** `GET /events/assigned`; inspect the query filter.
- **Test data:** One event assigned to `COORDINATOR_A`.
- **Expected:** `200`; one row, `assigned_coordinator_id` matches the caller;
  the query filters `eq("assigned_coordinator_id", <caller id>)`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_lists_only_their_assigned_events`

## TC-EVENTS-059 — a coordinator cannot view an event not assigned to them

- **Scenario:** Knowing an event's id does not expose it to an uninvolved
  coordinator — the same ownership principle as the organiser's routes.
- **Pre-conditions:** A verified `event_coordinator` session; the
  assignment-filtered lookup returns no rows.
- **Steps:** `GET /events/assigned/{event_id}`.
- **Test data:** An event id not assigned to the caller.
- **Expected:** `404` `"Event not found"`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_cannot_view_an_event_not_assigned_to_them`

## TC-EVENTS-060 — an organiser cannot list assigned events

- **Scenario:** `events:view_assigned` is coordinator-only.
- **Pre-conditions:** A verified `event_organiser` session.
- **Steps:** `GET /events/assigned`.
- **Test data:** None.
- **Expected:** `403`; Supabase is never queried.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_organiser_cannot_list_assigned_events`

## TC-EVENTS-061 — a coordinator can view one assigned event

- **Scenario:** The single-event counterpart to TC-EVENTS-058.
- **Pre-conditions:** A verified `event_coordinator` session; the
  assignment-filtered lookup returns the event.
- **Steps:** `GET /events/assigned/{event_id}`.
- **Test data:** An event assigned to `COORDINATOR_A`.
- **Expected:** `200`; `assigned_coordinator_id` matches the caller.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_views_one_assigned_event`

---

**Follow-up (same session).** Assignment was never rechecked on edit: a
submitted event's date/time could be changed via the public `PATCH` without
touching `assigned_coordinator_id` at all, even into a window the assigned
coordinator no longer had free. `event_requests` needs two things from this
service to fix that: a way to exclude an event's own row when checking
conflicts, and a trusted way to write a date/time change and a reassignment
in one update.

## TC-EVENTS-062 — coordinator load excludes the given event from conflict and count

- **Scenario:** Rechecking an event that already carries this exact window
  and assignment must not have it conflict with itself.
- **Pre-conditions:** The coordinator has one assigned submitted event —
  the same one being rechecked — covering the requested window exactly.
- **Steps:** `POST /events/coordinator-load` with `exclude_event_id` set to
  that event's id.
- **Test data:** One event, `id` equal to `exclude_event_id`.
- **Expected:** `200`; `conflict: false, assigned_count: 0` — without
  `exclude_event_id` this would conflict with itself.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_load_excludes_the_given_event_from_conflict_and_count`

## TC-EVENTS-063 — internal update reassigns the coordinator

- **Scenario:** The composite's edit-recheck flow writes the date/time
  change and the new assignment together.
- **Pre-conditions:** An owned submitted event assigned to one coordinator.
- **Steps:** `PATCH /events/{event_id}/internal` with `organiser_id`, a
  changed `start_time`, and a different `assigned_coordinator_id`.
- **Test data:** `start_time` changed to `20:00`; a second coordinator's id.
- **Expected:** `200`; the update sent to Supabase contains the new
  `start_time`, the new `assigned_coordinator_id`, and no `organiser_id`
  (that field only selects the row, it is never a column value).
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_update_reassigns_the_coordinator`

## TC-EVENTS-064 — internal update without reassignment leaves the coordinator untouched

- **Scenario:** When the composite does not include
  `assigned_coordinator_id` (nothing needed rechecking), the update touches
  only the fields actually supplied.
- **Pre-conditions:** An owned submitted event.
- **Steps:** `PATCH /events/{event_id}/internal` with `organiser_id` and
  `venue` only.
- **Test data:** `{"organiser_id": ..., "venue": "Room 9"}`.
- **Expected:** `200`; the update sent to Supabase is exactly
  `{"venue": "Room 9"}` — no `assigned_coordinator_id` key at all, not even
  null.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_update_without_reassignment_leaves_coordinator_untouched`

## TC-EVENTS-065 — internal update enforces ownership

- **Scenario:** A caller-supplied `organiser_id` does not bypass ownership —
  the same guarantee as every other internal route.
- **Pre-conditions:** The owned lookup for the given organiser id returns
  nothing.
- **Steps:** `PATCH /events/{event_id}/internal` with an organiser id that
  does not own the event.
- **Test data:** A non-owning organiser id.
- **Expected:** `404`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_update_enforces_ownership`

## TC-EVENTS-066 — internal update validates the resulting submitted event

- **Scenario:** Revised for S-36: `venue` is now an optional preference, so `name` stands in as the required field. The internal route is validated exactly as strictly as the
  public one — a caller-supplied `organiser_id` is not a way to bypass the
  submitted-required rules.
- **Pre-conditions:** An owned submitted event.
- **Steps:** `PATCH /events/{event_id}/internal` clearing `name`.
- **Test data:** `{"organiser_id": ..., "name": ""}`.
- **Expected:** `422`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_update_validates_the_resulting_submitted_event`

---

**S-14 additions.** An Event Coordinator can now record one of three
decisions — approve, reject, or return for amendment — on a request assigned
to them. Reject and return both require a reason; return alone may also
carry a clarification/amendment comment. A rejected request is closed
permanently (no further edits, no resubmission); a returned one goes back to
the organiser to edit and resubmit as the same record, which reuses the
submit route rather than creating a new one.

## TC-EVENTS-067 — a coordinator accepting a request moves it into planning

- **Scenario:** Approval needs no reason. The decision is recorded as
  `approved`, and the event moves to `planning`: it has passed the
  coordinator's check and venue and equipment planning can start. Revised
  for S-36, where the status was previously `approved`.
- **Pre-conditions:** A verified `event_coordinator` session; the assigned,
  submitted event exists.
- **Steps:** `POST /events/{event_id}/decision` with `{"decision":
  "approved"}`.
- **Test data:** The standard submitted payload, assigned to the caller.
- **Expected:** `200`; `status=planning`. The update sent to Supabase has
  `status=planning`, `decision=approved`, `decision_reason=null`,
  `decision_comment=null`, and a non-null `decided_at`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_approves_a_submitted_request`

## TC-EVENTS-068 — reject requires a reason

- **Scenario:** The story is explicit: every reject needs a reason before it
  can be saved.
- **Pre-conditions:** A verified `event_coordinator` session.
- **Steps:** `POST /events/{event_id}/decision` with `{"decision":
  "rejected"}` and no `reason`.
- **Test data:** As above.
- **Expected:** `422`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_reject_requires_a_reason`

## TC-EVENTS-069 — coordinator rejects with a reason

- **Pre-conditions:** A verified `event_coordinator` session; the assigned,
  submitted event exists.
- **Steps:** `POST /events/{event_id}/decision` with `{"decision":
  "rejected", "reason": "Venue unavailable"}`.
- **Test data:** As above.
- **Expected:** `200`; `status=rejected`; `decision_reason` echoes the given
  reason.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_rejects_with_a_reason`

## TC-EVENTS-070 — coordinator returns with a reason and comment

- **Scenario:** Return is the one decision that may also carry a
  clarification/amendment comment for the organiser.
- **Pre-conditions:** A verified `event_coordinator` session; the assigned,
  submitted event exists.
- **Steps:** `POST /events/{event_id}/decision` with `decision=returned`,
  a `reason`, and a `comment`.
- **Test data:** `reason="Missing risk assessment"`,
  `comment="Please attach the venue's fire safety form"`.
- **Expected:** `200`; `status=returned`; both `decision_reason` and
  `decision_comment` echo what was sent.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_returns_with_a_reason_and_comment`

## TC-EVENTS-071 — return requires a reason

- **Pre-conditions:** A verified `event_coordinator` session.
- **Steps:** `POST /events/{event_id}/decision` with `decision=returned` and
  a `comment` but no `reason`.
- **Test data:** `comment="please fix the venue"`.
- **Expected:** `422`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_return_requires_a_reason`

## TC-EVENTS-072 — approve rejects a reason

- **Scenario:** An approval is not a judgement call that needs defending —
  a `reason` alongside `decision=approved` is a validation error, not a
  silently-ignored extra field.
- **Pre-conditions:** A verified `event_coordinator` session.
- **Steps:** `POST /events/{event_id}/decision` with `decision=approved` and
  a `reason`.
- **Test data:** `reason="looks fine"`.
- **Expected:** `422`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_approve_rejects_a_reason`

## TC-EVENTS-073 — comment is rejected outside a return

- **Scenario:** A comment only makes sense alongside a return — there is
  nothing to amend after an approval or a closed rejection.
- **Pre-conditions:** A verified `event_coordinator` session.
- **Steps:** `POST /events/{event_id}/decision` with `decision=rejected`, a
  `reason`, and a `comment`.
- **Test data:** `reason="no venue"`, `comment="extra note"`.
- **Expected:** `422`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_comment_is_rejected_outside_a_return`

## TC-EVENTS-074 — a coordinator cannot decide an event not assigned to them

- **Scenario:** Same ownership principle as an organiser's own routes,
  applied to the coordinator side.
- **Pre-conditions:** A verified `event_coordinator` session; the
  assignment-filtered lookup returns no rows.
- **Steps:** `POST /events/{event_id}/decision` with `{"decision":
  "approved"}`.
- **Test data:** An event id not assigned to the caller.
- **Expected:** `404` `"Event not found"`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_coordinator_cannot_decide_an_event_not_assigned_to_them`

## TC-EVENTS-075 — a decision already made cannot be decided again

- **Pre-conditions:** A verified `event_coordinator` session; the assigned
  event is already `status=planning`, `decision=approved`. Revised for S-36.
- **Steps:** `POST /events/{event_id}/decision` with `{"decision":
  "approved"}`.
- **Test data:** As above.
- **Expected:** `409`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_decision_already_made_cannot_be_decided_again`

## TC-EVENTS-076 — an organiser cannot decide a request

- **Pre-conditions:** A verified `event_organiser` session.
- **Steps:** `POST /events/{event_id}/decision` with `{"decision":
  "approved"}`.
- **Test data:** None.
- **Expected:** `403`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_an_organiser_cannot_decide_a_request`

## TC-EVENTS-077 — a returned request can be resubmitted

- **Scenario:** The story requires a returned request to go back to the
  organiser to edit and resubmit as the same record — this proves the
  transition and that the prior decision is cleared, not carried forward.
- **Pre-conditions:** An owned event with `status=returned` and a recorded
  reason.
- **Steps:** `POST /events/{event_id}/submit` with the standard submitted
  payload.
- **Test data:** As above.
- **Expected:** `200`; `status=submitted`; the update sent to Supabase has
  `decision`, `decision_reason`, `decision_comment`, and `decided_at` all
  `null`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_returned_request_can_be_resubmitted`

## TC-EVENTS-078 — a request in planning cannot be resubmitted

- **Pre-conditions:** An owned event with `status=planning`,
  `decision=approved`. Revised for S-36, where the status was previously
  `approved`.
- **Steps:** `POST /events/{event_id}/submit` with the standard submitted
  payload.
- **Test data:** As above.
- **Expected:** `409`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_planning_request_cannot_be_resubmitted`

## TC-EVENTS-079 — a rejected request cannot be resubmitted

- **Scenario:** The story is explicit: a rejected request is closed
  permanently and cannot be resubmitted.
- **Pre-conditions:** An owned event with `status=rejected`.
- **Steps:** `POST /events/{event_id}/submit` with the standard submitted
  payload.
- **Test data:** As above.
- **Expected:** `409`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_rejected_request_cannot_be_resubmitted`

## TC-EVENTS-080 — a rejected event cannot be edited

- **Pre-conditions:** An owned event with `status=rejected`.
- **Steps:** `PATCH /events/{event_id}` with any field.
- **Test data:** `{"venue": "New Venue"}`.
- **Expected:** `409`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_rejected_event_cannot_be_edited`

## TC-EVENTS-081 — the internal update route also blocks a rejected event

- **Scenario:** The same permanence guarantee holds for the composite's
  edit-recheck path, not only the public route.
- **Pre-conditions:** An owned event with `status=rejected`.
- **Steps:** `PATCH /events/{event_id}/internal` with any field.
- **Test data:** `{"organiser_id": ..., "venue": "New Venue"}`.
- **Expected:** `409`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_update_also_blocks_a_rejected_event`

## TC-EVENTS-082 — editing a returned event still requires submitted fields

- **Scenario:** Revised for S-36: `venue` is now an optional preference, so `name` stands in as the required field. A returned request is not treated as a permissive draft on
  edit — the same strict validation as a submitted or approved event
  applies, since every required field already exists and resubmission
  expects them to stay that way.
- **Pre-conditions:** An owned event with `status=returned`.
- **Steps:** `PATCH /events/{event_id}` clearing `name`.
- **Test data:** `{"name": ""}`.
- **Expected:** `422`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_editing_a_returned_event_still_requires_submitted_fields`

## S-13 — the organiser responds to a return

TC-EVENTS-077 and TC-EVENTS-082 already prove a returned request can be
resubmitted and that editing one keeps the submitted-field rules. The cases
below cover what S-13's acceptance criteria add: the organiser can read what
was asked, can save an amendment without losing that request, the response
lands on the same record, and a failed resubmission leaves the record alone.

## TC-EVENTS-083 — the organiser can read the coordinator's return reason and comment

- **Scenario:** The organiser's own read of a returned event carries what the
  coordinator asked for (S-13 AC1).
- **Pre-conditions:** The fake returns one event owned by the signed-in
  organiser with `status=returned`, `decision=returned`, a reason, a comment
  and `decided_at` set.
- **Steps:** `GET /events/{event_id}` as that organiser.
- **Test data:** `decision_reason="Expected attendance exceeds the venue's capacity"`,
  `decision_comment="Reduce attendance to 80 or choose a larger venue"`,
  `decided_at="2026-09-20T10:00:00+00:00"`.
- **Expected:** `200`; the body has `status="returned"`, `decision="returned"`,
  and those exact `decision_reason`, `decision_comment` and `decided_at` values.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_organiser_can_read_the_return_reason_and_comment`

## TC-EVENTS-084 — saving an amendment to a returned event keeps it returned

- **Scenario:** The organiser can save an edit before resubmitting without the
  edit clearing the return or its reason (S-13 AC2).
- **Pre-conditions:** An owned event with `status=returned`, a reason and a
  comment; the fake's update echoes the merged row.
- **Steps:** `PATCH /events/{event_id}` with a valid change.
- **Test data:** `{"expected_attendance": 80}` (was `120`).
- **Expected:** `200`; the update sent to Supabase is exactly
  `{"expected_attendance": 80}`: it sets no `status`, `decision`,
  `decision_reason`, `decision_comment` or `decided_at`; the response still
  has `status="returned"`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_saving_an_amendment_to_a_returned_event_keeps_it_returned`

## TC-EVENTS-085 — resubmission updates the original record, never inserts one

- **Scenario:** The response stays attached to the original event request
  (S-13 AC4).
- **Pre-conditions:** An owned event with `status=returned` and id
  `EVENT_ID`.
- **Steps:** `POST /events/{EVENT_ID}/submit` with the standard submitted
  payload, amended.
- **Test data:** Standard submitted payload with `expected_attendance=80`.
- **Expected:** `200`; the response `id` equals `EVENT_ID`; exactly one
  `update(...)` is issued, filtered by `id=EVENT_ID`, the organiser's id, and
  `status in (draft, returned)`; the update carries `expected_attendance=80`;
  `insert` is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_resubmission_updates_the_original_record_and_never_inserts`

## TC-EVENTS-086 — a resubmission that loses a race changes nothing and says so

- **Scenario:** If the event stops being `returned` between the read and the
  write (for example, resubmitted from another tab), the status-guarded write
  matches nothing and the organiser is told (S-13 AC6).
- **Pre-conditions:** The first read returns an owned event with
  `status=returned`; the guarded update returns no rows.
- **Steps:** `POST /events/{event_id}/submit` with the standard submitted
  payload.
- **Test data:** As above.
- **Expected:** `409`; `detail` is
  `"This request is no longer awaiting changes. Reload to see its current status."`;
  no second write is attempted.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_resubmission_that_loses_a_race_changes_nothing_and_says_so`

## TC-EVENTS-087 — a storage failure during resubmission is reported, not swallowed

- **Scenario:** A Supabase error on the resubmission write reaches the
  organiser as a failure rather than a false success (S-13 AC6).
- **Pre-conditions:** An owned event with `status=returned`; the fake's
  update `.execute()` raises.
- **Steps:** `POST /events/{event_id}/submit` with the standard submitted
  payload.
- **Test data:** As above.
- **Expected:** `500` with the service's generic storage-failure detail; the
  response contains no event body; no second write is attempted.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_storage_failure_during_resubmission_is_reported`

---

**S-36 additions.** `approved` is no longer an event status. A
coordinator's approval moves an event to `planning` (TC-EVENTS-067), which is
where venue booking requests are made.

## TC-EVENTS-088 — approved is no longer a status an event can be read in

- **Scenario:** The status set matches the agreed flow: `draft`,
  `submitted`, `returned`, `rejected`, `planning`. A leftover `approved`
  status is a failure, not something silently shown.
- **Pre-conditions:** A verified `event_organiser` session.
- **Steps:** 1. `GET /events/{event_id}` where the owned row has
  `status=planning`, `decision=approved`. 2. Validate
  `EventRead` against a row with `status=approved`.
- **Test data:** The standard submitted payload.
- **Expected:** Step 1 returns `200` with `status=planning` and
  `decision=approved`. Step 2 raises a validation error on `status`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_approved_is_no_longer_a_status_an_event_can_be_read_in`

---

**S-36 venue requirements.** The organiser no longer names a venue; the
Coordinator books one. What the organiser gives instead is what the venue
has to offer: a room layout, facilities and accessibility features, chosen
from the venue catalogue's fixed sets so each venue can be checked against
them. All three are optional. The old free-text `venue` stays as an optional
preference.

Shared test data for these cases: the standard submitted payload, plus
`room_layout: "theatre"`, `required_facilities: ["projector", "stage"]`,
`required_accessibility: ["wheelchair_access"]`.

## TC-EVENTS-089 — the venue preference is optional on submission

- **Pre-conditions:** None.
- **Steps:** Instantiate `EventSubmittedCreate` without `venue`, then with
  `venue: "   "`.
- **Test data:** The standard submitted payload.
- **Expected:** Both are valid; `venue` is `None` both times.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_the_venue_preference_is_optional_on_submission`

## TC-EVENTS-090 — the venue requirements are accepted and tidied

- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` and `EventSubmittedCreate` with
  the shared requirements, with `projector` listed twice.
- **Test data:** `required_facilities: ["projector", "stage", "projector"]`.
- **Expected:** Both valid. `room_layout` is `"theatre"`,
  `required_facilities` is `["projector", "stage"]`,
  `required_accessibility` is `["wheelchair_access"]`.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_the_venue_requirements_are_accepted_and_tidied`

## TC-EVENTS-091 — the venue requirements default to none

- **Pre-conditions:** None.
- **Steps:** Instantiate `EventSubmittedCreate` from the standard payload,
  which has none of the three fields.
- **Test data:** As above.
- **Expected:** Valid; `room_layout` is `None`, `required_facilities` and
  `required_accessibility` are `[]`.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_the_venue_requirements_default_to_none`

## TC-EVENTS-092 — only values from the venue catalogue are accepted

- **Scenario:** The same fixed sets as the venues service, so an event can be
  compared with a venue.
- **Pre-conditions:** A verified `event_organiser` session.
- **Steps:** `POST /events/drafts` three times, each with one value outside
  its set.
- **Test data:** `room_layout: "ballroom"`; `required_facilities:
  ["jacuzzi"]`; `required_accessibility: ["ramp"]`.
- **Expected:** `422` each time, naming the field; nothing inserted.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_values_from_the_venue_catalogue_are_accepted`

## TC-EVENTS-093 — the venue requirements are stored and read back

- **Pre-conditions:** A verified `event_organiser` session; the fake's insert
  returns the inserted row.
- **Steps:** `POST /events` with the standard payload plus the shared
  requirements and no `venue`.
- **Test data:** As above.
- **Expected:** `201`. The insert sent to Supabase carries `room_layout`,
  `required_facilities` and `required_accessibility` as given and
  `venue=null`; the response includes all four.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_venue_requirements_are_stored_and_read_back`

## TC-EVENTS-094 — organisers get the option lists from the events service

- **Scenario:** Organisers cannot view venues, so the events service serves
  the three option sets for their form.
- **Pre-conditions:** A verified session for each role in turn.
- **Steps:** `GET /events/options`.
- **Test data:** Roles `event_organiser`, then `event_coordinator`,
  `venue_staff`, `technical_support`, `attendee`.
- **Expected:** `event_organiser`: `200` with `room_layouts`, `facilities` and
  `accessibility`, each exactly the venue catalogue's set in its order. Every
  other role: `403`.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_organisers_get_the_option_lists`, `test_app.py::test_other_roles_cannot_get_the_option_lists`

---

## S-43 — Auto-Assign Technical Support

The event owns four new current-state fields:
`technical_support_required`, `technical_support_details`, and
`assigned_technical_support_id`, plus server-managed
`technical_support_assigned_at`. The user id is opaque; there is no
cross-schema foreign key. The composite, not this atomic service, chooses the
staff member.

## TC-EVENTS-095 — support assignment fields are server-managed event state

- **Scenario:** Organisers cannot request support or choose an assigned staff
  member through draft/submission payloads.
- **Pre-conditions:** Standard event schemas.
- **Steps:** Validate each organiser payload with, in turn,
  `technical_support_required`, `technical_support_details`, and
  `assigned_technical_support_id`, and `technical_support_assigned_at`;
  validate an event read containing their stored values.
- **Expected:** Every organiser payload is rejected as extra input. Event reads
  expose `false/null/null/null` by default and stored support state when
  present. `confirmed` is a readable status, but S-43 creates no status
  transition into it.
- **Actual:** All four fields were rejected from organiser payloads and accepted in stored event reads; `confirmed` parsed successfully.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_support_assignment_fields_are_server_managed`

## TC-EVENTS-096 — only planning and confirmed assignments contribute to support load

- **Scenario:** Availability ignores events that do not occupy Technical
  Support Staff under the confirmed S-43 rule.
- **Pre-conditions:** The fake returns assignments for all supported lifecycle
  labels.
- **Steps:** `POST /events/technical-support-load` with two staff ids and a
  requested window.
- **Test data:** Assigned events in `planning`, `confirmed`, `draft`,
  `submitted`, `returned`, `rejected`, `completed`, and `cancelled`.
- **Expected:** The storage query requests only `planning` and `confirmed`.
  Only those rows contribute to `assigned_count` or an overlap conflict;
  submitted/under-review does not block availability.
- **Actual:** The query and response included only planning and confirmed assignments.
- **Status:** Pass
- **Evidence:** `test_app.py::test_support_load_counts_only_planning_and_confirmed_events`

## TC-EVENTS-097 — support overlap uses the complete date/time window

- **Scenario:** Any real overlap makes a staff member unavailable, while
  back-to-back events remain valid.
- **Pre-conditions:** One staff member has stored planning assignments.
- **Steps:** Check containment, partial overlap, cross-midnight overlap, and
  both touching-boundary directions.
- **Test data:** Requested window `2026-11-13 09:00`–`12:00`, plus the windows
  described above.
- **Expected:** Every positive-duration overlap reports `conflict=true`.
  An assignment ending at `09:00` or starting at `12:00` does not conflict.
- **Actual:** Every real overlap conflicted and both touching-boundary cases remained available.
- **Status:** Pass
- **Evidence:** `test_app.py::test_support_load_detects_overlap`, `test_app.py::test_support_load_allows_back_to_back_events`

## TC-EVENTS-098 — support load reports each candidate's live workload

- **Scenario:** The composite can implement least-busy selection without
  reading event storage itself.
- **Pre-conditions:** Candidates A, B, and C have respectively two, one, and
  zero planning/confirmed assignments; none overlaps the requested window.
- **Steps:** Request support load for A, B, and C.
- **Expected:** The response keeps all requested ids and reports counts
  `2`, `1`, and `0`, with `conflict=false` for each.
- **Actual:** Every requested candidate was returned with the expected live count and conflict flag.
- **Status:** Pass
- **Evidence:** `test_app.py::test_support_load_reports_each_candidates_live_workload`

## TC-EVENTS-099 — the internal action records support need and assignment atomically

- **Scenario:** A verified composite write changes only S-43 event state.
- **Pre-conditions:** A planning event assigned to Coordinator A; the internal
  payload supplies Coordinator A, optional normalized details, and Staff B.
- **Steps:** `PUT /events/{id}/technical-support/internal`.
- **Expected:** The update is guarded by event id, `status="planning"`, and
  `assigned_coordinator_id=A`; it sets required true, details, and Staff B in
  one update and sets `technical_support_assigned_at` server-side. Dates,
  event coordinator, equipment requirements, and other event fields are
  unchanged.
- **Actual:** The guarded update changed only the four S-43 fields and generated the first-assignment timestamp.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_support_action_records_requirement_and_assignment`

## TC-EVENTS-100 — a required event may remain honestly unassigned

- **Scenario:** No available staff does not create a false assignment or lose
  the Coordinator's explicit support requirement.
- **Pre-conditions:** The same planning event; the composite supplies no staff
  id.
- **Steps:** Call the internal support action with details and
  `assigned_technical_support_id=null`.
- **Expected:** `200`; required becomes true and details persist, while the
  assignment and assignment timestamp stay null. No placeholder user id is
  stored.
- **Actual:** Required and details were stored while both assignment fields remained null.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_support_action_preserves_unassigned_requirement`

## TC-EVENTS-113 — stale or failed support writes never report success

> **Renumbered 2026-10-08 from TC-EVENTS-101, which the integration suite had used first (TC-EVENTS-101, draft-to-submission round trip).**

- **Scenario:** The target must still be the same Coordinator's planning event
  when the atomic write happens.
- **Pre-conditions:** In turn, the conditional update returns no row for target
  statuses `draft`, `submitted`, `returned`, `rejected`, `confirmed`,
  `completed`, and `cancelled`, for reassignment to another Coordinator, or
  raises a storage exception.
- **Steps:** Attempt the internal support action in every case.
- **Expected:** Every stale/non-planning or ownership case returns `409` and
  changes nothing. Storage failure returns the normal safe `500` without
  internal details.
- **Actual:** Every stale target returned `409`; the simulated storage failure returned the safe `500` response.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_support_action_requires_current_planning_assignment`, `test_app.py::test_internal_support_action_storage_failure_is_safe`

---

## S-44 — check equipment availability

Story: S-44 Check equipment availability.
Confirmed by the developer on 2026-09-30. Not yet executed.
A new composite-only route, `POST /events/overlapping`, like
`/events/coordinator-load`: no Kong route. IDs continue from the next unused
number, as agreed with the developer on 2026-09-30 (this file's 001–099 range
is full).

## TC-EVENTS-105 — overlapping planning and confirmed events are returned

- **Scenario:** The events that can reserve equipment for a window (S-44 AC2).
- **Pre-conditions:** The fake returns, for statuses `planning` and
  `confirmed`: E1 `planning` 2026-11-12 10:00–11:00; E2 `confirmed`
  11:30–13:00; E4 `planning` 12:00–14:00; E5 `planning` 2026-11-11 18:00 →
  2026-11-12 09:30; E6 `confirmed` 2026-11-12 07:00–09:00.
- **Steps:** `POST /events/overlapping` with
  `{"start_date":"2026-11-12","start_time":"09:00","end_date":"2026-11-12","end_time":"12:00"}`.
- **Expected:** `200` with E5, E1, E2 in start order, each with `id`, `name`,
  `status`, `start_date`, `start_time`, `end_date`, `end_time`. E4 (starts as
  the window ends) and E6 (ends as it starts) are back-to-back and left out.
  The query filters `status in (planning, confirmed)`.
- **Actual:** E5, E1, E2 returned in start order with the seven fields; back-to-back E4 and E6 left out; the query filtered status in (planning, confirmed) with a coarse date range.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_overlapping.py::test_overlapping_planning_and_confirmed_events_are_returned_in_start_order`

## TC-EVENTS-106 — other statuses never reserve

- **Scenario:** Rejected, returned, draft and submitted events hold nothing.
- **Steps:** Inspect the storage query from TC-EVENTS-105.
- **Expected:** Only `planning` and `confirmed` are requested, so an
  overlapping `rejected`, `returned`, `draft` or `submitted` event is never
  returned.
- **Actual:** Only planning and confirmed were requested.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_overlapping.py::test_only_planning_and_confirmed_events_are_asked_for`

## TC-EVENTS-107 — an invalid window is refused

- **Steps:** Post an end equal to the start, an end before the start, and a
  body missing `end_time`.
- **Expected:** Each `422` with a field error; storage is not queried.
- **Actual:** Equal end, earlier end date and missing end_time each returned `422` without querying storage.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_overlapping.py::test_an_invalid_window_is_refused`

---

## S-43 — assigned-event visibility for Technical Support

Story: S-43 Auto-Assign Technical Support.
Specification updated by the developer on 2026-10-05. Active means
`planning` or `confirmed`; inactive assignments are not shown.

## TC-EVENTS-109 — Technical Support lists only their active assigned events

- **Scenario:** A Technical Support staff member sees the active events they
  personally support and no other staff member's assignments.
- **Pre-conditions:** The authenticated user is Technical Support A. Storage
  contains A's planning event, A's confirmed event, A's cancelled event, B's
  planning event, and an unassigned planning event.
- **Steps:** `GET /events/support-assigned`.
- **Test data:** Staff A and B UUIDs; the five events above with distinct
  names and update times.
- **Expected:** `200`; only A's planning and confirmed events are returned,
  newest update first. The storage query filters
  `assigned_technical_support_id=A` and status in `planning,confirmed`.
- **Actual:** The list returned only A's planning and confirmed fixtures in
  service order, and the mocked Supabase chain received both ownership and
  active-status predicates before sorting by `updated_at` descending.
- **Status:** Pass
- **Evidence:** `test_support_assignments.py::test_technical_support_lists_only_its_active_assigned_events`

## TC-EVENTS-110 — one support assignment cannot be read by another staff member

- **Scenario:** Assignment visibility is enforced by the events service, not
  by hiding a dashboard row.
- **Pre-conditions:** Event A is active and assigned to Technical Support A;
  Event B is active and assigned to B; Event C is cancelled and still stores
  A's historical assignment.
- **Steps:** As A, request each event at
  `GET /events/support-assigned/{event_id}`.
- **Test data:** Event A, B, and C UUIDs.
- **Expected:** Event A returns `200` with its event details. Event B and
  inactive Event C each return `404` without revealing their details.
- **Actual:** A's active assignment returned `200`; the assignment/status
  filtered empty result used for another worker, a cancelled assignment, and
  a missing event returned the same `404` response.
- **Status:** Pass
- **Evidence:** `test_support_assignments.py::test_support_worker_reads_one_active_event_assigned_to_them`; `test_support_assignments.py::test_support_worker_cannot_read_unassigned_or_inactive_event`

## TC-EVENTS-111 — support-assignment routes require the trusted role

- **Scenario:** An assignment UUID alone never grants event visibility.
- **Pre-conditions:** The target is an active event assigned to Technical
  Support A.
- **Steps:** Call both support-assignment routes as Coordinator, Organiser,
  Venue Staff, Attendee, an unknown role, and with no session.
- **Test data:** All listed roles and Event A's UUID.
- **Expected:** Every authenticated non-Technical-Support role receives `403`;
  no session receives `401`; storage is not queried after a role failure.
- **Actual:** Both routes returned `403` for every listed non-support role and
  `401` without a session; no rejected request reached the database mock.
- **Status:** Pass
- **Evidence:** `test_support_assignments.py::test_support_assignment_routes_reject_other_roles`; `test_support_assignments.py::test_support_assignment_routes_require_a_session`

---

## S-83 — unassigned queue and atomic assignment state

Story: S-83 Assign Event Requests from Unassigned Queue. Acceptance criteria
confirmed by the developer on 2026-10-08. Executed on the confirmed branch in
the full unit run on 2026-10-08.

## TC-EVENTS-112 — internal creation permits an unassigned submitted request

> **Renumbered 2026-10-08 from TC-EVENTS-108, which S-44 had already used for an integration case.**

- **Scenario:** The events service persists the new S-83 initial state.
- **Pre-conditions:** The fake insert returns the submitted event.
- **Steps:** `POST /events/internal` with complete event and organiser data but
  no coordinator id.
- **Test data:** Event `Autumn Forum`; organiser
  `11111111-1111-4111-8111-111111111111`.
- **Expected:** `201`; the inserted row is `submitted`, has a non-null
  `submitted_at`, and has `assigned_coordinator_id=null`.
- **Actual:** The internal insert stored `submitted`, a timestamp, and a null Coordinator.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_submission_can_start_unassigned`

## TC-EVENTS-114 — the internal queue contains only submitted unassigned events

> **Renumbered 2026-10-08 from TC-EVENTS-109, which S-43 had already used on `main`.**

- **Scenario:** Queue membership is determined by event state, not by the
  caller's UI filtering.
- **Pre-conditions:** Storage contains an unassigned submission, an assigned
  submission, a draft, a returned event, and a planning event.
- **Steps:** `GET /internal/events/unassigned`.
- **Test data:** Five rows with the states above.
- **Expected:** `200` with only the unassigned submitted row, ordered by
  `submitted_at` oldest first; the storage query filters `status=submitted`
  and `assigned_coordinator_id is null` and selects the agreed basic fields.
- **Actual:** The storage query applied both filters and oldest-first ordering.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_unassigned_queue_filters_and_orders_in_storage`

## TC-EVENTS-115 — assignment is conditional and idempotent for the same coordinator

> **Renumbered 2026-10-08 from TC-EVENTS-110, which S-43 had already used on `main`.**

- **Scenario:** A Lead's valid assignment changes one event without allowing a
  stale second owner.
- **Pre-conditions:** The first conditional update returns the submitted event
  assigned to coordinator A. A repeated request for A reads that same row.
- **Steps:** `POST /internal/events/{event_id}/assignment` twice with A.
- **Test data:** Shared event and coordinator A UUIDs.
- **Expected:** Both responses are `200`; the first response reports
  `assignment_created=true`, the retry `false`. The write is filtered by id,
  `status=submitted`, and null coordinator; organiser id and event name are
  returned for notification creation.
- **Actual:** The first conditional write reported created; the same-target retry read the existing row and reported not created.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_assignment_is_conditional_and_same_target_idempotent`

## TC-EVENTS-116 — a missing, ineligible-state, or differently assigned event is rejected

> **Renumbered 2026-10-08 from TC-EVENTS-111, which S-43 had already used on `main`.**

- **Scenario:** The atomic service distinguishes missing state from a stale
  assignment without overwriting either.
- **Pre-conditions:** The conditional update matches no row; the follow-up
  read returns no event, a draft/returned event, or coordinator B in turn.
- **Steps:** Attempt assignment to coordinator A for every state.
- **Test data:** Unknown event; draft; returned; event assigned to B.
- **Expected:** Unknown returns `404`; wrong state and different existing
  owner return `409`; no unconditional update occurs.
- **Actual:** Missing returned `404`; draft, returned, planning, and a different existing owner returned `409` without overwrite.
- **Status:** Pass
- **Evidence:** `test_s83.py::test_internal_assignment_rejects_a_different_existing_owner`, `test_s83.py::test_internal_assignment_rejects_wrong_state_targets`, `test_s83.py::test_internal_assignment_returns_404_for_a_missing_event`

---

## S-84 — atomic coordinator reassignment

Story: S-84 Reassign Event Coordinator. Acceptance criteria and test cases
confirmed by the developer on 2026-10-08. Executed locally on 2026-10-09.

## TC-EVENTS-112 — active assigned events are listed for Lead orchestration

- **Scenario:** The atomic service supplies the assigned work that can be
  reassigned without making role or profile decisions.
- **Steps:** `GET /internal/events/assigned-active`.
- **Expected:** Storage selects assigned events in `submitted`, `planning`,
  `confirmed`, or `returned`, excludes null owners, and orders newest updates
  first. Draft, rejected, and cancelled rows cannot enter the result.
- **Actual:** The query used the four active statuses, excluded null owners,
  and ordered by newest update.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_internal_active_assignments_filter_status_owner_and_order`

## TC-EVENTS-113 — reassignment compare-and-set transfers an active event

- **Scenario:** A request based on the current owner and assignment version
  changes exactly one event without checking schedule conflicts.
- **Steps:** Reassign coordinator A at version 0 to B.
- **Expected:** `200`; B becomes owner, A is retained as the previous owner,
  version becomes 1, and `reassignment_created=true`. The write is conditional
  on id, active status, A, and version 0; no schedule query occurs.
- **Actual:** The conditional write transferred A to B, retained A as the
  previous owner, and incremented version 0 to 1 without an availability call.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_internal_reassignment_uses_versioned_compare_and_set`

## TC-EVENTS-114 — exact retry is idempotent but stale requests cannot revert a newer owner

- **Scenario:** Notification repair is safe even after later reassignment.
- **Steps:** Retry A/v0→B after it committed; then retry that request after a
  later B/v1→A transition.
- **Expected:** The first retry returns `200`, version 1 and
  `reassignment_created=false`; the stale retry returns `409` and performs no
  write. A request selecting the current owner without matching retry metadata
  also returns `409`.
- **Actual:** The exact retry returned the stored transition without a write;
  stale-version and same-owner requests returned `409`.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_internal_reassignment_retry_is_idempotent`, `test_s84.py::test_internal_reassignment_rejects_stale_or_same_owner_requests`

## TC-EVENTS-115 — missing and ineligible events are unchanged

- **Scenario:** Rejected, cancelled, draft, unassigned, and missing events are
  not reassignment targets.
- **Expected:** Missing returns `404`; every other invalid state returns `409`;
  no unconditional update occurs.
- **Actual:** Missing returned `404`; every ineligible or unassigned row
  returned `409` without an update.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_internal_reassignment_rejects_missing_ineligible_and_unassigned_events`

---

## S-85 — coordinator oversight event source

Story: S-85 View Coordinator Assignments and Active Events. Acceptance
criteria and test cases confirmed by the developer on 2026-10-09. Executed
locally on 2026-10-09.

## TC-EVENTS-117 — oversight lists exactly the five confirmed active statuses

- **Scenario:** The events service supplies the complete active assigned-event
  set without making role, profile, or grouping decisions.
- **Pre-conditions:** Supabase is mocked; the query returns one assigned event
  for each accepted status.
- **Steps:** `GET /internal/events/coordinator-overview` and inspect the
  storage query and response validation.
- **Test data:** `submitted`, `under_review`, `returned`, `planning`, and
  `confirmed` assigned to coordinator A.
- **Expected:** The query includes exactly those five statuses, excludes null
  `assigned_coordinator_id` values, orders newest updates first, and accepts
  all five statuses in the response contract.
- **Actual:** The response accepted one row in each confirmed status; storage
  received the exact five-status filter, excluded null owners, and ordered by
  descending update time.
- **Status:** Pass
- **Evidence:** `test_s85.py::test_internal_oversight_uses_all_five_active_statuses`

## TC-EVENTS-118 — oversight excludes unassigned and inactive events at storage

- **Scenario:** Draft, rejected, cancelled, completed, and unassigned events
  cannot enter the Lead's oversight source.
- **Pre-conditions:** Supabase is mocked.
- **Steps:** Inspect the filters used by
  `GET /internal/events/coordinator-overview`.
- **Test data:** The five inactive/unassigned states plus the five active
  states from TC-EVENTS-117.
- **Expected:** Filtering is performed by the atomic owner: only the five
  active statuses and non-null owners are selected. The route performs no
  write and no other-service call.
- **Actual:** The read query contained only the five active values and the
  non-null-owner filter; no insert, update, or delete operation was made.
- **Status:** Pass
- **Evidence:** `test_s85.py::test_internal_oversight_excludes_unassigned_and_inactive_events`

---

## S-86 — Operational Safety Check persistence

Story: S-86 Conduct Operational Safety Check. Acceptance criteria and test
cases confirmed by the developer on 2026-10-10. Executed locally on
2026-10-10.

## TC-EVENTS-119 — only confirmed undecided events enter the safety queue

- **Pre-conditions:** Supabase is mocked with one `confirmed` row whose
  `safety_decision` is null.
- **Steps:** `GET /internal/events/safety-review`; open missing, non-confirmed,
  and already-decided ids.
- **Expected:** Storage filters by `confirmed` and null decision, oldest update
  first. Missing is `404`; ineligible/already decided is `409`.
- **Actual:** The queue used both storage predicates and oldest-update order;
  missing returned `404`, while wrong state/current decision returned `409`.
- **Status:** Pass
- **Evidence:** `test_s86.py::test_safety_queue_selects_only_undecided_confirmed_events`; `test_s86.py::test_safety_detail_distinguishes_missing_from_ineligible`

## TC-EVENTS-120 — safety outcomes are distinct and audited

> **S-17 (2026-10-19):** approval now yields `confirmed`, not `preparation` — see TC-EVENTS-139.

- **Pre-conditions:** A confirmed event has no safety decision.
- **Steps:** Record approval, rejection with reason, and changes requested with
  reason, each as Safety Officer D.
- **Expected:** Status becomes `preparation`, `safety_rejected`, or, after the
  S-87 clarification, `planning`; decision, optional reason, D, a server time
  and an immutable history entry are stored together.
- **Actual:** All outcomes stored the required current fields and appended one
  history record; requested changes returned directly to `planning`.
- **Status:** Pass
- **Evidence:** `test_s86.py::test_safety_decision_records_audit_and_distinct_lifecycle_state`

## TC-EVENTS-121 — safety decision validation is strict

- **Steps:** Submit blank/missing reasons for rejection/change request, a
  reason with approval, and an unknown decision.
- **Expected:** Each returns `422` before storage. Approval requires no reason;
  the other two require a non-blank reason.
- **Actual:** Every invalid combination returned `422` before an update.
- **Status:** Pass
- **Evidence:** `test_s86.py::test_invalid_safety_decisions_are_rejected_before_storage`

## TC-EVENTS-122 — missing, stale, repeated and concurrent decisions do not overwrite

> **S-17 (2026-10-19):** the conditional write now requires `pending_safety_check`, not `confirmed` — see TC-EVENTS-139.

- **Pre-conditions:** Missing event; already-decided event; and a confirmed
  event whose compare-and-set loses a concurrent race.
- **Steps:** Attempt a safety decision in each state.
- **Expected:** Missing is `404`; every stale/repeated/racing attempt is `409`;
  the conditional write requires id, `confirmed`, and null safety decision.
- **Actual:** Missing returned `404`; stale and empty compare-and-set updates
  returned `409` without a second/unconditional write.
- **Status:** Pass
- **Evidence:** `test_s86.py::test_missing_event_is_404_and_stale_event_is_409_without_update`; `test_s86.py::test_empty_conditional_update_reports_concurrent_decision_without_overwrite`

## S-62 — request event cancellation

Story: S-62 Request Event Cancellation.
Confirmed by the developer on 2026-10-11.
A new organiser route, `POST /events/{id}/cancellation-request`, reached by the
browser through Kong at `/api/events/{id}/cancellation-request`. IDs continue
from the next unused number, as agreed on 2026-09-30 (this file's 001–099
range is full).

**Acceptance criteria → cases (all layers)**

| Acceptance criterion | Cases |
| --- | --- |
| AC1: The Organiser can start a cancellation request for an eligible event they may access | EVENTS-123, 124, 126, FRONTEND-104, E2E-233 |
| AC2: The Organiser must confirm the request before it is submitted | E2E-233 |
| AC3: A submitted request is kept with the event | EVENTS-123, 129, 130 |
| AC4: The Organiser is told the request was submitted | E2E-233 |
| AC5: Submitting does not show the event as cancelled | EVENTS-123, 130, FRONTEND-104, E2E-233 |
| AC6: If submission fails, the status is unchanged and the Organiser is told | EVENTS-127, 128, FRONTEND-105 |

Decisions agreed with the developer on 2026-10-11:

- **Eligible statuses:** `submitted`, `under_review`, `planning`, `confirmed`,
  `preparation`, `safety_changes_requested`. Not `draft`, `returned`,
  `rejected`, `cancelled` or `safety_rejected`.
- **Reason:** required free text, trimmed, 1–1000 characters.
- **Stored on the event** as `cancellation_reason`,
  `cancellation_requested_at` and `cancellation_requested_by` in
  `events.events`. One request per event; no history.
- **The event's status never changes** when a request is submitted.
- **A second request while one exists is refused** with `409`.
- **Out of scope:** reviewing, completing or withdrawing a request, and
  notifying anyone. Those are a later story.

**Shared test data.** Organiser O (`11111111-…`), event E (`33333333-…`)
owned by O, reason `"Keynote speaker withdrew and no replacement is available"`.

## TC-EVENTS-123 — the Organiser requests cancellation of an eligible event

- **Scenario:** A request is stored on the event and its status is unchanged
  (AC1, AC3, AC5).
- **Pre-conditions:** O signed in. The fake returns E, owned by O, with no
  cancellation request, in each eligible status in turn. The conditional
  update returns the row with the three fields set.
- **Steps:** `POST /events/E/cancellation-request` with the test data, once
  per eligible status.
- **Test data:** `{"reason": "  Keynote speaker withdrew and no replacement is available  "}`;
  statuses `submitted`, `under_review`, `planning`, `confirmed`,
  `preparation`, `safety_changes_requested`.
- **Expected:** `200` with the event, its `status` unchanged, and
  `cancellation_reason` set to the trimmed reason,
  `cancellation_requested_by` set to O, and `cancellation_requested_at` set.
  The update writes exactly those three fields, never `status`.
  `cancellation_requested_at` is a server time, never from the body. The
  update is guarded by id, `organiser_id` O, an eligible status, and
  `cancellation_requested_at` being null.
- **Actual:** Each of the six statuses returned `200` with the status unchanged and the trimmed reason, requester and time set; the update wrote only the three cancellation fields, guarded by id, organiser, eligible status and a null `cancellation_requested_at`.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s62.py::test_the_organiser_requests_cancellation_of_an_eligible_event`

## TC-EVENTS-124 — an event that is not eligible cannot have a request

- **Scenario:** Only live, submitted events can be asked to be cancelled
  (AC1).
- **Pre-conditions:** O signed in. The fake returns E, owned by O, in each
  ineligible status.
- **Steps:** `POST /events/E/cancellation-request` with a valid reason.
- **Test data:** statuses `draft`, `returned`, `rejected`, `cancelled`,
  `safety_rejected`.
- **Expected:** `409` "This event can't be cancelled from its current
  status." No update is made.
- **Actual:** Each ineligible status returned `409` "This event can't be cancelled from its current status." with no update.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s62.py::test_an_event_that_is_not_eligible_cannot_have_a_request`

## TC-EVENTS-125 — a missing, blank or too-long reason is refused

- **Scenario:** The reason is required (AC1).
- **Pre-conditions:** O signed in; E eligible.
- **Steps:** `POST /events/E/cancellation-request` with each body.
- **Test data:** `{}`; `{"reason": ""}`; `{"reason": "   "}`;
  `{"reason": "x" * 1001}`; `{"reason": "ok", "cancellation_requested_at": "2020-01-01T00:00:00Z"}`.
- **Expected:** `422` for each. The last is refused because extra fields are
  forbidden. No database call is made.
- **Actual:** All five bodies returned `422` before any database call.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s62.py::test_a_missing_blank_or_too_long_reason_is_refused`

## TC-EVENTS-126 — only the event's own Organiser can request its cancellation

- **Scenario:** The event must be one the Organiser may access (AC1).
- **Pre-conditions:** The owned-event lookup returns no row for another
  organiser's or a missing event.
- **Steps:** `POST /events/E/cancellation-request` with a valid reason as:
  1. no session;
  2. each of `event_coordinator`, `venue_staff`, `technical_support`,
     `attendee`;
  3. O, for an event owned by someone else;
  4. O, for a missing id.
- **Expected:** 1 → `401`; 2 → `403`; 3 and 4 → `404` "Event not found". No
  update in any case.
- **Actual:** No session `401`; the four other roles `403`; someone else's or a missing event `404` "Event not found"; no update in any case.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s62.py::test_no_session_is_401`; `tests/unit/atomic/events/test_s62.py::test_other_roles_are_403`; `tests/unit/atomic/events/test_s62.py::test_someone_elses_or_a_missing_event_is_404`

## TC-EVENTS-127 — a second request is refused and the first is kept

- **Scenario:** A request already exists, or one lands between the read and
  the write (AC6).
- **Pre-conditions:** O signed in.
  1. E is `planning` with `cancellation_requested_at` already set.
  2. E is `planning` with no request, but the conditional update matches
     nothing (another tab got there first).
- **Steps:** `POST /events/E/cancellation-request` with a valid reason.
- **Expected:** 1 → `409` "A cancellation request has already been sent for
  this event." with no update. 2 → `409` with the same detail and no second,
  unguarded write. In both cases the stored reason is untouched.
- **Actual:** An existing request returned `409` with no update; a lost race returned `409` after the one guarded write, with no retry.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s62.py::test_a_second_request_is_refused_and_the_first_kept`; `tests/unit/atomic/events/test_s62.py::test_a_request_that_loses_a_race_is_refused_without_overwriting`

## TC-EVENTS-128 — a storage failure leaves the event as it was

- **Scenario:** Submission fails and nothing is recorded (AC6).
- **Pre-conditions:** O signed in; E `planning`; the update raises.
- **Steps:** `POST /events/E/cancellation-request` with a valid reason.
- **Expected:** `500` "Event storage unavailable". The only write attempted
  was the guarded one, which never includes `status`.
- **Actual:** `500` "Event storage unavailable"; the one write attempted was the guarded one, without `status`.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s62.py::test_a_storage_failure_leaves_the_event_as_it_was`

## TC-EVENTS-129 — the request is returned with the event

- **Scenario:** A stored request is part of the event the Organiser reads
  (AC3).
- **Pre-conditions:** O signed in. The fake returns E `planning` with the
  three cancellation fields set, plus a second event with none.
- **Steps:** `GET /events/E`; `GET /events`.
- **Expected:** Both return E with `cancellation_reason`,
  `cancellation_requested_at` and `cancellation_requested_by` as stored,
  and `status` `planning`. The second event has all three as `null`.
- **Actual:** Both routes returned the three fields as stored with status `planning`; the other event had all three `null`.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s62.py::test_the_request_is_returned_with_the_event`
---

## S-87 — Return after safety changes and resubmit

Story: S-87 Return Event to Planning After Safety Changes Requested.
Acceptance criteria and test cases confirmed by the developer on 2026-10-10.
Executed locally on 2026-10-13 at commit `72886bb` in the full Python unit
run: 981 passed, 17 skipped.

## TC-EVENTS-130 — change request returns atomically to planning with history

- **Pre-conditions:** A confirmed, undecided event has existing venue,
  equipment and Technical Support arrangements.
- **Steps:** Record `changes_requested` with a reason and Safety Officer id.
- **Expected:** One conditional Events-row update changes the status to
  `planning`, sets the current safety feedback, and appends review 1 to
  `safety_review_history`. It does not update or clear any resource field.
- **Actual:** The single conditional update set planning/current feedback and
  appended review 1 without including any resource field in the update.
- **Status:** Pass
- **Evidence:** `test_s87.py::test_changes_requested_returns_to_planning_and_appends_immutable_history`

## TC-EVENTS-131 — returned safety work belongs to its current Coordinator

- **Pre-conditions:** A planning event is assigned to Coordinator A and its
  current safety decision is `changes_requested`.
- **Steps:** Read its returned-safety source as A and Coordinator B.
- **Expected:** A receives the event and complete review history; B receives
  `404` and no event data.
- **Actual:** Coordinator A received the complete row and history; B received
  `404` from the assignment-scoped lookup.
- **Status:** Pass
- **Evidence:** `test_s87.py::test_only_currently_assigned_coordinator_can_open_returned_safety_work`

## TC-EVENTS-132 — resubmission is limited to safety-returned planning events

> **S-17 (2026-10-19):** a `pending_safety_check` event is also ineligible; the general S-17 submission is TC-EVENTS-136.

- **Steps:** Attempt the S-87 action for an ordinary planning event, a
  confirmed event, and a planning event whose current decision is not
  `changes_requested`.
- **Expected:** Every attempt returns `409` before an update. This route does
  not become the general S-17 confirmation workflow.
- **Actual:** All three ineligible states returned `409` and made no update.
- **Status:** Pass
- **Evidence:** `test_s87.py::test_only_safety_returned_planning_event_can_be_resubmitted`

## TC-EVENTS-133 — resubmission preserves audit history and resources

> **S-17 (2026-10-19):** resubmission now yields `pending_safety_check` — see TC-EVENTS-140.

- **Pre-conditions:** Coordinator A owns a safety-returned planning event with
  one history entry and existing resource fields.
- **Steps:** Resubmit it for a fresh safety review.
- **Expected:** One conditional update changes `planning` to `confirmed` and
  clears only the four current safety-decision fields. History and all event
  and resource fields remain unchanged, making the event eligible for S-86.
- **Actual:** The result was confirmed with null current safety fields and the
  original history; the update payload contained exactly those five lifecycle
  fields and no history/resource field.
- **Status:** Pass
- **Evidence:** `test_s87.py::test_resubmit_clears_only_current_blocker_and_preserves_history`

## TC-EVENTS-134 — stale and concurrent resubmissions cannot overwrite

- **Pre-conditions:** The eligibility read succeeds but the conditional write
  loses a concurrent race.
- **Steps:** Submit the S-87 transition.
- **Expected:** Empty update result returns `409`; there is no fallback or
  unconditional write and the prior review cannot be lost.
- **Actual:** An empty conditional result returned `409` after exactly one
  write attempt.
- **Status:** Pass
- **Evidence:** `test_s87.py::test_repeated_or_concurrent_resubmit_is_409_without_fallback_write`
## S-26 — Update Equipment Preparation Status

Story: S-26 Update Equipment Preparation Status. Acceptance criteria and test
cases confirmed by the developer on 2026-10-11. These cases are the canonical
backend trace for the story and have not yet been executed.

| Acceptance criterion | Cases |
| --- | --- |
| Technical Support can set Not Started, In Progress, and Ready | TC-EVENTS-123 |
| The current status is available to the event readiness view | TC-EVENTS-123, TC-EVENTS-126 |
| Only assigned Technical Support can change the status | TC-EVENTS-124 |
| Confirmed rules: backwards transitions, eligible event states, audit, and safe races/failures | TC-EVENTS-123–125 |

### TC-EVENTS-123 — assigned Technical Support records every preparation state with an audit trail

- **Scenario:** The assigned Technical Support worker maintains one equipment preparation status for the event.
- **Pre-conditions:** An event assigned to Technical Support A is in each eligible lifecycle state: `planning`, `confirmed`, or `preparation`.
- **Steps:** Read a newly eligible event; update it to `in_progress`, then `ready`, then back to `not_started`; read it again.
- **Test data:** Event `33333333-3333-4333-8333-333333333333`; Technical Support A `dddddddd-dddd-4ddd-8ddd-dddddddddddd`; the three status values.
- **Expected:** A new event reads as `not_started`. Every transition succeeds, including moving backwards; the response and later event read expose the current status, authenticated updater id, and a server-generated update time.
- **Actual:** All three values persisted in every eligible lifecycle state; each response contained the authenticated updater and server timestamp.
- **Status:** Pass
- **Evidence:** `test_equipment_preparation.py::test_assigned_support_can_record_each_status_and_move_backwards`

### TC-EVENTS-124 — preparation updates are restricted to the assigned Technical Support worker

- **Scenario:** Event assignment and trusted role jointly control the write.
- **Pre-conditions:** The eligible event is assigned to Technical Support A.
- **Steps:** Attempt the update as A, Technical Support B, its assigned Event Coordinator, Event Organiser, Venue Staff, Attendee, an unknown role, and without a session.
- **Test data:** Status `ready`; support ids A and B; all trusted project roles.
- **Expected:** A succeeds. B sees `404` so another worker's assignment is not disclosed. Other authenticated roles receive `403`; no session receives `401`; no denied request writes storage. The Coordinator can still read the resulting status through their existing assigned-event view.
- **Actual:** Assigned Technical Support was authorised; unassigned support was hidden with `404`; every other tested role was denied before storage.
- **Status:** Pass
- **Evidence:** `test_equipment_preparation.py::test_only_assigned_support_can_update_preparation`

### TC-EVENTS-125 — invalid, stale, concurrent, and failed preparation updates never report success

- **Scenario:** A response cannot claim a preparation change that storage did not make.
- **Pre-conditions:** Invalid payloads; an event that is missing, reassigned, cancelled, or changed concurrently; and a storage exception.
- **Steps:** Submit an unknown status, extra audit fields, and each stale or failing update.
- **Test data:** `done`; client-supplied updater/time; reassigned/cancelled event; empty conditional-update result; simulated Supabase failure.
- **Expected:** Invalid payloads return `422` before storage. Missing or hidden assignments return `404`; ineligible or concurrently changed events return `409`. The conditional write matches event id, assigned worker, and eligible lifecycle status. Storage failure returns safe `500`; no case fabricates a changed response.
- **Actual:** Invalid bodies failed before storage, an empty conditional update returned `409`, and a simulated storage exception returned only the safe service error.
- **Status:** Pass
- **Evidence:** `test_equipment_preparation.py::test_invalid_and_stale_updates_never_report_success`

## S-17 — submit an event for the Operational Safety Check

S-17 adds the stored status `pending_safety_check` between `planning` and
`confirmed`. The Coordinator's submission (and S-87's resubmission) moves
`planning → pending_safety_check`; the S-86 queue reads that status; a Safety
Officer's approval moves it to `confirmed`. `preparation` stays allowed but
nothing sets it in S-17. Readiness itself is checked in the `safety_checks`
composite (TC-SAFETYCHECKS-010 onwards) — this service only owns the
transitions and the Technical Support sign-off record.

Shared test data: event `E1` = `0b6f0e55-0000-4000-8000-000000000001`,
Coordinator `C1` = `c0000000-0000-4000-8000-000000000001`, Coordinator `C2` =
`c0000000-0000-4000-8000-000000000002`, Technical Support `T1` =
`70000000-0000-4000-8000-000000000001`, `T2` =
`70000000-0000-4000-8000-000000000002`, Safety Officer `S1` =
`50000000-0000-4000-8000-000000000001`.

## TC-EVENTS-135 — `pending_safety_check` is a valid stored status

- **Scenario:** The new stage validates and serialises like any other status.
- **Pre-conditions:** None (schema only).
- **Steps:** 1. Build `EventRead` from a row with `status: "pending_safety_check"`,
  `decision: "approved"`. 2. Build one with `status: "pending_safety_check"`,
  `decision: null`.
- **Test data:** The two rows above, otherwise a complete submitted event.
- **Expected:** 1 validates and `status == "pending_safety_check"`. 2 is
  refused at the database by `events_decision_matches_status` (covered by
  TC-EVENTS-147); the Pydantic model accepts the status value itself.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_pending_safety_check_is_a_valid_status`

## TC-EVENTS-136 — the assigned Coordinator's planning event moves to pending_safety_check

- **Scenario:** The internal safety-submission transition succeeds once.
- **Pre-conditions:** Fake returns `E1` with `status: "planning"`,
  `assigned_coordinator_id: C1`, `safety_decision: null`.
- **Steps:** 1. `POST /internal/events/E1/safety-submission` with
  `{"coordinator_id": C1}`.
- **Test data:** As above.
- **Expected:** `200`; body `status == "pending_safety_check"`. Exactly one
  update, values `{"status": "pending_safety_check"}`, filtered on `id = E1`,
  `status = planning`, `assigned_coordinator_id = C1`. No resource field
  (venue, equipment, Technical Support, sign-off) is in the update.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_planning_event_moves_to_pending_safety_check`

## TC-EVENTS-137 — only a planning event of the caller can be submitted

- **Scenario:** Ineligible states and other Coordinators never transition.
- **Pre-conditions:** Fake returns `E1` assigned to `C1` in each state below.
- **Steps:** 1. Submit as `C1` with `E1` in `submitted`, `pending_safety_check`,
  `confirmed`, `safety_rejected`, `rejected`. 2. Submit as `C2` with `E1` in
  `planning`. 3. Submit as `C1` with `E1` in `planning` but the conditional
  update matches no row (a concurrent submission).
- **Test data:** As above.
- **Expected:** 1 → `409` "This event is not in planning", no update call.
  2 → `404`, no update call. 3 → `409`, no second update.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_only_assigned_planning_event_can_be_submitted`

## TC-EVENTS-138 — the S-86 queue reads pending_safety_check

- **Scenario:** The Safety Officer's queue is the new stage, not `confirmed`.
- **Pre-conditions:** Fake records the query.
- **Steps:** 1. `GET /internal/events/safety-review`. 2. `GET
  /internal/events/safety-review/E1` with `E1` `confirmed`, then
  `pending_safety_check`.
- **Test data:** `E1` with `safety_decision: null`.
- **Expected:** 1 filters `status = pending_safety_check` and
  `safety_decision is null`, oldest `updated_at` first. 2 → `409` for
  `confirmed`, `200` for `pending_safety_check`.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_safety_queue_reads_pending_safety_check`

## TC-EVENTS-139 — safety approval makes the event Confirmed

- **Scenario:** Confirmed is reached only through the Safety Officer.
- **Pre-conditions:** `E1` is `pending_safety_check`, `safety_decision: null`.
- **Steps:** Record each decision in turn on a fresh `E1`: `approved`;
  `rejected` with reason `"Fire exits blocked"`; `changes_requested` with
  reason `"Add stewards"`; all by `S1`.
- **Test data:** As above.
- **Expected:** Resulting status `confirmed`, `safety_rejected`, `planning`
  respectively. Each conditional update filters `status =
  pending_safety_check` and `safety_decision is null`. No outcome sets
  `preparation`.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_safety_outcomes_from_pending_safety_check`

## TC-EVENTS-140 — S-87 resubmission returns to pending_safety_check

- **Scenario:** A safety-returned event re-enters the queue at the new stage.
- **Pre-conditions:** `E1` is `planning`, `safety_decision:
  "changes_requested"`, assigned to `C1`, one history record.
- **Steps:** `POST /internal/events/E1/safety-resubmit` with
  `{"coordinator_id": C1}`.
- **Test data:** As above.
- **Expected:** `200`, `status == "pending_safety_check"`, current safety
  decision fields null, history unchanged (still one record).
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_safety_resubmit_returns_to_pending_safety_check`

## TC-EVENTS-141 — assigned Technical Support records a sign-off

- **Scenario:** Approve and decline are stored with who and when, and the
  Coordinator can read them.
- **Pre-conditions:** `E1` is `planning`, `assigned_technical_support_id: T1`.
- **Steps:** 1. `PUT /internal/events/E1/technical-signoff` with
  `{"technical_support_id": T1, "decision": "approved"}`. 2. Same with
  `{"decision": "approved", "override_comment": "Borrowing 2 projectors from
  Library"}`. 3. Same with `{"decision": "declined", "reason": "Only one
  sound desk exists"}`. 4. `GET /events/assigned/E1` as `C1` after 3.
- **Test data:** As above.
- **Expected:** 1 stores `technical_signoff_decision: "approved"`,
  `technical_signoff_by: T1`, a server timestamp, reason and comment null.
  2 stores the comment. 3 stores `"declined"` and the reason, comment null.
  4 returns all five sign-off fields to the Coordinator.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_assigned_support_records_signoff`

## TC-EVENTS-142 — sign-off payload rules

- **Scenario:** A decline always has a reason; an approval never does.
- **Pre-conditions:** As TC-EVENTS-141.
- **Steps:** Send each payload.
- **Test data:** `{"decision": "declined"}`; `{"decision": "declined",
  "reason": "   "}`; `{"decision": "approved", "reason": "x"}`;
  `{"decision": "declined", "reason": "x", "override_comment": "y"}`;
  `{"decision": "approved", "override_comment": "  "}`; reason of 501
  characters; `{"decision": "maybe"}`.
- **Expected:** Every payload → `422` and no update.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_signoff_payload_rules`

## TC-EVENTS-143 — only the assigned Technical Support, only in planning

- **Scenario:** Only the assigned Technical Support signs off, and only in planning.
- **Pre-conditions:** As TC-EVENTS-141.
- **Steps:** 1. Sign off `E1` as `T2` while `T1` is assigned. 2. Sign off as
  `T1` with `E1` in `pending_safety_check`, then `confirmed`.
- **Test data:** `{"decision": "approved"}`.
- **Expected:** 1 → `404`, no update. 2 → `409` "Technical Support sign-off
  can only change while the event is in planning", no update.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_signoff_limited_to_assigned_support_in_planning`

## TC-EVENTS-144 — clearing a sign-off returns it to awaiting

- **Scenario:** A Coordinator equipment change voids the previous sign-off.
- **Pre-conditions:** `E1` `planning` with an approved sign-off (comment
  set); separately with a declined sign-off; separately with none.
- **Steps:** `POST /internal/events/E1/technical-signoff/clear` for each.
- **Test data:** As above.
- **Expected:** `200` each time; afterwards all five sign-off fields are null.
  Clearing when none exists is not an error.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_clear_signoff_returns_to_awaiting`

## TC-EVENTS-145 — the Organiser sees each stage

- **Scenario:** The Organiser's own event shows Pending Safety Check, then
  Confirmed.
- **Pre-conditions:** Organiser `O1` owns `E1`.
- **Steps:** `GET /events/E1` as `O1` with `E1` `pending_safety_check`, then
  `confirmed`.
- **Test data:** As above.
- **Expected:** `200` with `status` `pending_safety_check`, then `confirmed`.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_organiser_reads_pending_and_confirmed`

## TC-EVENTS-146 — pending_safety_check counts as an open event wherever confirmed does

- **Scenario:** The new stage is not silently dropped by existing lists.
- **Pre-conditions:** `E1` is `pending_safety_check`.
- **Steps:** 1. Coordinator active assignments (`/internal/events/assigned-active`).
  2. Technical Support's assigned list. 3. S-26 equipment preparation update
  by `T1`. 4. S-62 cancellation request by the Organiser.
- **Test data:** As above.
- **Expected:** 1 and 2 include `E1`; 3 → `200`; 4 → `200`, exactly as for a
  `confirmed` event.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** `test_s17.py::test_pending_safety_check_is_open_everywhere_confirmed_is`
