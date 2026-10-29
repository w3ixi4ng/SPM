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

  -- S-33: pending requests may be tentatively held before a final decision.
  status                     text not null default 'pending',
  held_by                    uuid,
  held_at                    timestamptz,
  hold_expires_at            timestamptz,
  hold_released_at           timestamptz,
  hold_release_reason        text,

  -- S-25: preparation is tracked per confirmed venue booking.
  venue_preparation_status      text not null default 'not_started',
  venue_preparation_updated_by  uuid,
  venue_preparation_updated_at  timestamptz,
  venue_preparation_version     integer not null default 0,

  -- S-91: one confirmed booking may be the attendee-facing venue.
  is_primary                 boolean not null default false,
  primary_selected_by        uuid,
  primary_selected_at        timestamptz,

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
    check (status in ('pending', 'held', 'confirmed', 'rejected')),

  constraint bookings_hold_valid check (
    (status = 'held' and held_by is not null and held_at is not null
      and hold_expires_at is not null
      and hold_released_at is null and hold_release_reason is null)
    or (status <> 'held'
      and ((hold_released_at is null and hold_release_reason is null)
        or (hold_released_at is not null and hold_release_reason is not null)))
  ),

  constraint bookings_hold_release_reason_allowed check (
    hold_release_reason is null or hold_release_reason in (
      'staff_released', 'event_rejected', 'event_cancelled', 'booking_replaced',
      'expired'
    )
  ),

  constraint bookings_venue_preparation_status_allowed
    check (venue_preparation_status in ('not_started', 'in_progress', 'ready')),
  constraint bookings_venue_preparation_audit_valid check (
    (venue_preparation_updated_by is null and venue_preparation_updated_at is null
      and venue_preparation_version = 0)
    or (venue_preparation_updated_by is not null and venue_preparation_updated_at is not null
      and venue_preparation_version > 0)
  ),

  constraint bookings_primary_valid check (
    (is_primary and status = 'confirmed'
      and primary_selected_by is not null and primary_selected_at is not null)
    or (not is_primary
      and primary_selected_by is null and primary_selected_at is null)
  ),

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

create unique index if not exists bookings_one_primary_per_event_idx
  on bookings.bookings (event_id) where is_primary;

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
-- BEGIN S-30 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test.
--
-- 1. A pending request is now a tentative hold, and holds are exclusive: no
--    two pending-or-confirmed rows may overlap for one venue. This widens
--    S-38's confirmed-only constraint. It fails safely, changing nothing, if
--    overlapping pending rows already exist. Find them with:
--
--      select a.id, b.id, a.venue_name, a.booking_date,
--             a.start_time, a.end_time, b.start_time, b.end_time
--      from bookings.bookings a
--      join bookings.bookings b
--        on a.venue_id = b.venue_id and a.booking_date = b.booking_date
--       and a.id < b.id
--       and a.start_time < b.end_time and b.start_time < a.end_time
--      where a.status in ('pending', 'confirmed')
--        and b.status in ('pending', 'confirmed');
--
--    Resolve them with the team (reject one of each pair), then rerun.
--
-- 2. bookings.blocks: whole days Venue Staff mark a venue unavailable.
--    venue_id is an opaque id owned by the venues service -- no foreign key,
--    since that would cross schemas. venue_name is a snapshot for messages.
--    A block may cover existing holds and bookings; nothing is changed or
--    reassigned automatically, so there is no constraint between the tables.
begin;
create extension if not exists btree_gist with schema extensions;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'bookings_no_live_overlap'
      and conrelid = 'bookings.bookings'::regclass
  ) then
    alter table bookings.bookings
      add constraint bookings_no_live_overlap
      exclude using gist (
        venue_id with =,
        (tsrange(booking_date + start_time, booking_date + end_time, '[)')) with &&
      ) where (status in ('pending', 'confirmed'));
  end if;
end $$;

-- Covered by the constraint above.
alter table bookings.bookings drop constraint if exists bookings_no_confirmed_overlap;

