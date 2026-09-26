# Venues service

Atomic FastAPI service for venues. It owns `venues.venues` and never queries
another service's tables.

## Endpoints

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| `POST` | `/venues` | `venues:create` | Add a venue. |
| `GET` | `/venues` | `venues:view` | List every venue, by name A–Z. |
| `GET` | `/venues/options` | `venues:view` | The fixed facilities, accessibility, room layout and day sets. |
| `GET` | `/venues/{venue_id}` | `venues:view` | Return one venue. |
| `GET` | `/venues/health` | none | Gateway-compatible liveness alias. |
| `GET` | `/health` | none | Liveness check. |

Every endpoint except health authenticates the `sb_access_token` and
`sb_refresh_token` cookies issued by the users service, then authorizes the
trusted `app_metadata.role`:

| Role | Permissions |
| --- | --- |
| `venue_staff` | `venues:create`, `venues:view` |
| `event_coordinator` | `venues:view` |
| `event_organiser`, `technical_support`, `attendee` | none |

The service sets `id`, `created_by` (the verified user's id) and `created_at`.
A `created_by` in the request body is ignored.

## Requests

### `POST /venues`

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `name` | string | yes | Trimmed; not blank. Unique, ignoring case. |
| `location` | string | yes | Trimmed; not blank. |
| `capacity` | integer | yes | At least `1`. |
| `room_layouts` | array of string | yes | At least one, from the layout set below. |
| `operating_hours` | array of `{day, open, close}` | yes | At least one day. `day` from the day set, at most once each; `open`/`close` are `HH:MM`, `close` after `open`. A day not listed means closed. |
| `facilities` | array of string | no | From the facility set below. Defaults to `[]`. |
| `accessibility` | array of string | no | From the accessibility set below. Defaults to `[]`. |
| `description` | string or null | no | Blank becomes null. |

Repeated entries in `facilities`, `accessibility` or `room_layouts` are dropped,
keeping the first. `operating_hours` is stored in week order.

The option sets (defined in [`schemas.py`](schemas.py), repeated as check
constraints in [`venues.sql`](../../../sql/venues.sql)):

| Field | Values |
| --- | --- |
| `facilities` | `projector`, `screen`, `sound_system`, `microphones`, `wifi`, `stage`, `whiteboard`, `video_conferencing`, `catering_kitchen`, `air_conditioning`, `parking` |
| `accessibility` | `wheelchair_access`, `step_free_entrance`, `accessible_toilets`, `lift`, `hearing_loop`, `accessible_parking` |
| `room_layouts` | `theatre`, `classroom`, `boardroom`, `u_shape`, `banquet`, `cabaret`, `cocktail` |
| `operating_hours[].day` | `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun` |

```json
{
  "name": "Harbourfront Hall",
  "location": "1 Harbourfront Walk, Singapore 098585",
  "capacity": 250,
  "facilities": ["projector", "wifi", "stage"],
  "accessibility": ["wheelchair_access", "accessible_toilets"],
  "room_layouts": ["theatre", "banquet"],
  "operating_hours": [
    {"day": "mon", "open": "09:00", "close": "18:00"},
    {"day": "sat", "open": "10:00", "close": "22:00"}
  ],
  "description": "Waterfront hall with a raised stage."
}
```

### `GET /venues/{venue_id}`

`venue_id` is a UUID.

## Responses

`POST /venues` returns `201`; everything else returns `200`. A venue:

```json
{
  "id": "22222222-2222-2222-2222-222222222222",
  "name": "Harbourfront Hall",
  "location": "1 Harbourfront Walk, Singapore 098585",
  "capacity": 250,
  "facilities": ["projector", "wifi", "stage"],
  "accessibility": ["wheelchair_access", "accessible_toilets"],
  "room_layouts": ["theatre", "banquet"],
  "operating_hours": [
    {"day": "mon", "open": "09:00:00", "close": "18:00:00"},
    {"day": "sat", "open": "10:00:00", "close": "22:00:00"}
  ],
  "description": "Waterfront hall with a raised stage.",
  "created_by": "11111111-1111-1111-1111-111111111111",
  "created_at": "2026-09-26T08:00:00Z"
}
```

`GET /venues` returns an array of these, `[]` when there are none.

`GET /venues/options`:

```json
{
  "facilities": ["projector", "screen", "sound_system", "microphones", "wifi", "stage", "whiteboard", "video_conferencing", "catering_kitchen", "air_conditioning", "parking"],
  "accessibility": ["wheelchair_access", "step_free_entrance", "accessible_toilets", "lift", "hearing_loop", "accessible_parking"],
  "room_layouts": ["theatre", "classroom", "boardroom", "u_shape", "banquet", "cabaret", "cocktail"],
  "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
}
```

`GET /health` returns `{"status": "ok"}`.

## Errors

| Status | Body | When |
| --- | --- | --- |
| `401` | `{"detail": "Not authenticated"}` | No valid session; an expired access token is refreshed when possible. |
| `403` | `{"detail": "Recognized role required"}` | The trusted role is missing or unknown. |
| `403` | `{"detail": "Permission denied"}` | The role lacks the route's permission. |
| `404` | `{"detail": "Venue not found"}` | No venue has that id. |
| `409` | `{"detail": "A venue with this name already exists"}` | Another venue has the same name, ignoring case. |
| `422` | see below | A required field is missing, or a value breaks a rule above; or the venue id is not a UUID. |
| `500` | `{"detail": "Venue storage unavailable"}` | Supabase failed. Internal details are not returned. |

```json
{
  "detail": "Please check the details you entered",
  "errors": {
    "capacity": "Field required",
    "operating_hours.0": "Value error, close must be after open"
  }
}
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `SUPABASE_URL` | Supabase project URL. |
| `SUPABASE_SERVICE_KEY` | Backend-only access to `venues.venues`. |
| `SUPABASE_ANON_KEY` | Supabase Auth session verification and refresh. |
| `AUTH_COOKIE_SECURE` | Whether refreshed session cookies carry `Secure`; defaults to `true`. |

## Database setup

Run [`backend/sql/venues.sql`](../../../sql/venues.sql) in **both** the dev and
test Supabase projects, then add `venues` under **Data API → Settings →
Exposed schemas** in each. The service fails every query until both are done.

## Running

### Development

Load the root `.env` into the shell, then:

```bash
cd backend/services/atomic/venues
uvicorn app:app --reload --port 8003
```

Or the whole stack, from the repository root:

```bash
docker compose up --build
```

The browser reaches the service through Kong at `/api/venues`; it is also
published directly on `localhost:8003`.

### Unit tests

No environment file, database, Docker or network needed. From the repository
root:

```bash
pip install -r backend/services/atomic/venues/requirements.txt -r tests/requirements.txt
pytest tests/unit/atomic/venues
```

### Integration tests

Need `.env.test` filled in with the **test** project, `venues.sql` applied and
`venues` exposed there. Start the stack from `.env.test` immediately before
running — never reuse one left running:

```bash
docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/atomic/venues
```

These create and delete real venues and Auth users.

## Test cases

- Unit: [`tests/unit/atomic/venues/TEST_CASES.md`](../../../../tests/unit/atomic/venues/TEST_CASES.md)
- Integration: [`tests/integration/atomic/venues/TEST_CASES.md`](../../../../tests/integration/atomic/venues/TEST_CASES.md)
