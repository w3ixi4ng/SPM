# Test cases — venues service (unit)

Covers `tests/unit/atomic/venues/test_schemas.py` and `test_app.py`: payload
validation, normalization, authentication, RBAC, and endpoint behaviour with
both Supabase clients mocked. They use no network, database, or Docker.

Story: S-27 Add Venue with Capacity and Facilities.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/venues` |
| Last run | 2026-09-27, branch `S-36/submit-venue-booking-request` at `96930b9` |
| Environment | Python 3.12.5, pytest 9.1.1, FastAPI 0.116.1, Pydantic 2.11.7, httpx 0.28.1, supabase-py 2.31.0; no network, database, or Docker |
| Result | 58 passed (30 cases, several parametrised); `cabaret` removed from the layout set |

## Shared test data

Referred to by name in the cases below.

**Valid venue** — every field supplied:

```json
{
  "name": "Harbourfront Hall",
  "location": "1 Harbourfront Walk, Singapore 098585",
  "capacity": 250,
  "facilities": ["projector", "wifi", "stage"],
  "accessibility": ["wheelchair_access", "accessible_toilets"],
  "room_layouts": ["theatre", "banquet"],
  "operating_hours": [
    {"day": "mon", "open": "09:00", "close": "18:00"},
    {"day": "sat", "open": "10:00", "close": "22:00"}
  ],
  "description": "Waterfront hall with a raised stage."
}
```

**Minimal venue** — required fields only:

```json
{
  "name": "Studio B",
  "location": "10 Anson Road, Singapore 079903",
  "capacity": 30,
  "room_layouts": ["boardroom"],
  "operating_hours": [{"day": "tue", "open": "08:00", "close": "17:00"}]
}
```

**Fixed option sets** — the only accepted values:

| Field | Values |
| --- | --- |
| `facilities` | `projector`, `screen`, `sound_system`, `microphones`, `wifi`, `stage`, `whiteboard`, `video_conferencing`, `catering_kitchen`, `air_conditioning`, `parking` |
| `accessibility` | `wheelchair_access`, `step_free_entrance`, `accessible_toilets`, `lift`, `hearing_loop`, `accessible_parking` |
| `room_layouts` | `theatre`, `classroom`, `boardroom`, `u_shape`, `banquet`, `cocktail` |
| `operating_hours[].day` | `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun` |

**Roles** — the mocked Auth user's `app_metadata.role`. `venue_staff` may
create and view; `event_coordinator` may view only; `event_organiser`,
`technical_support` and `attendee` may do neither.

---

## Schema validation (`test_schemas.py`)

## TC-VENUES-001 — a complete venue is accepted and normalised

- **Scenario:** A venue with every field supplied is valid, and text is tidied.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the valid venue, with `name` and
  `location` padded with spaces and `"wifi"` listed twice in `facilities`.
- **Test data:** Valid venue; `name` `"  Harbourfront Hall  "`; `facilities`
  `["projector", "wifi", "stage", "wifi"]`.
- **Expected:** Valid. `name` is `"Harbourfront Hall"`; `location` is trimmed;
  `facilities` is `["projector", "wifi", "stage"]` (duplicate dropped, order
  kept); every other field equals the input.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_complete_venue_is_accepted_and_normalised`

## TC-VENUES-002 — a venue with only required fields is accepted

- **Scenario:** Facilities, accessibility and description are optional.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue.
- **Test data:** Minimal venue.
- **Expected:** Valid. `facilities` is `[]`, `accessibility` is `[]`,
  `description` is `None`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_minimal_venue_is_accepted`

## TC-VENUES-003 — each required field must be present

- **Scenario:** Removing any one required field rejects the venue (AC 2).
- **Pre-conditions:** None.
- **Steps:** For each required field, instantiate `VenueCreate` with the
  minimal venue minus that one field.
- **Test data:** Minimal venue without, in turn, `name`, `location`,
  `capacity`, `room_layouts`, `operating_hours`.
- **Expected:** Five `ValidationError`s, each naming the removed field.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_each_required_field_must_be_present`

## TC-VENUES-004 — name and location cannot be blank

