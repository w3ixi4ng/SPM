-- backend/sql/venues.sql
--
-- The venues service. Venue staff add venues; venue staff and event
-- coordinators read them. created_by is the authenticated Supabase user who
-- added the venue, derived by the service from the verified session -- a
-- client never chooses it.
--
-- Run this in the SQL Editor of BOTH the dev and the test project, then add
-- `venues` under Data API -> Settings -> Exposed schemas. Neither step is
-- optional and neither works without the other.

-- Rebuild from scratch. DESTRUCTIVE -- drops the schema and every row in it,
-- with no confirmation and no undo. Uncomment only against a project whose
-- data you are happy to lose.
-- drop schema if exists venues cascade;

-- 1. The schema, named after the atomic service.
create schema if not exists venues;

-- 2. The service-owned table.
--
--    facilities, accessibility and room_layouts are chosen from fixed sets.
--    The sets are defined in backend/services/atomic/venues/schemas.py and
--    repeated in the check constraints below, so a value outside them cannot
--    be stored even by something that bypasses the API. Change both together.
--
--    operating_hours is a JSON array of {"day", "open", "close"}, at most one
--    entry per day; a day that is absent means the venue is closed that day.
--    Its per-entry rules (known day, close after open, no repeated day) are
--    enforced by the service, not here.
create table if not exists venues.venues (
  id              uuid primary key default gen_random_uuid(),
  name            text not null,
  location        text not null,
  capacity        integer not null,
  facilities      text[] not null default '{}',
  accessibility   text[] not null default '{}',
  room_layouts    text[] not null,
  operating_hours jsonb not null,
  description     text,
  created_by      uuid not null,
  created_at      timestamptz not null default now(),

  constraint venues_name_not_blank
    check (btrim(name) <> ''),

  constraint venues_location_not_blank
    check (btrim(location) <> ''),

  constraint venues_capacity_positive
    check (capacity > 0),

  constraint venues_description_not_blank
    check (description is null or btrim(description) <> ''),

  constraint venues_facilities_allowed
    check (facilities <@ array[
      'projector', 'screen', 'sound_system', 'microphones', 'wifi', 'stage',
      'whiteboard', 'video_conferencing', 'catering_kitchen',
      'air_conditioning', 'parking'
    ]::text[]),

  constraint venues_accessibility_allowed
    check (accessibility <@ array[
      'wheelchair_access', 'step_free_entrance', 'accessible_toilets', 'lift',
      'hearing_loop', 'accessible_parking'
    ]::text[]),

  constraint venues_room_layouts_allowed
    check (
      cardinality(room_layouts) > 0
      and room_layouts <@ array[
        'theatre', 'classroom', 'boardroom', 'u_shape', 'banquet', 'cocktail'
      ]::text[]
    ),

  constraint venues_operating_hours_present
    check (
      jsonb_typeof(operating_hours) = 'array'
      and jsonb_array_length(operating_hours) > 0
    )
);

-- Two venues cannot share a name, ignoring case: "Studio B" and "studio b"
-- are the same venue to anyone booking it. The service turns a violation of
-- this index into a 409.
create unique index if not exists venues_venues_name_key
  on venues.venues (lower(name));

-- 3. Grant access to the backend role. Supabase does not pre-configure access
--    to custom schemas, so both schema usage and table privileges are needed.
grant usage on schema venues to service_role;
grant all on all tables in schema venues to service_role;
grant all on all sequences in schema venues to service_role;

-- 4. Apply the same grants automatically to tables or sequences added later.
--    These do not replace the grants above for objects that already exist.
alter default privileges for role postgres in schema venues
  grant all on tables to service_role;
alter default privileges for role postgres in schema venues
  grant all on sequences to service_role;

-- 5. Block direct browser access. The backend uses service_role, which bypasses
--    RLS; no anon or authenticated policy is intentionally defined.
alter table venues.venues enable row level security;

-- ---------------------------------------------------------------------------
-- S-36: 'cabaret' is no longer a room layout. Already have the table? Run
-- this instead. Safe to run twice.
--
--   -- A venue whose only layout was cabaret would be left with none, which
--   -- venues_room_layouts_allowed refuses. This lists them; give each another
--   -- layout before running the rest.
--   select id, name from venues.venues where room_layouts = array['cabaret'];
--
--   update venues.venues
--      set room_layouts = array_remove(room_layouts, 'cabaret')
--    where 'cabaret' = any(room_layouts);
--
--   alter table venues.venues drop constraint if exists venues_room_layouts_allowed;
--   alter table venues.venues add constraint venues_room_layouts_allowed
--     check (
--       cardinality(room_layouts) > 0
--       and room_layouts <@ array[
--         'theatre', 'classroom', 'boardroom', 'u_shape', 'banquet', 'cocktail'
--       ]::text[]
--     );
-- ---------------------------------------------------------------------------

-- BEGIN S-75 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test. Fresh
-- installations need it too. Safe to run twice.
--
-- Each venue's setup time (needed before an event) and turnaround time
-- (needed after it), in whole minutes. A booking occupies its venue from
-- start - setup to end + turnaround. Every existing venue starts at 0, so
-- nothing changes until Venue Staff set them. No maximum.
begin;
alter table venues.venues
  add column if not exists setup_minutes integer not null default 0,
  add column if not exists turnaround_minutes integer not null default 0;

alter table venues.venues drop constraint if exists venues_setup_turnaround_not_negative;
alter table venues.venues add constraint venues_setup_turnaround_not_negative
  check (setup_minutes >= 0 and turnaround_minutes >= 0);

notify pgrst, 'reload schema';
commit;
-- END S-75 DATA-PRESERVING MIGRATION

-- 6. Ask PostgREST to refresh its view after the schema and grants change.
notify pgrst, 'reload schema';
