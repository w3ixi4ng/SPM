# Test cases — frontend role access (unit)

Covers `test_access.mjs`, `test_equipment.mjs`, `test_event_requests.mjs`,
`test_equipment_requirements.mjs`, `test_venues.mjs`,
`test_venue_bookings.mjs`, `test_booking_decision.mjs`, `test_venue_update.mjs`,
`test_technical_support_assignment.mjs`, and `test_venue_availability.mjs`.
These tests exercise the shared frontend presentation policy and the events and
venues API contracts without a browser or network. Backend authentication,
RBAC, and validation remain authoritative.

| | |
| --- | --- |
| Suite | `node --test tests/unit/frontend/test_*.mjs` |
| Last run | 2026-09-29, branch `S-38/prevent-overlapping-booking-confirmation`, pre-commit working tree |
| Environment | Node.js v22.16.0; no network or Supabase |
| Result | 64 passed |

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
  the empty draft contains only `required_facilities: []` and
  `required_accessibility: []`.
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
- **Steps:** Map attendance and time-order validation errors; then
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

## S-39 — equipment catalogue

### TC-FRONTEND-036 — equipment form validates required catalogue fields

- **Scenario:** Technical Support gets immediate, specific feedback before a
  bad catalogue item reaches the service.
- **Pre-conditions:** Equipment form validation is loaded.
- **Steps:** Validate an empty form, quantities `0`, `-1`, and `1.5`, then a
  complete form.
- **Test data:** Type `Wireless Microphone`, description `Handheld wireless
  microphone with receiver`, quantity `12`.
- **Expected:** Empty/blank type and every invalid quantity are identified;
  the complete form has no errors.
- **Actual:** Each invalid form produced the expected field error; the complete form passed.
- **Status:** Pass
- **Evidence:** `test_equipment.mjs` — `equipment form validates required catalogue fields`

### TC-FRONTEND-037 — equipment operations use the authenticated Kong contract

- **Scenario:** Catalogue screens call the S-39 gateway routes and do not send
  server-owned state.
- **Pre-conditions:** Fetch is recorded and returns a stored item.
- **Steps:** List the catalogue, list selection options, and create the
  complete item.
- **Test data:** As TC-FRONTEND-036, plus client-supplied fake id, creator and
  statuses that must not enter the request body.
- **Expected:** Authenticated calls use `GET /api/equipment`,
  `GET /api/equipment/selection`, and `POST /api/equipment`; the POST body is
  exactly type, description and numeric total quantity.
- **Actual:** All three calls used the specified paths and credentials; the POST omitted protected fields.
- **Status:** Pass
- **Evidence:** `test_equipment.mjs` — `equipment operations use authenticated Kong routes and safe payloads`

### TC-FRONTEND-038 — equipment errors are safe and actionable

- **Scenario:** The form maps API failures to guidance without exposing
  backend details.
- **Pre-conditions:** Equipment error helpers are loaded.
- **Steps:** Map `401`, `403`, `422`, and `500`, plus field errors for type and
  total quantity.
- **Test data:** Representative responses for each status.
- **Expected:** The user is told to sign in, that their role is not permitted,
  which fields to fix, or that the item was not saved; field names map to the
  matching form controls.
- **Actual:** Every status and field error mapped to the specified safe feedback.
- **Status:** Pass
- **Evidence:** `test_equipment.mjs` — `equipment errors are safe and actionable`

## S-35 — warn on attendance exceeding venue capacity

On the Coordinator's venue request screen, selecting a venue that does not
meet the event's venue requirements shows a warning listing why, and disables
**Send request** until a venue that fits is selected (warn and block, agreed
with the developer). The story names capacity; the developer confirmed the
same rule applies to every venue requirement the event has — capacity, room
layout, facilities and accessibility — as the project brief's capacity
example is one case of it. Opening hours and the event window depend on the
date and time typed in, so they are still checked by the service on send.

Acceptance criteria, as reworded by the developer for this scope:

| Acceptance criterion | Cases |
| --- | --- |
| AC1: Selecting a venue that doesn't meet the event's requirements — expected attendance above its capacity, or a missing room layout, facility or accessibility feature — triggers a warning that says why | TC-FRONTEND-039, TC-E2E-210 steps 3–4 |
| AC2: The warning is shown before the booking request can be submitted, and the request cannot be sent while the selected venue doesn't meet them | TC-E2E-210 steps 3–4 |
| AC3: The Coordinator can still choose a different, suitable venue after the warning, and the warning clears when they do | TC-E2E-210 steps 5–6 |

## TC-FRONTEND-039 — a venue that doesn't suit the event produces a warning listing why

- **Pre-conditions:** The venue booking helpers are loaded.
- **Steps:** Call `venueWarning(event, venue)` for each venue below.
- **Test data:** Event `expected_attendance: 100`, `room_layout: "banquet"`,
  `required_facilities: ["stage"]`, `required_accessibility: ["lift"]`.
  Venues, each named `Studio B`:
  - too small only: capacity `80`, layouts `["banquet"]`, facilities
    `["stage"]`, accessibility `["lift"]`;
  - large enough but missing the rest: capacity `150`, layouts
    `["theatre"]`, facilities `[]`, accessibility `[]`;
  - fits: capacity `100`, layouts `["banquet"]`, facilities `["stage"]`,
    accessibility `["lift"]`;
  - `null` (nothing selected yet).
- **Expected:**
  - Too small only: `"Studio B doesn't suit this event: Too small: holds
    80, event expects 100. Choose a venue that fits."`
  - Missing the rest: `"Studio B doesn't suit this event: No Banquet layout;
    Missing: Stage; Missing: Lift. Choose a venue that fits."`
  - Fits, and `null`: `null`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_venue_bookings.mjs` — `a venue that doesn't suit the event produces a warning listing why`

## S-40 — record required equipment

### TC-FRONTEND-040 — requirement calls use the authenticated composite route

- **Steps:** List one event's requirements, list all for Technical Support,
  save a quantity, and remove an item.
- **Expected:** Calls use `/api/equipment-requirements`, include credentials,
  encode ids, and send only `{required_quantity}` on PUT.
- **Actual:** All four calls used the composite route, credentials, encoded ids,
  and the numeric-only write payload.
