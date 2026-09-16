# Integration tests

The real service, running in Docker, talking to a real Supabase project. Slow,
and needs setup — but these are the only tests that prove the thing actually
works.

Keep the number small. Cover what only these can prove.

## Before they will run

1. **Make a `.env.test`** — copy [`.env.example`](../../.env.example) to
   `.env.test` and point it at a **test** Supabase project:

   ```bash
   cp .env.example .env.test
   ```

   This is a separate file from `.env` on purpose. `.env` is your day-to-day
   project; `.env.test` is the one these tests are allowed to write to and
   delete from. Both are gitignored.

2. **Never point `.env.test` at a project whose data you care about.** These
   tests create and delete real records, and the service key bypasses
   row-level security, so nothing stops them. See
   [`backend/sql/README.md`](../../backend/sql/README.md) for keeping the two
   projects in step.

3. **Set that project's database up** — the schema, the table, the grants, and
   the schema exposed under Data API → Settings. The full list is in
   [`AGENTS.md`](../../AGENTS.md#creating-a-new-schema--hand-this-to-the-developer).

4. **Start the stack with the test credentials:**

   ```bash
   docker compose --env-file .env.test up -d --build --wait
   ```

   `--env-file` is what makes the containers talk to the test project instead
   of your usual one. Leave it off and you are running against `.env`.

   `--wait` holds until each service reports healthy, so the tests do not start
   talking to something that has not finished booting.

## What to test here

- **Save something, then read it back.** One round trip per service. If it
  passes, the table exists, the service can reach it, the grants are right and
  the schema is exposed — all confirmed at once.
- **Once composite services exist**, a composite calling an atomic service over
  HTTP, to prove the addresses and error handling between them are right.

## What not to test here

Anything the unit tests already cover. There is no value in checking 404
handling against a real database — you already know the route works. These
tests are for the parts a fake cannot tell you about.

## Clean up

Each test deletes the records it created. These are real rows in a real
database, and the suite has to be runnable twice in a row.

## When one fails

Suspect the database before your code. Almost every failure here is setup:

- **the running stack is on `.env`, not `.env.test`** — the most likely cause
  and the least obvious. A container keeps whichever env file created it, and
  `pytest` does not start the stack or check it. A plain `docker compose up`
  from anywhere — another terminal, an IDE panel, Docker Desktop restarting
  containers — rebuilds it from `.env`. The services stay healthy and answer
  everything; they just write to your own project. Check it before anything
  else:

  ```bash
  docker exec spm-users-1 python -c "import os;print(os.environ['SUPABASE_URL'])"
  ```

  It must match `.env.test`. Recreate the stack if it does not, and note that
  rows written to `.env` in the meantime are still there — cleanup ran against
  the other project. They are addressed `spm-test-*` and `spm-e2e-*`.
- the schema was never exposed under Data API → Settings
- the grants were never run
- the table ended up in `public`

The error messages point somewhere else entirely — the table of what they
really mean is in
[`AGENTS.md`](../../AGENTS.md#%EF%B8%8F-expose-the-schema-and-the-table-or-nothing-works).

## Running

```bash
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration
docker compose --env-file .env.test down
```