- **Scenario:** Whitespace does not count as completing a required text field.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and a blank
  value, once for `name` and once for `location`.
- **Test data:** `""` and `"   "` for each field.
- **Expected:** `ValidationError` naming the blank field, all four times.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_name_and_location_cannot_be_blank`

## TC-VENUES-005 — capacity must be a whole number of at least 1

- **Scenario:** Capacity is a positive head count.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and each invalid
  capacity; then with capacity `1`.
- **Test data:** Invalid: `0`, `-5`, `10.5`, `"abc"`. Valid: `1`.
- **Expected:** `ValidationError` naming `capacity` for each invalid value;
  `1` is accepted.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_capacity_must_be_a_positive_whole_number`

## TC-VENUES-006 — at least one room layout is required

- **Scenario:** An empty layout list does not complete the required field.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and
  `room_layouts` empty.
- **Test data:** `"room_layouts": []`.
- **Expected:** `ValidationError` naming `room_layouts`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_room_layouts_cannot_be_empty`

## TC-VENUES-007 — at least one day of operating hours is required

- **Scenario:** A venue that is never open cannot be saved.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and
  `operating_hours` empty.
- **Test data:** `"operating_hours": []`.
- **Expected:** `ValidationError` naming `operating_hours`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_operating_hours_cannot_be_empty`

## TC-VENUES-008 — facilities outside the fixed set are rejected

- **Scenario:** Every venue chooses facilities from the same list.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and one unknown
  facility alongside a valid one.
- **Test data:** `"facilities": ["wifi", "jacuzzi"]`; then `["WiFi"]`
  (wrong case).
- **Expected:** `ValidationError` naming `facilities` for both.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_unknown_facility_is_rejected`

## TC-VENUES-009 — room layouts outside the fixed set are rejected

- **Scenario:** Every venue chooses layouts from the same list.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and an unknown
  layout.
- **Test data:** `"room_layouts": ["theatre", "amphitheatre"]`.
- **Expected:** `ValidationError` naming `room_layouts`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_unknown_room_layout_is_rejected`

## TC-VENUES-010 — accessibility features outside the fixed set are rejected

- **Scenario:** Every venue chooses accessibility features from the same list.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and an unknown
  accessibility feature.
- **Test data:** `"accessibility": ["ramp"]`.
- **Expected:** `ValidationError` naming `accessibility`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_unknown_accessibility_feature_is_rejected`

## TC-VENUES-011 — closing time must be after opening time

- **Scenario:** A day's hours must describe a real opening window.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and one day whose
  close is before, then equal to, its open.
- **Test data:** `{"day": "tue", "open": "18:00", "close": "09:00"}`;
  `{"day": "tue", "open": "09:00", "close": "09:00"}`.
- **Expected:** `ValidationError` containing `close must be after open`, both
  times.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_close_must_be_after_open`

## TC-VENUES-012 — a day may appear only once in operating hours

- **Scenario:** Each day has at most one opening window.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and Monday listed
  twice.
- **Test data:** `[{"day": "mon", "open": "09:00", "close": "12:00"},
  {"day": "mon", "open": "13:00", "close": "18:00"}]`.
- **Expected:** `ValidationError` naming `operating_hours`, containing
  `mon is listed more than once`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_day_cannot_repeat_in_operating_hours`

## TC-VENUES-013 — operating hours reject unknown days and malformed times

- **Scenario:** Days come from the fixed set and times are real clock times.
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and each invalid
  entry in turn.
- **Test data:** `{"day": "funday", "open": "09:00", "close": "17:00"}`;
  `{"day": "mon", "open": "25:00", "close": "26:00"}`;
  `{"day": "mon", "open": "nine", "close": "17:00"}`.
- **Expected:** `ValidationError` naming `operating_hours` for each.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_operating_hours_reject_bad_day_or_time`

## TC-VENUES-014 — a blank description is stored as none

- **Scenario:** An optional text field left blank means "not given".
- **Pre-conditions:** None.
- **Steps:** Instantiate `VenueCreate` with the minimal venue and a blank
  description.
