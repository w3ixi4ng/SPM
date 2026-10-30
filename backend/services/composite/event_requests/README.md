# Event requests service

Composite FastAPI service. It owns no storage and coordinates the users,
events, and notifications atomic services.

Story S-83 changes event assignment to an explicit Event Coordinator Lead
action. A submitted request enters an unassigned queue. A Lead may choose any
trusted Event Coordinator; schedule overlap and current workload do not block
that choice. Assignment creates persistent in-app notifications for the
Coordinator and Event Organiser. No email or external notification is sent.

Story S-84 lets the Lead reassign an active event to any other trusted Event
Coordinator. Schedule conflicts do not block that decision. Reassignment
transfers event access and persistently notifies the former Coordinator, new
Coordinator, and Event Organiser.

Story S-85 adds a read-only oversight view. It groups the Lead's active
assigned events under their current Coordinator, includes trusted Coordinators
with no work in that scope, and exposes an assignment count for each group.

S-88 lets the currently assigned Coordinator request reassignment with a
reason. Only the Lead who assigned that event sees the request. The request
does not change ownership; the existing S-84 action does. Events without a
recorded assigning Lead are excluded from Lead views and cannot receive a
new request until their provenance is resolved.

S-93 reads `app_metadata.coordinator_active` from the Users service's trusted
Auth Admin listing. Missing or `true` means available; `false` and malformed
values exclude a Coordinator from new S-83/S-84 assignments. Existing work
remains visible. The selected-Coordinator inventory below shows limited active
event summaries across Leads; only the recorded responsible Lead may transfer
an event. An inactive owner's warning remains until a successful S-84 transfer.

The existing S-43 Technical Support workflow remains available to assigned
Event Coordinators.

## Endpoints

| Method | Path | Role | Does |
| --- | --- | --- | --- |
| `POST` | `/event-requests` | Event Organiser | Creates a submitted, unassigned request. |
| `POST` | `/event-requests/{event_id}/submit` | Event Organiser | Submits a draft unassigned, or resubmits a returned request while preserving its assignment. |
| `PATCH` | `/event-requests/{event_id}` | Event Organiser | Updates an owned request without automatic assignment or reassignment. |
| `GET` | `/event-requests/{event_id}/change-requests` | Owning Organiser or assigned Coordinator | Returns accepted event data, request history, current Equipment requirements and selectable items for the Organiser. |
| `POST` | `/event-requests/{event_id}/change-requests` | Owning Event Organiser | S-59: submits a pending comparison without changing accepted arrangements. |
| `GET` | `/event-requests/unassigned` | Event Coordinator Lead | Lists submitted requests whose `assigned_coordinator_id` is null, oldest submission first, including organiser details. |
| `GET` | `/event-requests/coordinators` | Event Coordinator Lead | Lists trusted, active Event Coordinator accounts available for manual selection. |
| `GET` | `/event-requests/coordinators/{coordinator_id}/active-events` | Event Coordinator Lead | Returns limited active-event summaries for the selected Coordinator across Leads, with scope and warning indicators. |
| `POST` | `/event-requests/{event_id}/assignment` | Event Coordinator Lead | Assigns the selected Coordinator and creates both notifications. |
| `GET` | `/event-requests/assigned-active` | Event Coordinator Lead | Lists active events assigned by that Lead with organiser, current Coordinator, and assignment version. |
| `GET` | `/event-requests/coordinator-overview` | Event Coordinator Lead | Groups active events assigned by that Lead under every Coordinator. |
| `POST` | `/event-requests/{event_id}/reassignment-request` | Assigned Event Coordinator | Saves a reasoned request without changing ownership. |
| `GET` | `/event-requests/reassignment-requests/mine` | Event Coordinator | Lists the caller's pending and actioned request history, even after transfer. |
| `GET` | `/event-requests/reassignment-requests/lead` | Event Coordinator Lead | Lists requests for events assigned by the caller, with requester profiles. |
| `POST` | `/event-requests/{event_id}/reassignment` | Responsible Event Coordinator Lead | Transfers an active event to another Coordinator and creates three notifications. |
| `GET` | `/event-requests/{event_id}/technical-support-assignment` | Assigned Event Coordinator | Reads the event's Technical Support state. |
| `POST` | `/event-requests/{event_id}/technical-support-assignment` | Assigned Event Coordinator | Requests and automatically allocates Technical Support when possible. |
| `POST` | `/event-requests/{event_id}/cancellation-decision` | Assigned Event Coordinator | S-61: approve (cancel the event and release its venue bookings) or decline an Organiser's cancellation request. |
| `GET` | `/event-requests/{event_id}/history` | Assigned Event Coordinator, or any Event Coordinator Lead | S-82: who changed or decided what on the event, and when, with names. |
| `GET` | `/health` | Infrastructure | Liveness check. |

