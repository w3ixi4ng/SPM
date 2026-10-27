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
| `POST` | `/registrations` | Record one Attendee's place at one event, while the event has one left (S-50). |
| `GET` | `/registrations/events/{event_id}/attendees/{attendee_id}` | Return that Attendee's registration for the event, if any. |
| `GET` | `/registrations/events/{event_id}` | Every registration for the event, earliest first. |
| `GET` | `/registrations/attendees/{attendee_id}` | Every registration the Attendee holds, earliest first. |
| `POST` | `/registrations/waiting-list` | S-50: put an Attendee on an event's waiting list. |
| `GET` | `/registrations/waiting-list/events/{event_id}` | S-50: the event's waiting list, first come, first served (by `created_at`, then `id`). |
| `GET` | `/registrations/waiting-list/attendees/{attendee_id}` | S-52: every waiting-list entry the Attendee holds, oldest first. |
| `GET` | `/registrations/waiting-list/events/{event_id}/attendees/{attendee_id}` | S-50: that Attendee's waiting-list entry, if any. |
| `POST` | `/registrations/withdrawals` | S-53: give up an Attendee's place; the Attendee who has waited longest takes it, if a place is free. |
| `GET` | `/health` | Liveness check. |
| `GET` | `/registrations/health` | Gateway-compatible liveness alias. |

## Request

`POST /registrations`:

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `event_id` | UUID | yes | |
| `attendee_id` | UUID | yes | |
| `capacity` | integer | yes | `> 0`. The event's expected attendance; the events service owns it, so the caller passes it. |

`POST /registrations/waiting-list` takes `event_id` and `attendee_id` only.

`POST /registrations/withdrawals` takes the same three fields as
`POST /registrations`, except `capacity` is `>= 0`: someone is promoted only
while the places left after the withdrawal number fewer than `capacity`, so
`0` promotes no one.

No other field is accepted. The `GET` routes take their ids (UUIDs) in the
path and no query parameters.

```json
{"event_id": "22222222-2222-4222-8222-222222222222", "attendee_id": "33333333-3333-4333-8333-333333333333", "capacity": 50}
```

The place is taken by the `registrations.register` Postgres function, which
locks the event, counts its places and inserts only if one is left -- so two
people registering for the last place at once cannot both get it.

**Withdrawal** (`200` from `POST /registrations/withdrawals`): the place given
up, and the place the next Attendee waiting took, or `null`. Both happen in one
step in the `registrations.withdraw` Postgres function, under the same lock as
`registrations.register`, and the promoted Attendee leaves the waiting list.

```json
{
  "withdrawn": {"id": "55555555-5555-4555-8555-555555555555", "event_id": "22222222-2222-4222-8222-222222222222", "attendee_id": "33333333-3333-4333-8333-333333333333", "created_at": "2026-11-05T04:00:00Z"},
  "promoted": {"id": "99999999-9999-4999-8999-999999999999", "event_id": "22222222-2222-4222-8222-222222222222", "attendee_id": "44444444-4444-4444-8444-444444444444", "created_at": "2026-11-06T04:00:00Z"}
}
```

## Response

`201` from either `POST`, `200` from the single `GET`s; the list routes answer
`200` with an array of these, `[]` when there are none. A waiting-list entry
has the same shape:

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
| `409` | `POST /registrations` once the event's places reach `capacity`: `{"detail": "This event is full."}` |
| `409` | `POST /registrations/waiting-list` a second time: `{"detail": "You're already on the waiting list for this event."}` |
| `404` | `POST /registrations/withdrawals` when the Attendee holds no place: `{"detail": "You're not registered for this event."}` |
| `404` | `GET` when the Attendee is not registered: `{"detail": "You're not registered for this event."}`; or not waiting: `{"detail": "You're not on the waiting list for this event."}` |
| `422` | Missing or malformed ids (body or path), a missing or non-positive `capacity`, or an unexpected field: `{"detail": "Please check the registration", "errors": {...}}` |
| `500` | Storage failed: `{"detail": "Registration storage unavailable"}` |

`GET /health` returns `{"status": "ok"}`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `SUPABASE_URL` | Supabase project URL. |
| `SUPABASE_SERVICE_KEY` | Backend-only access to `registrations.registrations`, `registrations.waiting_list`, `registrations.register` and `registrations.withdraw`. |

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
