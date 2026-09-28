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