create table if not exists bookings.blocks (
  id          uuid primary key default gen_random_uuid(),
  venue_id    uuid not null,
  venue_name  text not null,
  start_date  date not null,
  end_date    date not null,
  reason      text not null,
  note        text,
  created_by  uuid not null,
  created_at  timestamptz not null default now(),

  -- Inclusive at both ends: a one-day block has start_date = end_date.
  constraint blocks_date_order check (end_date >= start_date),

  -- Repeated in backend/services/atomic/bookings/schemas.py. Change both.
  constraint blocks_reason_allowed check (reason in (
    'maintenance', 'renovation', 'safety', 'internal_activity', 'other'
  )),

  constraint blocks_text_not_blank check (
    btrim(venue_name) <> ''
    and (note is null or btrim(note) <> '')
    and (reason <> 'other' or note is not null)
  )
);

-- The calendar's lookup: one venue, overlapping a date range.
create index if not exists bookings_blocks_venue_dates_idx
  on bookings.blocks (venue_id, start_date, end_date);

grant all on table bookings.blocks to service_role;
alter table bookings.blocks enable row level security;

notify pgrst, 'reload schema';
commit;
-- END S-30 DATA-PRESERVING MIGRATION
notify pgrst, 'reload schema';

-- BEGIN S-33 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test.
-- Existing pending rows were displayed as S-30 holds, so migrate them to the
-- explicit held state rather than silently making their slots available.
begin;

alter table bookings.bookings
  add column if not exists held_by uuid,
  add column if not exists held_at timestamptz,
  add column if not exists hold_released_at timestamptz,
  add column if not exists hold_release_reason text;

alter table bookings.bookings drop constraint if exists bookings_no_live_overlap;
alter table bookings.bookings drop constraint if exists bookings_status_allowed;
alter table bookings.bookings drop constraint if exists bookings_decision_valid;
alter table bookings.bookings drop constraint if exists bookings_hold_valid;
alter table bookings.bookings drop constraint if exists bookings_hold_release_reason_allowed;

-- The coordinator who created an old pending request is the best available
-- audit identity for the automatic S-30 hold being migrated.
update bookings.bookings
set status = 'held', held_by = coordinator_id, held_at = submitted_at
where status = 'pending';

alter table bookings.bookings add constraint bookings_status_allowed
  check (status in ('pending', 'held', 'confirmed', 'rejected'));

alter table bookings.bookings add constraint bookings_decision_valid check (
  (decision_reason is null or decision_reason ~ '[^[:space:]]')
  and (decision_alternative is null or decision_alternative ~ '[^[:space:]]')
  and (
    (status in ('pending', 'held') and decided_by is null and decided_at is null
      and decision_reason is null and decision_alternative is null)
    or (status in ('confirmed', 'rejected') and decided_by is not null
      and decided_at is not null
      and (status = 'confirmed' or decision_reason is not null
           or decision_alternative is not null))
  )
);

alter table bookings.bookings add constraint bookings_hold_release_reason_allowed
  check (hold_release_reason is null or hold_release_reason in (
    'staff_released', 'event_rejected', 'event_cancelled', 'booking_replaced'
  ));

alter table bookings.bookings add constraint bookings_hold_valid check (
  (status = 'held' and held_by is not null and held_at is not null
    and hold_released_at is null and hold_release_reason is null)
  or (status <> 'held'
    and ((hold_released_at is null and hold_release_reason is null)
      or (hold_released_at is not null and hold_release_reason is not null)))
);

alter table bookings.bookings
  add constraint bookings_no_live_overlap
  exclude using gist (
    venue_id with =,
    (tsrange(booking_date + start_time, booking_date + end_time, '[)')) with &&
  ) where (status in ('held', 'confirmed'));

notify pgrst, 'reload schema';
commit;
-- END S-33 DATA-PRESERVING MIGRATION

-- BEGIN S-77 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test. Fresh
-- installations need it too. Safe to run twice.
--
-- S-77 turns S-30's whole-day blocks into timed unavailable periods: from
-- start_date + start_time up to, but not including, end_date + end_time. A
-- booking may end exactly when a period starts, or start exactly when it ends.
--
-- 1. Existing S-30 blocks were whole days, inclusive at both ends. The first
--    time the time columns are added, each moves to the same span as a
--    period: 00:00 on its first day to 00:00 the day after its last. This runs
--    once only -- on a second run the columns already exist and nothing moves.
-- 2. The reasons become the story's: equipment_failure is added, and
--    internal_activity is dropped. A block with that reason becomes other,
--    and keeps its note. A block with internal_activity and no note gets the
--    note "Internal activity", because other needs a description.
begin;

