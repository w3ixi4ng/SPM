# Events service

Atomic FastAPI service for event requests. It owns `events.events` and never
queries another service's tables.

## Endpoints

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| `POST` | `/events/drafts` | `events:save_draft` | Create an incomplete draft. |
| `POST` | `/events` | `events:create` | Create an immediately submitted request. |
| `GET` | `/events` | `events:view_own` | List the authenticated organiser's event requests, most recently updated first. |
| `GET` | `/events/{event_id}` | `events:view_own` | Return one event owned by the authenticated caller. |
| `PATCH` | `/events/{event_id}` | `events:update_own_draft` | Update supplied fields on an owned draft. |
| `POST` | `/events/{event_id}/submit` | `events:submit_own` | Replace the business fields of an owned draft with a complete submission and submit it. |
| `GET` | `/events/health` | none | Gateway-compatible liveness alias. |
| `GET` | `/health` | none | Liveness check. |

All event endpoints except health authenticate the `sb_access_token` and
`sb_refresh_token` cookies issued by the users service, then authorize the
trusted `app_metadata.role` against the permission shown above.

The centralized policy recognizes every project role. All may view their own
frontend dashboard; only Event Organiser workflows are currently defined:

| Role | Permissions |
| --- | --- |
| `event_organiser` | `dashboard:view`, `events:create`, `events:save_draft`, `events:view_own`, `events:update_own_draft`, `events:submit_own` |
| `event_coordinator` | `dashboard:view` |
| `venue_staff` | `dashboard:view` |
| `technical_support` | `dashboard:view` |
| `attendee` | `dashboard:view` |

The internal and attendee roles intentionally receive no speculative event
permissions. Their permissions can expand when a corresponding project story
defines a workflow.

The service derives `organiser_id` from the verified Supabase user. A request
cannot set `id`, `organiser_id`, `status`, `created_at`, or `updated_at`.

## Requests

### Draft fields

Every field is optional for `POST /events/drafts` and `PATCH /events/{event_id}`.
When supplied, values still have to be valid.

| Field | Type | Rules |
| --- | --- | --- |
| `name` | string or null | Blank text becomes null. |
| `purpose` | string or null | Blank text becomes null. |
| `start_date` | `YYYY-MM-DD` or null | Optional. |
| `end_date` | `YYYY-MM-DD` or null | Optional. |
| `start_time` | time or null | If a full start and end are present, the combined start date+time must be before the combined end date+time. |
| `end_time` | time or null | Same rule, the other side — this is what lets an event run past midnight into the next day. |
| `expected_attendance` | integer or null | Greater than zero when present. |
| `venue` | string or null | Blank text becomes null. |
| `equipment_requests` | object | Optional; values must be positive integers. Defaults to `{}` on create. |
| `accessibility_requirements` | string or null | Blank text becomes null. |

An empty draft is valid:

```json
{}
```

`PATCH` changes only fields present in the request. It cannot edit a submitted
event.

### Submitted fields

`POST /events` and `POST /events/{event_id}/submit` take the same body:

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `name` | string | yes | Nonblank. |
| `purpose` | string | yes | Nonblank. |
| `start_date` | `YYYY-MM-DD` | yes | |
| `end_date` | `YYYY-MM-DD` | yes | |
| `start_time` | time | yes | Combined with `start_date`, must be before the combined `end_date`+`end_time`. |
| `end_time` | time | yes | Combined with `end_date`, must be after the combined `start_date`+`start_time`. |
| `expected_attendance` | integer | yes | Greater than zero. |
| `venue` | string | yes | Nonblank. |
| `equipment_requests` | object | no | Values must be positive integers; defaults to `{}`. |
| `accessibility_requirements` | string or null | no | Blank text becomes null. |

```json
{
  "name": "Alumni networking evening",
  "purpose": "Connect alumni with graduating students",
  "start_date": "2026-10-20",
  "end_date": "2026-10-20",
  "start_time": "18:00",
  "end_time": "21:00",
  "expected_attendance": 120,
  "venue": "Main auditorium",
  "equipment_requests": {"projector": 1, "microphone": 2},
  "accessibility_requirements": "Wheelchair access"
}
```

