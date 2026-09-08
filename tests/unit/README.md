# Unit tests

One service, on its own, with a fake Supabase in place of the real one. No
network, no database, no Docker. Each test should finish in milliseconds.

Write plenty of these — they cost nothing to run.

## How the fake gets in

FastAPI routes ask for the database through `Depends(get_db)`. In a test you
replace that with a fake, and the route never knows:

```python
app.dependency_overrides[get_db] = lambda: fake
```

`MagicMock` from Python's standard library works well as the fake, because a
chain like `.schema(...).table(...).select(...).execute()` keeps working
without you writing anything:

```python
from unittest.mock import MagicMock

fake = MagicMock()
fake.schema().table().select().eq().execute().data = [
    {"id": 1, "name": "Wei", "email": "wei@x.com"}
]
```

Remember Supabase always hands back a **list**, even for one record. An empty
list is what a missing record looks like — that is the case that should produce
a 404.

Always undo the override when the test finishes:

```python
app.dependency_overrides.clear()
```

It is set on the app itself, so leaving it in place leaks into every later test
in the run.

## What to test here

- the route is at the URL you think it is
- the right status code — 201 when created, 404 when missing, 422 for a bad
  request body
- the response has the right fields
- any decision the code makes, both ways

## What these tests cannot catch

The fake agrees with everything, so none of this shows up:

- asking for a column that does not exist
- reading the wrong Postgres schema, or a table that ended up in `public`
- missing grants, or a schema that was never exposed
- row-level security quietly filtering everything out
- a composite service calling `localhost` instead of the Docker service name

All of those are real and common. They are what
[`../integration/`](../integration/README.md) is for.

## Running

```bash
pytest tests/unit
```