do $$
begin
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'bookings' and table_name = 'blocks'
      and column_name = 'start_time'
  ) then
    alter table bookings.blocks
      add column start_time time without time zone not null default '00:00',
      add column end_time   time without time zone not null default '00:00';
    alter table bookings.blocks drop constraint if exists blocks_date_order;
    update bookings.blocks set end_date = end_date + 1;
  end if;
end $$;

alter table bookings.blocks drop constraint if exists blocks_date_order;
alter table bookings.blocks drop constraint if exists blocks_period_order;
alter table bookings.blocks add constraint blocks_period_order
  check (end_date + end_time > start_date + start_time);

alter table bookings.blocks drop constraint if exists blocks_reason_allowed;
update bookings.blocks
   set reason = 'other', note = coalesce(note, 'Internal activity')
 where reason = 'internal_activity';
-- Repeated in backend/services/atomic/bookings/schemas.py. Change both.
alter table bookings.blocks add constraint blocks_reason_allowed check (reason in (
  'maintenance', 'equipment_failure', 'renovation', 'safety', 'other'
));

notify pgrst, 'reload schema';
commit;
-- END S-77 DATA-PRESERVING MIGRATION

-- BEGIN S-81 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test.
-- Existing indefinite holds receive a seven-day window from when they were
-- placed. A window already in the past is released on the next bookings
-- operation and remains recorded with release reason `expired`.
begin;

alter table bookings.bookings
  add column if not exists hold_expires_at timestamptz;

update bookings.bookings
set hold_expires_at = held_at + interval '7 days'
where status = 'held' and hold_expires_at is null;

alter table bookings.bookings drop constraint if exists bookings_hold_valid;
alter table bookings.bookings drop constraint if exists bookings_hold_release_reason_allowed;

alter table bookings.bookings add constraint bookings_hold_release_reason_allowed
  check (hold_release_reason is null or hold_release_reason in (
    'staff_released', 'event_rejected', 'event_cancelled', 'booking_replaced',
    'expired'
  ));

alter table bookings.bookings add constraint bookings_hold_valid check (
  (status = 'held' and held_by is not null and held_at is not null
    and hold_expires_at is not null
    and hold_released_at is null and hold_release_reason is null)
  or (status <> 'held'
    and ((hold_released_at is null and hold_release_reason is null)
      or (hold_released_at is not null and hold_release_reason is not null)))
);

-- This function is also called by the atomic service before every relevant
-- read or write, so expiry changes are visible without a background worker.
create or replace function bookings.expire_holds()
returns setof bookings.bookings
language sql
security definer
set search_path = bookings, pg_temp
as $$
  update bookings.bookings
     set status = 'pending', hold_released_at = now(),
         hold_release_reason = 'expired'
   where status = 'held' and hold_expires_at <= now()
  returning *;
$$;

-- Older draft versions of S-81 installed a write trigger here. Remove it:
-- invoking the same UPDATE from a BEFORE UPDATE trigger can attempt to change
-- one tuple twice in a statement. The atomic service calls expire_holds()
-- before every relevant read and write instead, including before the overlap
-- exclusion constraint is reached.
drop trigger if exists bookings_release_expired_before_write on bookings.bookings;
drop function if exists bookings.release_expired_holds();

notify pgrst, 'reload schema';
commit;
-- END S-81 DATA-PRESERVING MIGRATION

-- BEGIN S-78 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test. Fresh
-- installations need it too. Safe to run twice.
--
-- S-78 lets a Coordinator replace a booking an unavailable period affects.
--
-- 1. A replacement request points at the booking it replaces
--    (replaces_booking_id). When Venue Staff confirm it, the trigger below
--    marks the original `replaced` in the same transaction, pointing back
--    (replaced_by_booking_id) -- so a replacement is never confirmed while
--    its original still reserves the old venue. `replaced` is not live, so
--    the original stops reserving its slot (bookings_no_live_overlap only
--    covers held and confirmed).
-- 2. A Coordinator can instead resolve the flag with a note. The booking is
--    not changed; the three alternative_resolution columns record who, when
--    and what was arranged. The venue_bookings composite ignores every
--    period created up to alternative_resolved_at.
begin;

