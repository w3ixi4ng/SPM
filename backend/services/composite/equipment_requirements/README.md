# Equipment requirements service

Composite service for S-40, the S-43 Technical Support visibility flow and
S-17 Technical Support sign-off. It
verifies the signed-in user with `users`, asks `events` for the caller's
current assignment, then reads or stores requirements through the `equipment`
atomic service. It owns no database.

## Endpoints

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | Public | Process health check. |
| `GET` | `/equipment-requirements?event_id=<uuid>` | Coordinator, Technical Support | List requirements. Coordinators must supply their assigned planning event. Technical Support may supply one of their active assigned events, or omit it to list requirements across all of their active assigned events. |
| `PUT` | `/equipment-requirements/{event_id}/{equipment_item_id}` | Coordinator | Create or replace a quantity after accepting its impact while the assigned event is in planning. Clears the S-17 sign-off first. |
| `DELETE` | `/equipment-requirements/{event_id}/{equipment_item_id}?impact_accepted=true` | Coordinator | Remove a requirement after accepting its impact while the assigned event is in planning. Clears the S-17 sign-off first. |
| `POST` | `/equipment-requirements/{event_id}/sign-off` | Technical Support | S-17: approve or decline the event's equipment arrangements. See [Sign-off](#sign-off-s-17). |
| `GET` | `/equipment-requirements/availability` | Technical Support | S-44: how many of each active item are free for a window. See [Availability check](#availability-check-s-44). |

## Request

`PUT` accepts exactly:

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `required_quantity` | integer | Yes | Positive whole number. |
| `impact_accepted` | boolean | Yes for a write | Must be `true`; confirms the Coordinator reviewed the significant equipment impact. |

The service derives `recorded_by_coordinator_id` from the verified session.
That field is audit information only: every authorization decision asks the
events service for the event's current assignment.

For Technical Support, the service never trusts a staff id from the browser.
It obtains the authenticated user's active (`planning`, `pending_safety_check`,
`confirmed`, `preparation`) assignments
from `/events/support-assigned`, then passes only those event ids to the
equipment service. If there are no active assignments it returns `[]` without
requesting the global requirements collection. Supplying an event assigned to
someone else, or an inactive event, returns `404`.

## Response

Successful writes and reads return an equipment requirement:

```json
{
  "id": "44444444-4444-4444-8444-444444444444",
  "event_id": "33333333-3333-4333-8333-333333333333",
  "equipment_item_id": "22222222-2222-4222-8222-222222222222",
  "required_quantity": 4,
  "recorded_by_coordinator_id": "11111111-1111-4111-8111-111111111111",
  "created_at": "2026-09-27T08:00:00Z",
  "updated_at": "2026-09-27T08:00:00Z",
  "equipment": {
    "id": "22222222-2222-4222-8222-222222222222",
    "type": "Wireless Microphone",
    "description": "Handheld wireless microphone",
    "total_quantity": 12,
    "operational_status": "available",
    "lifecycle_status": "active"
  }
}
```

`GET` returns `200` with an array; no matching requirements returns `[]`.
`DELETE` returns `204`. Errors use `401` for no session, `403` for the wrong
role, `404` for a missing/unassigned event or item, `409` outside planning,
`422` for invalid input, and `502` when a dependency is unavailable. A write
without accepted impact returns `409` before the equipment service is called.

S-82: once the equipment service has accepted a change, the composite sends
it to the event's change history (Events
`POST /internal/events/{event_id}/history`): `equipment_requirement_set` or
`equipment_requirement_removed`, by the Coordinator, with `details`
`{"equipment_item_id", "item_name", "from_quantity", "to_quantity"}`
(`from_quantity` is `null` for a new requirement and `to_quantity` is `null`
for a removal). The current requirement is read first, so a `502` from that
read stops the change before anything is written. Saving the same quantity
again records nothing. Recording is best effort: if Events can't take the
entry, the change stands and the failure is logged at `ERROR`. Technical
Support's sign-off and preparation status are recorded by Events itself.

## Running

Set all variables listed in the root `.env.example`, start the three atomic
dependencies, then:

```bash
cd backend/services/composite/equipment_requirements
set -a; source ../../../../.env; set +a
uvicorn app:app --reload --port 8102
```

Tests:

```bash
pytest tests/unit/composite/equipment_requirements

docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/composite/equipment_requirements
```

## Sign-off (S-17)

`POST /equipment-requirements/{event_id}/sign-off` -- the event's assigned
Technical Support only, while the event is in `planning`. Through Kong:
`POST /api/equipment-requirements/{event_id}/sign-off`.

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `decision` | `"approved"` or `"declined"` | Yes | |
| `reason` | string ≤ 500 | With `declined` | Not blank. Refused with `approved`. |
| `override_comment` | string ≤ 500 | No | Only with `approved`. Not blank. Needed to approve over a shortage. |