- **Test data:** `"description": "   "`.
- **Expected:** Valid; `description` is `None`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_schemas.py::test_blank_description_becomes_none`

---

## Endpoints (`test_app.py`)

## TC-VENUES-015 — venue staff create a venue

- **Scenario:** A venue staff member saves a complete venue (AC 1).
- **Pre-conditions:** Auth mock returns a `venue_staff` user with id
  `11111111-1111-1111-1111-111111111111`. The db mock's insert returns the
  inserted values plus `id` `22222222-2222-2222-2222-222222222222` and
  `created_at` `2026-09-26T08:00:00+00:00`.
- **Steps:** `POST /venues` with the valid venue and a session cookie.
- **Test data:** Valid venue.
- **Expected:** `201`. Insert was called on schema `venues`, table `venues`,
  with every valid-venue field and `created_by` equal to the user id. The
  response body contains every valid-venue field plus `id`, `created_by` and
  `created_at`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_venue_staff_create_a_venue`

## TC-VENUES-016 — the creator is taken from the session, not the payload

- **Scenario:** A client cannot attribute a venue to someone else.
- **Pre-conditions:** As TC-VENUES-015.
- **Steps:** `POST /venues` with the valid venue plus a `created_by` field.
- **Test data:** Valid venue + `"created_by": "99999999-9999-9999-9999-999999999999"`.
- **Expected:** `201`; the inserted `created_by` is
  `11111111-1111-1111-1111-111111111111`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_created_by_comes_from_the_session`

## TC-VENUES-017 — a venue missing a required field is not saved

- **Scenario:** The API refuses to save until required fields are complete
  (AC 2).
- **Pre-conditions:** Auth mock returns a `venue_staff` user.
- **Steps:** `POST /venues` with the minimal venue minus `capacity` and with
  `name` blank.
- **Test data:** `{"name": "", "location": "10 Anson Road, Singapore 079903",
  "room_layouts": ["boardroom"], "operating_hours": [{"day": "tue",
  "open": "08:00", "close": "17:00"}]}`.
- **Expected:** `422` with body
  `{"detail": "Please check the details you entered", "errors": {...}}` where
  `errors` has keys `name` and `capacity`. Insert is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_missing_required_field_is_not_saved`

## TC-VENUES-018 — only venue staff may create a venue

- **Scenario:** Coordinators can view but not add; other roles can do neither.
- **Pre-conditions:** Auth mock returns a user with the role under test.
- **Steps:** `POST /venues` with the valid venue, once per role.
- **Test data:** Roles `event_coordinator`, `event_organiser`,
  `technical_support`, `attendee`.
- **Expected:** `403` `{"detail": "Permission denied"}` for each. Insert is
  never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_venue_staff_may_create`

## TC-VENUES-019 — creating a venue requires a session

- **Scenario:** An anonymous caller cannot add a venue.
- **Pre-conditions:** No cookies sent.
- **Steps:** `POST /venues` with the valid venue.
- **Test data:** Valid venue.
- **Expected:** `401` `{"detail": "Not authenticated"}`. Insert is never
  called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_create_requires_a_session`

## TC-VENUES-020 — a duplicate venue name is rejected

- **Scenario:** Two venues cannot share a name, ignoring case.
- **Pre-conditions:** Auth mock returns a `venue_staff` user. The db mock's
  insert raises a Postgres unique violation (`APIError` with code `23505`), as
  the case-insensitive unique index would.
- **Steps:** `POST /venues` with the valid venue.
- **Test data:** Valid venue.
- **Expected:** `409` `{"detail": "A venue with this name already exists"}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_duplicate_name_is_rejected`

## TC-VENUES-021 — venue staff list venues

- **Scenario:** Venue staff see every venue, alphabetically.
- **Pre-conditions:** Auth mock returns a `venue_staff` user. The db mock's
  select returns two venue rows.
- **Steps:** `GET /venues`.
- **Test data:** Rows named `Harbourfront Hall` and `Studio B`.
- **Expected:** `200` with both rows. The query targets schema `venues`,
  table `venues`, ordered by `name` ascending, with no filter on
  `created_by`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_venue_staff_list_venues`

## TC-VENUES-022 — event coordinators list venues

- **Scenario:** Coordinators can view venues.
- **Pre-conditions:** As TC-VENUES-021, with an `event_coordinator` user.
- **Steps:** `GET /venues`.
- **Test data:** As TC-VENUES-021.
- **Expected:** `200` with both rows.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_event_coordinators_list_venues`

