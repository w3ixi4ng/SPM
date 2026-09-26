# Bookings service

Atomic FastAPI service for venue booking requests (S-36). It owns
`bookings.bookings` and never queries another service's tables.

It stores and lists requests and nothing else. Whether a venue can take a
request is decided by the [`venue_bookings`](../../composite/venue_bookings/README.md)
composite before it writes here, because that needs the event and the venue.

**No browser reaches this service.** There is no Kong route and no session
check; the only caller is `venue_bookings`, inside the Docker network — the
same arrangement as the events service's internal routes.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/bookings` | Store a checked booking request as `pending`. |
| `GET` | `/bookings?status=pending` | List pending requests, oldest first. |
| `GET` | `/bookings?event_id={id}` | List the requests sent for one event, every status, oldest first. |
| `GET` | `/health` | Liveness check. |

## Requests

### `POST /bookings`

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `event_id` | UUID | yes | |
| `venue_id` | UUID | yes | |
| `coordinator_id` | UUID | yes | |
| `coordinator_name` | string | yes | Trimmed; not blank. |
| `coordinator_email` | string | yes | Trimmed; not blank. |
| `booking_date` | date `YYYY-MM-DD` | yes | |
| `start_time` | time `HH:MM` | yes | |
| `end_time` | time `HH:MM` | yes | After `start_time`. |
| `event_name` | string | yes | Trimmed; not blank. |
| `event_purpose` | string | yes | Trimmed; not blank. |
| `expected_attendance` | integer | yes | At least `1`. |
| `venue_name` | string | yes | Trimmed; not blank. |
| `accessibility_requirements` | string or null | no | The organiser's free text. Blank becomes null. |
| `required_accessibility` | array of string | no | From the venue accessibility set. Defaults to `[]`. |
| `required_facilities` | array of string | no | From the venue facility set. Defaults to `[]`. |
| `room_layout` | string or null | no | From the venue layout set. |
| `notes` | string or null | no | Blank becomes null. |

Repeated entries in the two arrays are dropped. `status` and `submitted_at`
are set by the service; sending either is a `422`. Any other unknown field is
a `422` too.

The option sets are the venue catalogue's (see
[`venues/README.md`](../venues/README.md)), repeated in
[`schemas.py`](schemas.py) and as check constraints in
[`bookings.sql`](../../../sql/bookings.sql).

### `GET /bookings`

| Query | Required | Values |
| --- | --- | --- |
| `status` | one of the two | `pending` |
| `event_id` | one of the two | UUID |

Both may be given together. With neither, the answer is `422`
`{"detail": "Filter by status or event_id"}` — nothing lists every booking.

## Responses

`POST /bookings` returns `201`; `GET /bookings` returns `200` with a list of
the same shape (`[]` when there are none).

```json
{
  "id": "44444444-4444-4444-8444-444444444444",
  "event_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  "venue_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  "coordinator_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  "coordinator_name": "Grace Hopper",
  "coordinator_email": "grace@example.com",
  "status": "pending",
  "booking_date": "2026-11-12",
  "start_time": "09:00:00",
  "end_time": "12:00:00",
  "event_name": "Alumni networking evening",
  "event_purpose": "Reconnect graduates with faculty",
  "expected_attendance": 120,
  "accessibility_requirements": "Two guests use wheelchairs",
  "required_accessibility": ["wheelchair_access"],
  "required_facilities": ["projector"],
  "room_layout": "theatre",
  "notes": "Access from 08:30 for setup",
  "venue_name": "Studio B",
  "submitted_at": "2026-10-01T09:00:00+00:00"
}
```

| Status | Meaning |
| --- | --- |
| `422` | The body or query failed validation. `{"detail": "Please check the details you entered", "errors": {"<field>": "<message>"}}` |
| `500` | `{"detail": "Booking storage unavailable"}` — Supabase could not be reached, or refused the write. |

## Running it

**First:** run [`backend/sql/bookings.sql`](../../../sql/bookings.sql) in the
Supabase SQL Editor of both the dev and the test project, and add `bookings`
under **Data API → Settings → Exposed schemas** in both.

**Development** — `.env` filled in from `.env.example`:

```bash
docker compose up --build
# or on its own:
cd backend/services/atomic/bookings
uvicorn app:app --reload --port 8004
```

**Tests:**

```bash
pytest tests/unit/atomic/bookings

docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/atomic/bookings
```
