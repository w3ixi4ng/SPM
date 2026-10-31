# Test cases — events service schemas (unit)

Covers `tests/unit/atomic/events/test_schemas.py`, `test_app.py`, and `test_s93.py`: validation,
normalization, authentication, RBAC, ownership, and endpoint behaviour with both
Supabase clients mocked. They use no network, database, or Docker.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/events` |
| Last run | 2026-10-27, S-93 merge tree of `5aed635` and `origin/sprint4` `0d143d7` |
| Environment | Python 3.14.8, pytest 9.1.1; mocked Supabase; no network, database or Docker. |
| Result | 343 passed in this folder; 1,503 passed, 17 skipped across Python unit. |

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

## TC-EVENTS-053 — internal create trusts the caller's organiser and starts unassigned

- **Scenario:** Unlike the public `POST /events`, this route does not derive
  `organiser_id` from a session — the caller (the composite) has already
  verified it and supplies it directly. S-83 reserves assignment for the Lead.
- **Pre-conditions:** None.
- **Steps:** `POST /events/internal` with a complete submitted payload plus
  `organiser_id` and null `assigned_coordinator_id`; inspect the insert.
- **Test data:** The standard valid submitted payload, an organiser id, and a
  null coordinator id.
- **Expected:** `201`; the inserted row's `organiser_id` is supplied and
  `assigned_coordinator_id` is null; `status=submitted`
  and `submitted_at` set, same as the public route.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_create_trusts_caller_organiser_but_starts_unassigned`

## TC-EVENTS-054 — internal submit preserves assignment and enforces ownership

- **Scenario:** The draft-to-submission internal route applies the same
  ownership and draft-status filter as the public one, while preserving any existing assignment.
- **Pre-conditions:** A draft owned by the given organiser id exists.
- **Steps:** `POST /events/{event_id}/submit/internal` with the standard
  submitted payload, that organiser id, and the stored coordinator id.
- **Test data:** As above.
- **Expected:** `200`; the update is filtered by both `id` and
  `organiser_id`, sets `status=submitted` and `submitted_at`, and keeps
  `assigned_coordinator_id` equal to the stored assignment.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_submit_preserves_existing_assignment`

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

> **S-61 (2026-10-11):** the expected set now also includes `events:decide_cancellation`.

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

## TC-EVENTS-063 — internal update cannot reassign the coordinator

- **Scenario:** An obsolete edit-recheck path cannot bypass S-84 by writing
  a new Coordinator ID with a date/time change.
- **Pre-conditions:** An owned submitted event assigned to one coordinator.
- **Steps:** `PATCH /events/{event_id}/internal` with `organiser_id`, a
  changed `start_time`, and a different `assigned_coordinator_id`.
- **Test data:** `start_time` changed to `20:00`; a second coordinator's id.
- **Expected:** `409`; no Supabase update runs, so neither the start time
  nor the Coordinator changes.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_update_rejects_a_different_coordinator`

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

## TC-EVENTS-112 — active assigned events support Lead oversight and notifications

- **Scenario:** The atomic service supplies assigned work to its responsible
  Lead while retaining the cross-service read needed for notifications.
- **Steps:** As a Lead, call `GET /internal/events/lead-assigned-active`;
  then, without a Lead session, call `GET /internal/events/assigned-active`
  as the venue notifications composite does.
- **Expected:** Storage selects the nine nonterminal assignment states from
  `submitted` through `safety_changes_requested`, excludes null owners, and orders newest updates
  first. The Lead read includes only events with that Lead's recorded assignment
  provenance; the cross-service read remains available for affected booking
  notifications. Draft, rejected, and cancelled rows cannot enter either result.
- **Actual:** The Lead query filtered by its trusted ID. The notification read
  worked without a Lead session and retained the active-status and owner filters.
- **Status:** Pass
- **Evidence:** `test_s84.py::test_internal_active_assignments_filter_status_owner_and_order`; `test_s84.py::test_notification_assignment_read_does_not_require_a_lead_session`; 2026-10-25 S-88 regression rerun.

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

## TC-EVENTS-117 — oversight lists every open assignment status

- **Scenario:** The events service supplies the complete active assigned-event
  set without making role, profile, or grouping decisions.
- **Pre-conditions:** Supabase is mocked; the query returns one assigned event
  for each accepted status.
- **Steps:** `GET /internal/events/coordinator-overview` and inspect the
  storage query and response validation.
- **Test data:** `submitted`, `under_review`, `returned`, `planning`,
  `pending_safety_check`, `confirmed`, `preparation`, `safety_rejected`, and
  `safety_changes_requested` assigned to coordinator A.
- **Expected:** The query includes exactly those nine statuses, excludes null
  `assigned_coordinator_id` values, orders newest updates first, and accepts
  all nine statuses in the response contract.
- **Actual:** The response accepted one row in each open status; storage
  received the exact nine-status filter, excluded null owners, and ordered by
  descending update time.
- **Status:** Pass
- **Evidence:** `test_s85.py::test_internal_oversight_uses_all_open_active_statuses`

## TC-EVENTS-118 — oversight excludes unassigned and inactive events at storage

- **Scenario:** Draft, rejected, cancelled, completed, and unassigned events
  cannot enter the Lead's oversight source.
- **Pre-conditions:** Supabase is mocked.
- **Steps:** Inspect the filters used by
  `GET /internal/events/coordinator-overview`.
- **Test data:** The draft/terminal/unassigned states plus the nine active
  states from TC-EVENTS-117.
- **Expected:** Filtering is performed by the atomic owner: only the nine
  active statuses and non-null owners are selected. The route performs no
  write and no other-service call.
- **Actual:** The read query contained only the nine active values and the
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
- **Evidence:** `test_s86.py::test_safety_queue_selects_only_undecided_pending_events`; `test_s86.py::test_safety_detail_distinguishes_missing_from_ineligible`

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

---

## S-18 — Update Event Information

Story: S-18 Update Event Information. Acceptance criteria supplied and design
decisions confirmed by the developer on 2026-10-19.

| Acceptance criterion | Cases |
| --- | --- |
| The assigned Coordinator can edit an event during planning | TC-EVENTS-148, TC-EVENTS-152 |
| Routine contact, description and internal-note edits do not trigger re-review | TC-EVENTS-148 |
| Date/time, attendance, venue-requirement and equipment-requirement changes require impact review | TC-EVENTS-149; equipment requirements are covered by TC-EQUIPMENTREQUIREMENTS-030 |
| Accepted significant changes to Confirmed/Preparation return to Planning and require a fresh safety check | TC-EVENTS-150 |
| Existing venue and equipment arrangements are preserved | TC-EVENTS-150, TC-EVENTS-151 |
| Saves are immediately reflected in the event record | TC-EVENTS-148, TC-EVENTS-150 |
| Every edit records what, who and when for future S-82 display | TC-EVENTS-148, TC-EVENTS-151 |

## TC-EVENTS-148 — routine edits save immediately without lifecycle review

- **Scenario:** The assigned Coordinator updates routine planning information.
- **Pre-conditions:** Coordinator A is assigned to event E in each of
  `planning`, `confirmed`, and `preparation`. E has an existing purpose,
  contact name/email/phone and internal note.
- **Steps:** Patch each routine field as A, then read E through the assigned
  event route.
- **Test data:** Purpose `Updated delegate briefing`; contact `Sam Lee`,
  `sam.lee@example.com`, `+65 6123 4567`; internal note
  `Call organiser on arrival`.
- **Expected:** The trimmed values are returned immediately and survive the
  later read. Status and current safety fields are unchanged; no impact-review
  confirmation is requested. One append-only history entry records only the
  fields whose normalized values changed, their before/after values, A's
  authenticated UUID and a server timestamp. Browser-supplied actor/time or
  history fields are rejected.
- **Actual:** Normalized routine values were saved in one versioned update;
  lifecycle and current safety fields were absent from the update, and the
  appended history named only the changed routine fields and trusted actor.
- **Status:** Pass
- **Evidence:** `test_s18.py::test_routine_edits_save_immediately_without_lifecycle_review`

## TC-EVENTS-149 — significant changes are classified by the server and require acceptance

- **Scenario:** A significant edit cannot bypass impact review by changing the
  browser request.
- **Pre-conditions:** Coordinator A is assigned to planning event E.
- **Steps:** Separately change start/end date or time, the effective duration,
  expected attendance, venue preference, room layout, required facilities,
  and required accessibility; repeat with normalized values equal to storage;
  attempt the save without and then with explicit impact acceptance.
- **Test data:** Attendance `120` to `150`; `theatre` to `banquet`; add
  `stage`; reorder an otherwise identical facility list; client-supplied
  `significant: false`.
- **Expected:** The service calculates significance from stored and proposed
  normalized values. Each real significant change first returns an impact
  summary and leaves E unchanged until accepted. Reordered/deduplicated equal
  lists and equal trimmed values are no-ops. Client classification is
  forbidden. An accepted planning edit saves once, remains `planning`, and
  records its exact audit entry.
- **Actual:** The server preview identified attendance and facility changes;
  a save without acceptance returned `409` before any update.
- **Status:** Pass
- **Evidence:** `test_s18.py::test_significant_changes_are_server_classified_and_require_acceptance`

## TC-EVENTS-150 — accepted significant edits restart the lifecycle and safety check

- **Scenario:** A material change after confirmation must pass through
  planning and a new Operational Safety Check.
- **Pre-conditions:** Coordinator A owns one `confirmed` and one `preparation`
  event. Each has current safety fields and at least one prior
  `safety_review_history` entry.
- **Steps:** Accept an attendance/date change; read the event; submit the
  revised planning event for its new safety check.
