# Test cases — frontend role access (unit)

Covers `test_access.mjs`, `test_event_requests.mjs`, `test_venues.mjs` and
`test_venue_bookings.mjs`.
These tests exercise the shared frontend presentation policy and the events and
venues API contracts without a browser or network. Backend authentication,
RBAC, and validation remain authoritative.

| | |
| --- | --- |
| Suite | `node --test tests/unit/frontend/test_*.mjs` |
| Last run | 2026-09-27, branch `S-36/submit-venue-booking-request` at `96930b9` |
| Environment | Node.js v22.16.0; no network or Supabase |
| Result | 34 passed |

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
- **Steps:** Check every `events:*` permission the organiser role holds,
  against every supported role.
- **Test data:** Five roles and `event_organiser`'s five `events:*` permissions.
- **Expected:** All are true for `event_organiser` and false for every other role.
- **Actual:** All five event permissions were exclusive to `event_organiser`.
- **Status:** Pass
- **Evidence:** `test_access.mjs` — `only event organisers receive organiser-only event permissions`

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

- **Scenario:** Revised for S-36: the requirement lists are always sent, like equipment. Form state becomes snake_case JSON without server-owned fields.
- **Pre-conditions:** The event API helper is loaded.
- **Steps:** Map a complete form and an empty draft.
- **Test data:** Complete event fields plus client-supplied system fields; then
  an otherwise empty draft.
- **Expected:** Business fields use backend names and numeric quantities;
  `id`, `organiser_id`, `status`, `created_at`, and `updated_at` are absent;
  the empty draft contains only `equipment_requests: {}`,
  `required_facilities: []` and `required_accessibility: []`.
- **Note:** covers `special_requirements` as well, including trimming and the
  blank-to-null rule.
- **Actual:** As expected.
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
- **Expected:** Draft create and read use `/api/events`; update and both
  submit actions (direct-submit and submit-existing-draft) use
  `/api/event-requests` instead -- S-12 routes update through the
  event_requests composite too, since an edit to a submitted event's
  date/time has to recheck the assigned coordinator, which create/read never
  need to. JSON bodies omit protected fields, and every request sets
  `credentials: include`.
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

## TC-FRONTEND-013 — coordinator permissions are not exposed to other roles

- **Scenario:** `events:view_assigned`/`events:decide` (a coordinator's two
  permissions) are coordinator-only, the same guarantee as TC-FRONTEND-002.
- **Pre-conditions:** The frontend access mapping is loaded.
- **Steps:** Check every `events:*` permission the coordinator role holds,
  against every supported role.
- **Test data:** Five roles and `event_coordinator`'s `events:*` permissions.
- **Expected:** True for `event_coordinator`, false for every other role.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_access.mjs` — `only event coordinators receive coordinator-only event permissions`

---

**S-14 additions.**

## TC-FRONTEND-014 — every backend status has a distinct display

- **Scenario:** Revised for S-36, where `planning` replaced `approved`. The organiser and coordinator dashboards both derive a
  status badge's label and color from one shared source, so the two never
  drift apart.
- **Pre-conditions:** None.
- **Steps:** Call `eventStatusMeta` for each of `draft`, `submitted`,
  `planning`, `returned`, `rejected`.
- **Test data:** The five statuses above.
- **Expected:** Each returns a string label and a `#rrggbb` color; the five
  labels are all distinct. `planning` is labelled `"Planning"` in green
  (`#3F8F5F`), the color `approved` used.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `eventStatusMeta covers every backend status with a distinct label`

## TC-FRONTEND-015 — an unrecognised status still renders safely

- **Pre-conditions:** None.
- **Steps:** Call `eventStatusMeta('made_up_status')`.
- **Test data:** `'made_up_status'`.
- **Expected:** No throw; the status string itself is used as the label, and
  a valid fallback color is returned.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `eventStatusMeta falls back safely for an unrecognised status`

## TC-FRONTEND-016 — a decision posts to the events service, not event-requests

- **Scenario:** Unlike submit/update, deciding never touches assignment, so
  there is nothing for the composite to orchestrate — this goes straight to
  the events service.
- **Pre-conditions:** `fetch` records the request and returns a stub event.
- **Steps:** Call `decideEventRequest('event-1', {decision: 'approved'})`.
- **Test data:** As above.
- **Expected:** `POST /api/events/event-1/decision`, `credentials: include`,
  body exactly `{"decision": "approved"}`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `decideEventRequest posts to the events service, not event-requests`

