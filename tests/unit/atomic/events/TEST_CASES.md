# Test cases — events service schemas (unit)

Covers `tests/unit/atomic/events/test_schemas.py` and `test_app.py`: validation,
normalization, authentication, RBAC, ownership, and endpoint behaviour with both
Supabase clients mocked. They use no network, database, or Docker.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/events` |
| Last run | 2026-09-25, branch `S-14/auto-assign-ec` |
| Environment | Python 3.14.4, pytest 9.1.1, FastAPI 0.141.1, Pydantic 2.13.5, supabase-py 2.31.0; no network, database, or Docker |
| Result | 82 passed |

## TC-EVENTS-001 — valid partial draft

- **Scenario:** A draft accepts valid supplied values without requiring the full submission.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` with a padded name, attendance,
  start/end times, one equipment quantity, and blank accessibility text.
- **Test data:** Name `"  Alumni networking evening  "`, attendance `120`,
  times `18:00`–`21:00`, equipment `{"projector": 1}`, accessibility `"   "`.
- **Expected:** The model is valid; text is trimmed; blank optional accessibility
  becomes `None`; attendance and equipment are retained.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_valid_draft_accepts_and_normalises_supplied_values`

## TC-EVENTS-002 — empty draft

- **Scenario:** A user can save a draft before filling in any business field.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` without arguments.
- **Test data:** `{}`.
- **Expected:** The model is valid; every optional field is `None` and
  `equipment_requests` is `{}`.
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

## TC-EVENTS-004 — invalid equipment quantity

- **Scenario:** A supplied equipment quantity must be positive.
- **Pre-conditions:** None.
- **Steps:** Instantiate `EventDraftCreate` with a zero projector quantity.
- **Test data:** `{"equipment_requests": {"projector": 0}}`.
- **Expected:** Pydantic raises `ValidationError`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_draft_rejects_non_positive_equipment_quantity`

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

- **Scenario:** A submitted request cannot omit a required field.
- **Pre-conditions:** The otherwise-valid submitted payload from TC-EVENTS-006.
- **Steps:** Remove `venue` and instantiate `EventSubmittedCreate`.
- **Test data:** Valid submitted payload without `venue`.
- **Expected:** `ValidationError` identifies `venue`.
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

- **Scenario:** PATCH on a submitted event is validated against the
  submitted-required rules, not the draft's permissive ones, so it cannot
  null out a field the database's own constraint requires.
- **Pre-conditions:** The owned lookup returns the submitted payload from
  TC-EVENTS-014.
- **Steps:** `PATCH` the event, clearing `venue`.
- **Test data:** `{"venue": ""}`.
- **Expected:** `422` identifying `venue`; update is never called.
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

- **Scenario:** Only submitted (awaiting decision) and approved (confirmed)
  events represent committed time on a coordinator's schedule. Updated for
  S-14: drafts never counted; returned and rejected now don't either, since
  neither is a live commitment.
- **Pre-conditions:** None beyond the shared fakes.
- **Steps:** `POST /events/coordinator-load`; inspect the Supabase query sent.
- **Test data:** One coordinator id, any window.
- **Expected:** The query filters on `status in ("submitted", "approved")` --
  every other status is excluded at the query itself, not filtered out
  afterwards, so it can never reach the conflict check or the count.
- **Actual:** As expected; `.in_("status", ["submitted", "approved"])` called
  once.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_load_query_only_counts_submitted_and_approved_events`

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

- **Scenario:** The internal route is validated exactly as strictly as the
  public one — a caller-supplied `organiser_id` is not a way to bypass the
  submitted-required rules.
- **Pre-conditions:** An owned submitted event.
- **Steps:** `PATCH /events/{event_id}/internal` clearing `venue`.
- **Test data:** `{"organiser_id": ..., "venue": ""}`.
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

## TC-EVENTS-067 — coordinator approves a submitted request

- **Scenario:** Approval needs no reason and closes the decision loop with
  `status=approved`.
- **Pre-conditions:** A verified `event_coordinator` session; the assigned,
  submitted event exists.
- **Steps:** `POST /events/{event_id}/decision` with `{"decision":
  "approved"}`.
- **Test data:** The standard submitted payload, assigned to the caller.
- **Expected:** `200`; `status=approved`; the update sent to Supabase has
  `decision=approved`, `decision_reason=null`, `decision_comment=null`, and a
  non-null `decided_at`.
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
  event's status is already `approved`.
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

## TC-EVENTS-078 — an approved request cannot be resubmitted

- **Pre-conditions:** An owned event with `status=approved`.
- **Steps:** `POST /events/{event_id}/submit` with the standard submitted
  payload.
- **Test data:** As above.
- **Expected:** `409`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_an_approved_request_cannot_be_resubmitted`

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

- **Scenario:** A returned request is not treated as a permissive draft on
  edit — the same strict validation as a submitted or approved event
  applies, since every required field already exists and resubmission
  expects them to stay that way.
- **Pre-conditions:** An owned event with `status=returned`.
- **Steps:** `PATCH /events/{event_id}` clearing `venue`.
- **Test data:** `{"venue": ""}`.
- **Expected:** `422`; no update issued.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_editing_a_returned_event_still_requires_submitted_fields`
