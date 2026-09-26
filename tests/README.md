# Tests

Two kinds of test, in two folders.

| Folder | What it does | Needs |
| --- | --- | --- |
| `unit/` | Runs one service on its own, with a **fake** Supabase that returns whatever the test tells it. | Nothing |
| `integration/` | Runs the real service in Docker against a **real** (test) Supabase. | Docker, a filled-in `.env.test`, a test Supabase project |
| `e2e/` | Drives a **real browser** over the whole stack through Kong. | All of the above, plus Chromium and the frontend container |

## The difference, plainly

A unit test checks *your code*. The fake database says yes to everything, so
the test only proves your code behaves correctly when it gets a given answer.

An integration test checks *the whole thing actually works* — that the table
exists, that the service can reach it, and that a saved record comes back.

This matters here more than usual. Every Supabase trap in
[`AGENTS.md`](../AGENTS.md) — a schema that was never exposed, missing grants,
a table that landed in `public` — is **invisible to unit tests**. The fake
pretends it all worked.

> A green unit-test run does not mean the service works. It means the code is
> right *if* the database is set up correctly.

## How many of each

**Lots of unit tests, only a few integration tests.**

Unit tests cost nothing to run, so use them for every case: good input, bad
input, a record that is not there. Integration tests are slow and need Docker,
so keep them to the things only they can prove — usually one save-then-read per
service. If that passes, the schema, the permissions, and the connection are
all confirmed at once.

## End-to-end tests

`tests/e2e/` drives a real browser (Playwright, through pytest) over the built
frontend, Kong, both services and a real test Supabase project — the way a
person would: sign up, log in, add a venue, check a role is kept out of a
route it should not reach.

Four journeys, and that is meant to stay small. They are the slowest tests
here and the most fragile, so one belongs there only if nothing cheaper can
prove it: the gateway's routing, nginx's SPA fallback, an httpOnly cookie
surviving a page load, and whether the frontend's permission mirror still
matches the backend's policy.

Needs the whole stack up, Chromium installed, and email confirmation off in the
test project. See [`e2e/README.md`](e2e/README.md).

## Naming

Test files are `test_<subject>.py`, in a folder that mirrors the service:

```
tests/unit/atomic/users/test_app.py
tests/integration/atomic/users/test_app.py
```

## Running

```bash
# fast ones, no setup
pytest tests/unit

# the frontend's unit tests are Node's own runner, not pytest -- they import
# frontend/src/lib/ directly, so there is nothing to install
node --test tests/unit/frontend/test_*.mjs

# needs the stack running first, against the test project
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration

# a real browser over the same stack -- needs `playwright install chromium`
pytest tests/e2e

docker compose --env-file .env.test down -v
```

All three run in CI on every push and pull request, as the three jobs of
`.github/workflows/tests.yml`. The integration job needs the repo secrets and
is skipped on pull requests from forks — see
[`AGENTS.md`](../AGENTS.md#ci).

Details: [`unit/README.md`](unit/README.md) ·
[`integration/README.md`](integration/README.md)