`GET /event-requests/health` is the gateway-compatible health alias.

### S-59 proposal contract

`POST /event-requests/{event_id}/change-requests` takes `values` with all
current/proposed date and time fields (`start_date`, `start_time`, `end_date`,
`end_time`), `expected_attendance`, nullable `venue`,
`special_requirements`, `room_layout`, `required_facilities` and
`required_accessibility`; `equipment` is an array of
`{equipment_item_id, required_quantity}`. The composite reads accepted
Equipment requirements over HTTP, validates changed items against the active
catalogue, and sends both snapshots to the Events owner through a trusted
service request. It does not write Equipment. `201` returns the saved pending
request; `401` requires sign-in, `403` requires the Organiser role, `404`
means the event is not owned, `409` means ineligible/stale/duplicate, `422`
means invalid or unchanged data, and `502` means a dependency failed.

The GET response is `{event, requests, equipment, equipment_options}`; only
the current assigned Coordinator or owning Organiser can read it. The
submitted state may be unassigned; the request stays pending and becomes
visible to the Coordinator after S-83 assignment. S-60 owns any later impact
review or acceptance.

## Event submission and editing

Both submission endpoints accept:

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `name` | string | yes | Nonblank. |
| `purpose` | string | yes | Nonblank. |
| `start_date` | `YYYY-MM-DD` | yes | |
| `start_time` | time | yes | Before `end_time` for a single-day event. |
| `end_date` | `YYYY-MM-DD` | yes | On or after `start_date`. |
| `end_time` | time | yes | After `start_time` for a single-day event. |
| `expected_attendance` | positive integer | yes | |
| `venue` | string or null | no | Organiser preference. |
| `room_layout` | string or null | no | One of the events service's layout options. |
| `required_facilities` | array of strings | no | Defaults to `[]`. |
| `required_accessibility` | array of strings | no | Defaults to `[]`. |
| `special_requirements` | string or null | no | |

`PATCH` accepts the same fields, all optional. The composite derives
`organiser_id` from the verified session. New submissions always send
`assigned_coordinator_id: null`; the Organiser cannot choose a Coordinator.

Submission returns the events service's complete event. A new request returns
`201`; draft submission, resubmission, and edits return `200`.

## Manual assignment (S-83)

Assignment accepts exactly one field:

```json
{"coordinator_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}
```

The id must belong to an account whose trusted Auth role is
`event_coordinator` and whose `coordinator_active` value is available. The Lead may choose any such account. This workflow does
not query coordinator load and does not reject schedule conflicts.

The Events atomic assignment writes require a separate
`X-Assignment-Service-Token` matching `ASSIGNMENT_SERVICE_SECRET`. The composite
adds it only after checking Users eligibility. A Lead session alone cannot
write through the published Events port. Configure the same independent,
random secret in the Events and event_requests services; keep it server-side.

For older events without `assigning_lead_id`, the S-93 inventory reports
`scope: legacy` and `actionable: false`. A controlled repair requires an
operator to verify the original assignment audit and responsible Lead, record
an approved change ticket, then update provenance through an audited admin
database procedure. Do not infer the Lead from the current Coordinator or
grant temporary access to every Lead. Recheck S-85/S-88 scope after repair.

The events service conditionally writes the assignment only while the request
is still `submitted` and unassigned. The successful response is the updated
event plus `assignment_created`, which is `true` for the first write and
`false` when the same Coordinator assignment is retried.
It records the authenticated Lead's ID as `assigning_lead_id`. That value
remains the event's supervisory scope after a Coordinator transfer.

After the event write, the composite asks the notifications service to persist
exactly two `event_assignment` notifications:

