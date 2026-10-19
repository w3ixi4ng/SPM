# Test cases — equipment_requirements composite (unit)

Story: S-40 Record Required Equipment.

These cases were confirmed before implementation. All downstream HTTP
services are mocked; they specify the authorization and orchestration boundary.

| | |
| --- | --- |
| Suite | `pytest tests/unit/composite/equipment_requirements` |
| Last run | 2026-09-27, branch `S-40/record-required-equipment`, pre-commit working tree |
| Environment | Unit test environment; users, events, and equipment mocked |
| Result | 48 passed |

Shared data: event `eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee`, equipment item
`22222222-2222-4222-8222-222222222222`, assigned Coordinator
`cccccccc-cccc-4ccc-8ccc-cccccccccccc`, and quantity `6`.

## TC-EQUIPMENTREQUIREMENTS-001 — health has no dependencies

- **Pre-conditions:** No downstream service is available.
- **Steps:** Read `/health` and `/equipment-requirements/health`.
- **Expected:** Both return `200 {"status":"ok"}` without a downstream call.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

## TC-EQUIPMENTREQUIREMENTS-002 — assigned Coordinator records a planning requirement

- **Pre-conditions:** Users identifies the caller as the shared Coordinator;
  Events returns the shared event as assigned to them with `status=planning`;
  Equipment accepts the write.
- **Steps:** `PUT /equipment-requirements/{event}/{item}` with quantity `6`.
- **Expected:** `200`; Equipment receives event id, item id, quantity, and
  `recorded_by_coordinator_id` from the verified user, never from the browser.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

## TC-EQUIPMENTREQUIREMENTS-003 — recording the same item edits rather than duplicates

- **Pre-conditions:** The requirement already exists at quantity `6`; the
  current caller is still the assigned Coordinator and the event is planning.
- **Steps:** Put quantity `9` for the same event and item.
- **Expected:** `200`; the same relationship id is returned with quantity `9`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

## TC-EQUIPMENTREQUIREMENTS-004 — every non-planning status is immutable

- **Pre-conditions:** Caller is the assigned Coordinator; Events returns each
  tested status in turn.
- **Steps:** Try both PUT and DELETE for each status.
- **Test data:** `draft`, `submitted`, `returned`, `rejected`, `confirmed`,
  `completed`, `cancelled`, and unknown `made_up_status`.
- **Expected:** Every attempt returns `409`; Equipment receives no mutation.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

## TC-EQUIPMENTREQUIREMENTS-005 — assignment is checked on every mutation

- **Pre-conditions:** A row's audit field names the former Coordinator; Events
  has reassigned the event to a new Coordinator.
- **Steps:** Former Coordinator tries PUT and DELETE; new Coordinator then PUTs.
- **Expected:** Former Coordinator receives `404` from the assigned-event
  check and Equipment is untouched. New Coordinator succeeds and becomes the
  new `recorded_by_coordinator_id`. The stored audit value is never consulted
  for authorization.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

## TC-EQUIPMENTREQUIREMENTS-006 — only a Coordinator mutates requirements

- **Pre-conditions:** Users returns each other supported role.
- **Steps:** Try PUT and DELETE.
- **Test data:** Event Organiser, Technical Support, Venue Staff, Attendee,
  missing role, and unknown role.
- **Expected:** Recognized non-Coordinators receive `403`; missing/unknown
  roles fail closed; Events and Equipment receive no call.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

## TC-EQUIPMENTREQUIREMENTS-007 — quantity input fails before orchestration

- **Pre-conditions:** None.
- **Steps:** PUT missing quantity, `0`, `-1`, `1.5`, an unknown field, and a
  browser-supplied `recorded_by_coordinator_id`.
- **Expected:** Each returns `422`; no downstream service is called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

## TC-EQUIPMENTREQUIREMENTS-008 — Coordinator reads their assigned event requirements

- **Pre-conditions:** Events confirms the event is currently assigned to the
  caller; Equipment returns its requirements with catalogue details.
- **Steps:** `GET /equipment-requirements?event_id={event}`.
- **Expected:** `200` with the Equipment response. Read access is not limited
  to planning, but assignment is checked at request time.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

## TC-EQUIPMENTREQUIREMENTS-009 — Technical Support reads requirements without editing

- **Pre-conditions:** Users identifies Technical Support; Equipment returns
  requirements.
- **Steps:** GET all requirements, then GET filtered by event; try PUT/DELETE.
- **Expected:** Both reads return `200`; no Events call is needed. Mutations
  return `403` and never reach Equipment.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

## TC-EQUIPMENTREQUIREMENTS-010 — other roles cannot read requirements

- **Pre-conditions:** Users returns Event Organiser, Venue Staff, or Attendee.
- **Steps:** GET requirements.
- **Expected:** `403`; Events and Equipment receive no call.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

