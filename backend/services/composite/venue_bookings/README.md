# Venue bookings service

Composite FastAPI service for venue booking requests (S-36). An Event
Coordinator submits a request for a venue, date and time against one of their
events; Venue Staff see every pending or held request. Owns no table — requests are
stored by the [`bookings`](../../atomic/bookings/README.md) service.

| Calls | For |
| --- | --- |
| `users` — `GET /users/me` | Who is asking, and their role |
| `events` — `GET /events/assigned/{id}` | The event, with the caller's own session, so only an event assigned to this Coordinator is found |
| `venues` — `GET /venues/{id}` | The venue, with the caller's own session |
| `bookings` — `POST /bookings`, `GET /bookings?status=pending`, `GET /bookings?event_id={id}` | Store and list requests |
| `bookings` — `GET /bookings?venue_id&from&to`, `GET /blocks?venue_id&from&to`, `POST /blocks`, `DELETE /blocks/{id}` | S-30: the availability calendar and venue blocks |
| `bookings` — `GET /bookings?status=live&from&venue_id`, `GET /blocks/{id}` | S-77: the bookings an unavailable period affects |
| `events` — `GET /internal/events/assigned-active` | S-77: each affected event's current Coordinator |
| `notifications` — `POST /internal/notifications` | Tell Coordinators about unavailable periods and tentative-hold expiry |
| `venues` — `GET /venues`; `bookings` — `GET /bookings/{id}`, `POST /bookings/{id}/alternative-resolution` | S-78: replacement venues and resolutions |

Reached through Kong at `/api/venue-bookings`.

Dependency reads use a 10-second read timeout and retry transport timeouts or
network errors up to three times with bounded backoff. Only idempotent `GET`
requests are retried. Booking, decision, hold, release, and block writes are
sent exactly once, so a lost response cannot create a duplicate write. After
all read attempts fail, the existing safe `502` response is returned.