- one for the newly assigned Event Coordinator;
- one for the Event Organiser.

Each row has the stable key
`event_assignment:{event_id}:{recipient_id}`. The notifications service
upserts on that unique key. Repeating the same assignment therefore leaves
exactly one notification per recipient.

The event and notification writes are separate service operations. If event
assignment succeeds but notification persistence fails, this endpoint returns
`502`. Retrying the same request preserves the existing Coordinator, reruns
the idempotent notification batch, creates any missing row, and does not
duplicate an existing row. A retry with a different Coordinator returns
`409`.

## Coordinator reassignment (S-84)

Reassignment accepts the selected Coordinator plus the current owner and
version displayed by the Lead:

```json
{
  "coordinator_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  "expected_coordinator_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "expected_assignment_version": 0
}
```

The selected id must be a different trusted, active `event_coordinator`.
Events are eligible while `submitted`, `under_review`, `returned`, `planning`,
`pending_safety_check`, `confirmed`, `preparation`, `safety_rejected`, or
`safety_changes_requested`; draft, rejected, cancelled, unassigned, missing,
or stale targets are not changed.
The atomic write compares the expected owner and version, then increments the
version. It deliberately performs no schedule conflict check; the composite
checks trusted Auth availability before sending the write.
The caller must be the event's recorded assigning Lead. Another Lead gets
`404`; an older event with no recorded Lead returns `409`.

A successful transfer creates one persistent `event_reassignment`
notification for the former Coordinator, new Coordinator, and Organiser.
Keys are `event_reassignment:{event_id}:{version}:{recipient_id}`. If the
event write succeeds but notification persistence fails, the endpoint returns
`502`; repeating the identical request recognizes the committed transition
and upserts any missing rows without duplicates. Once a newer transfer has
incremented the version, an old retry returns `409` and cannot move the event
back.

## Reassignment requests (S-88)

`POST /event-requests/{event_id}/reassignment-request` accepts only
`{"reason":"Cannot cover the November event"}`. `reason` is a required,
nonblank string of at most 2,000 characters. The Events service checks the
verified Coordinator session and current event assignment, then stores a
request. Its database trigger locks the event during insertion, preventing a
request for an owner who was concurrently replaced. A partial unique index
allows only one pending request per event; a duplicate returns `409`.

Success returns `201`:

```json
{"id":"ffffffff-ffff-4fff-8fff-ffffffffffff","event_id":"33333333-3333-4333-8333-333333333333","event_name":"November Forum","requester_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","assigning_lead_id":"dddddddd-dddd-4ddd-8ddd-dddddddddddd","assignment_version":2,"reason":"Cannot cover the November event","status":"pending","created_at":"2026-10-25T00:00:00Z","actioned_at":null}
```

Both list endpoints take no body or query parameters and return arrays of
these rows. The Lead's list also includes `requester` with `id`, `name`, and
`email`. The Events service derives each list filter from the verified
session, so another Lead or Coordinator cannot choose a different ID. When
S-84 changes the current owner, the Events database trigger changes the
matching pending row to `actioned` and sets `actioned_at` in the same
transaction. Failed transfers leave it pending. The original requester can
still read it from `/mine` after losing event access. Historic rows are kept.

Failures use `{"detail":"..."}`: `401` means no session, `403` means the
role is not allowed, `404` means the event is missing or belongs to another
Coordinator or Lead, `409` means a pending request exists, assignment changed,
or no responsible Lead is recorded, `422` means invalid reason, and `502`
means a required atomic service is unavailable.

## Coordinator oversight (S-85)

`GET /event-requests/coordinator-overview` accepts no parameters or body. Only
an authenticated `event_coordinator_lead` may call it. Active means
`submitted`, `under_review`, `returned`, `planning`, `pending_safety_check`,
`confirmed`, `preparation`, `safety_rejected`, or
`safety_changes_requested`, and an
event must have a current `assigned_coordinator_id`. Unassigned, draft,
rejected, cancelled, and completed events are excluded by Events before the
composite groups them.
It returns only events whose `assigning_lead_id` matches the authenticated
Lead. The unassigned queue remains shared by all Leads.

