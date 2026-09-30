# Events service

Atomic FastAPI service for event requests. It owns `events.events` and never
queries another service's tables.

## Endpoints

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| `POST` | `/events/drafts` | `events:save_draft` | Create an incomplete draft. |
| `POST` | `/events` | `events:create` | Create an immediately submitted request. |
| `GET` | `/events` | `events:view_own` | List the authenticated organiser's event requests, most recently updated first. |
| `GET` | `/events/options` | `events:create` | The venue requirement option sets for the organiser's form: `room_layouts`, `facilities`, `accessibility`. |
| `GET` | `/events/{event_id}` | `events:view_own` | Return one event owned by the authenticated caller. |
| `PATCH` | `/events/{event_id}` | `events:update_own_draft` | Update supplied fields on an owned event — draft or already submitted. |
| `POST` | `/events/{event_id}/submit` | `events:submit_own` | Replace the business fields of an owned draft *or returned request* with a complete submission and (re)submit it. |
| `GET` | `/events/assigned` | `events:view_assigned` | List the authenticated coordinator's assigned event requests, most recently updated first. |
| `GET` | `/events/assigned/{event_id}` | `events:view_assigned` | Return one event assigned to the authenticated coordinator. |
| `POST` | `/events/{event_id}/decision` | `events:decide` | Record the assigned coordinator's approve/reject/return decision. See [Decisions](#decisions-s-14). |
| `GET` | `/events/health` | none | Gateway-compatible liveness alias. |
| `GET` | `/health` | none | Liveness check. |

