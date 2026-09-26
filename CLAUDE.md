# AGENTS.md

Conventions for this repo. Follow them when adding or changing a service.

## Repo layout

```
backend/
  services/
    atomic/       one service per entity, owns its own storage
      users/
      events/
    composite/    orchestrates atomic services, owns no storage
  sql/            schema definition per service, applied by hand
frontend/
tests/
  unit/           fast, isolated, everything mocked
  integration/    crosses a real boundary (Supabase, HTTP)
```

## Branches and commits

Work never lands directly on `main`. Every change goes on its own branch, named
for the story it implements: the story id, a slash, then the story name.

```
S-01/user-accounts
S-07/event-requests
```

The story id goes first so every branch belonging to one story sorts together
and `git branch --list 'S-07/*'` is the whole story. The story name is the
story's title in lowercase kebab-case — short, and the same name the tracker
uses, so the branch reads as the story without looking the id up.

Nothing else goes in the name. No task ids, no initials, no `feature/` prefix.
The pull request is where the work gets described.

Infrastructure and tooling work that belongs to no story — CI, docs, repo
setup — goes on `update/<area>` instead, e.g. `update/ci`.

Create the branch before writing any files, so the first commit is already in
the right place. **That means the story id and name are needed before the work
starts, not at the end.** If you were not given them, ask — do not invent them
and do not start on a placeholder name meaning to rename it later.

### The story goes in the pull request

The branch carries the story too, but a branch is deleted on merge. The pull
request is what a reviewer actually reads and what the tracker links to, so
every PR description names the story it implements, id verbatim:

```markdown
Story: S-01 User accounts

Adds sign-up, login, logout and /users/me to the users service, wrapping
Supabase Auth so the browser never holds a token.
```

A description can be edited at any time, which is the point — the story can be
added or corrected later without rewriting anything.

Commit messages need no id. Write them for whoever is reading the diff: what
changed and why, not which ticket asked for it.

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

Supabase addresses tables as `schema.table`, so the users service's table is
`users.users` and the events service's is `events.events`:

| Service | Schema | Table | Addressed as |
| --- | --- | --- | --- |
| `atomic/users` | `users` | `users` | `users.users` |
| `atomic/events` | `events` | `events` | `events.events` |
| `atomic/venues` | `venues` | `venues` | `venues.venues` |

Rules:

- One schema per atomic service, named after the service.
- **Names are plural.** `users`, not `user`. Beyond reading better, it dodges
  Postgres reserved words: `create schema user` is a syntax error, `users` is
  fine. The same trap waits on `order`, `group`, `session`, and `default` —
  plural clears all of them.
- **Nothing goes in `public`.** If a table is in `public`, it has no owner.
  Write every statement as `schema.table` — `create table users.users`, never
  `create table users`. The SQL Editor has `public` on its search path, so an
  unqualified name lands there silently and still looks like it worked.
- A service's client only ever touches its own schema. Needing another
  service's data means calling that service over HTTP, not querying across
  schemas.
- Composite services own no schema at all.

Select the schema on the client before the table:

```python
db.schema("events").table("events").select("*").execute()
```

### Creating a new schema — hand this to the developer

**An agent cannot apply this.** Creating a schema, granting privileges, and
exposing the schema all happen in the Supabase dashboard, outside this repo.

What an agent *does* do is **write the SQL to that service's file in
[`backend/sql/`](backend/sql/README.md)** — `backend/sql/users.sql` — and
commit it. The database is not generated from Python, so those files are the
only record of what the schema is, and a project should be rebuildable by
running them.

Then **stop and hand the developer the SQL**, and ask them to:

1. Run it in the Supabase **SQL Editor** — in **both** the dev and test
   projects, or the two databases drift apart.
2. Add the schema under **Data API → Settings → Exposed schemas**.

Do not report the service as working until they confirm both. The code is
correct and still fails until then.

```sql
-- 1. Create the schema, named after the service. Plural — `user` (singular)
--    is a reserved word in Postgres and would need quoting everywhere.
create schema if not exists users;

-- 2. Create the table inside it. Never in public.
create table if not exists users.users (
  id         bigint generated always as identity primary key,
  name       text not null,
  email      text not null unique,
  created_at timestamptz not null default now()
);

-- 3. Grant access to the backend role.
--    Supabase pre-configures privileges on `public` only. A schema you create
--    yourself has NONE, so service_role cannot read it until this runs — even
--    once the schema is exposed.
grant usage on schema users to service_role;
grant all on all tables in schema users to service_role;
grant all on all sequences in schema users to service_role;

-- 4. Same grants for tables added later. This only affects tables created
--    AFTER it runs, which is why step 3 is still needed for existing ones.
alter default privileges for role postgres in schema users
  grant all on tables to service_role;
alter default privileges for role postgres in schema users
  grant all on sequences to service_role;

-- 5. Enable RLS so nothing leaks if an anon key ever reaches this table.
--    service_role bypasses RLS, so the services keep working.
alter table users.users enable row level security;

-- 6. Nudge PostgREST if the table still is not visible after all of the above.
notify pgrst, 'reload schema';
```