The response contains every trusted Auth Event Coordinator, including those
without a profile or current work. A missing profile uses the Auth email for
display. Active events whose owner is not in the trusted pool are never
fabricated into Coordinator groups; they are reported separately in
`invalid_assignments` with `reason: identity_missing` for data-integrity review. The endpoint does not change
those assignments:

```json
{
  "coordinators": [
    {
      "coordinator": {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "name": "Alex Coordinator",
        "email": "alex@example.com"
      },
      "active_assignment_count": 1,
      "events": [
        {
          "id": "33333333-3333-4333-8333-333333333333",
          "name": "Autumn Forum",
          "status": "under_review",
          "organiser": {
            "id": "11111111-1111-4111-8111-111111111111",
            "name": "Ada Organiser",
            "email": "ada@example.com"
          },
          "coordinator": {
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "name": "Alex Coordinator",
            "email": "alex@example.com"
          },
          "start_date": "2026-11-18",
          "start_time": "09:00:00",
          "end_date": "2026-11-18",
          "end_time": "12:00:00",
          "coordinator_assignment_version": 0
        }
      ]
    }
  ],
  "invalid_assignments": [
    {
      "event_id": "44444444-4444-4444-8444-444444444444",
      "name": "Orphaned forum",
      "status": "planning",
      "assigned_coordinator_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      "reason": "identity_missing"
    }
  ]
}
```

The event objects retain the Events response fields in addition to the shown
summary. S-85 writes no state and creates no notification. S-84 reassignment
remains the only transfer action; after it succeeds, the next overview read
places the event under the new Coordinator with updated counts.

## Selected Coordinator active events (S-93)

`GET /event-requests/coordinators/{coordinator_id}/active-events` takes a
Coordinator UUID and no body. A signed-in Lead gets `200` with that
Coordinator's trusted Auth status, an active count, and limited event
summaries across responsible Leads. Unknown or non-Coordinator IDs get `404`;
missing sessions get `401`, wrong roles `403`, and downstream failure `502`.
For example:

```json
{
  "coordinator": {"id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","name":"Alex Coordinator","email":"alex@example.com","coordinator_active":false},
  "active_assignment_count": 1,
  "events": [{
    "id":"33333333-3333-4333-8333-333333333333","name":"Autumn Forum","status":"preparation",
    "start_date":"2026-11-18","start_time":"09:00:00","end_date":"2026-11-18","end_time":"12:00:00",
    "assigned_coordinator_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "assigning_lead_id":"dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    "coordinator_assignment_version":2,"scope":"other_lead","actionable":false,"inactive_owner":true
  }]
}
```

`scope` is `mine`, `other_lead`, or `legacy` when Lead provenance is absent.
Only `mine` is actionable through S-84; the Events write checks responsible
Lead scope again. S-85 and S-88 retain their ordinary Lead filters. A legacy
row is always read-only until a controlled provenance repair, documented in
the Events service README. The count and warning come from current Events
ownership on every read, so a failed transfer cannot clear them.

## Technical Support assignment (S-43)

The Technical Support `POST` accepts optional notes:

```json
{"support_details": "Wireless microphone setup and sound check"}
```

Only the event's assigned Coordinator may use these endpoints, and a new
request is accepted only while the event is `planning`. The composite chooses
the least-loaded conflict-free trusted Technical Support account, breaking
ties by ascending UUID. If none is available, it persists the requirement
with no assignee and returns `assignment_state: "unassigned"`.

## Cancellation decision (S-61)

**`POST /event-requests/{event_id}/cancellation-decision`**, through Kong at
`/api/event-requests/{event_id}/cancellation-decision`.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `decision` | `"approved"` \| `"declined"` | yes | |
| `reason` | string | when declining | 1–1000 characters. Not accepted when approving. |

```json
{"decision": "declined", "reason": "The venue is non-refundable; move the date instead"}
```

The events service checks the session, that the caller is the event's
assigned Coordinator, and that a cancellation request is pending, and then
records the decision. Its answer (`200`, `401`, `403`, `404`, `409`, `422`)
is passed on unchanged.

- **Declined:** `200` with the event. Its status is unchanged and
  `cancellation_decision` is `declined` with the reason. Bookings are not
  touched.
