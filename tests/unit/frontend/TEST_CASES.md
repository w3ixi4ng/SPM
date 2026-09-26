# Test cases — frontend role access (unit)

Covers `test_access.mjs`, `test_event_requests.mjs` and `test_venues.mjs`.
These tests exercise the shared frontend presentation policy and the events and
venues API contracts without a browser or network. Backend authentication,
RBAC, and validation remain authoritative.

| | |
| --- | --- |
| Suite | `node --test tests/unit/frontend/test_*.mjs` |
| Last run | 2026-09-26, branch `S-27/add-venue-with-capacity-and-facilities` |
| Environment | Local Node.js; no network or Supabase |
| Result | 12 passed |

## TC-FRONTEND-001 — each known role has one dashboard

- **Scenario:** Every trusted project role resolves to its own dashboard path.
- **Pre-conditions:** The frontend access mapping is loaded.
- **Steps:** Read each role's configured dashboard path.
- **Test data:** All five supported role names.
- **Expected:** Five distinct, role-appropriate `/dashboard/...` paths.
- **Actual:** All five roles resolved to distinct expected dashboard paths.
- **Status:** Pass
- **Evidence:** `test_access.mjs` — `every supported role has its own dashboard`

## TC-FRONTEND-002 — organiser permissions are not exposed to other roles

- **Scenario:** Only an Event Organiser sees organiser event capabilities.
- **Pre-conditions:** The frontend access mapping is loaded.
- **Steps:** Check every `events:*` permission for every supported role.
- **Test data:** Five roles and five organiser event permissions.
- **Expected:** All are true for `event_organiser` and false for every other role.
- **Actual:** All five event permissions were exclusive to `event_organiser`.
- **Status:** Pass
- **Evidence:** `test_access.mjs` — `only event organisers receive organiser event permissions`

## TC-FRONTEND-003 — missing and unknown roles fail closed

- **Scenario:** Untrusted roles cannot resolve a dashboard or permission.
- **Pre-conditions:** The frontend access mapping is loaded.
- **Steps:** Resolve missing and unknown roles, then check dashboard and event permissions.
- **Test data:** `undefined`, `not_a_role`.
- **Expected:** Role lookup returns null and every permission check returns false.
- **Actual:** Missing and unknown roles resolved no access.
- **Status:** Pass
- **Evidence:** `test_access.mjs` — `missing and unknown roles fail closed`

## TC-FRONTEND-004 — event form maps to the backend contract

- **Scenario:** Form state becomes snake_case JSON without server-owned fields.
- **Pre-conditions:** The event API helper is loaded.
- **Steps:** Map a complete form and an empty draft.
- **Test data:** Complete event fields plus client-supplied system fields; then
  an otherwise empty draft.
- **Expected:** Business fields use backend names and numeric quantities;
  `id`, `organiser_id`, `status`, `created_at`, and `updated_at` are absent;
  the empty draft contains only `equipment_requests: {}`.
- **Note:** covers `special_requirements` as well, including trimming and the
  blank-to-null rule.
- **Actual:** Business fields were mapped exactly and all server-owned fields
  were omitted; an empty draft mapped to an empty equipment object only.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `form mapping uses the backend contract and omits server-owned fields`

## TC-FRONTEND-005 — event responses map to React state

- **Scenario:** A stored event can repopulate the existing form controls.
- **Pre-conditions:** The event API helper is loaded.
- **Steps:** Map a complete API event response.
- **Test data:** Draft response with SQL-style times and integer quantities.
- **Expected:** Fields are camelCase, times are `HH:MM`, and attendance is an
  input-compatible string.
- **Note:** covers `special_requirements` as well, including trimming and the
  blank-to-null rule.
- **Actual:** All response fields mapped to their input-compatible values.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `API responses populate the existing React state shape`

## TC-FRONTEND-006 — event operations use the authenticated Kong contract

- **Scenario:** Every form flow calls the intended gateway path and method.
- **Pre-conditions:** `fetch` records requests and returns a valid event.
- **Steps:** Create a draft, update it, create a submission, submit a draft,
  and load an event.
- **Test data:** The complete shared event form and one UUID.
- **Expected:** Correct `/api/events` paths and HTTP methods, JSON bodies omit
  protected fields, and every request sets `credentials: include`.
- **Actual:** All five operations used the expected gateway path and method,
  carried credentials, and omitted protected fields.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `event API functions use Kong paths, methods, JSON, and credentials`

