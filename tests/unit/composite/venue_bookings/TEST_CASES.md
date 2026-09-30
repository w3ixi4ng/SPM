# Test cases — venue_bookings service (unit)

Covers `tests/unit/composite/venue_bookings/test_app.py`: the composite that
stands between the browser and three atomic services for venue booking
requests. For a Coordinator's request it checks the session (`users`), the
event (`events`) and the venue (`venues`), then writes the request
(`bookings`). For Venue Staff it serves the pending list. All four outbound
clients are faked and record every call. There is no network, database, or
Docker.

| | |
| --- | --- |
| Suite | `pytest tests/unit/composite/venue_bookings` |
| Last run | 2026-09-27, branch `S-36/submit-venue-booking-request` at `665c7b3` |
| Environment | Python 3.12.5, pytest 9.1.1, FastAPI 0.116.1, Pydantic 2.11.7, httpx 0.28.1, supabase-py 2.31.0; no network, database, or Docker |
| Result | 65 passed |

**Story:** S-36 Submit venue booking request.

**Acceptance criteria → cases**

| Acceptance criterion | Cases |
| --- | --- |
| AC1: A Coordinator can submit a booking request for a specific venue, date and time against an event | 002–011, 017, 019, 020 |
| AC2: The request includes the event's relevant requirements needed for Venue Staff to assess it | 012–016, 018 |
| AC3: A submitted request appears in Venue Staff's pending-requests view | 021–024 |
| AC4: A Coordinator can see the booking requests they have sent for an event, with each one's status | 025–030 |

The conditions agreed with the developer behind AC1 and AC2:

- A Coordinator can request a venue only for an event **assigned to them**
  and in status **`planning`**. Submitting a request does not change the
  event's status.
- The booking is on **one date**. Its start and end must fall inside the
  event's own start and end, with equal times allowed. They must also fall
  inside the venue's opening hours for that weekday.
- The venue requirements come from the **event**: the organiser gives a
  room layout, facilities and accessibility features when creating it. The
  Coordinator chooses only the venue, the date and time, and optional notes.
- A request is **refused at submission** when the event's
  `expected_attendance` exceeds the venue's `capacity`, or when the event's
  room layout, facilities or accessibility features are not all offered by
  the venue. This
  is validation, not a booking decision: nothing is saved, and Venue Staff
  never see it. Venue Staff's own approve/reject is the Venue Booking
  Approval story.
- The event's details are **copied** onto the request when it is submitted.
  Later edits to the event do not change a request already sent.
- Duplicate and overlapping requests are **not** checked here. They belong to
  the tentative-holds and conflict-detection stories.
- **All** Venue Staff see every pending request.

**Shared pre-conditions.** The app built with `get_users_client`,
`get_events_client`, `get_venues_client` and `get_bookings_client`
overridden by fakes. Unless a case says otherwise:
- `GET /users/me` resolves to the shared coordinator.
- `GET /events/assigned/{event_id}` returns the shared event.
- `GET /venues/{venue_id}` returns the shared venue.
- `POST /bookings` returns `201` with the body it was sent, plus an `id`,
  `status: "pending"` and `submitted_at`.

**Shared test data.**

```
coordinator   id cccccccc-…, name "Grace Hopper", email grace@example.com,
              role event_coordinator

event         id eeeeeeee-…, status planning, assigned to the coordinator
              name "Alumni networking evening"
              purpose "Reconnect graduates with faculty"
              2026-11-12 09:00 -- 2026-11-12 18:00        (a Thursday)
              expected_attendance 120
              special_requirements "Vegetarian catering for 40"
              room_layout theatre
              required_facilities [projector]
              required_accessibility [wheelchair_access]

venue         id vvvvvvvv-…, name "Studio B", capacity 150
              facilities    [projector, sound_system, wifi]
              accessibility [wheelchair_access, lift]
              room_layouts  [theatre, classroom]
              operating_hours thu 08:00-20:00, fri 08:00-20:00  (closed Sat)

request body  {"event_id": <event>, "venue_id": <venue>,
               "booking_date": "2026-11-12",
               "start_time": "09:00", "end_time": "12:00",
               "notes": "Access from 08:30 for setup"}
```

