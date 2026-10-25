# Registrations service

Atomic FastAPI service for S-51 and S-48 event registrations: which Attendee holds a
place at which event. It owns `registrations.registrations` and never queries
another service's tables. Event and attendee ids are opaque here.

There is no Kong route. Only the
[`event_registrations`](../../composite/event_registrations/README.md)
composite calls it, after checking that the event is confirmed and its
registration period is open. Its port, 8007, is published for testing.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/registrations` | Record one Attendee's place at one event. |
| `GET` | `/registrations/events/{event_id}/attendees/{attendee_id}` | Return that Attendee's registration for the event, if any. |
| `GET` | `/registrations/events/{event_id}` | Every registration for the event, earliest first. |
| `GET` | `/registrations/attendees/{attendee_id}` | Every registration the Attendee holds, earliest first. |
| `GET` | `/health` | Liveness check. |
| `GET` | `/registrations/health` | Gateway-compatible liveness alias. |

## Request

`POST /registrations`:

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `event_id` | UUID | yes | |
| `attendee_id` | UUID | yes | |

No other field is accepted. The `GET` routes take their ids (UUIDs) in the
path and no query parameters.

```json
{"event_id": "22222222-2222-4222-8222-222222222222", "attendee_id": "33333333-3333-4333-8333-333333333333"}
```

## Response

`201` from `POST`, `200` from the single `GET`; the two list routes answer
`200` with an array of these, `[]` when there are none:

```json
{
  "id": "55555555-5555-4555-8555-555555555555",
  "event_id": "22222222-2222-4222-8222-222222222222",
  "attendee_id": "33333333-3333-4333-8333-333333333333",
  "created_at": "2026-11-05T04:00:00Z"
}
```

| Status | When |
| --- | --- |
| `409` | `POST` for an Attendee already registered for that event: `{"detail": "You're already registered for this event."}`. The table's unique `(event_id, attendee_id)` constraint enforces it, so two simultaneous requests still produce one place. |
| `404` | `GET` when the Attendee is not registered: `{"detail": "You're not registered for this event."}` |
| `422` | Missing or malformed ids (body or path), or an unexpected field: `{"detail": "Please check the registration", "errors": {...}}` |
| `500` | Storage failed: `{"detail": "Registration storage unavailable"}` |

`GET /health` returns `{"status": "ok"}`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `SUPABASE_URL` | Supabase project URL. |
| `SUPABASE_SERVICE_KEY` | Backend-only access to `registrations.registrations`. |

## Database setup

Run [`backend/sql/registrations.sql`](../../../sql/registrations.sql) in
**both** the dev and test Supabase projects, then add `registrations` under
**Data API → Settings → Exposed schemas** in each. Both steps are needed.

## Running

Development, with `.env` filled in and the schema applied and exposed:

```bash
cd backend/services/atomic/registrations
uvicorn app:app --reload --port 8007
```

Unit tests need no Docker or Supabase:

```bash
pytest tests/unit/atomic/registrations
```

Integration tests need `.env.test`, the schema applied and exposed in the
test project, and a stack started immediately before:

```bash
docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/atomic/registrations
```

## Test cases

[`tests/unit/atomic/registrations/TEST_CASES.md`](../../../../tests/unit/atomic/registrations/TEST_CASES.md)
and [`tests/integration/atomic/registrations/TEST_CASES.md`](../../../../tests/integration/atomic/registrations/TEST_CASES.md).
