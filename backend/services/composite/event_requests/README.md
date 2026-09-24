# Event requests service

Composite FastAPI service. Owns no table of its own — every write ends up in
`events.events` by way of the events service. Orchestrates the one workflow
that spans the `events` and `users` entities: when an event organiser submits
a request, this service routes it to an event coordinator who has no other
assigned event overlapping the requested date and time.

Story: S-12 — event coordinator assignment.

## Endpoints

| Method | Path | Does |
| --- | --- | --- |
| `POST` | `/event-requests` | Submits a brand-new request (equivalent to the events service's `POST /events`), assigning a coordinator as part of submission. |
| `POST` | `/event-requests/{event_id}/submit` | Submits an existing draft the caller owns (equivalent to `POST /events/{event_id}/submit`), assigning a coordinator the same way. |
| `PATCH` | `/event-requests/{event_id}` | Edits an owned event (equivalent to `PATCH /events/{event_id}`), rechecking the assigned coordinator when a submitted event's date/time actually changes. |
| `GET` | `/event-requests/health` | Gateway-compatible liveness alias. |
| `GET` | `/health` | Liveness check. |

Draft creation, listing, and reading are unaffected by this service and still
go straight to the events service at `/api/events`. Editing is routed through
here now too — not because every edit needs it, but because *some* edits do,
and the frontend has no way to know which without asking: an edit to a draft,
or to any field but the four date/time ones, is a plain passthrough (this
service adds one extra hop and nothing else); an edit that actually changes a
submitted event's window is where the coordinator gets rechecked.

## Request

Both `POST` endpoints take the same body as the events service's own
submitted-event routes:

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `name` | string | yes | Nonblank. |
| `purpose` | string | yes | Nonblank. |
| `start_date` | `YYYY-MM-DD` | yes | |
| `start_time` | time | yes | Before `end_time` when the event is single-day. |
| `end_date` | `YYYY-MM-DD` | yes | On or after `start_date`. |
| `end_time` | time | yes | After `start_time` when the event is single-day. |
| `expected_attendance` | integer | yes | Greater than zero. |
| `venue` | string | yes | Nonblank. |
| `equipment_requests` | object | no | Values must be positive integers; defaults to `{}`. |
| `accessibility_requirements` | string or null | no | Blank text becomes null. |
| `special_requirements` | string or null | no | Free text. Blank becomes null. |

`PATCH /event-requests/{event_id}` takes the same fields, all optional —
supply only what changes, the same contract as the events service's own
`PATCH /events/{event_id}`.

The caller never supplies `organiser_id` or `assigned_coordinator_id` on any
of these — both are set by this service, the first from the verified
session, the second by the assignment logic below.

## Response

`201` from `POST /event-requests`, `200` from the submit-existing-draft route
— both return the created/updated event exactly as the events service shaped
it, `assigned_coordinator_id` included:

```json
{
  "id": "33333333-3333-4333-8333-333333333333",
  "organiser_id": "11111111-1111-4111-8111-111111111111",
  "status": "submitted",
  "assigned_coordinator_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "...": "the rest of the event fields, see the events service README"
}
```

### Assignment logic

1. Fetch every account with role `event_coordinator` from the users service.
2. Ask the events service which of them have no assigned **submitted** event
   overlapping the requested window at all (a request starting exactly when
   another ends is not a conflict).
3. Among the conflict-free coordinators, pick whoever currently has the
   fewest assigned submitted events. Ties are broken at random, so load
   spreads out over many requests even when no one is busy yet.
4. If no coordinator is conflict-free — including when no coordinator
   accounts exist at all — the request is rejected. Nothing is created.

### Recheck logic (`PATCH`)

An edit only reaches any of this when the event being edited is currently
`submitted` **and** the request actually changes `start_date`, `start_time`,
`end_date`, or `end_time` to a different value than it already has —
resubmitting the same value, or editing any other field, skips straight to
a plain passthrough of the edit.

1. Ask the events service whether the *currently* assigned coordinator has a
   conflict against the new window (excluding this event's own row from the
   check — see the events service's `exclude_event_id`).
2. Still free → the edit is applied as a plain passthrough; the assignment
   does not change.
3. Conflicts → run the same assignment logic as a fresh submission
   (excluding this event's own row throughout), and write the edit and the
   new `assigned_coordinator_id` together in one update.
4. No coordinator is free even after that → the edit is rejected. Nothing
   changes, including the fields that had nothing to do with scheduling.

### Errors

| Status | When |
| --- | --- |
| `401` | No valid session. |
| `403` | The session's trusted role is not `event_organiser`. |
| `404` | The event does not exist or is not owned by the caller. |
| `409` | No event coordinator is free for the requested window, or the draft has already been submitted. |
| `422` | The request body is invalid — checked here, before either downstream service is called. |
| `502` | The users or events service could not be reached or answered unexpectedly. |

`GET /health` returns:

```json
{"status": "ok"}
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `USERS_SERVICE_URL` | Base URL of the users service, e.g. `http://users:8001`. |
| `EVENTS_SERVICE_URL` | Base URL of the events service, e.g. `http://events:8002`. |

Both are listed in the root [`.env.example`](../../../../.env.example).

## Running

### Development

Load the root `.env` into the shell (with `USERS_SERVICE_URL` and
`EVENTS_SERVICE_URL` pointed at `localhost` rather than the compose service
names), then:

```bash
cd backend/services/composite/event_requests
uvicorn app:app --reload --port 8100
```

The users and events services must already be running — this service calls
both. The browser reaches this service through Kong at `/api/event-requests`;
it is also published directly on `localhost:8100` for service-level
integration tests.

### Unit tests

From the repository root:

```bash
pip install -r backend/services/composite/event_requests/requirements.txt -r tests/requirements.txt
pytest tests/unit/composite/event_requests
```

Both outbound clients are replaced with fakes, so the unit tests need no
environment file, database, Docker, or network.

### Integration tests

Needs the whole stack — both atomic services, this one, and Kong — running
against the test Supabase project:

```bash
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/composite/event_requests
```

Do not point either command at development or production data: the tests
create and delete real event and Auth records.

## Test cases

- Unit: [`tests/unit/composite/event_requests/TEST_CASES.md`](../../../../tests/unit/composite/event_requests/TEST_CASES.md)
- Integration: [`tests/integration/composite/event_requests/TEST_CASES.md`](../../../../tests/integration/composite/event_requests/TEST_CASES.md)