"Refused at submission" below means: `422` with
`{"detail": "This venue can't take this booking", "errors": {...}}`, the
named key present in `errors`, and **no** call to `POST /bookings`.

---

## TC-VENUEBOOKINGS-001 — health check

- **Scenario:** The service reports itself up without calling anything
  downstream.
- **Pre-conditions:** Shared.
- **Steps:** `GET /health`.
- **Test data:** None.
- **Expected:** `200`, `{"status": "ok"}`; no client called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_health_reports_ok`

## TC-VENUEBOOKINGS-002 — a request needs a session

- **Pre-conditions:** `GET /users/me` answers `401`.
- **Steps:** `POST /venue-bookings` with the shared body and no cookies.
- **Test data:** Shared body.
- **Expected:** `401`, `{"detail": "Not authenticated"}`; events, venues and
  bookings are never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_request_needs_a_session`

## TC-VENUEBOOKINGS-003 — only an Event Coordinator can submit a request

- **Pre-conditions:** `GET /users/me` resolves to each other role in turn.
- **Steps:** `POST /venue-bookings` with the shared body, once per role.
- **Test data:** Roles `event_organiser`, `venue_staff`,
  `technical_support`, `attendee`.
- **Expected:** `403`, `{"detail": "Permission denied"}` for every one;
  events, venues and bookings are never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_an_event_coordinator_can_submit`

## TC-VENUEBOOKINGS-004 — the body is checked before any downstream call

- **Scenario:** Revised for S-36: the requirements come from the event, not the request. A malformed request costs no call to events, venues or
  bookings.
- **Pre-conditions:** Shared.
- **Steps:** `POST /venue-bookings` once for each bad body below.
- **Test data:**
  - `venue_id` missing
  - `booking_date` missing
  - `end_time` `"09:00"` with `start_time` `"09:00"`
  - `room_layout: "theatre"` (the event's, not the request's)
  - `required_facilities: ["projector"]` (likewise)
  - an extra field `"status": "approved"`
- **Expected:** `422` with the offending field in `errors` for each one.
  No downstream service is called, not even users: FastAPI checks the body
  before the route runs, the same as TC-EVENTREQUESTS-004.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_body_is_checked_before_any_downstream_call`, `test_app.py::test_an_end_time_before_the_start_names_the_problem`

## TC-VENUEBOOKINGS-005 — a Coordinator cannot book for an event not assigned to them

- **Scenario:** The events service decides who is assigned. The composite
  forwards the Coordinator's own session and takes the answer as given.
- **Pre-conditions:** `GET /events/assigned/{event_id}` answers `404`.
- **Steps:** `POST /venue-bookings` with the shared body.
- **Test data:** Shared body.
- **Expected:** `404`, `{"detail": "Event not found"}`. The events call
  carried the request's cookies. Venues and bookings are never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_coordinator_cannot_book_for_an_event_not_assigned_to_them`

## TC-VENUEBOOKINGS-006 — only an event in planning can have a venue requested

- **Pre-conditions:** The shared event, with its status set to each value
  below in turn.
- **Steps:** `POST /venue-bookings` with the shared body, once per status.
- **Test data:** `submitted`, `returned`, `rejected`.
- **Expected:** `409`,
  `{"detail": "A venue can only be requested for an event in planning"}`
  for every one; venues and bookings are never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_an_event_in_planning_can_have_a_venue_requested`

## TC-VENUEBOOKINGS-007 — the venue must exist

- **Pre-conditions:** `GET /venues/{venue_id}` answers `404`.
- **Steps:** `POST /venue-bookings` with the shared body.
- **Test data:** Shared body with a random `venue_id`.
- **Expected:** `404`, `{"detail": "Venue not found"}`; bookings is never
  called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_venue_must_exist`

## TC-VENUEBOOKINGS-008 — the booking must fall inside the event's date and time

