-- backend/sql/bookings.sql
--
-- The bookings service. One row per venue booking request an Event
-- Coordinator submits (S-36). The venue_bookings composite checks each
-- request against the event and the venue before it is written here, so
-- every row is a request Venue Staff can assess.
--
-- event_id, venue_id and coordinator_id are opaque ids owned by other
-- services -- no foreign keys, since those would cross schemas. The event's
-- name, purpose, attendance and requirements, the venue's name and the
-- coordinator's name and email are a snapshot taken at submission: Venue
-- Staff assess what was asked, even if the event changes afterwards.
--
-- Run this in the SQL Editor of BOTH the dev and the test project, then add
-- `bookings` under Data API -> Settings -> Exposed schemas. Neither step is
-- optional and neither works without the other.

-- Rebuild from scratch. DESTRUCTIVE -- drops the schema and every row in it,
-- with no confirmation and no undo. Uncomment only against a project whose
-- data you are happy to lose.
-- drop schema if exists bookings cascade;

-- 1. The schema, named after the atomic service.
create schema if not exists bookings;

-- 2. The service-owned table.
--
--    room_layout, required_facilities and required_accessibility use the
--    venue catalogue's fixed sets (backend/sql/venues.sql), so a request can
--    be compared with a venue. The sets are repeated in
--    backend/services/atomic/bookings/schemas.py. Change all three together.
create table if not exists bookings.bookings (
  id                         uuid primary key default gen_random_uuid(),
  event_id                   uuid not null,
  venue_id                   uuid not null,
  coordinator_id             uuid not null,
  coordinator_name           text not null,
  coordinator_email          text not null,

  -- S-37: confirmation is the final state of this original request row.
  status                     text not null default 'pending',

  booking_date               date not null,
  start_time                 time without time zone not null,
  end_time                   time without time zone not null,

  event_name                 text not null,
  event_purpose              text not null,
  expected_attendance        integer not null,
  special_requirements       text,
  required_accessibility     text[] not null default '{}',
  required_facilities        text[] not null default '{}',
  room_layout                text,
  notes                      text,
  venue_name                 text not null,

  submitted_at               timestamptz not null default now(),

  constraint bookings_status_allowed
    check (status in ('pending', 'confirmed', 'rejected')),

  -- One date, so the end is simply after the start. A venue's opening hours
  -- never cross midnight, so neither can a booking.
  constraint bookings_time_order
    check (end_time > start_time),

  constraint bookings_attendance_positive
    check (expected_attendance > 0),

  constraint bookings_required_text_not_blank
    check (
      btrim(coordinator_name) <> '' and btrim(coordinator_email) <> ''
      and btrim(event_name) <> '' and btrim(event_purpose) <> ''
      and btrim(venue_name) <> ''
    ),

  constraint bookings_optional_text_not_blank
    check (
      (special_requirements is null or btrim(special_requirements) <> '')
      and (notes is null or btrim(notes) <> '')
    ),

  constraint bookings_required_facilities_allowed
    check (required_facilities <@ array[
      'projector', 'screen', 'sound_system', 'microphones', 'wifi', 'stage',
      'whiteboard', 'video_conferencing', 'catering_kitchen',
      'air_conditioning', 'parking'
    ]::text[]),

  constraint bookings_required_accessibility_allowed
    check (required_accessibility <@ array[
      'wheelchair_access', 'step_free_entrance', 'accessible_toilets', 'lift',
      'hearing_loop', 'accessible_parking'
    ]::text[]),

  constraint bookings_room_layout_allowed
    check (room_layout is null or room_layout in (
      'theatre', 'classroom', 'boardroom', 'u_shape', 'banquet', 'cocktail'
    ))
);

-- Venue Staff's pending list: filter by status, oldest first.
create index if not exists bookings_bookings_status_submitted_at_idx
  on bookings.bookings (status, submitted_at);

-- 3. Grant access to the backend role. Supabase does not pre-configure access
--    to custom schemas, so both schema usage and table privileges are needed.
grant usage on schema bookings to service_role;
grant all on all tables in schema bookings to service_role;
grant all on all sequences in schema bookings to service_role;

