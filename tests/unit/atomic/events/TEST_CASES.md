# Test cases — events service schemas (unit)

Covers `tests/unit/atomic/events/test_schemas.py` and `test_app.py`: validation,
normalization, authentication, RBAC, ownership, and endpoint behaviour with both
Supabase clients mocked. They use no network, database, or Docker.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/events` |
| Last run | 2026-09-16, working tree of branch `event-request-status-toast` |
| Environment | Python 3.14.4, pytest 9.1.1, FastAPI 0.141.1, Pydantic 2.13.5, supabase-py 2.31.0; no network, database, or Docker |
| Result | 40 passed |

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

- **Scenario:** Known internal and attendee roles gain no unimplemented event powers.
- **Pre-conditions:** The centralized role policy is loaded.
- **Steps:** Read the permission set for every other known role.
- **Test data:** `event_coordinator`, `venue_staff`, `technical_support`, `attendee`.
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