- **Pre-conditions:** Shared.
- **Steps:** `POST /venue-bookings` once for each window below.
- **Test data:** All are inside the venue's opening hours:
  - `2026-11-13` `09:00`–`12:00` (a day the event is not on)
  - `2026-11-12` `08:30`–`10:00` (starts before the event)
  - `2026-11-12` `17:00`–`19:00` (ends after the event)
- **Expected:** Each is refused at submission with `errors.booking_date`
  = `"The booking must fall within the event's date and time"`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_booking_must_fall_inside_the_event`

## TC-VENUEBOOKINGS-009 — a booking may use the event's full window, and one day of a multi-day event

- **Scenario:** The window check is inclusive. On a multi-day event, any
  single day inside it is valid.
- **Pre-conditions:** Shared; for the second step, the event runs
  `2026-11-12 18:00` to `2026-11-13 12:00`.
- **Steps:** 1. `POST /venue-bookings` for `2026-11-12` `09:00`–`18:00`
  against the shared event. 2. `POST /venue-bookings` for `2026-11-13`
  `08:00`–`12:00` against the multi-day event.
- **Test data:** As above.
- **Expected:** `201` both times.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_booking_may_use_the_events_full_window`, `test_app.py::test_a_booking_may_use_one_day_of_a_multi_day_event`

## TC-VENUEBOOKINGS-010 — the venue must be open that day

- **Pre-conditions:** The event runs `2026-11-14 10:00`–`12:00`, a Saturday.
  The venue has no Saturday hours.
- **Steps:** `POST /venue-bookings` for `2026-11-14` `10:00`–`12:00`.
- **Test data:** As above.
- **Expected:** Refused at submission with `errors.operating_hours`
  = `"Studio B is closed on Saturdays"`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_venue_must_be_open_that_day`

## TC-VENUEBOOKINGS-011 — the booking must fall inside the venue's opening hours

- **Scenario:** Opening hours are inclusive at both ends.
- **Pre-conditions:** The event runs `2026-11-12 06:00`–`23:00`, so only the
  venue's hours (`08:00`–`20:00`) can fail.
- **Steps:** `POST /venue-bookings` once for each window below.
- **Test data:** `07:00`–`09:00`; `19:00`–`21:00`; `08:00`–`20:00`.
- **Expected:** The first two are refused at submission with
  `errors.operating_hours` = `"Studio B is open 08:00–20:00 on Thursdays"`.
  The third returns `201`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_booking_must_fall_inside_opening_hours`, `test_app.py::test_opening_hours_are_inclusive`

## TC-VENUEBOOKINGS-012 — the venue must hold the expected attendance

- **Pre-conditions:** Shared, with the event's `expected_attendance` set to
  each value below.
- **Steps:** `POST /venue-bookings` with the shared body, once per value.
- **Test data:** `151`; `150`.
- **Expected:** `151` is refused at submission with
  `errors.expected_attendance`
  = `"Studio B holds 150 people; this event expects 151"`. `150` returns
  `201`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_venue_must_hold_the_expected_attendance`, `test_app.py::test_attendance_equal_to_capacity_is_accepted`

## TC-VENUEBOOKINGS-013 — every required facility must be at the venue

- **Scenario:** Revised for S-36: the requirements come from the event, not the request.
- **Pre-conditions:** Shared, with the event's `required_facilities` set to
  `["projector", "stage", "whiteboard"]`.
- **Steps:** `POST /venue-bookings` with the shared body.
- **Test data:** As above. The venue has `projector` but not `stage` or
  `whiteboard`.
- **Expected:** Refused at submission with `errors.required_facilities`
  = `"Studio B does not have: stage, whiteboard"`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_every_required_facility_must_be_at_the_venue`

## TC-VENUEBOOKINGS-014 — every required accessibility feature must be at the venue

- **Scenario:** Revised for S-36: the requirements come from the event, not the request.
- **Pre-conditions:** Shared, with the event's `required_accessibility` set
  to `["wheelchair_access", "hearing_loop"]`.
