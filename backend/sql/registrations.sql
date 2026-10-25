-- backend/sql/registrations.sql
--
-- S-51: who holds a place at which event. The service stores opaque event
-- and attendee ids; events and users remain the sources of truth for those.
--
-- Run this in the SQL Editor of BOTH dev and test projects, then add
-- `registrations` under Data API -> Settings -> Exposed schemas.

-- Rebuild from scratch. DESTRUCTIVE -- drops the schema and every row in it,
-- with no confirmation and no undo. Uncomment only against a project whose
-- data you are happy to lose.
-- drop schema if exists registrations cascade;

create schema if not exists registrations;

create table if not exists registrations.registrations (
  id          uuid primary key default gen_random_uuid(),
  event_id    uuid not null,
  attendee_id uuid not null,
  created_at  timestamptz not null default now(),

  -- One place per account per event. Also what turns a double-click, or two
  -- tabs registering at once, into a 409 rather than two places.
  constraint registrations_one_per_attendee unique (event_id, attendee_id)
);

grant usage on schema registrations to service_role;
grant all on all tables in schema registrations to service_role;
grant all on all sequences in schema registrations to service_role;

alter default privileges for role postgres in schema registrations
  grant all on tables to service_role;
alter default privileges for role postgres in schema registrations
  grant all on sequences to service_role;

alter table registrations.registrations enable row level security;

notify pgrst, 'reload schema';