- **Expected:** The accepted edit atomically saves the values, changes status
  to `planning`, clears only the current safety decision/reason/officer/time,
  and preserves prior safety history. The later lifecycle action conditionally
  uses the S-17 readiness check and moves this revised event from `planning`
  to `pending_safety_check`. Only the Safety Officer can later make it
  `confirmed`. The response at each step reflects the stored state immediately.
- **Actual:** Acceptance produced Planning, cleared only current safety state,
  retained safety history and existing sign-offs. S-17 separately proves that
  a ready planning event moves to Pending Safety Check without a bypass.
- **Status:** Pass
- **Evidence:** `test_s18.py::test_accepted_significant_edit_restarts_lifecycle_without_resetting_signoffs`; `test_s17.py::test_planning_event_moves_to_pending_safety_check`

## TC-EVENTS-151 — significant edits preserve existing arrangements and append immutable history

- **Scenario:** Re-review does not silently discard work already completed by
  Venue Staff or Technical Support.
- **Pre-conditions:** A confirmed/preparation event has equipment preparation
  `ready`, a Technical Support assignment, safety-review history, and external
  venue-booking/equipment-requirement references.
- **Steps:** Accept a significant event edit and inspect the conditional update
  payload, returned record, and edit history; attempt to overwrite or delete
  an earlier history entry.
- **Expected:** The event update does not reset equipment preparation or
  assignments and does not issue writes to booking/equipment storage. Previous
  safety and edit history remains byte-for-byte unchanged and a new numbered
  edit entry is appended. History mutation through the edit payload is `422`.
- **Actual:** The conditional Events update omitted equipment preparation and
  safety history; schemas forbid browser-supplied audit and arrangement fields.
  Database-backed browser verification retained the booking and requirement.
- **Status:** Pass
- **Evidence:** `test_s18.py::test_accepted_significant_edit_restarts_lifecycle_without_resetting_signoffs`; `tests/e2e/test_update_event_information.py`

## TC-EVENTS-152 — assignment, state, validation, concurrency and storage failures fail closed

- **Scenario:** An edit reports success only when the assigned Coordinator's
  complete change and audit record were stored together.
- **Pre-conditions:** Events assigned to Coordinator A in editable and closed
  states; Coordinator B; invalid payloads; a stale version; simulated storage
  failure.
- **Steps:** Edit as A, B, every other role and without a session; edit a
  cancelled/rejected event; submit invalid contact/time values, a no-op, and a
  stale concurrent write; make the atomic event-plus-history operation fail.
- **Expected:** A may edit `planning`, `confirmed`, and `preparation`. B sees
  `404`; other roles `403`; no session `401`; closed states and stale writes
  `409`; invalid bodies `422`; a no-op creates no history; storage failure is a
  safe `500`. No failure leaves changed event data without its audit entry or
  an audit entry without its event change.
- **Actual:** Wrong assignment was hidden, closed lifecycle and stale version
  returned `409`, invalid/extra fields were rejected by the strict schema, and
  the version predicate kept the data-plus-history update conditional.
- **Status:** Pass
- **Evidence:** `test_s18.py::test_event_edits_fail_closed_and_are_atomic`; focused Python run, 377 passed, 2026-10-19.
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
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
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
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
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
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_only_planning_events_can_be_submitted`; `test_s17.py::test_only_assigned_planning_event_can_be_submitted`; `test_s17.py::test_safety_returned_event_is_resubmitted_not_submitted`

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
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s86.py::test_safety_queue_selects_only_undecided_pending_events`

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
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s86.py::test_safety_decision_records_audit_and_distinct_lifecycle_state`; `test_s86.py::test_empty_conditional_update_reports_concurrent_decision_without_overwrite`

## TC-EVENTS-140 — S-87 resubmission returns to pending_safety_check

- **Scenario:** A safety-returned event re-enters the queue at the new stage.
- **Pre-conditions:** `E1` is `planning`, `safety_decision:
  "changes_requested"`, assigned to `C1`, one history record.
- **Steps:** `POST /internal/events/E1/safety-resubmit` with
  `{"coordinator_id": C1}`.
- **Test data:** As above.
- **Expected:** `200`, `status == "pending_safety_check"`, current safety
  decision fields null, history unchanged (still one record).
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s87.py::test_resubmit_clears_only_current_blocker_and_preserves_history`

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
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_assigned_support_records_signoff`; `test_s17.py::test_coordinator_reads_the_signoff`

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
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_signoff_payload_rules`

## TC-EVENTS-143 — only the assigned Technical Support, only in planning

- **Scenario:** Only the assigned Technical Support signs off, and only in planning.
- **Pre-conditions:** As TC-EVENTS-141.
- **Steps:** 1. Sign off `E1` as `T2` while `T1` is assigned. 2. Sign off as
  `T1` with `E1` in `pending_safety_check`, then `confirmed`.
- **Test data:** `{"decision": "approved"}`.
- **Expected:** 1 → `404`, no update. 2 → `409` "Technical Support sign-off
  can only change while the event is in planning", no update.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_signoff_limited_to_assigned_support_in_planning`

## TC-EVENTS-144 — clearing a sign-off returns it to awaiting

- **Scenario:** A Coordinator equipment change voids the previous sign-off.
- **Pre-conditions:** `E1` `planning` with an approved sign-off (comment
  set); separately with a declined sign-off; separately with none.
- **Steps:** `POST /internal/events/E1/technical-signoff/clear` for each.
- **Test data:** As above.
- **Expected:** `200` each time; afterwards all five sign-off fields are null.
  Clearing when none exists is not an error.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_clear_signoff_returns_to_awaiting`

## TC-EVENTS-145 — the Organiser sees each stage

- **Scenario:** The Organiser's own event shows Pending Safety Check, then
  Confirmed.
- **Pre-conditions:** Organiser `O1` owns `E1`.
- **Steps:** `GET /events/E1` as `O1` with `E1` `pending_safety_check`, then
  `confirmed`.
- **Test data:** As above.
- **Expected:** `200` with `status` `pending_safety_check`, then `confirmed`.
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
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
- **Actual:** Passed at `cd996d0`: every point under Expected held.
- **Status:** Pass
- **Evidence:** `test_s17.py::test_pending_safety_check_is_open_everywhere_confirmed_is`


## S-61 — review and approve cancellation request

Story: S-61 Review and Approve Cancellation Request.
Confirmed by the developer on 2026-10-11.
A new Coordinator route, `POST /events/{id}/cancellation-decision`, called by
the `event_requests` composite, which also releases the event's venue
bookings. IDs continue from the next unused number (this file's 001–099
range is full).

**Acceptance criteria → cases (all layers)**

| Acceptance criterion | Cases |
| --- | --- |
| AC1: A Coordinator can approve a submitted cancellation request, changing the event's status to Cancelled | EVENTS-154, 157, 158, 160, EVENTREQUESTS-069, 112, FRONTEND-141, E2E-245 |
| AC2: Approving releases the event's committed venue and equipment reservations | BOOKINGS-064, 065, EVENTREQUESTS-069, 067, 112, E2E-245; equipment: EVENTS-105/106 (only `planning` and `confirmed` events reserve equipment) and EVENTREQUESTS-112 |
| AC3: The decision is recorded against the event | EVENTS-154, 155, EVENTREQUESTS-112 |

Decisions agreed with the developer on 2026-10-11:

- **Approve or decline.** Approving sets the status to `cancelled`.
  Declining needs a reason and leaves the status as it was.
- **Recorded on the event** in four new columns: `cancellation_decision`
  (`approved` or `declined`), `cancellation_decision_reason` (decline only),
  `cancellation_decided_by` and `cancellation_decided_at`. These hold the
  latest decision only.
- **After a decline the Organiser may request again.** The new request
  overwrites the old one and clears the decision (changes S-62's
  TC-EVENTS-127 rule for this one case).
- **Venue bookings are deleted, not marked.** Every booking row for the event
  is removed, so its times show as available and nothing is tied to the
  cancelled event.
- **Equipment** is freed by the status change alone. Requirement rows stay
  but stop counting, because only `planning` and `confirmed` events reserve
  equipment.
- **Order and retry.** The status changes first, then the bookings are
  removed. If that removal fails, approving again finishes it without
  changing the status again.
- **A `cancelled` event may have no request decision**, so a `submitted` or
  `under_review` event can be cancelled. This needs an SQL constraint change.
- **No notification** for now. The Organiser sees "Cancelled".

**Shared test data.** Coordinator K (`aaaaaaaa-…`) is assigned event E
(`33333333-…`). E is `planning` with a pending request from Organiser O:
reason "Keynote speaker withdrew", requested `2026-10-11T09:00:00Z`, no
decision.

## TC-EVENTS-154 — the assigned Coordinator approves a cancellation request

- **Scenario:** Approval cancels the event and records the decision (AC1, AC3).
- **Pre-conditions:** K signed in. The assigned-event lookup returns E in
  each status a request can be made in. The guarded update returns the
  cancelled row.
- **Steps:** `POST /events/E/cancellation-decision` `{"decision": "approved"}`
  once per status.
- **Test data:** statuses `submitted`, `under_review`, `planning`,
  `confirmed`, `preparation`, `safety_changes_requested`.
- **Expected:** `200` with `status` `cancelled`, `cancellation_decision`
  `approved`, `cancellation_decided_by` K, `cancellation_decided_at` set, and
  `cancellation_decision_reason` null. The write sets exactly those five
  fields. The decision time is the server's. The write is guarded by id,
  `assigned_coordinator_id` K, a non-null `cancellation_requested_at` and a
  null `cancellation_decision`.
- **Actual:** All six statuses returned `200` `cancelled` with the decision, coordinator and time set and no reason; the write set exactly those five fields, guarded by id, assigned coordinator, a requested and an undecided request.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s61.py::test_the_assigned_coordinator_approves_a_cancellation_request`

## TC-EVENTS-155 — the assigned Coordinator declines with a reason