- **Steps:** `POST /venue-bookings` with the shared body.
- **Test data:** As above. The venue lacks `hearing_loop`.
- **Expected:** Refused at submission with `errors.required_accessibility`
  = `"Studio B does not have: hearing_loop"`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_every_required_accessibility_feature_must_be_at_the_venue`

## TC-VENUEBOOKINGS-015 — the room layout must be one the venue offers

- **Scenario:** Revised for S-36: the requirements come from the event, not the request.
- **Pre-conditions:** Shared, with the event's `room_layout` set to
  `banquet`.
- **Steps:** `POST /venue-bookings` with the shared body.
- **Test data:** As above. The venue offers `theatre` and `classroom` only.
- **Expected:** Refused at submission with `errors.room_layout`
  = `"Studio B does not offer the banquet layout"`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_room_layout_must_be_one_the_venue_offers`

## TC-VENUEBOOKINGS-016 — every problem is reported at once

- **Scenario:** Revised for S-36: the requirements come from the event, not the request. A Coordinator fixes everything in one pass instead of
  discovering problems one at a time.
- **Pre-conditions:** Shared, with the event's `expected_attendance` at
  `200`, `room_layout` `banquet` and `required_facilities` `["stage"]`.
- **Steps:** `POST /venue-bookings` for `2026-11-12` `07:00`–`10:00`.
- **Test data:** As above.
- **Expected:** One `422` whose `errors` holds exactly these keys:
  `booking_date`, `operating_hours`, `expected_attendance`,
  `required_facilities`, `room_layout`. Bookings is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_every_problem_is_reported_at_once`

## TC-VENUEBOOKINGS-017 — an event with no venue requirements, and no notes

- **Scenario:** Revised for S-36: the requirements come from the event, not the request.
- **Pre-conditions:** Shared, with the event's `room_layout` null and both
  requirement lists empty.
- **Steps:** `POST /venue-bookings` with only `event_id`, `venue_id`,
  `booking_date`, `start_time` and `end_time`.
- **Test data:** As above.
- **Expected:** `201`. The body sent to `POST /bookings` has
  `room_layout=null`, `required_facilities=[]`,
  `required_accessibility=[]` and `notes=null`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_an_event_with_no_venue_requirements_and_no_notes`

## TC-VENUEBOOKINGS-018 — the request carries the event's requirements for Venue Staff

- **Scenario:** Revised for S-36: the free-text accessibility notes are gone; `special_requirements` (Other requirements) is the one free-text field. Revised for S-36: the requirements come from the event, not the request. AC2. What Venue Staff need — including the room layout,
  facilities, accessibility features and other requirements — is copied onto the request from
  the event, the venue and the session. None of it is taken from the
  browser.
- **Pre-conditions:** Shared.
- **Steps:** `POST /venue-bookings` with the shared body.
- **Test data:** Shared.
- **Expected:** `POST /bookings` is called once, with exactly:

  ```json
  {
    "event_id": "<event>", "venue_id": "<venue>",
    "coordinator_id": "<coordinator>",
    "coordinator_name": "Grace Hopper",
    "coordinator_email": "grace@example.com",
    "booking_date": "2026-11-12",
    "start_time": "09:00:00", "end_time": "12:00:00",
    "event_name": "Alumni networking evening",
    "event_purpose": "Reconnect graduates with faculty",
    "expected_attendance": 120,
    "special_requirements": "Vegetarian catering for 40",
    "required_accessibility": ["wheelchair_access"],
    "required_facilities": ["projector"],
    "room_layout": "theatre",
    "notes": "Access from 08:30 for setup",
    "venue_name": "Studio B"
  }
  ```

  The response is `201` with the bookings service's body, including
  `status: "pending"`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_request_carries_the_events_requirements_for_venue_staff`

## TC-VENUEBOOKINGS-019 — submitting a request writes nothing to the event

- **Scenario:** The event is already in planning and stays there. This
  story changes only the bookings table.
- **Pre-conditions:** Shared.
- **Steps:** `POST /venue-bookings` with the shared body.
- **Test data:** Shared.
- **Expected:** `201`. The events fake received exactly one call, the
  `GET /events/assigned/{event_id}`, and no `POST`, `PATCH` or `PUT`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_submitting_a_request_writes_nothing_to_the_event`

