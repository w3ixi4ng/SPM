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

- **Scenario:** Attendee names and emails reach no one else (developer's answer, 2026-10-25).
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