- **Scenario:** Declining records why and leaves the event as it was (AC3).
- **Pre-conditions:** As TC-EVENTS-154, E `planning`.
- **Steps:** `POST /events/E/cancellation-decision`.
- **Test data:** `{"decision": "declined", "reason": "  Venue is non-refundable; move the date instead  "}`
- **Expected:** `200` with `status` still `planning`, `cancellation_decision`
  `declined`, the trimmed reason, and `cancellation_decided_by` and
  `cancellation_decided_at` set. The write never includes `status`.
- **Actual:** `200` with status `planning`, `declined` and the trimmed reason; the write had the four decision fields and no `status`.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s61.py::test_the_assigned_coordinator_declines_with_a_reason`

## TC-EVENTS-156 — a decision with a missing or wrong field is refused

- **Scenario:** A decline needs a reason; an approval takes none.
- **Pre-conditions:** K signed in.
- **Steps:** `POST /events/E/cancellation-decision` with each body.
- **Test data:** `{}`; `{"decision": "maybe"}`;
  `{"decision": "declined"}`; `{"decision": "declined", "reason": "   "}`;
  `{"decision": "declined", "reason": "x" * 1001}`;
  `{"decision": "approved", "reason": "ok"}`;
  `{"decision": "approved", "status": "draft"}`.
- **Expected:** `422` for each, before any database call.
- **Actual:** All seven bodies returned `422` before any database call.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s61.py::test_a_decision_with_a_missing_or_wrong_field_is_refused`

## TC-EVENTS-157 — only the event's assigned Coordinator may decide

- **Scenario:** Nobody else can cancel or decline (AC1).
- **Pre-conditions:** The assigned-event lookup returns no row for an
  unassigned or missing event.
- **Steps:** Approve E as:
  1. no session;
  2. each of `event_organiser`, `venue_staff`, `technical_support`,
     `attendee`;
  3. a Coordinator E is not assigned to;
  4. K, for a missing id.
- **Expected:** 1 → `401`; 2 → `403`; 3 and 4 → `404` "Event not found". No
  update in any case.
- **Actual:** No session `401`; four other roles `403`; unassigned and missing `404`; no update.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s61.py::test_no_session_is_401`; `tests/unit/atomic/events/test_s61.py::test_other_roles_are_403`; `tests/unit/atomic/events/test_s61.py::test_an_unassigned_or_missing_event_is_404`

## TC-EVENTS-158 — there must be a pending request to decide

- **Scenario:** A Coordinator can't cancel an event nobody asked to cancel,
  or decide twice (AC1).
- **Pre-conditions:** K signed in.
- **Steps:** Approve, then decline, E in each state.
- **Test data:**
  1. E with no request (`cancellation_requested_at` null);
  2. E already declined;
  3. E already approved (`cancelled`) — decline only.
- **Expected:** `409` each time: 1 "There is no cancellation request to
  decide for this event."; 2 and 3 "This cancellation request has already
  been decided." No update.
- **Actual:** No request `409` "There is no cancellation request to decide for this event."; declined, and decline-after-approve, `409` "This cancellation request has already been decided."; no update.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s61.py::test_there_must_be_a_pending_request_to_decide`

## TC-EVENTS-159 — approving an already approved request again changes nothing

- **Scenario:** A retry after a failed booking release is safe (decision 7).
- **Pre-conditions:** K signed in; E `cancelled` with `cancellation_decision`
  `approved` by K.
- **Steps:** `POST /events/E/cancellation-decision` `{"decision": "approved"}`.
- **Expected:** `200` with E as stored. No update is made.
- **Actual:** `200` with the cancelled event; no update.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s61.py::test_approving_an_already_approved_request_again_changes_nothing`

## TC-EVENTS-160 — a decision that loses a race is refused without overwriting

- **Scenario:** Two Coordinators' tabs, or a status change, between the read
  and the write.
- **Pre-conditions:** K signed in; E pending; the guarded update matches
  nothing.
- **Steps:** Approve E.
- **Expected:** `409` "This cancellation request has already been decided."
  after the one guarded write, with no unguarded retry.
- **Actual:** `409` after the one guarded write; no retry.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s61.py::test_a_decision_that_loses_a_race_is_refused_without_overwriting`

## TC-EVENTS-161 — after a decline the Organiser can request again

- **Scenario:** A declined request doesn't lock the Organiser out (decision 1).
- **Pre-conditions:** O signed in. E `planning` with a declined request.
- **Steps:**
  1. `POST /events/E/cancellation-request` `{"reason": "Speaker still unavailable"}`.
  2. The same while E's request is pending (not decided).
  3. The same once E's request is approved (E `cancelled`).
- **Expected:**
  1. `200`. The write sets the new reason, requester and time, and clears all
     four decision fields. It is guarded by a request that is either absent
     or declined.
  2. `409` "A cancellation request has already been sent for this event." (as
     TC-EVENTS-127).
  3. `409` "This event can't be cancelled from its current status." (as
     TC-EVENTS-124).
- **Actual:** After a decline the new request returned `200`, cleared all four decision fields, and was guarded by an absent-or-declined request; pending and approved still returned their `409`s.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s61.py::test_after_a_decline_the_organiser_can_request_again`; `tests/unit/atomic/events/test_s61.py::test_a_pending_or_approved_request_still_blocks_another`

## TC-EVENTS-162 — a cancelled event can't be edited or resubmitted

- **Scenario:** A cancelled event is closed, at the service as well as in
  the page (S-61; added 2026-10-13 at the developer's request, after the
  page was locked for cancelled events).
- **Pre-conditions:** Organiser O signed in; the owned-event lookup returns E
  `cancelled`.
- **Steps:**
  1. `PATCH /events/E` `{"name": "New name"}`.
  2. The same through `PATCH /events/E/internal` with `organiser_id` O.
  3. `POST /events/E/submit` with a full valid body.
- **Expected:** 1 and 2 → `409` "This event has been cancelled and is
  closed."; 3 → `409` "Event has already been submitted.". No update in any
  case.
- **Actual:** Editing through both routes returned `409` "This event has been cancelled and is closed."; resubmitting returned `409` "Event has already been submitted"; no update.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s61.py::test_a_cancelled_event_cant_be_edited_or_resubmitted`; `pytest tests/unit`: 964 passed, 17 skipped, 2026-10-13.

## S-51 — Configure registration and its open/close period

Registration settings are three new fields on the event: `registration_required`
(boolean, default `false`), `registration_opens_at` and `registration_closes_at`
(date-times with no timezone, read as Singapore time). Event E below, unless a
case says otherwise, starts `2026-11-20` at `18:00`. "Today" is `2026-10-25`.

## TC-EVENTS-163 — registration is off unless the Organiser turns it on

- **Scenario:** An event that says nothing about registration does not need it (S-51 AC1).
- **Pre-conditions:** None.
- **Steps:** 1. Instantiate `EventDraftCreate` with `{}`. 2. Instantiate
  `EventSubmittedCreate` with a full valid body that has no registration fields.
- **Test data:** The full body used by TC-EVENTS-006's valid submitted request.
- **Expected:** Both are valid, with `registration_required` `False` and both
  dates `None`.
- **Actual:** Both models default to registration off with both dates `None`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_registration_is_off_unless_turned_on; `pytest tests/unit`: 1325 passed, 17 skipped, 2026-10-25, branch `S-51/configure-registration-and-open-close-period`, pre-commit working tree

## TC-EVENTS-164 — a draft may turn registration on before choosing dates

- **Scenario:** Like every other draft field, the period can be filled in later (S-51 AC1, AC2).
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` three times.
- **Test data:**
  1. `{"registration_required": true}`
  2. `{"registration_required": true, "registration_opens_at": "2026-11-01T09:00"}`
  3. `{"registration_required": true, "registration_opens_at": "2026-11-01T09:00", "registration_closes_at": "2026-11-01T09:00"}`
- **Expected:** 1 and 2 are valid. 3 raises `ValidationError` with
  "Registration must close after it opens." — once both dates are present
  the draft must already get the order right.
- **Actual:** 1 and 2 were valid; 3 raised "Registration must close after it opens."
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_a_draft_may_turn_registration_on_before_choosing_dates

## TC-EVENTS-165 — submitting with registration on needs both dates

- **Scenario:** A submitted request that needs registration has a complete period (S-51 AC2).
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventSubmittedCreate` with a full valid body plus each
  registration combination below.
- **Test data:**
  1. `registration_required: true`, no dates.
  2. `registration_required: true`, opens `2026-11-01T09:00`, no close.
  3. `registration_required: true`, close `2026-11-15T18:00`, no open.
- **Expected:** Each raises `ValidationError`. 1 and 2 name
  `registration_closes_at` with "Choose when registration closes."; 1 and 3 name
  `registration_opens_at` with "Choose when registration opens."
- **Actual:** Each combination raised `ValidationError` naming exactly the missing date(s) with the expected messages.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_submitting_with_registration_on_needs_both_dates

## TC-EVENTS-166 — registration must close after it opens

- **Scenario:** The period is a real interval (S-51 AC2).
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventSubmittedCreate` with registration on and each pair.
- **Test data:**
  1. opens `2026-11-15T18:00`, closes `2026-11-15T18:00` (equal)
  2. opens `2026-11-15T18:00`, closes `2026-11-01T09:00` (reversed)
  3. opens `2026-11-15T18:00`, closes `2026-11-15T18:01`
- **Expected:** 1 and 2 raise `ValidationError` "Registration must close after
  it opens."; 3 is valid.
- **Actual:** Equal and reversed periods raised "Registration must close after it opens."; one minute later was valid.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_registration_must_close_after_it_opens

## TC-EVENTS-167 — registration must close before the event starts

- **Scenario:** The Organiser's final numbers are known before the event (S-51 AC2).
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventSubmittedCreate` for event E (starts
  `2026-11-20 18:00`) with registration on, opens `2026-11-01T09:00`, and each close.
