# Bookings service

Atomic FastAPI service for venue booking requests (S-36). It owns
`bookings.bookings`, and since S-30 `bookings.blocks` (days Venue Staff mark
a venue unavailable). It never queries another service's tables.

It stores and lists requests and records final staff decisions. Whether a venue can take a
request is decided by the [`venue_bookings`](../../composite/venue_bookings/README.md)
composite before it writes here, because that needs the event and the venue.

There is no direct Kong route. The composite calls this service; its port is
also published for testing. S-37's decision endpoint independently verifies
the access-token cookie through Supabase Auth and requires trusted
`app_metadata.role=venue_staff`. Existing create/list endpoints retain their
internal-service contract. Atomic services never call the users service.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/bookings` | Store a checked booking request as `pending`. It does not reserve the slot. Refused with `409` if the slot already overlaps a hold, confirmed booking, or block. |
| `POST` | `/bookings/{id}/hold` | Venue Staff only: turn a pending request into an exclusive tentative hold. The service records `held_by` and `held_at`; an overlapping live slot returns `409`. |
| `POST` | `/bookings/{id}/release` | Release a hold back to pending and record its release time and reason. Venue Staff can release manually; the owning Coordinator can release with `booking_replaced` (no longer sent by `venue_bookings` since S-79, which keeps every request an event makes). |
| `POST` | `/bookings/{id}/decision` | Venue Staff only: finally confirm or reject a pending or held request; confirmation overlapping another live booking or an unavailable period is refused. |
| `GET` | `/bookings?status=pending` | List pending requests, oldest first. `status=actionable` lists pending and held requests. |
| `GET` | `/bookings?status=live&from={date}` | S-76: every held and confirmed booking dated `from` or later, every venue (optionally `venue_id`), ordered by venue, date, start. `from` is required (`422` without). |
| `GET` | `/bookings?event_id={id}` | List the requests sent for one event, every status, oldest first. |
| `GET` | `/bookings?venue_id={id}&from={date}&to={date}` | S-30: one venue's requests dated in the range, every status, by date then start time. |
| `POST` | `/blocks` | S-30/S-77, Venue Staff only: mark a venue unavailable for a timed period. |
| `GET` | `/blocks?venue_id={id}&from={date}&to={date}` | S-30: one venue's periods touching the range, by start date. |
| `GET` | `/blocks/{id}` | S-77: one period, for the composite (internal). `404` `{"detail": "Block not found"}` if missing. |
| `DELETE` | `/blocks/{id}` | S-30, Venue Staff only: remove a block. |
| `GET` | `/bookings/{id}` | S-75: one request, for the composite (internal, like the other reads). `404` `{"detail": "Booking not found"}` if missing. |
| `GET` | `/health` | Liveness check. |

## Requests

### `POST /bookings`

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `event_id` | UUID | yes | |
| `venue_id` | UUID | yes | |
| `coordinator_id` | UUID | yes | |
| `coordinator_name` | string | yes | Trimmed; not blank. |
| `coordinator_email` | string | yes | Trimmed; not blank. |
| `booking_date` | date `YYYY-MM-DD` | yes | |
| `start_time` | time `HH:MM` | yes | |
| `end_time` | time `HH:MM` | yes | After `start_time`. |
| `event_name` | string | yes | Trimmed; not blank. |
| `event_purpose` | string | yes | Trimmed; not blank. |
| `expected_attendance` | integer | yes | At least `1`. |
| `venue_name` | string | yes | Trimmed; not blank. |
| `special_requirements` | string or null | no | The event's other requirements, free text. Blank becomes null. |
| `required_accessibility` | array of string | no | From the venue accessibility set. Defaults to `[]`. |
| `required_facilities` | array of string | no | From the venue facility set. Defaults to `[]`. |
| `room_layout` | string or null | no | From the venue layout set. |
| `notes` | string or null | no | Blank becomes null. |

Repeated entries in the two arrays are dropped. `status` and `submitted_at`
are set by the service; sending either is a `422`. Any other unknown field is
a `422` too.

The option sets are the venue catalogue's (see
[`venues/README.md`](../venues/README.md)), repeated in
[`schemas.py`](schemas.py) and as check constraints in
[`bookings.sql`](../../../sql/bookings.sql).

### `GET /bookings`

| Query | Required | Values |
| --- | --- | --- |
| `status` | one filter is | `pending` |
| `event_id` | one filter is | UUID |
| `venue_id`, `from`, `to` | all three together | UUID, date `YYYY-MM-DD`, date `YYYY-MM-DD` (inclusive) |

`status` and `event_id` may be given together. With no filter, the answer is
`422` `{"detail": "Filter by status or event_id"}` — nothing lists every
booking. A venue filter always needs its range: `venue_id`, `from` or `to`
alone is `422` `{"detail": "Filter by venue_id with from and to"}`, and `to`
before `from` is `422`
`{"detail": "The end date must be on or after the start date"}`.

## Responses

`POST /bookings` returns `201`; `GET /bookings` returns `200` with a list of
the same shape (`[]` when there are none).

```json
{
  "id": "44444444-4444-4444-8444-444444444444",
  "event_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  "venue_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  "coordinator_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  "coordinator_name": "Grace Hopper",
  "coordinator_email": "grace@example.com",
  "status": "pending",
  "booking_date": "2026-11-12",
  "start_time": "09:00:00",
  "end_time": "12:00:00",
  "event_name": "Alumni networking evening",
  "event_purpose": "Reconnect graduates with faculty",
  "expected_attendance": 120,
  "special_requirements": "Vegetarian catering for 40",
  "required_accessibility": ["wheelchair_access"],
  "required_facilities": ["projector"],
  "room_layout": "theatre",
  "notes": "Access from 08:30 for setup",
  "venue_name": "Studio B",
  "submitted_at": "2026-10-01T09:00:00+00:00"
}
```

| Status | Meaning |
| --- | --- |
| `409` | `POST /bookings` only (S-30): the slot is taken. One of `{"detail": "Studio B is already confirmed on 12 Nov 2026 from 10:00 to 12:00."}`, `{"detail": "Studio B is already tentatively held on 12 Nov 2026 from 10:00 to 12:00."}` or `{"detail": "Studio B is unavailable from 13 Nov 2026 to 16 Nov 2026."}` |
| `422` | The body or query failed validation. `{"detail": "Please check the details you entered", "errors": {"<field>": "<message>"}}` |
| `500` | `{"detail": "Booking storage unavailable"}` — Supabase could not be reached, or refused the write. |

## Running it

**First:** run [`backend/sql/bookings.sql`](../../../sql/bookings.sql) in the
Supabase SQL Editor of both the dev and the test project, and add `bookings`
under **Data API → Settings → Exposed schemas** in both.

**Development** — `.env` filled in from `.env.example`:

```bash
docker compose up --build
# or on its own:
cd backend/services/atomic/bookings
uvicorn app:app --reload --port 8004
```

**Tests:**

```bash
pytest tests/unit/atomic/bookings

docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/atomic/bookings
```

## S-37 decisions

Request: `POST /bookings/{id}/decision` (UUID path parameter), with
the `sb_access_token` session cookie. The gateway equivalent is
`POST /api/venue-bookings/{id}/decision`.

```json
{"decision":"rejected","reason":"Room needs repairs","alternative":"Try Studio C on Friday"}
```

`decision` is required, either `approved` or `rejected`. Optional `reason`
and `alternative` are strings or null; whitespace is trimmed and blanks become
null. Rejection requires at least one nonblank explanation. Approval needs
neither; both may be supplied. Other fields, including staff ID/time, are
rejected. An alternative is a suggestion, never a booking or hold.

200 returns the full original BookingRead request, with these decision fields:
```json
{"status":"rejected","decision_reason":"Room needs repairs","decision_alternative":"Try Studio C on Friday","decided_by":"abababab-abab-4bab-8bab-abababababab","decided_at":"2026-09-28T01:00:00Z"}
```
The JSON above shows the added fields; the response also includes all original
request fields documented above. Approval returns `status=confirmed`.
Pending records have null decision fields. Server identity comes from verified
Auth app metadata; time comes from the server. No request snapshot is rewritten.

| Status | JSON body / meaning |
| --- | --- |
| 401 | `{"detail":"Not authenticated"}` — sign in again, including after an expired access token |
| 403 | `{"detail":"Permission denied"}` — only Venue Staff may decide |
| 404 | `{"detail":"Booking not found"}` |
| 409 | Already decided: `{"detail":"This booking request has already been decided"}`. Overlap (S-76): `{"detail":"Can't confirm this booking: it overlaps Alumni talk (confirmed), which occupies Studio B on 12 Nov 2026 from 10:00 to 12:00."}` |
| 422 | `{"detail":"Please check the details you entered","errors":{"body":"Value error, Provide a reason or alternative to reject this request"}}` — body validation; field/path errors vary |
| 500 | `{"detail":"Booking storage unavailable"}` — database failure; unexpected failures use `{"detail":"Internal server error"}` |

The composite maps downstream 500/network failures to 502 and sanitizes error
messages. On uncertain network failure, reload before retrying: the write may
have succeeded. Final requests cannot be decided again.

### Database setup

Existing projects: copy the entire block between
`BEGIN S-37 DATA-PRESERVING MIGRATION` and
`END S-37 DATA-PRESERVING MIGRATION` in
[`backend/sql/bookings.sql`](../../../sql/bookings.sql) into the Supabase SQL
Editor, first in development and then in test. Run the whole transaction.
It adds four nullable columns and replaces check constraints; it does not
delete or rewrite requests. Do not uncomment the destructive schema-drop line.

For a fresh database run the complete file. In both projects, confirm
`bookings` is exposed under Data API Settings and existing service_role
usage/table grants are present. No new schema, port, secret or browser grant is
required. Docker now passes the existing SUPABASE_ANON_KEY into bookings for
session verification. Confirm both setups before real integration/browser tests.

For S-38, copy the entire block between `BEGIN S-38 DATA-PRESERVING MIGRATION`
and `END S-38 DATA-PRESERVING MIGRATION` into the SQL Editor of both projects.
It installs `btree_gist` and adds a partial exclusion constraint over confirmed
rows. The range is `[start,end)`, so back-to-back event times pass the
constraint; the service itself also requires the venue's setup and turnaround
between bookings (S-75, S-76 — see below). Pending
and rejected requests do not reserve a slot. If existing confirmed rows already
overlap, the transaction fails without changing the schema; resolve those rows
with the team and rerun it.

S-38 checks availability when Venue Staff confirm, then relies on that database
constraint as the final authority. This prevents two concurrent confirmations
from both winning. A blocked request stays pending. S-38 did not create holds;
S-30 since has — see below.

### S-37 verification

From the repository root:
```powershell
python -m pytest tests/unit/atomic/bookings tests/unit/composite/venue_bookings -q
node --test tests/unit/frontend/test_*.mjs
```

After the developer confirms the SQL on dev and test, recreate the test stack
immediately before running real tests (these create and clean up test data):
```powershell
docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
python -m pytest tests/integration/atomic/bookings tests/integration/composite/venue_bookings -q
python -m pytest tests/e2e/test_decide_booking.py -q
```
For development, after dev SQL setup: `docker compose up -d --build --wait`.
Open Kong, or run `npm.cmd run dev` from frontend for hot reload.

## S-30 holds and blocks

**Holds.** A `pending` request is actionable but does not reserve a slot. A
Venue Staff member explicitly changes it to `held`; held and confirmed rows
are exclusive. Back-to-back ranges are allowed because the end time is not
part of the occupied range — once the venue's setup and turnaround are added
(S-76 supersedes S-38 here): with 30 min setup and 45 min turnaround, a
booking may start no earlier than 75 minutes after the previous one ends.
`POST /bookings` refuses, with the `409`s above, a request that overlaps a
pending or confirmed request for the same venue and date, or that overlaps an
unavailable period (S-77). The range is `[start,end)`, so back-to-back requests are fine;
rejected requests hold nothing. The database constraint
`bookings_no_live_overlap` is the final authority, so of two simultaneous
overlapping requests exactly one is stored. Rejecting a request releases its
hold. A hold has no expiry.

**Blocks (unavailable periods, S-77).** A period a venue cannot be used, from
`start_date` + `start_time` up to, but not including, `end_date` + `end_time`.
A booking overlaps a period when the window it occupies the venue — start −
setup to end + turnaround, from the `setup_minutes` and `turnaround_minutes`
query parameters the composite passes — overlaps it. Touching is fine: a
booking may end exactly when a period starts. A request, a hold or a
confirmation that overlaps one is `409`:

```json
{"detail": "Studio B is unavailable from 13 Nov 2026 09:00 to 14 Nov 2026 17:00."}
```

A period may cover existing holds and bookings; none of them is changed here.
The `venue_bookings` composite identifies them and notifies their
Coordinators. A request inside a period can still be rejected.

### `POST /blocks`

Venue Staff only, with the `sb_access_token` cookie; the session is verified
here as for decisions. The gateway equivalent is `POST /api/venue-bookings/blocks`.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `venue_id` | UUID | yes | |
| `venue_name` | string | yes | A snapshot from the venues service, for messages. Trimmed; not blank. |
| `start_date` | date `YYYY-MM-DD` | yes | |
| `start_time` | time `HH:MM` | yes | |
| `end_date` | date `YYYY-MM-DD` | yes | |
| `end_time` | time `HH:MM` | yes | The end is exclusive, and must be after the start: `errors.body` "Value error, The period must end after it starts". |
| `reason` | string | yes | `maintenance`, `equipment_failure`, `renovation`, `safety` or `other`. |
| `note` | string or null | no | The description. Trimmed; blank becomes null. Required when `reason` is `other`: "Value error, Add a description when the reason is other". |

`created_by` (the verified staff id) and `created_at` are set by the service;
sending either, or any other unknown field, is `422`.

`201`:

```json
{
  "id": "77777777-7777-4777-8777-777777777777",
  "venue_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  "venue_name": "Studio B",
  "start_date": "2026-11-13",
  "start_time": "09:00:00",
  "end_date": "2026-11-14",
  "end_time": "17:00:00",
  "reason": "equipment_failure",
  "note": "Air handling unit down",
  "created_by": "abababab-abab-4bab-8bab-abababababab",
  "created_at": "2026-11-10T01:00:00+00:00"
}
```

### `GET /blocks`

`venue_id`, `from` and `to` are all required, with the same `422`s as the
venue filter on `GET /bookings`. `200` with a list of blocks shaped as above,
every block overlapping the range (one that only partly does included), by
start date. A period ending at `00:00` on `from` stopped the day before, so it
is left out.

### `DELETE /blocks/{id}`

Venue Staff only, with the cookie. `204` with no body; `404`
`{"detail": "Block not found"}` if there is no such block.

| Status | Meaning (block writes) |
| --- | --- |
| `401` | `{"detail": "Not authenticated"}` — no or expired session |
| `403` | `{"detail": "Permission denied"}` — not Venue Staff |
| `422` | Validation; field errors as above |
| `500` | `{"detail": "Booking storage unavailable"}` |

### S-30 database setup

Copy the entire block between `BEGIN S-30 DATA-PRESERVING MIGRATION` and
`END S-30 DATA-PRESERVING MIGRATION` in
[`backend/sql/bookings.sql`](../../../sql/bookings.sql) into the SQL Editor of
**both** projects. It replaces S-38's confirmed-only constraint with one over
pending and confirmed rows, and creates `bookings.blocks` with its grant and
RLS. If overlapping pending requests already exist it fails without changing
anything; the block's comment has the query that finds them. No new schema,
port or secret: `bookings` is already exposed.

### S-77 database setup

Copy the entire block between `BEGIN S-77 DATA-PRESERVING MIGRATION` and
`END S-77 DATA-PRESERVING MIGRATION` in
[`backend/sql/bookings.sql`](../../../sql/bookings.sql) into the SQL Editor of
**both** projects, after the S-30 block. It adds `start_time` and `end_time`
to `bookings.blocks`, and turns each existing whole-day block into the same
span as a period (00:00 on its first day to 00:00 the day after its last). It
also changes the reasons: `internal_activity` becomes `other`, keeping its
note. Safe to run twice.

### S-77 verification

```bash
pytest tests/unit/atomic/bookings

docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/atomic/bookings
```

### S-30 verification

```bash
pytest tests/unit/atomic/bookings tests/unit/composite/venue_bookings
node --test tests/unit/frontend/test_*.mjs

docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/atomic/bookings tests/integration/composite/venue_bookings
pytest tests/e2e/test_venue_availability.py
```

## Setup and turnaround (S-75)

`POST /bookings`, `POST /bookings/{id}/hold` and `POST /bookings/{id}/decision`
take two optional query parameters, `setup_minutes` and `turnaround_minutes`
(whole numbers ≥ 0, default 0). The `venue_bookings` composite passes the
venue's current values; without them the check is the same as before S-75.

With them, a held or confirmed booking at the same venue and date clashes when
`other.start < new.end + turnaround + setup` and
`other.end > new.start − setup − turnaround` — the two bookings' occupied
windows (*start − setup* to *end + turnaround*) overlap. Touching windows do
not clash. The refusal says why:

```json
{"detail": "Studio B is already confirmed on 12 Nov 2026 from 10:00 to 12:00. With 30 min setup and 45 min turnaround it is in use until 12:45."}
```

The overlap check also excludes the booking being held or confirmed, so a
held request is never refused for clashing with itself.

The database's `bookings_no_live_overlap` constraint still uses the raw
booking times: it blocks raw overlaps even under a race, but not the
setup/turnaround gap. Storing each venue's times on its bookings to enforce
the gap there would mean rewriting bookings whenever a venue's times change,
which S-75 says must never silently alter bookings.

### S-76 — Venue Staff's refusal names the booking in the way

`POST /bookings/{id}/decision` (approve) and `POST /bookings/{id}/hold` are
Venue Staff only, so their overlap `409` names the event in the way and gives
the whole period it occupies the venue:

```json
{"detail": "Can't confirm this booking: it overlaps Alumni talk (confirmed), which occupies Studio B on 12 Nov 2026 from 09:30 to 12:45 (event 10:00–12:00, 30 min setup, 45 min turnaround)."}
```

A hold says `Can't hold this booking: …`; a held booking in the way is
`(tentatively held)`; with no setup or turnaround the bracketed part is left
off. The same detail comes back when the database constraint wins a race.
`POST /bookings` (a Coordinator's request) keeps the S-75 wording and never
names another event.

