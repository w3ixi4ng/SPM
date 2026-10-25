# Test cases — registrations service (unit)

Covers `tests/unit/atomic/registrations/test_app.py`: the registrations service
on its own, with Supabase replaced by a `MagicMock`. No network, database, or
Docker. Only composites call this service; it has no Kong route.

A registration is one Attendee's place at one event, and `(event_id,
attendee_id)` is unique, so one account holds at most one place per event.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/registrations` |
| Last run | 2026-10-25, branch `S-48/register-for-event`, pre-commit working tree |
| Environment | Python 3.14.4, pytest 9.1.1; no network, database, or Docker |
| Result | 7 cases, 11 tests passed in this suite; 1364 passed, 17 skipped across `tests/unit` |

Test data used throughout: event E `22222222-2222-4222-8222-222222222222`,
Attendee A `33333333-3333-4333-8333-333333333333`, Attendee B
`44444444-4444-4444-8444-444444444444`.

## TC-REGISTRATIONS-001 — health

- **Scenario:** The service answers its health check.
- **Pre-conditions:** None.
- **Steps:** `GET /health`.
- **Test data:** None.
- **Expected:** `200` `{"status": "ok"}`.
- **Actual:** `200` `{"status": "ok"}`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_health_reports_ok; `pytest tests/unit`: 1325 passed, 17 skipped, 2026-10-25

## TC-REGISTRATIONS-002 — an Attendee takes a place

- **Scenario:** A registration is saved (S-51 AC5).
- **Pre-conditions:** The insert returns the new row.
- **Steps:** `POST /registrations`.
- **Test data:** `{"event_id": E, "attendee_id": A}`.
- **Expected:** `201` `{"id": "<uuid>", "event_id": E, "attendee_id": A,
  "created_at": "<timestamp>"}`. The insert goes to
  `registrations.registrations` with exactly those two fields.
- **Actual:** `201` with the row; inserted into `registrations.registrations` with exactly the two ids.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_an_attendee_takes_a_place

## TC-REGISTRATIONS-003 — one account registers once

- **Scenario:** A second registration by the same account is refused (S-51 AC5; developer's answer, 2026-10-25).
- **Pre-conditions:** The insert raises a Postgres unique violation (`23505`).
- **Steps:** `POST /registrations` with the body from TC-REGISTRATIONS-002.
- **Expected:** `409` "You're already registered for this event."
- **Actual:** `409` "You're already registered for this event."
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_one_account_registers_once

## TC-REGISTRATIONS-004 — malformed registration requests

- **Scenario:** Bad input never reaches the database.
- **Pre-conditions:** None.
- **Steps:** `POST /registrations` with each body.
- **Test data:**
  1. `{"event_id": E}` (no attendee)
  2. `{"event_id": "not-a-uuid", "attendee_id": A}`
  3. `{"event_id": E, "attendee_id": A, "id": E}` (extra field)
- **Expected:** Each → `422`; the insert is never called.
- **Actual:** All three → `422`; insert never called.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_malformed_registration_requests

## TC-REGISTRATIONS-005 — reading whether an Attendee holds a place

- **Scenario:** Composites can tell whether someone is registered (S-51 AC5).
- **Pre-conditions:** Fake returns A's row for the first call, `[]` for B.
- **Steps:**
  1. `GET /registrations/events/E/attendees/A`
  2. `GET /registrations/events/E/attendees/B`
- **Expected:** 1 → `200` A's row. 2 → `404` "You're not registered for this
  event." Both filter `event_id = E` and the attendee id.
- **Actual:** A's row → `200`; B → `404` "You're not registered for this event."; both filtered by event and attendee.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_reading_whether_an_attendee_holds_a_place

## TC-REGISTRATIONS-006 — every place at one event

- **Scenario:** A registration can be read back against its event (S-48 AC3).
- **Pre-conditions:** Fake returns A's row (created `2026-11-05T04:00:00Z`)
  and B's row (created `2026-11-06T04:00:00Z`) for E, then `[]` for event
  `66666666-6666-4666-8666-666666666666`.
- **Steps:**
  1. `GET /registrations/events/E`
  2. `GET /registrations/events/66666666-6666-4666-8666-666666666666`
- **Test data:** As pre-conditions.
- **Expected:** 1 → `200`, a list of A's row then B's row, filtered
  `event_id = E` and ordered by `created_at` ascending. 2 → `200` `[]` (never
  `404`). `GET /registrations/events/not-a-uuid` → `422`, no query made.
- **Actual:** A then B, filtered by event and ordered by `created_at`; an event with none → `200` `[]`; `not-a-uuid` → `422` with no query.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_every_place_at_one_event; tests/unit/atomic/registrations/test_app.py::test_listing_an_events_places_needs_a_uuid

## TC-REGISTRATIONS-007 — every place one Attendee holds

- **Scenario:** A registration can be read back against its Attendee (S-48 AC3).
- **Pre-conditions:** Fake returns A's rows for E and for event
  `66666666-6666-4666-8666-666666666666`, then `[]` for B.
- **Steps:**
  1. `GET /registrations/attendees/A`
  2. `GET /registrations/attendees/B`
- **Test data:** As pre-conditions.
- **Expected:** 1 → `200`, both of A's rows, filtered `attendee_id = A` and
  ordered by `created_at` ascending. 2 → `200` `[]`.
  `GET /registrations/attendees/not-a-uuid` → `422`, no query made.
- **Actual:** Both of A's rows, filtered by attendee and ordered by `created_at`; B → `200` `[]`; `not-a-uuid` → `422` with no query.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_every_place_one_attendee_holds; tests/unit/atomic/registrations/test_app.py::test_listing_an_attendees_places_needs_a_uuid