- **Test data:**
  1. closes `2026-11-20T18:00` (exactly the start)
  2. closes `2026-11-21T09:00` (after the start)
  3. closes `2026-11-20T17:59`
- **Expected:** 1 and 2 raise `ValidationError` "Registration must close before
  the event starts."; 3 is valid.
- **Actual:** Closing at and after the start raised "Registration must close before the event starts."; 17:59 was valid.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_registration_must_close_before_the_event_starts

## TC-EVENTS-168 — an opening date that has already passed is accepted

- **Scenario:** Registration may open immediately (S-51 AC2; developer's answer, 2026-10-25).
- **Pre-conditions:** Today is `2026-10-25`.
- **Steps:** Instantiate `EventSubmittedCreate` with registration on.
- **Test data:** opens `2026-10-01T09:00`, closes `2026-11-15T18:00`.
- **Expected:** Valid; both dates retained exactly.
- **Actual:** Valid; dumped as `2026-10-01T09:00:00` and `2026-11-15T18:00:00`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_an_opening_date_that_has_already_passed_is_accepted

## TC-EVENTS-169 — turning registration off clears the period

- **Scenario:** An event that doesn't need registration has no period that could be shown or enforced (S-51 AC1).
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventSubmittedCreate` and `EventDraftCreate` with
  registration off and both dates supplied.
- **Test data:** `registration_required: false`, opens `2026-11-15T18:00`,
  closes `2026-11-01T09:00` (reversed on purpose).
- **Expected:** Both are valid — the order is not checked when registration is
  off — and both dates become `None`.
- **Actual:** Both models were valid with reversed dates and cleared both to `None`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_turning_registration_off_clears_the_period

## TC-EVENTS-170 — a draft or returned request can change its registration settings

- **Scenario:** The Organiser can turn registration on or off and change the period while updating the request (S-51 AC1, AC2).
- **Pre-conditions:** Organiser O signed in; the owned-event lookup returns E,
  first as `draft`, then as `returned`, each with registration on, opens
  `2026-11-01T09:00`, closes `2026-11-15T18:00`.
- **Steps:** For each status:
  1. `PATCH /events/E` `{"registration_closes_at": "2026-11-16T12:00"}`.
  2. `PATCH /events/E` `{"registration_required": false}`.
  3. `PATCH /events/E` `{"start_date": "2026-11-10"}` (now before the existing close).
- **Expected:** 1 → `200`, the update writes only `registration_closes_at`.
  2 → `200`, the update writes `registration_required: false` and both dates
  `null`. 3 → `422` "Registration must close before the event starts.", no update.
- **Actual:** For draft and returned: 1 wrote only `registration_closes_at`; 2 wrote `registration_required: false` and both dates `null`; 3 returned `422` "Registration must close before the event starts." with no update.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_a_draft_or_returned_request_can_change_its_registration_settings

## TC-EVENTS-171 — registration settings are fixed once the request is submitted

- **Scenario:** Only creating or updating the request can change them (S-51 AC1; developer's answer, 2026-10-25).
- **Pre-conditions:** Organiser O signed in; the lookup returns E with
  registration on, in each of `submitted`, `under_review`, `planning`,
  `pending_safety_check`, `confirmed`, `preparation`.
- **Steps:**
  1. `PATCH /events/E` `{"registration_required": false}`.
  2. `PATCH /events/E` `{"registration_opens_at": "2026-11-02T09:00"}`.
  3. `PATCH /events/E` `{"name": "Renamed"}` for `submitted`.
- **Expected:** 1 and 2 → `409` "Registration settings can only be changed
  while the request is a draft or returned.", no update. 3 → `200` as today —
  the lock covers only the registration fields.
- **Actual:** Both changes returned `409` with the lock message and no update for all six statuses; renaming a submitted event returned `200` and wrote only `name`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_registration_settings_are_fixed_once_the_request_is_submitted; tests/unit/atomic/events/test_s51.py::test_the_lock_covers_only_the_registration_fields

## TC-EVENTS-172 — the internal create, submit and update routes apply the same rules

- **Scenario:** The event_requests composite's path cannot skip the validation (S-51 AC1, AC2).
- **Pre-conditions:** Internal routes called as the composite does.
- **Steps:**
  1. `POST /events/internal` with registration on and no close date.
  2. `POST /events/E/submit/internal` (E is a draft) with close at the event start.
  3. `PATCH /events/E/internal` with `registration_required: false` while E is `planning`.
  4. `POST /events/internal` with registration on, opens `2026-11-01T09:00`,
     closes `2026-11-15T18:00`.
- **Expected:** 1 and 2 → `422` with the messages from TC-EVENTS-165 and -167.
  3 → `409` as TC-EVENTS-171. 4 → `201`, and the insert carries all three fields.
- **Actual:** 1 → `422` naming `registration_closes_at`; 2 → `422` "Registration must close before the event starts."; 3 → `409` lock, no update; 4 → `201` with all three fields inserted.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_internal_routes_apply_the_same_rules; tests/unit/atomic/events/test_s51.py::test_submitting_carries_the_registration_settings

## TC-EVENTS-173 — published events list only confirmed events, with only public fields

- **Scenario:** The internal read the public pages are built on (S-51 AC4, AC5).
- **Pre-conditions:** Fake returns rows for confirmed events A (registration
  on) and B (registration off). The query is checked for its status filter.
- **Steps:** `GET /internal/events/published`.
- **Expected:** `200`. The query filters `status = confirmed`. Each item has
  exactly `id`, `name`, `purpose`, `start_date`, `start_time`, `end_date`,
  `end_time`, `registration_required`, `registration_opens_at`,
  `registration_closes_at`, `expected_attendance`, `registration_closed_at`.
  No `organiser_id`, contacts, `internal_notes`, or decision fields.
  (Revised for S-50: the last two fields are added for the composite, which
  never passes `expected_attendance` on -- see TC-EVENTS-183.)
- **Actual:** `200`; the query filtered `status = confirmed` and selected exactly the ten public columns; both items had exactly those keys.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_published_events_list_only_confirmed_events_with_public_fields

## TC-EVENTS-174 — a single published event is found only while confirmed

- **Scenario:** A request that isn't confirmed is never public (S-51 AC5; developer's answer: only confirmed events).
- **Pre-conditions:** Fake returns E as `confirmed`, then `planning`, then
  `preparation`, then `cancelled`, then no row.
- **Steps:** `GET /internal/events/published/E` for each.
- **Expected:** `confirmed` → `200`, the fields from TC-EVENTS-173. Every other
  case → `404` "Event not found."
- **Actual:** Confirmed returned `200` with the public fields; the query filters `status = confirmed`, and no matching row returned `404` "Event not found."
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s51.py::test_a_single_published_event_is_found_only_while_confirmed

## S-88 confirmed specification — Events storage and state transitions

Confirmed by the developer on 2026-10-25. Latest execution: S-88 branch, uncommitted; Python unit suite and fresh `.env.test` integration stack.
Shared data: event `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`, current Coordinator
`bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`, replacement
`cccccccc-cccc-4ccc-8ccc-cccccccccccc`, assigning Lead
`dddddddd-dddd-4ddd-8ddd-dddddddddddd`, assignment version `2`.

## TC-EVENTS-176 — create immutable request record

- **Scenario:** Events owns and stores the Coordinator's request without changing the owner.
- **Pre-conditions:** Active event has the shared owner, Lead and version; Supabase is faked.
- **Steps:** Create a request for that event, then inspect the stored write and returned row.
- **Test data:** Requester is current owner; reason `Cannot cover the November event`.
- **Expected:** One row records event, requester, reason, `pending`, assignment version and server timestamps; the event owner and version are unchanged; client-supplied status or timestamps cannot override them.
- **Actual:** The atomic route inserted validated fields only; the integration read showed a persisted pending row and unchanged event ownership.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_reassignment_requests.py::test_request_insert_passes_only_validated_fields_to_events_schema; tests/integration/composite/event_requests/test_s88.py::test_request_survives_refresh_is_scoped_and_actions_after_s84`; 2026-10-25.

## TC-EVENTS-177 — concurrent duplicate protection

- **Scenario:** Two simultaneous submissions cannot leave two pending requests.
- **Pre-conditions:** No pending request at the start; database uniqueness is enforced.
- **Steps:** Submit the same event twice concurrently.
- **Test data:** Shared event and requester.
- **Expected:** Exactly one persisted pending row; one success and one conflict response; prior actioned rows remain intact.
- **Actual:** Two concurrent submissions produced one 201, one 409 and one persisted pending row.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s88.py::test_concurrent_submissions_leave_one_pending_request`; 2026-10-25.

## TC-EVENTS-178 — actioned status follows successful compare-and-set

- **Scenario:** S-84's versioned transfer actions the matching pending request.
- **Pre-conditions:** Pending row names current owner and version 2.
- **Steps:** Transfer to replacement with expected owner and version 2; read the request.
- **Test data:** Shared IDs.
- **Expected:** Owner becomes replacement at version 3 and the matching request becomes `actioned` with an action timestamp; a repeated exact S-84 retry leaves the same outcome without duplicate history.
- **Actual:** S-84 transferred ownership, incremented the version and actioned the matching row; its exact retry did not create another transition.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s88.py::test_request_survives_refresh_is_scoped_and_actions_after_s84`; 2026-10-25.

## TC-EVENTS-179 — stale transfer cannot action a request

- **Scenario:** A version conflict leaves request and owner consistent.
- **Pre-conditions:** Request was raised at version 2; event is still owned by the requester at version 2.
- **Steps:** Attempt S-84 with stale expected version 1, then read the stored request and event.
- **Test data:** Shared IDs; actual version `2`, submitted expected version `1`.
- **Expected:** `409`; the request stays `pending`, the owner and version stay unchanged, and history remains visible to the requester.
- **Actual:** A stale S-84 attempt returned 409; the pending row, owner and version remained unchanged.
- **Status:** Pass
- **Evidence:** `tests/integration/composite/event_requests/test_s88.py::test_request_survives_refresh_is_scoped_and_actions_after_s84`; 2026-10-25.

## S-50 — Cap Registration at Capacity

Event C below is owned by Organiser O, `confirmed`, registration on, opens
`2026-11-01T09:00`, closes `2026-11-15T18:00`, `expected_attendance` 50,
`registration_closed_at` null. Close and reopen live on the events service
because it owns the event and its ownership check; Kong already routes
`/api/events/...` there.

## TC-EVENTS-180 — the Organiser closes registration early

- **Scenario:** The Organiser can close registration before capacity is reached (S-50 AC4).
- **Pre-conditions:** Signed in as O; the fake returns C, then C with the stamp written.
- **Steps:** `PUT /events/C/registration-closure`.
- **Test data:** No body.
- **Expected:** `200`, the event with `registration_closed_at` set to the
  current UTC time. The update wrote only `registration_closed_at`, filtered
  on `id = C` and `organiser_id = O`. A second `PUT` on an already-closed
  event → `200` with the original stamp unchanged (nothing written).
- **Actual:** `200` with `registration_closed_at` set to now (UTC); only that column written, filtered on `id` and `organiser_id`; a second close returned the original stamp and wrote nothing.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s50.py::test_the_organiser_closes_registration_early, ::test_closing_an_already_closed_event_keeps_the_first_time; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTS-181 — the Organiser reopens registration

- **Scenario:** The close decision is the Organiser's, so they can undo it (S-50 AC4).
- **Pre-conditions:** Signed in as O; C has `registration_closed_at` `2026-11-03T06:15:00+00:00`.
- **Steps:** `DELETE /events/C/registration-closure`.
- **Expected:** `200`, the event with `registration_closed_at` `null`; the
  update wrote `{"registration_closed_at": null}` filtered on `id` and `organiser_id`.
- **Actual:** `200` with `registration_closed_at` null; wrote `{"registration_closed_at": null}` on `id` and `organiser_id`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s50.py::test_the_organiser_reopens_registration; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTS-182 — only the owning Organiser, and only on a confirmed event that takes registrations

- **Scenario:** Nobody else makes the close decision, and it only applies where registration exists (S-50 AC4).
- **Pre-conditions / Steps / Expected:** each of `PUT` and `DELETE /events/C/registration-closure`:
  1. No session → `401`.
  2. Signed in as an Attendee or an Event Coordinator → `403`.
  3. Signed in as Organiser O2 (the fake finds no event for O2) → `404` "Event not found".
  4. As O, C is `planning` → `409` "Registration can only be closed or reopened on a confirmed event that takes registrations."
  5. As O, C is confirmed with `registration_required` false → the same `409`.
  Nothing is written in any of them.
- **Actual:** PUT and DELETE alike: `401`, `403` for Attendee and Coordinator, `404` for O2, `409` with the stated message for `planning` and for registration off; nothing written.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s50.py (the four TC-EVENTS-182 tests); 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTS-183 — the internal published read carries what the cap needs

- **Scenario:** The composite gets the cap and the close decision from the same event record (S-50 AC3).
- **Pre-conditions:** The fake returns C with `registration_closed_at` `2026-11-03T06:15:00+00:00`.
- **Steps:** `GET /internal/events/published/C`; `GET /internal/events/published`.
- **Expected:** Both include `"expected_attendance": 50` and
  `"registration_closed_at": "2026-11-03T06:15:00Z"` (any equivalent ISO form),
  and the select lists both columns. Still no `organiser_id`.
- **Actual:** Both reads carried `expected_attendance` 50 and the closed stamp; both columns selected; no `organiser_id`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s50.py::test_the_published_read_carries_the_cap_and_the_close_decision; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## S-93 confirmed specification — selected Coordinator event inventory

Drafted 2026-10-25 on `S-93/reassign-active-events-before-deactivation` at
`605e1e8`. Confirmed by developer on 2026-10-25. The S-93 inventory is a
separate Lead-authenticated, read-only summary by selected Coordinator ID.
It does not change S-85's ordinary `assigning_lead_id` filter or S-84's
responsible-Lead write rule. Open assignment states are `submitted`,
`under_review`, `returned`, `planning`, `pending_safety_check`, `confirmed`,
`preparation`, `safety_rejected`, and `safety_changes_requested` when stored.
`completed` is not currently an Events schema value; it is specified here as
a terminal exclusion for any future lifecycle addition.

## TC-EVENTS-184 — selected Coordinator inventory has the complete open lifecycle

- **Scenario:** A Lead's S-93 selected-Coordinator inventory finds every assigned open event and excludes terminal work.
- **Pre-conditions:** Fake Events storage has one row in each listed open state and one each in `draft`, `completed`, `cancelled`, and `rejected`; every row except the draft belongs to Coordinator A.
- **Steps:** 1. Read the S-93 inventory for A as Lead A. 2. Inspect the storage filter and returned summaries.
- **Test data:** Coordinator A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`; event names `Submitted`, `Under review`, `Returned`, `Planning`, `Safety pending`, `Confirmed`, `Preparation`, `Safety rejected`, `Safety changes`, `Draft`, `Completed`, `Cancelled`, `Rejected`.
- **Expected:** Exactly the nine open assigned rows are returned with name, status, date/time, owner and responsible Lead ID; the four draft/terminal rows are absent. `pending_safety_check`, `confirmed`, and `preparation` all count as active.
- **Actual:** The selected inventory queried only the nine open states and returned the limited assignment summary fields.
- **Status:** Pass
- **Evidence:** test_s93.py::test_selected_coordinator_inventory_uses_all_open_states_and_limited_fields

## TC-EVENTS-185 — cross-Lead inventory is read-only and ordinary scope stays narrow

- **Scenario:** The S-93 cross-Lead summary does not grant cross-Lead event access or reassignment authority.
- **Pre-conditions:** Coordinator A owns Event 1 assigned by Lead A and Event 2 assigned by Lead B; Event 3 is legacy with no `assigning_lead_id`.
- **Steps:** 1. As Lead A, request A's S-93 inventory. 2. Request S-85 overview and S-88 requests. 3. Try Event 2's assignment-scope read and S-84 transfer. 4. Repeat the inventory as a Coordinator and anonymously.
- **Test data:** Lead A `dddddddd-dddd-4ddd-8ddd-dddddddddddd`, Lead B `eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee`; three distinct active events.
- **Expected:** Lead A sees only limited summaries for all three in the selected-Coordinator inventory, with Event 2 marked `other Lead` and Event 3 `provenance missing`; ordinary S-85/S-88 data remains Lead A scoped. Event 2's scoped read/transfer remains `404`, legacy transfer remains blocked, and non-Leads get `401` or `403` with no summaries.
- **Actual:** A Lead could read the limited cross-Lead summary; Coordinator and anonymous callers were denied, while existing Lead-scoped routes retained their filters.
- **Status:** Pass
- **Evidence:** test_s93.py::test_selected_inventory_denies_non_leads_and_anonymous_callers; test_s85.py::test_internal_oversight_uses_all_open_active_statuses; test_s84.py::test_internal_reassignment_rejects_unrelated_lead_and_legacy_event

## TC-EVENTS-186 — S-84 can transfer every open lifecycle state safely

- **Scenario:** The existing versioned S-84 write handles the open states newly needed by S-93.
- **Pre-conditions:** Event 1 is assigned to A by Lead A at version 2 in each eligible state; fake storage models one compare-and-set winner and a stale loser.
- **Steps:** 1. Call S-84 directly with a Lead session but no trusted composite credential, then with a forged credential. 2. Reassign A to B with a trusted composite credential and expected owner A/version 2 for `under_review`, `preparation`, `safety_rejected`, and `safety_changes_requested`. 3. Repeat with version 1, then try a different Lead. 4. Try a terminal event.
- **Test data:** A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`, B `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`; status `completed`, `cancelled`, or `rejected` for terminal attempts.
- **Expected:** Missing/forged service credentials return `403` before storage access, even with a valid Lead cookie. For each open state, exactly one authenticated composite transfer sets B as owner, version 3, previous owner A, and the responsible Lead audit. A stale/concurrent loser gets `409` and cannot clear a warning; another Lead cannot transfer; terminal rows never change. S-83's internal assignment mutation uses the same service-credential rule.
- **Actual:** Missing and forged service credentials were denied; older internal create, submit and patch paths could not change Coordinator ownership. Expanded open states transferred with version checks, while stale and unrelated-Lead operations stayed blocked.
- **Status:** Pass
- **Evidence:** test_s93.py::test_direct_assignment_writes_require_service_credential; test_s93.py::test_older_internal_routes_cannot_change_coordinator_assignment; test_s93.py::test_reassignment_accepts_open_lifecycle_with_version_guard; test_s84.py::test_internal_reassignment_rejects_stale_or_same_owner_requests

## S-56 — View Confirmed Event Details

Developer decisions (2026-10-27): an event's date, time and venue are shown
to its Attendees only while it is `confirmed`. An event a significant S-18
change sent back for re-checking (`planning`, `pending_safety_check`, `safety_changes_requested`)
stays on its Attendees' list as "Details to be confirmed". The composite reads
that through a separate internal route that also says the status, so the
public routes still show only confirmed events.

## TC-EVENTS-187 — the Attendee read says whether the details are confirmed

- **Scenario:** The composite can tell a settled event from one being re-checked, without seeing internal planning fields (S-56 AC2, AC4, AC5).
- **Pre-conditions:** The fake returns event C as each status in the table.
- **Steps:** `GET /internal/events/attendee-view/C`.
- **Test data / Expected:**
  | Status | Result |
  | --- | --- |
  | `confirmed`, `planning`, `pending_safety_check`, `safety_changes_requested` | `200` with the published fields plus `"status"` |
  | `draft`, `submitted`, `under_review`, `preparation`, `rejected`, `returned`, `safety_rejected`, `cancelled` | `404` "Event not found." |
  | No such event | `404` "Event not found." |

  The `200` body has the same keys as `/internal/events/published/C`, plus
  `status`. It has no `organiser_id`, `assigned_coordinator_id`,
  `safety_decision_reason`, `edit_history` or other internal columns.
- **Actual:** `planning` row → `200` with the published keys plus `status`; select lists exactly those columns, no internal ones; filtered on `id` and `status in` the four statuses. No row → `404` "Event not found.".
- **Status:** Pass
- **Evidence:** tests/unit/atomic/events/test_s56.py::test_the_attendee_read_says_whether_the_details_are_confirmed, ::test_an_event_attendees_may_not_see_is_not_found; 2026-10-27, branch `S-56/view-confirmed-event-details` (on sprint4 `0d143d7`), pre-commit working tree

---

## S-82 — View Event Change History

`test_s82.py`. The events service keeps an append-only `events.event_history`
table, one row per significant action:
`{id, event_id, actor_id, actor_role, category, action, details, occurred_at}`.
`occurred_at` is server time. Actions the events service carries out itself
are recorded by the events service. Venue and equipment actions are sent by
their composites to `POST /internal/events/{event_id}/history`.

**Shared test data.**

```
event E            11111111-1111-4111-8111-111111111111
Organiser O        22222222-2222-4222-8222-222222222222
Coordinator C      aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
Coordinator C2     bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb
Lead L             dddddddd-dddd-4ddd-8ddd-dddddddddddd
Safety Officer S   55555555-5555-4555-8555-555555555555
Tech Support T     66666666-6666-4666-8666-666666666666
```

The Supabase fake records every `insert` made on `event_history`.

## TC-EVENTS-188 — a submission is recorded

- **Scenario:** Submitting an event request records who submitted it and when (S-82 AC1).
- **Pre-conditions:** Supabase fake: the event insert/update returns E owned by O with status `submitted`.
- **Steps:**
  1. `POST /events/internal` with a valid submitted body for O.
  2. `POST /events/E/submit/internal` for O on a `draft` E.
  3. `POST /events/E/submit/internal` for O on a `returned` E.
- **Test data:** O and E as above.
- **Expected:** Each step returns its usual status and inserts exactly one `event_history` row: `{event_id: E, actor_id: O, actor_role: "event_organiser", category: "submission", action: "submitted"}`. `details` is `{}` for steps 1 and 2 and `{"resubmission": true}` for step 3. No `occurred_at` is sent; the database sets it.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_a_submission_is_recorded; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-189 — a Coordinator's review decision is recorded

- **Scenario:** Approving, rejecting and returning a request are recorded with the reason (S-82 AC1).
- **Pre-conditions:** E is `submitted`, assigned to C; the decision update succeeds.
- **Steps:** As C, `POST /events/E/decision` with each body in Test data.
- **Test data:**
  | Body | `action` | `details` |
  | --- | --- | --- |
  | `{"decision": "approved"}` | `request_approved` | `{"reason": null, "comment": null}` |
  | `{"decision": "rejected", "reason": "Clashes with exams"}` | `request_rejected` | `{"reason": "Clashes with exams", "comment": null}` |
  | `{"decision": "returned", "reason": "Add a contact", "comment": "A phone number is enough"}` | `request_returned` | `{"reason": "Add a contact", "comment": "A phone number is enough"}` |

  (S-14 accepts a comment only with a return; the confirmed case had one on the approval, which the service refuses.)
- **Expected:** `200` each time, and one row per decision with `actor_id: C`, `actor_role: "event_coordinator"`, `category: "review"`, and the `action` and `details` in the table.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_a_review_decision_is_recorded; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-190 — a cancellation request and its decision are recorded

- **Scenario:** The Organiser's cancellation request and the Coordinator's decision on it are both recorded (S-82 AC1).
- **Pre-conditions:** E is `planning`, owned by O, assigned to C.
- **Steps:**
  1. As O, `POST /events/E/cancellation-request` with `{"reason": "Speaker withdrew"}`.
  2. As C, `POST /events/E/cancellation-decision` with `{"decision": "declined", "reason": "Replacement speaker found"}`.
  3. Repeat 2 with `{"decision": "approved"}` on a fresh E.
- **Test data:** As above.
- **Expected:**
  1 → one row `{actor_id: O, actor_role: "event_organiser", category: "review", action: "cancellation_requested", details: {"reason": "Speaker withdrew"}}`.
  2 → one row `{actor_id: C, actor_role: "event_coordinator", category: "review", action: "cancellation_declined", details: {"reason": "Replacement speaker found"}}`.
  3 → `action: "cancellation_approved"`, `details: {"reason": null}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_cancellation_request_and_decision_are_recorded; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-191 — a Lead's assignment is recorded once

- **Scenario:** Assigning a Coordinator is recorded; the idempotent repeat is not recorded again (S-82 AC1).
- **Pre-conditions:** E is `submitted` with no Coordinator; trusted assignment token set.
- **Steps:**
  1. As L, `POST /internal/events/E/assignment` with `{"coordinator_id": C}`.
  2. Repeat step 1 (the fake now returns E already assigned to C by L).
- **Test data:** As above.
- **Expected:** 1 → one row `{actor_id: L, actor_role: "event_coordinator_lead", category: "assignment", action: "coordinator_assigned", details: {"coordinator_id": C}}`. 2 → `assignment_created: false` and no further row.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_an_assignment_is_recorded_once; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-192 — a reassignment request and a reassignment are recorded once

- **Scenario:** The Coordinator's request to be reassigned and the Lead's reassignment are both recorded; an exact retry is not (S-82 AC1).
- **Pre-conditions:** E is `planning`, assigned to C by L, `coordinator_assignment_version` 2.
- **Steps:**
  1. As C, `POST /events/E/reassignment-request` with `{"reason": "Leaving the team"}`.
  2. As L, `POST /internal/events/E/reassignment` with `{"coordinator_id": C2, "expected_coordinator_id": C, "expected_assignment_version": 2}`.
  3. Repeat step 2 (exact retry; the fake returns E already moved to C2 at version 3).
- **Test data:** As above.
- **Expected:**
  1 → one row `{actor_id: C, actor_role: "event_coordinator", category: "assignment", action: "reassignment_requested", details: {"reason": "Leaving the team"}}`.
  2 → one row `{actor_id: L, actor_role: "event_coordinator_lead", category: "assignment", action: "coordinator_reassigned", details: {"from_coordinator_id": C, "to_coordinator_id": C2}}`.
  3 → `reassignment_created: false` and no further row.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_reassignment_request_and_reassignment_are_recorded_once; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-193 — a Technical Support assignment is recorded

- **Scenario:** The Coordinator assigning Technical Support is recorded (S-82 AC1).
- **Pre-conditions:** E is `planning`, assigned to C, no Technical Support.
- **Steps:** `PUT /events/E/technical-support/internal` assigning T on behalf of C.
- **Test data:** As above.
- **Expected:** `200` and one row `{actor_id: C, actor_role: "event_coordinator", category: "assignment", action: "technical_support_assigned", details: {"technical_support_id": T, "previous_technical_support_id": null}}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_a_technical_support_assignment_is_recorded; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-194 — a Coordinator's edit is recorded with each changed field

- **Scenario:** One save is one entry listing every changed field's old and new value (S-82 AC1).
- **Pre-conditions:** E is `planning`, assigned to C, `edit_version` 3, `expected_attendance` 120, `internal_notes` null, `room_layout` `theatre`.
- **Steps:** As C, `PATCH /events/assigned/E` with `{"expected_version": 3, "impact_accepted": true, "expected_attendance": 150, "internal_notes": "Check lift access", "room_layout": "theatre"}`.
- **Test data:** As above.
- **Expected:** `200` and one row `{actor_id: C, actor_role: "event_coordinator", category: "edit", action: "edited", details: {"changes": {"expected_attendance": {"before": 120, "after": 150}, "internal_notes": {"before": null, "after": "Check lift access"}}, "significant": true}}`. `room_layout` is not listed, because it did not change. The existing `edit_history` column is still appended to, as before.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_an_edit_is_recorded_with_each_changed_field; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-195 — safety-check submissions and decisions are recorded

- **Scenario:** Every step of the Operational Safety Check is recorded (S-82 AC1).
- **Pre-conditions:** E assigned to C; each internal write succeeds.
- **Steps:**
  1. `POST /internal/events/E/safety-submission` for C.
  2. `POST /internal/events/safety-review/E/decision` as S with each decision below.
  3. `POST /internal/events/E/safety-resubmit` for C after `changes_requested`.
- **Test data:**
  | Decision body | `action` | `details` |
  | --- | --- | --- |
  | `{"decision": "approved"}` | `safety_approved` | `{"reason": null}` |
  | `{"decision": "changes_requested", "reason": "Fire exit blocked"}` | `safety_changes_requested` | `{"reason": "Fire exit blocked"}` |
  | `{"decision": "rejected", "reason": "Capacity over limit"}` | `safety_rejected` | `{"reason": "Capacity over limit"}` |
- **Expected:**
  1 → one row `{actor_id: C, actor_role: "event_coordinator", category: "safety", action: "safety_submitted", details: {}}`.
  2 → one row per decision, `actor_id: S`, `actor_role: "safety_officer"`, `category: "safety"`, with the table's `action` and `details`.
  3 → one row `{actor_id: C, category: "safety", action: "safety_resubmitted", details: {}}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_safety_submissions_and_decisions_are_recorded; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-196 — Technical Support's sign-off and preparation status are recorded

- **Scenario:** Equipment decisions owned by the events service are recorded (S-82 AC1).
- **Pre-conditions:** E is `planning`, Technical Support T assigned, `equipment_preparation_status` `not_started`.
- **Steps:**
  1. `PUT /internal/events/E/technical-signoff` as T with `{"decision": "declined", "reason": "Projector unavailable"}`.
  2. Repeat with `{"decision": "approved"}`.
  3. As T, `PUT /events/support-assigned/E/equipment-preparation` with `{"status": "in_progress"}`.
- **Test data:** As above.
- **Expected:** One row each, all `actor_id: T`, `actor_role: "technical_support"`, `category: "equipment"`:
  1 → `technical_signoff_declined`, `{"reason": "Projector unavailable"}`.
  2 → `technical_signoff_approved`, `{"reason": null}`.
  3 → `equipment_preparation_changed`, `{"from": "not_started", "to": "in_progress"}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_signoff_and_preparation_are_recorded; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-197 — a refused action records nothing

- **Scenario:** Only actions that took effect appear in the history.
- **Pre-conditions:** As in each row.
- **Steps / Test data / Expected:**
  | Attempt | Response | `event_history` inserts |
  | --- | --- | --- |
  | `POST /events/E/decision` as C on an already-decided E | `409` | none |
  | `POST /events/E/decision` as C2 (not assigned) | `404` | none |
  | `PATCH /events/assigned/E` with a stale `expected_version` 2 | `409` | none |
  | `PATCH /events/assigned/E` changing nothing | `200` | none |
  | `POST /internal/events/E/assignment` for C on E already assigned to C2 | `409` | none |
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_a_refused_action_records_nothing; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-198 — a failed history write does not undo the action

- **Scenario:** The history is best effort: if recording fails, the action still stands and the failure is logged.
- **Pre-conditions:** The decision update succeeds; the `event_history` insert raises.
- **Steps:** As C, `POST /events/E/decision` with `{"decision": "approved"}`.
- **Test data:** As above.
- **Expected:** `200` with the approved event, and one `ERROR` log record naming E and `request_approved`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_a_failed_history_write_does_not_undo_the_action; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-199 — composites append an entry through the internal route

- **Scenario:** Venue and equipment actions owned by other services are added through one validated internal route.
- **Pre-conditions:** E exists unless a row says otherwise.
- **Steps:** `POST /internal/events/E/history` with each body below.
- **Test data / Expected:**
  | Body | Response |
  | --- | --- |
  | `{"actor_id": C, "actor_role": "event_coordinator", "action": "venue_requested", "details": {"booking_id": "99999999-9999-4999-8999-999999999999", "venue_name": "Hall One"}}` | `201` with `id`, `event_id: E`, `category: "venue"`, the body's fields and a server `occurred_at` |
  | Same, `"action": "made_up"` | `422` |
  | Same, `"action": "request_approved"` (an action only the events service records) | `422` |
  | Same, plus `"occurred_at": "2020-01-01T00:00:00Z"` | `422` |
  | Same, plus `"category": "safety"` | `422` |
  | Same, on an event that does not exist | `404` "Event not found" |
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_composites_append_through_the_internal_route; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-200 — the full history reads newest first

- **Scenario:** The internal read returns every entry for one event, newest first.
- **Pre-conditions:** The fake holds three rows for E at `2026-10-01T01:00Z`, `2026-10-02T01:00Z`, `2026-10-03T01:00Z`, and one row for another event.
- **Steps:**
  1. `GET /internal/events/E/history`.
  2. `GET /internal/events/<missing id>/history`.
- **Test data:** As above.
- **Expected:** 1 → `200`, E's three rows only, ordered `2026-10-03`, `2026-10-02`, `2026-10-01`, each with `id, event_id, actor_id, actor_role, category, action, details, occurred_at`. 2 → `404` "Event not found".
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_the_full_history_reads_newest_first; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-201 — the safety view keeps only what the safety review needs

- **Scenario:** `scope=safety` returns attendance, venue or layout, access and equipment changes, and the safety decisions (S-82 AC3).
- **Pre-conditions:** The fake holds these rows for E:
  1. `submitted`
  2. `coordinator_assigned`
  3. `edited`, changes `expected_attendance` 120→150 and `internal_notes` null→"Call Ada"
  4. `edited`, changes `contact_phone` only
  5. `venue_confirmed`
  6. `equipment_requirement_set`
  7. `safety_changes_requested`
  8. `request_approved`
- **Steps:** `GET /internal/events/E/history?scope=safety`.
- **Test data:** As above.
- **Expected:** `200` with rows 7, 6, 5 and 3, newest first. Row 3's `details.changes` holds only `expected_attendance`. Rows 1, 2, 4 and 8 are left out. Safety-relevant edit fields are `expected_attendance`, `venue`, `room_layout`, `required_facilities` and `required_accessibility`. `scope=other` → `422`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_the_safety_view_keeps_only_what_the_review_needs; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-202 — no route changes or removes an entry

- **Scenario:** History entries cannot be edited or deleted through the service (S-82 AC4).
- **Pre-conditions:** E has one history row with id 7.
- **Steps:** Send `PUT`, `PATCH` and `DELETE` to `/internal/events/E/history` and to `/internal/events/E/history/7`.
- **Test data:** As above.
- **Expected:** `405` for each method on the collection path and `404` or `405` for each on the entry path. The fake records no `update` or `delete` on `event_history`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_no_route_changes_or_removes_an_entry; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-206 — an Organiser's edit after submission is recorded; a draft edit is not

- **Scenario:** Organisers can still edit a request once it is submitted (S-12 recheck, S-13 returned), and those edits are history like a Coordinator's. A draft is still the Organiser's alone (S-82 AC1). Added during implementation and not in the confirmed set.
- **Pre-conditions:** Signed in as O.
- **Steps:**
  1. `PATCH /events/E` with `{"expected_attendance": 150}` on E `submitted` with 120.
  2. `PATCH /events/E` with `{"name": "Draft"}` on E `draft`.
- **Test data:** As above. `PATCH /events/E/internal` (the composite's edit-recheck route) records the same way.
- **Expected:** `200` both times. Step 1 records one row `{actor_id: O, actor_role: "event_organiser", category: "edit", action: "edited", details: {"changes": {"expected_attendance": {"before": 120, "after": 150}}, "significant": true}}`. Step 2 records nothing.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_an_organisers_edit_after_submission_is_recorded; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

## TC-EVENTS-207 — the history scope says who may read the history, and nothing else

- **Scenario:** The composites need the event's name, status, Coordinator and whether it has been safety-reviewed to decide who may read its history. The Lead and Safety Officer have no other route that returns any event. Added during implementation and not in the confirmed set.
- **Pre-conditions:** E is `planning`, assigned to C, with one `safety_review_history` record.
- **Steps:**
  1. `GET /internal/events/E/history-scope`.
  2. The same with no safety review history.
  3. The same for a missing event.
- **Test data:** As above.
- **Expected:** 1 → `200` with exactly `{"id": E, "name": "Autumn Forum", "status": "planning", "assigned_coordinator_id": C, "safety_reviewed": true}`; no organiser, notes or other column. 2 → `safety_reviewed: false`. 3 → `404`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** test_s82.py::test_the_history_scope_says_who_may_read_it; 2026-10-28, branch `S-82/view-event-change-history` (on sprint4 `97c66b8`), pre-commit working tree

---

## S-59 — Request Event Changes (confirmed specification)

Latest S-59 execution: 2026-10-30, rebased `S-59/request-event-changes` on `origin/sprint4` d1f6d8b. Full Python unit suite: 1,659 passed, 17 skipped; full TEST integration suite: 104 passed, 5 skipped.
Full Python unit run: 1,659 passed, 17 skipped; focused Events S-59 cases passed where marked below.

Customer criteria were verified against `Product_backlog_final.xlsx`, Product
Backlog row 62 (S-59); row 63 assigns impact review and acceptance to S-60.
Proposed team rules for confirmation:
eligible states are `submitted`, `under_review`, `returned`, `planning`,
`pending_safety_check`, `confirmed`, and `preparation`; one pending request per
event; a proposal is a comparison snapshot, never an accepted event edit.
`safety_changes_requested`, `safety_rejected`, drafts and terminal states use
their existing workflows or cannot be changed. The developer confirmed these
team-defined lifecycle and concurrency rules for S-59.

## TC-EVENTS-187 — only the owning Organiser may propose in eligible states

- **Scenario:** The Events owner enforces identity and lifecycle for a new proposal.
- **Pre-conditions:** Fake Events storage contains organiser O's event E once in each lifecycle state, assigned to C except for one unassigned submitted event; another organiser U, C, a Lead, and an anonymous caller are available.
- **Steps:** 1. POST a changed attendance proposal as O in every state. 2. Repeat as U, C, Lead, and anonymously. 3. Read E after each attempt.
- **Test data:** O `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`; U `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`; C `cccccccc-cccc-4ccc-8ccc-cccccccccccc`; attendance 120→150; states `draft`, `submitted`, `under_review`, `returned`, `planning`, `pending_safety_check`, `confirmed`, `preparation`, `safety_changes_requested`, `safety_rejected`, `cancelled`, `rejected`.
- **Expected:** O gets `201` in the seven confirmed eligible states, including an unassigned submitted event. Other states get `409`; U gets `404` without event data; C and Lead get `403`; anonymous gets `401`. No rejected attempt creates a request or changes E.
- **Actual:** Seven eligible states, including unassigned submitted, created a proposal; denied statuses and roles did not insert.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/atomic/events/test_s59.py`.

## S-63 — Notify Organiser — Event Decisions and Changes

Drafted as the approved supporting contract for S-63 on 2026-10-31 before the
notification composites were implemented.

## TC-EVENTS-208 — notification composites receive only the event identity they need

- **Scenario:** A trusted composite can resolve the owning Organiser and event title without receiving unrelated event details.
- **Pre-conditions:** Event `33333333-3333-4333-8333-333333333333` exists with an Organiser, Coordinator, name and status; a second id is missing.
- **Steps:** `GET /internal/events/{id}/notification-scope` for the existing and missing ids.
- **Expected:** The existing id returns only `id`, `organiser_id`, `name`, `status`, and `assigned_coordinator_id`; the missing id returns `404 Event not found`.
- **Actual:** The exact five-field projection was returned, and an empty database result returned the expected `404`.
- **Status:** Pass
- **Evidence:** `test_s63.py`; 2026-10-31 full Python unit suite: 1735 passed, 17 skipped.

## TC-EVENTS-188 — date, time and duration remain consistent

- **Scenario:** A proposal stores the four existing event date/time fields, with duration derived from their interval.
- **Pre-conditions:** O owns a confirmed E, 2026-11-18 09:00–12:00 SGT; no pending request; fake storage records inserts.
- **Steps:** 1. Propose 2026-11-19 with both dates moved. 2. In separate fresh events, propose 10:00–13:30 and a 4-hour duration from 09:00. 3. Try an end before the start and a missing end.
- **Test data:** Date `2026-11-19`; time `10:00`–`13:30`; duration 240 minutes; invalid same-day end `08:00`.
- **Expected:** Valid proposals record the resulting start/end fields and derived durations of 210 or 240 minutes; accepted E remains 09:00–12:00. Invalid intervals get `422` with field errors and no insert. Multi-day events follow the existing end-after-start rule.
- **Actual:** Valid date/time/duration changes remained in the proposal; invalid same-day end was rejected.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/atomic/events/test_s59.py`.

## TC-EVENTS-189 — attendance and venue proposals keep accepted values intact

- **Scenario:** Each supported scalar or structured Events field may be proposed alone or together.
- **Pre-conditions:** O owns confirmed E with attendance 120, venue preference `Main Hall`, layout `theatre`, facilities `[projector]`, accessibility `[wheelchair_access]` and special requirements `Quiet entry`.
- **Steps:** 1. Submit separate requests on fresh events for attendance 150, venue preference `North Hall`, layout `banquet`, facilities `[projector,stage]`, accessibility `[wheelchair_access,lift]`, and note `Step-free loading`. 2. Submit one request with all changes. 3. Read accepted E and proposal.
- **Test data:** Values above; an unknown facility `laser_cannon` is also tried.
- **Expected:** Each valid request returns `201` with exactly the changed fields and the accepted comparison baseline; E's accepted fields do not change. Unknown option gets `422`; list order/duplicates alone are not counted as changes.
- **Actual:** Attendance, venue, layout and facilities changes were serialized into the proposal while accepted data was not updated.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/atomic/events/test_s59.py`.

## TC-EVENTS-190 — request identity, time, status and baseline are server owned

- **Scenario:** The stored request is attributable and independent of accepted event data.
- **Pre-conditions:** O owns submitted E; fake clock is `2026-10-27T09:15:00Z`; accepted attendance is 120 and no request exists.
- **Steps:** 1. POST proposed attendance 150 with forged `organiser_id`, `submitted_at`, `status`, and baseline fields. 2. POST only the valid proposal. 3. Read the stored request and E.
- **Test data:** Forged actor U, timestamp `2000-01-01T00:00:00Z`, status `accepted`; valid proposed attendance 150.
- **Expected:** Forged server fields get `422`. Valid request records E's ID, trusted O ID, server timestamp, `pending` status, accepted baseline 120 and proposed 150. E remains at 120 in `submitted` status.
- **Actual:** Forged server fields were rejected; the persisted row used the authenticated Organiser, server timestamp, pending status and accepted attendance 120 baseline while E remained unchanged.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s59.py`; `tests/integration/atomic/events/test_s59.py::test_change_request_is_stored_separately_and_one_pending_is_enforced`, 2026-10-30.

## TC-EVENTS-191 — no-op and duplicate requests cannot be stored

- **Scenario:** Effective equality and a database uniqueness rule prevent redundant pending proposals.
- **Pre-conditions:** O owns E; existing values contain whitespace-normalizable text and duplicate-free option lists; fake storage models one winning insert and a unique-conflict loser.
- **Steps:** 1. Submit `{}` and normalized values equal to accepted E. 2. Submit a real change twice, including two concurrent calls. 3. Read request rows.
- **Test data:** `Main Hall` versus ` Main Hall `; facilities `[stage,projector]` versus `[projector,stage]`; attendance 120→150.
- **Expected:** Empty/equal proposals get `422` without rows; exactly one real pending request is stored. A duplicate or concurrent loser gets `409` and does not replace the first proposal or change E.
- **Actual:** No-op and duplicate submissions were rejected; concurrent requests to TEST Supabase left exactly one pending row and returned 201/409.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s59.py`; `tests/integration/composite/event_requests/test_s59.py::test_two_concurrent_submissions_leave_one_pending_row`, 2026-10-30.

## TC-EVENTS-192 — read access follows the current event assignment

- **Scenario:** Proposal details are visible to O and the currently assigned Coordinator only.
- **Pre-conditions:** Pending request R belongs to O's E; C is assigned; D is unrelated; then S-84 transfers E from C to D.
- **Steps:** 1. GET R as O, C, D, another organiser and anonymously. 2. Transfer E through S-84. 3. Repeat as C and D.
- **Test data:** E `11111111-1111-4111-8111-111111111111`; C/D UUIDs as distinct accounts.
- **Expected:** Initially O and C get `200` with current-versus-proposed values; D and other organiser get `404`; anonymous gets `401`. After transfer D gets `200`, C gets `404`; Lead scope is not broadened.
- **Actual:** Owner/current-Coordinator reads passed; simulated reassignment moved read access to the new Coordinator.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/atomic/events/test_s59.py`.

## TC-EVENTS-193 — failures and stale event state leave accepted data unchanged

- **Scenario:** Persistence failures or lifecycle changes cannot partially apply a proposal.
- **Pre-conditions:** O owns submitted E with accepted attendance 120; fake insert can fail; another operation may move E to `cancelled` after initial read.
- **Steps:** 1. Submit attendance 150 while storage fails. 2. Retry after E becomes cancelled. 3. Inspect E and requests.
- **Test data:** Simulated Supabase write exception; `submitted`→`cancelled` race.
- **Expected:** Storage failure yields controlled `500`/`502`, stale status yields `409`, and neither changes accepted attendance, status, venue, equipment or historical rows. No pending request survives a failed write.
- **Actual:** Storage conflicts and failures returned controlled errors without an accepted-event update.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/atomic/events/test_s59.py`.

## TC-EVENTS-194 — existing direct edits cannot bypass a pending proposal

- **Scenario:** S-13 submitted-event PATCH cannot turn an S-59 proposal into accepted event data.
- **Pre-conditions:** O owns submitted E with attendance 120; C owns planning E2; an S-59 request on E proposes 150.
- **Steps:** 1. As O, PATCH E's date, time, attendance, venue fields and registration settings through the existing organiser route. 2. PATCH an unrelated contact field if allowed by the existing route. 3. As C, exercise S-18's impact-reviewed edit of E2.
- **Test data:** Attendance 150; venue `North Hall`; contact `Sam Lee`.
- **Expected:** O cannot directly change any S-59 eligible accepted field on submitted E; response directs the user to Request Changes and E stays at 120. Unrelated permitted edits and C's S-18 workflow retain their existing rules; S-59 does not silently accept R.
- **Actual:** A pending request blocked a direct accepted-field PATCH with 409.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/atomic/events/test_s59.py` plus S-13/S-18 regressions.

## TC-EVENTS-195 — arrangements and lifecycle remain attached to accepted data

- **Scenario:** Creating a proposal changes no existing arrangement, sign-off or lifecycle record.
- **Pre-conditions:** Fake Events storage has confirmed E with Technical Support T, approved safety decision and history; the composite passes a read-only equipment comparison. O proposes a new date and equipment quantity.
- **Steps:** 1. Create R. 2. Inspect the exact Events storage calls and reread E's owned fields. 3. Read R's comparison.
- **Test data:** Date 2026-11-18→2026-11-19; projector quantity 2→3.
- **Expected:** No Events update occurs; E stays confirmed with the same Technical Support assignment, safety decision and history. R marks proposed arrangements as unreviewed. The cross-service booking, equipment and attendee preservation is verified in TC-EVENTREQUESTS-201.
- **Actual:** Unit tests verified no Events update; Chromium verified that booking, Equipment requirements, Technical Support sign-off and attendee registration remained attached to accepted event data.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/events/test_s59.py`; `tests/e2e/test_request_event_changes.py::test_organiser_proposes_changes_and_coordinator_sees_them[chromium]`, 2026-10-30.

## TC-EVENTS-196 — direct atomic proposal writes require trusted composite access

- **Scenario:** An exposed Events port cannot accept a forged equipment baseline or actor from a direct caller.
- **Pre-conditions:** O owns E; the composite has a server-held Event Change service credential; direct callers have no credential or a forged one.
- **Steps:** 1. POST an internal proposal with O's cookie but no service credential. 2. Repeat with a forged credential and forged accepted equipment snapshot. 3. Repeat through the authenticated composite. 4. Inspect stored actor/baseline.
- **Test data:** Accepted projector quantity 2, forged baseline 9, proposed 3; O `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`.
- **Expected:** Direct calls get `403` before storage access. The composite call succeeds only with its server-held credential, and atomic Events still verifies O's trusted session/ownership; caller-supplied actor, timestamp and baseline fields cannot override the validated values.
- **Actual:** Missing or forged service credentials were rejected before persistence.
- **Status:** Pass
- **Evidence:** Full rebased TEST run on 2026-10-30; `tests/unit/atomic/events/test_s59.py`.
