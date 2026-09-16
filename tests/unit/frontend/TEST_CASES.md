# Test cases — frontend role access (unit)

Covers `test_access.mjs` and `test_event_requests.mjs`. These tests exercise
the shared frontend presentation policy and event API contract without a
browser or network. Backend authentication, RBAC, and validation remain
authoritative.

| | |
| --- | --- |
| Suite | `node --test tests/unit/frontend/test_*.mjs` |
| Last run | 2026-09-14, working tree of branch `events-schema` |
| Environment | Local Node.js; no network or Supabase |
| Result | 8 passed |

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
