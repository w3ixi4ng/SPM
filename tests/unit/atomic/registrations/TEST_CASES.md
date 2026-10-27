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

- **Scenario:** A registration is saved (S-51 AC5). Revised for S-50: the body also carries `"capacity": 50` and the place is taken through `rpc("register", ...)` rather than a plain insert (see TC-REGISTRATIONS-008).
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

- **Scenario:** A second registration by the same account is refused (S-51 AC5; developer's answer, 2026-10-25). Revised for S-50: the body carries `"capacity": 50`; the duplicate comes back from `rpc("register", ...)`.
- **Pre-conditions:** The insert raises a Postgres unique violation (`23505`).
- **Steps:** `POST /registrations` with the body from TC-REGISTRATIONS-002.
- **Expected:** `409` "You're already registered for this event."
- **Actual:** `409` "You're already registered for this event."
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_one_account_registers_once

## TC-REGISTRATIONS-004 — malformed registration requests

- **Scenario:** Bad input never reaches the database. Revised for S-50: each malformed body otherwise carries `"capacity": 50`, so only the named fault is under test.
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

## S-50 — Cap Registration at Capacity

The cap is enforced in Postgres, not in Python: `POST /registrations` now
carries the event's `capacity` and calls the `registrations.register(...)`
function, which locks the event, counts its places and inserts only if one is
left. The fake below stands in for that function's answers.

## TC-REGISTRATIONS-008 — a place is taken while the event has room

- **Scenario:** Registering under the cap stores the place through the capped insert (S-50 AC1, AC3).
- **Pre-conditions:** The fake's `rpc("register", ...)` returns one row
  `{"id": "R", "event_id": E, "attendee_id": A, "created_at": "2026-11-02T01:00:00+00:00"}`.
- **Steps:** `POST /registrations`.
- **Test data:** `{"event_id": E, "attendee_id": A, "capacity": 50}`.
- **Expected:** `201` with that row. The fake was called on schema
  `registrations` with `rpc("register", {"p_event_id": E, "p_attendee_id": A, "p_capacity": 50})`.
  No plain `.table(...).insert(...)` was made.
- **Actual:** `201` with the row; `rpc("register", {p_event_id: E, p_attendee_id: A, p_capacity: 50})` on schema `registrations`; no plain insert.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_a_place_is_taken_while_the_event_has_room; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-REGISTRATIONS-009 — a full event refuses the place

- **Scenario:** Once registered Attendees reach capacity, registration is blocked (S-50 AC1).
- **Pre-conditions:** The fake's `rpc` raises `APIError` with code `SP050`
  (what `registrations.register` raises when the count has reached capacity).
- **Steps:** `POST /registrations`.
- **Test data:** `{"event_id": E, "attendee_id": B, "capacity": 1}`.
- **Expected:** `409` `{"detail": "This event is full."}`.
- **Actual:** `409` `{"detail": "This event is full."}`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_a_full_event_refuses_the_place; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-REGISTRATIONS-010 — a registration without a usable capacity is rejected

- **Scenario:** Every place is taken against a cap; an uncapped insert is impossible.
- **Pre-conditions:** None. The fake is never called.
- **Steps:** `POST /registrations` once per payload.
- **Test data:** `{"event_id": E, "attendee_id": A}`; the same with `"capacity": 0`; with `"capacity": -5`.
- **Expected:** Each → `422` with `errors.capacity` present. `rpc` not called.
- **Actual:** All three → `422` with `errors.capacity`; `rpc` not called.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_a_registration_without_a_usable_capacity_is_rejected; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-REGISTRATIONS-011 — joining the waiting list, once

- **Scenario:** An Attendee is recorded on an event's waiting list (S-50 AC2).
- **Pre-conditions:** First insert into `registrations.waiting_list` returns
  `{"id": "W", "event_id": E, "attendee_id": B, "created_at": "2026-11-02T02:00:00+00:00"}`;
  second raises `APIError` code `23505`.
- **Steps:** `POST /registrations/waiting-list` twice.
- **Test data:** `{"event_id": E, "attendee_id": B}`.
- **Expected:** First → `201` with that row, written to schema
  `registrations`, table `waiting_list`. Second → `409`
  `{"detail": "You're already on the waiting list for this event."}`.
- **Actual:** `201` with the row written to `registrations.waiting_list`; repeat → `409` "You're already on the waiting list for this event."
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_joining_the_waiting_list_once; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-REGISTRATIONS-012 — an event's waiting list, in join order

- **Scenario:** The waiting list reads back oldest first.
- **Pre-conditions:** The fake returns two rows for E (B joined `02:00`, A joined `03:00`), then `[]` for event F.
- **Steps:** `GET /registrations/waiting-list/events/E`; `GET /registrations/waiting-list/events/F`.
- **Expected:** E → `200`, B's row then A's; the query filtered `event_id = E`
  and ordered by `created_at`. F → `200` `[]`, not `404`.
- **Actual:** E → B then A, filtered on `event_id` and ordered by `created_at`; F → `[]`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_an_events_waiting_list_in_join_order; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## TC-REGISTRATIONS-013 — one Attendee's waiting-list entry

- **Scenario:** Whether an Attendee is on an event's waiting list.
- **Pre-conditions:** The fake returns B's row, then `[]`.
- **Steps:** `GET /registrations/waiting-list/events/E/attendees/B`, then `.../attendees/A`.
- **Expected:** B → `200` with the row. A → `404`
  `{"detail": "You're not on the waiting list for this event."}`.
- **Actual:** B → `200` with the row; A → `404` "You're not on the waiting list for this event."
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_one_attendees_waiting_list_entry; 2026-10-26, branch `S-50/cap-registration-at-capacity`, pre-commit working tree

## S-52 — Join Waiting List

The waiting list is first-come, first-served: an entry's place is its order
by `created_at`, with `id` breaking a tie so two entries never share a place
(developer's answers, 2026-10-26). Attendee C is
`55555555-5555-4555-8555-555555555555`; event F is
`66666666-6666-4666-8666-666666666666`.

## TC-REGISTRATIONS-014 — an Attendee's waiting-list entries

- **Scenario:** Every event an Attendee is waiting for can be read in one call, for their dashboard (S-52 AC3).
- **Pre-conditions:** The fake returns B's rows for E (`created_at` `2026-11-05T04:00:00+00:00`) and F (`2026-11-06T04:00:00+00:00`), then `[]`.
- **Steps:** `GET /registrations/waiting-list/attendees/B`, then `GET /registrations/waiting-list/attendees/A`.
- **Test data:** As above.
- **Expected:** B → `200`, both rows, E then F, each `{"id", "event_id", "attendee_id", "created_at"}`. The query is on `registrations.waiting_list`, filtered `attendee_id = B`, ordered by `created_at`. A → `200` `[]` (not a 404).
- **Actual:** B → `200`, E's row then F's, queried on `waiting_list` by `attendee_id` ordered by `created_at`; A → `200` `[]`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_an_attendees_waiting_list_entries; 2026-10-26, branch `S-52/join-waiting-list` (on S-50 `a3011b3`), pre-commit working tree

## TC-REGISTRATIONS-015 — an event's waiting list is first-come, first-served

- **Scenario:** The waiting list is returned in the order people joined, with a fixed tie-break (S-52 AC2).
- **Pre-conditions:** The fake returns B's and C's rows for E.
- **Steps:** `GET /registrations/waiting-list/events/E`.
- **Test data:** As above.
- **Expected:** `200` with both rows in the order the fake returned them. The query is filtered `event_id = E` and ordered by `created_at` and then by `id`, both ascending.
- **Actual:** `200` with both rows; ordered by `created_at` then `id`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_an_events_waiting_list_is_first_come_first_served; 2026-10-26, branch `S-52/join-waiting-list` (on S-50 `a3011b3`), pre-commit working tree

## S-53 — Withdraw Registration

Developer decisions (2026-10-26): withdrawing removes the place, so the
Attendee is back to not registered and may register again. In the same
locked step as the removal, the first Attendee on the waiting list (first
come, first served: `created_at`, then `id`) takes the freed place. Someone is
promoted only while a place is genuinely free (places taken after the
withdrawal < `capacity`), and at most one per withdrawal. The withdrawal and the
promotion run in `registrations.withdraw` under the same per-event lock as
`registrations.register`. A missing place raises `SP053`.

## TC-REGISTRATIONS-016 — an Attendee withdraws and no one is waiting

- **Scenario:** A withdrawal removes the place and reports that no one was promoted (S-53 AC1, AC2).
- **Pre-conditions:** `rpc("withdraw", ...)` returns `{"withdrawn": <A's row for E>, "promoted": null}`.
- **Steps:** `POST /registrations/withdrawals`.
- **Test data:** `{"event_id": E, "attendee_id": A, "capacity": 2}`; A's row `created_at` `2026-11-05T04:00:00+00:00`.
- **Expected:** `200` `{"withdrawn": {"id", "event_id": E, "attendee_id": A, "created_at"}, "promoted": null}`. The call is `schema("registrations").rpc("withdraw", {"p_event_id": E, "p_attendee_id": A, "p_capacity": 2})`; no table is written to directly.
- **Actual:** `200` with A's row and `promoted` null; one `rpc("withdraw", {p_event_id: E, p_attendee_id: A, p_capacity: 2})` on `registrations`; no table call.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_an_attendee_withdraws_and_no_one_is_waiting; 2026-10-26, branch `S-53/withdraw-registration` (on S-52 + S-49 `fde7b1f`), pre-commit working tree

## TC-REGISTRATIONS-017 — the freed place goes to the next Attendee waiting

- **Scenario:** The withdrawal answers with the Attendee who was promoted into the freed place (S-53 AC3, AC4).
- **Pre-conditions:** `rpc("withdraw", ...)` returns `{"withdrawn": <A's row>, "promoted": <B's new row for E, created_at 2026-11-06T04:00:00+00:00>}`.
- **Steps:** `POST /registrations/withdrawals`.
- **Test data:** As TC-REGISTRATIONS-016.
- **Expected:** `200` with `withdrawn` A's row and `promoted` `{"id", "event_id": E, "attendee_id": B, "created_at": "2026-11-06T04:00:00Z"}`.
- **Actual:** `200`; `withdrawn` A's row, `promoted` B's row with `created_at` `2026-11-06T04:00:00Z`.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_the_freed_place_goes_to_the_next_attendee_waiting; 2026-10-26, branch `S-53/withdraw-registration` (on S-52 + S-49 `fde7b1f`), pre-commit working tree

## TC-REGISTRATIONS-018 — withdrawing a place that isn't held

- **Scenario:** Withdrawing without a place is refused, not silently accepted (S-53 AC1).
- **Pre-conditions:** `rpc("withdraw", ...)` raises `APIError` with code `SP053`.
- **Steps:** `POST /registrations/withdrawals`.
- **Test data:** `{"event_id": E, "attendee_id": B, "capacity": 2}`.
- **Expected:** `404` `{"detail": "You're not registered for this event."}`.
- **Actual:** `404` "You're not registered for this event."
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_withdrawing_a_place_that_isnt_held; 2026-10-26, branch `S-53/withdraw-registration` (on S-52 + S-49 `fde7b1f`), pre-commit working tree

## TC-REGISTRATIONS-019 — a malformed withdrawal, or storage failing

- **Scenario:** Bad input is refused before storage is touched, and a storage error doesn't pass as success.
- **Pre-conditions:** For the last row, `rpc` raises `APIError` code `XX000`.
- **Steps:** `POST /registrations/withdrawals` with each body.
- **Test data / Expected:**
  | Body | Result |
  | --- | --- |
  | `{"event_id": E, "attendee_id": A}` (no capacity) | `422`, `errors.capacity` set; rpc not called |
  | `{"event_id": E, "attendee_id": A, "capacity": -1}` | `422`, `errors.capacity` set; rpc not called |
  | `{"event_id": "nope", "attendee_id": A, "capacity": 2}` | `422`, `errors.event_id` set; rpc not called |
  | `{"event_id": E, "attendee_id": A, "capacity": 2, "x": 1}` | `422`, `errors.x` set; rpc not called |
  | `{"event_id": E, "attendee_id": A, "capacity": 0}` | Accepted (`0` means no place is free, so no one is promoted) |
  | Valid body, storage raises `XX000` | `500` `{"detail": "Registration storage unavailable"}` |
- **Actual:** All four malformed bodies `422` with the named field, rpc not called; capacity `0` accepted with `p_capacity` 0; storage error `500` "Registration storage unavailable".
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_a_malformed_withdrawal_is_refused, ::test_a_withdrawal_with_no_free_place_is_accepted, ::test_a_withdrawal_storage_cant_record; 2026-10-26, branch `S-53/withdraw-registration` (on S-52 + S-49 `fde7b1f`), pre-commit working tree
