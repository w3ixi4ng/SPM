# ConnectSphere

**ConnectSphere** is an event management platform. Event Organisers submit
event requests, Coordinators plan them, and Venue Staff, Technical Support and
Safety Officers each handle their part before the event opens to Attendees for
registration. It is built as FastAPI microservices on Supabase, behind a Kong
gateway, with a React frontend.

**Repository:** https://github.com/w3ixi4ng/SPM

---

## User roles

| Role | What they do |
| --- | --- |
| Event Organiser | Creates event requests, saves drafts, submits them, requests changes or cancellation, and closes registration |
| Event Coordinator Lead | Assigns unassigned event requests to a Coordinator and reassigns them when needed |
| Event Coordinator | Reviews assigned requests, books venues, records equipment, assigns Technical Support, and handles changes and cancellations |
| Venue Staff | Manages the venue catalogue, approves or rejects booking requests, places holds, and marks venues unavailable |
| Technical Support | Manages the equipment catalogue, checks availability, and prepares equipment for assigned events |
| Safety Officer | Reviews confirmed events' arrangements and approves them or sends them back to planning |
| Attendee | Browses confirmed events, registers, joins the waiting list, and withdraws |

---

## Prerequisites

- Docker Desktop
- Node.js 20.19+ and npm (for `npm run dev`; Vite 8 needs it)
- Python 3.11+ (for running the tests on the host)
- The `.env` file included in the submission (or your own Supabase project, see
  below)

---

## Local setup

> Make sure Docker Desktop is running.

### 1. Environment file

Place the `.env` file included in the submission at the **project root**, next
to `docker-compose.yml`. It points at a Supabase project that is already set
up, so no other configuration is needed. If `.env.test` is included too, put it
beside `.env`; it is only used by the integration and e2e tests.

<details>
<summary>Using your own Supabase project instead</summary>

Create the env files from the template:

```bash
cp .env.example .env         # the project you work against
cp .env.example .env.test    # a throwaway project, for tests and scans
```

Fill these in for each file. The Supabase values come from that project's
dashboard, under **Project Settings**:

```
SUPABASE_URL=<project url, host only: https://xxxx.supabase.co>
SUPABASE_SERVICE_KEY=<service_role key, backend only>
SUPABASE_ANON_KEY=<anon / publishable key>
```

Then set up each project's database:

1. Run every file in [`backend/sql/`](backend/sql/README.md) in the Supabase
   **SQL Editor**.
2. Add each schema (`users`, `events`, `venues`, `bookings`, `equipment`,
   `notifications`, `registrations`) under **Data API → Settings → Exposed
   schemas**.
3. In the test project, turn off **Authentication → Providers → Email →
   Confirm email**. The e2e sign-up journey needs this.

If a service returns `PGRST106`, `PGRST205` or `42501`, a step above was
missed. See the troubleshooting table in [`AGENTS.md`](AGENTS.md).

The accounts in `accounts.txt` exist only in the bundled project. In your own
project, sign up as an Attendee or Event Organiser, and set any other role in
the user's `app_metadata.role` under **Authentication → Users**.

</details>

### 2. Start the stack

```bash
docker compose up -d --build
```

Open the app at **http://localhost:8000**. Kong serves both the frontend and
`/api/...`.

To sign in as each role, use the logins in `accounts.txt`. It is included in
the submission but not committed to the repo. Sign-up only creates Attendee
and Event Organiser accounts; every other role is assigned by an
administrator.

For frontend work with hot reload, keep the stack running and also start:

```bash
cd frontend
npm i
npm run dev
```

Then open **http://localhost:5173**. Vite forwards `/api` to Kong, so session
cookies work just as they do in the full stack.

### 3. Stop the stack

```bash
docker compose down
```

This stops and removes the containers. Data lives in Supabase, so no events,
bookings or accounts are deleted.

---

## Running tests

```bash
pip install -r tests/requirements.txt

# Unit: no network, no Docker
pytest tests/unit
node --test tests/unit/frontend/test_*.mjs

# Integration and e2e: always start the stack fresh on .env.test first
docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration

playwright install chromium
pytest tests/e2e
```

> Integration and e2e tests create and delete real rows. Start the stack with
> `--env-file .env.test` **immediately** before running them. A stack started
> earlier with plain `docker compose up` is on your own project. It still
> passes health checks, but it writes there.

More in [`tests/README.md`](tests/README.md) and
[`tests/e2e/README.md`](tests/e2e/README.md).

---

## Services and ports

