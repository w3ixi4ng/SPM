# Equipment requirements service

Composite service for S-40. It verifies the signed-in user with `users`, asks
`events` whether that Coordinator is currently assigned and the event is in
`planning`, then stores requirements through the `equipment` atomic service.
It owns no database.

## Endpoints

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | Public | Process health check. |
| `GET` | `/equipment-requirements?event_id=<uuid>` | Coordinator, Technical Support | List requirements. Coordinators must supply an assigned event; Technical Support may omit it to list all. |
| `PUT` | `/equipment-requirements/{event_id}/{equipment_item_id}` | Coordinator | Create or replace a quantity while the currently assigned event is in planning. |
| `DELETE` | `/equipment-requirements/{event_id}/{equipment_item_id}` | Coordinator | Remove a requirement while the currently assigned event is in planning. |

## Request

`PUT` accepts exactly:

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `required_quantity` | integer | Yes | Positive whole number. |

The service derives `recorded_by_coordinator_id` from the verified session.
That field is audit information only: every authorization decision asks the
events service for the event's current assignment.

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

`DELETE` returns `204`. Errors use `401` for no session, `403` for the wrong
role, `404` for a missing/unassigned event or item, `409` outside planning,
`422` for invalid input, and `502` when a dependency is unavailable.

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
