-- backend/sql/users.sql
--
-- The users service. Credentials live in Supabase Auth (`auth.users`, managed
-- by Supabase); this schema holds the profile that belongs to each account.
--
-- Run this in the SQL Editor of BOTH the dev and the test project, then add
-- `users` under Data API -> Settings -> Exposed schemas. Neither step is
-- optional and neither works without the other.

-- Rebuild from scratch. DESTRUCTIVE -- drops the schema and every row in it,
-- with no confirmation and no undo. Uncomment only against a project whose
-- data you are happy to lose.
-- drop schema if exists users cascade;

-- 1. The schema, named after the service. Plural, because `user` is a
--    reserved word in Postgres and `create schema user` is a syntax error.
create schema if not exists users;

-- 2. The profile table, inside that schema -- never in public.
--
--    `id` is the Supabase Auth user's id rather than a generated one, so the
--    account and its profile are the same row from every direction, and there
--    is no second identifier to keep in step. The foreign key means deleting
--    the account takes the profile with it; drop the `references` clause if
--    you would rather the two were independent.
create table if not exists users.users (
  id         uuid primary key references auth.users (id) on delete cascade,
  name       text not null,
  email      text not null unique,
  created_at timestamptz not null default now()
);

-- Sign-up and login both look a profile up by address.
create index if not exists users_users_email_idx on users.users (email);

-- 3. Grant access to the backend role.
--    Supabase pre-configures privileges on `public` only. A schema you create
--    yourself has NONE, so service_role cannot read it until this runs -- even
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
--    The service holds the service_role key, which bypasses RLS, so it keeps
--    working. No policy is defined on purpose: with none, every other role
--    sees nothing, and the browser is meant to go through the service.
alter table users.users enable row level security;

-- 6. Nudge PostgREST if the table still is not visible after all of the above.
notify pgrst, 'reload schema';
