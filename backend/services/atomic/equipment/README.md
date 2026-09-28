# Equipment service

Atomic owner of the equipment catalogue. One item is an equipment type/pool,
such as “Wireless Microphone”, with a total quantity; it is not one serialized
physical unit. It also owns the event-to-item relationship in
`equipment.requirements`. The service calls no other service.

## Endpoints

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | Public | Process health check. |
| `GET` | `/equipment/health` | Public | Gateway-compatible health alias. |
| `POST` | `/equipment` | Technical Support | Add an equipment item. |
| `GET` | `/equipment` | Technical Support | List the complete management catalogue. |
| `GET` | `/equipment/selection` | Technical Support, Event Coordinator, Event Organiser | List active, available options for requirement forms. |
| `GET` | `/internal/equipment-requirements` | Equipment requirements composite | List requirements, optionally filtered by `event_id`. |
| `PUT` | `/internal/equipment-requirements/{event_id}/{equipment_item_id}` | Equipment requirements composite | Upsert a positive required quantity and audit user. |
| `DELETE` | `/internal/equipment-requirements/{event_id}/{equipment_item_id}` | Equipment requirements composite | Delete one event/item relationship. |

## Request

`POST /equipment` accepts:

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `type` | string | Yes | Must contain non-whitespace text. |
| `description` | string or null | No | Blank text becomes null. |
| `total_quantity` | integer | Yes | Positive whole number. |

The service sets `operational_status="available"`,
`lifecycle_status="active"`, and `created_by` from the verified session.
Clients cannot choose these values.

The internal `PUT` body contains `required_quantity` (positive integer) and
`recorded_by_coordinator_id` (UUID). The relationship's `event_id` is opaque
to this atomic service: assignment and event status are checked by the
composite before it calls this route. These internal routes are not exposed
through Kong.

## Response

Creation returns `201`; both lists return `200`. An item has this shape:

```json
{
  "id": "22222222-2222-4222-8222-222222222222",
  "type": "Wireless Microphone",
  "description": "Handheld wireless microphone with receiver",
  "total_quantity": 12,
  "operational_status": "available",
  "lifecycle_status": "active",
  "created_by": "11111111-1111-4111-8111-111111111111",
  "created_at": "2026-09-27T08:00:00Z",
  "updated_at": "2026-09-27T08:00:00Z"
}
```

Errors:

| Status | Body | Meaning |
| --- | --- | --- |
| `401` | `{"detail":"Not authenticated"}` | Session is absent or expired. |
| `403` | `{"detail":"Permission denied"}` | Trusted role lacks the requested permission. |
| `422` | `{"detail":"Please check the details you entered","errors":{...}}` | Request validation failed. |
| `500` | `{"detail":"Equipment storage unavailable"}` | Catalogue storage failed safely. |

## Database setup

Run `backend/sql/equipment.sql` in the SQL Editor of both dev and test
projects, then add `equipment` under **Data API → Settings → Exposed schemas**.
Both the exposure and the SQL grants are required.

## Running

Development, after the root `.env` is filled and the schema is ready:

```bash
cd backend/services/atomic/equipment
set -a; source ../../../../.env; set +a
uvicorn app:app --reload --port 8005
```

Tests:

```bash
pytest tests/unit/atomic/equipment

docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/atomic/equipment
```

Specifications live beside the tests in their respective `TEST_CASES.md`
files.
