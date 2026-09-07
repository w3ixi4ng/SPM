# AGENTS.md

Conventions for this repo. Follow them when adding or changing a service.

## Repo layout

```
backend/
  services/
    atomic/       one service per entity, owns its own storage
      user/
      event/
    composite/    orchestrates atomic services, owns no storage
frontend/
tests/
  unit/           fast, isolated, everything mocked
  integration/    crosses a real boundary (Supabase, HTTP)
```

## Stack

FastAPI + Pydantic, talking to **Supabase directly** through the
`supabase-py` client. There is no ORM — no SQLAlchemy, no SQLModel, no
`declarative_base`. Queries are written against the Supabase client
(`.table(...).select(...)`), and tables are created in Supabase itself, not
generated from Python. There is no `models.py` in this repo — the Pydantic
schemas in `schemas.py` describe payloads, never tables.

## Database schemas — one per service

This is a microservices project, so **each service owns its own Postgres schema
in Supabase.** Services do not share a schema, and no service reads another
service's tables. The schema is the database-level enforcement of the same
boundary the code rules describe.

Supabase addresses tables as `schema.table`, so the user service's table is
`user.user` and the event service's is `event.event`:

| Service | Schema | Table | Addressed as |
| --- | --- | --- | --- |
| `atomic/user` | `user` | `user` | `user.user` |
| `atomic/event` | `event` | `event` | `event.event` |

Rules:

- One schema per atomic service, named after the service.
- **Nothing goes in `public`.** If a table is in `public`, it has no owner.
- A service's client only ever touches its own schema. Needing another
  service's data means calling that service over HTTP, not querying across
  schemas.
- Composite services own no schema at all.

Select the schema on the client before the table:

```python
db.schema("event").table("event").select("*").execute()
```

### ⚠️ Expose the schema, or nothing works

> **Read this before debugging a new service.**
>
> Supabase only serves the schemas you have explicitly exposed. A brand new
> schema is invisible to the API no matter how correct your table, your keys,
> and your code are.
>
> **Fix:** Supabase dashboard → **Settings → API → Exposed schemas** → add the
> service's schema → save. PostgREST reloads within a few seconds.

This is the single most common reason a new service fails on its first
request, and **the error does not tell you that's the problem.** What you get
back instead looks like a bug in your code:

| What you see | What it actually means |
| --- | --- |
| `PGRST106` / "the schema must be one of the following" | The schema is not exposed |
| `PGRST205` / "Could not find the table ... in the schema cache" | Schema not exposed, or PostgREST hasn't reloaded |
| `42P01` / "relation does not exist" | The table or schema was never created |
| Empty `.data` with no error | Wrong schema, or RLS is filtering every row |

So when a new service returns nothing on a query you are sure is right, check
in this order:

1. Is the schema listed under Exposed schemas?
2. Does the table exist at `<service>.<table>` and not in `public`?
3. Is the service using `SUPABASE_SERVICE_KEY`, not the anon key? The anon key
   is subject to row-level security and will quietly return `[]`.

Do not start rewriting the query until all three are ruled out.

## Service structure

Every service — atomic or composite — is a FastAPI app with the same four
files. Do not invent a different layout per service.

```
backend/services/<atomic|composite>/<name>/
  app.py             FastAPI app + routes
  schemas.py         request + response schemas
  database.py        Supabase client
  Dockerfile
  requirements.txt
  README.md
```

### `schemas.py`

Pydantic schemas only. These describe the shape of requests and responses —
they are **not** table definitions; the tables live in Supabase. Keep a
separate schema per direction rather than reusing one everywhere.

```python
from pydantic import BaseModel

class UserBase(BaseModel):
    name: str
    email: str

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None

class UserRead(UserBase):
    id: int
```

Supabase returns plain dicts, so build a response with `UserRead(**row)` and
let FastAPI's `response_model` do the validating.

### `database.py`

