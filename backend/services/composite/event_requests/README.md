# Event requests service

Composite FastAPI service. Owns no table of its own — every write ends up in
`events.events` by way of the events service. Orchestrates the one workflow
that spans the `events` and `users` entities: when an event organiser submits
a request, this service routes it to an event coordinator who has no other
assigned event overlapping the requested date and time.

Story: S-12 — event coordinator assignment. S-14 — coordinator decisions —
extends this service to also handle resubmitting a request a coordinator
returned for amendment. S-43 adds explicit, automatic Technical Support
assignment for planning events.

## Endpoints

| Method | Path | Does |
| --- | --- | --- |
| `POST` | `/event-requests` | Submits a brand-new request (equivalent to the events service's `POST /events`), assigning a coordinator as part of submission. |
| `POST` | `/event-requests/{event_id}/submit` | Submits a draft for the first time, *or* resubmits a `returned` request (equivalent to `POST /events/{event_id}/submit`) — see [Assignment logic](#assignment-logic). |
| `PATCH` | `/event-requests/{event_id}` | Edits an owned event (equivalent to `PATCH /events/{event_id}`), rechecking the assigned coordinator when a submitted event's date/time actually changes. |
| `GET` | `/event-requests/{event_id}/technical-support-assignment` | Returns the assigned Coordinator's persisted Technical Support request state without allocating anyone. |
| `POST` | `/event-requests/{event_id}/technical-support-assignment` | Explicitly requests Technical Support for the assigned planning event and automatically selects eligible staff when available. |
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
| `venue` | string or null | no | The organiser's venue preference. Blank becomes null. |
| `room_layout` | string or null | no | From the venue layout set. |
| `required_facilities` | array of string | no | From the venue facility set. Defaults to `[]`. |
| `required_accessibility` | array of string | no | From the venue accessibility set. Defaults to `[]`. |
| `special_requirements` | string or null | no | Free text. Blank becomes null. |

`PATCH /event-requests/{event_id}` takes the same fields, all optional —
supply only what changes, the same contract as the events service's own
`PATCH /events/{event_id}`.

The caller never supplies `organiser_id` or `assigned_coordinator_id` on any
of these — both are set by this service, the first from the verified
session, the second by the assignment logic below.

The Technical Support `POST` accepts only optional notes:

```json
{"support_details": "Wireless microphone setup and sound check"}
```

Blank notes become null. There is deliberately no staff-id field: the client
cannot choose or replace the assignee.

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

`POST /event-requests/{event_id}/submit` picks a coordinator differently
depending on what the event currently is:

**A draft's first submission** — no prior assignment to consider:

1. Fetch every account with role `event_coordinator` from the users service.
2. Ask the events service which of them have no assigned **submitted or
   planning** event overlapping the requested window at all (a request
   starting exactly when another ends is not a conflict).
3. Among the conflict-free coordinators, pick whoever currently has the
   fewest assigned submitted/planning events. Ties are broken at random, so
   load spreads out over many requests even when no one is busy yet.
4. If no coordinator is conflict-free — including when no coordinator
   accounts exist at all — the request is rejected. Nothing is created.

**Resubmitting a `returned` request (S-14)** — it already has a
coordinator, so continuity comes first:

1. Ask the events service whether the *currently* assigned coordinator has a
   conflict against the (possibly edited) window, excluding this event's own
   row from the check.
2. Still free → resubmitted to the same coordinator.
3. Conflicts → run the fresh-pick logic above instead (excluding this
   event's own row throughout).
4. No coordinator is free even after that → the resubmission is rejected.
   Nothing changes.

A coordinator's own decision (`POST /events/{event_id}/decision`) is not
part of this service at all — it never touches assignment, so it goes
straight to the events service. See the events service's
[Decisions](../../atomic/events/README.md#decisions-s-14).

### Technical Support assignment (S-43)

Only the event's currently assigned Coordinator can read or request this
assignment, and a new request is accepted only while the event is `planning`.
Equipment requirements do not trigger it; the Coordinator must explicitly use
this endpoint.

1. Fetch accounts whose trusted Auth `app_metadata.role` is
   `technical_support` from the users service.
2. Ask the events service for each candidate's strict-overlap conflict and
   total `planning`/`confirmed` assignment count.
3. Exclude conflicting candidates, then choose the least-loaded remaining
   candidate; break ties by ascending UUID. The selection function is isolated
   so a future strategy can replace it without changing the route contract.
4. Persist the requirement, optional notes, and selected id through the events
   service. If nobody is eligible and free, persist the requirement and notes
   with a null assignment and return the successful `unassigned` state.

An existing assignment is fixed and idempotent. Repeating the request does not
re-run allocation or change its timestamp; changing only the notes preserves
the same staff id and first-assigned time.

Both GET and POST return:

```json
{
  "technical_support_required": true,
  "support_details": "Wireless microphone setup and sound check",
  "assigned_technical_support_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "technical_support_assigned_at": "2026-09-29T04:00:00Z",
  "assignment_state": "assigned",
  "assigned_staff": {
    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "name": "Technical Support One",
    "email": "support@example.com"
  },
  "message": "Technical Support Staff assigned"
}
```

`assignment_state` is `not_required`, `assigned`, or `unassigned`.
`assigned_staff` is null unless an assignment exists. The unassigned response
is a `200`, not an error: it explicitly says support is required but no
eligible staff member is currently available.

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
| `403` | The session's trusted role is not permitted for the endpoint: organiser for submission/edit flows, assigned Event Coordinator for S-43. |
| `404` | The event does not exist, is not owned by the organiser, or is not assigned to the calling Coordinator. |
| `409` | No event coordinator is free for a submission window; the draft has already been submitted; or Technical Support was requested after the target stopped being the caller's planning event. |
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
