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
| Last run | 2026-10-25, branch `S-51/configure-registration-and-open-close-period`, pre-commit working tree |
| Environment | Python 3.14.4, pytest 9.1.1; no network, database, or Docker |
| Result | 12 cases, 17 tests passed in this suite; 1325 passed, 17 skipped across `tests/unit` |

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
   "registration_opens_at": "2026-11-01T09:00:00", "registration_closes_at": "2026-11-15T18:00:00"}
  ```
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

- **Scenario:** Attempts before opening are blocked with a message (S-51 AC3).
- **Pre-conditions:** Signed-in Attendee A; event E.
- **Steps:** `POST /event-registrations/events/E/registration` at each clock.
- **Test data:** 1. `2026-10-25 10:00` SGT. 2. `2026-11-01 08:59` SGT.
  3. `2026-11-01 09:00` SGT (exactly opening).
- **Expected:** 1 and 2 → `409` "Registration opens on 1 Nov 2026, 9:00 am."
  and the registrations service is not called. 3 → `201`.
- **Actual:** 10:00 on 25 Oct and 08:59 on 1 Nov → `409` "Registration opens on 1 Nov 2026, 9:00 am." with no registrations call; 09:00 → `201`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_registering_before_the_period_opens_is_blocked; tests/unit/composite/event_registrations/test_app.py::test_registration_opens_at_exactly_the_opening_time

## TC-EVENTREGISTRATIONS-007 — registering after the period closes is blocked

- **Scenario:** Attempts after closing are blocked with a message (S-51 AC3).
- **Pre-conditions:** Signed-in Attendee A; event E.
- **Steps:** `POST /event-registrations/events/E/registration` at each clock.
- **Test data:** 1. `2026-11-15 17:59` SGT. 2. `2026-11-15 18:00` SGT
  (exactly closing). 3. `2026-11-18 09:00` SGT.
- **Expected:** 1 → `201`. 2 and 3 → `409` "Registration closed on 15 Nov
  2026, 6:00 pm." and the registrations service is not called.
- **Actual:** 17:59 → `201`; 18:00 on 15 Nov and 09:00 on 18 Nov → `409` "Registration closed on 15 Nov 2026, 6:00 pm." with no registrations call.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_registering_after_the_period_closes_is_blocked; tests/unit/composite/event_registrations/test_app.py::test_registration_is_still_open_a_minute_before_closing

## TC-EVENTREGISTRATIONS-008 — registering inside the period takes a place

- **Scenario:** A registered Attendee holds a place (S-51 AC5).
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
- **Expected:** 1 → `409` "Registration opens on 1 Nov 2026, 9:00 am."
  2 → `201`.
- **Actual:** 00:59Z → `409` with the opening message; 01:00Z → `201`.
- **Status:** Pass
- **Evidence:** tests/unit/composite/event_registrations/test_app.py::test_now_is_singapore_time_whatever_the_servers_clock

## TC-EVENTREGISTRATIONS-011 — an Attendee sees whether they hold a place

- **Scenario:** The event page can show "You're registered" (S-51 AC5).
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