Internal, composite-only routes — no Kong route, unauthenticated at this
layer because they are unreachable from a browser; only the `event_requests`
composite calls them. See [Internal routes](#internal-routes-composite-only).

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/events/coordinator-load` | Conflict and current load for a set of coordinators against a requested window. Takes an optional `exclude_event_id` so rechecking an existing event never conflicts with itself. |
| `POST` | `/events/technical-support-load` | Conflict and current live workload for candidate Technical Support Staff against a requested window. |
| `POST` | `/events/overlapping` | S-44: the `planning` and `confirmed` events overlapping a window, for the `equipment_requirements` composite's availability check. |
| `PUT` | `/events/{event_id}/technical-support/internal` | Persist a planning event's Technical Support requirement and automatic assignment for its currently assigned Coordinator. |
| `POST` | `/events/internal` | Create an already-submitted event with a caller-supplied `organiser_id` and `assigned_coordinator_id`. |
| `POST` | `/events/{event_id}/submit/internal` | Submit an owned draft with a caller-supplied `organiser_id` and `assigned_coordinator_id`. |
| `PATCH` | `/events/{event_id}/internal` | Update an owned event with a caller-supplied `organiser_id`, optionally reassigning `assigned_coordinator_id` in the same write. |

All event endpoints except health authenticate the `sb_access_token` and
`sb_refresh_token` cookies issued by the users service, then authorize the
trusted `app_metadata.role` against the permission shown above.

The centralized policy recognizes every project role. All may view their own
frontend dashboard; Event Organiser and Event Coordinator workflows are
currently defined:

| Role | Permissions |
| --- | --- |
| `event_organiser` | `dashboard:view`, `events:create`, `events:save_draft`, `events:view_own`, `events:update_own_draft`, `events:submit_own` |
| `event_coordinator` | `dashboard:view`, `events:view_assigned`, `events:decide` |
| `venue_staff` | `dashboard:view` |
| `technical_support` | `dashboard:view` |
| `attendee` | `dashboard:view` |

`events:view_assigned` is read-only. `events:decide` (S-14) is the one write
a coordinator can make: approve, reject, or return a request assigned to
them — never edit its fields directly.

The remaining internal and attendee roles intentionally receive no
speculative event permissions. Their permissions can expand when a
corresponding project story defines a workflow.

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
| `start_time` | time or null | If both times exist and the event is single-day, must be before `end_time`. |
| `end_date` | `YYYY-MM-DD` or null | Optional. If both dates exist, must be on or after `start_date`. |
| `end_time` | time or null | If both times exist and the event is single-day, must be after `start_time`. |
| `expected_attendance` | integer or null | Greater than zero when present. |
| `venue` | string or null | The organiser's venue preference, free text. Blank text becomes null. |
| `special_requirements` | string or null | Anything the fixed fields do not cover — registration arrangements, catering, security. Blank text becomes null. |
| `room_layout` | string or null | From the venue layout set. |
| `required_facilities` | array of string | From the venue facility set. Defaults to `[]`. |
| `required_accessibility` | array of string | From the venue accessibility set. Defaults to `[]`. |

**Venue requirements (S-36).** `room_layout`, `required_facilities` and
`required_accessibility` say what a venue must offer. They use the venue
catalogue's fixed sets — repeated in [`schemas.py`](schemas.py) and as check
constraints in [`events.sql`](../../../sql/events.sql) — so the
`venue_bookings` composite can check each venue against them. The Coordinator
books the actual venue; `venue` is only the organiser's preference.

An empty draft is valid:

```json
{}
```

`PATCH` changes only fields present in the request, and works on a submitted
event as well as a draft — submitting a request does not lock it. The status
of the record is never changed by a PATCH; a submitted event stays
`submitted` after the edit. The one difference: on a submitted event, the
resulting record is checked against the *submitted*-required rules below (not
the permissive draft ones), so a PATCH cannot null out a field the database
requires — that comes back as `422`, the same as any other validation
failure, rather than reaching the database's own constraint as an opaque
`500`.

### Submitted fields

`POST /events` and `POST /events/{event_id}/submit` take the same body.
`/submit` covers both a draft's first submission and resubmitting a
`returned` request — see [Status model](#status-model-s-14).

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `name` | string | yes | Nonblank. |
| `purpose` | string | yes | Nonblank. |
| `start_date` | `YYYY-MM-DD` | yes | |
| `start_time` | time | yes | Before `end_time` when the event is single-day. |
| `end_date` | `YYYY-MM-DD` | yes | On or after `start_date`. |
| `end_time` | time | yes | After `start_time` when the event is single-day (`end_date == start_date`); unconstrained relative to `start_time` for a multi-day event. |
| `expected_attendance` | integer | yes | Greater than zero. |
| `venue` | string or null | no | The organiser's venue preference. Blank becomes null. |
| `special_requirements` | string or null | no | Free text. Blank becomes null. |
| `room_layout` | string or null | no | One of `theatre`, `classroom`, `boardroom`, `u_shape`, `banquet`, `cocktail`. |
| `required_facilities` | array of string | no | From the venue facility set; repeats dropped. Defaults to `[]`. |
| `required_accessibility` | array of string | no | From the venue accessibility set; repeats dropped. Defaults to `[]`. |

```json
{
  "name": "Alumni networking evening",
  "purpose": "Connect alumni with graduating students",
  "start_date": "2026-10-20",
  "start_time": "18:00",
  "end_date": "2026-10-20",
  "end_time": "21:00",
  "expected_attendance": 120,
  "venue": "Main auditorium",
  "special_requirements": "Registration closes a week before",
  "submitted_at": "2026-09-17T10:04:11.502Z",
  "special_requirements": "Registration closes a week before",
  "submitted_at": null
}
```

## Response

> `submitted_at` is set by the service when a request is submitted and is null
> on a draft. Like `organiser_id` and `status` it is never read from the request
> body — a client able to choose its own submission time could backdate one.
> With `organiser_id` it is the record of who submitted the request and when.


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
  "start_time": "18:00:00",
  "end_date": "2026-10-20",
  "end_time": "21:00:00",
  "expected_attendance": 120,
  "venue": "Main auditorium",
  "room_layout": "theatre",
  "required_facilities": ["projector"],
  "required_accessibility": ["wheelchair_access"],
  "assigned_coordinator_id": null,
  "technical_support_required": false,
  "technical_support_details": null,
  "assigned_technical_support_id": null,
  "technical_support_assigned_at": null,
  "decision": null,
  "decision_reason": null,
  "decision_comment": null,
  "decided_at": null,
  "created_at": "2026-09-14T00:00:00Z",
  "updated_at": "2026-09-14T00:00:00Z"
}
```

`assigned_coordinator_id` is null until the `event_requests` composite
assigns a coordinator on submission; an organiser's own request can never set
it. See [Internal routes](#internal-routes-composite-only).

The four `technical_support_*` fields are controlled by the S-43 assignment
flow. They record whether support was explicitly requested, the optional
Coordinator notes, the automatically selected staff member, and the first
assignment time. Clients cannot set these fields through normal event create
or update payloads.

`decision`, `decision_reason`, `decision_comment`, and `decided_at` are all
null until the assigned coordinator decides (S-14) — see
[Decisions](#decisions-s-14).

`GET /events` returns an array containing only rows whose `organiser_id`
matches the verified user. An organiser with no requests receives `[]`.

`GET /health` returns:

```json
{"status": "ok"}
```

## Status model (S-14, S-36, S-43)

```
draft ──submit──> submitted ──approve──> planning   (venue/equipment planning)
                    ▲   │ ────reject───> rejected   (terminal)
                    │   └─────return───> returned
                    └──edit + resubmit──────┘
```

`confirmed` is now a valid stored state because S-43 must include confirmed
events when checking Technical Support commitments. S-43 does not introduce a
transition into it. `completed` and `cancelled` remain later workflow states.

- **draft** — incomplete, editable, never assigned a coordinator.
- **submitted** — complete, assigned a coordinator, awaiting their decision.
  Still editable; editing does not change the status.
- **planning** — the coordinator approved the request (S-36: an approval
  moves the event here; there is no `approved` status, only the recorded
  `decision=approved`). Venue booking requests are made against events in
  this status. No further submit action; edits still go through the same
  `PATCH`.
- **confirmed** — a live commitment for Technical Support workload and
  overlap checks. This story defines how it is counted, not how an event
  moves from planning to confirmed.
- **rejected** — the coordinator's negative decision. **Closed
  permanently**: `PATCH` and `POST /events/{event_id}/submit` both answer
  `409` for a rejected event, with no exception.
- **returned** — the coordinator asked for changes. The organiser edits it
  with the same `PATCH` (still held to the submitted-required fields, same
  as `submitted`) and resubmits it with the same
  `POST /events/{event_id}/submit` used for a draft's first submission —
  it is the same record throughout, never a new one. Resubmitting clears
  `decision`/`decision_reason`/`decision_comment`/`decided_at` back to null
  and sets a fresh `submitted_at`.

A coordinator's assigned submitted **or planning** events both occupy their
calendar for the purposes of routing a new request (see
[`POST /events/coordinator-load`](#post-eventscoordinator-load)); returned
and rejected do not, since neither is a live commitment.

## Decisions (S-14)

**`POST /events/{event_id}/decision`** — only the coordinator this request
is assigned to may call it, and only while it is `submitted`.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `decision` | `"approved"` \| `"rejected"` \| `"returned"` | yes | |
| `reason` | string | required for `rejected`/`returned`, forbidden for `approved` | Nonblank. |
| `comment` | string | optional, only accepted for `returned` | A clarification/amendment note for the organiser. |

```json
{"decision": "returned", "reason": "Missing risk assessment", "comment": "Please attach the venue's fire safety form"}
```

Returns `200` with the updated event, `decided_at` set. `status` becomes
`planning` for `approved`, and matches the decision for `rejected` and
`returned`. `409` if the request is not currently `submitted` —
including a decision already made, since a decision cannot be changed once
recorded. `404` if the caller is not the assigned coordinator.

## Internal routes (composite-only)

These six exist for the `event_requests` composite service
([`backend/services/composite/event_requests`](../../composite/event_requests/README.md)),
which is the only caller — there is no Kong route for any of them, and they
carry no session-derived authorization of their own. A browser cannot reach
them from outside the Docker network.

### `POST /events/coordinator-load`

```json
{
  "coordinator_ids": ["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"],
  "start_date": "2026-10-20",
  "start_time": "18:00",
  "end_date": "2026-10-20",
  "end_time": "21:00"
}
```

For each id in `coordinator_ids`, reports whether that coordinator has an
assigned **submitted or planning** event overlapping the given window at all
(touching endpoints do not count as overlapping), and how many such events
are currently assigned to them in total, independent of the window:

```json
[
  {
    "coordinator_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "conflict": false,
    "assigned_count": 2
  }
]
```

Draft, returned, and rejected events are never live commitments, so they
never appear in either figure — see [Status model](#status-model-s-14).

`exclude_event_id` matters when rechecking an event that already has this
window and this assignment stored: without it, the event would always
conflict with its own row.

### `POST /events/technical-support-load`

Takes `staff_ids` and the same four date/time fields as coordinator load. For
each candidate it reports `staff_id`, strict-overlap `conflict`, and
`assigned_count`. Only existing `planning` and `confirmed` assignments count;
draft, submitted, returned, rejected, completed and cancelled events do not.
An event ending exactly when another begins is not a conflict.

### `POST /events/overlapping`

S-44, called by the `equipment_requirements` composite (not `event_requests`).
Takes exactly `start_date`, `start_time`, `end_date` and `end_time`; the end
must be after the start, or it is `422`. The window may span days.

```json
{"start_date": "2026-11-12", "start_time": "09:00", "end_date": "2026-11-12", "end_time": "12:00"}
```

`200` with the overlapping events in start order, each shaped:

```json
{"id": "…", "name": "Alumni talk", "status": "planning", "start_date": "2026-11-12", "start_time": "10:00:00", "end_date": "2026-11-12", "end_time": "11:00:00"}
```

Only `planning` and `confirmed` events are returned: their equipment
requirements reserve equipment. An event ending exactly when the window
starts, or starting exactly when it ends, is not an overlap. `500` with the
usual safe detail if storage fails.

### `PUT /events/{event_id}/technical-support/internal`

Takes `coordinator_id`, optional `technical_support_details`, and an optional
automatically selected `assigned_technical_support_id`. The event must still
be in `planning` and assigned to that Coordinator. The write always records
`technical_support_required=true`; a null staff id records the successful
"required but currently unassigned" state.

Once assigned, the staff id is fixed. Calling the route again never replaces
it, and an unchanged request performs no storage update. Updating the notes
preserves both the staff id and the original
`technical_support_assigned_at`. Conditional update filters reject a stale
event or concurrent assignment with `409` rather than silently overwriting it.

### `POST /events/internal` and `POST /events/{event_id}/submit/internal`

Same body as the public `POST /events` / `POST /events/{event_id}/submit`,
plus two fields the public routes forbid because the organiser's own request
must never set them:

| Field | Type | Purpose |
| --- | --- | --- |
| `organiser_id` | uuid | The organiser the composite already authenticated — not derived from a session here. |
| `assigned_coordinator_id` | uuid | The coordinator the composite already chose. |

Same responses and status codes as the public routes they mirror
(`201`/`200`, `404` for another organiser's draft, `409` for an event that is
not currently `draft` or `returned`).

### `PATCH /events/{event_id}/internal`

Same body as the public `PATCH /events/{event_id}` (every field optional),
plus `organiser_id` (required, same reason as above) and
`assigned_coordinator_id` (optional — included only when the composite is
changing it). Same responses as the public route: `200` with the updated
event, `404` for another organiser's event.

## Errors

| Status | When |
| --- | --- |
| `401` | No valid session; expired access tokens are refreshed when possible. |
| `403` | The trusted role is missing, unknown, or lacks the route's permission. |
| `404` | The event does not exist, belongs to another user, or (for `/decision`) is not assigned to the calling coordinator. |
| `409` | `POST /events/{event_id}/submit` on an event that is not `draft` or `returned`; `PATCH` or `/submit` on a `rejected` event (closed permanently); `POST /events/{event_id}/decision` on an event that is not currently `submitted`; an internal Technical Support write when the event is no longer the Coordinator's planning event or changed concurrently. Editing a `submitted`/`returned`/`planning` event via `PATCH` is otherwise allowed and does not 409. |
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
