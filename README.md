# SPM

Microservices project.

## Structure

```
backend/
  services/
    atomic/       one service per entity (user, event)
    composite/    orchestrates atomic services
frontend/
tests/
  unit/           fast, isolated, everything mocked
  integration/    crosses a real boundary (db, HTTP)
```

Each service is a FastAPI app with `app.py`, `schemas.py`, `database.py`, and a
`Dockerfile`. See [`AGENTS.md`](AGENTS.md) for the full conventions.

- [`AGENTS.md`](AGENTS.md) — service structure and conventions
- [`tests/README.md`](tests/README.md) — how tests are organised