- **Status:** Pass
- **Evidence:** `test_equipment_requirements.mjs` — `requirement API uses the composite route and numeric quantity`

### TC-FRONTEND-041 — only valid positive whole quantities are saved

- **Test data:** Blank, `0`, `-1`, `1.5`, and `6`.
- **Expected:** The first four are rejected locally; `6` is accepted.
- **Actual:** Blank, zero, negative and decimal quantities were rejected; the
  positive whole number was accepted.
- **Status:** Pass
- **Evidence:** `test_equipment_requirements.mjs` — `requirement quantity accepts only positive whole numbers`

### TC-FRONTEND-042 — presentation permissions match the composite policy

- **Expected:** Event Coordinator has edit/view; Technical Support has view
  only; every other role has neither.
- **Actual:** The permission matrix matched the composite policy for all roles.
- **Status:** Pass
- **Evidence:** `test_access.mjs` — `coordinators edit requirements and technical support can only view them`

### TC-FRONTEND-043 — organiser event payloads no longer carry equipment requirements

- **Scenario:** S-40 has one source of truth owned by the equipment service.
- **Steps:** Map complete organiser event form state to create/update payloads.
- **Expected:** `equipment_requests` is absent even if stale form state contains
  it; the events API rejects a direct browser-supplied field.
- **Actual:** Event mapping omitted the legacy field and the events request
  model rejected it as an extra field.
- **Status:** Pass
- **Evidence:** `test_event_requests.mjs` and `test_schemas.py::test_draft_rejects_legacy_organiser_equipment_requests`

## S-41 — update equipment item details

### TC-FRONTEND-044 — the editor maps current and changed catalogue details

- **Scenario:** A stored item can populate the editor and return the complete
  S-41 update contract.
- **Steps:** Map an API item to form state, validate it, then map changed form
  state to an update payload.
- **Test data:** Renamed microphone, blank optional description, quantity `18`,
  and each allowed operational status; then blank type, invalid quantities,
  and an unknown status.
- **Expected:** Current values populate matching controls; valid fields map to
  `type`, nullable `description`, numeric `total_quantity`, and
  `operational_status`; invalid values receive field errors.
- **Actual:** Stored fields populated the form, all three statuses validated, invalid status failed, and the payload contained exactly the four S-41 fields.
- **Status:** Pass
- **Evidence:** `test_equipment.mjs` — `equipment edit mapping accepts exactly the S-41 fields and statuses`

### TC-FRONTEND-045 — detail and update calls use authenticated Kong routes

- **Steps:** Load and update an item whose id needs URL encoding.
- **Expected:** Calls use `GET /api/equipment/{id}` and
  `PUT /api/equipment/{id}`, include credentials, and the update body contains
  only the four editable fields.
- **Actual:** Both encoded, credentialed Kong calls used the expected methods and the update body omitted protected fields.
- **Status:** Pass
- **Evidence:** `test_equipment.mjs` — `equipment detail and update use authenticated Kong routes`

### TC-FRONTEND-046 — equipment status labels reflect management state

- **Scenario:** Technical Support still sees unavailable and maintenance items
  and can distinguish their status.
- **Steps:** Format all three allowed operational statuses and both existing
  lifecycle statuses for catalogue rows.
- **Expected:** Human-readable labels come from the stored values rather than a
  hardcoded `Available · Active` string.
- **Actual:** Catalogue labels reflected all tested stored operational and lifecycle combinations.
- **Status:** Pass
- **Evidence:** `test_equipment.mjs` — `equipment catalogue status labels reflect stored state`

## S-28 approved coverage

ID reconciliation: main retains TC-FRONTEND-040 through TC-FRONTEND-046
for S-40 and S-41. The S-28 edit helpers and permissions case is now
TC-FRONTEND-047 (originally TC-FRONTEND-036, then TC-FRONTEND-040
on the S-28 branch). Earlier S-28 references to those IDs refer to this
venue-edit case, not the equipment cases. No case was removed.

The S-28 result below records its original execution. The combined suite was
rerun successfully on S-42; the header records that latest execution.

Latest S-28 execution: 2026-09-27; base commit `0d27acc` plus uncommitted S-28 changes. Environment: Windows/Python 3.14/Node; integration uses freshly recreated `.env.test` Docker stack.

### TC-FRONTEND-047 - Edit helpers and permissions

- Scenario: Edit helpers and permissions
- Pre-conditions: Saved venue: location Block A, capacity 250, facilities projector, accessibility wheelchair_access.
- Steps: 1. Load form, change capacity to 100, save; check role policy and failures.
- Test data: Values specified above; existing shared fixtures supply remaining required fields.
- Expected: Only four fields sent via credentialled PATCH; staff alone has update permission; safe errors.
- Actual: All 39 Node tests passed, including five S-28 cases.
- Status: Pass
- Evidence: `tests/unit/frontend/test_venue_update.mjs`; local execution, no CI run.

## S-42 — retire equipment item

S-28 already owns `TC-FRONTEND-047` on current `main`, so S-42 begins at the
next unused frontend id.

### TC-FRONTEND-048 — retirement uses the authenticated item action

- **Steps:** Retire an item whose id requires URL encoding.
- **Expected:** The client sends credentialed
  `POST /api/equipment/{id}/retire` with no client-controlled lifecycle or
  catalogue body and returns the retired item response.
- **Actual:** The encoded, credentialed POST used the explicit retirement path
  and sent no request body.
- **Status:** Pass
- **Evidence:** `test_equipment.mjs` — `retirement uses the authenticated item action without a lifecycle payload`

### TC-FRONTEND-049 — only Technical Support sees a valid retirement action

- **Scenario:** Presentation policy mirrors the backend while lifecycle state
  prevents a meaningless repeat control.
- **Steps:** Check retirement permission for every role and action visibility
  for active and retired items; format the retired catalogue status.
- **Expected:** Only Technical Support has retirement permission. Its active
  items expose Retire; retired items remain visible with a clear Retired label
  but no unretire or additional retirement action.
- **Actual:** Only Technical Support received the permission; only active items
  exposed the action, while retired items kept their Retired label.
- **Status:** Pass
- **Evidence:** `test_access.mjs` — `only technical support can retire equipment` and `test_equipment.mjs` — `retirement actions and labels follow lifecycle state`