Only `service_role` is granted, because only the backend touches tables. Do not
grant `anon` or `authenticated` unless the browser genuinely needs to query
that table directly — the frontend goes through the services.

### ⚠️ Expose the schema *and* the table, or nothing works

> **Read this before debugging a new service.**
>
> There are **two** separate steps, and doing only one leaves the service just
> as broken as doing neither.
>
> **1. Expose the schema** — Supabase dashboard →
> **Data API → Settings → Exposed schemas** → add the service's schema →
> save.
> Without this the whole schema is invisible to the API, no matter how correct
> your table, keys and code are.
>
> **2. Grant the table** — an exposed schema does not mean its tables are
> reachable. PostgREST serves a table only if the calling role has privileges
> on that table:
>
> ```sql
> grant usage on schema users to service_role;              -- the schema
> grant all on all tables in schema users to service_role;  -- the tables
> ```
>
> `grant usage` on the schema alone is not enough. Nor is the dashboard
> setting. You need both steps.

**Watch the order.** `grant all on all tables in schema ...` applies only to
tables that exist **when it runs**. Add a table afterwards and it is in an
exposed, granted schema and still unreachable. That is what the
`alter default privileges` lines in the SQL block are for — they cover tables
created later. If a new table 404s while its neighbours work, its grant is
missing.

This is the single most common reason a new service fails on its first
request, and **the error does not tell you that's the problem.** What you get
back instead looks like a bug in your code:

| What you see | What it actually means |
| --- | --- |
| `PGRST106` / "the schema must be one of the following" | The schema is not exposed |
| `PGRST205` / "Could not find the table ... in the schema cache" | Schema not exposed, the table has no grant, or PostgREST hasn't reloaded |
| `42501` / "permission denied for schema" | The schema grant was never run |
| `42501` / "permission denied for table" | The schema is granted but this table is not — added after the grants ran |
| `42P01` / "relation does not exist" | The table or schema was never created |
| `42601` / syntax error on `create schema <name>` | The name is a Postgres reserved word — use the plural |
| Empty `.data` with no error | Wrong schema, or RLS is filtering every row |

So when a new service returns nothing on a query you are sure is right, check
in this order:

1. Is the schema listed under Exposed schemas?
2. Was `grant usage` run on the schema?
3. Was `grant all on all tables` run on **this** table? A table added after the
   grants is not covered unless `alter default privileges` was set first.
4. Does the table exist at `<service>.<table>` and not in `public`?
5. Is the service using `SUPABASE_SERVICE_KEY`, not the anon key? The anon key
   is subject to row-level security and will quietly return `[]`.

Do not start rewriting the query until all five are ruled out.

## Service structure

Every service is a FastAPI app with the same layout. Do not invent a different
one per service.

```
backend/services/<atomic|composite>/<name>/
  app.py             FastAPI app + routes
  schemas.py         request + response schemas
  database.py        Supabase client        (atomic only)
  clients.py         outbound HTTP          (composite only)
  Dockerfile
  requirements.txt
  README.md         API doc — see below
```

Atomic services own data, so they have `database.py`. Composite services own
none and call other services instead, so they have `clients.py`. Everything
else is identical.

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

### `clients.py` (composite services)

Outbound HTTP goes in `clients.py`, exposed as a dependency — the same reason
`database.py` exists. It keeps every base URL in one place, gives you one place
to set timeouts, and gives composite routes a seam that unit tests can override
exactly like `get_db`.

```python
import os

import httpx

USERS_URL = os.environ["USERS_SERVICE_URL"]
EVENTS_URL = os.environ["EVENTS_SERVICE_URL"]

def get_users_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=USERS_URL, timeout=5.0)

def get_events_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=EVENTS_URL, timeout=5.0)
```

Always set a timeout. A composite calling three services without one is how a
single slow atomic service stalls every request in the system.

### `app.py`

The FastAPI app and its routes. Get the client via `Depends(get_db)` — never
import the module-level `supabase` object into a route.

```python
from fastapi import Depends, FastAPI, HTTPException
from supabase import Client

from database import get_db
from schemas import UserCreate, UserRead

app = FastAPI(title="Users Service")

SCHEMA = "users"
TABLE = "users"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Client = Depends(get_db)):
    res = db.schema(SCHEMA).table(TABLE).select("*").eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="User not found")
    return res.data[0]

@app.post("/users", response_model=UserRead, status_code=201)
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

Every service hardcodes **its own port** from the table in
[Ports](#ports) — not a shared 8000. This is the `users` service (8001):

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
```

