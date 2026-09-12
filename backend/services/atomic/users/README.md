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
| `GET` | `/health` | Liveness, for `docker compose --wait`. |

Paths are bare, the way every service in this repo mounts its routes. The
`/api/users/...` the frontend calls is the gateway's prefix, not this service's
— Kong (or the Vite dev proxy) strips it.

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

`SameSite=Lax` means **the frontend has to reach these routes same-origin.**
In development that is a Vite proxy:

```js
// frontend/vite.config.js
server: {
  proxy: {
    "/api": {
      target: "http://localhost:8001",
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ""),
    },
  },
}
```

and in production it is Kong in front of both. Calling `http://localhost:8001`
straight from `http://localhost:5173` will look like it works and then quietly
drop the cookie — that is the one thing to check first if login "succeeds" and
`/users/me` still says 401.

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

```bash
docker compose up --build users        # port 8001

# or directly, with the root .env loaded into the environment
cd backend/services/atomic/users
uvicorn app:app --reload --port 8001
```

## Tests

- Unit: `tests/unit/atomic/users/` — cases in
  [`TEST_CASES.md`](../../../../tests/unit/atomic/users/TEST_CASES.md)
- Integration: `tests/integration/atomic/users/` — cases in
  [`TEST_CASES.md`](../../../../tests/integration/atomic/users/TEST_CASES.md)
