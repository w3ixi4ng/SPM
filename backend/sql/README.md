# SQL

The schema definition for each service. One file per service, describing what
that service's database looks like:

```
users.sql
events.sql
venues.sql
bookings.sql
equipment.sql
notifications.sql
registrations.sql
```

The database is not generated from Python, so these files are the only record
of what the schema is. **They are declarative** — running a file gives you
exactly what it says, so a project can be rebuilt from this folder.

## What goes in a file

Everything that service needs, with a destructive rebuild at the top, left
commented:

```sql
-- backend/sql/users.sql

-- Rebuild from scratch. DESTRUCTIVE — drops the schema and every row in it,
-- with no confirmation and no undo. Uncomment only against a project whose
-- data you are happy to lose.
-- drop schema if exists users cascade;

create schema if not exists users;

create table if not exists users.users (
  id         bigint generated always as identity primary key,
  name       text not null,
  email      text not null unique,
  created_at timestamptz not null default now()
);

grant usage on schema users to service_role;
grant all on all tables in schema users to service_role;
grant all on all sequences in schema users to service_role;

alter default privileges for role postgres in schema users
  grant all on tables to service_role;

alter table users.users enable row level security;

notify pgrst, 'reload schema';
```

Everything is `if not exists`, so running the file without the drop is
harmless and can be repeated.

## Changing the schema

Edit the file, uncomment the `drop`, run it, re-comment the `drop`. The
database is rebuilt to match, so the file can never drift from reality.

Do this in **every project** — dev and test — at the same time:

| Project | Used by |
| --- | --- |
| dev | your local `.env` |
| test | GitHub Actions secrets |

Changing one and not the other is how the databases drift apart, and the
symptom is a CI failure on a PR that has nothing to do with the change:
`column ... does not exist` in a test you never touched.

Commit the change in the same PR as the code that needs it, so a reviewer sees
the column and the code reading it together.

## Always write `schema.table`

Never a bare table name. The SQL Editor runs with `public` on the search path,
so an unqualified statement silently creates the table in `public` — the one
place [`AGENTS.md`](../../AGENTS.md) forbids, because a table there has no
owning service. It looks like it worked, and the service still cannot find it.

```sql
create table if not exists users.users (...);   -- right
create table if not exists users (...);         -- wrong: creates public.users
```

## Once you have data worth keeping

Drop-and-recreate works while the rows are throwaway. When losing them stops
being acceptable, leave the `drop` commented and make that one change with an
`alter` instead:

```sql
alter table users.users add column phone text;
```

Then update the file so it still describes the finished shape — it stays the
source of truth either way. This is the exception, not the routine.

## New service

The full block — schema, table, grants, RLS — is in
[`AGENTS.md`](../../AGENTS.md#creating-a-new-schema--hand-this-to-the-developer).
Save it here as `<service>.sql` before running it.
