# Events service

Atomic FastAPI service for event requests. It owns `events.events` and
`events.reassignment_requests` and never
queries another service's tables.

## Endpoints

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| `POST` | `/events/drafts` | `events:save_draft` | Create an incomplete draft. |
| `POST` | `/events` | `events:create` | Create an immediately submitted request. |
| `GET` | `/events` | `events:view_own` | List the authenticated organiser's event requests, most recently updated first. |
| `GET` | `/events/options` | `events:create` | The venue requirement option sets for the organiser's form: `room_layouts`, `facilities`, `accessibility`. |
| `GET` | `/events/{event_id}` | `events:view_own` | Return one event owned by the authenticated caller. |
| `GET` | `/events/booking-status/{event_id}` | `events:view_booking_status` | Return only the event id and authoritative status so Venue Staff can release a terminal event's tentative hold. |
| `PATCH` | `/events/{event_id}` | `events:update_own_draft` | Update supplied fields on an owned event — draft or already submitted. |
| `POST` | `/events/{event_id}/submit` | `events:submit_own` | Replace the business fields of an owned draft *or returned request* with a complete submission and (re)submit it. |
| `GET` | `/events/assigned` | `events:view_assigned` | List the authenticated coordinator's assigned event requests, most recently updated first. |
| `GET` | `/events/assigned/{event_id}` | `events:view_assigned` | Return one event assigned to the authenticated coordinator. |
| `POST` | `/events/{event_id}/reassignment-request` | `events:request_reassignment` | Create a reasoned request for the current Coordinator. |
| `GET` | `/events/reassignment-requests/mine` | `events:request_reassignment` | List the caller's request history, including actioned requests after transfer. |
| `POST` | `/events/assigned/{event_id}/edit-impact` | `events:update_assigned` | Preview significant information changes without saving. |
| `PATCH` | `/events/assigned/{event_id}` | `events:update_assigned` | Save assigned-event information with version checking and append-only edit history. |
| `GET` | `/events/support-assigned` | `events:view_support_assigned` | List the authenticated Technical Support staff member's assigned `planning`, `pending_safety_check`, `confirmed`, and `preparation` events. |
| `GET` | `/events/support-assigned/{event_id}` | `events:view_support_assigned` | Return one active event assigned to the authenticated Technical Support staff member. |
| `POST` | `/events/{event_id}/cancellation-request` | `events:request_cancellation` | S-62: the owning organiser asks for a live event to be cancelled. The status does not change. See [Cancellation requests](#cancellation-requests-s-62). |
| `PUT` | `/events/support-assigned/{event_id}/equipment-preparation` | `events:update_equipment_preparation` | Set the assigned event's equipment preparation status and server-owned audit fields. |
| `POST` | `/events/{event_id}/cancellation-decision` | `events:decide_cancellation` | S-61: the assigned coordinator approves (status becomes `cancelled`) or declines a pending cancellation request. See [Cancellation requests](#cancellation-requests-s-62). |
| `POST` | `/events/{event_id}/decision` | `events:decide` | Record the assigned coordinator's approve/reject/return decision. See [Decisions](#decisions-s-14). |
| `GET` | `/events/health` | none | Gateway-compatible liveness alias. |
| `GET` | `/health` | none | Liveness check. |

Internal, composite-only routes have no Kong route. S-83/S-84/S-85/S-88
assignment and request routes also verify the Lead's session at this layer,
because service ports are published for direct testing. See
[Internal routes](#internal-routes-composite-only).

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/events/coordinator-load` | Conflict and current load for a set of coordinators against a requested window. Takes an optional `exclude_event_id` so rechecking an existing event never conflicts with itself. |
| `POST` | `/events/technical-support-load` | Conflict and current live workload for candidate Technical Support Staff against a requested window. |
| `POST` | `/events/overlapping` | S-44: the `planning` and `confirmed` events overlapping a window, for the `equipment_requirements` composite's availability check. |
| `PUT` | `/events/{event_id}/technical-support/internal` | Persist a planning event's Technical Support requirement and automatic assignment for its currently assigned Coordinator. |
| `GET` | `/internal/events/unassigned` | List submitted requests with no Coordinator, oldest submission first. |
| `POST` | `/internal/events/{event_id}/assignment` | Authenticated Lead assigns an unassigned request, recording their ID; same-target retry support. |
| `GET` | `/internal/events/assigned-active` | Authenticated Lead's active assignments, newest update first. |
| `GET` | `/internal/events/coordinator-overview` | Authenticated Lead's scoped S-85 active events, newest update first. |
| `GET` | `/internal/events/{event_id}/assignment-scope` | Return an event only to its recorded assigning Lead. |
| `GET` | `/internal/reassignment-requests/lead` | Return only the authenticated Lead's request history. |
| `GET` | `/internal/events/safety-review` | S-86 queue source: list `pending_safety_check` events with no current safety decision, oldest update first. |
| `GET` | `/internal/events/safety-review/{event_id}` | Return one eligible safety-review event; missing is `404`, stale/ineligible is `409`. |
| `POST` | `/internal/events/safety-review/{event_id}/decision` | Atomically record the first safety decision and lifecycle outcome. |
| `GET` | `/internal/events/{event_id}/safety-return?coordinator_id=…` | S-87: return a planning event's preserved safety feedback only when the supplied Coordinator is its current assignee. |
| `POST` | `/internal/events/{event_id}/safety-resubmit` | S-87: conditionally resubmit a safety-returned planning event for a fresh review (to `pending_safety_check`). |
| `POST` | `/internal/events/{event_id}/safety-submission` | S-17: move the Coordinator's planning event to `pending_safety_check`. See [Safety-check submission](#safety-check-submission-and-sign-off-s-17). |
| `PUT` | `/internal/events/{event_id}/technical-signoff` | S-17: record the assigned Technical Support's approval or decline. |
| `POST` | `/internal/events/{event_id}/technical-signoff/clear` | S-17: clear the sign-off after a Coordinator equipment change. |
| `POST` | `/internal/events/{event_id}/reassignment` | Authenticated responsible Lead's versioned compare-and-set transfer, with exact-retry support. |
| `POST` | `/events/internal` | Create an already-submitted event with a caller-supplied `organiser_id` and optional `assigned_coordinator_id`. |
| `POST` | `/events/{event_id}/submit/internal` | Submit an owned draft with a caller-supplied `organiser_id` and optional `assigned_coordinator_id`. |
| `PATCH` | `/events/{event_id}/internal` | Update an owned event with a caller-supplied `organiser_id`, optionally reassigning `assigned_coordinator_id` in the same write. |
| `GET` | `/internal/events/published` | S-51: every `confirmed` event's public details, by start. For the `event_registrations` composite. See [Registration (S-51)](#registration-s-51). |
| `GET` | `/internal/events/published/{event_id}` | S-51: one `confirmed` event's public details; any other status is `404`. |

Public event endpoints and the S-83/S-84/S-85/S-88 Lead routes authenticate the `sb_access_token` and
`sb_refresh_token` cookies issued by the users service, then authorize the
trusted `app_metadata.role` against the permission shown above.

The centralized policy recognizes every project role. All may view their own
frontend dashboard. Event Organiser, Event Coordinator, Venue Staff, and
Technical Support workflows have the following event permissions:

| Role | Permissions |
| --- | --- |
| `event_organiser` | `dashboard:view`, `events:create`, `events:save_draft`, `events:view_own`, `events:update_own_draft`, `events:submit_own`, `events:request_cancellation` |
| `event_coordinator` | `dashboard:view`, `events:view_assigned`, `events:update_assigned`, `events:decide`, `events:decide_cancellation`, `events:request_reassignment` |
| `event_coordinator_lead` | `dashboard:view`, `events:lead_assignments` |
| `venue_staff` | `dashboard:view`, `events:view_booking_status` |
| `technical_support` | `dashboard:view`, `events:view_support_assigned`, `events:update_equipment_preparation` |
| `attendee` | `dashboard:view` |

`events:view_assigned` is read-only. `events:decide` (S-14) is the one write
a coordinator can make: approve, reject, or return a request assigned to
them — never edit its fields directly.

Both Technical Support read routes derive the staff id from the verified
session, never a query or path parameter. They include only live assignments
(`planning`, `pending_safety_check`, `confirmed`, and `preparation`). The S-26 update route applies the
same assignment and lifecycle predicates again on its write, so a reassignment
or lifecycle change racing the request cannot update stale work.
An event assigned to another staff member, or an inactive assignment, returns
`404` from the item route so it cannot be distinguished from a missing event.

### Equipment preparation (S-26)

`PUT /events/support-assigned/{event_id}/equipment-preparation` accepts exactly:

```json
{"status": "in_progress"}
```

`status` is one of `not_started`, `in_progress`, or `ready`. It may move in
either direction while the event is in `planning`, `pending_safety_check`,
`confirmed`, or `preparation`. The service records the authenticated Technical Support id and
server time; clients cannot supply either audit field. Success returns the
complete event. `401` means no valid session, `403` means the trusted role is
not Technical Support, `404` hides missing or differently assigned work,
`409` means assignment or lifecycle changed concurrently, `422` means an
invalid body, and `500` means storage did not save the change.

The remaining internal and attendee roles intentionally receive no
speculative event permissions. Their permissions can expand when a
corresponding project story defines a workflow.

### Coordinator event information (S-18)

The three assigned-event write routes accept only events in `planning`,
`confirmed`, or `preparation`, and hide another Coordinator's event as `404`.
The preview route calculates changed and significant fields from stored data
without writing. The PATCH requires the current `expected_version`; a
significant change also requires `impact_accepted=true`. A stale version or
missing acceptance returns `409`.

Routine purpose, contact, and internal-note edits keep the lifecycle state.
Accepted schedule, attendance, or venue-requirement changes on a confirmed or
preparation event return it to planning and clear only its current safety
decision. Existing venue and equipment work, Technical Support assignment,
equipment preparation, and prior safety history remain. Every successful edit
increments `edit_version` and appends changed fields, before/after values, the
authenticated Coordinator id, and server time to `edit_history`. The submit
route then returns a revised planning event to `confirmed`, awaiting a new
Operational Safety Check.

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
| `registration_required` | boolean | S-51. Defaults to `false`. Turning it off clears both dates. |
| `registration_opens_at` | `YYYY-MM-DDTHH:MM` or null | S-51. Singapore time, no offset. May be left empty on a draft. |
| `registration_closes_at` | `YYYY-MM-DDTHH:MM` or null | S-51. After `registration_opens_at`, and before the event's start, whenever those are known. |

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
| `registration_required` | boolean | no | S-51. Defaults to `false`; when `false` both dates are stored as null. |
| `registration_opens_at` | `YYYY-MM-DDTHH:MM` | when registration is on | Singapore time, no offset. May already have passed. |
| `registration_closes_at` | `YYYY-MM-DDTHH:MM` | when registration is on | After `registration_opens_at`; before `start_date` + `start_time`. |

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
  "coordinator_assignment_version": 0,
  "technical_support_required": false,
  "technical_support_details": null,
  "assigned_technical_support_id": null,
  "technical_support_assigned_at": null,
  "decision": null,
  "decision_reason": null,
  "decision_comment": null,
  "decided_at": null,
  "cancellation_reason": null,
  "cancellation_requested_at": null,
  "cancellation_requested_by": null,
  "cancellation_decision": null,
  "cancellation_decision_reason": null,
  "cancellation_decided_by": null,
  "cancellation_decided_at": null,
  "safety_decision": null,
  "safety_decision_reason": null,
  "safety_officer_id": null,
  "safety_decided_at": null,
  "safety_review_history": [],
  "registration_required": true,
  "registration_opens_at": "2026-10-01T09:00:00",
  "registration_closes_at": "2026-10-15T18:00:00",
  "created_at": "2026-09-14T00:00:00Z",
  "updated_at": "2026-09-14T00:00:00Z"
}
```

`assigned_coordinator_id` is null until the `event_requests` composite records
the Lead's assignment; an organiser's own request can never set it.
`coordinator_assignment_version` starts at `0` and increments for each real
S-84 owner-to-owner transfer. The composite supplies the current owner and
version when reassigning, so a stale request cannot overwrite newer work.
See [Internal routes](#internal-routes-composite-only).

S-85's internal coordinator-overview route is read-only and recognizes
`submitted`, `under_review`, `returned`, `planning`, and `confirmed` as active.
It excludes null assignments and every other lifecycle state. S-85 does not
create or transition event statuses and makes no schema change; it only
defines how an assigned `under_review` row is treated when that workflow state
is supplied by its owning lifecycle feature.

S-86 interprets `confirmed` as meaning the event's required venue and
technical arrangements have been confirmed and are ready for Operational
Safety Check. The safety result is deliberately separate from the original
Coordinator decision:

- `approved` moves the event to `preparation`;
- `rejected` moves it to `safety_rejected`, not generic `rejected`;
- `changes_requested` appends an immutable history record and returns the event
  directly to `planning`, while remaining the current blocking decision.

Rejection and changes require a nonblank reason; approval forbids one. The
service stores the verified Safety Officer id and server time. A conditional
update matching `confirmed` plus null `safety_decision` makes repeated, stale,
and concurrent decisions return `409` without overwrite.

S-87's narrow resubmission action applies only to a `planning` event whose
current decision is `changes_requested` and whose current assignee matches the
verified Coordinator supplied by the composite. It changes the event to
`confirmed` and clears only the current safety fields. The append-only
`safety_review_history` remains intact, so the prior feedback is never lost;
the null current decision makes the event eligible for a completely fresh
S-86 review. The same conditional write makes stale, repeated, reassigned, or
concurrent attempts return `409`. No venue, equipment, Technical Support, or
event-information field is changed.

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

`GET /events/support-assigned` returns only `planning` and `confirmed` rows
whose `assigned_technical_support_id` matches the verified Technical Support
user, most recently updated first. No assigned active events returns `[]`.

`GET /health` returns:

```json
{"status": "ok"}
```

## Registration (S-51)

The Organiser decides whether attendees register, and sets the period they
may do it in, while creating or updating the request: on a `draft` or a
`returned` request. Once it is submitted the settings are fixed. A `PATCH`
that names any of the three fields on an event in any other status is
refused with `409` "Registration settings can only be changed while the
request is a draft or returned.", even if the values are unchanged. Other
fields on the same event can still be edited as before.

The period is Singapore wall-clock time and is stored without a timezone,
like the event's own dates and times. A date-time sent with an offset is
converted to Singapore time first.

| Rule | Message (`422`) |
| --- | --- |
| Registration on and submitted without an opening | "Choose when registration opens." on `registration_opens_at` |
| Registration on and submitted without a closing | "Choose when registration closes." on `registration_closes_at` |
| Closing at or before opening | "Registration must close after it opens." |
| Closing at or after the event starts | "Registration must close before the event starts." |

The rules apply to the record a `PATCH` produces, so moving the event's start
before an existing closing date is refused too. Registration being off clears
both dates, and the order of dates is not checked while it is off.

`GET /internal/events/published` and `GET /internal/events/published/{id}`
return only `confirmed` events, and only their public fields:

```json
{
  "id": "33333333-3333-4333-8333-333333333333",
  "name": "Alumni networking evening",
  "purpose": "Reconnect alumni with current students",
  "start_date": "2026-11-20",
  "start_time": "18:00:00",
  "end_date": "2026-11-20",
  "end_time": "21:00:00",
  "registration_required": true,
  "registration_opens_at": "2026-11-01T09:00:00",
  "registration_closes_at": "2026-11-15T18:00:00"
}
```

A missing event, or one in any other status, is `404` "Event not found.".
Registrations themselves are stored by the
[registrations service](../registrations/README.md); this service only holds
the settings.

## Status model (S-14, S-36, S-43, S-17, S-86, S-87)

```
draft ──submit──> submitted ──approve──> planning   (venue/equipment planning)
                    ▲   │ ────reject───> rejected   (terminal)
                    │   └─────return───> returned
                    └──edit + resubmit──────┘

planning ──S-17 submit──> pending_safety_check ──safety approve──> confirmed
                                  │────safety reject────> safety_rejected
                                  └──request changes───> planning
                                        └──S-87 resubmit──> pending_safety_check
```

S-17: the Coordinator submits once every mandatory arrangement is complete;
the `safety_checks` composite checks that and this service owns only the
transition. Approved (the Coordinator's decision, `decision=approved`) and
Confirmed (the Safety Officer's approval) are separate stages.

- **draft** — incomplete, editable, never assigned a coordinator.
- **submitted** — complete, assigned a coordinator, awaiting their decision.
  Still editable; editing does not change the status.
- **planning** — the coordinator approved the request (S-36: an approval
  moves the event here; there is no `approved` status, only the recorded
  `decision=approved`). Venue booking requests are made against events in
  this status. No further submit action; edits still go through the same
  `PATCH`.
- **pending_safety_check** — S-17: venue and technical arrangements are
  complete and the event waits for the Safety Officer; also a live commitment
  for Technical Support workload and overlap checks.
- **confirmed** — the Safety Officer approved the arrangements (S-17; S-86
  used `preparation`). Applying the S-17 SQL moves existing undecided
  `confirmed` rows to `pending_safety_check` and approved `preparation` rows to
  `confirmed`.
- **preparation** — allowed for a later story; nothing sets it now.
- **safety_rejected** — the safety arrangement was rejected; this is distinct
  from the original request's generic `rejected` state.
- **safety_changes_requested** — retained only as a legacy-compatible enum for
  pre-S-87 data; applying the S-87 SQL migrates such rows to `planning` while
  preserving their decision in history.
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

## Safety-check submission and sign-off (S-17)

Internal, called by composites only; none is routed through Kong.

**`POST /internal/events/{event_id}/safety-submission`** takes
`{"coordinator_id": "<uuid>"}` and moves the event from `planning` to
`pending_safety_check` in one conditional write. The `safety_checks`
composite has already checked every arrangement. `200` with the event; `404`
if it is not that Coordinator's event; `409` `"This event is not in
planning"`, or, for an event the Safety Officer sent back, a `409` saying to
resubmit it instead (S-87's route clears the feedback).

**`PUT /internal/events/{event_id}/technical-signoff`**:

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `technical_support_id` | uuid | Yes | Must be the event's assigned Technical Support, else `404`. |
| `decision` | `"approved"` / `"declined"` | Yes | |
| `reason` | string ≤ 500 | With `declined` | Not blank; refused with `approved`. |
| `override_comment` | string ≤ 500 | No | Only with `approved`; not blank. |

Stores `technical_signoff_decision`, `_reason`, `_override_comment`, `_by`
and a server `_at`. `200` with the event; `409` `"Technical Support sign-off
can only change while the event is in planning"`; `422` for the rules above.

**`POST /internal/events/{event_id}/technical-signoff/clear`** sets all five
sign-off fields to null. `200` with the event, also when there was nothing to
clear; `404` if the event does not exist.

Every event read (`EventRead`) carries the five sign-off fields, all `null`
while awaiting Technical Support.

## Cancellation requests (S-62)

**`POST /events/{event_id}/cancellation-request`** is for the organiser who
owns the event only. It is reached through Kong at
`/api/events/{event_id}/cancellation-request`.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `reason` | string | yes | Trimmed; 1–1000 characters. Any other field is a `422`. |

```json
{"reason": "Keynote speaker withdrew and no replacement is available"}
```

Returns `200` with the event. `cancellation_reason`,
`cancellation_requested_at` (server time) and `cancellation_requested_by`
(the caller) are set. **`status` is unchanged**: the event is not cancelled
until a later review completes it. There is one request per event, and it
comes back on `GET /events` and `GET /events/{event_id}`.

| Status | When |
| --- | --- |
| `401` | No valid session. |
| `403` | Not an `event_organiser`. |
| `404` | `Event not found`: missing, or not the caller's. |
| `409` | `This event can't be cancelled from its current status.`: only `submitted`, `under_review`, `planning`, `pending_safety_check`, `confirmed`, `preparation` and `safety_changes_requested` qualify. |
| `409` | `A cancellation request has already been sent for this event.`: also returned when another request lands between the read and the write. |
| `422` | Missing, blank or over-long `reason`, or an extra field. |
| `500` | `Event storage unavailable`: nothing was recorded. |

### Deciding a request (S-61)

**`POST /events/{event_id}/cancellation-decision`** is for the coordinator the
event is assigned to only. The browser reaches it through the
`event_requests` composite, which also releases the event's venue bookings.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `decision` | `"approved"` \| `"declined"` | yes | |
| `reason` | string | when declining | Trimmed, 1–1000 characters. Not accepted when approving. |

**Approving** sets `status` to `cancelled`. **Declining** leaves `status`
alone. Both set `cancellation_decision`, `cancellation_decided_by` and
`cancellation_decided_at`; a decline also sets
`cancellation_decision_reason`. The record keeps the latest decision only.
After a decline the organiser may request again, which clears the decision.

| Status | When |
| --- | --- |
| `200` | Decided. Approving a request that is already approved returns the event unchanged, which is how the composite retries a failed booking release. |
| `401` / `403` | No session / not an `event_coordinator`. |
| `404` | `Event not found`: missing, or not assigned to the caller. |
| `409` | `There is no cancellation request to decide for this event.` |
| `409` | `This cancellation request has already been decided.`: also returned when another decision lands between the read and the write. |
| `422` | Unknown `decision`, a decline without a reason, an approval with one, or an extra field. |

## Internal routes (composite-only)

These routes support the repository's composite services. There is no Kong
route for any of them, and they carry no session-derived authorization of
their own. A browser cannot reach them from outside the Docker network; each
calling composite authenticates and authorizes its workflow first.

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

Only `planning`, `pending_safety_check` and `confirmed` events are returned:
their equipment requirements reserve equipment. An event ending exactly when the window
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
| `assigned_coordinator_id` | uuid or null | Existing assignment to preserve; S-83 submissions use null until a Lead assigns the request. |

Same responses and status codes as the public routes they mirror
(`201`/`200`, `404` for another organiser's draft, `409` for an event that is
not currently `draft` or `returned`).

### `GET /internal/events/unassigned` and assignment

The internal queue returns only `submitted` events with a null
`assigned_coordinator_id`, oldest `submitted_at` first. The S-83 composite
adds organiser profiles; this atomic service does not read user storage.

`POST /internal/events/{event_id}/assignment` accepts:

```json
{"coordinator_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}
```

It conditionally updates a submitted, unassigned event and returns the event
plus `assignment_created: true`. Repeating the same Coordinator assignment
returns `200` with `assignment_created: false`; this lets the composite repair
a failed notification write. A different existing assignment or changed
status returns `409`, and a missing event returns `404`. This atomic route does
not evaluate schedule conflicts.
The Lead identity comes from the verified session and is stored as
`assigning_lead_id`; a retry by another Lead cannot claim the event.

### Reassignment requests (S-88)

The authenticated current Coordinator may call
`POST /events/{event_id}/reassignment-request` with exactly
`{"reason":"Cannot cover the November event"}`. The reason must be nonblank
and at most 2,000 characters. The service derives requester, assigning Lead,
and assignment version from the current event; clients cannot provide them.
The request is inserted into `events.reassignment_requests` with database
timestamps. A database trigger locks and rechecks the event in the same
transaction as insertion. A unique pending index rejects concurrent duplicates.

Success is `201` with this shape:

```json
{"id":"ffffffff-ffff-4fff-8fff-ffffffffffff","event_id":"33333333-3333-4333-8333-333333333333","event_name":"November Forum","requester_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","assigning_lead_id":"dddddddd-dddd-4ddd-8ddd-dddddddddddd","assignment_version":2,"reason":"Cannot cover the November event","status":"pending","created_at":"2026-10-25T00:00:00Z","actioned_at":null}
```

`GET /events/reassignment-requests/mine` and the Lead-only internal list
take no parameters or body and return arrays of these rows. Both filter by
the verified caller's ID. A successful S-84 event update actions the matching
pending request in the same database transaction, setting `actioned_at`; a
failed transfer leaves it pending. The original requester can read the
actioned row after losing event ownership. Historical rows remain.

Failures use `{"detail":"..."}`: `401` for no session, `403` for a wrong
role, `404` for an event outside the Coordinator's or Lead's scope, `409` for
no recorded Lead, duplicate pending request, or a stale assignment, `422`
for an invalid reason, and `500` if Events storage fails.

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
| `409` | `POST /events/{event_id}/submit` on an event that is not `draft` or `returned`; `PATCH` or `/submit` on a `rejected` event (closed permanently); `PATCH` on a `cancelled` event (S-61: "This event has been cancelled and is closed."); `POST /events/{event_id}/decision` on an event that is not currently `submitted`; S-51: a `PATCH` naming a registration field on an event that is not `draft` or `returned`; an internal Technical Support write when the event is no longer the Coordinator's planning event or changed concurrently. Editing a `submitted`/`returned`/`planning` event via `PATCH` is otherwise allowed and does not 409. |
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