## TC-VENUEBOOKINGS-020 — a service that can't be reached is a 502, and nothing is half-written

- **Pre-conditions:** One downstream service fails at a time. Each fails
  once by raising `httpx.ConnectError` and once by answering `500`.
- **Steps:** `POST /venue-bookings` with the shared body, once per failure.
- **Test data:** users, events, venues, bookings.
- **Expected:** `502`, with detail `"Users service unavailable"`,
  `"Events service unavailable"`, `"Venues service unavailable"` or
  `"Bookings service unavailable"` respectively. When users, events or
  venues fail, bookings is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_service_that_cannot_be_reached_is_a_502`

## TC-VENUEBOOKINGS-021 — the pending list needs a session

- **Pre-conditions:** `GET /users/me` answers `401`.
- **Steps:** `GET /venue-bookings/pending` with no cookies.
- **Test data:** None.
- **Expected:** `401`; bookings is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_pending_list_needs_a_session`

## TC-VENUEBOOKINGS-022 — only Venue Staff see the pending list

- **Pre-conditions:** `GET /users/me` resolves to each other role in turn.
- **Steps:** `GET /venue-bookings/pending`, once per role.
- **Test data:** `event_coordinator`, `event_organiser`,
  `technical_support`, `attendee`.
- **Expected:** `403`, `{"detail": "Permission denied"}` for every one;
  bookings is never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_venue_staff_see_the_pending_list`

## TC-VENUEBOOKINGS-023 — any Venue Staff member sees every pending request

- **Scenario:** AC3. The list is not filtered by who created the venue.
- **Pre-conditions:** `GET /users/me` resolves to a `venue_staff` user who
  created neither venue. `GET /bookings?status=pending` returns two
  bookings for two venues created by other staff.
- **Steps:** `GET /venue-bookings/pending`.
- **Test data:** As above.
- **Expected:** `200` with both bookings, in the order the bookings service
  returned them. The bookings call was `GET /bookings` with
  `status=pending`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_any_venue_staff_member_sees_every_pending_request`

## TC-VENUEBOOKINGS-024 — the pending list fails loudly when bookings is down

- **Pre-conditions:** A `venue_staff` session. The bookings fake raises
  `httpx.ConnectError`, then answers `500`.
- **Steps:** `GET /venue-bookings/pending`, once per failure.
- **Test data:** As above.
- **Expected:** `502`, `{"detail": "Bookings service unavailable"}` both
  times. An outage is never shown as an empty list.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_pending_list_fails_loudly_when_bookings_is_down`

---

**S-36 AC4 additions.** `GET /venue-bookings?event_id={event}` lists the
requests sent for one event. Only a Coordinator the event is assigned to can
list them, checked the same way as submitting: through the events service
with the Coordinator's own session.

## TC-VENUEBOOKINGS-025 — listing an event's requests needs a session

- **Pre-conditions:** `GET /users/me` answers `401`.
- **Steps:** `GET /venue-bookings?event_id={event}` with no cookies.
- **Test data:** The shared event id.
- **Expected:** `401`; events and bookings are never called.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_listing_an_events_requests_needs_a_session`

## TC-VENUEBOOKINGS-026 — only an Event Coordinator can list an event's requests

- **Pre-conditions:** `GET /users/me` resolves to each other role in turn.
- **Steps:** `GET /venue-bookings?event_id={event}`, once per role.
- **Test data:** `event_organiser`, `venue_staff`, `technical_support`,
  `attendee`.
- **Expected:** `403`, `{"detail": "Permission denied"}` for every one;
  events and bookings are never called.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_only_an_event_coordinator_can_list_an_events_requests`

## TC-VENUEBOOKINGS-027 — the event id is required and must be a UUID

- **Pre-conditions:** Shared.
- **Steps:** `GET /venue-bookings` with no query, then with
  `event_id=not-a-uuid`.
- **Test data:** As above.
- **Expected:** `422` with `event_id` in `errors` both times; no downstream
  service is called.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_event_id_is_required_and_must_be_a_uuid`