### TC-FRONTEND-050 — retirement failures are actionable and never claim success

- **Steps:** Map retirement failures for `401`, `403`, `404`, and `500`.
- **Expected:** The user is told to sign in, that their role is not permitted,
  that the item is missing, or that retirement failed. No success notice is
  produced for a rejected request.
- **Actual:** All four statuses mapped to safe, actionable feedback and server
  failure messaging explicitly said the item was not retired.
- **Status:** Pass
- **Evidence:** `test_equipment.mjs` — `retirement failures are safe and actionable`

S-37 IDs reconciled after merging S-42 and S-43: TC-FRONTEND-048 -> TC-FRONTEND-051 -> TC-FRONTEND-054, and TC-FRONTEND-049 -> TC-FRONTEND-052 -> TC-FRONTEND-055. Earlier S-37 references identify the same cases.

## S-37 confirmed specifications

Confirmed by the developer on 2026-09-28, with no reassignment exception.
S-37 execution: 2026-09-29; base c4934e9 merged with S-37 plus conflict-resolution changes on
S-37/approve-reject-booking-with-reason-or-alternative.
Windows, Python 3.14, Node.js; existing results above describe earlier coverage.
Approval stores `status=confirmed`; rejection stores `status=rejected`.
Decision metadata: `decision_reason`, `decision_alternative`, `decided_by`, `decided_at`.
B means the saved booking fixture; S means the authenticated deciding staff UUID.
No S-33 hold behaviour or S-38 cross-request overlap guarantee is included.

### TC-FRONTEND-054 — Decision form validation and permissions match backend policy

- **Scenario:** Decision form validation and permissions match backend policy (AC1, AC2).
- **Pre-conditions:** Pure frontend helpers loaded; no network.
- **Steps:** 1. Validate approval and rejection variants.
  2. Check all five role permissions.
- **Test data:** approved with no reason; rejected with reason='Repairs', alternative='Try Studio C', both, or whitespace only.
- **Expected:** Only Venue Staff receive decision permission. Approval needs no text; rejection requires one trimmed nonblank field. Unknown decisions invalid.
- **Actual:** Passed in local isolated suites: 529 Python tests and 59 Node tests.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_booking_decision.mjs`; local execution, no CI run. Node IDs/test names: `only venue staff have booking decision permission; approval needs no reason and rejection needs reason or alternative`.

### TC-FRONTEND-055 — Decision API and saved status presentation

- **Scenario:** Decision API and saved status presentation (AC1, AC2, AC3).
- **Pre-conditions:** Mock fetch records requests and returns saved booking or error.
- **Steps:** 1. Submit a decision.
  2. Map all three statuses and errors.
- **Test data:** B=44444444-4444-4444-8444-444444444444; rejected; alternative='  Try Friday  '; extra decided_by; HTTP401,403,404,409,422,500 and network failure.
- **Expected:** Credentialled POST /api/venue-bookings/B/decision sends only decision/reason/alternative with trimming. Distinct Pending, Confirmed and Rejected labels; safe actionable errors; no false saved message. Server-owned fields excluded.
- **Actual:** Passed in local isolated suites: 529 Python tests and 59 Node tests.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_booking_decision.mjs`; local execution, no CI run. Node IDs/test names: `decision call uses credentialled gateway route and only permitted fields; saved booking statuses have distinct labels and safe failure messages`.
## S-43 — Auto-Assign Technical Support

### TC-FRONTEND-051 — support assignment uses the explicit authenticated action

- **Steps:** Read an event's support state, then request assignment for an id
  requiring URL encoding with padded optional details.
- **Expected:** Credentialed GET and POST use
  `/api/event-requests/{id}/technical-support-assignment`. POST sends only
  normalized `support_details`; it never sends a staff id, role, status, or
  assignment field.
- **Actual:** The encoded GET and notes-only POST used the authenticated composite route; no protected assignment field was sent.
- **Status:** Pass
- **Evidence:** `test_technical_support_assignment.mjs` — `support assignment uses the explicit authenticated action`

### TC-FRONTEND-052 — only planning Coordinators see assignment controls and persisted state

- **Steps:** Check the presentation permission for all roles and action
  visibility for every event status; format unrequested, assigned, and
  required-but-unavailable states.
- **Expected:** Only Event Coordinators have the presentation permission and
  only planning events expose the action. An assignment shows staff name and
  email after reload; an unavailable result has explicit `unassigned` state
  and says nobody is currently available; no individual staff picker exists.
- **Actual:** Permission, planning-only action visibility, and all three persisted presentation states matched the specification.
- **Status:** Pass
- **Evidence:** `test_access.mjs` — `only coordinators can request technical support assignment`; `test_technical_support_assignment.mjs` — `support assignment controls and states follow the event`

### TC-FRONTEND-053 — support assignment errors never claim success

- **Steps:** Map `401`, `403`, `404`, `409`, and dependency/server failures.
- **Expected:** Feedback distinguishes expired session, forbidden role,
  missing/unassigned event, non-planning/stale event, and unavailable service.
  Failures never display an assigned staff member.
- **Actual:** Every tested failure mapped to safe feedback and none reported assignment success.
- **Status:** Pass
- **Evidence:** `test_technical_support_assignment.mjs` — `support assignment failures are safe and actionable`

## S-38 confirmed specifications

Story: S-38 Prevent Overlapping Booking Confirmation.
Confirmed by the developer on 2026-09-29. Back-to-back bookings are allowed.

### TC-FRONTEND-056 — An overlapping confirmation displays the identified conflict

- **Scenario:** Venue Staff receive actionable conflict feedback and no false
  confirmation (AC2, AC3).
- **Pre-conditions:** The booking decision helper receives a `409` response
  containing the conflicting venue name, date, start time and end time.
- **Steps:** Map the response to decision feedback and the pending-list state.
- **Test data:** Studio B, `2026-11-12`, `10:00`–`12:00`.
- **Expected:** The displayed message says the booking cannot be confirmed and
  identifies Studio B, `12 Nov 2026`, and `10:00`–`12:00`. No success notice
  appears, and the attempted request remains Pending so staff can reject it or
  choose another action.