## Endpoints

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| `POST` | `/venue-bookings` | `event_coordinator` | Check a venue request and submit it as pending. An event may have several (S-79). |
| `POST` | `/venue-bookings/{id}/decision` | `venue_staff` | Record a final approval or rejection; forward session to the atomic service. |
| `GET` | `/venue-bookings?event_id={id}` | `event_coordinator` | The requests sent for one of the caller's events, every status, oldest first. `404` if the event is not assigned to the caller. |
| `GET` | `/venue-bookings/pending` | `venue_staff` | Every actionable pending or held request, oldest first. Terminal-event holds are released and removed. |
| `POST` | `/venue-bookings/{id}/hold` | `venue_staff` | Place an exclusive tentative hold with required future, timezone-aware `expires_at`; the assigned Coordinator is told when it will expire. |
| `POST` | `/venue-bookings/{id}/release` | `venue_staff` | Release a tentative hold immediately. |
| `GET` | `/venue-bookings/availability?venue_id={id}&from={date}&to={date}` | `event_coordinator`, `venue_staff` | S-30: a venue's holds, confirmed bookings and blocks across a range. |
| `GET` | `/venue-bookings/clashes?venue_id={id}` | `venue_staff` | S-75: pairs of held/confirmed bookings, today on, that clash under the venue's current setup and turnaround. |
| `GET` | `/venue-bookings/clashes` | `venue_staff` | S-76: the same pairs for every venue that has any — Venue Staff's standing clashes to review. |
| `GET` | `/venue-bookings/{id}` | `venue_staff` | S-75: one request, with its clash warning, for its own page. Decided requests are returned too. |
| `POST` | `/venue-bookings/blocks` | `venue_staff` | S-30/S-77: mark a venue unavailable for a timed period; the response names the bookings it affects. See [S-77](#s-77-unavailable-periods). |
| `POST` | `/venue-bookings/blocks/{id}/notify` | `venue_staff` | S-77: retry telling the Coordinators of the bookings a period affects. |
| `DELETE` | `/venue-bookings/blocks/{id}` | `venue_staff` | S-30: remove a block. |
| `GET` | `/venue-bookings/{id}/replacement-venues` | `event_coordinator` | S-78: venues that could replace an affected booking. See [S-78](#s-78-replacement-venues). |
| `POST` | `/venue-bookings/{id}/replacement` | `event_coordinator` | S-78: request a replacement venue for an affected booking. |
| `POST` | `/venue-bookings/{id}/resolution` | `event_coordinator` | S-78: resolve an affected booking's flag with a note. |
| `GET` | `/health`, `/venue-bookings/health` | none | Liveness check. |

## Requests

### `POST /venue-bookings`

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `event_id` | UUID | yes | An event assigned to the caller, in status `planning`. |
| `venue_id` | UUID | yes | |
| `booking_date` | date `YYYY-MM-DD` | yes | One date. |
| `start_time` | time `HH:MM` | yes | |
| `end_time` | time `HH:MM` | yes | After `start_time`. |
| `notes` | string or null | no | Blank becomes null. |

```json
{
  "event_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  "venue_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  "booking_date": "2026-11-12",
  "start_time": "09:00",
  "end_time": "12:00",
  "notes": "Access from 08:30 for setup"
}
```

Any other field is a `422`, including `room_layout`, `required_facilities`
and `required_accessibility`: those are the event's venue requirements, set
by the organiser. Everything else on the stored request — the event's name,
purpose, expected attendance, venue requirements and other requirements, the
venue's name, the Coordinator's name and email — is looked up by this
service and copied onto the request. It is a snapshot: later edits to the
event do not change a request already sent.

**Checks before anything is saved.** A request that fails any of these is
refused with `422`, is never stored, and never reaches Venue Staff. All
failures are reported together, keyed by the field to change:

| `errors` key | Refused when | Message |
| --- | --- | --- |
| `booking_date` | The booking starts before the event or ends after it (equal is fine) | `The booking must fall within the event's date and time` |
| `operating_hours` | The venue has no hours that weekday, or the booking runs outside them (equal is fine) | `Studio B is closed on Saturdays` / `Studio B is open 08:00–20:00 on Thursdays` |
| `expected_attendance` | The event's attendance is more than the venue's capacity | `Studio B holds 150 people; this event expects 151` |
| `required_facilities` | One of the event's facilities is not at the venue | `Studio B does not have: stage, whiteboard` |
| `required_accessibility` | One of the event's accessibility features is not at the venue | `Studio B does not have: hearing_loop` |
| `room_layout` | The venue does not offer the event's layout | `Studio B does not offer the banquet layout` |

**Holds (S-33).** A stored request starts pending. Venue Staff explicitly place
the tentative hold, and only held and confirmed rows reserve time. Holds are
exclusive. The bookings service refuses a request that overlaps another hold,
a confirmed booking or a block, and this service passes its `409` through
unchanged — see the table below.

**Several venues per event (S-79).** An event can have any number of
requests, at different venues, dates or times, and two may run at the same
time in different venues. Each is checked on its own, as above. Capacity is
always checked against the event's total expected attendance. A new request
never replaces, releases or changes the event's other requests. Sending one
that matches a pending or held request's venue, date and times exactly
returns that request with `201` instead of storing a duplicate.

Submitting a request writes nothing to the event — it is already in
`planning` and stays there.

## Responses

`POST /venue-bookings` returns `201` with the stored request, and
`GET /venue-bookings?event_id={id}` and `GET /venue-bookings/pending` return
`200` with a list of them — both
exactly as the bookings service returns them (see
[`bookings/README.md`](../../atomic/bookings/README.md#responses)):

```json
{
  "id": "44444444-4444-4444-8444-444444444444",
  "status": "pending",
  "event_name": "Alumni networking evening",
  "venue_name": "Studio B",
  "booking_date": "2026-11-12",
  "start_time": "09:00:00",
  "end_time": "12:00:00",
  "expected_attendance": 120,
  "...": "every other field of the stored request"
}
```

| Status | Body | Meaning |
| --- | --- | --- |
| `401` | `{"detail": "Not authenticated"}` | No valid session. |
| `403` | `{"detail": "Permission denied"}` | Wrong role for the route. |
| `404` | `{"detail": "Event not found"}` | No such event, or it is not assigned to the caller. |
| `404` | `{"detail": "Venue not found"}` | No such venue. |
| `409` | `{"detail": "A venue can only be requested for an event in planning"}` | The event is `submitted`, `returned` or `rejected`. |
| `409` | `{"detail": "Studio B is already tentatively held on 12 Nov 2026 from 10:00 to 12:00."}` | S-30: the slot is held. Also `… is already confirmed on …` and (S-77) `Studio B is unavailable from 13 Nov 2026 09:00 to 14 Nov 2026 17:00.` Nothing was saved. |
| `422` | `{"detail": "Please check the details you entered", "errors": {...}}` | The body failed validation. |
| `422` | `{"detail": "This venue can't take this booking", "errors": {...}}` | Refused by the checks above. |
| `502` | `{"detail": "<Users\|Events\|Venues\|Bookings> service unavailable"}` | A downstream service could not be reached or failed. Nothing was saved. |

## Running it

**First:** every schema it depends on applied and exposed in both the dev and
the test project — `users`, `events` (including the S-36 `planning` change),
`venues`, `bookings` and `notifications`, including the S-77 blocks in
`bookings.sql` and `notifications.sql`. See
[`backend/sql/`](../../../sql/README.md).

**Development** — `.env` filled in from `.env.example`, including
`VENUES_SERVICE_URL`, `BOOKINGS_SERVICE_URL` and `NOTIFICATIONS_SERVICE_URL`:

```bash
docker compose up --build
# or on its own, with the *_SERVICE_URL values switched to localhost:
cd backend/services/composite/venue_bookings
uvicorn app:app --reload --port 8101
```

**Tests:**

```bash
pytest tests/unit/composite/venue_bookings

docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/composite/venue_bookings
```

## S-37 approval and rejection

Venue Staff may POST `/venue-bookings/{id}/decision` with required
`decision` (`approved` or `rejected`), optional `reason` and `alternative`
(string/null). Rejection needs at least one nonblank explanation. Approval
requires neither. Unknown fields return 422. The composite checks the staff
role and forwards cookies to the atomic service, which independently verifies
the caller and writes the final decision conditionally on `status=pending`.

200 returns the full saved booking with status `confirmed` or `rejected`,
`decision_reason`, `decision_alternative`, `decided_by`, and `decided_at`.
See the [atomic contract](../../atomic/bookings/README.md#s-37-decisions)
for request/response examples, SQL migration and exact test commands.

Errors use `{"detail":"..."}`: 401 `Not authenticated`; 403 `Permission denied`;
404 `Booking not found`; 409 `This booking request has already been decided`,
or an S-76 conflict naming the booking in the way, such as `Can't confirm
this booking: it overlaps Alumni talk (confirmed), which occupies Studio B on
12 Nov 2026 from 09:30 to 12:45 (event 10:00–12:00, 30 min setup, 45 min
turnaround).` (holds: `Can't hold this booking: …`);
422 `Please check the decision and provide a reason or alternative when rejecting`
for downstream validation. Local body validation uses the existing 422
`detail`/`errors` response. Unavailable downstream services return safe 502
messages, for example `{"detail":"Bookings service unavailable"}`.

The assigned Coordinator sees the saved result on the existing event request
list after refreshing. **No reassignment exception:** a previous requester
who is no longer assigned still gets 404. Their continued access is an open
team requirement. No new Coordinator permissions are granted.

S-38 must protect the atomic pending-to-confirmed write against overlapping
bookings. The atomic bookings exclusion constraint remains the final
concurrency guarantee.

## S-30 availability calendar and blocks

### `GET /venue-bookings/availability`

| Query | Required | Values |
| --- | --- | --- |
| `venue_id` | yes | UUID |
| `from` | yes | date `YYYY-MM-DD`, first day |
| `to` | yes | date `YYYY-MM-DD`, last day, on or after `from` |

No rule here keeps the range in the future; the page greys out and disables
days before tomorrow in the browser, as every date picker in the app does.

`200`:

```json
{
  "venue_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  "venue_name": "Studio B",
  "from": "2026-11-11",
  "to": "2026-12-08",
  "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
  "entries": [
    {"state": "confirmed", "start_date": "2026-11-12", "end_date": "2026-11-12", "start_time": "09:00:00", "end_time": "12:00:00"},
    {"state": "held", "start_date": "2026-11-12", "end_date": "2026-11-12", "start_time": "14:00:00", "end_time": "16:00:00"},
    {"state": "blocked", "start_date": "2026-11-13", "end_date": "2026-11-14", "start_time": "09:00:00", "end_time": "17:00:00", "reason": "maintenance"}
  ]
}
```

`held` is a distinct tentative reservation, `confirmed` an approved one; rejected requests
are left out. Entries are in date order, then by start time. No entry carries
an event name, a coordinator, or a booking or event id. For `venue_staff`
only, a `blocked` entry also has the block's `id` and `note`, which they need
to remove it. `operating_hours` is the venue's own, for working out closed
days.

| Status | Body | Meaning |
| --- | --- | --- |
| `401` | `{"detail": "Not authenticated"}` | No valid session. |
| `403` | `{"detail": "Permission denied"}` | Not a Coordinator or Venue Staff. |
| `404` | `{"detail": "Venue not found"}` | No such venue. |
| `422` | `{"detail": "Please check the details you entered", "errors": {...}}` | A query parameter is missing or malformed, or `to` is before `from` (`errors.to`). |
| `502` | `{"detail": "<Users\|Venues\|Bookings> service unavailable"}` | Never an empty calendar, which would read as available. |

### `POST /venue-bookings/blocks`

*Superseded by [S-77](#s-77-unavailable-periods), which adds the times and
the affected bookings.* Venue Staff only. Body: `venue_id`, `start_date`,
`start_time`, `end_date`, `end_time`, `reason`, optional `note` — the rules in the
[bookings contract](../../atomic/bookings/README.md#post-blocks). The venue's
name is looked up here and the session is forwarded, so `venue_name` and
`created_by` in the body are `422`.

```json
{"venue_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "start_date": "2026-11-13", "start_time": "09:00", "end_date": "2026-11-14", "end_time": "17:00", "reason": "maintenance", "note": "Ceiling repair"}
```

`201` with the stored block. `404` `{"detail": "Venue not found"}`; a `422`
from the bookings service is passed through with its `errors`; `401`, `403`
and `502` as above.

### `DELETE /venue-bookings/blocks/{id}`

Venue Staff only. `204` with no body; `404` `{"detail": "Block not found"}`.

A decision refused because the request overlaps an unavailable period is
passed through too: `409` `{"detail": "Studio B is unavailable from 13 Nov 2026 09:00 to 14 Nov 2026 17:00."}`.

**Before running it:** the S-30 block in
[`bookings.sql`](../../../sql/bookings.sql) applied in both projects — see
[S-30 database setup](../../atomic/bookings/README.md#s-30-database-setup).
Tests are those listed under
[S-30 verification](../../atomic/bookings/README.md#s-30-verification).

## Setup and turnaround (S-75)

A booking occupies its venue from *start − setup* to *end + turnaround*,
using the venue's **current** `setup_minutes` and `turnaround_minutes` (read
from the venues service each time). This service applies that everywhere:

- **Submitting a request:** the whole occupied window must be inside the
  venue's opening hours, or `422` with `errors.operating_hours`, e.g.
  `Studio B is open 08:00–20:00 on Thursdays; with 30 min setup and 45 min turnaround a booking must run within 08:30–19:15`.
  The two times are passed to the bookings service, whose `409` says when the
  clashing booking's venue is in use until.
- **Hold and decision:** the booking (`GET /bookings/{id}`) and its venue are
  read first, and their times passed on.
- **Clashes** are worked out live from current data, between **held and
  confirmed** bookings dated **today or later**; nothing is stored and no
  booking is ever changed, released or removed because of one:
  - `GET /venue-bookings?event_id=` and `GET /venue-bookings/pending` give
    each row `clashes` — `[]` when there is none. For a held/confirmed row the
    venue's `setup_minutes` and `turnaround_minutes` are added. Each clash
    gives the other booking's date, times, occupied window and status only:
    ```json
    {"booking_date": "2026-11-12", "start_time": "10:00:00", "end_time": "12:00:00", "occupied_start": "09:30", "occupied_end": "12:45", "status": "confirmed"}
    ```
  - `GET /venue-bookings/clashes?venue_id=` (Venue Staff) lists each clashing
    pair once, with event and coordinator names:
    ```json
    {"venue_id": "…", "venue_name": "Studio B", "setup_minutes": 30, "turnaround_minutes": 45,
     "pairs": [{"first": {"id": "…", "event_id": "…", "event_name": "Alumni talk", "coordinator_name": "…", "status": "confirmed",
                          "booking_date": "2026-11-12", "start_time": "10:00:00", "end_time": "12:00:00",
                          "occupied_start": "09:30", "occupied_end": "12:45"},
                "second": {"…": "the same fields for Board lunch"}}]}
    ```
- **Calendar:** `GET /venue-bookings/availability` adds `setup_minutes` and
  `turnaround_minutes`.
- **Clashes to review (S-76):** `GET /venue-bookings/clashes` with no
  `venue_id` (Venue Staff) reads every venue and every live booking from today
  (`GET /bookings?status=live&from=`) once, and returns the venues with at
  least one clashing pair, by venue name, each pair as above:
  ```json
  {"venues": [{"venue_id": "…", "venue_name": "Hall C", "setup_minutes": 15, "turnaround_minutes": 15, "pairs": [ … ]}]}
  ```
  `{"venues": []}` when nothing clashes. A booking whose venue no longer
  exists is skipped; venues or bookings failing is `502`, never an empty
  list. Other roles `403`.

`GET /venue-bookings/{id}` (Venue Staff) returns one request as the pending
list does, with `clashes`; `404` `{"detail": "Booking not found"}`; other
roles `403`. Venues or bookings failing is `502`, never a missing warning.

**Before running it:** the S-75 block in
[`venues.sql`](../../../sql/venues.sql) run in both projects (see the
[venues README](../../atomic/venues/README.md#setup-and-turnaround-s-75)).

Tests: `pytest tests/unit/composite/venue_bookings`, then on a freshly
recreated `.env.test` stack `pytest tests/integration/composite/venue_bookings`
and `pytest tests/e2e/test_setup_turnaround.py`.


## S-77 unavailable periods

Venue Staff mark a venue unavailable for a period, with a reason, so it is not
booked while it can't be used. The period is stored by the bookings service as
a block (see [its contract](../../atomic/bookings/README.md#post-blocks)); this
service adds what spans other services: which bookings it affects, and telling
their Coordinators.

### `POST /venue-bookings/blocks`

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `venue_id` | UUID | yes | `404` `{"detail": "Venue not found"}` if there is no such venue. |
| `start_date`, `start_time` | date `YYYY-MM-DD`, time `HH:MM` | yes | |
| `end_date`, `end_time` | date `YYYY-MM-DD`, time `HH:MM` | yes | Exclusive; after the start. |
| `reason` | string | yes | `maintenance`, `equipment_failure`, `renovation`, `safety` or `other`. |
| `note` | string or null | no | The description; required when `reason` is `other`. |

`venue_name` and `created_by` in the body are `422`.

```json
{"venue_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "start_date": "2026-11-13", "start_time": "09:00", "end_date": "2026-11-14", "end_time": "17:00", "reason": "equipment_failure", "note": "Air handling unit down"}
```

`201` with the stored block plus:

```json
{
  "...": "every field of the stored block",
  "affected_bookings": [
    {"id": "…", "event_id": "…", "event_name": "Alumni talk", "coordinator_name": "Ada Lim",
     "status": "confirmed", "booking_date": "2026-11-13", "start_time": "10:00:00", "end_time": "12:00:00",
     "occupied_start": "09:30", "occupied_end": "12:30"}
  ],
  "coordinators_notified": true
}
```

- **Affected** means a **held or confirmed** booking at the venue whose occupied
  window (start − setup to end + turnaround, the venue's current times)
  overlaps the period. They are listed in date and start order. Pending
  requests are never affected: the bookings service won't hold or confirm one
  inside a period anyway.
- **Nothing is changed.** No booking is released, rejected or edited, and no
  event is cancelled or written to.
- **Coordinators are told.** Each affected booking's event's **current**
  Coordinator, from `GET /internal/events/assigned-active`, gets one
  `venue_unavailable` notification:
  `"Studio B is unavailable from 13 Nov 2026 09:00 to 14 Nov 2026 17:00 (Equipment failure). Your booking on 13 Nov 2026 from 10:00 to 12:00 needs alternative arrangements."`
  Its deduplication key is `venue_unavailable:<block id>:<booking id>:<recipient id>`,
  sent in batches of at most 20. A booking whose event has no current
  Coordinator is still listed, but nobody is notified about it.
- **A failure doesn't undo the period.** If the events or notifications
  service fails, the response is still `201`, with `"coordinators_notified": false`.
  If the affected bookings can't be read, `affected_bookings` is `null` (unknown,
  not "none"). Either way, retry with `/notify`.

A `422` from the bookings service is passed through with its `errors`; `401`,
`403` and `502` as elsewhere.

### `POST /venue-bookings/blocks/{id}/notify`

Venue Staff only, no body. Works out the affected bookings again from current
data and sends the notifications with the same keys, so nobody is told twice.
`200` with `{"affected_bookings": [...], "coordinators_notified": true|false}`.
`404` `{"detail": "Block not found"}`.

### The flag on every booking read

`GET /venue-bookings?event_id=` (Coordinator), `GET /venue-bookings/pending`
and `GET /venue-bookings/{id}` (Venue Staff) give each row:

```json
{
  "requires_alternative_arrangements": true,
  "unavailable_periods": [
    {"start_date": "2026-11-13", "start_time": "09:00:00", "end_date": "2026-11-14",
     "end_time": "17:00:00", "reason": "equipment_failure", "note": "Air handling unit down"}
  ]
}
```

`false` and `[]` for pending and rejected rows, and for bookings before today.
The flag is worked out live, like S-75's clashes: remove the period and it is
gone. If the periods can't be read, the read is `502`, never a missing flag.

The calendar's `blocked` entries now carry the period's `start_time` and
`end_time`.

**Before running it:** the S-77 blocks in
[`bookings.sql`](../../../sql/bookings.sql) and
[`notifications.sql`](../../../sql/notifications.sql) run in both projects.

Tests: `pytest tests/unit/composite/venue_bookings`, then on a freshly
recreated `.env.test` stack `pytest tests/integration/composite/venue_bookings`
and `pytest tests/e2e/test_mark_venue_unavailable.py`.


## S-78 replacement venues

A Coordinator can replace a booking an unavailable period affects with
another venue, without entering the event again, or resolve the flag with a
note.

**Who and which booking.** All three routes are for the event's **current**
Coordinator, checked with `GET /events/assigned/{event_id}` using the
caller's session. The booking must carry S-77's flag
(`requires_alternative_arrangements: true`). Its event must be `planning`,
`confirmed`, `preparation` or `safety_changes_requested`.

| Status | Body | Meaning |
| --- | --- | --- |
| `401` | `{"detail": "Not authenticated"}` | No valid session. |
| `403` | `{"detail": "Permission denied"}` | Not a Coordinator. |
| `404` | `{"detail": "Booking not found"}` | No such booking, or its event isn't assigned to the caller. |
| `409` | `{"detail": "This booking doesn't need a replacement venue"}` (resolution: `"This booking doesn't need alternative arrangements"`) | Not flagged: pending, rejected, replaced, past, no period, or already resolved. |
| `409` | `{"detail": "This event's venue bookings can no longer be changed"}` | The event is in any other status. |
| `502` | `{"detail": "<Users\|Events\|Venues\|Bookings> service unavailable"}` | A downstream service failed. Never an empty result. |

### `GET /venue-bookings/{id}/replacement-venues`

`200`:

```json
{
  "booking": {"id": "…", "venue_name": "Studio B", "booking_date": "2026-11-13", "start_time": "10:00:00", "end_time": "12:00:00"},
  "venues": [{"id": "…", "name": "Hall C", "...": "every field, exactly as GET /venues returns it"}]
}
```

Venues by name, each one both:

- **suitable**, by the event's **current** requirements and the booking's
  date and times — the same checks as `POST /venue-bookings`: capacity,
  layout, facilities, accessibility, and the occupied window inside opening
  hours;
- **available** then — no held or confirmed booking within the venue's
  setup + turnaround gap, and no unavailable period over its occupied window.
  A pending request doesn't reserve time, so it doesn't count.

The booking's own venue is never listed. `"venues": []` when none qualifies.

### `POST /venue-bookings/{id}/replacement`

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `venue_id` | UUID | yes | |
| `notes` | string or null | no | Blank becomes null. |

Any other field is `422`. The request is stored for the booking's event,
date and times, with `replaces_booking_id` set to the booking, and the
event's details are copied in as for `POST /venue-bookings`. `201` with the
stored request.

- **One at a time.** If a pending or held replacement for this booking
  exists, sending the same venue returns it with `201`. Any other venue is
  `409` `{"detail": "A replacement request for this booking is already with Venue Staff"}`.
  Once that request is rejected, another may be sent.
- Refusals as for `POST /venue-bookings`: `422` `{"detail": "This venue can't take this booking", "errors": {...}}`,
  the bookings service's slot `409`s passed through, `404` `{"detail": "Venue not found"}`.
- **The original stays flagged** until Venue Staff approve the replacement.
  Approving it (`POST /venue-bookings/{id}/decision`) makes the original
  `replaced` — see the
  [bookings contract](../../atomic/bookings/README.md#s-78-replacement-requests-and-resolutions).
  A replaced booking is never flagged.

### `POST /venue-bookings/{id}/resolution`

Body `{"note": "Moved online for this session"}`: trimmed, 1–500 characters;
any other field is `422`. `200` with the booking, which now carries
`alternative_resolved_at`, `alternative_resolved_by` and
`alternative_resolution_note`. The booking is otherwise unchanged. A
replacement request already sent stays with Venue Staff.

From then on the flag ignores every period created at or before
`alternative_resolved_at`. A period created later flags the booking again.

### Venue Staff's request page

`GET /venue-bookings/{id}` adds `replaces`: `null`, or for a replacement
request, the booking it replaces:

```json
{"replaces": {"id": "…", "venue_name": "Studio B", "booking_date": "2026-11-13", "start_time": "10:00:00", "end_time": "12:00:00", "status": "confirmed"}}
```

**Before running it:** the S-78 block in
[`bookings.sql`](../../../sql/bookings.sql) run in both projects.

Tests: `pytest tests/unit/composite/venue_bookings`, then on a freshly
recreated `.env.test` stack `pytest tests/integration/composite/venue_bookings`
and `pytest tests/e2e/test_replace_affected_booking.py`.
