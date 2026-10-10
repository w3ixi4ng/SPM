# Safety Checks service

Composite FastAPI service for S-86. It owns no database. It authenticates a
Safety Officer through Users, reads the current event from Events, enriches it
with Users, Bookings, Venues and Equipment, and sends the decision back to the
Events atomic owner.

`confirmed` is this project's documented lifecycle interpretation that the
required venue and technical arrangements are confirmed. It is not a status
name prescribed by the customer document.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/safety-checks` | List confirmed events with no safety decision, enriched with organiser. |
| `GET` | `/safety-checks/{event_id}` | Return all operational-safety evidence for one eligible event. |
| `POST` | `/safety-checks/{event_id}/decision` | Record the first safety decision as the authenticated Safety Officer. |
| `GET` | `/health` | Liveness check. |

Only trusted `app_metadata.role=safety_officer` is accepted. No Safety Officer
assignment is introduced: every Safety Officer can access every eligible row.

## Requests

The decision body contains only client-owned fields:

```json
{"decision": "changes_requested", "reason": "Move speaker cables away from the north exit"}
```

`decision` is `approved`, `rejected`, or `changes_requested`. Rejection and
changes require a nonblank `reason`; approval accepts no reason. The service
adds `safety_officer_id` from `/users/me`; a browser cannot select it.

## Responses

The queue returns event summaries with an `organiser` profile. An empty queue
is `[]`.

Detail returns:

```json
{
  "event": {"id": "…", "name": "Forum", "status": "confirmed", "expected_attendance": 120, "special_requirements": "Keep emergency access clear"},
  "organiser": {"id": "…", "name": "Ada Organiser", "email": "ada@example.com"},
  "technical_support": {"id": "…", "name": "Terry Support", "email": "terry@example.com"},
  "technical_support_notes": "Place speakers away from exits",
  "confirmed_venues": [{
    "booking_id": "…", "venue_id": "…", "name": "Grand Hall",
    "capacity": 200, "layout": "theatre",
    "accessibility": ["wheelchair_access"],
    "restrictions": "No open flame; keep north exit clear"
  }],
  "equipment_requirements": [{"required_quantity": 4, "equipment": {"type": "Wireless microphone"}}]
}
```

Venue `description` is the existing catalogue field used for venue notes and
restrictions; S-86 exposes it under the explicit `restrictions` response name.
Only bookings whose current status is `confirmed` enter `confirmed_venues`.

A successful decision returns the updated Event object. Transitions are:

| Decision | Event status |
| --- | --- |
| `approved` | `preparation` |
| `rejected` | `safety_rejected` |
| `changes_requested` | `safety_changes_requested` |

The Events service conditionally writes only a `confirmed` row with a null
current safety decision. A stale, repeated, or concurrent attempt returns
`409` and cannot overwrite the first stored result. S-86 creates no
notifications; S-87 owns routing requested changes back into planning.

## Errors

| Status | Meaning |
| --- | --- |
| `401` | No valid session. |
| `403` | The authenticated role is not Safety Officer. |
| `404` | The event does not exist. |
| `409` | It is ineligible, stale, or already decided. |
| `422` | Invalid event id, decision, reason combination, or extra field. |
| `502` | A required atomic service is unavailable or returned an unidentified failure. |

## Configuration and running

The service reads `USERS_SERVICE_URL`, `EVENTS_SERVICE_URL`,
`VENUES_SERVICE_URL`, `BOOKINGS_SERVICE_URL`, and `EQUIPMENT_SERVICE_URL`.
Every outbound client has a bounded timeout.

Development:

```bash
cd backend/services/composite/safety_checks
uvicorn app:app --reload --port 8103
```

Whole test stack and tests:

```bash
docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/composite/safety_checks
pytest tests/e2e/test_operational_safety_check.py
```

Before integration or browser tests, apply
[`backend/sql/events.sql`](../../../sql/events.sql) to both dev and test
Supabase projects. Unit tests require neither Docker nor Supabase:

```bash
pytest tests/unit/composite/safety_checks
```