| Service | Type | Port | Gateway route |
| --- | --- | --- | --- |
| **Kong** | gateway | **8000** | serves everything under `/` and `/api` |
| [`users`](backend/services/atomic/users/README.md) | atomic | 8001 | `/api/users` |
| [`events`](backend/services/atomic/events/README.md) | atomic | 8002 | `/api/events` |
| [`venues`](backend/services/atomic/venues/README.md) | atomic | 8003 | `/api/venues` |
| [`bookings`](backend/services/atomic/bookings/README.md) | atomic | 8004 | none (composites only) |
| [`equipment`](backend/services/atomic/equipment/README.md) | atomic | 8005 | `/api/equipment` |
| [`notifications`](backend/services/atomic/notifications/README.md) | atomic | 8006 | `/api/notifications` |
| [`registrations`](backend/services/atomic/registrations/README.md) | atomic | 8007 | none (composites only) |
| [`event_requests`](backend/services/composite/event_requests/README.md) | composite | 8100 | `/api/event-requests` |
| [`venue_bookings`](backend/services/composite/venue_bookings/README.md) | composite | 8101 | `/api/venue-bookings` |
| [`equipment_requirements`](backend/services/composite/equipment_requirements/README.md) | composite | 8102 | `/api/equipment-requirements` |
| [`safety_checks`](backend/services/composite/safety_checks/README.md) | composite | 8103 | `/api/safety-checks` |
| [`event_registrations`](backend/services/composite/event_registrations/README.md) | composite | 8104 | `/api/event-registrations` |
| `frontend` | nginx | not published | reached through Kong |

Each service's README documents its endpoints, request and response bodies,
and how to run it.

---

## Project structure

```
.
├── backend/
│   ├── kong/                 kong.yml: the gateway's whole routing table
│   ├── sql/                  one schema file per atomic service, applied by hand
│   └── services/
│       ├── atomic/           one service per entity, owns its own schema
│       │   ├── users/
│       │   ├── events/
│       │   ├── venues/
│       │   ├── bookings/
│       │   ├── equipment/
│       │   ├── notifications/
│       │   └── registrations/
│       └── composite/        orchestrates atomic services, owns no storage
│           ├── event_requests/
│           ├── venue_bookings/
│           ├── equipment_requirements/
│           ├── safety_checks/
│           └── event_registrations/
├── frontend/
│   └── src/
│       ├── pages/            one file per page
│       ├── components/       shared UI
│       ├── lib/              API calls and access rules, unit-tested with node
│       └── auth/             session context (AuthProvider, useAuth)
├── tests/
│   ├── unit/                 fast, Supabase mocked
│   ├── integration/          real services in Docker against the test project
│   └── e2e/                  Playwright through Kong
├── docs/                     project brief and customer change requests
├── .github/workflows/        CI: tests, Semgrep SAST, Wapiti DAST
├── docker-compose.yml
├── .env.example
└── AGENTS.md                 conventions for every service, page and test
```

Every service has at least these files. Larger ones split their logic into
extra modules such as `authorization.py` or `availability.py`.

```
app.py            FastAPI app and routes
schemas.py        Pydantic request and response schemas
database.py       Supabase client       (atomic only)
clients.py        outbound HTTP         (composite only)
Dockerfile
requirements.txt
README.md         the service's API doc
```

---

## Technical implementation

### Backend
- **Microservice architecture**: atomic services own data, composite services
  orchestrate them
- **FastAPI + Pydantic**, with Swagger UI generated at `/docs`
- **Supabase (PostgreSQL)** queried through `supabase-py`, no ORM, one schema
  per service
- **Supabase Auth** behind the `users` service, with httpOnly session cookies
- **Kong API Gateway**, DB-less and configured from one YAML file
- **Docker Compose** with health checks, so services wait on their dependencies

### Frontend
- React 19 + Vite SPA
- React Router for client-side routing and role-based dashboards
- Tailwind CSS + `lucide-react` icons
- Served by nginx behind Kong in the stack, or by Vite's dev server

### Testing and CI
- **pytest** unit tests with a mocked Supabase client
- **pytest** integration tests against real containers and a test Supabase
  project
- **Playwright** end-to-end tests through the gateway
- **node:test** for the frontend's `lib/` helpers
- **GitHub Actions** running the suites, **Semgrep** (SAST) and **Wapiti**
  (DAST) on every push and pull request to `main` and the sprint branches

---

## Frameworks and technologies

