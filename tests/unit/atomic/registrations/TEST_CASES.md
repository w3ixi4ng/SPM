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

- **Scenario:** A withdrawal removes the place and reports that no one was offered it (S-53 AC1, AC2). Amended by S-55 (2026-10-30): the key is `offered`, which was `promoted`.
- **Pre-conditions:** `rpc("withdraw", ...)` returns `{"withdrawn": <A's row for E>, "offered": null}`.
- **Steps:** `POST /registrations/withdrawals`.
- **Test data:** `{"event_id": E, "attendee_id": A, "capacity": 2}`; A's row `created_at` `2026-11-05T04:00:00+00:00`.
- **Expected:** `200` `{"withdrawn": {"id", "event_id": E, "attendee_id": A, "created_at"}, "offered": null}`. The call is `schema("registrations").rpc("withdraw", {"p_event_id": E, "p_attendee_id": A, "p_capacity": 2})`; no table is written to directly.
- **Actual:** `200` with A's row and `offered` null; one `rpc("withdraw", {p_event_id: E, p_attendee_id: A, p_capacity: 2})` on `registrations`; no table call.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_an_attendee_withdraws_and_no_one_is_waiting; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-REGISTRATIONS-017 — the freed place goes to the next Attendee waiting

> **Retired by S-55 (2026-10-30).** A freed place is now offered, not given. See TC-REGISTRATIONS-020. The record below is S-53's last run.

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
  | `{"event_id": E, "attendee_id": A, "capacity": 0}` | Accepted (`0` means no place is free, so no one is offered it; S-55 wording) |
  | Valid body, storage raises `XX000` | `500` `{"detail": "Registration storage unavailable"}` |
- **Actual:** All four malformed bodies `422` with the named field, rpc not called; capacity `0` accepted with `p_capacity` 0; storage error `500` "Registration storage unavailable".
- **Status:** Pass
- **Evidence:** tests/unit/atomic/registrations/test_app.py::test_a_malformed_withdrawal_is_refused, ::test_a_withdrawal_with_no_free_place_is_accepted, ::test_a_withdrawal_storage_cant_record; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## S-55 — Notify Waitlisted Attendee of Opening

Developer decisions (2026-10-30): a freed place is **offered**, never given.
This replaces S-53's automatic promotion. A withdrawal, or a decline, marks the first
Attendee on the waiting list who has no offer yet (first come, first served:
`created_at`, then `id`) with `offered_at`. That Attendee stays on the waiting
list, and the offer counts as a taken place: `registrations.register` counts
places held **plus** open offers against `capacity`, so no one else can take
it. Only the invited Attendee's own action registers them
(`registrations.accept_offer`), or passes the place on
(`registrations.decline_offer`, which also removes them from the waiting list).
There is no expiry. An offer is made only while places held + open offers <
`capacity`, and at most one per freed place. All four functions take the same
per-event lock. Having no open offer raises `SP055`.

`POST /registrations/withdrawals` now answers `{"withdrawn", "offered"}` in
place of `{"withdrawn", "promoted"}`. TC-REGISTRATIONS-016 and -019 are amended
to that key, and TC-REGISTRATIONS-017 is retired in favour of
TC-REGISTRATIONS-020.

Attendee B is `44444444-4444-4444-8444-444444444444` (first in line), C is
`55555555-5555-4555-8555-555555555555` (second). B's waiting-list row id is
`77777777-7777-4777-8777-777777777777`, joined `2026-11-04T04:00:00+00:00`.

## TC-REGISTRATIONS-020 — a withdrawal offers the freed place to the next in line

- **Scenario:** The withdrawal answers with the waiting-list entry that was offered the place. Nobody is registered on their behalf (S-55 AC1, AC2).
- **Pre-conditions:** `rpc("withdraw", ...)` returns `{"withdrawn": <A's row for E>, "offered": <B's waiting-list row, offered_at 2026-11-06T04:00:00+00:00>}`.
- **Steps:** `POST /registrations/withdrawals`.
- **Test data:** `{"event_id": E, "attendee_id": A, "capacity": 2}`.
- **Expected:** `200` with `withdrawn` A's row and `offered` `{"id": "7777…7777", "event_id": E, "attendee_id": B, "created_at": "2026-11-04T04:00:00Z", "offered_at": "2026-11-06T04:00:00Z"}`. The body has no `promoted` key.
- **Actual:** `200`; `withdrawn` A's row, `offered` B's entry with `created_at` `2026-11-04T04:00:00Z` and `offered_at` `2026-11-06T04:00:00Z`; no `promoted` key.
- **Status:** Pass
- **Evidence:** test_app.py::test_a_withdrawal_offers_the_freed_place_to_the_next_in_line; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-REGISTRATIONS-021 — the invited Attendee accepts the place