## TC-VENUES-023 — other roles cannot view venues

- **Scenario:** Viewing is limited to venue staff and coordinators.
- **Pre-conditions:** Auth mock returns a user with the role under test.
- **Steps:** `GET /venues`, `GET /venues/22222222-2222-2222-2222-222222222222`
  and `GET /venues/options`, once per role.
- **Test data:** Roles `event_organiser`, `technical_support`, `attendee`.
- **Expected:** `403` `{"detail": "Permission denied"}` for every call. No
  query is executed.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_other_roles_cannot_view_venues`

## TC-VENUES-024 — read one venue

- **Scenario:** A single venue can be opened by id.
- **Pre-conditions:** Auth mock returns a `venue_staff` user; the db mock's
  select returns the valid venue row with id
  `22222222-2222-2222-2222-222222222222`.
- **Steps:** `GET /venues/22222222-2222-2222-2222-222222222222`.
- **Test data:** That id.
- **Expected:** `200` with the row; the query filters `id` on that value.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_read_one_venue`

## TC-VENUES-025 — a missing venue is a 404

- **Scenario:** Reading an id that does not exist says so.
- **Pre-conditions:** Auth mock returns a `venue_staff` user; the db mock's
  select returns `[]`.
- **Steps:** `GET /venues/33333333-3333-3333-3333-333333333333`.
- **Test data:** That id.
- **Expected:** `404` `{"detail": "Venue not found"}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_missing_venue_is_404`

## TC-VENUES-026 — a malformed venue id is rejected

- **Scenario:** A non-UUID id never reaches the database.
- **Pre-conditions:** Auth mock returns a `venue_staff` user.
- **Steps:** `GET /venues/not-a-uuid`.
- **Test data:** `not-a-uuid`.
- **Expected:** `422`; no query is executed.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_malformed_venue_id_is_rejected`

## TC-VENUES-027 — storage failure is a safe 500

- **Scenario:** A Supabase outage does not leak internals.
- **Pre-conditions:** Auth mock returns a `venue_staff` user; the db mock's
  `execute()` raises `Exception("connection refused")`.
- **Steps:** `POST /venues` with the valid venue; `GET /venues`.
- **Test data:** Valid venue.
- **Expected:** `500` `{"detail": "Venue storage unavailable"}` for both;
  the body does not contain `connection refused`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_storage_failure_is_a_safe_500`

## TC-VENUES-028 — an unrecognised role is refused

- **Scenario:** A user whose role is missing or unknown gets nothing.
- **Pre-conditions:** Auth mock returns a user with no role, then with role
  `admin`.
- **Steps:** `GET /venues` and `POST /venues` with the valid venue, for each.
- **Test data:** `app_metadata` `{}` and `{"role": "admin"}`.
- **Expected:** `403` `{"detail": "Recognized role required"}` for all four.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_unrecognised_role_is_refused`

## TC-VENUES-029 — the option sets are served to the form

- **Scenario:** The browser builds its checkboxes from the service's own sets,
  so the form and the validation cannot drift apart.
- **Pre-conditions:** Auth mock returns a `venue_staff` user, then an
  `event_coordinator` user.
- **Steps:** `GET /venues/options` for each.
- **Test data:** None.
- **Expected:** `200` for both, with body
  `{"facilities": [...], "accessibility": [...], "room_layouts": [...],
  "days": [...]}` equal, in order, to the fixed option sets above. No
  database query is executed.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_option_sets_are_served`

## TC-VENUES-030 — health check

- **Scenario:** Compose and Kong can probe the service without a session.
- **Pre-conditions:** None.
- **Steps:** `GET /health`.
- **Test data:** None.
- **Expected:** `200` `{"status": "ok"}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_health`


## S-28 approved coverage

Latest S-28 execution: 2026-09-27; base commit `0d27acc` plus uncommitted S-28 changes. Environment: Windows/Python 3.14/Node; integration uses freshly recreated `.env.test` Docker stack.

