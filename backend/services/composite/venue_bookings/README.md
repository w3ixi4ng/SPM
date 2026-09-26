# Venue bookings service

Composite FastAPI service for venue booking requests (S-36). An Event
Coordinator submits a request for a venue, date and time against one of their
events; Venue Staff see every pending request. Owns no table — requests are
stored by the [`bookings`](../../atomic/bookings/README.md) service.

| Calls | For |
| --- | --- |
| `users` — `GET /users/me` | Who is asking, and their role |
| `events` — `GET /events/assigned/{id}` | The event, with the caller's own session, so only an event assigned to this Coordinator is found |
| `venues` — `GET /venues/{id}` | The venue, with the caller's own session |
| `bookings` — `POST /bookings`, `GET /bookings?status=pending`, `GET /bookings?event_id={id}` | Store and list requests |

Reached through Kong at `/api/venue-bookings`.

## Endpoints

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| `POST` | `/venue-bookings` | `event_coordinator` | Check a venue request and submit it as pending. |
| `GET` | `/venue-bookings?event_id={id}` | `event_coordinator` | The requests sent for one of the caller's events, every status, oldest first. `404` if the event is not assigned to the caller. |
| `GET` | `/venue-bookings/pending` | `venue_staff` | Every pending request, oldest first. Not filtered by who added the venue. |
| `GET` | `/health`, `/venue-bookings/health` | none | Liveness check. |

## Requests

### `POST /venue-bookings`

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `event_id` | UUID | yes | An event assigned to the caller, in status `planning`. |
| `venue_id` | UUID | yes | |
| `booking_date` | date `YYYY-MM-DD` | yes | One date. |
| `start_time` | time `HH:MM` | yes | |
| `end_time` | time `HH:MM` | yes | After `start_time`. |
| `notes` | string or null | no | Blank becomes null. |

```json
{
  "event_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  "venue_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  "booking_date": "2026-11-12",
  "start_time": "09:00",
  "end_time": "12:00",
  "notes": "Access from 08:30 for setup"
}
```

Any other field is a `422`, including `room_layout`, `required_facilities`
and `required_accessibility`: those are the event's venue requirements, set
by the organiser. Everything else on the stored request — the event's name,
purpose, expected attendance, venue requirements and other requirements, the
venue's name, the Coordinator's name and email — is looked up by this
service and copied onto the request. It is a snapshot: later edits to the
event do not change a request already sent.

**Checks before anything is saved.** A request that fails any of these is
refused with `422`, is never stored, and never reaches Venue Staff. All
failures are reported together, keyed by the field to change:

| `errors` key | Refused when | Message |
| --- | --- | --- |
| `booking_date` | The booking starts before the event or ends after it (equal is fine) | `The booking must fall within the event's date and time` |
| `operating_hours` | The venue has no hours that weekday, or the booking runs outside them (equal is fine) | `Studio B is closed on Saturdays` / `Studio B is open 08:00–20:00 on Thursdays` |
| `expected_attendance` | The event's attendance is more than the venue's capacity | `Studio B holds 150 people; this event expects 151` |
| `required_facilities` | One of the event's facilities is not at the venue | `Studio B does not have: stage, whiteboard` |
| `required_accessibility` | One of the event's accessibility features is not at the venue | `Studio B does not have: hearing_loop` |
| `room_layout` | The venue does not offer the event's layout | `Studio B does not offer the banquet layout` |

Duplicate and overlapping requests are not checked here; they belong to the
tentative-holds and conflict-detection stories.

Submitting a request writes nothing to the event — it is already in
`planning` and stays there.

## Responses

`POST /venue-bookings` returns `201` with the stored request, and
`GET /venue-bookings?event_id={id}` and `GET /venue-bookings/pending` return
`200` with a list of them — both
exactly as the bookings service returns them (see
[`bookings/README.md`](../../atomic/bookings/README.md#responses)):

```json
{
  "id": "44444444-4444-4444-8444-444444444444",
  "status": "pending",
  "event_name": "Alumni networking evening",
  "venue_name": "Studio B",
  "booking_date": "2026-11-12",
  "start_time": "09:00:00",
  "end_time": "12:00:00",
  "expected_attendance": 120,
  "...": "every other field of the stored request"
}
```

| Status | Body | Meaning |
| --- | --- | --- |
| `401` | `{"detail": "Not authenticated"}` | No valid session. |
| `403` | `{"detail": "Permission denied"}` | Wrong role for the route. |
| `404` | `{"detail": "Event not found"}` | No such event, or it is not assigned to the caller. |
| `404` | `{"detail": "Venue not found"}` | No such venue. |
| `409` | `{"detail": "A venue can only be requested for an event in planning"}` | The event is `submitted`, `returned` or `rejected`. |
| `422` | `{"detail": "Please check the details you entered", "errors": {...}}` | The body failed validation. |
| `422` | `{"detail": "This venue can't take this booking", "errors": {...}}` | Refused by the checks above. |
| `502` | `{"detail": "<Users\|Events\|Venues\|Bookings> service unavailable"}` | A downstream service could not be reached or failed. Nothing was saved. |

## Running it

**First:** every schema it depends on applied and exposed in both the dev and
the test project — `users`, `events` (including the S-36 `planning` change),
`venues` and `bookings`. See [`backend/sql/`](../../../sql/README.md).

**Development** — `.env` filled in from `.env.example`, including
`VENUES_SERVICE_URL` and `BOOKINGS_SERVICE_URL`:

```bash
docker compose up --build
# or on its own, with the *_SERVICE_URL values switched to localhost:
cd backend/services/composite/venue_bookings
uvicorn app:app --reload --port 8101
```

**Tests:**

```bash
pytest tests/unit/composite/venue_bookings

docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/composite/venue_bookings
```