## TC-VENUEBOOKINGS-028 — a Coordinator cannot list requests for an event not assigned to them

- **Pre-conditions:** `GET /events/assigned/{event_id}` answers `404`.
- **Steps:** `GET /venue-bookings?event_id={event}`.
- **Test data:** The shared event id.
- **Expected:** `404`, `{"detail": "Event not found"}`. The events call
  carried the request's cookies. Bookings is never called.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_a_coordinator_cannot_list_requests_for_an_event_not_assigned_to_them`

## TC-VENUEBOOKINGS-029 — the event's requests come back with their status

- **Scenario:** AC4. Whatever the bookings service holds for the event is
  returned as-is, `status` included.
- **Pre-conditions:** Shared. `GET /bookings?event_id={event}` returns two
  bookings, both `pending`.
- **Steps:** `GET /venue-bookings?event_id={event}`.
- **Test data:** As above.
- **Expected:** `200` with both bookings, in the order returned. Bookings
  was called once, `GET /bookings` with `params={"event_id": <event>}`.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_the_events_requests_come_back_with_their_status`

## TC-VENUEBOOKINGS-030 — a service that can't be reached is a 502, not an empty list

- **Pre-conditions:** A Coordinator session. Events, then bookings, each
  raise `httpx.ConnectError` once and answer `500` once.
- **Steps:** `GET /venue-bookings?event_id={event}`, once per failure.
- **Test data:** As above.
- **Expected:** `502` with `"Events service unavailable"` or
  `"Bookings service unavailable"` respectively.

- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_listing_an_events_requests_is_a_502_when_a_service_is_down`


## S-28 approved coverage

Latest S-28 execution: 2026-09-27; base commit `0d27acc` plus uncommitted S-28 changes. Environment: Windows/Python 3.14/Node; integration uses freshly recreated `.env.test` Docker stack.

### TC-VENUEBOOKINGS-031 ? Submission rereads venue information

- Scenario: Submission rereads venue information
- Pre-conditions: Mock suitable venue and event.
- Steps: 1. Submit once; change mocked capacity to 1, then facilities/accessibility to empty; submit again.
- Test data: Values specified above; existing shared fixtures supply remaining required fields.
- Expected: Each submission fetches venue; subsequent unsuitable requests return 422 without a new booking.
- Actual: Each submission fetched venue information again; changed capacity/features caused 422 without another write. Full 359-test Python suite passed.
- Status: Pass
- Evidence: `tests/unit/composite/venue_bookings/test_app.py::test_submission_rereads_updated_venue`; local execution, no CI run.

## S-37 confirmed specifications

Confirmed by the developer on 2026-09-28, with no reassignment exception.
S-37 execution: 2026-09-29; base c4934e9 merged with S-37 plus conflict-resolution changes on
S-37/approve-reject-booking-with-reason-or-alternative.
Windows, Python 3.14, Node.js; existing results above describe earlier coverage.
Approval stores `status=confirmed`; rejection stores `status=rejected`.
Decision metadata: `decision_reason`, `decision_alternative`, `decided_by`, `decided_at`.
B means the saved booking fixture; S means the authenticated deciding staff UUID.
No S-33 hold behaviour or S-38 cross-request overlap guarantee is included.

### TC-VENUEBOOKINGS-032 — Only staff may submit decisions through the gateway contract

- **Scenario:** Only staff may submit decisions through the gateway contract (AC1, AC2).
- **Pre-conditions:** Mock users and bookings HTTP dependencies.
- **Steps:** 1. Submit both decisions with every role and missing session.
  2. Inspect forwarded request.