### TC-VENUES-031 ? Partial update and staff authorisation

- Scenario: Partial update and staff authorisation
- Pre-conditions: Mock existing venue with capacity 250 and another creator.
- Steps: 1. PATCH capacity=100; repeat with each role and no session.
- Test data: Values specified above; existing shared fixtures supply remaining required fields.
- Expected: Staff receives 200; only capacity is written; other roles 403; no session 401.
- Actual: 164 focused tests and full 359-test Python suite passed.
- Status: Pass
- Evidence: `tests/unit/atomic/venues/test_update.py`; local execution, no CI run.

### TC-VENUES-032 ? Update validation and safe failures

- Scenario: Update validation and safe failures
- Pre-conditions: Mock venue storage.
- Steps: 1. PATCH blank location, capacity 0/1.5/true/null, unknown options, protected fields, empty body; simulate missing row and storage failure.
- Test data: Values specified above; existing shared fixtures supply remaining required fields.
- Expected: Invalid bodies 422 without writes; missing row 404; safe storage error 500.
- Actual: 164 focused tests and full 359-test Python suite passed.
- Status: Pass
- Evidence: `tests/unit/atomic/venues/test_update.py`; local execution, no CI run.

---

## S-75 — configure venue setup and turnaround time

Story: S-75 Configure Venue Setup and Turnaround Time.
Confirmed by the developer on 2026-10-07. Not yet executed.
Two new venue fields, `setup_minutes` and `turnaround_minutes`: whole minutes,
0 or more, default 0, no maximum. They join the fields Venue Staff may edit.

## TC-VENUES-033 — a new venue records its setup and turnaround times

- **Steps:** `POST /venues` as Venue Staff with the existing valid body plus
  `"setup_minutes": 30, "turnaround_minutes": 45`; then without them.
- **Expected:** `201` echoing 30 and 45; without them, both stored and
  returned as `0`.
- **Actual:** Created with 30/45 echoed and stored; without them both stored and returned as 0.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/venues/test_setup_turnaround.py::test_a_new_venue_records_its_setup_and_turnaround_times`; `tests/unit/atomic/venues/test_setup_turnaround.py::test_a_new_venue_without_times_starts_at_zero`

## TC-VENUES-034 — times cannot be negative or fractional; 0 is accepted

- **Steps:** Create and `PATCH` with each value for `setup_minutes`, then for
  `turnaround_minutes`: `-1`, `1.5`, `"30"`, `null`, `0`, `600`.
- **Expected:** `-1`, `1.5`, `"30"` and `null` → `422` naming the field, with
  nothing written. `0` and `600` are accepted.
- **Actual:** -1, 1.5, "30" and null were 422 naming the field on create and update, with nothing written; 0 and 600 accepted.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/venues/test_setup_turnaround.py::test_times_cannot_be_negative_fractional_text_or_null`; `tests/unit/atomic/venues/test_setup_turnaround.py::test_zero_and_large_times_are_accepted`

## TC-VENUES-035 — Venue Staff update the times at any time, leaving other fields as they are

- **Steps:** `PATCH /venues/{id}` with only `{"setup_minutes": 15}`, then only
  `{"turnaround_minutes": 0}`.
- **Expected:** `200` each time; only that field changes. Non-staff → `403`
  as for other venue edits (TC-VENUES-031 policy unchanged).
- **Actual:** Each single-field PATCH wrote only that field; other roles 403 with no write.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/venues/test_setup_turnaround.py::test_staff_update_one_time_leaving_the_rest`; `tests/unit/atomic/venues/test_setup_turnaround.py::test_only_venue_staff_update_the_times`

## TC-VENUES-036 — every venue read includes both times

- **Steps:** `GET /venues` and `GET /venues/{id}`.
- **Expected:** Each venue has `setup_minutes` and `turnaround_minutes`.
- **Actual:** List and single reads both carried 30/45.
- **Status:** Pass
- **Evidence:** `tests/unit/atomic/venues/test_setup_turnaround.py::test_every_venue_read_includes_both_times`