alter table bookings.bookings
  add column if not exists replaces_booking_id uuid
    references bookings.bookings (id) on delete set null,
  add column if not exists replaced_by_booking_id uuid
    references bookings.bookings (id) on delete set null,
  add column if not exists replaced_at timestamptz,
  add column if not exists alternative_resolved_at timestamptz,
  add column if not exists alternative_resolved_by uuid,
  add column if not exists alternative_resolution_note text;

-- An event's replacement requests for one booking, oldest first.
create index if not exists bookings_bookings_replaces_booking_id_idx
  on bookings.bookings (replaces_booking_id)
  where replaces_booking_id is not null;

-- Repeated in backend/services/atomic/bookings/schemas.py. Change both.
alter table bookings.bookings drop constraint if exists bookings_status_allowed;
alter table bookings.bookings add constraint bookings_status_allowed
  check (status in ('pending', 'held', 'confirmed', 'rejected', 'replaced'));

-- As S-33's, plus `replaced`: the original may have been pending, held
-- (never decided) or confirmed (decided) when its replacement was confirmed.
alter table bookings.bookings drop constraint if exists bookings_decision_valid;
alter table bookings.bookings add constraint bookings_decision_valid check (
  (decision_reason is null or decision_reason ~ '[^[:space:]]')
  and (decision_alternative is null or decision_alternative ~ '[^[:space:]]')
  and (
    status = 'replaced'
    or (status in ('pending', 'held') and decided_by is null and decided_at is null
      and decision_reason is null and decision_alternative is null)
    or (status in ('confirmed', 'rejected') and decided_by is not null
      and decided_at is not null
      and (status = 'confirmed' or decision_reason is not null
           or decision_alternative is not null))
  )
);

-- replaced_by_booking_id is not required: deleting the replacement sets it
-- null (on delete set null), and the original stays replaced.
alter table bookings.bookings drop constraint if exists bookings_replaced_valid;
alter table bookings.bookings add constraint bookings_replaced_valid check (
  (status = 'replaced') = (replaced_at is not null)
  and (replaces_booking_id is null or replaces_booking_id <> id)
);

alter table bookings.bookings drop constraint if exists bookings_alternative_resolution_valid;
alter table bookings.bookings add constraint bookings_alternative_resolution_valid check (
  (alternative_resolved_at is null and alternative_resolved_by is null
    and alternative_resolution_note is null)
  or (alternative_resolved_at is not null and alternative_resolved_by is not null
    and btrim(alternative_resolution_note) <> ''
    and char_length(alternative_resolution_note) <= 500)
);

create or replace function bookings.replace_original_on_confirm()
returns trigger
language plpgsql
as $$
begin
  -- An original already replaced by another booking is left as it is. S-17:
  -- a rejected original is replaced too, so the rejection stops blocking the
  -- event's submission for the Operational Safety Check.
  update bookings.bookings
     set status = 'replaced',
         replaced_by_booking_id = new.id,
         replaced_at = now()
   where id = new.replaces_booking_id
     and status in ('pending', 'held', 'confirmed', 'rejected');
  return new;
end;
$$;

drop trigger if exists bookings_replace_original_on_confirm on bookings.bookings;
create trigger bookings_replace_original_on_confirm
  after update of status on bookings.bookings
  for each row
  when (new.status = 'confirmed' and old.status is distinct from 'confirmed'
        and new.replaces_booking_id is not null)
  execute function bookings.replace_original_on_confirm();

notify pgrst, 'reload schema';
commit;
-- END S-78 DATA-PRESERVING MIGRATION

-- BEGIN S-25 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test.
-- Safe to repeat; existing bookings begin Not Started with no audit actor.
begin;

alter table bookings.bookings
  add column if not exists venue_preparation_status text not null default 'not_started',
  add column if not exists venue_preparation_updated_by uuid,
  add column if not exists venue_preparation_updated_at timestamptz,
  add column if not exists venue_preparation_version integer not null default 0;

alter table bookings.bookings
  drop constraint if exists bookings_venue_preparation_status_allowed;
alter table bookings.bookings add constraint bookings_venue_preparation_status_allowed
  check (venue_preparation_status in ('not_started', 'in_progress', 'ready'));

alter table bookings.bookings
  drop constraint if exists bookings_venue_preparation_audit_valid;