- **Actual:** The identified conflict was shown verbatim and never mapped to a success message.
- **Status:** Pass
- **Evidence:** `test_booking_decision.mjs` — `overlap conflict identifies the unavailable venue slot`; full Node suite: 64 passed.

## S-34 — search and filter venues

Coordinators filter venues in two places: the **Venues** tab on their
dashboard (filters start empty) and the venue request screen for an event
(filters start from the event: its attendance, facilities and accessibility,
and the booking's date and time). Filtering happens in the browser over the
full venue list. Decisions confirmed with the developer:

- **Date and time** means the venue is *open* then — its opening hours for
  that weekday cover the times. Whether it is already booked is the Booking
  Conflict Detection story.
- **Expected attendance** means *holds at least* that many; it also covers
  capacity, so there is no separate capacity filter.
- **Location** is a text search over the venue's location and name.
- **Room layout** was added by the developer: one layout at a time, and a
  venue matches if it offers it.

| Acceptance criterion | Cases |
| --- | --- |
| AC1: A Coordinator can filter venues by date, time, expected attendance, location, capacity, accessibility, and facilities | TC-FRONTEND-057 to 061, TC-FRONTEND-064, TC-E2E-219 |
| AC2: Search results only include venues matching all applied filter criteria | TC-FRONTEND-062, TC-E2E-219 step 5 |
| AC3: Results update when filter criteria are changed | TC-E2E-219 steps 2–6 |

Shared test data for TC-FRONTEND-057 to 064, in this order:

```
Harbour Hall   location "1 Harbourfront Walk", capacity 250,
               layouts [theatre, banquet],
               facilities [projector, stage], accessibility [lift],
               open mon 09:00-18:00, thu 08:00-20:00
Studio B       location "10 Anson Road", capacity 80,
               layouts [classroom, boardroom],
               facilities [projector], accessibility [],
               open thu 08:00-20:00
Anson Suite    location "12 Anson Road", capacity 150,
               layouts [theatre, cocktail],
               facilities [stage], accessibility [lift, hearing_loop],
               open sat 10:00-16:00
```

`2026-11-12` is a Thursday; `2026-11-14` a Saturday.

## TC-FRONTEND-057 — no filters shows every venue, in order

- **Steps:** `filterVenues(venues, emptyVenueFilters())`.
- **Test data:** Shared.
- **Expected:** All three, in the order given. The input list is unchanged.

- **Actual:**
- **Status:** Not Executed
- **Evidence:**

## TC-FRONTEND-058 — the text search matches location or name, ignoring case

- **Steps:** Filter with `query` set to each value below.
- **Test data:** `"anson"`; `"  HARBOUR "`; `"studio"`; `"nowhere"`.
- **Expected:** `"anson"` → Studio B and Anson Suite (location);
  `"  HARBOUR "` → Harbour Hall; `"studio"` → Studio B (name); `"nowhere"`
  → none.

- **Actual:**
- **Status:** Not Executed
- **Evidence:**

## TC-FRONTEND-059 — "holds at least" keeps venues with enough capacity

- **Steps:** Filter with `attendance` set to each value below.
- **Test data:** `"150"`; `"151"`; `""`.
- **Expected:** `"150"` → Harbour Hall and Anson Suite (equal counts);
  `"151"` → Harbour Hall; `""` → all three.

- **Actual:**
- **Status:** Not Executed
- **Evidence:**

## TC-FRONTEND-060 — facilities and accessibility need every one ticked

- **Steps:** Filter by each selection below.
- **Test data:** facilities `["projector"]`; facilities
  `["projector", "stage"]`; accessibility `["lift"]`; accessibility
  `["lift", "hearing_loop"]`.
- **Expected:** `["projector"]` → Harbour Hall and Studio B;
  `["projector", "stage"]` → Harbour Hall; `["lift"]` → Harbour Hall and
  Anson Suite; `["lift", "hearing_loop"]` → Anson Suite.

- **Actual:**
- **Status:** Not Executed
- **Evidence:**

## TC-FRONTEND-061 — date and time keep venues open then

- **Steps:** Filter by each date and time below.
- **Test data:**
  - `2026-11-12`, no times;
  - `2026-11-12`, `09:00`–`19:00`;
  - `2026-11-12`, `07:00`–`10:00`;
  - `2026-11-14`, `10:00`–`16:00`;
  - no date, `09:00`–`12:00`.
- **Expected:**
  - Thursday, no times → Harbour Hall and Studio B (open that day).
  - Thursday `09:00`–`19:00` → Harbour Hall and Studio B (inside
    `08:00`–`20:00`).
  - Thursday `07:00`–`10:00` → none (before opening).
  - Saturday `10:00`–`16:00` → Anson Suite (exactly its hours).
  - Times with no date → all three: times only apply with a date.

- **Actual:**
- **Status:** Not Executed
- **Evidence:**

## TC-FRONTEND-062 — results match every applied filter at once

- **Scenario:** AC2.
- **Steps:** Filter with every criterion set together.
- **Test data:** `query "anson"`, `attendance "100"`, `layout "theatre"`,
  facilities `["stage"]`, accessibility `["lift"]`, date `2026-11-14`,
  `10:00`–`12:00`.
- **Expected:** Anson Suite only. Changing the date to `2026-11-12` gives
  none.

- **Actual:**
- **Status:** Not Executed
- **Evidence:**

## TC-FRONTEND-063 — the request screen's filters start from the event

- **Steps:** `venueFiltersFromEvent(event)`.
- **Test data:** Event `expected_attendance: 100`, `room_layout: "theatre"`,
  `required_facilities: ["stage"]`, `required_accessibility: ["lift"]`,
  `start_date: "2026-11-14"`, `start_time: "10:00:00"`,
  `end_time: "12:00:00"`.
- **Expected:** `{query: "", attendance: "100", layout: "theatre",
  facilities: ["stage"], accessibility: ["lift"], date: "2026-11-14",
  startTime: "10:00", endTime: "12:00"}`. An event with no layout gives
  `layout: ""`.

- **Actual:**
- **Status:** Not Executed
- **Evidence:**

## TC-FRONTEND-064 — the room layout filter keeps venues that offer it

- **Steps:** Filter with `layout` set to each value below.
- **Test data:** `"theatre"`; `"boardroom"`; `"banquet"`; `""`.
- **Expected:** `"theatre"` → Harbour Hall and Anson Suite; `"boardroom"` →
  Studio B; `"banquet"` → Harbour Hall; `""` → all three.
- **Actual:**
- **Status:** Not Executed
- **Evidence:**

**Opening hours on the request screen (revised with the developer).**
**Clear filters** there now clears everything, including "open at the
booking's date and time", so every venue can be seen. The panel's **Only venues open
at the booking's date and time** checkbox, ticked by default, turns that
filter back on.

On both screens the filter panel starts **collapsed**, its header showing
**Filters** with how many are applied and a **Clear filters** button; opening
it shows the fields (confirmed with the developer, covered by TC-E2E-219 and
TC-E2E-210). A venue closed at the booking's date and
time is marked, and choosing it shows the S-35 warning and disables **Send
request**, like any other mismatch. Each venue's mark sits under its name.

## TC-FRONTEND-065 — a venue closed at the booking's date and time is marked

- **Steps:** Call `venueFit(event, venue, when)` with `when` set to each
  booking below.
- **Test data:** Event with no requirements, `expected_attendance: 10`.
  Venue capacity `100`, open `thu 08:00-20:00` only. Bookings:
  `2026-11-12` `09:00`–`12:00`; `2026-11-12` `07:00`–`10:00`;
  `2026-11-14` `10:00`–`12:00`; no `when` at all.
- **Expected:** Thursday inside hours → `[]`. Thursday `07:00`–`10:00` →
  `["Open 08:00–20:00 on Thursdays"]`. Saturday → `["Closed on
  Saturdays"]`. No `when` → `[]`, as TC-FRONTEND-035.
- **Actual:**
- **Status:** Not Executed
- **Evidence:**

## TC-FRONTEND-066 — a closed venue produces the S-35 warning

- **Steps:** `venueWarning(event, venue, when)` for the Saturday booking in
  TC-FRONTEND-065, with the venue named `Studio B`.
- **Expected:** `"Studio B doesn't suit this event: Closed on Saturdays.
  Choose a venue that fits."`
- **Actual:**
- **Status:** Not Executed
- **Evidence:**

## S-30 — view venue availability calendar

Story: S-30 View venue availability calendar.
Confirmed by the developer on 2026-09-30. Executed locally on 2026-09-30.
These cases cover a new `frontend/src/lib/venueAvailability.js` and additions
to `venueBookings.js` and `access.js`. They are pure functions, tested with no
browser. "Today" is passed in as a local date, `2026-11-10`, the same way
`DateSelect` in `EventRequestForm.jsx` reads the browser's own date. Studio B
is open `mon`–`fri` `08:00`–`18:00`.

## TC-FRONTEND-067 — the calendar shows one month, opening on tomorrow's, and moves a month at a time

- **Scenario:** A Coordinator views a venue a month at a time and moves with
  the arrows or the Month and Year dropdowns (AC1). Changed by the developer on 2026-09-30: one month at a time with arrows and Month/Year dropdowns, replacing the From/To range.
- **Steps:** Call `initialMonth` for today `2026-11-10`, `2026-11-30` and
  `2026-12-31`. Call `monthRange` for November 2026 and February 2028. Call
  `shiftMonth` from November 2026 by `+1`, `+2`, and from January 2027 by
  `-1`. Call `isBeforeMonth` against November 2026, and `yearOptions`.
- **Expected:**
  - It opens on the month tomorrow is in: November 2026, December 2026, January 2027.
  - The range fetched is the whole month: `2026-11-01`–`2026-11-30`, and
    `2028-02-01`–`2028-02-29` in a leap year.
  - The arrows cross years: December 2026, January 2027, back to December 2026.
  - October 2026 is before the first month, so ◀ is disabled there and
    earlier months are disabled in the dropdown. November 2026 and later
    months are not.
  - The Year dropdown offers 2026–2031, the six years `DateSelect` offers.
- **Actual:** As expected for every call.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_venue_availability.mjs — the calendar opens on the month tomorrow falls in, and shows a whole month`; `tests/unit/frontend/test_venue_availability.mjs — the arrows move one month, across years, and never before the first month`

## TC-FRONTEND-068 — each day gets one state and label, and a block outranks everything

- **Scenario:** Confirmed, held and blocked days are clearly distinct (AC2).
- **Pre-conditions:** The entries from TC-VENUEBOOKINGS-035.
- **Steps:** Call `availabilityDays({from: "2026-11-11", to: "2026-11-17"}, entries, operating_hours)`.
- **Expected:** Seven days:
  - `11 Nov` (wed) → `available`, "Available"
  - `12 Nov` → entries "Booked 09:00–12:00" and "Tentatively held 14:00–16:00",
    in start order
  - `13`–`16 Nov` → `blocked`, "Unavailable — Maintenance" (reason through
    `optionLabel`), **including** the weekend days, because a block outranks
    closed
  - `17 Nov` (tue) → `available`

  Available is `green`. Held uses the colour `bookingStatusMeta('pending')`
  already uses (amber). Booked is `rose` (red). Blocked is `sky`. Closed is
  `inkFaint`. No two states share a colour (changed by the developer on
  2026-09-30, so Booked never looks like Available).
  Every state has a text label, never colour alone.
- **Actual:** Days and labels as specified; available green, held amber, booked rose, blocked sky including the weekend, every colour distinct. Holds-only day reads held, in start order. Each day's block names its state, e.g. "Booked + Held".
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_venue_availability.mjs — each block names its state`; `tests/unit/frontend/test_venue_availability.mjs — each day gets one state and label, and a block outranks everything`; `tests/unit/frontend/test_venue_availability.mjs — a day with only holds reads as held, and holds sort by start time`

## TC-FRONTEND-069 — days before tomorrow are greyed and disabled, like DateSelect

- **Scenario:** Unselectable dates are greyed out (AC1, as clarified).
- **Steps:** Build the November 2026 grid with today `2026-11-10`, then the
  December 2026 grid. Read each cell's `disabled`. (Changed by the developer on 2026-09-30: one month at a time with arrows and Month/Year dropdowns, replacing the From/To range.)
- **Expected:** Weeks start on Sunday, as in `DateSelect`
  (`Su Mo Tu We Th Fr Sa`). In November, `1`–`10 Nov` (today included) are
  `disabled: true` and `11`–`30 Nov` are enabled; the earliest selectable day
  is `2026-11-11`, `DateSelect`'s own rule. December has two blanks before
  the 1st (a Tuesday) and every day enabled.
- **Actual:** Sunday-first grid; 1–10 Nov disabled, 11–30 enabled; December had two leading blanks and no disabled day.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_venue_availability.mjs — days before tomorrow are greyed and disabled`; `tests/unit/frontend/test_venue_availability.mjs — a later month is fully selectable, with leading blanks before the 1st`

## TC-FRONTEND-070 — closed weekdays read as Closed, not Available

- **Scenario:** A day outside the venue's opening hours is not shown as free
  (AC2).
- **Steps:** Build days for `2026-11-14`..`2026-11-16` with no entries.
- **Expected:** `14 Nov` (sat) and `15 Nov` (sun) → `closed`, "Closed",
  found by the same `WEEK` day-key lookup as `venues.js`. `16 Nov` (mon) →
  `available`.
- **Actual:** Sat and Sun `closed`/"Closed"; Mon `available`.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_venue_availability.mjs — closed weekdays read as Closed, not Available`

## TC-FRONTEND-071 — the API helpers call the composite fresh each time and surface failures

- **Scenario:** Opening, changing the range, or pressing Refresh always
  refetches (AC3).
- **Steps:** With a fake `fetch`, call
  `getVenueAvailability(venueId, "2026-11-11", "2026-12-08")` twice, then
  `addVenueBlock(form)` and `removeVenueBlock(id)`. Pass the errors each
  answer produces to `availabilityErrorMessage`.
- **Expected:** Both reads issue
  `GET /api/venue-bookings/availability?venue_id=…&from=2026-11-11&to=2026-12-08`
  through `requestJSON`, with credentials included, so two calls make two
  requests. The add is a `POST /api/venue-bookings/blocks` with the JSON body;
  a blank note is sent as `null`. The remove is a
  `DELETE /api/venue-bookings/blocks/{id}`, and its `204` resolves to `null`.
  The messages:
  - `401` → "Your session has expired. Please sign in again."
  - `403` → "Your role is not permitted to view venue availability."
  - `404` → the server's detail
  - anything else → "We couldn't load this venue's availability. Try again
    in a moment."

  A failure never resolves to an empty calendar.
- **Actual:** Four requests with the specified URLs, methods and credentials; blank note sent as null; `204` resolved to null. Each failure rejected with an `ApiError` mapped to the specified message.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_venue_availability.mjs — the API helpers call the composite fresh each time`; `tests/unit/frontend/test_venue_availability.mjs — a failed load rejects with a message and never an empty calendar`

## TC-FRONTEND-072 — hold and block conflicts are shown in the server's words

- **Scenario:** A Coordinator refused by a hold or block, or staff refused by
  a block, see why.
- **Steps:** Pass `ApiError`s with status `409` and each TC-BOOKINGS-025,
  026 and 028 detail to `venueBookingErrorMessages`. Pass the TC-BOOKINGS-028
  detail to `bookingDecisionErrorMessage`.
- **Expected:** Each returns the detail exactly. The request helper already
  does this for every `409`. The decision helper, which today recognises only
  "already confirmed", now also recognises "is unavailable from". Other `409`s
  still say "This request has already been decided…".
- **Actual:** All three details returned exactly; the decision helper returned the block and S-38 details, and the generic message otherwise.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_venue_availability.mjs — hold and block conflicts are shown in the server's words`

## TC-FRONTEND-073 — Coordinators and Venue Staff see the calendar, and only staff manage blocks

- **Scenario:** `access.js` agrees with the composite's role checks (AC1).
- **Steps:** Call `hasPermission(role, …)` for each role.
- **Expected:** `PERMISSIONS.VIEW_VENUE_AVAILABILITY`
  (`venue_bookings:view_availability`) is granted to `event_coordinator` and
  `venue_staff` only. `PERMISSIONS.MANAGE_VENUE_BLOCKS`
  (`venue_bookings:manage_blocks`) is granted to `venue_staff` only.
- **Actual:** Only Coordinator and Venue Staff had `view_availability`; only Venue Staff had `manage_blocks`.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_venue_availability.mjs — Coordinators and Venue Staff see the calendar, and only staff manage blocks`

## S-44 — check equipment availability

Story: S-44 Check equipment availability.
Confirmed by the developer on 2026-09-30. Not yet executed.
These cases cover a new `frontend/src/lib/equipmentAvailability.js` and an
addition to `access.js`. Today is passed in as `2026-11-10`.

## TC-FRONTEND-074 — the check's form is validated before anything is sent

- **Scenario:** Useful messages before a request (S-44 AC1).
- **Steps:** Call `validateAvailabilityForm` with: everything blank; start
  `2026-11-12 12:00` and end `2026-11-12 12:00`; end date before start date;
  quantity `0`, `-2` and `1.5`; a valid window with a blank type and quantity.
- **Expected:** Blank → "Choose a start date and time." and "Choose an end
  date and time."; equal or reversed → "The end must be after the start.";
  bad quantities → "Enter a whole number of 1 or more, or leave it blank.";
  the last → no errors (type and quantity are optional).
- **Actual:** All the specified messages; a valid window with blank type and quantity had none.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_equipment_availability.mjs — the check form is validated before anything is sent`

## TC-FRONTEND-075 — each item reads as available, short, unavailable or over-reserved

- **Scenario:** The result's wording (S-44 AC1, AC2).
- **Steps:** Call `availabilitySummary(item)` for the items in
  TC-EQUIPMENTREQUIREMENTS-012 and 014, with and without a quantity.
- **Expected:**
  - Microphone → "2 of 12 available", with the reserved "10 reserved".
  - With quantity 2 → "Enough" (green); with 3 → "Not enough — 2 available" (rose).
  - Projector (maintenance) → "0 of 4 available — Maintenance" (amber),
    and "Not enough" whenever a quantity is given.
  - Over-reserved → "0 of 12 available — over-reserved by 2".

  Each status has a text label, never colour alone.
- **Actual:** "2 of 12 available", "10 reserved", "Enough" (green), "Not enough — 2 available" (rose), "0 of 4 available — Maintenance" (amber), "over-reserved by 2".
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_equipment_availability.mjs — each item reads as available, short, unavailable or over-reserved`

## TC-FRONTEND-076 — the API helper sends only what was filled in

- **Steps:** Call `checkEquipmentAvailability(form)` with a fake `fetch`: once
  with type " Mic " and quantity "3", once with both blank.
- **Expected:** `GET /api/equipment-requirements/availability?start_date=2026-11-12&start_time=09:00&end_date=2026-11-12&end_time=12:00&type=Mic&quantity=3`
  through `requestJSON` with credentials; the second omits `type` and
  `quantity`. Two calls make two requests.
- **Actual:** Two requests to the specified path through `requestJSON` with credentials; blank type and quantity omitted. The times' `:` is sent URL-encoded as `%3A`, which the service reads as the same value.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_equipment_availability.mjs — the API helper sends only what was filled in`

## TC-FRONTEND-077 — only Technical Support can open the check

- **Steps:** Call `hasPermission(role, PERMISSIONS.CHECK_EQUIPMENT_AVAILABILITY)`
  for each role.
- **Expected:** `equipment:check_availability`, granted to
  `technical_support` only.
- **Actual:** Only `technical_support` has `equipment:check_availability`.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_equipment_availability.mjs — only Technical Support can open the check`

## TC-FRONTEND-078 — failures are shown, never an empty result, and the check time is shown

- **Steps:** Pass `ApiError`s with 401, 403, 422 (with field errors) and 502
  to `availabilityErrorMessages`. Call `checkedAtLabel("2026-11-10T06:32:10Z")`
  in UTC.
- **Expected:** 401 → "Your session has expired. Please sign in again.";
  403 → "Only Technical Support can check equipment availability."; 422 → the
  field messages; 502 → "We couldn't check availability. Nothing is shown
  until it works — try again in a moment." The label reads
  "Checked at 06:32".
- **Actual:** Each status gave the specified message; the label read "Checked at 06:32".
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_equipment_availability.mjs — failures are shown, never an empty result, and the check time is shown`

## S-33 — place tentative venue hold

Story: S-33 Place Tentative Venue Hold.
Confirmed by the developer on 2026-09-30. Not yet executed.

### TC-FRONTEND-079 — Hold actions and errors follow Venue Staff permissions

- **Scenario:** A Venue Staff member can hold a Pending request without the browser claiming a booking is confirmed (AC1).
- **Pre-conditions:** Frontend access and booking helpers loaded; mocked fetch.
- **Steps:** Check every role; place a hold; map `401`, `403`, `404`, `409`, `422`, `500` and network failures.
- **Test data:** Booking B; identified Held/Confirmed conflict responses.
- **Expected:** Only Venue Staff receive the hold permission. The authenticated action sends no protected metadata. Success renders Held and keeps Confirm/Reject actions. Conflict names the blocking slot; failures never show success or Confirmed.
- **Actual:** Venue Staff alone received the permission; hold/release used credentialled routes with safe success and error mapping.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_access.mjs` and `tests/unit/frontend/test_venue_bookings.mjs`

### TC-FRONTEND-080 — Availability calendar distinguishes Tentative and Confirmed slots

- **Scenario:** Venue Staff can visually distinguish active holds from final bookings (AC2, AC4).
- **Pre-conditions:** Availability helper receives Held, Confirmed and Released rows.
- **Steps:** Load a venue/month; map entries to calendar presentation; apply a release response without reloading the page.
- **Test data:** Studio B in November 2026: Held `09:00`–`12:00`, Confirmed `13:00`–`16:00`, Released `17:00`–`18:00`.
- **Expected:** The request is credentialled and scoped to venue/date range. Held displays `Tentative hold` with a distinct label/colour from `Confirmed`. Released is absent. After release, the Tentative entry disappears immediately and the slot displays as available.
- **Actual:** Held entries map to Tentative while Confirmed remains distinct, and released Pending rows do not appear on the calendar.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_venue_bookings.mjs` and existing calendar presentation tests; full Node suite, 93 passed.

## S-43 — Technical Support assigned-event visibility

Story: S-43 Auto-Assign Technical Support.
Specification updated by the developer on 2026-10-05.

### TC-FRONTEND-081 — assigned-event reads use authenticated gateway routes

- **Scenario:** Technical Support asks the backend for its own assignment;
  the browser never chooses a staff id.
- **Pre-conditions:** Mocked `fetch` returns two active assigned events.
- **Steps:** List assigned support events and fetch one by an id containing
  URL-sensitive characters.
- **Test data:** Event id `event/support 1`.
- **Expected:** Credentialed GETs use `/api/events/support-assigned` and
  `/api/events/support-assigned/event%2Fsupport%201`. No query parameter,
  header, or body contains a staff id.
- **Actual:** Both helpers sent credentialed GETs to the expected encoded Kong
  routes with no caller-selected staff identifier.
- **Status:** Pass
- **Evidence:** `test_technical_support_assignment.mjs` — `assigned support event reads use authenticated gateway routes without a staff id`

### TC-FRONTEND-082 — the workspace groups assigned events with their equipment

- **Scenario:** Technical Support can identify each active assignment and the
  equipment they must prepare.
- **Pre-conditions:** The assigned-events API returns one planning and one
  confirmed event; the requirements API returns requirements for those events.
- **Steps:** Build the dashboard assignment presentation.
- **Test data:** `Sound check` and `Awards night`, with dates/times, support
  notes, Microphone ×2 and Projector ×1.
- **Expected:** The Assigned events area shows both event names, dates/times,
  statuses, support notes, and the matching equipment under the correct
  event. It does not render a requirement whose `event_id` is not in the
  assigned-event response.
- **Actual:** The presentation helper kept planning and confirmed assignments,
  grouped each matching requirement under its event, and discarded an
  unrelated requirement.
- **Status:** Pass
- **Evidence:** `test_technical_support_assignment.mjs` — `assigned event work groups only matching equipment under active events`

### TC-FRONTEND-083 — catalogue and assignment failure states remain honest

- **Scenario:** Shared inventory stays shared while assignment failures never
  look like an empty workload.
- **Pre-conditions:** Exercise an empty assignment response and rejected
  assignment/requirements requests while the catalogue succeeds.
- **Steps:** Resolve the dashboard state for each response.
- **Test data:** Empty arrays; HTTP `401`, `403`, `404`, and `502`; catalogue
  item `Shared microphone`.
- **Expected:** The complete Equipment Catalogue remains visible and
  manageable. A successful empty assignment says no active events are
  assigned. A failed load shows a safe error with retry rather than the empty
  message or unrelated requirements.
- **Actual:** Empty work remained an empty successful collection; each failure
  mapped to safe assignment feedback instead of being presented as no work.
  The catalogue code and permissions remained independent and all frontend
  unit tests passed.
- **Status:** Pass
- **Evidence:** `test_technical_support_assignment.mjs` — `assigned event failures stay distinct from an empty workload`; `node --test tests/unit/frontend/test_*.mjs`: 97 passed.

## S-75 — configure venue setup and turnaround time

Story: S-75 Configure Venue Setup and Turnaround Time.
Confirmed by the developer on 2026-10-07. Not yet executed.
Studio B: open `thu` 08:00–20:00, setup 30, turnaround 45.

## TC-FRONTEND-088 — the venue form records both times, 0 or more

- **Steps:** Build an empty venue form and an edit form from a venue with
  30/45; validate with `""`, `-1`, `1.5` and `0` in each field; build both
  payloads.
- **Expected:** An empty form starts at `"0"`/`"0"`; the edit form loads
  `"30"`/`"45"`. Blank, `-1` and `1.5` → "Enter whole minutes, 0 or more." on
  that field; `0` is fine. Payloads send integers, and the edit payload
  includes the two times alongside the existing editable fields.
- **Actual:** Empty form 0/0, edit form 30/45; blank, -1 and 1.5 gave the message on both forms; integers sent.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_setup_turnaround.mjs — the venue form records both times, 0 or more`

## TC-FRONTEND-089 — the request screen applies setup and turnaround to opening hours

- **Steps:** `venueFit` and the "open then" filter for Studio B on a Thursday
  at 08:00–10:00, 08:30–10:00 and 18:00–19:30.
- **Expected:** 08:30–10:00 fits. The others give "Open 08:00–20:00 on
  Thursdays, with 30 min setup and 45 min turnaround" and are filtered out
  when "open then" is on. A venue with 0/0 behaves as before.
- **Actual:** 08:30–10:00 fits; 08:00 and 19:30 gave the specified problem and were filtered out; 0/0 behaves as before.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_setup_turnaround.mjs — the request screen applies setup and turnaround to opening hours`

## TC-FRONTEND-090 — the calendar shows the event's time and the venue's time in use

- **Steps:** Build the 2026-11-12 day for Studio B with A confirmed and B held.
- **Expected:** "Booked 10:00–12:00 · venue in use 09:30–12:45" and
  "Tentatively held 12:30–14:00 · venue in use 12:00–14:45". With 0/0 there
  is no "venue in use" part. `setupTurnaroundLabel` reads "Setup 30 min ·
  Turnaround 45 min".
- **Actual:** Both labels as specified; no "venue in use" with 0/0; "Setup 30 min · Turnaround 45 min".
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_setup_turnaround.mjs — the calendar shows the event time and the time the venue is in use`

## TC-FRONTEND-091 — a clashing booking shows a warning to its Coordinator

- **Steps:** `bookingClashMessage(booking)` for B with the clash from
  TC-VENUEBOOKINGS-053, and for a booking with `clashes: []`.
- **Expected:** "Clashes with another confirmed booking on 12 Nov 2026,
  10:00–12:00 (venue in use 09:30–12:45) under Studio B's setup and
  turnaround times. Contact Venue Staff to rearrange." — and `null` with no
  clashes.
- **Actual:** The specified warning; null with no clashes.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_setup_turnaround.mjs — a clashing booking shows a warning to its Coordinator`

## TC-FRONTEND-085 — Venue Staff see the clashes after saving

- **Steps:** `getVenueClashes(venueId)` with a fake `fetch`; then
  `clashPairLabel(pair)` for the A–B pair.
- **Expected:** `GET /api/venue-bookings/clashes?venue_id=…` with credentials.
  The label reads "Alumni talk (Confirmed, 10:00–12:00) and Board lunch
  (Tentatively held, 12:30–14:00) on 12 Nov 2026". ("Tentatively held" is the
  app's existing label for a held request since S-33; the confirmed draft
  said "Held".)