Creates the Supabase client and nothing else. Read the URL and key from the
environment and expose a `get_db` dependency so routes never build their own
client.

```python
import os

from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_db() -> Client:
    return supabase
```

- The client is created once at import and reused; do not build one per
  request.
- Never hardcode the URL or key, and never commit them. They come from the
  environment.
- Use the service key only on the backend — it bypasses row-level security and
  must never reach the frontend.

Composite services hold no data, so they have no `database.py`. They get a
`clients.py` instead, holding the base URLs of the atomic services they call,
also read from the environment.

### `app.py`

The FastAPI app and its routes. Get the client via `Depends(get_db)` — never
import the module-level `supabase` object into a route.

```python
from fastapi import Depends, FastAPI, HTTPException
from supabase import Client

from database import get_db
from schemas import UserCreate, UserRead

app = FastAPI(title="User Service")

SCHEMA = "user"
TABLE = "user"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/user/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Client = Depends(get_db)):
    res = db.schema(SCHEMA).table(TABLE).select("*").eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="User not found")
    return res.data[0]

@app.post("/user", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: Client = Depends(get_db)):
    res = db.schema(SCHEMA).table(TABLE).insert(payload.model_dump()).execute()
    return res.data[0]
```

Notes on the client:

- `.execute()` returns a response whose `.data` is a **list**, even for a
  single row. Check `if not res.data` before indexing — that is your 404.
- `.select()` returns `[]` for a missing row rather than raising, so a missing
  record is never an exception you can catch.
- Use `.single()` only when you want a missing row to raise.

Every service exposes `GET /health`.

Routes stay thin: validate, query, return. Anything longer than a few lines
moves out of the route body.

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Copy `requirements.txt` and install before copying the rest, so the dependency
layer stays cached.

### `requirements.txt`

```
fastapi
uvicorn[standard]
supabase
pydantic
```

## Rules

- **Atomic services never call other services.** They own one entity and expose
  CRUD over it. Anything spanning two entities is a composite service.
- **Composite services own no tables.** All state lives behind an atomic
  service; composites talk to them over HTTP only.
- **No ORM.** Query Supabase through its client.
- **One Postgres schema per service**, named after the service, so tables
  are addressed as `event.event`. Never query across schemas, and never put
  a table in `public`.
- Config comes from environment variables, never from committed values.
- `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are required by every atomic
  service. Every variable a service reads must be listed in the root
  [`.env.example`](.env.example) with an empty value — that file is the
  contract for what a new developer has to fill in. `.env` itself is
  gitignored; `.env.example` is deliberately not.
- Return the right status codes: `201` on create, `404` when missing, `422` is
  handled by FastAPI's validation.

## Tests

Tests live at the repo root in `tests/`, not next to the service. Mirror the
source path:

```
tests/unit/atomic/user/test_app.py
tests/integration/atomic/user/test_app.py
```

- `tests/unit/` — never touches Supabase. Override `get_db` with a fake client
  via `app.dependency_overrides[get_db]`.
- `tests/integration/` — hits a real Supabase project and real HTTP between
  services. Point these at a test project, never production.

Use FastAPI's `TestClient`. Each test cleans up the rows it creates.

```bash
pytest tests/unit
pytest tests/integration
```

## When adding a new service

1. Create the folder under `atomic/` or `composite/`, whichever the rules above
   call for.
2. Add all four files plus `requirements.txt` and `README.md`.
3. Add the `README.md` even if the service is a stub — git will not commit an
   empty folder.
4. Create the matching test folders under `tests/unit/` and
   `tests/integration/`.
5. Create the service's schema in Supabase, then the table inside it
   (`<service>.<table>`) — neither gets generated from Python.
6. **Expose the new schema** under Settings → API → Exposed schemas. Skipping
   this makes every query fail with an error that points somewhere else — see
   [Expose the schema, or nothing works](#%EF%B8%8F-expose-the-schema-or-nothing-works).
7. List the service in its parent `README.md` table.