## TC-EQUIPMENTREQUIREMENTS-011 — missing assignment and downstream failures are safe

- **Pre-conditions:** In turn: Events returns `404`; Users, Events, or
  Equipment raises/returns an unavailable response.
- **Steps:** Read or mutate a requirement.
- **Expected:** An unassigned/wrong-Coordinator event is `404`; dependency
  failures return a named `502` without internal details.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py`

---

## S-44 — check equipment availability

Story: S-44 Check equipment availability.
Confirmed by the developer on 2026-09-30. Not yet executed.

**Acceptance criteria → cases (all layers)**

| Acceptance criterion | Cases |
| --- | --- |
| AC1: Technical Support can check whether enough of an equipment type is available for a date/time, using filters | EQUIPMENTREQUIREMENTS-012, 015, 016, 017, 018, FRONTEND-074–077, E2E-222 |
| AC2: Equipment reserved or marked unavailable for an overlapping period is left out of the available count | EVENTS-105, 106, EQUIPMENT-030, EQUIPMENTREQUIREMENTS-012–014, 103, FRONTEND-075 |
| AC3: The check reflects real-time reservation data at the time it is performed | EQUIPMENTREQUIREMENTS-019, 103, FRONTEND-078, E2E-222 |

The conditions agreed with the developer on 2026-09-30:

- **Reserved** means equipment requirements on events in `planning` or
  `confirmed` whose start–end overlaps the window checked. A requirement has
  no time of its own; its time is its event's. Rejected, returned, draft and
  submitted events reserve nothing.
- **Unavailable** means the existing pool-wide `operational_status`: an item
  that is `unavailable` or `maintenance` has 0 available for any window.
  Retired items are left out of the check entirely. There are no dated or
  partial unavailability periods.
- **Filters:** a start date/time and an end date/time (required; the window may
  span days, like events), an optional equipment-type search, and an optional
  quantity needed. Every active item matching the search shows total,
  reserved, unavailable and available; with a quantity, each also says
  whether that is enough.
- Each item lists the overlapping events holding it (name, start–end, status,
  quantity), which Technical Support can already see as requirements.
- **Technical Support only.**
- **Real-time:** every check reads the live catalogue, events and
  requirements; nothing is cached. The result carries the time it was checked.
- Also proposed here, for confirmation:
  - Overlap follows the existing `_windows_overlap` rule: a window ending
    exactly when another starts is **not** an overlap.
  - Available never goes below 0. If requirements exceed a pool (nothing stops
    Coordinators over-recording today), available is 0 and the item is marked
    `over_reserved`.
  - The type search is a case-insensitive "contains" match.
  - The page's date pickers start at **today** (unlike S-30's tomorrow), since
    checking for an event happening today is a real need. The API itself
    accepts any window, as no service enforces "future only".

**Shared test data.** Window `2026-11-12 09:00` → `2026-11-12 12:00`.
Items: **Wireless Microphone** (`available`, active, total 12); **Projector**
(`maintenance`, active, total 4); **Old Speaker** (retired, total 6).
Overlapping events returned by the events service: E1 `planning`
`2026-11-12 10:00–11:00`, needs 5 microphones; E2 `confirmed`
`2026-11-12 11:30–13:00`, needs 3 microphones; E5 `planning`
`2026-11-11 18:00` → `2026-11-12 09:30`, needs 2 microphones and 1 projector.

## TC-EQUIPMENTREQUIREMENTS-012 — availability counts reserved and unavailable units for the window

- **Scenario:** The core check (AC1, AC2).
- **Pre-conditions:** Users returns `technical_support`. Events
  `POST /events/overlapping` returns E1, E2, E5. Equipment `GET /equipment`
  returns the three items; `GET /internal/equipment-requirements?event_ids=…`
  returns the E1, E2, E5 requirements.
- **Steps:** `GET /equipment-requirements/availability?start_date=2026-11-12&start_time=09:00&end_date=2026-11-12&end_time=12:00`.
- **Expected:** `200` with `checked_at` (server time, ISO 8601), the window
  echoed back, `quantity: null`, and `items` in type order:
  - Projector: `total 4, reserved 1, unavailable 4, available 0, over_reserved false`
  - Wireless Microphone: `total 12, reserved 10, unavailable 0, available 2, over_reserved false`

  Old Speaker (retired) is absent. Each item has `sufficient: null` and a
  `reservations` list: for the microphone, E5 (2), E1 (5), E2 (3) in start
  order, each with `event_id`, `event_name`, `status`, start/end date and
  time, and `required_quantity`.
- **Actual:** Projector 4/1/4/0 and microphone 12/10/0/2 as specified; retired speaker absent; microphone reservations E5 (2), E1 (5), E2 (3); window echoed; overlapping events requested by `event_ids`; catalogue read with the caller's cookies.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/equipment_requirements/test_availability.py::test_availability_counts_reserved_and_unavailable_units_for_the_window`