-- 4. Apply the same grants automatically to tables or sequences added later.
--    These do not replace the grants above for objects that already exist.
alter default privileges for role postgres in schema bookings
  grant all on tables to service_role;
alter default privileges for role postgres in schema bookings
  grant all on sequences to service_role;

-- 5. Block direct browser access. The backend uses service_role, which bypasses
--    RLS; no anon or authenticated policy is intentionally defined.
alter table bookings.bookings enable row level security;

-- ---------------------------------------------------------------------------
-- S-36: 'cabaret' is no longer a room layout. Already have the table? Run
-- this instead. Safe to run twice. A request that asked for cabaret is
-- cleared to no layout preference.
--
--   update bookings.bookings set room_layout = null where room_layout = 'cabaret';
--
--   alter table bookings.bookings drop constraint if exists bookings_room_layout_allowed;
--   alter table bookings.bookings add constraint bookings_room_layout_allowed
--     check (room_layout is null or room_layout in (
--       'theatre', 'classroom', 'boardroom', 'u_shape', 'banquet', 'cocktail'
--     ));
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- S-36: the request carries the event's other requirements instead of its
-- free-text accessibility notes, which the event no longer has. Already have
-- the table? Run this instead. Safe to run twice.
--
--   do $$
--   begin
--     if exists (select 1 from information_schema.columns
--                where table_schema = 'bookings' and table_name = 'bookings'
--                  and column_name = 'accessibility_requirements') then
--       alter table bookings.bookings
--         rename column accessibility_requirements to special_requirements;
--     end if;
--   end $$;
--
--   alter table bookings.bookings drop constraint if exists bookings_optional_text_not_blank;
--   alter table bookings.bookings add constraint bookings_optional_text_not_blank
--     check (
--       (special_requirements is null or btrim(special_requirements) <> '')
--       and (notes is null or btrim(notes) <> '')
--     );
-- ---------------------------------------------------------------------------

-- 6. Ask PostgREST to refresh its view after the schema and grants change.
-- BEGIN S-37 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test.
-- No rows or request snapshot fields are deleted or rewritten.
begin;
alter table bookings.bookings
  add column if not exists decision_reason text,
  add column if not exists decision_alternative text,
  add column if not exists decided_by uuid,
  add column if not exists decided_at timestamptz;

alter table bookings.bookings drop constraint if exists bookings_status_allowed;
alter table bookings.bookings add constraint bookings_status_allowed
  check (status in ('pending', 'confirmed', 'rejected'));

alter table bookings.bookings drop constraint if exists bookings_decision_valid;
alter table bookings.bookings add constraint bookings_decision_valid check (
  (decision_reason is null or decision_reason ~ '[^[:space:]]')
  and (decision_alternative is null or decision_alternative ~ '[^[:space:]]')
  and (
    (status = 'pending' and decided_by is null and decided_at is null
      and decision_reason is null and decision_alternative is null)
    or (status in ('confirmed', 'rejected') and decided_by is not null
      and decided_at is not null
      and (status = 'confirmed' or decision_reason is not null
           or decision_alternative is not null))
  )
);
notify pgrst, 'reload schema';
commit;
-- END S-37 DATA-PRESERVING MIGRATION
-- BEGIN S-38 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test.
-- It fails safely if overlapping confirmed rows already exist; resolve those
-- rows with the team before retrying. Pending and rejected rows never block.
begin;
create extension if not exists btree_gist with schema extensions;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'bookings_no_confirmed_overlap'
      and conrelid = 'bookings.bookings'::regclass
  ) then
    alter table bookings.bookings
      add constraint bookings_no_confirmed_overlap
      exclude using gist (
        venue_id with =,
        (tsrange(booking_date + start_time, booking_date + end_time, '[)')) with &&
      ) where (status = 'confirmed');
  end if;
end $$;

notify pgrst, 'reload schema';
commit;
-- END S-38 DATA-PRESERVING MIGRATION
notify pgrst, 'reload schema';
