# Event requests service

Composite FastAPI service. It owns no storage and coordinates the users,
events, and notifications atomic services.

Story S-83 changes event assignment to an explicit Event Coordinator Lead
action. A submitted request enters an unassigned queue. A Lead may choose any
trusted Event Coordinator; schedule overlap and current workload do not block
that choice. Assignment creates persistent in-app notifications for the
Coordinator and Event Organiser. No email or external notification is sent.

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
| `GET` | `/event-requests/{event_id}/technical-support-assignment` | Assigned Event Coordinator | Reads the event's Technical Support state. |
| `POST` | `/event-requests/{event_id}/technical-support-assignment` | Assigned Event Coordinator | Requests and automatically allocates Technical Support when possible. |
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

## Errors

| Status | When |
| --- | --- |
| `401` | No valid session. |
| `403` | The trusted role is not permitted for the endpoint. |
| `404` | The event is missing or not accessible to the caller. |
| `409` | Assignment lost a concurrent race, targets another existing Coordinator, or an event is no longer in the required lifecycle state. |
| `422` | Invalid input, including selecting an id that is not a trusted Event Coordinator. |
| `502` | A required atomic service failed or returned an unexpected response. For assignment, retrying the same request is safe. |

## Configuration

| Variable | Purpose |
| --- | --- |
| `USERS_SERVICE_URL` | Users service, e.g. `http://users:8001`. |
| `EVENTS_SERVICE_URL` | Events service, e.g. `http://events:8002`. |
| `NOTIFICATIONS_SERVICE_URL` | Notifications service, e.g. `http://notifications:8006`. |

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