## Response

Create endpoints return `201`; list, get, update, and submit-existing return
`200`. Every event object has this shape:

```json
{
  "id": "33333333-3333-4333-8333-333333333333",
  "organiser_id": "11111111-1111-4111-8111-111111111111",
  "status": "submitted",
  "name": "Alumni networking evening",
  "purpose": "Connect alumni with graduating students",
  "start_date": "2026-10-20",
  "end_date": "2026-10-20",
  "start_time": "18:00:00",
  "end_time": "21:00:00",
  "expected_attendance": 120,
  "venue": "Main auditorium",
  "equipment_requests": {"projector": 1, "microphone": 2},
  "accessibility_requirements": "Wheelchair access",
  "created_at": "2026-09-14T00:00:00Z",
  "updated_at": "2026-09-14T00:00:00Z"
}
```

`GET /events` returns an array containing only rows whose `organiser_id`
matches the verified user. An organiser with no requests receives `[]`.

`GET /health` returns:

```json
{"status": "ok"}
```

## Errors

| Status | When |
| --- | --- |
| `401` | No valid session; expired access tokens are refreshed when possible. |
| `403` | The trusted role is missing, unknown, or lacks the route's permission. |
| `404` | The event does not exist or belongs to another user. |
| `409` | A submitted event was edited or submitted again. |
| `422` | The request body or event id is invalid. |
| `500` | Event storage or another internal operation failed. Internal details are not returned. |

Validation errors use the same shape as the users service:

```json
{
  "detail": "Please check the details you entered",
  "errors": {"expected_attendance": "Input should be greater than 0"}
}
```

## Configuration

The service reads these variables from the root environment:

| Variable | Purpose |
| --- | --- |
| `SUPABASE_URL` | Supabase project URL. |
| `SUPABASE_SERVICE_KEY` | Backend-only access to `events.events`. |
| `SUPABASE_ANON_KEY` | Supabase Auth session verification and refresh. |
| `AUTH_COOKIE_SECURE` | Whether authentication cookies carry `Secure`; defaults to `true`. |

## Database setup

Run [`backend/sql/events.sql`](../../../sql/events.sql) in both the dev and test
Supabase projects. In each project, add `events` under **Data API → Settings →
Exposed schemas**. The SQL grants the table to `service_role`; do not grant
`anon` or `authenticated` direct table access.

Write endpoints also require the authenticated user's trusted Supabase Auth
`app_metadata.role` to be `event_organiser`. User-supplied metadata must not be
used for this decision.

## Running

### Development

Load the root `.env` into the shell, then:

```bash
cd backend/services/atomic/events
uvicorn app:app --reload --port 8002
```

The Dockerfile also runs the service internally on port 8002. To run it with
the rest of the current test stack, from the repository root:

```bash
docker compose --env-file .env.test up -d --build --wait
```

The browser reaches this service through Kong at `/api/events`; the service is
also published directly on `localhost:8002` for service-level integration
tests.

### Unit tests

From the repository root:

```bash
pip install -r backend/services/atomic/events/requirements.txt -r tests/requirements.txt
pytest tests/unit/atomic/events
```

The unit tests replace both Supabase clients with mocks, so they need no
environment file, database, Docker, or network.

### Integration tests

Two real round trips are defined under `tests/integration/atomic/events`: one
calls the service directly and one verifies all browser-facing event routes
through Kong. With the test stack running as above:

```bash
pytest tests/integration/atomic/events
```

Do not point either command at development or production data because the test
creates and deletes real event and Auth records.

## Test cases

- Unit: [`tests/unit/atomic/events/TEST_CASES.md`](../../../../tests/unit/atomic/events/TEST_CASES.md)
- Integration: [`tests/integration/atomic/events/TEST_CASES.md`](../../../../tests/integration/atomic/events/TEST_CASES.md)