- **Scenario:** Accepting turns B's offer into a place, through one locked database call (S-55 AC2: registration happens only on B's action).
- **Pre-conditions:** `rpc("accept_offer", ...)` returns B's new registration row for E, `created_at` `2026-11-07T04:00:00+00:00`.
- **Steps:** `POST /registrations/offers/acceptances`.
- **Test data:** `{"event_id": E, "attendee_id": B}`.
- **Expected:** `201` `{"id", "event_id": E, "attendee_id": B, "created_at": "2026-11-07T04:00:00Z"}`. The call is `schema("registrations").rpc("accept_offer", {"p_event_id": E, "p_attendee_id": B})`. No table is written to directly.
- **Actual:** `201` with B's place, `created_at` `2026-11-07T04:00:00Z`; one `rpc("accept_offer", {p_event_id: E, p_attendee_id: B})`; no table call.
- **Status:** Pass
- **Evidence:** test_app.py::test_the_invited_attendee_accepts_the_place; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-REGISTRATIONS-022 — accepting without an open offer

- **Scenario:** Only the Attendee holding the offer can take the place: someone further down the line, or not waiting at all, is refused (S-55 AC1).
- **Pre-conditions:** `rpc("accept_offer", ...)` raises `APIError` with code `SP055`.
- **Steps:** `POST /registrations/offers/acceptances`.
- **Test data:** `{"event_id": E, "attendee_id": C}`.
- **Expected:** `404` `{"detail": "You don't have a place on offer for this event."}`.
- **Actual:** `404` "You don't have a place on offer for this event."
- **Status:** Pass
- **Evidence:** test_app.py::test_accepting_without_an_open_offer; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-REGISTRATIONS-023 — declining passes the place to the next in line

- **Scenario:** Declining removes B from the waiting list and, in the same step, offers the place to the next Attendee waiting, if there is one (S-55 AC1).
- **Pre-conditions:** `rpc("decline_offer", ...)` returns, per row below.
- **Steps:** `POST /registrations/offers/declines`.
- **Test data / Expected:** Body `{"event_id": E, "attendee_id": B, "capacity": 2}`. The call is `schema("registrations").rpc("decline_offer", {"p_event_id": E, "p_attendee_id": B, "p_capacity": 2})`.
  | rpc returns | Result |
  | --- | --- |
  | `{"declined": <B's row>, "offered": <C's row, offered_at 2026-11-07T04:00:00+00:00>}` | `200`, `declined.attendee_id` B, `offered.attendee_id` C, `offered.offered_at` `"2026-11-07T04:00:00Z"` |
  | `{"declined": <B's row>, "offered": null}` (no one else waiting) | `200`, `declined.attendee_id` B, `offered` `null` |
- **Actual:** C offered: `200`, declined B, offered C at `2026-11-07T04:00:00Z`; no one else: `200`, declined B, offered `null`; one `rpc("decline_offer", {E, B, capacity 2})`.
- **Status:** Pass
- **Evidence:** test_app.py::test_declining_passes_the_place_to_the_next_in_line, ::test_declining_with_no_one_else_waiting; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-REGISTRATIONS-024 — declining without an open offer

- **Scenario:** An Attendee who wasn't offered a place can't "decline" it, so they don't drop off the waiting list by accident.
- **Pre-conditions:** `rpc("decline_offer", ...)` raises `APIError` with code `SP055`.
- **Steps:** `POST /registrations/offers/declines`.
- **Test data:** `{"event_id": E, "attendee_id": C, "capacity": 2}`.
- **Expected:** `404` `{"detail": "You don't have a place on offer for this event."}`.
- **Actual:** `404` "You don't have a place on offer for this event."
- **Status:** Pass
- **Evidence:** test_app.py::test_declining_without_an_open_offer; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-REGISTRATIONS-025 — a malformed accept or decline, or storage failing