Copy `requirements.txt` and install before copying the rest, so the dependency
layer stays cached.

Distinct ports mean every service can run at once whether or not Docker is
involved, and a container's internal port matches its published one — so a URL
is the same from the host and from inside the network.

### `requirements.txt`

```
fastapi
uvicorn[standard]
supabase
pydantic
```

### `README.md`

**Every service documents its own API here.** A reader should be able to call
the service without opening `app.py`. Four things, always:

1. **Endpoints** — method, path, and what each one does. One row each.
2. **Request** — the body fields or query parameters each endpoint takes, with
   types and which are required. Name the actual fields: "a user payload" is
   not a parameter list.
3. **Response** — the JSON that comes back on success, and every status code it
   answers with on failure, with what each one means. Show the body, do not
   describe it.
4. **How to run it** — the command for **development** and the command for
   **tests**, both spelled out, including whatever has to be true first: the
   schema applied, `.env` or `.env.test` filled in, the stack up.

A stub service still gets a README — git will not commit an empty folder — but
once it has routes, it has all four.

Keep it in step with the code. A README describing a field that no longer
exists is worse than no README, because it is believed.

## Ports

Every service gets its own port. 8000 is the gateway's.

| Service | Port | Reached at |
| --- | --- | --- |
| **Kong (gateway)** | **8000** | `http://localhost:8000/api/...` — the only one a browser uses |
| `atomic/users` | 8001 | `http://users:8001` (compose) / `http://localhost:8001` |
| `atomic/events` | 8002 | `http://events:8002` / `http://localhost:8002` |
| `atomic/venues` | 8003 | `http://venues:8003` / `http://localhost:8003` |
| `frontend` | — | `http://frontend:80` — through Kong only, see below |
| first composite | 8100 | reserved |

Services stay published on their own ports as well, so you can bypass the
gateway to test a service on its own — which is what the integration tests do.

**The frontend is the exception: it is not published at all.** The app calls a
relative `/api`, so it is only coherent on an origin that serves both it and
the services — Kong. Published on its own port it would load and then 404 every
API call, which reads as a broken backend. Reach it at
`http://localhost:${KONG_PROXY_PORT}`, or run `npm run dev` for hot reload,
whose Vite proxy imitates the same arrangement.
Composites start at 8100 to leave the 800x block to atomic services.

A new service claims the next free port and must be registered in **four**
places. Miss one and it does not run, or runs and cannot be reached:

1. its `Dockerfile` — `EXPOSE` and the `--port` in `CMD`
2. `.env.example` — `<NAME>_SERVICE_PORT`, plus `<NAME>_SERVICE_URL` if
   composites call it
3. `docker-compose.yml` — a service block publishing
   `"${<NAME>_SERVICE_PORT}:<port>"`, with a `/health` healthcheck so
   dependants can wait on it
4. `backend/kong/kong.yml` — a route, if the browser reaches it

### The gateway

Everything the browser calls goes through Kong, so the frontend knows one
prefix — `/api` — and never a port. A new service is one entry, and the
service's own path prefix goes on the **url**, not the route:

```yaml
  - name: events
    url: http://events:8002/events     # the service's own prefix
    routes:
      - name: events
        paths:
          - /api/events                # what the browser calls
        strip_path: true
```

Kong strips `/api/events` and appends what is left to the url, so
`/api/events/42` arrives as `/events/42`. Leave the prefix off the url and it
arrives as `/42` — a 404 that reads like the service is broken.

Kong is DB-less: that file is the entire configuration, so a routing change is
a diff, not an admin API call. It takes effect on `docker compose restart kong`.

A service with no browser-facing routes — one only composites call — needs no
Kong entry. More in [`backend/kong/README.md`](backend/kong/README.md).

## Running the stack

```bash
cp .env.example .env      # fill in the Supabase values first
docker compose up --build
```

Inside the compose network a service is reachable at its **compose service
name** — `http://users:8001`, not `localhost`. `localhost` inside a container
means that container. This is why `.env.example` defaults
`USERS_SERVICE_URL` to `http://users:8001`; switch it to `localhost` only when
running services by hand:

```bash
cd backend/services/atomic/users
uvicorn app:app --reload --port 8001
```

Each service defines a `/health` check in `docker-compose.yml`, so a composite
can wait for its dependencies with `depends_on: condition: service_healthy`
instead of racing them at startup.

The frontend reaches the backend through `VITE_API_URL`, set in
`frontend/.env`. Point it at the composite service that serves the frontend —
or, once Kong is set up as the gateway, at Kong, which routes to the services
behind it.

## Frontend / UI

`frontend/` is React + Tailwind CSS + `lucide-react`, no `framer-motion`. Every
page follows the same design system below, so a new page matches the existing
ones without re-deriving the look each time.

### Environment constraint — no Tailwind JIT