alter table bookings.bookings add constraint bookings_venue_preparation_audit_valid check (
  (venue_preparation_updated_by is null and venue_preparation_updated_at is null
    and venue_preparation_version = 0)
  or (venue_preparation_updated_by is not null and venue_preparation_updated_at is not null
    and venue_preparation_version > 0)
);

notify pgrst, 'reload schema';
commit;
-- END S-25 DATA-PRESERVING MIGRATION

-- BEGIN S-91 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test.
-- Safe to repeat. Existing events receive their earliest confirmed booking
-- as the initial primary so the migration preserves attendee information.
begin;

alter table bookings.bookings
  add column if not exists is_primary boolean not null default false,
  add column if not exists primary_selected_by uuid,
  add column if not exists primary_selected_at timestamptz;

-- Backfill exactly one confirmed booking per event. The decision actor is the
-- best audit identity; coordinator_id is the fallback for legacy rows.
with ranked as (
  select id,
         row_number() over (
           partition by event_id order by submitted_at, id
         ) as position
  from bookings.bookings
  where status = 'confirmed'
)
update bookings.bookings b
set is_primary = true,
    primary_selected_by = coalesce(b.decided_by, b.coordinator_id),
    primary_selected_at = coalesce(b.decided_at, b.submitted_at)
from ranked r
where b.id = r.id and r.position = 1
  and not exists (
    select 1 from bookings.bookings current
    where current.event_id = b.event_id and current.is_primary
  );

alter table bookings.bookings drop constraint if exists bookings_primary_valid;
alter table bookings.bookings add constraint bookings_primary_valid check (
  (is_primary and status = 'confirmed'
    and primary_selected_by is not null and primary_selected_at is not null)
  or (not is_primary
    and primary_selected_by is null and primary_selected_at is null)
);

create unique index if not exists bookings_one_primary_per_event_idx
  on bookings.bookings (event_id) where is_primary;

-- First confirmation becomes primary. Losing a confirmed state clears the
-- marker, but never guesses which remaining venue the Coordinator prefers.
create or replace function bookings.maintain_primary_booking()
returns trigger
language plpgsql
set search_path = bookings, pg_temp
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(new.event_id::text, 0));
  if new.status <> 'confirmed' then
    new.is_primary := false;
    new.primary_selected_by := null;
    new.primary_selected_at := null;
  elsif not exists (
    select 1 from bookings.bookings b
    where b.event_id = new.event_id and b.is_primary
      and (tg_op = 'INSERT' or b.id <> new.id)
  ) then
    new.is_primary := true;
    new.primary_selected_by := coalesce(new.decided_by, new.coordinator_id);
    new.primary_selected_at := coalesce(new.decided_at, now());
  end if;
  return new;
end;
$$;

drop trigger if exists bookings_maintain_primary_booking on bookings.bookings;
create trigger bookings_maintain_primary_booking
  before insert or update of status on bookings.bookings
  for each row execute function bookings.maintain_primary_booking();

-- Move the marker under one event lock. Clearing then selecting avoids a
-- transient duplicate while the partial unique index remains the final guard.
create or replace function bookings.set_primary_booking(
  p_booking_id uuid,
  p_selected_by uuid
)
returns setof bookings.bookings
language plpgsql
security definer
set search_path = bookings, pg_temp
as $$
declare
  target bookings.bookings%rowtype;
begin
  select * into target from bookings.bookings where id = p_booking_id;
  if not found then return; end if;
  if target.status <> 'confirmed' then
    raise exception 'Only a confirmed venue booking can be primary'
      using errcode = 'P0001';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(target.event_id::text, 0));
  update bookings.bookings
     set is_primary = false,
         primary_selected_by = null,
         primary_selected_at = null
   where event_id = target.event_id and is_primary and id <> target.id;
  update bookings.bookings
     set is_primary = true,
         primary_selected_by = p_selected_by,
         primary_selected_at = now()
   where id = target.id and status = 'confirmed'
  returning * into target;
  if not found then
    raise exception 'Only a confirmed venue booking can be primary'
      using errcode = 'P0001';
  end if;
  return next target;
end;
$$;

revoke execute on function bookings.set_primary_booking(uuid, uuid)
  from public, anon, authenticated;
grant execute on function bookings.set_primary_booking(uuid, uuid)
  to service_role;

notify pgrst, 'reload schema';
commit;
-- END S-91 DATA-PRESERVING MIGRATION
