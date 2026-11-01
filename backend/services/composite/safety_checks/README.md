# Safety Checks service

Composite FastAPI service for S-17, S-63, S-68, S-86 and S-87. It owns no database. It
authenticates Safety Officers and Event Coordinators through Users, reads the
current event from Events, enriches safety evidence and feedback, and sends
lifecycle actions back to the Events atomic owner.

The lifecycle is `planning → pending_safety_check → confirmed`. S-17: the
Coordinator submits a planning event once every mandatory arrangement is
complete, which moves it to `pending_safety_check` -- the S-86 queue. Only the
Safety Officer's approval makes it `confirmed`.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/safety-checks` | List `pending_safety_check` events with no safety decision, enriched with organiser. |
| `GET` | `/safety-checks/{event_id}` | Return all operational-safety evidence for one eligible event. |
| `POST` | `/safety-checks/{event_id}/decision` | Record the first safety decision as the authenticated Safety Officer. |
| `GET` | `/safety-checks/{event_id}/history` | S-82: the safety review's part of the event's change history, for any Safety Officer once the event has reached the safety check. See [Change history](#change-history-s-82). |
| `GET` | `/safety-checks/coordinator/events/{event_id}` | Return preserved safety feedback and history to the currently assigned Event Coordinator. |
| `GET` | `/safety-checks/coordinator/events/{event_id}/readiness` | S-17: what is still outstanding before the event can be submitted, without submitting. |
| `POST` | `/safety-checks/coordinator/events/{event_id}/submit` | S-17: submit a fully arranged planning event for the Operational Safety Check. |
| `POST` | `/safety-checks/coordinator/events/{event_id}/resubmit` | Resubmit revised arrangements for a completely fresh safety review, after the same S-17 check. |
| `GET` | `/health` | Liveness check. |

Only trusted `app_metadata.role=safety_officer` is accepted. No Safety Officer
assignment is introduced: every Safety Officer can access every eligible row.

## Requests

`readiness`, `submit` and `resubmit` take no body and no query parameters.
`submit` and `resubmit` refuse any body with `422`: there is no override.

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
| `approved` | `confirmed` |
| `rejected` | `safety_rejected` |
| `changes_requested` | `planning` with preserved current feedback and immutable history |

The Events service conditionally writes only a `pending_safety_check` row with
a null current safety decision. A stale, repeated, or concurrent attempt returns
`409` and cannot overwrite the first stored result. S-63 then sends the
owning Organiser one idempotent `safety_check_outcome` notification. Approval
states that the event is now confirmed. Rejection and requested changes carry
the Safety Officer's actionable reason and tell the Organiser to work with
their Event Coordinator. A notification failure is reported as `502` after
the safety result has been saved; retrying cannot duplicate the notice.

For S-68, a later approval also compares the newly approved attendee-facing
schedule with the schedule at the preceding approval. If the date or time has
changed, the service reads the event's current registrations and sends each
registered Attendee one idempotent `event_schedule_changed` notification. The
message names the event, gives its new start and end, and confirms that the
registration remains active. Initial confirmation, rejected or returned safety
reviews, internal booking problems, edits that restore the previously confirmed
window, waitlisted people and withdrawn registrations do not produce this
notification. Notification writes are split into batches of at most 20 rows.

For S-87, only `event_coordinator` passes the composite role check and Events
also requires the authenticated id to be the event's current assignee. The
returned detail resolves the recorded Safety Officer identity and exposes the
reason, decision time and complete `safety_review_history`. Resubmission is
permitted only for `planning` plus current `changes_requested`; ordinary
planning events receive `409` and are submitted instead. Resubmission runs the
same S-17 check as a submission and is refused the same way. Success changes
the event to `pending_safety_check`, clears the current blocker, retains
history, and returns it to the S-86 queue. Events performs that transition in
one conditional write; this composite performs no resource writes or retries.

### S-17 submission

An event is ready when:

- **Venue approved** -- at least one `confirmed` booking, and no booking
  `pending` or `held`, no `rejected` booking that has not been replaced (a
  confirmed replacement marks it `replaced`, which stops counting), and no
  `confirmed` booking with an unresolved S-77 unavailable period.
- **Equipment and technical support arranged** -- only when the event has an
  equipment requirement or `technical_support_required`: Technical Support
  is assigned, its sign-off is `approved` (an approval over a shortage, with
  its comment, counts), and `equipment_preparation_status` is `ready`.

`GET .../readiness` answers `200`:

```json
{"ready": false, "outstanding": [
  {"code": "venue_awaiting", "booking_id": "…", "label": "Studio 2 on 20 Nov 2026 is waiting for Venue Staff"},
  {"code": "technical_signoff_awaiting", "label": "Technical Support has not approved the equipment arrangements"}
]}
```

`POST .../submit` answers `200` with the updated event (`"status":
"pending_safety_check"`), or `409` with every outstanding item at once and
nothing written:

```json
{"detail": "This event has outstanding arrangements", "outstanding": [ … ]}
```

| `code` | `label` |
| --- | --- |
| `venue_missing` | No venue booking has been confirmed yet |
| `venue_awaiting` | {venue} on {date} is waiting for Venue Staff |
| `venue_rejected` | {venue} on {date} was rejected — request a replacement venue |
| `venue_unavailable` | {venue} on {date} is affected by an unavailable period — replace it or record alternative arrangements |
| `technical_support_unassigned` | Technical Support has not been assigned |
| `technical_signoff_awaiting` | Technical Support has not approved the equipment arrangements |
| `technical_signoff_declined` | Technical Support declined: {reason} |
| `equipment_preparation` | Equipment preparation is {Not Started / In Progress} |

Venue items carry the `booking_id` they are about. The rules are in
[`readiness.py`](readiness.py); the S-77 flag rule there is repeated from
`venue_bookings`.

## Change history (S-82)

`GET /safety-checks/{event_id}/history`, no body, Safety Officer only. It
returns the events service's `scope=safety` view: safety decisions and
submissions, venue and equipment entries, and edits cut down to attendance,
venue, layout, facilities and access. The body has the same shape as
`event_requests`' `GET /event-requests/{event_id}/history`, with names filled
in. Available once the event has reached the safety check: its status is
`pending_safety_check`, `safety_changes_requested`, `safety_rejected`,
`confirmed` or `preparation`, or it has any recorded safety review. That
last case covers an event sent back to `planning`. Any other event, and a
missing one, is `404` "Event not found".

## Errors

| Status | Meaning |
| --- | --- |
| `401` | No valid session. |
| `403` | The authenticated role is not Safety Officer (queue, detail, decision) or Event Coordinator (coordinator routes). |
| `404` | The event does not exist, or is not assigned to the calling Coordinator. |
| `409` | It is ineligible, stale, or already decided; for submit/resubmit, not in planning (`"This event is not in planning"`) or has outstanding arrangements (body above). |
| `422` | Invalid event id, decision, reason combination, or extra field; any body on submit/resubmit. |
| `502` | A required atomic service is unavailable or returned an unidentified failure. |

## Configuration and running

The service reads `USERS_SERVICE_URL`, `EVENTS_SERVICE_URL`,
`VENUES_SERVICE_URL`, `BOOKINGS_SERVICE_URL`, `EQUIPMENT_SERVICE_URL`, and
`NOTIFICATIONS_SERVICE_URL`, and `REGISTRATIONS_SERVICE_URL`.
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
pytest tests/e2e/test_operational_safety_check.py tests/e2e/test_confirm_event.py tests/e2e/test_notify_attendee_event_rescheduled.py
```

Before integration or browser tests, apply
[`backend/sql/events.sql`](../../../sql/events.sql) and the S-78 block of
[`backend/sql/bookings.sql`](../../../sql/bookings.sql) to both dev and test
Supabase projects. Unit tests require neither Docker nor Supabase:

```bash
pytest tests/unit/composite/safety_checks
```
