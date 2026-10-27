# Users service

Atomic service. Owns the `users` entity: the account and the profile that goes
with it.

## Responsibility

Authentication, wrapped. Credentials never reach this code — they are passed
to Supabase Auth, which stores and checks them. What this service adds is the
part Supabase does not do for you:

- server-side validation, so a request that skipped the form is still checked;
- one duplicate-address answer, whichever layer noticed;
- the profile row in `users.users`, created with the account and removed again
  if it cannot be written;
- the session in **httpOnly cookies** instead of a token the browser can read.

The browser never talks to Supabase Auth directly, so the anon key and the
session token both stay on the server side of this boundary.

Does not call any other service.

## Endpoints

| Method | Path | Does |
| --- | --- | --- |
| `POST` | `/users/signup` | Creates the account and its profile. `201` with the profile; sets the session cookies unless the address needs confirming. |
| `POST` | `/users/login` | Checks the credentials, sets the session cookies, returns the profile. |
| `POST` | `/users/logout` | Expires the cookies and revokes the refresh token. `204`. |
| `GET` | `/users/me` | The signed-in user, for a route guard to call on every page load. `401` when signed out. |
| `POST` | `/internal/users/profiles` | Internal batch lookup for basic profiles by UUID. |
| `GET` | `/health` | Liveness, for `docker compose --wait`. |

Paths are bare, the way every service in this repo mounts its routes. The
`/api/users/...` the frontend calls is the gateway's prefix, not this service's
— Kong (or the Vite dev proxy) strips it.

**`GET /internal/users/coordinators`**, **`POST /internal/users/profiles`**, and
**`GET /users/technical-support`** are
internal, composite-only routes — no Kong route, and no session required at
this layer, because a browser cannot reach them from outside the Docker
network. The `event_requests` composite
([`backend/services/composite/event_requests`](../../composite/event_requests/README.md))
is the only caller. The first lists trusted Coordinator choices for a Lead;
the profile route resolves organiser details for the unassigned queue; the
third finds candidates for an event's Technical Support assignment. Role
routes use only trusted Supabase Auth `app_metadata.role`, including across
all Auth pagination pages. The Coordinator route returns every matching Auth
account even when its `users.users` profile is missing. Profile name/email
enrich the display when available; otherwise Auth email supplies both display
fields (or Auth phone/id supplies the name if no email exists):

```json
// 200
[{"id": "aaaa...", "name": "Grace Hopper", "email": "grace@example.com", "coordinator_active": true},
 {"id": "bbbb...", "name": "idle@example.com", "email": "idle@example.com", "coordinator_active": false}]
```

S-93 reads `coordinator_active` from trusted Auth
`app_metadata.coordinator_active`. An explicit boolean `false` excludes the
account from new assignments; `true` or a missing key means available. A
malformed value returns `null` and is ineligible. Editable `user_metadata`
does not affect this field. Administrators can change it through the Supabase
Auth Admin API while preserving existing `app_metadata.role` and any other
metadata; this service exposes no Coordinator deactivation endpoint.

`[]` when no account currently holds that role.

`POST /internal/users/profiles` accepts 0–100 UUIDs, removes duplicates while
preserving order, and returns the profiles that exist:

```json
{"ids": ["11111111-1111-4111-8111-111111111111"]}
```

`GET /users/technical-support` still returns only profiled accounts whose
trusted role is `technical_support`. A role in editable
`user_metadata`, or a profile-table value, never makes an account eligible.

### Request and response

Every endpoint takes and returns JSON. The session travels in cookies, never in
a body — no endpoint accepts or returns a token.

**`POST /users/signup`**

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `name` | string | yes | 1–100 characters, trimmed |
| `email` | string | yes | a valid address; lower-cased before storage |
| `password` | string | yes | 8–72 characters (bcrypt ignores anything past 72) |

No other fields are accepted. In particular, public signup has no `role`
field. After Supabase creates the account, the backend uses its administrative
client to assign trusted `app_metadata.role=event_organiser`; callers cannot
select an internal role.

```json
// 201, plus Set-Cookie: sb_access_token, sb_refresh_token
{"id": "3f1c...", "name": "Ada Lovelace", "email": "ada@example.com"}
```

**`POST /users/login`**

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `email` | string | yes | a valid address |
| `password` | string | yes | 1–72 characters — deliberately not the sign-up rules, so an older password still logs in |

```json
// 200, plus Set-Cookie: sb_access_token, sb_refresh_token
{"id": "3f1c...", "name": "Ada Lovelace", "email": "ada@example.com"}
```

**`POST /users/logout`** — no body. Returns `204` with no content, and both
cookies expired.

**`GET /users/me`** — no body, no parameters. The session cookies identify the
caller.

```json
// 200
{"id": "3f1c...", "name": "Ada Lovelace", "email": "ada@example.com", "role": "event_organiser"}
```

`role` is read from the verified Auth user's trusted `app_metadata.role`. It is
`null` for an authenticated account with no assigned role; the browser must
fail closed for that state. It never comes from `user_metadata` or the profile
table.

**`GET /health`** — no body.