- **Actual:** The specified request with credentials; the pair label as specified, with "Tentatively held".
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_setup_turnaround.mjs — Venue Staff see the clashes after saving`

## TC-FRONTEND-086 — each pending request is one compact row that opens its page

- **Steps:** `pendingRequestSummary(booking)` for pending D and held B (with
  its clash), and `pendingRequestPath(booking)`.
- **Expected:** D → title "Alumni talk", line "Studio B · 12 Nov 2026,
  12:15–12:45", status "Pending". B → status "Tentatively held" (the app's
  label for held since S-33; the confirmed draft said "Held") and the flag
  "Clash".
  The path is `/venue-bookings/{id}`. No decision or hold controls are part of
  the row.
- **Actual:** D and B summaries as specified (B "Tentatively held" with "Clash"); path `/venue-bookings/b1`.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_setup_turnaround.mjs — each pending request is one compact row that opens its page`

## TC-FRONTEND-087 — the request page is Venue Staff only, and a decision returns to the list once

- **Steps:** Check `PERMISSIONS.VIEW_PENDING_VENUE_BOOKINGS` for each role;
  call `decisionNotice("approved", booking)` and `decisionNotice("rejected",
  booking)`.
- **Expected:** Only `venue_staff` can open `/venue-bookings/:id`. The notices
  read "Booking for Alumni talk at Studio B confirmed." and "… rejected." —
  shown once on the dashboard after returning, then cleared, so a reload does
  not repeat it.
- **Actual:** Only venue_staff can open the page; both notices read as specified.
- **Status:** Pass
- **Evidence:** `tests/unit/frontend/test_setup_turnaround.mjs — the request page is Venue Staff only, and a decision notice reads once`
