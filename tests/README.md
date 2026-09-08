# Tests

Two kinds of test, in two folders.

| Folder | What it does | Needs |
| --- | --- | --- |
| `unit/` | Runs one service on its own, with a **fake** Supabase that returns whatever the test tells it. | Nothing |
| `integration/` | Runs the real service in Docker against a **real** (test) Supabase. | Docker, a filled-in `.env.test`, a test Supabase project |

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

## End-to-end tests — later

Not set up, on purpose. An end-to-end test drives a real browser through the
whole path — frontend, composite service, atomic service, database — the way a
person would: log in, create something, check it appears.

That needs a working frontend, working services, and real user journeys to
test. None of those exist yet, so there is nothing for it to click on.

Add it once the stack works end to end, as `tests/e2e/` with a browser tool
such as Cypress or Playwright, and name specs after journeys (`userAuth`,
`createTask`) rather than after services.

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

# needs the stack running first, against the test project
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration
```

Details: [`unit/README.md`](unit/README.md) ·
[`integration/README.md`](integration/README.md)
