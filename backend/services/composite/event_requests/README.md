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

Story S-85 adds a read-only oversight view. It groups all active assigned
events under their current Coordinator, includes trusted Coordinators with no
active work, and exposes an assignment count for each group.

The existing S-43 Technical Support workflow remains available to assigned
Event Coordinators.

## Endpoints

| Method | Path | Role | Does |
| --- | --- | --- | --- |
| `POST` | `/event-requests` | Event Organiser | Creates a submitted, unassigned request. |
| `POST` | `/event-requests/{event_id}/submit` | Event Organiser | Submits a draft unassigned, or resubmits a returned request while preserving its assignment. |
| `PATCH` | `/event-requests/{event_id}` | Event Organiser | Updates an owned request without automatic assignment or reassignment. |
| `GET` | `/event-requests/unassigned` | Event Coordinator Lead | Lists submitted requests whose `assigned_coordinator_id` is null, oldest submission first, including organiser details. |
| `GET` | `/event-requests/coordinators` | Event Coordinator Lead | Lists trusted Event Coordinator accounts available for manual selection. |
| `POST` | `/event-requests/{event_id}/assignment` | Event Coordinator Lead | Assigns the selected Coordinator and creates both notifications. |
| `GET` | `/event-requests/assigned-active` | Event Coordinator Lead | Lists assigned active events with organiser, current Coordinator, and assignment version. |
| `GET` | `/event-requests/coordinator-overview` | Event Coordinator Lead | Groups active assigned events under every Coordinator, including zero-assignment Coordinators. |
| `POST` | `/event-requests/{event_id}/reassignment` | Event Coordinator Lead | Transfers an active event to another Coordinator and creates three notifications. |
| `GET` | `/event-requests/{event_id}/technical-support-assignment` | Assigned Event Coordinator | Reads the event's Technical Support state. |
| `POST` | `/event-requests/{event_id}/technical-support-assignment` | Assigned Event Coordinator | Requests and automatically allocates Technical Support when possible. |
| `POST` | `/event-requests/{event_id}/cancellation-decision` | Assigned Event Coordinator | S-61: approve (cancel the event and release its venue bookings) or decline an Organiser's cancellation request. |
| `GET` | `/health` | Infrastructure | Liveness check. |

`GET /event-requests/health` is the gateway-compatible health alias.

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
`event_coordinator`. The Lead may choose any such account. This workflow does
not query coordinator load and does not reject schedule conflicts.

The events service conditionally writes the assignment only while the request
is still `submitted` and unassigned. The successful response is the updated
event plus `assignment_created`, which is `true` for the first write and
`false` when the same Coordinator assignment is retried.

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

The selected id must be a different trusted `event_coordinator`. Events are
eligible while `submitted`, `planning`, `confirmed`, or `returned`; draft,
rejected, cancelled, unassigned, missing, or stale targets are not changed.
The atomic write compares the expected owner and version, then increments the
version. It deliberately performs no availability or conflict check.

A successful transfer creates one persistent `event_reassignment`
notification for the former Coordinator, new Coordinator, and Organiser.
Keys are `event_reassignment:{event_id}:{version}:{recipient_id}`. If the
event write succeeds but notification persistence fails, the endpoint returns
`502`; repeating the identical request recognizes the committed transition
and upserts any missing rows without duplicates. Once a newer transfer has
incremented the version, an old retry returns `409` and cannot move the event
back.

## Coordinator oversight (S-85)

`GET /event-requests/coordinator-overview` accepts no parameters or body. Only
an authenticated `event_coordinator_lead` may call it. Active means
`submitted`, `under_review`, `returned`, `planning`, or `confirmed`, and an
event must have a current `assigned_coordinator_id`. Unassigned, draft,
rejected, cancelled, and completed events are excluded by Events before the
composite groups them.

The response contains every trusted Event Coordinator, including those with
no current work:

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
  ]
}
```

The event objects retain the Events response fields in addition to the shown
summary. S-85 writes no state and creates no notification. S-84 reassignment
remains the only transfer action; after it succeeds, the next overview read
places the event under the new Coordinator with updated counts.

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

## Running and tests

Load the root `.env`, point the three service URLs at locally running atomic
services, then:

```bash
cd backend/services/composite/event_requests
uvicorn app:app --reload --port 8100
```

Unit tests replace all outbound clients:

```bash
pytest tests/unit/composite/event_requests
```

Integration tests require the whole stack and the events, users, and
notifications schemas applied, granted, and exposed in the test project:

```bash
docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/composite/event_requests
```

Test specifications:

- [`tests/unit/composite/event_requests/TEST_CASES.md`](../../../../tests/unit/composite/event_requests/TEST_CASES.md)
- [`tests/integration/composite/event_requests/TEST_CASES.md`](../../../../tests/integration/composite/event_requests/TEST_CASES.md)