- **Approved:** the event becomes `cancelled`, and then every venue booking
  for it is deleted through the bookings service, so its times show as
  available. Equipment needs no call, because only `planning` and `confirmed`
  events reserve it. The response is `200` with the event plus
  `released_bookings`:

```json
{"id": "33333333-…", "status": "cancelled", "cancellation_decision": "approved", "released_bookings": 2}
```

| Status | Detail | Meaning |
| --- | --- | --- |
| `502` | `The events service is unavailable. Nothing was changed.` | No decision was recorded. |
| `502` | `The event is cancelled, but its venue bookings were not released. Approve again to release them.` | Approving again is safe. The event is not written a second time, and the bookings are removed. |

## Change history (S-82)

`GET /event-requests/{event_id}/history`, no body. Readable by the event's
currently assigned Coordinator and by any Lead. A Coordinator who is not
assigned, including one reassigned away, gets `404` "Event not found", the same as a
missing event. The entries are the events service's
(see its [Change history](../../atomic/events/README.md#change-history-s-82)),
newest first, with each actor's name from the users service:

```json
{
  "event_id": "11111111-…",
  "event_name": "Autumn Forum",
  "entries": [
    {"id": 3, "occurred_at": "2026-10-03T01:00:00Z", "category": "assignment",
     "action": "coordinator_reassigned",
     "details": {"from_coordinator_id": "aaaaaaaa-…", "to_coordinator_id": "bbbbbbbb-…"},
     "actor": {"id": "dddddddd-…", "name": "Lee Lead", "role": "event_coordinator_lead"}}
  ],
  "people": {"aaaaaaaa-…": "Alex Coordinator", "bbbbbbbb-…": "Blair Coordinator"}
}
```

`people` names every user id an entry's `details` mentions. A name no longer
on file is `null`, and a backfilled entry whose actor was never recorded has
`"actor": null`.

| Status | When |
| --- | --- |
| `401` | No session. |
| `403` | Any role but Event Coordinator or Event Coordinator Lead. |
| `404` | No such event, or the Coordinator is not assigned to it. |
| `502` | Events or Users did not answer: "Events service unavailable" / "Users service unavailable". |

## Errors

| Status | When |
| --- | --- |
| `401` | No valid session. |
| `403` | The trusted role is not permitted for the endpoint. |
| `404` | The event is missing or not accessible to the caller. |
| `409` | Assignment/reassignment lost a concurrent race, used a stale version, or the event is no longer in the required lifecycle state. |
| `422` | Invalid input, including selecting an id that is not a trusted Event Coordinator. |
| `502` | A required atomic service failed or returned an unexpected response. For assignment, retrying the same request is safe. |

## Configuration

| Variable | Purpose |
| --- | --- |
| `USERS_SERVICE_URL` | Users service, e.g. `http://users:8001`. |
| `EVENTS_SERVICE_URL` | Events service, e.g. `http://events:8002`. |
| `NOTIFICATIONS_SERVICE_URL` | Notifications service, e.g. `http://notifications:8006`. |
| `BOOKINGS_SERVICE_URL` | S-61: bookings service, e.g. `http://bookings:8004`. |
| `ASSIGNMENT_SERVICE_SECRET` | Independent random service credential shared only with Events for S-83/S-84 writes. |

## Running and tests

Load the root `.env`, configure the same `ASSIGNMENT_SERVICE_SECRET` in Events,
and point the service URLs at locally running atomic
services, then:

```bash
cd backend/services/composite/event_requests
uvicorn app:app --reload --port 8100
```

Unit tests replace all outbound clients:

```bash
pytest tests/unit/composite/event_requests
```

Integration tests require the whole stack and the events, users, equipment,
and notifications schemas applied, granted, and exposed in the test project.
S-59 additionally requires the `BEGIN S-59 EVENT CHANGE REQUESTS` block of
`backend/sql/events.sql` in both DEV and TEST:

```bash
docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/composite/event_requests
```

Test specifications:

- [`tests/unit/composite/event_requests/TEST_CASES.md`](../../../../tests/unit/composite/event_requests/TEST_CASES.md)
- [`tests/integration/composite/event_requests/TEST_CASES.md`](../../../../tests/integration/composite/event_requests/TEST_CASES.md)
