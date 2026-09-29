# Bookings service

Atomic FastAPI service for venue booking requests (S-36). It owns
`bookings.bookings` and never queries another service's tables.

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
| `POST` | `/bookings` | Store a checked booking request as `pending`. |
| `POST` | `/bookings/{id}/decision` | Venue Staff only: finally confirm or reject a pending request; overlapping confirmation is blocked. |
| `GET` | `/bookings?status=pending` | List pending requests, oldest first. |
| `GET` | `/bookings?event_id={id}` | List the requests sent for one event, every status, oldest first. |
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
| `status` | one of the two | `pending` |
| `event_id` | one of the two | UUID |

Both may be given together. With neither, the answer is `422`
`{"detail": "Filter by status or event_id"}` — nothing lists every booking.

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
| 409 | Already decided: `{"detail":"This booking request has already been decided"}`. Overlap: `{"detail":"Studio B is already confirmed on 12 Nov 2026 from 10:00 to 12:00."}` |
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
rows. The range is `[start,end)`, so back-to-back bookings are allowed. Pending
and rejected requests do not reserve a slot. If existing confirmed rows already
overlap, the transaction fails without changing the schema; resolve those rows
with the team and rerun it.

S-38 checks availability when Venue Staff confirm, then relies on that database
constraint as the final authority. This prevents two concurrent confirmations
from both winning. A blocked request stays pending. S-38 does not create holds,
change venue records, or stop Coordinators from submitting competing pending
requests.

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
