# Test cases — event_registrations composite (unit)

Covers `tests/unit/composite/event_registrations/test_app.py`: the composite
with every outbound client (users, events, bookings, venues, registrations)
replaced by a fake. No network, database, or Docker. The clock is injected.

The composite serves the public event pages and the Attendee's register
action. "Now" is Singapore time (UTC+8), because the registration period is
stored without a timezone (developer's answer, 2026-10-25). Opening is
inclusive and closing is exclusive: at exactly the opening time registration is
open; at exactly the closing time it is closed.

| | |
| --- | --- |
| Suite | `pytest tests/unit/composite/event_registrations` |
| Last run | 2026-10-25, branch `S-49/registration-confirmation-notification`, pre-commit working tree |
| Environment | Python 3.14.4, pytest 9.1.1; no network, database, or Docker |
| Result | 23 cases, 41 tests passed in this suite; 1407 passed, 17 skipped across `tests/unit` |

Event E below is `confirmed`, starts `2026-11-20 18:00`, registration on,
opens `2026-11-01T09:00`, closes `2026-11-15T18:00`. Its one confirmed booking
is the venue "Seminar Room 2-1".

## TC-EVENTREGISTRATIONS-001 — health

- **Scenario:** The composite answers its health check.
- **Pre-conditions:** None.
- **Steps:** `GET /health`.
- **Expected:** `200` `{"status": "ok"}`.
- **Actual:** `200` `{"status": "ok"}`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_health_reports_ok; `pytest tests/unit`: 1325 passed, 17 skipped, 2026-10-25

## TC-EVENTREGISTRATIONS-002 — anyone can list confirmed events without signing in

- **Scenario:** People who haven't registered see public details, including the period (S-51 AC4, AC5).
- **Pre-conditions:** No cookie. Events fake returns E and F (F has
  registration off); bookings/venues fakes return "Seminar Room 2-1" for E and
  nothing for F.
- **Steps:** `GET /event-registrations/events`.
- **Expected:** `200`, two items. E's is exactly:
  ```json
  {"id": "E", "name": "Alumni networking evening", "purpose": "Reconnect alumni with current students",
   "start_date": "2026-11-20", "start_time": "18:00:00", "end_date": "2026-11-20", "end_time": "21:00:00",
   "venues": ["Seminar Room 2-1"], "registration_required": true,
   "registration_opens_at": "2026-11-01T09:00:00", "registration_closes_at": "2026-11-15T18:00:00",
   "registration_closed_by_organiser": false, "is_full": false}
  ```
  (Revised for S-50: the last two fields are new; the registrations fake
  holds no places for E.)
  F's has `"registration_required": false`, both dates `null`, `"venues": []`.
  No item has `organiser_id`, `expected_attendance`, or contact fields. The
  users service is never called.
- **Actual:** `200`; E matched exactly, F had registration off, null dates and no venues; no private fields; users never called.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_anyone_can_list_confirmed_events_without_signing_in

## TC-EVENTREGISTRATIONS-003 — one public event, and events that aren't public

- **Scenario:** A single event's public details, and nothing for an event that isn't confirmed (S-51 AC4, AC5).
- **Pre-conditions:** No cookie. Events fake returns E, then `404`.
- **Steps:** `GET /event-registrations/events/E` twice.
- **Expected:** First → `200`, the same body as E's item in
  TC-EVENTREGISTRATIONS-002. Second → `404` "Event not found."
- **Actual:** E → `200` with the same body; an unpublished id → `404` "Event not found."
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_one_public_event_and_events_that_arent_public

## TC-EVENTREGISTRATIONS-004 — registering needs a signed-in Attendee account

- **Scenario:** Only registered Attendees hold a place (S-51 AC5).
- **Pre-conditions:** Clock `2026-11-05 12:00` SGT. Users fake: no session →
  `401`; then a signed-in `event_organiser`; then a signed-in `attendee`.
- **Steps:** `POST /event-registrations/events/E/registration` for each.
- **Expected:** No session → `401` "Sign in to register for this event."
  Organiser → `403` "Only attendee accounts can register for events."
  Attendee → `201` (TC-EVENTREGISTRATIONS-008). The registrations service is
  not called for the first two.
- **Actual:** No session → `401`, organiser → `403`, both with the expected messages and no registrations call; attendee → `201`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_registering_needs_a_signed_in_attendee_account

## TC-EVENTREGISTRATIONS-005 — registering for an event that doesn't need it

- **Scenario:** Registration turned off means there's nothing to register for (S-51 AC1).
- **Pre-conditions:** Signed-in Attendee A; events fake returns F (registration off).
- **Steps:** `POST /event-registrations/events/F/registration`.
- **Expected:** `409` "This event doesn't need registration." Registrations
  service not called.
- **Actual:** `409` "This event doesn't need registration."; registrations not called.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_registering_for_an_event_that_doesnt_need_it

## TC-EVENTREGISTRATIONS-006 — registering before the period opens is blocked

- **Scenario:** Attempts before opening are blocked with a message (S-51 AC3; S-48 AC1, AC2 — the message states the whole window, developer's answer 2026-10-25).
- **Pre-conditions:** Signed-in Attendee A; event E.
- **Steps:** `POST /event-registrations/events/E/registration` at each clock.
- **Test data:** 1. `2026-10-25 10:00` SGT. 2. `2026-11-01 08:59` SGT.
  3. `2026-11-01 09:00` SGT (exactly opening).
- **Expected:** 1 and 2 → `409` "Registration hasn't opened yet. It's open from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm."
  and the registrations service is not called. 3 → `201`.
- **Actual:** 10:00 on 25 Oct and 08:59 on 1 Nov → `409` with the whole-window "hasn't opened yet" message, no registrations call; 09:00 → `201`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_registering_before_the_period_opens_is_blocked; tests/unit/composite/event_registrations/test_app.py::test_registration_opens_at_exactly_the_opening_time

## TC-EVENTREGISTRATIONS-007 — registering after the period closes is blocked

- **Scenario:** Attempts after closing are blocked with a message (S-51 AC3; S-48 AC1, AC2).
- **Pre-conditions:** Signed-in Attendee A; event E.
- **Steps:** `POST /event-registrations/events/E/registration` at each clock.
- **Test data:** 1. `2026-11-15 17:59` SGT. 2. `2026-11-15 18:00` SGT
  (exactly closing). 3. `2026-11-18 09:00` SGT.
- **Expected:** 1 → `201`. 2 and 3 → `409`
  "Registration has closed. It was open from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm." and the registrations service is not called.
- **Actual:** 17:59 → `201`; 18:00 on 15 Nov and 09:00 on 18 Nov → `409` with the whole-window "has closed" message, no registrations call.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_registering_after_the_period_closes_is_blocked; tests/unit/composite/event_registrations/test_app.py::test_registration_is_still_open_a_minute_before_closing

## TC-EVENTREGISTRATIONS-008 — registering inside the period takes a place

- **Scenario:** A registered Attendee holds a place (S-51 AC5). Revised for S-50: the registrations call also carries `"capacity": 2` (E's expected attendance), and the response adds `"waitlisted": false, "joined_at": null`.
- **Pre-conditions:** Signed-in Attendee A (id `33333333-…`); clock
  `2026-11-05 12:00` SGT; registrations fake returns a new row.
- **Steps:** `POST /event-registrations/events/E/registration`.
- **Expected:** `201` `{"event_id": "E", "registered": true, "registered_at":
  "<timestamp>"}`. The registrations service received exactly
  `{"event_id": "E", "attendee_id": "33333333-…"}` — the attendee id from the
  session, never from the request.
- **Actual:** `201` with the expected body; registrations received exactly the event id and the session's attendee id, ignoring an `attendee_id` in the request body.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_registering_inside_the_period_takes_a_place

## TC-EVENTREGISTRATIONS-009 — registering twice

- **Scenario:** One account holds one place (S-51 AC5; developer's answer, 2026-10-25).
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-008; registrations fake returns
  `409` "You're already registered for this event."
- **Steps:** `POST /event-registrations/events/E/registration`.
- **Expected:** `409` "You're already registered for this event."
- **Actual:** `409` "You're already registered for this event."
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_registering_twice

## TC-EVENTREGISTRATIONS-010 — "now" is Singapore time whatever the server's clock

- **Scenario:** The period is read in Singapore time (developer's answer, 2026-10-25).
- **Pre-conditions:** Signed-in Attendee A; event E. The injected clock is UTC.
- **Steps:** `POST /event-registrations/events/E/registration` at each UTC instant.
- **Test data:** 1. `2026-11-01T00:59:00Z` (08:59 SGT). 2. `2026-11-01T01:00:00Z` (09:00 SGT).
- **Expected:** 1 → `409` "Registration hasn't opened yet. It's open from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm."
  2 → `201`.
- **Actual:** 00:59Z → `409` with the whole-window "hasn't opened yet" message; 01:00Z → `201`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_now_is_singapore_time_whatever_the_servers_clock

## TC-EVENTREGISTRATIONS-011 — an Attendee sees whether they hold a place

- **Scenario:** The event page can show "You're registered" (S-51 AC5). Revised for S-50: both answers also carry `waitlisted` and `joined_at` (false / null here; see TC-EVENTREGISTRATIONS-025).
- **Pre-conditions:** Signed-in Attendee A. Registrations fake returns A's
  row, then `404`.
- **Steps:** `GET /event-registrations/events/E/registration` twice.
- **Expected:** `200` `{"event_id": "E", "registered": true, "registered_at":
  "<timestamp>"}`, then `200` `{"event_id": "E", "registered": false,
  "registered_at": null}`.
- **Actual:** Registered → `200` with `registered: true`; `404` from registrations → `200` with `registered: false, registered_at: null`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_an_attendee_sees_whether_they_hold_a_place

## TC-EVENTREGISTRATIONS-012 — a service it depends on is down

- **Scenario:** A downstream failure is reported as one, not as a validation error.
- **Pre-conditions:** Signed-in Attendee A; the events fake raises
  `httpx.ConnectError`, then the registrations fake does.
- **Steps:** `POST /event-registrations/events/E/registration` for each.
- **Expected:** `502` "Events service unavailable", then `502`
  "Registrations service unavailable" — the same shape the other composites use.
- **Actual:** `502` "Events service unavailable", then `502` "Registrations service unavailable".
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_a_service_it_depends_on_is_down

## S-48 — Register for Event

Acceptance criteria and the developer's answers, 2026-10-25: a successful
registration is visible to the Attendee, as a list on their dashboard, and to
the event's own Organiser only, as the event's attendee list with each
attendee's name, email and registration time plus a count. The period checks
and their messages are TC-EVENTREGISTRATIONS-006, -007 and -010.

Organiser O (id `77777777-7777-4777-8777-777777777777`) owns E. Attendees A
("Ada Tan", `ada@example.com`, registered `2026-11-05T04:00:00Z`) and B
("Ben Lim", `ben@example.com`, registered `2026-11-06T04:00:00Z`).

## TC-EVENTREGISTRATIONS-013 — the Organiser sees who registered for their event

- **Scenario:** A registration is recorded against the event and its Organiser sees it (S-48 AC3). Revised for S-50: the body also carries `"waiting_list": []`, and the waiting list is read alongside the places.
- **Pre-conditions:** O's session cookie. Events fake answers
  `GET /events/E` (with O's cookie forwarded) `200`. Registrations fake
  returns A's and B's rows for E. Users fake answers
  `POST /internal/users/profiles` with A and B.
- **Steps:** `GET /event-registrations/events/E/attendees`.
- **Test data:** As above.
- **Expected:** `200` exactly:
  ```json
  {"event_id": "E", "count": 2, "attendees": [
    {"attendee_id": "A", "name": "Ada Tan", "email": "ada@example.com", "registered_at": "2026-11-05T04:00:00Z"},
    {"attendee_id": "B", "name": "Ben Lim", "email": "ben@example.com", "registered_at": "2026-11-06T04:00:00Z"}]}
  ```
  Earliest registration first. The users service received `{"ids": [A, B]}`.
- **Actual:** `200` with the exact body, A before B; O's cookie forwarded to `GET /events/E`; users received `{"ids": [A, B]}`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_the_organiser_sees_who_registered_for_their_event

## TC-EVENTREGISTRATIONS-014 — an event no one has registered for yet

- **Scenario:** The Organiser's list is empty rather than an error. Revised for S-50: the body also carries `"waiting_list": []`.
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-013, but the registrations fake returns `[]`.
- **Steps:** `GET /event-registrations/events/E/attendees`.
- **Test data:** As above.
- **Expected:** `200` `{"event_id": "E", "count": 0, "attendees": []}`. The
  users profile lookup is not called.
- **Actual:** `200` `{"event_id": "E", "count": 0, "attendees": []}`; users never called.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_an_event_no_one_has_registered_for_yet

## TC-EVENTREGISTRATIONS-015 — only the event's own Organiser sees its attendees

- **Scenario:** Attendee names and emails reach no one else (developer's answer, 2026-10-25). Revised for S-57: the assigned Coordinator is let through (TC-EVENTREGISTRATIONS-062); the events fake answers `GET /events/assigned/E` with `403` here, so the `403` case still holds.
- **Pre-conditions:** The events fake's `GET /events/E` answers, in turn:
  `401`, `403` `{"detail": "Insufficient permissions"}` (an Attendee or
  Coordinator), `404` `{"detail": "Event not found"}` (another Organiser).
- **Steps:** `GET /event-registrations/events/E/attendees` once per answer.
- **Test data:** As above.
- **Expected:** `401` "Sign in to see who has registered.", then `403`
  "Insufficient permissions", then `404` "Event not found". The registrations
  and users services are never called.
- **Actual:** `401` "Sign in to see who has registered.", `403` "Insufficient permissions", `404` "Event not found"; registrations and users never called.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_only_the_events_own_organiser_sees_its_attendees

## TC-EVENTREGISTRATIONS-016 — an Attendee sees the events they registered for

- **Scenario:** A registration is recorded against the Attendee and they see it (S-48 AC3). Revised for S-52: each row also carries `"status": "confirmed"`, `"joined_at": null` and `"position": null` (see TC-EVENTREGISTRATIONS-029).
- **Pre-conditions:** Signed-in Attendee A. Registrations fake answers
  `GET /registrations/attendees/A` with A's rows for E (registered
  `2026-11-05T04:00:00Z`) and for event G (registered `2026-11-02T04:00:00Z`),
  where G is confirmed and starts `2026-11-10 10:00`. Events fake returns E's
  and G's published details.
- **Steps:** `GET /event-registrations/me/registrations`.
- **Test data:** As above.
- **Expected:** `200`, G first then E (soonest event first), each exactly
  `{"event_id", "name", "start_date", "start_time", "end_date", "end_time",
  "registered_at"}`, e.g. E's:
  ```json
  {"event_id": "E", "name": "Alumni networking evening", "start_date": "2026-11-20", "start_time": "18:00:00",
   "end_date": "2026-11-20", "end_time": "21:00:00", "registered_at": "2026-11-05T04:00:00Z"}
  ```
  The attendee id comes from the session only.
- **Actual:** `200`, G then E; E matched exactly; registrations read for the session's Attendee A.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_an_attendee_sees_the_events_they_registered_for

## TC-EVENTREGISTRATIONS-017 — an Attendee with no public registrations

- **Scenario:** The Attendee's list is empty rather than an error, and lists only public events.
- **Pre-conditions:** Signed-in Attendee A. 1: registrations fake returns
  `[]`. 2: it returns A's row for E, and the events fake answers
  `GET /internal/events/published/E` `404` (E is no longer confirmed).
- **Steps:** `GET /event-registrations/me/registrations` for each.
- **Test data:** As above.
- **Expected:** Both → `200` `[]`. In 1 the events service is not called.
- **Actual:** Both `200` `[]`; with no rows the events service was not called.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_an_attendee_with_no_public_registrations

## TC-EVENTREGISTRATIONS-018 — the Attendee's list needs a signed-in Attendee

- **Scenario:** Nobody else reads an Attendee's registrations.
- **Pre-conditions:** Users fake answers `GET /users/me` with `401`, then an
  `event_organiser` user.
- **Steps:** `GET /event-registrations/me/registrations` for each.
- **Test data:** As above.
- **Expected:** `401` "Sign in to register for this event.", then `403`
  "Only attendee accounts can register for events." The registrations service
  is never called.
- **Actual:** `401` "Sign in to register for this event.", then `403` "Only attendee accounts can register for events."; registrations never called.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_the_attendees_list_needs_a_signed_in_attendee

## S-50 — Cap Registration at Capacity

The cap is the event's `expected_attendance` -- the figure the S-35 venue
check compares against a venue's capacity (developer's answer, 2026-10-26).
The figure itself is never shown publicly; the public page gets only
`is_full`. Clock `2026-11-05 12:00` SGT (inside E's period) unless stated.
E has `expected_attendance` 2 and `registration_closed_at` null unless stated.
Attendee A is signed in unless stated.

Where several things block registration, the message shown is the first that
applies: registration off → period not yet open or already over → closed by
the Organiser → full.

## TC-EVENTREGISTRATIONS-019 — the public event says when it is full or closed

- **Scenario:** Anyone viewing the event can see it is full or closed, without seeing the attendance figure (S-50 AC1, AC4).
- **Pre-conditions:** No cookie. Registrations fake returns 2 places for E;
  for event G (`expected_attendance` 50, `registration_closed_at`
  `2026-11-03T06:15:00+00:00`) it returns 1 place.
- **Steps:** `GET /event-registrations/events/E`; `GET /event-registrations/events/G`; `GET /event-registrations/events`.
- **Expected:** E → `200` with `"is_full": true, "registration_closed_by_organiser": false`.
  G → `"is_full": false, "registration_closed_by_organiser": true`. The list
  carries the same two values per event. No body contains `expected_attendance`
  or `registration_closed_at`.
- **Actual:** E full/not closed, G not full/closed, the list agreed; no body had `expected_attendance` or `registration_closed_at`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s50.py::test_the_public_event_says_when_it_is_full_or_closed; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTREGISTRATIONS-020 — registering is capped at the event's expected attendance

- **Scenario:** The cap passed to the registrations service is exactly the S-35 figure (S-50 AC1, AC3).
- **Pre-conditions:** E has `expected_attendance` 2; registrations fake answers `201`.
- **Steps:** `POST /event-registrations/events/E/registration`.
- **Expected:** `201` `{"event_id": E, "registered": true, ...}`. The
  registrations fake received `{"event_id": E, "attendee_id": A, "capacity": 2}`.
- **Actual:** `201`; registrations received `capacity` 2.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s50.py::test_registering_is_capped_at_the_events_expected_attendance; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTREGISTRATIONS-021 — a full event offers the waiting list instead

- **Scenario:** An Attendee registering once capacity is reached is blocked and offered the waiting list (S-50 AC1, AC2).
- **Pre-conditions:** Registrations fake answers `409` "This event is full.".
- **Steps:** `POST /event-registrations/events/E/registration`.
- **Expected:** `409` `{"detail": "This event is full. You can join the waiting list."}`.
- **Actual:** `409` "This event is full. You can join the waiting list."
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s50.py::test_a_full_event_offers_the_waiting_list_instead; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTREGISTRATIONS-022 — registration closed by the Organiser is refused

- **Scenario:** Once the Organiser closes registration, nobody registers, with or without places left (S-50 AC4).
- **Pre-conditions:** E has `registration_closed_at` `2026-11-03T06:15:00+00:00`, 0 places taken.
- **Steps:** `POST /event-registrations/events/E/registration`.
- **Expected:** `409` `{"detail": "The organiser has closed registration for this event."}`.
  The registrations service is never called.
- **Actual:** `409` "The organiser has closed registration for this event."; registrations not called.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s50.py::test_registration_closed_by_the_organiser_is_refused; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTREGISTRATIONS-023 — joining the waiting list of a full event

- **Scenario:** The offered waiting list can be joined (S-50 AC2).
- **Pre-conditions:** Registrations fake: 2 places for E (full), A not
  registered, waiting-list insert answers `201` with `created_at` `2026-11-05T04:00:00+00:00`.
- **Steps:** `POST /event-registrations/events/E/waiting-list`.
- **Expected:** `201` `{"event_id": E, "waitlisted": true, "joined_at": "2026-11-05T04:00:00Z"}`
  (any equivalent ISO form). The fake received `{"event_id": E, "attendee_id": A}` -- the
  attendee is the session's, never the body's.
- **Actual:** `201` `{waitlisted: true, joined_at}`; the insert carried the session's attendee, not the body's.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s50.py::test_joining_the_waiting_list_of_a_full_event; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTREGISTRATIONS-024 — when the waiting list is refused

- **Scenario:** The waiting list is only offered when the event is full and otherwise open (S-50 AC2, AC4).
- **Steps:** `POST /event-registrations/events/E/waiting-list`, once per row.
- **Test data / Expected:**
  | Situation | Expected |
  | --- | --- |
  | No session | `401` "Sign in to register for this event." |
  | Signed in as an Event Organiser | `403` "Only attendee accounts can register for events." |
  | E has 1 place taken (not full) | `409` "This event still has places. Register instead." |
  | Clock `2026-11-16 12:00` SGT (period over), E full | `409` "Registration has closed. It was open from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm." |
  | E full and closed by the Organiser | `409` "The organiser has closed registration for this event." |
  | E full, A already holds a place | `409` "You're already registered for this event." |
  | E full, waiting-list insert answers `409` | `409` "You're already on the waiting list for this event." |
  | E has registration off | `409` "This event doesn't need registration." |

  The waiting-list insert is never called in rows 1--6 and 8.
- **Actual:** All eight rows returned the stated status and message; the insert was only reached for the already-waiting row.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s50.py::test_when_the_waiting_list_is_refused; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTREGISTRATIONS-025 — the Attendee's status shows the waiting list

- **Scenario:** An Attendee who joined can see they're on the waiting list (S-50 AC2).
- **Pre-conditions:** Registrations fake: A holds no place for E; A's waiting-list entry exists, `created_at` `2026-11-05T04:00:00+00:00`. Then neither exists.
- **Steps:** `GET /event-registrations/events/E/registration` twice.
- **Expected:** First → `200` `{"event_id": E, "registered": false, "registered_at": null, "waitlisted": true, "joined_at": "2026-11-05T04:00:00Z"}`.
  Second → `"registered": false, "waitlisted": false, "joined_at": null`. A
  registered Attendee gets `"waitlisted": false` without a waiting-list lookup.
- **Actual:** Waitlisted → `waitlisted: true` with `joined_at`; not waiting → false/null; registered → no waiting-list lookup.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s50.py::test_the_attendees_status_shows_the_waiting_list; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-EVENTREGISTRATIONS-026 — the Organiser sees the waiting list in join order

- **Scenario:** The Organiser sees who is waiting for a full event (S-50 AC2, per developer's answer).
- **Pre-conditions:** Signed in as the owning Organiser. Registrations fake:
  places for A1, A2; waiting list B (joined `04:00`) then C (joined `05:00`).
  Users fake returns names and emails for all four.
- **Steps:** `GET /event-registrations/events/E/attendees`.
- **Expected:** `200`; `count` 2 and `attendees` as before (S-48), plus
  `"waiting_list": [{"attendee_id": B, "name": ..., "email": ..., "joined_at": ...}, {... C ...}]`
  in that order. With no one waiting, `"waiting_list": []`. Another Organiser → `404` as before.
- **Actual:** `count` 2; `waiting_list` C then D with names, emails, `joined_at`; empty → `[]`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s50.py::test_the_organiser_sees_the_waiting_list_in_join_order; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## S-52 — Join Waiting List

Developer's answers, 2026-10-26: S-50 already lets an Attendee join a full
event's waiting list. S-52 adds the Attendee's **place in line** (1 = next)
to the event page, and lists waitlisted events on the Attendee dashboard
alongside confirmed ones, each row marked "Confirmed" or "Waiting list". A
place is the Attendee's 1-based index in the event's waiting list as the
registrations service orders it (TC-REGISTRATIONS-015). Waitlisted Attendees
are not promoted automatically: no cancellation exists yet.

Event E's waiting list below is B (joined `2026-11-05T04:00:00Z`), then A
(`2026-11-05T05:00:00Z`), then C (`2026-11-05T06:00:00Z`) unless stated.

## TC-EVENTREGISTRATIONS-027 — the Attendee's status gives their place in line

- **Scenario:** A waitlisted Attendee sees where they stand, not a confirmation (S-52 AC2, AC3).
- **Pre-conditions:** Signed-in Attendee A. Registrations fake: A holds no place for E; A's waiting-list entry exists; `GET /registrations/waiting-list/events/E` returns B, A, C. Then: A on no waiting list. Then: A holds a place.
- **Steps:** `GET /event-registrations/events/E/registration` for each.
- **Test data:** As above.
- **Expected:** 1 → `200` `{"event_id": E, "registered": false, "registered_at": null, "waitlisted": true, "joined_at": "2026-11-05T05:00:00Z", "position": 2}`. 2 → `"waitlisted": false, "joined_at": null, "position": null`. 3 → `"registered": true, "position": null`, with no waiting-list lookup.
- **Actual:** Waitlisted → `position: 2` with `joined_at`; not waiting → `waitlisted: false`, `position: null`; registered → `position: null` and no waiting-list read.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s52.py::test_the_attendees_status_gives_their_place_in_line; 2026-10-26, branch `S-52/join-waiting-list` (on S-50 `a3011b3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-028 — joining the waiting list answers with the place in line

- **Scenario:** Straight after joining, the Attendee is told their place (S-52 AC1, AC2).
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-023 (E full, A not registered, insert answers `201` with `created_at` `2026-11-05T05:00:00+00:00`); afterwards the event's waiting list reads B, A.
- **Steps:** `POST /event-registrations/events/E/waiting-list`.
- **Test data:** As above.
- **Expected:** `201` `{"event_id": E, "waitlisted": true, "joined_at": "2026-11-05T05:00:00Z", "position": 2}`.
- **Actual:** `201` `{waitlisted: true, joined_at: 2026-11-05T05:00:00Z, position: 2}`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s52.py::test_joining_the_waiting_list_answers_with_the_place_in_line; 2026-10-26, branch `S-52/join-waiting-list` (on S-50 `a3011b3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-029 — the Attendee's dashboard list includes the waiting list

- **Scenario:** The dashboard list shows confirmed places and waiting-list entries, and tells them apart (S-52 AC3). Revises the row shape of TC-EVENTREGISTRATIONS-016.
- **Pre-conditions:** Signed-in Attendee A. Registrations fake: A holds a place at G (registered `2026-11-02T04:00:00Z`; G confirmed, starts `2026-11-10 10:00`); `GET /registrations/waiting-list/attendees/A` returns A's entry for E, plus one for event H, which the events fake answers `404` (no longer public). E's waiting list reads B, A, C.
- **Steps:** `GET /event-registrations/me/registrations`.
- **Test data:** As above.
- **Expected:** `200`, exactly two rows, G then E (soonest first), each `{"event_id", "name", "start_date", "start_time", "end_date", "end_time", "status", "registered_at", "joined_at", "position"}`:
  - G → `"status": "confirmed", "registered_at": "2026-11-02T04:00:00Z", "joined_at": null, "position": null`
  - E → `"status": "waitlisted", "registered_at": null, "joined_at": "2026-11-05T05:00:00Z", "position": 2`

  H is left out. An Attendee with neither places nor entries still gets `200` `[]` (TC-EVENTREGISTRATIONS-017).
- **Actual:** `200`, G (`confirmed`) then E (`waitlisted`, `position: 2`), exact shapes matched; H left out.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s52.py::test_the_attendees_dashboard_list_includes_the_waiting_list; 2026-10-26, branch `S-52/join-waiting-list` (on S-50 `a3011b3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-030 — the waiting list can't be read

- **Scenario:** A failure reading the waiting list is reported, not shown as "not waiting".
- **Pre-conditions:** Signed-in Attendee A, on E's waiting list. The registrations fake answers `GET /registrations/waiting-list/events/E` with `500`; then `GET /registrations/waiting-list/attendees/A` with `500`.
- **Steps:** `GET /event-registrations/events/E/registration`; then `GET /event-registrations/me/registrations`.
- **Test data:** As above.
- **Expected:** Both → `502` "Registrations service unavailable".
- **Actual:** Both `502` "Registrations service unavailable".
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s52.py::test_the_waiting_list_cant_be_read; 2026-10-26, branch `S-52/join-waiting-list` (on S-50 `a3011b3`), pre-commit working tree

## S-49 — Registration Confirmation Notification

Developer decisions (2026-10-25): the confirmation is an in-app notification
only (no email), stored by the `notifications` service with kind
`registration_confirmation` and shown on the Attendee dashboard. "Entry
details" are the Attendee's name and email. A confirmed-venue list that is
empty reads "venue to be confirmed"; several are joined with ", ". If the
place is recorded but the confirmation cannot be built or stored, the
registration still answers `201`; the failure is only logged.

For these cases Attendee A is `33333333-3333-4333-8333-333333333333`, name
"Ada Tan", email `ada@example.com`; the registrations fake answers `201` with
id `88888888-8888-4888-8888-888888888888`; the clock is
`2026-11-05 12:00` SGT (inside E's period).

## TC-EVENTREGISTRATIONS-031 — a successful registration sends the Attendee one confirmation

- **Scenario:** Once the place is recorded, a confirmation naming the event,
  date, time, venue and the Attendee's name and email is sent to that
  Attendee (S-49 AC1, AC2).
- **Pre-conditions:** Users fake returns A as `attendee`; events fake returns
  E (20 Nov 2026, 18:00–21:00); bookings fake returns one `confirmed` booking
  at venue "Seminar Room 2-1"; registrations fake answers `201`;
  notifications fake answers `201`.
- **Steps:** `POST /event-registrations/events/E/registration`.
- **Test data:** As above.
- **Expected:** `201` as before. The notifications fake received exactly one
  `POST /internal/notifications` with one row:
  `recipient_id` A, `event_id` E, `event_name` "Alumni networking evening",
  `kind` `registration_confirmation`, `deduplication_key`
  `registration_confirmation:88888888-8888-4888-8888-888888888888`,
  `message`
  "Registration confirmed: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, at Seminar Room 2-1. Name: Ada Tan. Email: ada@example.com."
  The registrations call happened before the notifications call.
- **Actual:** `201`; exactly one row sent to `/internal/notifications` with recipient A, event E, kind `registration_confirmation`, key `registration_confirmation:8888…8888` and the expected message; registrations called before notifications.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_a_successful_registration_sends_the_attendee_one_confirmation

## TC-EVENTREGISTRATIONS-032 — an event spanning days shows both dates

- **Scenario:** The confirmation's date/time covers an event that ends on a
  later day, and 12-hour times read correctly at noon and midnight (S-49 AC2).
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-031, but E runs
  `2026-11-20 12:00` to `2026-11-21 00:30`.
- **Steps:** `POST /event-registrations/events/E/registration`.
- **Test data:** As above.
- **Expected:** `201`; the message is
  "Registration confirmed: Alumni networking evening, 20 Nov 2026, 12:00 pm – 21 Nov 2026, 12:30 am, at Seminar Room 2-1. Name: Ada Tan. Email: ada@example.com."
- **Actual:** `201`; message read "… 20 Nov 2026, 12:00 pm – 21 Nov 2026, 12:30 am, at Seminar Room 2-1. …" as expected.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_an_event_spanning_days_shows_both_dates

## TC-EVENTREGISTRATIONS-033 — no confirmed venue, or several

- **Scenario:** The venue part still reads correctly when no venue is
  confirmed yet, or more than one is (S-49 AC2).
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-031, run twice:
  1. bookings fake returns only a `pending` booking;
  2. bookings fake returns two `confirmed` bookings, venues "Seminar Room 2-1"
     and "Hall A".
- **Steps:** `POST /event-registrations/events/E/registration` in each setup.
- **Test data:** As above.
- **Expected:** Both `201`. Messages:
  1. "Registration confirmed: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, venue to be confirmed. Name: Ada Tan. Email: ada@example.com."
  2. "Registration confirmed: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, at Seminar Room 2-1, Hall A. Name: Ada Tan. Email: ada@example.com."
- **Actual:** Both `201`; messages read "…, venue to be confirmed. …" and "…, at Seminar Room 2-1, Hall A. …" as expected.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_no_confirmed_venue_reads_to_be_confirmed; tests/unit/composite/event_registrations/test_app.py::test_several_confirmed_venues_are_joined

## TC-EVENTREGISTRATIONS-034 — no confirmation when the registration did not succeed

- **Scenario:** Every way a registration can fail sends nothing (S-49 AC3).
- **Pre-conditions:** Notifications fake records calls. One run per row:

  | Setup | Expected status |
  | --- | --- |
  | Users fake `401` | `401` |
  | Users fake returns an `event_organiser` | `403` |
  | Events fake `404` | `404` |
  | E with registration off | `409` "This event doesn't need registration." |
  | Clock `2026-10-31 12:00` SGT | `409` "Registration hasn't opened yet. …" |
  | Clock `2026-11-15 18:00` SGT | `409` "Registration has closed. …" |
  | Registrations fake `409` "You're already registered for this event." | `409`, same detail |
  | Registrations fake `500` | `502` "Registrations service unavailable" |

- **Steps:** `POST /event-registrations/events/E/registration` in each setup.
- **Test data:** As above.
- **Expected:** Each answers the status in its row, and the notifications
  fake was never called.
- **Actual:** All eight setups answered their status and detail; notifications never called.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_no_confirmation_when_the_registration_did_not_succeed (8 parametrised)

## TC-EVENTREGISTRATIONS-035 — a failed confirmation does not undo the registration

- **Scenario:** The place is secured even if the confirmation cannot be built
  or stored (developer decision).
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-031, one run per row:
  1. notifications fake answers `500`;
  2. notifications fake raises `httpx.ConnectError`;
  3. bookings fake answers `500` (venue names can't be read).
- **Steps:** `POST /event-registrations/events/E/registration` in each setup.
- **Test data:** As above.
- **Expected:** Each answers `201`
  `{"event_id": E, "registered": true, "registered_at": "2026-11-05T04:00:00Z"}`.
  In run 3 the notifications fake was never called.
- **Actual:** All three `201` with the registration body; notifications not called in run 3.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_a_confirmation_that_isnt_stored_keeps_the_registration; tests/unit/composite/event_registrations/test_app.py::test_an_unreachable_notifications_service_keeps_the_registration; tests/unit/composite/event_registrations/test_app.py::test_unreadable_venues_keep_the_registration_and_send_nothing

## S-53 — Withdraw Registration

Developer decisions (2026-10-26): a registered Attendee can withdraw until
the event starts (`start_date` + `start_time`, Singapore time), even after the
registration period has closed or the Organiser has closed registration. At
the start time itself, withdrawing is refused. Withdrawing removes the place, so
the Attendee is back to not registered. The registrations service then gives
the freed place to the first Attendee on the waiting list in the same step
(capacity = the event's `expected_attendance`), whether or not registration is
still open. The promoted Attendee gets one in-app notification of kind
`waiting_list_promotion`, worded like the S-49 confirmation. The withdrawing
Attendee gets none. As with S-49, a notification that can't be built or stored
is logged and the withdrawal still answers `200`.

Route: `DELETE /event-registrations/events/{id}/registration`. Clock
`2026-11-05 12:00` SGT unless stated; E starts `2026-11-20 18:00`. Attendee A
(Ada Lovelace, `ada@example.com`) is signed in unless stated. The
registrations fake answers `POST /registrations/withdrawals` with `200`
`{"withdrawn": <A's row>, "promoted": null}` unless stated. (S-55 renames
`promoted` to `offered`; see the S-55 section.) Attendee B is
`44444444-4444-4444-8444-444444444444`, "Ben Lee", `ben@example.com`; B's
promoted row id is `99999999-9999-4999-8999-999999999999`.

## TC-EVENTREGISTRATIONS-036 — a registered Attendee withdraws

- **Scenario:** Withdrawing before the event removes A's place and A is no longer registered (S-53 AC1, AC2).
- **Pre-conditions:** As above; no one is promoted.
- **Steps:** `DELETE /event-registrations/events/E/registration`.
- **Test data:** As above.
- **Expected:** `200` `{"event_id": E, "registered": false, "registered_at": null, "waitlisted": false, "joined_at": null, "position": null}` (S-55 adds `"offered": false`). The registrations service gets exactly one `POST /registrations/withdrawals` with `{"event_id": E, "attendee_id": A, "capacity": 2}`: A is taken from the session, and capacity is E's `expected_attendance`. No notification is sent.
- **Actual:** `200` with the not-registered body including `offered` false; one `POST /registrations/withdrawals` `{E, A, capacity 2}`; no notification.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s53.py::test_a_registered_attendee_withdraws; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-037 — withdrawing is open until the event starts

- **Scenario:** The cutoff is the event's start in Singapore time, not the registration period (S-53 AC1).
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-036, with the clock and E as in each row.
- **Steps:** `DELETE /event-registrations/events/E/registration`.
- **Test data / Expected:**
  | Clock (SGT) | E | Result |
  | --- | --- | --- |
  | `2026-11-16 12:00` (after registration closed) | as above | `200`; registrations called |
  | `2026-11-05 12:00` | `registration_closed_at` `2026-11-04T02:00:00+00:00` (Organiser closed) | `200`; registrations called |
  | `2026-11-20 17:59` | as above | `200`; registrations called |
  | `2026-11-20 18:00` | as above | `409` "This event has already started. You can no longer withdraw."; registrations not called |
  | `2026-11-21 09:00` | as above | `409`, same detail; registrations not called |
  | `2026-11-20 17:59` given as the UTC instant `2026-11-20T09:59Z` | as above | `200` (the comparison is in SGT whatever the server's clock zone) |
- **Actual:** After the period, after an Organiser close, and at 17:59 → `200` with registrations called; 18:00 and the next morning → `409` with the started message, registrations not called; the UTC instant `09:59Z` → `200`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s53.py::test_withdrawing_is_open_until_the_event_starts, ::test_withdrawing_is_refused_once_the_event_starts, ::test_the_cutoff_is_read_in_singapore_time; 2026-10-26, branch `S-53/withdraw-registration` (on S-52 + S-49 `fde7b1f`), pre-commit working tree

## TC-EVENTREGISTRATIONS-038 — who may withdraw, and from what

- **Scenario:** Only a signed-in Attendee who holds a place at a public event can withdraw (S-53 AC1).
- **Pre-conditions:** As in each row.
- **Steps:** `DELETE /event-registrations/events/{id}/registration`.
- **Test data / Expected:**
  | Situation | Result |
  | --- | --- |
  | Users `/users/me` answers `401` | `401` "Sign in to withdraw your registration."; registrations not called |
  | Signed in as an `event_organiser` | `403` "Only attendee accounts can register for events."; registrations not called |
  | Event id not public (events answers `404` "Event not found.") | `404` "Event not found."; registrations not called |
  | Registrations answers `404` "You're not registered for this event." | `404` "You're not registered for this event." |
  | A is only on E's waiting list (registrations answers `404`) | `404` "You're not registered for this event."; A stays on the waiting list |
- **Actual:** `401` "Sign in to withdraw your registration."; `403` "Only attendee accounts can register for events."; unknown event `404` "Event not found."; no place `404` "You're not registered for this event." with the waiting list untouched; registrations not called in the first three.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s53.py::test_withdrawing_needs_a_signed_in_attendee, ::test_withdrawing_from_an_event_that_isnt_public, ::test_withdrawing_without_a_place; 2026-10-26, branch `S-53/withdraw-registration` (on S-52 + S-49 `fde7b1f`), pre-commit working tree

## TC-EVENTREGISTRATIONS-039 — the promoted Attendee is notified

> **Retired by S-55 (2026-10-30).** A freed place is now offered, not given. See TC-EVENTREGISTRATIONS-054. The record below is S-53's last run.

- **Scenario:** When the freed place goes to the next Attendee in line, they get one notification with the event and entry details (S-53 AC3, AC4).
- **Pre-conditions:** Registrations answers `200` with `promoted` = B's row for E (id `9999…9999`). Users `POST /internal/users/profiles` `{"ids": [B]}` answers B's profile.
- **Steps:** `DELETE /event-registrations/events/E/registration`.
- **Test data:** As above. E's one confirmed venue is "Seminar Room 2-1".
- **Expected:** `200`, the same body as TC-EVENTREGISTRATIONS-036. Exactly one `POST /internal/notifications` with one row: `recipient_id` B, `event_id` E, `event_name` "Alumni networking evening", `kind` `waiting_list_promotion`, `deduplication_key` `waiting_list_promotion:99999999-9999-4999-8999-999999999999`, `message` "A place opened up: you're now registered for Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, at Seminar Room 2-1. Name: Ben Lee. Email: ben@example.com.". No row is addressed to A. With no confirmed venue, the message reads "…9:00 pm, venue to be confirmed. Name: …". It also works when promotion happens after registration has closed (clock `2026-11-16 12:00`).
- **Actual:** `200`; one profile lookup for B; exactly one row to B with kind `waiting_list_promotion`, the expected message and key; none to A; no-venue wording "venue to be confirmed"; also sent after registration closed.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s53.py::test_the_promoted_attendee_is_notified, ::test_a_promotion_without_a_confirmed_venue, ::test_a_promotion_after_registration_has_closed; 2026-10-26, branch `S-53/withdraw-registration` (on S-52 + S-49 `fde7b1f`), pre-commit working tree

## TC-EVENTREGISTRATIONS-040 — a failed notification doesn't undo the withdrawal

> **Retired by S-55 (2026-10-30).** See TC-EVENTREGISTRATIONS-055. The record below is S-53's last run.

- **Scenario:** The place has already moved, so a notification that can't be built or stored is logged and the withdrawal still succeeds.
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-039, except as in each row.
- **Steps:** `DELETE /event-registrations/events/E/registration`.
- **Test data / Expected:**
  | Failure | Result |
  | --- | --- |
  | Notifications answers `500` | `200`, same body as TC-EVENTREGISTRATIONS-036 |
  | Notifications unreachable (`ConnectError`) | `200`, same body |
  | Users profiles answers `500` | `200`, same body; no notification sent |
  | Bookings answers `500` (venues unreadable) | `200`, same body; no notification sent |
- **Actual:** All four failures → `200` with the same body; notifications attempted for the first two, not sent for the last two.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s53.py::test_a_failed_notification_keeps_the_withdrawal; 2026-10-26, branch `S-53/withdraw-registration` (on S-52 + S-49 `fde7b1f`), pre-commit working tree

## TC-EVENTREGISTRATIONS-041 — the registrations service fails

- **Scenario:** A withdrawal that may not have been recorded is not reported as done.
- **Pre-conditions:** Registrations answers `500`, or is unreachable.
- **Steps:** `DELETE /event-registrations/events/E/registration` for each.
- **Test data:** As above.
- **Expected:** Both → `502` "Registrations service unavailable"; no notification sent.
- **Actual:** Both → `502` "Registrations service unavailable"; no notification.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s53.py::test_the_registrations_service_fails; 2026-10-26, branch `S-53/withdraw-registration` (on S-52 + S-49 `fde7b1f`), pre-commit working tree

## S-56 — View Confirmed Event Details

Developer decisions (2026-10-27): the details show on each card in "Your
registrations" on the Attendee's dashboard (`GET /me/registrations`), not on a
new page. Only an Attendee holding a place sees the venue. A waiting-list
entry stays as S-52 left it: name, date and time, and its place in line, with
no venue. The details are shown while the event is `confirmed`. If a
significant change sends it back for re-checking
(`planning`, `pending_safety_check`, `safety_changes_requested`), the place
stays listed with `details_confirmed: false` and no date, time or venue,
until it is confirmed again. A cancelled event is not listed, as before.

The primary venue, until S-91 records one: the confirmed booking made first
(earliest `submitted_at`). A booking that has been replaced (S-78) passes its
place to the booking that replaced it. While a replacement is still being
arranged, the original booking is still `confirmed`, so it is the one shown,
with no warning. The public page keeps listing every confirmed venue.

TC-EVENTREGISTRATIONS-016 and -029's expected rows gain `details_confirmed`
and `venue`. Their tests were updated to match and still pass. TC-EVENTREGISTRATIONS-043
was dropped before it was run (`preparation` is out of scope); the ID stays unused.

Route: `GET /event-registrations/me/registrations`. Attendee A is signed in
and holds a place at event E unless stated. The events fake answers
`/internal/events/attendee-view/E` with E as `confirmed`. The bookings fake
answers `GET /bookings?event_id=E` with booking H1: `confirmed`, venue
"Hall A", submitted `2026-10-01T02:00:00Z`.

## TC-EVENTREGISTRATIONS-042 — a held place at a confirmed event shows date, time and venue

- **Scenario:** The Attendee sees when and where to go (S-56 AC1).
- **Pre-conditions:** As above.
- **Steps:** `GET /event-registrations/me/registrations`.
- **Expected:** `200`, one row: `"event_id": E`, `"start_date": "2026-11-20"`, `"start_time": "18:00:00"`, `"end_date": "2026-11-20"`, `"end_time": "21:00:00"`, `"status": "confirmed"`, `"details_confirmed": true`, `"venue": "Hall A"`.
- **Actual:** `200`, one row for E with the 2026-11-20 18:00–21:00 dates and times, `details_confirmed` true, `venue` "Hall A"; bookings read once by `event_id`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s56.py::test_a_held_place_at_a_confirmed_event_shows_when_and_where; 2026-10-27, branch `S-56/view-confirmed-event-details` (on sprint4 `0d143d7`), pre-commit working tree

## TC-EVENTREGISTRATIONS-044 — an event sent back for re-checking shows "to be confirmed"

- **Scenario:** Details that may be about to change are hidden until confirmed again, and the place stays listed (S-56 AC2, AC4).
- **Pre-conditions:** As above, with E as each of `planning`, `pending_safety_check`, `safety_changes_requested`.
- **Steps:** As TC-EVENTREGISTRATIONS-042, once per status.
- **Expected:** Each → `200`, one row for E with `"status": "confirmed"`, `"details_confirmed": false`, and `start_date`, `start_time`, `end_date`, `end_time` and `venue` all `null`. `name` is still E's name.
- **Actual:** All three statuses → the row stays listed with E's name, `details_confirmed` false, dates, times and `venue` null.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s56.py::test_an_event_being_rechecked_shows_details_to_be_confirmed (3 params); 2026-10-27, branch `S-56/view-confirmed-event-details` (on sprint4 `0d143d7`), pre-commit working tree

## TC-EVENTREGISTRATIONS-045 — the primary venue is the confirmed booking made first

- **Scenario:** A multi-venue event shows one venue (S-56 AC3).
- **Pre-conditions:** As above, with the bookings in each row, in the order given.
- **Steps:** As TC-EVENTREGISTRATIONS-042, once per row.
- **Test data / Expected:**
  | Bookings for E | `venue` |
  | --- | --- |
  | "Room B" confirmed, submitted `2026-10-03`; "Hall A" confirmed, submitted `2026-10-01` | "Hall A" |
  | "Room P" pending, submitted `2026-09-01`; "Room Q" held, submitted `2026-09-02`; "Room R" rejected, submitted `2026-09-03`; "Hall A" confirmed, submitted `2026-10-01` | "Hall A" |
  | "Room P" pending only | `null`, still `"details_confirmed": true` |
  | None | `null`, still `"details_confirmed": true` |
- **Actual:** "Hall A", "Hall A", `null`, `null`; `details_confirmed` true in every row.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s56.py::test_the_primary_venue_is_the_confirmed_booking_made_first (4 params); 2026-10-27, branch `S-56/view-confirmed-event-details` (on sprint4 `0d143d7`), pre-commit working tree

## TC-EVENTREGISTRATIONS-046 — a venue issue shows only once the change is confirmed

- **Scenario:** An unresolved venue issue is not shown; a confirmed replacement is (S-56 AC4).
- **Pre-conditions:** As above, with the bookings in each row.
- **Steps:** As TC-EVENTREGISTRATIONS-042, once per row.
- **Test data / Expected:**
  | Bookings for E | `venue` |
  | --- | --- |
  | H1 "Hall A" `confirmed`, submitted `2026-10-01` (an unavailable period overlaps it); H3 "Hall C" `pending`, `replaces_booking_id` H1, submitted `2026-10-10` | "Hall A" |
  | H1 "Hall A" `replaced`, `replaced_by_booking_id` H3, submitted `2026-10-01`; H2 "Room B" `confirmed`, submitted `2026-10-03`; H3 "Hall C" `confirmed`, `replaces_booking_id` H1, submitted `2026-10-10` | "Hall C" (it took H1's place, ahead of H2) |

  Neither row says anything about the unavailable period or the replacement.
- **Actual:** Replacement pending → "Hall A"; replacement confirmed → "Hall C". Row keys unchanged, nothing about the issue.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s56.py::test_a_venue_issue_shows_only_once_the_change_is_confirmed (2 params); 2026-10-27, branch `S-56/view-confirmed-event-details` (on sprint4 `0d143d7`), pre-commit working tree

## TC-EVENTREGISTRATIONS-047 — a waiting-list entry shows no venue

- **Scenario:** Only an Attendee holding a place sees the venue; a waiting Attendee sees they're waiting (S-56 developer decision).
- **Pre-conditions:** A holds no place at E and is 2nd on its waiting list; E is `confirmed` with H1.
- **Steps:** As TC-EVENTREGISTRATIONS-042.
- **Expected:** `200`, one row for E with `"status": "waitlisted"`, `"position": 2`, E's dates and times as in TC-EVENTREGISTRATIONS-042, and `"venue": null`.
- **Actual:** `waitlisted`, position 2, E's dates and times, `venue` null; bookings not read.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s56.py::test_a_waiting_list_entry_shows_no_venue; 2026-10-27, branch `S-56/view-confirmed-event-details` (on sprint4 `0d143d7`), pre-commit working tree

## TC-EVENTREGISTRATIONS-048 — no internal planning information

- **Scenario:** The Attendee's list carries only what the card shows (S-56 AC5).
- **Pre-conditions:** As above, with the events fake's E also carrying `purpose`, `expected_attendance` 120, `registration_closed_at` and `registration_required`, and H1 carrying `coordinator_name`, `coordinator_email`, `notes` and `special_requirements`.
- **Steps:** As TC-EVENTREGISTRATIONS-042.
- **Expected:** The row's keys are exactly `event_id`, `name`, `start_date`, `start_time`, `end_date`, `end_time`, `status`, `registered_at`, `joined_at`, `position`, `details_confirmed` and `venue`. None of the extra event or booking fields appear.
- **Actual:** Exactly the twelve keys; none of the purpose, attendance, organiser, coordinator or booking notes in the row.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s56.py::test_the_list_carries_no_internal_planning_information; 2026-10-27, branch `S-56/view-confirmed-event-details` (on sprint4 `0d143d7`), pre-commit working tree

## TC-EVENTREGISTRATIONS-049 — a cancelled or closed event is not listed

- **Scenario:** The list keeps its S-48 behaviour for events that are over (S-56 developer decision).
- **Pre-conditions:** As above, with the events fake answering `404` for E (cancelled, rejected or otherwise not shown to Attendees).
- **Steps:** As TC-EVENTREGISTRATIONS-042.
- **Expected:** `200` `[]`.
- **Actual:** `200` `[]`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s56.py::test_a_cancelled_or_closed_event_is_not_listed; 2026-10-27, branch `S-56/view-confirmed-event-details` (on sprint4 `0d143d7`), pre-commit working tree

## TC-EVENTREGISTRATIONS-050 — the bookings service fails

## S-91 — Designate Primary Venue

### TC-EVENTREGISTRATIONS-051 — attendees receive only the explicitly primary venue

- **Pre-conditions:** Published event E has confirmed bookings B1 and B2; B2 has `is_primary=true`.
- **Steps:** Read E from the public list, public detail, Attendee dashboard, and build a registration notification.
- **Expected:** Every attendee-facing result names only B2. B1 and all non-confirmed bookings are absent.

### TC-EVENTREGISTRATIONS-052 — no primary reads as venue to be confirmed

- **Pre-conditions:** E has confirmed bookings but none is primary, including immediately after its old primary was cancelled or replaced.
- **Steps:** Read E and build its attendee detail/notification.
- **Expected:** The public venue list is empty, the attendee detail venue is null, and notification wording says `venue to be confirmed`.

### TC-EVENTREGISTRATIONS-053 — an invalid primary marker is never exposed

- **Pre-conditions:** A defensive fixture marks a held, rejected, or replaced booking primary.
- **Steps:** Build attendee-facing venue data.
- **Expected:** Only a row that is both confirmed and primary is exposed.

- **Scenario:** A venue that can't be read is reported, not shown as "to be confirmed".
- **Pre-conditions:** As above, with bookings answering `500`, then unreachable.
- **Steps:** As TC-EVENTREGISTRATIONS-042, for each.
- **Expected:** Both → `502` "Bookings service unavailable".
- **Actual:** Both → `502` "Bookings service unavailable".
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s56.py::test_the_bookings_service_fails (2 params); 2026-10-27, branch `S-56/view-confirmed-event-details` (on sprint4 `0d143d7`), pre-commit working tree

## S-55 — Notify Waitlisted Attendee of Opening

Developer decisions (2026-10-30):

- A place freed before the event starts is **offered** to the first Attendee
  on the waiting list (first come, first served). They are **not** registered.
  This replaces S-53's automatic promotion: TC-EVENTREGISTRATIONS-039 and -040
  are retired in favour of -054 and -055.
- The offer is held for them. It counts as a taken place, so the event stays
  full to everyone else and nobody further down the line can take it.
- It has no expiry. It stays open until the invited Attendee accepts or
  declines, or the event starts. Declining takes them off the waiting list and
  offers the place to the next in line.
- Places are freed only by a withdrawal (S-53) or a decline. A raised expected
  attendance is out of scope.
- Offering, accepting and declining are open until the event starts (SGT),
  whatever the registration period or an Organiser close says. At the start
  itself, accepting and declining are refused.
- The invited Attendee gets one in-app notification of kind
  `waiting_list_offer`: "A place opened up at {event}, {S-49 date/time}, at
  {venues}. It's held for you: accept it on the event page to register."
  Accepting sends the S-49 `registration_confirmation`. As before, a
  notification that can't be built or stored is logged and the request still
  succeeds.
- The Organiser's view is unchanged: the invited Attendee stays at the top of
  their waiting list until they answer (my default, not asked).

Routes: accept `POST /event-registrations/events/{id}/waiting-list/offer`,
decline `DELETE /event-registrations/events/{id}/waiting-list/offer`. The status
body (`RegistrationStatus`) gains `offered: bool`. Clock, E, A and B as in S-53
above: E has `expected_attendance` 2 and starts `2026-11-20 18:00`. C is
`55555555-5555-4555-8555-555555555555`, "Cy Tan", `cy@example.com`. B's
waiting-list row id is `77777777-7777-4777-8777-777777777777` and C's is
`88888888-8888-4888-8888-888888888888`.

## TC-EVENTREGISTRATIONS-054 — a withdrawal invites the next in line instead of registering them

- **Scenario:** When A withdraws and a place frees up, B is invited and told so. B is not registered (S-55 AC1, AC2).
- **Pre-conditions:** Registrations answers `POST /registrations/withdrawals` with `200` `{"withdrawn": <A's row>, "offered": <B's waiting-list row, offered_at set>}`. Users `POST /internal/users/profiles` `{"ids": [B]}` answers B's profile. E's one confirmed primary venue is "Seminar Room 2-1".
- **Steps:** As A, `DELETE /event-registrations/events/E/registration`.
- **Test data:** As above. Variants: no confirmed venue; clock `2026-11-16 12:00` (after registration closed).
- **Expected:** `200` `{"event_id": E, "registered": false, "registered_at": null, "waitlisted": false, "joined_at": null, "position": null, "offered": false}`. Exactly one `POST /internal/notifications` with one row: `recipient_id` B, `event_id` E, `event_name` "Alumni networking evening", `kind` `waiting_list_offer`, `deduplication_key` `waiting_list_offer:77777777-7777-4777-8777-777777777777`, `message` "A place opened up at Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, at Seminar Room 2-1. It's held for you: accept it on the event page to register.". No row is addressed to A. No `waiting_list_promotion` or `registration_confirmation` is sent, and the composite never calls `POST /registrations` for B. With no venue: "…9:00 pm, venue to be confirmed. It's held for you: …". After registration closed, the invitation is still sent.
- **Actual:** `200` not-holding body; one profile lookup for B; exactly one `waiting_list_offer` row to B with the expected message and key; none to A; only `POST /registrations/withdrawals` called; no-venue wording "venue to be confirmed. It's held for you: …"; also sent after registration closed.
- **Status:** Pass
- **Evidence:** test_s55.py::test_a_withdrawal_invites_the_next_in_line, ::test_an_invitation_without_a_confirmed_venue, ::test_an_invitation_after_registration_has_closed; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-055 — a failed invitation doesn't undo the withdrawal

- **Scenario:** The withdrawal and the offer are already recorded, so an invitation that can't be built or stored is logged and the withdrawal still succeeds.
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-054, except as in each row.
- **Steps:** As A, `DELETE /event-registrations/events/E/registration`.
- **Test data / Expected:**
  | Failure | Result |
  | --- | --- |
  | Notifications answers `500` | `200`, same body as TC-EVENTREGISTRATIONS-054 |
  | Notifications unreachable (`ConnectError`) | `200`, same body |
  | Users profiles answers `500` | `200`, same body; no notification sent |
  | Bookings answers `500` (venues unreadable) | `200`, same body; no notification sent |
- **Actual:** All four failures `200` with the same body; notifications attempted for the first two, not sent for the last two.
- **Status:** Pass
- **Evidence:** test_s55.py::test_a_failed_invitation_keeps_the_withdrawal; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-056 — a held offer counts as a taken place

- **Scenario:** While B's offer is open, the event reads as full to everyone else and offers them the waiting list, not a place (S-55 AC1: the place goes to B, first come, first served).
- **Pre-conditions:** E has `expected_attendance` 2. Registrations holds one place (A). The waiting list is B (`offered_at` set) then C (`offered_at` null). Attendee D (`66666666-6666-4666-8666-666666666666`) is signed in for the last two rows.
- **Steps / Expected:**
  | Request | Result |
  | --- | --- |
  | `GET /event-registrations/events/E` | `200`, `"is_full": true` |
  | `GET /event-registrations/events` | E's entry has `"is_full": true` |
  | As D, `POST /event-registrations/events/E/waiting-list` | `201`; joining is allowed, not refused with "This event still has places." |
  | Same, with B's `offered_at` null (no offer held) | `409` "This event still has places. Register instead." |
- **Test data:** As above.
- **Actual:** Event and list both `is_full` true; D joined `201` at position 3; with no offer held, `409` "This event still has places. Register instead."
- **Status:** Pass
- **Evidence:** test_s55.py::test_a_held_offer_counts_as_a_taken_place, ::test_a_newcomer_can_join_the_waiting_list_while_an_offer_is_held, ::test_without_an_open_offer_the_place_is_free; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-057 — the invited Attendee's status shows the offer

- **Scenario:** The event page can tell an invited Attendee from one still waiting (S-55 AC1).
- **Pre-conditions:** As TC-EVENTREGISTRATIONS-056. Registrations answers `404` for B's and C's place lookups.
- **Steps:** `GET /event-registrations/events/E/registration` as B, as C, then as A (registered).
- **Test data:** As above.
- **Expected:** B → `{"registered": false, "waitlisted": true, "joined_at": <B's>, "position": 1, "offered": true, ...}`. C → `"waitlisted": true, "position": 2, "offered": false`. A → `"registered": true, "offered": false`.
- **Actual:** B waitlisted at 1 with `offered` true; C at 2 with `offered` false; A registered with `offered` false.
- **Status:** Pass
- **Evidence:** test_s55.py::test_the_invited_attendees_status_shows_the_offer; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-058 — the invited Attendee accepts and is registered

- **Scenario:** B takes the held place by their own action, gets a place and gets the S-49 confirmation (S-55 AC2).
- **Pre-conditions:** As B. Registrations answers `POST /registrations/offers/acceptances` with `201` and B's new place (id `99999999-9999-4999-8999-999999999999`, `created_at` `2026-11-06T04:00:00+00:00`). E's primary venue is "Seminar Room 2-1".
- **Steps:** `POST /event-registrations/events/E/waiting-list/offer`.
- **Test data:** Clock variants: `2026-11-05 12:00`; `2026-11-16 12:00` (period closed); `2026-11-05 12:00` with `registration_closed_at` set (Organiser closed).
- **Expected:** All three → `201` `{"event_id": E, "registered": true, "registered_at": "2026-11-06T04:00:00Z", "offered": false, ...}`. Registrations gets exactly one `POST /registrations/offers/acceptances` `{"event_id": E, "attendee_id": B}`, with B taken from the session. Exactly one notification is sent: `recipient_id` B, `kind` `registration_confirmation`, key `registration_confirmation:9999…9999`, message "Registration confirmed: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, at Seminar Room 2-1. Name: Ben Lee. Email: ben@example.com.". If notifications answers `500`, it is still `201`.
- **Actual:** All three clocks `201` registered at `2026-11-06T04:00:00Z`; one `POST /registrations/offers/acceptances` `{E, B}`; one `registration_confirmation` to B with the S-49 message and key; notifications `500` still `201`.
- **Status:** Pass
- **Evidence:** test_s55.py::test_the_invited_attendee_accepts_and_is_registered, ::test_a_failed_confirmation_keeps_the_acceptance; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-059 — the invited Attendee declines and the next in line is invited

- **Scenario:** B passes on the place: B leaves the waiting list and C, next in line, is invited (S-55 AC1).
- **Pre-conditions:** As B. Registrations answers `POST /registrations/offers/declines` per row.
- **Steps:** `DELETE /event-registrations/events/E/waiting-list/offer`.
- **Test data / Expected:** Registrations always gets exactly one `POST /registrations/offers/declines` `{"event_id": E, "attendee_id": B, "capacity": 2}`. The response is always `200` `{"event_id": E, "registered": false, "registered_at": null, "waitlisted": false, "joined_at": null, "position": null, "offered": false}`.
  | Registrations answers | Notifications |
  | --- | --- |
  | `{"declined": <B's row>, "offered": <C's row>}` | exactly one `waiting_list_offer` row to C, key `waiting_list_offer:8888…8888`, same message as TC-EVENTREGISTRATIONS-054; none to B |
  | `{"declined": <B's row>, "offered": null}` | none sent |
  | C offered, notifications answers `500` | still `200` |
- **Actual:** `200` not-holding body each time; one `POST /registrations/offers/declines` `{E, B, capacity 2}`; C offered → one `waiting_list_offer` to C; none when no one is offered; notifications `500` still `200`.
- **Status:** Pass
- **Evidence:** test_s55.py::test_declining_invites_the_next_in_line, ::test_declining_with_no_one_else_waiting, ::test_a_failed_invitation_keeps_the_decline; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-060 — who may accept or decline, and when

- **Scenario:** Only a signed-in Attendee holding the offer, before the event starts, can answer it.
- **Pre-conditions:** As in each row. Each row is run against both routes (accept `POST`, decline `DELETE` on `/event-registrations/events/{id}/waiting-list/offer`).
- **Steps:** Send the request.
- **Test data / Expected:**
  | Situation | Result |
  | --- | --- |
  | Users `/users/me` answers `401` | `401` "Sign in to respond to this offer."; registrations not called |
  | Signed in as an `event_organiser` | `403` "Only attendee accounts can register for events."; registrations not called |
  | Event id not public (events answers `404` "Event not found.") | `404` "Event not found."; registrations not called |
  | Clock `2026-11-20 18:00` SGT (the start) | `409` "This event has already started. The place can no longer be taken."; registrations not called |
  | Clock `2026-11-20 17:59` SGT | accepted/declined as normal |
  | Registrations answers `404` (C, who holds no offer) | `404` "You don't have a place on offer for this event."; no notification |
  | Registrations answers `500`, or is unreachable | `502` "Registrations service unavailable"; no notification |
- **Actual:** Both routes: `401` "Sign in to respond to this offer."; `403`; unknown event `404`; 18:00 `409` with the started message and registrations not called, 17:59 answered; no offer `404`; registrations `500`/unreachable `502`; no notification on any refusal.
- **Status:** Pass
- **Evidence:** test_s55.py::test_answering_needs_a_signed_in_attendee, ::test_answering_an_offer_for_an_event_that_isnt_public, ::test_answering_is_open_until_the_event_starts, ::test_answering_without_an_offer, ::test_answering_when_the_registrations_service_fails; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-EVENTREGISTRATIONS-061 — the dashboard shows an offer

- **Scenario:** "Your registrations" lists the event with an offer, so the invited Attendee can find it from their dashboard (S-55 AC1).
- **Pre-conditions:** As B. Registrations holds no place for B. B's waiting list holds B's row for E with `offered_at` set. E is `confirmed`, with primary venue "Seminar Room 2-1".
- **Steps:** `GET /event-registrations/me/registrations`.
- **Test data:** Variant: B's row with `offered_at` null.
- **Expected:** One row for E: `"status": "offered"`, `"position": 1`, `"joined_at"` B's, `"registered_at": null`, `"venue": null` (only a held place shows where), with E's date and time. Variant: `"status": "waitlisted"` as before (S-52). As with a waiting-list entry, it is listed only while E is `confirmed`.
- **Actual:** Offered row `status` "offered", position 1, B's join time, no venue, E's date and time; not offered → "waitlisted"; not listed while E is `planning`.
- **Status:** Pass
- **Evidence:** test_s55.py::test_the_dashboard_shows_an_offer, ::test_an_offer_is_listed_only_while_the_event_is_confirmed; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## S-57 — View Event Registration List

Acceptance criteria (developer, 2026-10-30): the Event Organiser can view
attendee registration information for an event they are permitted to access;
it identifies the attendees currently registered; withdrawn Attendees are
distinguishable or excluded; changes to registrations are reflected; with no
current registrations the viewer is clearly told so.

Developer's answers, 2026-10-30: "permitted to access" means the event's own
Organiser **and** the Event Coordinator assigned to it. A withdrawn Attendee is
excluded, because S-53 deletes the place. "Reflected" means every read is
fresh, and the panel gets a **Refresh list** button.

The composite asks the events service about the event as the caller.
`GET /events/E` answers `200` to the owning Organiser. If that answers `403`,
the composite tries `GET /events/assigned/E`, which answers `200` to the
assigned Coordinator. This revises TC-EVENTREGISTRATIONS-015: a `403` from
`GET /events/E` no longer ends the request.

Drafted 2026-10-30 on `S-57/view-event-registration-list` (from `origin/sprint4`). Confirmed by the developer 2026-10-30.

Organiser O owns E. Coordinator C (`55555555-5555-4555-8555-555555555555`)
is E's `assigned_coordinator_id`. Attendees A and B as in S-48.

## TC-EVENTREGISTRATIONS-062 — the assigned Coordinator sees who registered

- **Scenario:** The Coordinator assigned to the event sees the same list as its Organiser (S-57 AC1, AC2).
- **Pre-conditions:** C's session cookie. Events fake: `GET /events/E` answers `403` `{"detail": "Insufficient permissions"}`; `GET /events/assigned/E` (C's cookie forwarded) answers `200`. Registrations fake returns A's and B's rows for E; waiting list `[]`. Users fake answers `POST /internal/users/profiles` with A and B.
- **Steps:** `GET /event-registrations/events/E/attendees`.
- **Test data:** As above.
- **Expected:** `200` with the exact TC-EVENTREGISTRATIONS-013 body: `count` 2, A then B with name, email and `registered_at`, `"waiting_list": []`. C's cookie was forwarded to both events calls.
- **Actual:** `200` with `count` 2, A then B, `waiting_list` `[]`; events asked `/events/E` then `/events/assigned/E`, C's cookie forwarded to both.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s57.py::test_the_assigned_coordinator_sees_who_registered; 2026-10-30, branch `S-57/view-event-registration-list` rebased on sprint4 `30837ca` (S-55); Python 3.12.5, pytest 9.1.1: 129 passed in this suite, 1706 passed and 17 skipped across `tests/unit`

## TC-EVENTREGISTRATIONS-063 — a Coordinator not assigned to the event is refused

- **Scenario:** Only the assigned Coordinator gets the list, not every Coordinator (S-57 AC1).
- **Pre-conditions:** Coordinator C2's cookie. Events fake: `GET /events/E` answers `403`; `GET /events/assigned/E` answers `404` `{"detail": "Event not found"}`.
- **Steps:** `GET /event-registrations/events/E/attendees`.
- **Test data:** As above.
- **Expected:** `404` "Event not found". The registrations and users services are never called.
- **Actual:** `404` "Event not found"; registrations and users never called.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s57.py::test_a_coordinator_not_assigned_to_the_event_is_refused; 2026-10-30, branch `S-57/view-event-registration-list` rebased on sprint4 `30837ca` (S-55); Python 3.12.5, pytest 9.1.1: 129 passed in this suite, 1706 passed and 17 skipped across `tests/unit`

## TC-EVENTREGISTRATIONS-064 — every other role is still refused

- **Scenario:** Attendee names and emails still reach no one beyond the Organiser and the assigned Coordinator (S-57 AC1; keeps TC-EVENTREGISTRATIONS-015's 403).
- **Pre-conditions:** An Attendee's, a Venue Staff member's and a Coordinator Lead's cookie, in turn. Events fake answers both `GET /events/E` and `GET /events/assigned/E` with `403` `{"detail": "Insufficient permissions"}`.
- **Steps:** `GET /event-registrations/events/E/attendees` once per role.
- **Test data:** As above.
- **Expected:** `403` "Insufficient permissions" each time. The registrations and users services are never called. A `401` from `GET /events/E` still answers `401` "Sign in to see who has registered." without calling `/events/assigned/E`.
- **Actual:** `403` "Insufficient permissions" for attendee, venue_staff and event_coordinator_lead; registrations and users never called. Signed out: `401` "Sign in to see who has registered.", only `/events/E` asked.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s57.py::test_every_other_role_is_still_refused_the_attendee_list, ::test_signed_out_is_answered_without_asking_as_a_coordinator; 2026-10-30, branch `S-57/view-event-registration-list` rebased on sprint4 `30837ca` (S-55); Python 3.12.5, pytest 9.1.1: 129 passed in this suite, 1706 passed and 17 skipped across `tests/unit`

## TC-EVENTREGISTRATIONS-065 — each read shows the registrations as they are now

- **Scenario:** The list is never cached. A withdrawal shows on the next read, and so does the last one (S-57 AC3, AC4, AC5).
- **Pre-conditions:** O's cookie; events fake answers `GET /events/E` `200`. The registrations fake for `GET /registrations/events/E` returns, on successive calls: A and B; then B only; then `[]`. Waiting list `[]` throughout.
- **Steps:** `GET /event-registrations/events/E/attendees` three times.
- **Test data:** As above.
- **Expected:** 1 → `count` 2, A then B. 2 → `count` 1, `attendees` B only; A appears nowhere in the body. 3 → `200` `{"event_id": "E", "count": 0, "attendees": [], "waiting_list": []}`. The registrations service was called three times.
- **Actual:** `count` 2 (A, B); then `count` 1 (B only, A's id absent); then `{"event_id": "E", "count": 0, "attendees": [], "waiting_list": []}`; places read three times.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_s57.py::test_each_read_shows_the_registrations_as_they_are_now; 2026-10-30, branch `S-57/view-event-registration-list` rebased on sprint4 `30837ca` (S-55); Python 3.12.5, pytest 9.1.1: 129 passed in this suite, 1706 passed and 17 skipped across `tests/unit`