An approval without `override_comment` first checks S-44 availability over
the event's own window: whatever every other overlapping event reserves is
taken off, and any requirement still not met is a shortage. A decline needs
no check.

| Status | Body | Meaning |
| --- | --- | --- |
| `200` | The updated event, with `technical_signoff_decision`, `_reason`, `_override_comment`, `_by`, `_at` | Recorded. |
| `401` | `{"detail": "Not authenticated"}` | No valid session. |
| `403` | `{"detail": "Permission denied"}` | Not Technical Support. |
| `404` | `{"detail": "Event not found or not assigned to you"}` | Not the caller's assignment. |
| `409` | `{"detail": "Some equipment is short for this event", "short": [{"equipment_item_id": "…", "name": "Projector", "required": 4, "available": 2}]}` | Approve again with an `override_comment`. Nothing recorded. |
| `409` | `{"detail": "Technical Support sign-off can only change while the event is in planning"}` | The event moved on. |
| `422` | `{"detail": "Please check the details you entered", "errors": {...}}` | The field rules above. |
| `502` | `{"detail": "<Users\|Events\|Equipment> service unavailable"}` | A dependency failed. Nothing recorded. |

Any Coordinator `PUT` or `DELETE` of a requirement clears the sign-off
(`POST /internal/events/{event_id}/technical-signoff/clear`) **before** the
change. If clearing fails the change is not made and the answer is `502`.

## Availability check (S-44)

`GET /equipment-requirements/availability` — Technical Support only. Through
Kong: `GET /api/equipment-requirements/availability`. It calls `events`
`POST /events/overlapping`, then `equipment` `GET /equipment` (with the
caller's session) and `GET /internal/equipment-requirements?event_ids=…`. No
new table or SQL: it reads what S-39 and S-40 already store.

| Query | Type | Required | Rule |
| --- | --- | --- | --- |
| `start_date`, `start_time` | date `YYYY-MM-DD`, time `HH:MM` | Yes | Start of the window. |
| `end_date`, `end_time` | date, time | Yes | Must be after the start; the window may span days. |
| `type` | string | No | Case-insensitive "contains" match on the item type; blank is ignored. |
| `quantity` | integer ≥ 1 | No | The quantity needed; adds `sufficient` to each item. |

How it counts, per active item (retired items are left out):

- **reserved** — the sum of requirements on `planning` and `confirmed`
  events overlapping the window. An event ending exactly when the window
  starts, or starting exactly when it ends, reserves nothing.
- **unavailable** — the whole pool when its `operational_status` is
  `unavailable` or `maintenance`, otherwise 0.
- **available** — 0 for an out-of-service pool, otherwise `total − reserved`,
  never below 0. When requirements exceed the pool, `over_reserved` is true.

Nothing is cached: each call reads live data and returns `checked_at`.

`200`:

```json
{
  "checked_at": "2026-11-10T06:32:10.123456+00:00",
  "start_date": "2026-11-12", "start_time": "09:00",
  "end_date": "2026-11-12", "end_time": "12:00",
  "type": null,
  "quantity": 3,
  "items": [
    {
      "id": "…", "type": "Wireless Microphone", "operational_status": "available",
      "total": 12, "reserved": 10, "unavailable": 0, "available": 2,
      "over_reserved": false, "sufficient": false,
      "reservations": [
        {"event_id": "…", "event_name": "Alumni talk", "status": "planning",
         "start_date": "2026-11-12", "start_time": "10:00:00",
         "end_date": "2026-11-12", "end_time": "11:00:00", "required_quantity": 5}
      ]
    }
  ]
}
```

Items are in type order; each item's `reservations` in event start order.
`sufficient` is `null` when no `quantity` was given.

| Status | Body | Meaning |
| --- | --- | --- |
| `401` | `{"detail": "Not authenticated"}` | No valid session. |
| `403` | `{"detail": "Permission denied"}` | Not Technical Support. |
| `422` | `{"detail": "Please check the details you entered", "errors": {...}}` | A field is missing or malformed, `quantity` is below 1, or the end is not after the start (`errors.end_time`). |
| `502` | `{"detail": "<Users\|Events\|Equipment> service unavailable"}` | A dependency failed. Never an empty or partial answer. |

Tests: `pytest tests/unit/composite/equipment_requirements`, then on a
freshly recreated `.env.test` stack
`pytest tests/integration/composite/equipment_requirements tests/integration/atomic/events`
and `pytest tests/e2e/test_check_equipment_availability.py`.