- **Scenario:** Bad input is refused before storage is touched, and a storage error doesn't pass as success.
- **Pre-conditions:** For the storage rows, `rpc` raises `APIError` code `XX000`.
- **Steps:** Send each body to the route named.
- **Test data / Expected:**
  | Route | Body | Result |
  | --- | --- | --- |
  | acceptances | `{"event_id": "nope", "attendee_id": B}` | `422`, `errors.event_id` set; rpc not called |
  | acceptances | `{"event_id": E, "attendee_id": B, "x": 1}` | `422`, `errors.x` set; rpc not called |
  | declines | `{"event_id": E, "attendee_id": B}` (no capacity) | `422`, `errors.capacity` set; rpc not called |
  | declines | `{"event_id": E, "attendee_id": B, "capacity": -1}` | `422`, `errors.capacity` set; rpc not called |
  | declines | `{"event_id": E, "attendee_id": B, "capacity": 0}` | Accepted (`0` offers no one) |
  | acceptances | valid, storage raises `XX000` | `500` `{"detail": "Registration storage unavailable"}` |
  | declines | valid, storage raises `XX000` | `500` `{"detail": "Registration storage unavailable"}` |
- **Actual:** All four malformed bodies `422` with the named field, rpc not called; capacity `0` accepted; both storage errors `500` "Registration storage unavailable".
- **Status:** Pass
- **Evidence:** test_app.py::test_a_malformed_accept_or_decline_is_refused, ::test_a_decline_with_no_free_place_is_accepted, ::test_an_accept_or_decline_storage_cant_record; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## TC-REGISTRATIONS-026 — waiting-list reads say who holds an offer

- **Scenario:** Every waiting-list read carries `offered_at`, so the composite can tell an invited Attendee from one still waiting, and count the held place as taken.
- **Pre-conditions:** The table fake returns B's row with `offered_at` `2026-11-06T04:00:00+00:00` and C's row with `offered_at` `null`.
- **Steps:** `GET /registrations/waiting-list/events/E`; `GET /registrations/waiting-list/attendees/B`; `GET /registrations/waiting-list/events/E/attendees/C`.
- **Test data:** As above.
- **Expected:** The list is `200` `[B's row with "offered_at": "2026-11-06T04:00:00Z", C's row with "offered_at": null]`, still in `created_at`, `id` order. B's list is `200` with B's row, `offered_at` set. C's entry is `200` with `offered_at` `null`.
- **Actual:** Event list `200` in order B, C with `offered_at` set then `null`; B's list carries `offered_at`; C's entry `offered_at` `null`.
- **Status:** Pass
- **Evidence:** test_app.py::test_waiting_list_reads_say_who_holds_an_offer; 2026-10-30, branch `S-55/notify-waitlisted-attendee-of-opening` (on sprint4 `44701d3`), pre-commit working tree

## S-58 — View My Registration Status

Developer decisions (2026-10-30): a withdrawal is now **recorded**, not just a
deleted place. S-53's withdrawal and S-55's decline both write the Attendee's
row in the new `registrations.withdrawals` table, in the same locked step that
frees the place. There is one row per `(event_id, attendee_id)`, and a later
withdrawal from the same event replaces its `withdrawn_at`. The composite
reads these rows to list the event as "Withdrawn" on the dashboard.
Withdrawals made before the S-58 SQL was applied were never recorded and
cannot appear.

## TC-REGISTRATIONS-027 — an Attendee's withdrawals are listed

- **Scenario:** The service lists every event an Attendee has withdrawn from, with when, so the composite can show "Withdrawn" (S-58 AC1).
- **Pre-conditions:** The table fake for `registrations.withdrawals` returns A's row `{"id": W, "event_id": E, "attendee_id": A, "withdrawn_at": "2026-10-28T02:15:00+00:00"}`.
- **Steps:** `GET /registrations/withdrawals/attendees/A`. Repeat with the fake returning `[]`, then with `.execute()` raising. Then `GET /registrations/withdrawals/attendees/not-a-uuid`.
- **Test data:** A, E, W random uuids.
- **Expected:** `200` `[{"id": W, "event_id": E, "attendee_id": A, "withdrawn_at": "2026-10-28T02:15:00Z"}]`, read from schema `registrations`, table `withdrawals`, filtered `attendee_id = A`, ordered by `withdrawn_at`. Empty → `200` `[]` (an answer, not a 404). Raising → `500` `"Registration storage unavailable"`. Not a uuid → `422`.
- **Actual:** `200` with A's row, `withdrawn_at` "2026-10-28T02:15:00Z", read from `registrations.withdrawals` filtered by `attendee_id`, ordered by `withdrawn_at`; empty `200` `[]`; raising `500` "Registration storage unavailable"; bad id `422`.
- **Status:** Pass
- **Evidence:** test_app.py::test_an_attendees_withdrawals_are_listed; 2026-10-31, branch `S-58/view-my-registration-status` (on sprint4 `b8830b4`), pre-commit working tree