<p align="center"><strong>UI Stack</strong></p>
<p align="center">
<a href="https://vitejs.dev/"><img src="https://upload.wikimedia.org/wikipedia/commons/f/f1/Vitejs-logo.svg" alt="Vite" width="40"/></a>&nbsp;&nbsp;
<a href="https://react.dev/"><img src="https://upload.wikimedia.org/wikipedia/commons/a/a7/React-icon.svg" alt="React" width="40"/></a>&nbsp;&nbsp;
<a href="https://reactrouter.com/"><img src="https://raw.githubusercontent.com/devicons/devicon/master/icons/reactrouter/reactrouter-original.svg" alt="React Router" width="40"/></a>&nbsp;&nbsp;
<a href="https://tailwindcss.com/"><img src="https://raw.githubusercontent.com/devicons/devicon/master/icons/tailwindcss/tailwindcss-original.svg" alt="Tailwind CSS" width="40"/></a>&nbsp;&nbsp;
<a href="https://lucide.dev/"><img src="https://lucide.dev/logo.light.svg" alt="Lucide" width="40"/></a>&nbsp;&nbsp;
<br>
<i>Vite · React · React Router · Tailwind CSS · Lucide</i>
</p>
<br>

<p align="center"><strong>Microservices Language</strong></p>
<p align="center">
<a href="https://www.python.org/"><img src="https://raw.githubusercontent.com/devicons/devicon/master/icons/python/python-original.svg" alt="Python" width="40"/></a>
<br>
<i>Python</i>
</p>
<br>

<p align="center"><strong>Microservices Framework</strong></p>
<p align="center">
<a href="https://fastapi.tiangolo.com/"><img src="https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png" alt="FastAPI" width="120"/></a>
<br>
<i>FastAPI · Pydantic · httpx</i>
</p>
<br>

<p align="center"><strong>API Gateway</strong></p>
<p align="center">
<a href="https://konghq.com/"><img src="https://www.vectorlogo.zone/logos/konghq/konghq-ar21.svg" alt="Kong" width="150"/></a>
<br>
<i>Kong API Gateway (DB-less)</i>
</p>
<br>

<p align="center"><strong>Storage and Auth</strong></p>
<p align="center">
<a href="https://supabase.com/"><img src="https://www.vectorlogo.zone/logos/supabase/supabase-icon.svg" alt="Supabase" width="40"/></a>
<br>
<i>Supabase (PostgreSQL · Auth)</i>
</p>
<br>

<p align="center"><strong>API Documentation</strong></p>
<p align="center">
<a href="https://swagger.io/"><img src="https://raw.githubusercontent.com/devicons/devicon/master/icons/swagger/swagger-original.svg" alt="Swagger" width="40"/></a>
<br>
<i>Swagger UI (via FastAPI)</i>
</p>
<br>

<p align="center"><strong>Containerisation</strong></p>
<p align="center">
<a href="https://www.docker.com/"><img src="https://upload.wikimedia.org/wikipedia/commons/4/4e/Docker_%28container_engine%29_logo.svg" alt="Docker" width="130"/></a>&nbsp;&nbsp;
<a href="https://nginx.org/"><img src="https://raw.githubusercontent.com/devicons/devicon/master/icons/nginx/nginx-original.svg" alt="nginx" width="40"/></a>&nbsp;&nbsp;
<br>
<i>Docker · Docker Compose · nginx</i>
</p>
<br>

<p align="center"><strong>Testing</strong></p>
<p align="center">
<a href="https://pytest.org/"><img src="https://raw.githubusercontent.com/devicons/devicon/master/icons/pytest/pytest-original.svg" alt="pytest" width="40"/></a>&nbsp;&nbsp;
<a href="https://playwright.dev/"><img src="https://raw.githubusercontent.com/devicons/devicon/master/icons/playwright/playwright-original.svg" alt="Playwright" width="40"/></a>&nbsp;&nbsp;
<a href="https://nodejs.org/api/test.html"><img src="https://raw.githubusercontent.com/devicons/devicon/master/icons/nodejs/nodejs-original.svg" alt="Node.js test runner" width="40"/></a>&nbsp;&nbsp;
<br>
<i>pytest · Playwright · node:test</i>
</p>
<br>

<p align="center"><strong>DevSecOps</strong></p>
<p align="center">
<a href="https://github.com/features/actions"><img src="https://github.com/user-attachments/assets/84046b86-7745-4ddd-8c36-b39b6a9ead91" alt="GitHub Actions" width="40"/></a>&nbsp;&nbsp;
<a href="https://semgrep.dev/"><img src="https://raw.githubusercontent.com/semgrep/semgrep/develop/images/semgrep-logo-light.svg" alt="Semgrep" width="120"/></a>&nbsp;&nbsp;
<br>
<i>GitHub Actions · Semgrep (SAST) · Wapiti (DAST)</i>
</p>
<br>

---

## Contributors

<div align="center">
    <table>
        <tr>
            <th>WeiXiang</th>
            <th>Yuelin</th>
            <th>Qikun</th>
            <th>Devin</th>
            <th>Jiaxu</th>
        </tr>
    </table>
</div>