## TC-EQUIPMENTREQUIREMENTS-013 — a quantity says whether each item is enough

- **Scenario:** Confirm sufficiency (AC1).
- **Pre-conditions:** As TC-EQUIPMENTREQUIREMENTS-012.
- **Steps:** Repeat with `quantity=2`, then `quantity=3`.
- **Expected:** With 2, the microphone is `sufficient: true` and the projector
  `false`. With 3, both are `false`. `quantity` is echoed back.
- **Actual:** Quantity 2: microphone enough, projector not. Quantity 3: neither.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/equipment_requirements/test_availability.py::test_a_quantity_says_whether_each_item_is_enough`

## TC-EQUIPMENTREQUIREMENTS-014 — over-reserved pools show 0, never a negative

- **Scenario:** Requirements exceeding a pool (AC2).
- **Pre-conditions:** As TC-EQUIPMENTREQUIREMENTS-012, but E1 needs 9
  microphones (reserved 14 of 12).
- **Expected:** Microphone `reserved 14, available 0, over_reserved true`.
- **Actual:** Microphone reserved 14, available 0, over_reserved true.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/equipment_requirements/test_availability.py::test_over_reserved_pools_show_zero_never_a_negative`

## TC-EQUIPMENTREQUIREMENTS-015 — the type search narrows the items

- **Scenario:** Filter by equipment type (AC1).
- **Steps:** Repeat TC-EQUIPMENTREQUIREMENTS-012 with `type=MICRO`, then
  `type=  ` (blank), then `type=drum`.
- **Expected:** `MICRO` returns only Wireless Microphone. Blank is ignored and
  returns both active items. `drum` returns `items: []` with `200`.
- **Actual:** `MICRO` gave only the microphone; blank gave both active items; `drum` gave `[]` with `200`.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/equipment_requirements/test_availability.py::test_the_type_search_narrows_the_items`

## TC-EQUIPMENTREQUIREMENTS-016 — no overlapping events means nothing is reserved

- **Scenario:** A free window (AC1, AC2).
- **Pre-conditions:** Events returns `[]`.
- **Expected:** `200`; microphone `reserved 0, available 12`; projector
  `available 0` (maintenance). Equipment requirements are **not** requested,
  since there are no events to ask about.
- **Actual:** Microphone 0 reserved, 12 available; projector 0; requirements were not requested.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/equipment_requirements/test_availability.py::test_no_overlapping_events_means_nothing_is_reserved`

## TC-EQUIPMENTREQUIREMENTS-017 — only Technical Support can check, and the window is validated

- **Scenario:** Role and input checks before any data is read (AC1).
- **Steps / Expected:**
  - `event_coordinator`, `event_organiser`, `venue_staff` → `403`
    `{"detail":"Permission denied"}`; no session → `401`
    `{"detail":"Not authenticated"}`. Events and Equipment are never called.
  - Missing `start_date`, `start_time`, `end_date` or `end_time`, or a
    malformed one → `422` naming the field.
  - End not after start (e.g. `12:00` → `12:00` on one date, or an end date
    before the start date) → `422`, `errors.end_time` "The end must be after
    the start".
  - `quantity=0`, `-1` or `two` → `422` naming `quantity`.
  - No `422` calls Events or Equipment.
- **Actual:** Other roles `403`, no session `401`; missing, malformed and zero/negative/non-numeric quantity `422` naming the field; end not after start `422` on `end_time`; no downstream call in any of them.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/equipment_requirements/test_availability.py::test_only_technical_support_can_check`; `tests/unit/composite/equipment_requirements/test_availability.py::test_no_session_cannot_check`; `tests/unit/composite/equipment_requirements/test_availability.py::test_a_malformed_check_is_refused_naming_the_field`; `tests/unit/composite/equipment_requirements/test_availability.py::test_the_end_must_be_after_the_start`

## TC-EQUIPMENTREQUIREMENTS-018 — a failing dependency is never an answer

- **Scenario:** A failure must not read as "all available" (AC1, AC3).
- **Steps / Expected:** Events, Equipment catalogue or Equipment requirements
  fails to connect, times out or returns `500` → `502`
  `{"detail":"<Events|Equipment> service unavailable"}`; never `200`.
- **Actual:** Connection failures and `500`s from events, the catalogue and the requirements each returned the named `502`.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/equipment_requirements/test_availability.py::test_a_failing_dependency_is_never_an_answer`

## TC-EQUIPMENTREQUIREMENTS-019 — every check reads live data

- **Scenario:** Nothing is cached (AC3).
- **Steps:** Run the same check twice; between them, the Equipment fake adds a
  4-microphone requirement to E1.
- **Expected:** Both checks call Events and Equipment afresh. The second
  shows microphone `reserved 14, available 0`, and a later `checked_at`.
