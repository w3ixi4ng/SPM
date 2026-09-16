-- backend/sql/events.sql
--
-- The events service. Each row is owned by the authenticated Supabase user
-- whose id is stored in organiser_id. The events service must derive that id
-- from the verified session; clients must never choose it in a request body.
--
-- Run this in the SQL Editor of BOTH the dev and the test project, then add
-- `events` under Data API -> Settings -> Exposed schemas. Neither step is
-- optional and neither works without the other.

-- Rebuild from scratch. DESTRUCTIVE -- drops the schema and every row in it,
-- with no confirmation and no undo. Uncomment only against a project whose
-- data you are happy to lose.
-- drop schema if exists events cascade;

-- 1. The schema, named after the atomic service.
create schema if not exists events;

-- 2. The service-owned table. Draft business fields are nullable so a user
--    can save incomplete work; the submitted-fields constraint below makes
--    the required fields mandatory as soon as status becomes submitted.
create table if not exists events.events (
  id                         uuid primary key default gen_random_uuid(),
  organiser_id               uuid not null,
  status                     text not null default 'draft',
  name                       text,
  purpose                    text,
  event_date                 date,
  start_time                 time without time zone,
  end_time                   time without time zone,
  expected_attendance        integer,
  venue                      text,
  equipment_requests         jsonb not null default '{}'::jsonb,
  accessibility_requirements text,
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),

  constraint events_status_allowed
    check (status in ('draft', 'submitted')),

  constraint events_name_not_blank
    check (name is null or btrim(name) <> ''),

  constraint events_purpose_not_blank
    check (purpose is null or btrim(purpose) <> ''),

  constraint events_venue_not_blank
    check (venue is null or btrim(venue) <> ''),

  constraint events_attendance_positive
    check (expected_attendance is null or expected_attendance > 0),

  constraint events_time_order
    check (start_time is null or end_time is null or end_time > start_time),

  constraint events_equipment_requests_object
    check (jsonb_typeof(equipment_requests) = 'object'),

  constraint events_submitted_fields_required
    check (
      status <> 'submitted'
      or (
        name is not null
        and purpose is not null
        and event_date is not null
        and start_time is not null
        and end_time is not null
        and expected_attendance is not null
        and venue is not null
      )
    )
);

-- Event access is scoped by the authenticated organiser, so this supports
-- owner-filtered reads and updates without scanning the full table.
create index if not exists events_events_organiser_id_idx
  on events.events (organiser_id);

-- Keep updated_at accurate for every update, regardless of which backend
-- operation changes the row.
create or replace function events.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists events_set_updated_at on events.events;
create trigger events_set_updated_at
  before update on events.events
  for each row
  execute function events.set_updated_at();

-- 3. Grant access to the backend role. Supabase does not pre-configure access
--    to custom schemas, so both schema usage and table privileges are needed.
grant usage on schema events to service_role;
grant all on all tables in schema events to service_role;
grant all on all sequences in schema events to service_role;

-- 4. Apply the same grants automatically to tables or sequences added later.
--    These do not replace the grants above for objects that already exist.
alter default privileges for role postgres in schema events
  grant all on tables to service_role;
alter default privileges for role postgres in schema events
  grant all on sequences to service_role;

-- 5. Block direct browser access. The backend uses service_role, which bypasses
--    RLS; no anon or authenticated policy is intentionally defined.
alter table events.events enable row level security;

-- 6. Ask PostgREST to refresh its view after the schema and grants change.
notify pgrst, 'reload schema';
