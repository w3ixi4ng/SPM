# Test cases — registrations service (unit)

Covers `tests/unit/atomic/registrations/test_app.py`: the registrations service
on its own, with Supabase replaced by a `MagicMock`. No network, database, or
Docker. Only composites call this service; it has no Kong route.

A registration is one Attendee's place at one event, and `(event_id,
attendee_id)` is unique, so one account holds at most one place per event.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/registrations` |
| Last run | 2026-10-25, branch `S-51/configure-registration-and-open-close-period`, pre-commit working tree |
| Environment | Python 3.14.4, pytest 9.1.1; no network, database, or Docker |
| Result | 5 cases, 7 tests passed in this suite; 1325 passed, 17 skipped across `tests/unit` |

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
