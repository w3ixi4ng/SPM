# SPM

Microservices project.

## Structure

```
backend/
  services/
    atomic/       one service per entity (users, events, venues)
    composite/    orchestrates atomic services
frontend/
tests/
  unit/           fast, isolated, everything mocked
  integration/    crosses a real boundary (db, HTTP)
```

Each service is a FastAPI app with `app.py`, `schemas.py`, `database.py`, and a
`Dockerfile`. See [`AGENTS.md`](AGENTS.md) for the full conventions.

## Running

```bash
cp .env.example .env      # fill in the Supabase values first
docker compose up --build
```

| Service | Port |
| --- | --- |
| users | 8001 |
| events | 8002 |
| venues | 8003 |

- [`AGENTS.md`](AGENTS.md) — service structure and conventions
- [`tests/README.md`](tests/README.md) — how tests are organised