## TC-FRONTEND-017 — reason and comment are omitted when not given

- **Scenario:** An approval sends neither field — the backend rejects a
  reason on approve, so the client must not send an empty string for one.
- **Pre-conditions:** As above.
- **Steps:** Call `decideEventRequest('event-1', {decision: 'approved',
  reason: '', comment: undefined})`.
- **Test data:** As above.
- **Expected:** Body is exactly `{"decision": "approved"}` — no `reason` or
  `comment` key at all.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `decideEventRequest omits reason and comment when not given`

## TC-FRONTEND-018 — reason and comment are included when given

- **Pre-conditions:** As above.
- **Steps:** Call `decideEventRequest('event-1', {decision: 'returned',
  reason: 'Missing risk assessment', comment: 'Please attach the fire safety
  form'})`.
- **Test data:** As above.
- **Expected:** Body includes `decision`, `reason`, and `comment` exactly as
  given.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `decideEventRequest includes reason and comment when given`

## TC-FRONTEND-019 — returned and awaiting-decision requests sort to the front, in that order

- **Scenario:** Revised for S-36, where `planning` replaced `approved`. On the organiser dashboard, `returned` (sent back for
  amendment -- the one status that needs the organiser to act) and
  `submitted` (awaiting the coordinator's decision) are the two statuses the
  organiser cares about most, so both surface before draft/planning/rejected
  -- `returned` first, then `submitted`.
- **Pre-conditions:** `sortEventsForOrganiser` is loaded.
- **Steps:** Call `sortEventsForOrganiser(events)` with a mixed list of
  statuses in a non-sorted order.
- **Test data:** `[{id:'a',status:'submitted'}, {id:'b',status:'returned'},
  {id:'c',status:'draft'}, {id:'d',status:'returned'},
  {id:'e',status:'planning'}, {id:'f',status:'submitted'}]`.
- **Expected:** `['b','d','a','f','c','e']` — all `returned` events first
  (original relative order), then all `submitted` events (original relative
  order), then the rest (original relative order). `draft`, `planning`, and
  `rejected` are never moved ahead of each other.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `sortEventsForOrganiser sorts returned first, then submitted, then the rest, stable within each group`

## TC-FRONTEND-020 — sorting is a no-op with none of the two priority statuses, and does not mutate the input

- **Scenario:** Revised for S-36, where `planning` replaced `approved`. A list with neither `submitted` nor `returned` requests is
  left in its existing (backend-provided) order, and the function does not
  mutate its argument.
- **Pre-conditions:** As above.
- **Steps:** Call `sortEventsForOrganiser(events)` on a list containing only
  `draft` and `planning` events, then compare the result to the input order,
  and separately assert the original array's element order is unchanged
  after the call.
- **Test data:** `[{id:'a',status:'draft'}, {id:'b',status:'planning'},
  {id:'c',status:'draft'}]`.
- **Expected:** Result order is `['a','b','c']`, identical to the input, and
  the input array itself still reads `['a','b','c']` afterward.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `sortEventsForOrganiser is a no-op with neither priority status, and does not mutate its argument`

## TC-FRONTEND-021 — only the returned-for-amendment badge pulses, and only for the organiser

- **Scenario:** Per confirmed design, only `returned` gets the attention-
  drawing pulse animation on the organiser dashboard — `submitted` keeps a
  static badge, distinguished only by sort position and label/color, not
  motion.
- **Pre-conditions:** None.
- **Steps:** This case documents the status-to-animation-class mapping the
  `Dashboard.jsx` badge depends on (`event.status === 'returned'` ?
  `csp-pulse-badge` : none) — the animation class itself is applied in JSX,
  which these Node tests do not render. See the note below for what is and
  isn't covered.
- **Test data:** N/A — see note.
- **Expected:** N/A — see note.
- **Actual:** N/A — see note.
- **Status:** Blocked
- **Evidence:** —
- **Note:** The pulse animation, its 2.2s cadence, and the
  `prefers-reduced-motion` fallback are a rendered/CSS concern `node --test`
  cannot exercise without a DOM. Which status gets which *label and color*
  is covered by `organiserStatusMeta`, below (TC-FRONTEND-022/023/024) —
  this case is Blocked pending a browser/E2E check for the animation class
  itself, not claimed as covered here.

## TC-FRONTEND-022 — the organiser dashboard relabels a returned request as "Action required", in rose

- **Scenario:** From the organiser's point of view, `returned` is the status
  that needs *their* action (edit + resubmit), so the organiser dashboard
  renames the coordinator-facing "Returned for amendment" to "Action
  required" and colors it rose — the same "needs attention" red already
  used for `rejected` — instead of the shared amber. The coordinator's own
  views (`eventStatusMeta` directly) are unaffected.
- **Pre-conditions:** `organiserStatusMeta` is loaded.
- **Steps:** Call `organiserStatusMeta('returned')`.
- **Test data:** `'returned'`.
- **Expected:** `{ label: 'Action required', color: '#B25547' }`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `organiserStatusMeta relabels returned as Action required, in rose`

## TC-FRONTEND-023 — the organiser dashboard relabels a submitted request as "Under review", keeping the shared color

- **Scenario:** `submitted` is awaiting the coordinator, not the organiser,
  so only the wording changes ("Awaiting decision" → "Under review") —
  the color stays whatever `eventStatusMeta` already assigns it (shared
  amber), since this status doesn't get the rose "needs attention" treatment.
- **Pre-conditions:** As above.
- **Steps:** Call `organiserStatusMeta('submitted')` and compare its color
  to `eventStatusMeta('submitted').color`.
- **Test data:** `'submitted'`.
- **Expected:** `label` is `'Under review'`; `color` equals
  `eventStatusMeta('submitted').color` exactly.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `organiserStatusMeta relabels submitted as Under review, keeping the shared color`

## TC-FRONTEND-024 — every other status falls through to the shared meta unchanged

- **Scenario:** Revised for S-36, where `planning` replaced `approved`. `draft`, `planning`, and `rejected` are not part of this
  organiser-only reframing — they must render identically to the
  coordinator-facing `eventStatusMeta`, label and color both.
- **Pre-conditions:** As above.
- **Steps:** Call `organiserStatusMeta(status)` for `'draft'`, `'planning'`,
  and `'rejected'`, and compare each to `eventStatusMeta(status)`.
- **Test data:** `'draft'`, `'planning'`, `'rejected'`.
- **Expected:** `organiserStatusMeta(status)` deep-equals
  `eventStatusMeta(status)` for all three.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `organiserStatusMeta falls through to the shared meta for every other status`

## TC-FRONTEND-025 — a failed resubmission tells the organiser nothing was changed

- **Scenario:** Every way a resubmission can fail produces a message that says
  it was not resubmitted and that the saved request is unchanged (S-13 AC6).
  TC-FRONTEND-007 covers the general mapping; its `409` and network messages
  say neither.
- **Pre-conditions:** The event API error mapping is loaded.
- **Steps:** Resolve the resubmission failure message for each error below.
- **Test data / Expected:**

  | Error | Message |
  | --- | --- |
  | `409`, detail `"No event coordinator is available for the requested date and time"` | `"No event coordinator is available for the requested date and time. Your request was not resubmitted. Try a different date or time."` |
  | `409`, detail `"This request is no longer awaiting changes. Reload to see its current status."` | that detail, then `" Nothing was resubmitted."` |
  | `500` / `502` | `"The event service is unavailable. Your request was not resubmitted and nothing was changed."` |
  | status `0` (network) | `"We couldn't reach the server. Your request was not resubmitted and nothing was changed."` |
  | `422` | `"Please check the highlighted event details."` (unchanged, fields highlighted as TC-FRONTEND-007) |

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `a failed resubmission tells the organiser nothing was changed`

## S-13 — rejected requests in their own tab

A rejected request is closed for good, so the organiser dashboard splits its
list into two tabs: **Active** (returned, under review, draft, planning) and
**Rejected**. Rejected rows still open the read-only form.

## TC-FRONTEND-026 — rejected requests go to the Rejected tab, everything else stays Active

- **Scenario:** Revised for S-36, where `planning` replaced `approved`. The organiser's list is split by status, and the Active tab
  keeps the existing priority order (TC-FRONTEND-019).
- **Pre-conditions:** The event request helpers are loaded.
- **Steps:** Split the test list into the organiser's two tabs.
- **Test data:** Six events in backend order: `a` draft, `b` rejected, `c`
  planning, `d` submitted, `e` rejected, `f` returned.
- **Expected:** Active holds `f, d, a, c`: returned, then submitted, then the
  rest in backend order. Rejected holds `b, e` in backend order. No event
  appears in both tabs. The input array is unchanged.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `rejected requests go to the Rejected tab, everything else stays Active`

## TC-FRONTEND-027 — tab labels carry counts, and each tab has its own empty message

- **Scenario:** Each tab says how many requests it holds and what an empty
  tab means.
- **Pre-conditions:** As TC-FRONTEND-026.
- **Steps:** Build the tabs for the TC-FRONTEND-026 list, then for a list
  holding only a draft, then for an empty list.
- **Test data:** As above; `[{status: "draft"}]`; `[]`.
- **Expected:** The tabs are in the order Active, then Rejected.
  - TC-FRONTEND-026 list: labels `"Active (4)"` and `"Rejected (2)"`.
  - Draft only: `"Active (1)"` and `"Rejected (0)"`. The Rejected tab's empty
    message is `"No rejected requests."`
  - Empty list: `"Active (0)"` and `"Rejected (0)"`. The Active tab's empty
    message is `"You have no saved event requests yet."`
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `tab labels carry counts, and each tab has its own empty message`

## S-36 — venue booking requests

A Coordinator requests a venue for an event in planning. Venue Staff see
every pending request on their dashboard. The backend is authoritative for
every rule below; these cases cover only what the browser decides for
itself: who sees the controls, which paths are called, and what an error
says.

## TC-FRONTEND-028 — venue booking permissions match the venue_bookings service

- **Scenario:** Only a Coordinator sees "Request venue", and only Venue
  Staff see the pending list.
- **Pre-conditions:** The frontend access mapping is loaded.
- **Steps:** Check `venue_bookings:create` and
  `venue_bookings:view_pending` for every supported role.
- **Test data:** All five supported role names.
- **Expected:** `event_coordinator` has `venue_bookings:create` only.
  `venue_staff` has `venue_bookings:view_pending` only. `event_organiser`,
  `technical_support` and `attendee` have neither.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_access.mjs` — `only coordinators request venues and only venue staff see pending requests`

## TC-FRONTEND-029 — "Request venue" is offered only for an event in planning

- **Pre-conditions:** The venue booking helpers are loaded.
- **Steps:** Call `canRequestVenue(status)` for every event status.
- **Test data:** `draft`, `submitted`, `returned`, `rejected`, `planning`,
  and `undefined`.
- **Expected:** `true` for `planning`; `false` for everything else.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_venue_bookings.mjs` — `Request venue is offered only for an event in planning`

## TC-FRONTEND-030 — venue booking calls use the authenticated Kong contract

- **Scenario:** Revised for S-36: the requirements come from the event, not the request.
- **Pre-conditions:** `fetch` records requests and returns a valid booking.
- **Steps:** Call `submitVenueBooking(form)` twice, first with every field
  filled and then with only the required ones. Then call
  `listPendingVenueBookings()`.
- **Test data:** Full form: event `e1`, venue `v1`, date `2026-11-12`,
  `09:00`–`12:00`, notes `"  Setup from 08:30 "`.
  Required-only form: the same event, venue, date and times, with notes
  `""`.
- **Expected:** `POST /api/venue-bookings` and
  `GET /api/venue-bookings/pending`, each with `credentials: include`.
  - The full POST body is exactly `{event_id, venue_id, booking_date,
    start_time, end_time, notes}`, with notes trimmed to
    `"Setup from 08:30"`. No layout, facilities or accessibility: those come
    from the event.
  - The required-only body leaves out `notes`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_venue_bookings.mjs` — `venue booking calls use the authenticated Kong contract`

## TC-FRONTEND-031 — venue booking errors say what happened and what to do

- **Pre-conditions:** The venue booking error mapping is loaded.
- **Steps:** Resolve the message for each response below.
- **Test data:**
  - `422` with `{"detail": "This venue can't take this booking",
    "errors": {"expected_attendance": "Studio B holds 150 people; this
    event expects 200", "operating_hours": "Studio B is open 08:00–20:00 on
    Thursdays"}}`
  - `404` `"Event not found"`
  - `404` `"Venue not found"`
  - `409` `"A venue can only be requested for an event in planning"`
  - `401`
  - `502`
  - a network failure
- **Expected:**
  - `422`: both `errors` messages, as a list, so each problem is shown.
  - `404` and `409`: the service's `detail` as given.
  - `401`: `"Your session has expired. Please sign in again."`
  - `502` and network failure: `"We couldn't send the venue request. Nothing
    was submitted — try again in a moment."`
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_venue_bookings.mjs` — `venue booking errors say what happened and what to do`

## TC-FRONTEND-032 — an event's venue requests load through Kong

- **Scenario:** AC4. The event page asks for the requests sent for that
  event only.
- **Pre-conditions:** `fetch` records requests and returns `[]`.
- **Steps:** Call `listVenueBookingsForEvent('e 1/2')`.
- **Test data:** An id that needs encoding, `e 1/2`.
- **Expected:** One `GET /api/venue-bookings?event_id=e%201%2F2` with
  `credentials: include`.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_venue_bookings.mjs` — `an event's venue requests load through Kong`

## TC-FRONTEND-033 — the organiser's venue requirements map both ways

- **Pre-conditions:** The event API helper is loaded.
- **Steps:** Map a form with requirements to a payload; map it with a blank
  layout; map an API response with requirements back to form state.
- **Test data:** Form `roomLayout: "theatre"`, `requiredFacilities:
  ["projector"]`, `requiredAccessibility: ["lift"]`, `venue: ""`; the same
  with `roomLayout: ""`; a response with `room_layout: "banquet"`,
  `required_facilities: ["stage"]`, `required_accessibility: []`,
  `venue: null`.
- **Expected:** Payload carries `room_layout: "theatre"`,
  `required_facilities: ["projector"]`, `required_accessibility: ["lift"]`,
  `venue: null`. A blank layout is sent as `room_layout: null` (and left out
  when `omitEmpty` is set). The response maps to `roomLayout: "banquet"`,
  `requiredFacilities: ["stage"]`, `requiredAccessibility: []`, `venue: ""`.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `the organiser's venue requirements map both ways`

## TC-FRONTEND-034 — organisers load the option lists from the events service

- **Pre-conditions:** `fetch` records requests.
- **Steps:** Call `getEventOptions()`.
- **Test data:** None.
- **Expected:** One `GET /api/events/options` with `credentials: include`.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` — `organisers load the option lists from the events service`

## TC-FRONTEND-035 — each venue is marked against the event's requirements

- **Scenario:** The request screen lists every venue and says, before
  anything is sent, why one would not fit. Opening hours are left out: they
  depend on the date and time, which the service checks on send.
- **Pre-conditions:** The venue booking helpers are loaded.
- **Steps:** Call `venueFit(event, venue)` for a venue that fits and one that
  fails everything.
- **Test data:** Event: `expected_attendance: 100`, `room_layout: "banquet"`,
  `required_facilities: ["projector", "stage"]`,
  `required_accessibility: ["hearing_loop"]`. Fitting venue: capacity `100`,
  layouts `["banquet"]`, facilities `["projector", "stage"]`, accessibility
  `["hearing_loop"]`. Failing venue: capacity `80`, layouts `["theatre"]`,
  facilities `["projector"]`, accessibility `[]`.
- **Expected:** Fitting venue: `[]`. Failing venue, in this order:
  `"Too small: holds 80, event expects 100"`,
  `"No Banquet layout"`, `"Missing: Stage"`, `"Missing: Hearing loop"`.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_venue_bookings.mjs` — `each venue is marked against the event requirements`


## S-28 approved coverage

Latest S-28 execution: 2026-09-27; base commit `0d27acc` plus uncommitted S-28 changes. Environment: Windows/Python 3.14/Node; integration uses freshly recreated `.env.test` Docker stack.

### TC-FRONTEND-036 ? Edit helpers and permissions

- Scenario: Edit helpers and permissions
- Pre-conditions: Saved venue: location Block A, capacity 250, facilities projector, accessibility wheelchair_access.
- Steps: 1. Load form, change capacity to 100, save; check role policy and failures.
- Test data: Values specified above; existing shared fixtures supply remaining required fields.
- Expected: Only four fields sent via credentialled PATCH; staff alone has update permission; safe errors.
- Actual: All 39 Node tests passed, including five S-28 cases.
- Status: Pass
- Evidence: `tests/unit/frontend/test_venue_update.mjs`; local execution, no CI run.