- **Actual:** The second check read the changed requirement (reserved 14, available 0) with a later-or-equal `checked_at`.
- **Status:** Pass
- **Evidence:** `tests/unit/composite/equipment_requirements/test_availability.py::test_every_check_reads_live_data`

---

## S-43 — requirements follow the Technical Support assignment

Story: S-43 Auto-Assign Technical Support.
Specification updated by the developer on 2026-10-05.

## TC-EQUIPMENTREQUIREMENTS-020 — Technical Support lists requirements only for assigned active events

- **Scenario:** The dashboard requirements list cannot expose another staff
  member's work.
- **Pre-conditions:** Users identifies Technical Support A. Events returns A's
  two active assigned events. Equipment contains requirements for those two
  events plus another staff member's event.
- **Steps:** `GET /equipment-requirements` without `event_id`.
- **Test data:** Assigned event IDs A1 and A2; unrelated event B1; one
  requirement on each.
- **Expected:** The composite asks Events for A's authenticated active
  assignments, then asks Equipment with only `event_ids=A1&event_ids=A2`.
  `200` contains A1 and A2 requirements only. No browser-supplied staff ID is
  accepted or trusted.
- **Actual:** The composite read the authenticated support assignments and
  called Equipment once with repeated `event_ids` for A1 and A2 only; the
  returned list contained no B1 requirement.
- **Status:** Pass
- **Evidence:** `test_app.py::test_support_lists_only_requirements_for_its_active_assignments`

## TC-EQUIPMENTREQUIREMENTS-021 — an empty assignment list returns no requirements

- **Scenario:** No assigned events means no equipment responsibility, not a
  fallback to all requirements.
- **Pre-conditions:** Users identifies Technical Support A; Events returns no
  active assigned events.
- **Steps:** `GET /equipment-requirements`.
- **Test data:** Equipment storage may contain unrelated requirements.
- **Expected:** `200 []`; Equipment's internal requirements endpoint is not
  called, so unrelated rows cannot leak.
- **Actual:** An empty Events response produced `200 []` and the Equipment
  client recorded no request.
- **Status:** Pass
- **Evidence:** `test_app.py::test_support_with_no_active_assignments_gets_empty_requirements`

## TC-EQUIPMENTREQUIREMENTS-022 — a support worker cannot select an unrelated event

- **Scenario:** Adding `event_id` to the URL cannot bypass assignment
  filtering.
- **Pre-conditions:** Event A is active and assigned to Technical Support A;
  Event B belongs to B; Event C is A's inactive event.
- **Steps:** As A, request requirements for A, B, and C individually.
- **Test data:** `?event_id=A`, `?event_id=B`, `?event_id=C`.
- **Expected:** A returns only A's requirements. B and C return `404`, and
  Equipment is not queried for either denied event. Existing Coordinator
  assignment checks and edit behavior remain unchanged.
- **Actual:** The assigned event returned its requirements. Both an event
  assigned to someone else and an inactive assignment returned `404` before
  the Equipment client was called.
- **Status:** Pass
- **Evidence:** `test_app.py::test_support_can_list_one_assigned_event`; `test_app.py::test_support_cannot_select_unassigned_or_inactive_event`

---

## S-18 — significant equipment-requirement edits

Story: S-18 Update Event Information. Specification confirmed by the
developer on 2026-10-19. Equipment owns requirement rows and their edit audit;
S-82 can later combine this history with Events-owned history.

## TC-EQUIPMENTREQUIREMENTS-023 — equipment requirement changes require accepted impact review and audit

- **Scenario:** Adding, changing, or removing required equipment is a
  significant event change and cannot bypass impact review.
- **Pre-conditions:** Coordinator A is assigned to planning event E. E has one
  requirement for two microphones.
- **Steps:** Add a projector, change microphones from 2 to 4, and remove the
  projector; first omit impact acceptance and then accept it. Repeat as an
  unassigned Coordinator and after E changes concurrently.
- **Expected:** Every real mutation first returns a server-derived impact
  summary without changing Equipment. Accepted mutations save immediately and
  append a service-owned audit entry containing item/quantity before and
  after, A's authenticated UUID, and server time. A same-quantity no-op creates
  no history. Unassigned access is `404`; stale state is `409`; dependency or
  storage failure never leaves a requirement change without its audit entry.
  Browser-supplied significance, actor, time, or history is rejected.
- **Actual:** Missing acceptance was rejected before mutation; accepted writes
  used only the atomic audited routes with the authenticated Coordinator id.
  Atomic tests proved each mutation is delegated to one database function.
- **Status:** Pass
- **Evidence:** `test_app.py::test_requirement_changes_require_accepted_impact`; `tests/unit/atomic/equipment/test_s18.py`; focused Python run, 377 passed, 2026-10-19.