Only Tailwind's pre-built utility classes resolve. Arbitrary-value syntax like
`bg-[#123456]` or `font-[Fraunces]` does **not** work. Structural classes
(`flex`, `grid`, `gap-4`, `rounded-sm`, `px-6`, `max-w-6xl`) come from
Tailwind; every brand color and font is applied through inline `style={{}}` or
a plain `<style>` block instead. Do not reach for arbitrary-value Tailwind
classes to fix a color or font that doesn't look right — that's the sign it
needs to go through `style` instead.

### File layout

One file per page, CSS and JS together. Break a page into small components
inside that same file (`Header`, `Hero`, `Footer`, ...) rather than splitting
across files, and export exactly one default per page.

### Color tokens

Define this object once per page and reference it via `style`, never inline
hex elsewhere:

```js
const C = {
  ink: "#10192B",       // primary text, dark section backgrounds
  inkSoft: "#1C2A42",   // surfaces sitting on top of `ink` (cards on dark bg)
  inkFaint: "#4C5A70",  // secondary/muted text
  paper: "#F8F6F1",     // page background (light sections)
  paperDim: "#F1EEE6",  // slightly recessed light surface (alt sections)
  line: "#E3DFD3",      // hairline borders on paper
  lineOnInk: "#2A3A54", // hairline borders on ink
  teal: "#0E7C74",      // primary accent — CTAs, active states, links
  tealBright: "#149E92",// accent on dark backgrounds (better contrast)
  tealDeep: "#0A5F59",  // pressed/active state of primary accent
  sky: "#3C6E96",       // secondary accent — icons, minor highlights
  amber: "#B5842B",     // warning / partial status
  rose: "#B25547",      // error / urgent status
  green: "#3F8F5F",     // success / operational status
};
```

- `paper` is the default page background; `ink` is for dark bands and primary
  text. Never pure black or Tailwind's `slate-900`.
- `teal` is the only primary action color on a page. `sky`/`amber`/`rose`/
  `green` are supporting/status colors, not alternative CTAs — don't
  introduce a second "primary" hue.
- No gradients as decoration. Keep body text at 4.5:1 contrast against
  whichever background token it sits on.

### Typography

```css
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap');
.font-display { font-family: 'Fraunces', Georgia, serif; }
.font-ui { font-family: 'Inter', ui-sans-serif, system-ui, sans-serif; }
```

`.font-display` (Fraunces) is for headlines, big stat numerals, and hero copy
only — it's the brand voice, used sparingly. `.font-ui` (Inter) is the default
for everything else (nav, body, labels, forms, tables); set it on the page's
root wrapper and opt into `.font-display` per element.

Reuse this scale rather than inventing new sizes per page:

| Element | Classes |
| --- | --- |
| Hero/H1 | `text-4xl sm:text-5xl font-display leading-[1.08]` |
| Section H2 | `text-3xl font-display` |
| Big stat numeral | `text-4xl font-display` |
| Body copy | `text-base`/`text-sm`, `.font-ui`, `leading-relaxed`, `inkFaint` |
| Meta/caption | `text-xs`, `.font-ui`, `inkFaint` |

No all-caps eyebrow labels above headings, and no bolding/coloring a single
word inside a headline for emphasis. Constrain body copy width (`max-w-sm` /
`max-w-md` / `max-w-3xl`) so paragraphs don't run edge-to-edge.

### Layout

- Container: `max-w-6xl mx-auto px-6` for full-width sections, `max-w-3xl` for
  narrow long-form content (testimonials, prose).
- Left-align hero and section copy — centered stacks read as a generic
  template.
- Vary section shape instead of repeating a card grid everywhere: hero is a
  two-column asymmetric grid; stats are one row divided by hairlines
  (`divide-x`), not separate cards; a features/services section is one larger
  lead item plus a compact `divide-y` list for the rest, not N identical
  cards; a testimonial is a plain block quote on a dimmed band, no card
  border or shadow.
- Alternate section backgrounds between `paper`, `paperDim`, and `ink` for
  rhythm instead of adding borders/shadows everywhere.
- Numbered markers (01/02/03) only for a genuine sequence (a real timeline or
  ordered steps) — not for nav items, stats, or a features list.
- `rounded-sm` everywhere buttons/inputs/cards get radius. Don't mix radius
  sizes on one page.

### One bold moment per page

Exactly one visually rich, animated element per page; everything else stays
quiet and structural:

1. Identify the thing most characteristic of what the page does (a live
   preview, a key number, a real interaction).
2. Build that with real motion/data — a working count-up, progress
   animation, or countdown — not a static mockup image.
3. Keep every other element restrained: hairline borders, no shadows outside
   that one hero element, minimal hover states.

Don't add scroll-triggered fade-ins to every section or hover-lift to every
card — reserve entrance animation (`rise-in`, ~0.7s, staggered by up to
~150ms for at most two elements) for the single hero element:

```css
@keyframes riseIn {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
.rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
```

| Trigger | Use |
| --- | --- |
| Page load | One `rise-in` on the single hero element only |
| Scroll into view | Count-up on stat numerals (`IntersectionObserver`, threshold 0.4) |
| Hover on primary button | `-translate-y-0.5`, 200ms |
| Hover on nav link | Color transition only, 200ms, no movement |
| Panel/drawer open | translateX slide, 320ms |
| Anything else | No animation |

Respect `prefers-reduced-motion` — animated classes should degrade to an
instant state change when it's set.

### Components to reuse

**Primary button**

```jsx
<button
  className="px-5 py-3 rounded-sm font-medium transition-transform duration-200 hover:-translate-y-0.5"
  style={{ backgroundColor: C.teal, color: C.paper }}
>
  Start planning
</button>
```

**Secondary/ghost button**

```jsx
<button
  className="px-5 py-3 rounded-sm font-medium border transition-colors duration-200"
  style={{ borderColor: C.ink, color: C.ink }}
>
  Log in
</button>
```

**Sticky header** — transparent at the top; once `window.scrollY > 8`, gains a
translucent blurred background and a hairline bottom border. Reuse the same
scroll-listener pattern on every page that has a header.

**Slide-over panel** — the house pattern for any secondary flow that
shouldn't navigate away (login, filters, item detail, quick-create), used
instead of a centered modal dialog:

- Fixed, full height, right-anchored, `max-w-md`.
- Backdrop `rgba(16,25,43,0.5)`, closes on click.
- Enter animation: `translateX` 100% → 0 over `0.32s`
  (`cubic-bezier(0.22, 1, 0.36, 1)`).
- Closes on `Escape`, always has a visible `X` close button top-right, traps
  focus while open, returns focus to the trigger on close.

**Status indicators** — small filled or dashed dots: `green` = done/
operational, `amber` = partial/warning, `inkFaint` outline = not started,
`rose` = urgent/error. Always pair the color with a text label, never color
alone.

**Stat numeral** — `.font-display` number in `ink`/`paper`, small `.font-ui`
label underneath in `inkFaint`, `tealBright`/`teal` colored suffix (`+`, `%`,
`h`). Animate with count-up on scroll-into-view, except for anything already
above the fold in the page's "one bold moment," which animates on mount.

**Divided list row** (services, checklists) — icon (20px, `sky` or
`inkFaint`) + title (`text-base font-medium`, `ink`) + one-line description
(`text-sm`, `inkFaint`), rows separated by `divide-y` in `line`. No card
background, no shadow.

### Copy voice

Plain, active-voice, specific. Buttons say what happens ("Start planning",
"Sign in", "Save changes"), not "Submit" or "Learn more". No filler
adjectives ("revolutionary", "seamless", "cutting-edge"). Section headings
describe what the section is ("Venue & vendor logistics"), not a marketing
tagline. Numbers read like product facts ("98.7% on-time launch rate"), not
superlatives. Errors and empty states say what happened and what to do next,
in the product's voice.

### Accessibility floor

Non-negotiable on every page:

- Icon-only buttons have an `aria-label`.
- Visible focus states on every interactive element — don't remove Tailwind's
  default outline without replacing it.
- Color is never the only signal for status; pair it with a label.
- Panels/drawers trap focus while open, close on `Escape`, return focus to
  the trigger on close.
- 4.5:1 text contrast against whichever background token the text sits on.

### Checklist before shipping a page

- [ ] Uses the `C` color object and `.font-display`/`.font-ui` — no raw
      Tailwind color/font classes for brand elements.
- [ ] Exactly one bold/animated hero moment; everything else is quiet.
- [ ] Section shapes vary — no repeated "four identical cards" pattern.
- [ ] Buttons/panels reuse the exact patterns above rather than new variants.
- [ ] Copy follows the active-voice, no-filler rules above.
- [ ] Accessibility floor above is met.
- [ ] Single file, CSS + JS together, one default export.

## CI

Three workflows in `.github/workflows/`. All run on pushes and pull requests to
`main`, and can be started by hand.

| Workflow | What it does | When it runs |
| --- | --- | --- |
| `tests.yml` | Runs the test suites — see below | Every push. A failure fails the job. |
| `semgrep-sast.yml` | Static analysis of the code — Python, JavaScript, React, secrets | Every push. Findings fail the job. |
| `wapiti-dast.yml` | Attacks the running services and reports what it finds | Every push, once a service has a `Dockerfile` |

### What `tests.yml` runs

Three independent jobs, so a broken unit test and a broken container are told
apart at a glance:

| Job | Command | Needs |
| --- | --- | --- |
| **Unit (pytest)** | `pytest tests/unit` | Nothing |
| **Unit (node)** | `node --test tests/unit/frontend/test_*.mjs` | Nothing — no `npm ci`, these import `frontend/src/lib/` directly |
| **Integration (pytest + docker)** | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration` | The repo secrets below |
| **End-to-end (playwright)** | the same stack, plus `playwright install --with-deps chromium`, then `pytest tests/e2e` | The repo secrets below |

Both Docker jobs bring up the **whole** stack, Kong and the frontend included:
the events tests exercise the gateway routes as well as the service directly,
and the browser has nothing to open otherwise. The e2e job waits for the
integration job, pass or fail, rather than running alongside it: both write to
the same test project, and a coordinator account an e2e journey creates
mid-way through an integration test is one that test never blocked, so it wins
the assignment. Both are skipped on pull
requests from forks — those get no secrets, and a job that cannot authenticate
would fail for a reason the contributor cannot fix.

The e2e job uploads Playwright's `test-results/` on every run. A failed browser
test is close to unreadable without them.

A missing secret would otherwise surface as "container is unhealthy", which
points nowhere — so the job checks for them first and fails naming the
variable. `wapiti-dast.yml` does the same, deliberately duplicated rather than
factored into a composite action for two call sites.

### Repo secrets

The integration job and Wapiti both need `SUPABASE_URL`,
`SUPABASE_SERVICE_KEY` and `SUPABASE_ANON_KEY` in
**Settings → Secrets and variables → Actions**. Without them the containers exit
at import and the job fails.

**These are the test project's credentials, not your own project's.** Both
create and delete real rows — the integration tests by design, and the scan
because it attacks every endpoint it finds, including `POST`, `PUT` and
`DELETE`. The service key bypasses row-level security, so nothing stops either
of them. CI writes the secrets to `.env.test` and starts the stack with
`--env-file .env.test`, exactly as you would locally.

The test project needs the same setup as your own: every schema in
`backend/sql/` applied, exposed, and granted. An integration job that fails on
a fresh project is almost always that, not the code.

## Rules

- **Acceptance criteria come from the developer, and the test cases are
  confirmed before any code is written.** Never invent an acceptance criterion
  or infer one from a task title — ask, and wait. See
  [Acceptance criteria and test cases come first](#acceptance-criteria-and-test-cases-come-first).
- **Atomic services never call other services.** They own one entity and expose
  CRUD over it. Anything spanning two entities is a composite service.
- **Composite services own no tables.** All state lives behind an atomic
  service; composites talk to them over HTTP only.
- **No ORM.** Query Supabase through its client.
- **One Postgres schema per service**, named after the service and plural, so
  tables are addressed as `events.events`. Never query across schemas, and
  never put a table in `public`.
- **Each service's schema lives in `backend/sql/<service>.sql`**, declarative
  and committed with the code that needs it. Change it by editing the file and
  rebuilding the schema, not by patching the database by hand — and apply it to
  the dev *and* test projects at the same time.
- Config comes from environment variables, never from committed values.
- `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are required by every atomic
  service. Every variable a service reads must be listed in the root
  [`.env.example`](.env.example) with an empty value — that file is the
  contract for what a new developer has to fill in. `.env` itself is
  gitignored; `.env.example` is deliberately not.