```json
// 200
{"status": "ok"}
```

`id` is the Supabase Auth user's id, a uuid. `created_at` exists on the row but
is not returned.

### Errors

| Status | When |
| --- | --- |
| `422` | The payload is wrong: missing field, malformed address, password under 8 characters. FastAPI's own validation. |
| `409` | The address already has an account — whether this service's table or Supabase noticed. |
| `401` | Wrong credentials, or no usable session. Login never says which half was wrong; a form that distinguishes "no such account" from "wrong password" is a way to enumerate addresses. |
| `429` | Supabase is rate-limiting that address. |
| `502` | Supabase Auth could not be reached or made no sense. |

Every error has the same shape, so a caller reads `detail` once and is done:

```json
{"detail": "Email already registered"}
```

A `422` adds the per-field messages a form needs, with `detail` still a
sentence rather than FastAPI's default list of error objects:

```json
{
  "detail": "Please check the details you entered",
  "errors": {"email": "value is not a valid email address"}
}
```

That includes crashes — an unhandled exception is JSON too, not `text/plain`,
so the frontend can parse the responses most worth logging.

## Sessions

Login returns no token. It sets two cookies — `sb_access_token` and
`sb_refresh_token` — each `HttpOnly`, `Secure` and `SameSite=Lax`, so script on
the page cannot read them and cross-site requests do not carry them.

The frontend never calls this service directly. It calls **Kong** at
`/api/users/...`, and Kong forwards to `http://users:8001/users/...` — see
[`backend/kong/`](../../../kong/README.md). That is what keeps the frontend
from knowing this service's port at all.

It also keeps the browser on **one origin**, which is what the cookies need.
In development Vite serves the app and proxies `/api` to Kong
([`frontend/vite.config.js`](../../../../frontend/vite.config.js)); in
production Kong fronts both. Calling `http://localhost:8001` straight from
`http://localhost:5173` is cross-origin, and the browser blocks it for want of
CORS headers this service deliberately does not send — the fix is the proxy,
not the headers, because CORS with credentials would also force the weaker
`SameSite=None`.

The access token lasts about an hour, so `/users/me` refreshes it from the
refresh cookie when it has expired and writes the renewed pair back on the same
response. An idle tab is not logged out.

## Configuration

From the root `.env`; all four are listed in
[`.env.example`](../../../../.env.example).

| Variable | Why |
| --- | --- |
| `SUPABASE_URL` | The project. |
| `SUPABASE_SERVICE_KEY` | Reading and writing `users.users`, and the admin calls that delete an account or revoke a token. Bypasses RLS — backend only. |
| `SUPABASE_ANON_KEY` | Talking to Supabase Auth. Signing up and signing in are anonymous operations; the service key would make every login look like an admin request. |
| `AUTH_COOKIE_SECURE` | `true` by default. Browsers count localhost as a secure origin, so leave it alone for local work. |

## Database

Schema in [`backend/sql/users.sql`](../../../sql/users.sql). One table,
`users.users`, whose `id` **is** the Supabase Auth user's id, so the account and
its profile are one row from every direction.

Credentials live in Supabase's own `auth.users`, which this service does not
own and never queries — it goes through the Auth API.

Before this service works, a developer has to run that SQL in **both** the dev
and test projects, and add `users` under **Data API → Settings → Exposed
schemas** in both. Neither step works without the other, and the error you get
when one is missing points somewhere else entirely — see
[AGENTS.md](../../../../AGENTS.md#%EF%B8%8F-expose-the-schema-and-the-table-or-nothing-works).

## Running

**First, once per Supabase project:** apply
[`backend/sql/users.sql`](../../../sql/users.sql) and expose the `users` schema
(Data API → Settings → Exposed schemas). Nothing below works until both are
done, and the error you get says something else entirely.

### For development

Reads the root `.env` — your own project, the one whose rows survive.

```bash
docker compose up -d --build --wait users    # port 8001

# or directly, with the root .env loaded into your shell
cd backend/services/atomic/users
uvicorn app:app --reload --port 8001
```

```bash
curl http://localhost:8001/health
curl -i -X POST http://localhost:8001/users/signup   -H "Content-Type: application/json"   -d '{"name":"Ada Lovelace","email":"ada@example.com","password":"correct-horse-battery"}'
```

`-i` shows the `Set-Cookie` headers, which is the part worth checking.

### For tests

Unit tests need nothing — no Docker, no Supabase, no `.env`:

```bash
pip install -r tests/requirements.txt
pytest tests/unit/atomic/users
```

Integration tests need the stack up against `.env.test` — the throwaway
project, because they create and delete real accounts:

```bash
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/atomic/users
docker compose --env-file .env.test down
```

Changing a value in an env file needs `--force-recreate`; a running container
keeps the environment it started with.

## Test cases

- Unit: `tests/unit/atomic/users/` — cases in
  [`TEST_CASES.md`](../../../../tests/unit/atomic/users/TEST_CASES.md)
- Integration: `tests/integration/atomic/users/` — cases in
  [`TEST_CASES.md`](../../../../tests/integration/atomic/users/TEST_CASES.md)
