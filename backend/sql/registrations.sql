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

-- BEGIN S-50 CAPACITY AND WAITING LIST
-- Existing installations: run through END S-50 in BOTH dev and test. Safe to
-- run repeatedly and data-preserving.

-- Attendees waiting for a place at a full event, in the order they joined.
create table if not exists registrations.waiting_list (
  id          uuid primary key default gen_random_uuid(),
  event_id    uuid not null,
  attendee_id uuid not null,
  created_at  timestamptz not null default now(),

  constraint waiting_list_one_per_attendee unique (event_id, attendee_id)
);

create index if not exists waiting_list_event_idx
  on registrations.waiting_list (event_id, created_at);

-- Takes a place only while the event has one. The capacity comes from the
-- caller (the event's expected attendance, owned by the events service); the
-- count and the insert happen here, under a per-event lock, so two people
-- registering for the last place at the same moment cannot both get it.
--   SP050 -- the event is full
--   23505 -- this Attendee already holds a place
create or replace function registrations.register(
  p_event_id    uuid,
  p_attendee_id uuid,
  p_capacity    integer
)
returns setof registrations.registrations
language plpgsql
set search_path = ''
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 50));

  if exists (
    select 1 from registrations.registrations
    where event_id = p_event_id and attendee_id = p_attendee_id
  ) then
    raise exception 'already registered' using errcode = '23505';
  end if;

  if (
    select count(*) from registrations.registrations where event_id = p_event_id
  ) >= p_capacity then
    raise exception 'event full' using errcode = 'SP050';
  end if;

  return query
    insert into registrations.registrations (event_id, attendee_id)
    values (p_event_id, p_attendee_id)
    returning *;
end;
$$;

-- The table was created after the grants at the top of this file ran on an
-- existing project, so grant it here too. Functions are executable by
-- PUBLIC by default; only the backend should call this one.
grant all on registrations.waiting_list to service_role;
revoke all on function registrations.register(uuid, uuid, integer) from public, anon, authenticated;
grant execute on function registrations.register(uuid, uuid, integer) to service_role;

alter table registrations.waiting_list enable row level security;

notify pgrst, 'reload schema';
-- END S-50 CAPACITY AND WAITING LIST