- **`.env` is your project, `.env.test` is the throwaway one.** Integration
  tests, e2e tests and any scanning run against `.env.test`
  (`docker compose --env-file .env.test up`), because they create and delete
  real rows. **Start the stack immediately before running them** — a container
  keeps whichever file created it, so a stack left running from earlier can be
  on `.env` without saying so. See
  [Bring the stack up yourself](#⚠️-bring-the-stack-up-yourself-every-time).
- Return the right status codes: `201` on create, `404` when missing, `422` is
  handled by FastAPI's validation.

## Tests

Tests live at the repo root in `tests/`, not next to the service, in a folder
that mirrors the source path:

```
tests/unit/atomic/users/test_app.py
tests/unit/atomic/users/TEST_CASES.md
tests/integration/atomic/users/test_app.py
tests/integration/atomic/users/TEST_CASES.md
```

Every test folder gets an empty `__init__.py`, all the way down. Two services
both have a `tests/unit/.../test_app.py`, and without packages pytest cannot
give them distinct module names — `pytest tests` fails to collect with "import
file mismatch" while each suite passes on its own. Being a package also means a
test imports its neighbouring conftest relatively: `from .conftest import ...`.

- **`tests/unit/`** — one service on its own, with a fake in place of Supabase.
  Swap it in with `app.dependency_overrides[get_db]`; a `MagicMock` handles the
  `.schema().table().select().execute()` chain without extra code. No network,
  no database, no Docker.
- **`tests/integration/`** — the real service in Docker against a real Supabase
  project, plus, once composite services exist, a composite calling an atomic
  service over HTTP.

**Many unit tests, few integration tests.** Unit tests cost nothing, so cover
every case in them — good input, bad input, a missing record. Integration tests
are slow and need the stack running, so keep them to what only they can prove:
usually one save-then-read per service, which confirms the table, the grants,
the schema exposure and the connection all at once.

**A passing unit test does not mean the service works.** The fake agrees with
everything, so none of this shows up until integration: a column that does not
exist, the wrong Postgres schema, a table left in `public`, missing grants, a
schema that was never exposed, RLS filtering every row, or a composite calling
`localhost` instead of the Docker service name.

Integration tests point at the **test** Supabase project, never a real one, and
delete the rows they create — the suite has to run twice in a row. That is what
`.env.test` is for: `.env` is the project you work against day to day,
`.env.test` is the one tests are allowed to destroy. Both are gitignored.

```bash
pytest tests/unit

docker compose --env-file .env.test up -d --build --wait
pytest tests/integration
```

### ⚠️ Bring the stack up yourself, every time

> **Read this before believing an integration or e2e failure.**
>
> `--env-file .env.test` is read **once, when a container is created**, and
> baked in. `pytest` never starts anything — it assumes a stack is already
> running and reads `.env.test` separately, on the host, for the admin client
> it cleans up with.
>
> So there are two readers at two different moments, and they can disagree.
> A plain `docker compose up` — from another terminal, an IDE's Docker panel,
> or Docker Desktop restarting containers on launch — recreates the stack from
> **`.env`**, your own project. Nothing warns you. The services are healthy and
> answer every request; they are simply writing somewhere else.
>
> **Always start the stack immediately before you run the tests**, in the same
> sitting. Never reuse one from earlier — not even one you started correctly.
>
> ```bash
> docker compose --env-file .env.test down -v
> docker compose --env-file .env.test up -d --build --wait
> pytest tests/integration
> ```
>
> To check a stack you did not just start:
>
> ```bash
> docker exec spm-users-1 python -c "import os;print(os.environ['SUPABASE_URL'])"
> ```
>
> That must equal `SUPABASE_URL` in `.env.test`. If it equals the one in
> `.env`, the stack is on your own project — recreate it.

**What this looks like when it happens.** The tests write through the services
into one project and verify through the admin client in the other, so the row
is genuinely missing where it looks:

| What you see | What you will go and check | What it actually is |
| --- | --- | --- |
| `no row in users.users -- check the schema is exposed and granted` | grants, exposed schemas, RLS | the row is in the other project |
| `assert 401 == 201` on a route that works by hand | the auth code, the cookies | the token came from a different project's Auth |
| `AuthApiError: User not found` during cleanup | the fixture's teardown | the user was created in the other project |

None of these name the cause, and all three send you somewhere real but
irrelevant — the same failure mode as
[the exposed-schema trap](#%EF%B8%8F-expose-the-schema-and-the-table-or-nothing-works).
Rule out the project before you touch any SQL.

**It leaves rows behind in your dev project.** Cleanup runs against
`.env.test`, so anything the services wrote to `.env` survives, and the suite
that is supposed to be runnable twice has quietly polluted the database you
demo from. They are addressed `spm-test-*` and `spm-e2e-*`, so they are easy
to find:

```sql
select id, email from users.users where email like 'spm-%';
```

**CI cannot hit this.** Each job writes `.env.test`, brings the stack up, and
runs pytest in one sequence, so the two always agree. This is a local-only
failure, which is worse — it is the environment you debug in.

- **`tests/e2e/`** — a real browser, driving the built frontend through Kong
  against both services and a real (test) Supabase project. Needs the whole
  stack up, Chromium installed, and email confirmation off in the test project.

**Fewer e2e tests than integration tests.** They are the slowest thing in the
repo and have more ways to be flaky than everything else combined, so a
journey earns its place only if no other suite can prove it: Kong's routing,
nginx's SPA fallback, an httpOnly cookie surviving a page load, and whether
`frontend/src/lib/access.js` still agrees with the events service's
`authorization.py`. Validation rules and status codes are already covered in
`tests/unit/` — do not restage them in a browser.

Name a spec after the journey, not the service: `test_sign_up.py`, never
`test_users.py`. Details in [`tests/e2e/README.md`](tests/e2e/README.md).

### `TEST_CASES.md`

The tests are the code; `TEST_CASES.md` is the written record of what they
prove. One per test folder, next to the `test_*.py` it describes.

**The specification half is written before the code and confirmed by the
developer** — see
[Acceptance criteria and test cases come first](#acceptance-criteria-and-test-cases-come-first).
Cases written afterwards describe what was built instead of checking it.

Each case states the **specification** — written once, changed only when the
requirement changes:

| Field | What goes in it |
| --- | --- |
| ID | `TC-<SERVICE>-<NNN>`, see below |
| Scenario | One line: the objective |
| Pre-conditions | The starting state. Unit: what the fake returns. Integration: `.env.test`, the stack, the schema exposed and granted |
| Steps | Numbered, followable by someone who has not read the code |
| Test data | The actual values, not a description of them |
| Expected | Specific enough that two people agree on pass/fail |

Then the **latest execution** — overwritten each run, not appended:

| Field | What goes in it |
| --- | --- |
| Actual | What happened |
| Status | Pass / Fail / Not Executed / Blocked |
| Evidence | The pytest node id, plus a CI link or issue number where one applies |

No run history is kept, only the most recent result, so each file's header
records the commit and environment it was last run against — a pass is only
ever passing as of that build.

**Blocked is not Fail.** Blocked means the case could not run — the schema is
not applied, the stack is down. Say which. An integration case is honestly
Blocked until the developer has run the SQL and exposed the schema, and that
is worth writing down rather than leaving blank.

Vague cases are the failure mode. "Create a user with valid data" is a wish;
`{"name": "Ada", "email": "ada@example.com"}` → `201` with `id` present, and
readable at `GET /users/{id}`, is a test case.

**IDs.** `TC-<SERVICE>-<NNN>`, service uppercased, numbered by layer:

```
TC-USERS-001    001-099   unit
TC-USERS-101    101-199   integration
```

Allocated in order and never recycled. Drop a case and the gap stays — an ID
quoted in a commit or an issue has to keep pointing at the same case.

More detail in [`tests/README.md`](tests/README.md).

## Acceptance criteria and test cases come first

**Nothing is written until both exist.** Not the service, not a route, not a
page. This is a hard gate, and it is the developer's to open.

1. **The developer provides the acceptance criteria.** An agent does not write
   them, infer them from the task title, or work from a guess at what the story
   probably means. If they were not given, **ask and wait** — the same rule as
   the story id, for the same reason: an acceptance criterion nobody wrote down
   gets quietly satisfied by whatever the code happens to do.

2. **The test cases are written next, and the developer confirms them.** Write
   them into the relevant `TEST_CASES.md` as specification — ID, Scenario,
   Pre-conditions, Steps, Test data, Expected — with Actual blank and Status
   `Not Executed`. Then stop and have the developer agree they are the right
   cases, and that together they cover every acceptance criterion.

Only then does code get written.

The order is the point. `TEST_CASES.md` separates what a case *specifies* from
what a run *produced*, and cases written after the code collapse that
distinction: they stop being a check on the work and become a description of
it, agreeing with whatever was built, bugs included. Confirming them up front
is also the cheapest moment to discover that an acceptance criterion is
ambiguous, untestable, or describes something nobody meant to build — the cost
of finding that out in review is a rewrite.

Write the cases for every criterion, including the ones that are inconvenient.
If a criterion cannot be expressed as a case with a specific expected result,
it is not ready to build against; say so and ask for it to be reworded rather
than picking an interpretation and coding to it.

## When adding a new service

1. **Acceptance criteria in hand and test cases confirmed**, per the section
   above. Do not skip ahead to the folder because the service "obviously" needs
   to exist.
2. Branch — see [Branches and commits](#branches-and-commits). The
   branch is named `<story-id>/<story-name>`, so both have to be in hand
   before anything is written; ask for them if they were not given. Then create the
   folder under `atomic/` or `composite/`, whichever the rules above call for.
3. Add the files listed in [Service structure](#service-structure) —
   `database.py` for an atomic service, `clients.py` for a composite.
4. Add the `README.md` — endpoints, request and response params, and how to
   run it for development and for tests. See [`README.md`](#readmemd). Add it
   even if the service is a stub; git will not commit an empty folder.
5. Create the matching test folders under `tests/unit/` and
   `tests/integration/`, each with an empty `__init__.py` and a
   `TEST_CASES.md` recording its cases — see [`TEST_CASES.md`](#test_casesmd).
6. Write the schema SQL from
   [Creating a new schema](#creating-a-new-schema--hand-this-to-the-developer)
   to `backend/sql/<service>.sql`, commit it, then **hand it to the developer
   to run**. Schemas, tables, and grants are not generated from Python and an
   agent cannot create them.
7. **Ask the developer to expose the schema** under Data API → Settings →
   Exposed schemas, *and* to confirm the table grants ran — both are required, and one
   without the other leaves the service broken. Confirm before you call the
   service finished. Skipping either makes every query fail with an error that points
   somewhere else — see
   [Expose the schema, or nothing works](#%EF%B8%8F-expose-the-schema-and-the-table-or-nothing-works).
8. Claim the next free port and register it in all four places — the
   Dockerfile, `.env.example`, `docker-compose.yml`, and
   `backend/kong/kong.yml` if the browser reaches it. See [Ports](#ports).
9. List the service in its parent `README.md` table.