- **Test data:** POST /venue-bookings/B/decision; approved; rejected with reason='Repairs'.
- **Expected:** 401 without valid session; 403 for nonstaff; staff request forwards authenticated credentials to atomic decision route. No event/venue/hold mutation; identity fields cannot be forged.
- **Actual:** Passed in local isolated suites: 529 Python tests and 59 Node tests.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/venue_bookings/test_decision.py`; local execution, no CI run. Node IDs/test names: `test_staff_decision_forwarded_with_credentials; test_nonstaff_cannot_decide; test_missing_session_denied`.

### TC-VENUEBOOKINGS-033 — Decision responses and failures survive orchestration safely

- **Scenario:** Decision responses and failures survive orchestration safely (AC1, AC2).
- **Pre-conditions:** Mock bookings returns success or documented error; mock users verifies staff.
- **Steps:** 1. Submit valid and invalid bodies.
  2. Simulate downstream failures.
- **Test data:** HTTP 200,401,403,404,409,422,500; timeout; unknown decision and extra decided_at.
- **Expected:** Successful saved record returned; expected client errors retain status and safe guidance; upstream failure/timeout produces safe 502 without false success. Invalid body does not mutate storage.
- **Actual:** Passed in local isolated suites: 529 Python tests and 59 Node tests.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/venue_bookings/test_decision.py`; local execution, no CI run. Node IDs/test names: `test_safe_downstream_errors; test_timeout_is_safe; test_invalid_body_never_forwarded`.

### TC-VENUEBOOKINGS-034 — Coordinator visibility remains scoped after reassignment

- **Scenario:** Coordinator visibility remains scoped after reassignment (AC3).
- **Pre-conditions:** Event E reassigned from requester C1 to C2; bookings contain requests by C1 and C2; C3 unrelated. Events service allows C2 only.
- **Steps:** 1. List E requests as C1, C2 and C3.
  2. Repeat with users/events/bookings failures.
- **Test data:** C1=11111111-1111-4111-8111-111111111111; C2=22222222-2222-4222-8222-222222222222; C3=33333333-3333-4333-8333-333333333333.
- **Expected:** Existing TC-VENUEBOOKINGS-028 remains authoritative: C1 and C3 receive 404; C2 retains existing assigned-event access, including saved decisions. Other roles remain forbidden. Upstream failures do not grant fallback access or appear as an empty success. Full event access stays assignment-only.
- **Actual:** Passed in local isolated suites: 529 Python tests and 59 Node tests.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/venue_bookings/test_decision.py`; local execution, no CI run. Node IDs/test names: `test_reassigned_requester_still_denied; test_assigned_coordinator_sees_saved_decision; test_app.py::test_listing_an_events_requests_is_a_502_when_a_service_is_down`.

## S-33 specifications awaiting developer confirmation

Story: S-33 Place Tentative Venue Hold.

### TC-VENUEBOOKINGS-035 — Hold and availability routes preserve role and atomic-service policy

- **Scenario:** Only Venue Staff manage holds and view the venue availability calendar (AC1, AC2).
- **Pre-conditions:** Mock users and bookings services; all supported roles and missing session.
- **Steps:** Place a hold, list availability by venue/date range, and release a hold through the composite routes.
- **Test data:** Booking B; venue V; `2026-11-01` through `2026-11-30`; release reason supplied internally rather than by the browser.
- **Expected:** Missing session returns `401`; nonstaff returns `403`; Venue Staff calls are forwarded with verified session. The browser cannot forge hold/release staff, timestamps or release reason. Safe downstream failures never report success.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** —

### TC-VENUEBOOKINGS-036 — Event state and replacement requests release holds through orchestration

- **Scenario:** Holds are released when their event closes or their requested slot is replaced (AC3, AC4).
- **Pre-conditions:** Event E has one active hold; events and bookings clients are mocked.
- **Steps:** Synchronise E when its authoritative status is `rejected`, `cancelled`, and each nonterminal status; submit a replacement venue request with a changed venue, date or time; repeat the same request unchanged.
- **Test data:** Original Studio B `2026-11-12` `09:00`–`12:00`; replacements change venue to Studio C, date to `2026-11-13`, or time to `13:00`–`16:00`.
- **Expected:** Rejected releases with `event_rejected`; cancelled releases with `event_cancelled`; other event statuses do not release. Each changed replacement releases the old hold with `booking_replaced` before the new Pending request is returned. An identical retry does not release or duplicate anything. Failure cannot leave a falsely available or half-replaced slot.
- **Actual:**
- **Status:** Not Executed
- **Evidence:** —