## TC-FRONTEND-007 — events errors are safe and actionable

- **Scenario:** Backend validation fields and HTTP failures produce useful,
  non-misleading form feedback.
- **Pre-conditions:** The event API error mapping is loaded.
- **Steps:** Map attendance, equipment, and time-order validation errors; then
  resolve messages for `401`, `403`, `404`, `409`, `422`, and `500`.
- **Test data:** Backend snake_case field paths and each required status code.
- **Expected:** Field paths target the current React controls; each status gets
  a safe message; server errors explicitly say changes were not saved.
- **Actual:** Every field and status mapped to the expected feedback.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `event API errors map to safe status and field feedback`

## TC-FRONTEND-008 — saved requests load through Kong

- **Scenario:** The organiser dashboard can retrieve server-persisted event
  requests without browser storage.
- **Pre-conditions:** `fetch` records requests and returns one saved draft.
- **Steps:** Call `listEventRequests()`.
- **Test data:** One complete `EventRead` draft response.
- **Expected:** `GET /api/events` includes session credentials and returns the
  response array unchanged.
- **Actual:** The list used the expected path and credentials and returned the
  saved draft.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `event list loads the authenticated organisers saved requests`

## TC-FRONTEND-009 — venue permissions match the venues service policy

- **Scenario:** The dashboard shows venue actions only to the roles the
  venues service allows (S-27).
- **Pre-conditions:** The frontend access mapping is loaded.
- **Steps:** Check `venues:create` and `venues:view` for every supported role.
- **Test data:** All five supported role names.
- **Expected:** `venue_staff` has both; `event_coordinator` has
  `venues:view` only; `event_organiser`, `technical_support` and `attendee`
  have neither.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_access.mjs` — `only venue staff create venues and only venue staff and coordinators view them`

## TC-FRONTEND-010 — the venue form reports every missing required field

- **Scenario:** The form refuses to save until required fields are complete,
  and says which ones are missing (S-27 AC 2).
- **Pre-conditions:** The venue form validation in `frontend/src/lib/venues.js`
  is loaded.
- **Steps:** Call `validateVenueForm()` on an empty form; on a form with
  whitespace-only name and location, capacity `0`, and a day whose close is
  before its open; then on a complete form.
- **Test data:** Empty form; `{name: "  ", location: "  ", capacity: "0",
  roomLayouts: [], hours: {mon: {open: "18:00", close: "09:00"}}}`; the valid
  venue from `tests/unit/atomic/venues/TEST_CASES.md` in form shape.
- **Expected:** Empty form: errors for `name`, `location`, `capacity`,
  `room_layouts`, `operating_hours`. Second form: errors for `name`,
  `location`, `capacity`, `room_layouts`; `hours.mon` saying closing time must
  be after opening time (this outlines Monday's row); and `operating_hours`
  naming Monday. Complete form: no errors.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_venues.mjs` — `venue form reports every missing required field`

## TC-FRONTEND-011 — venue operations use the authenticated Kong contract

- **Scenario:** The dashboard calls the intended gateway paths and sends only
  the fields the service accepts.
- **Pre-conditions:** `fetch` records requests and returns a valid venue.
- **Steps:** Call `listVenues()`, `getVenueOptions()`, and `createVenue()` with
  the complete form.
- **Test data:** The complete form from TC-FRONTEND-010.
- **Expected:** `GET /api/venues`, `GET /api/venues/options`,
  `POST /api/venues`; every request sets `credentials: include`; the POST
  body has `capacity` as a number, `operating_hours` as a list of
  `{day, open, close}` for enabled days only, and no `created_by`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_venues.mjs` — `venue API functions use Kong paths, methods, JSON, and credentials`

## TC-FRONTEND-012 — venue errors are safe and actionable

- **Scenario:** A rejected save tells the user what to fix.
- **Pre-conditions:** The venue API error mapping is loaded.
- **Steps:** Resolve messages for `401`, `403`, `409`, `422` and `500`; map a
  `422` body's `errors` keys to form fields.
- **Test data:** `422` body `{"detail": "Please check the details you
  entered", "errors": {"capacity": "...", "operating_hours.0": "..."}}`.
- **Expected:** `409` says a venue with that name already exists and to choose
  another name; `500` says the venue was not saved; `capacity` and
  `operating_hours.0` map to the capacity input and the Monday hours row.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_venues.mjs` — `venue API errors map to safe status and field feedback`
