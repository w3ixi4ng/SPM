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
  start_date                 date,
  start_time                 time without time zone,
  end_date                   date,
  end_time                   time without time zone,
  expected_attendance        integer,
  venue                      text,
  -- S-40 stores equipment requirements in equipment.requirements. Keep this
  -- legacy column temporarily so applying this declarative file to an
  -- existing project is non-destructive; the events API no longer accepts or
  -- returns it.
  equipment_requests         jsonb not null default '{}'::jsonb,

  -- A catch-all for anything the fixed fields do not cover -- registration
  -- arrangements, catering, security, whatever the organiser needs to say.
  -- Deliberately one free-text field rather than a column per concern: the
  -- requirement names no structure, and inventing one would be guessing.
  special_requirements       text,

  -- S-36: the venue requirements, from the venue catalogue's fixed sets so a
  -- venue can be checked against them. All optional. `venue` above is now
  -- only the organiser's free-text preference; the Coordinator books the
  -- actual venue.
  room_layout                text,
  required_facilities        text[] not null default '{}',
  required_accessibility     text[] not null default '{}',

  -- The event coordinator this request was routed to on submission -- null
  -- until then, and never chosen by the organiser. No foreign key to
  -- users.users: that would be a cross-schema reference, which the one
  -- schema per service rule (see AGENTS.md) does not allow. Like
  -- organiser_id, it is an opaque id the users service is the source of
  -- truth for.
  assigned_coordinator_id    uuid,

  -- S-43: requested by the assigned Coordinator during planning. The staff
  -- id is opaque: users remains the source of truth and no cross-schema
  -- foreign key is created.
  technical_support_required     boolean not null default false,
  technical_support_details      text,
  assigned_technical_support_id  uuid,
  technical_support_assigned_at  timestamptz,

  -- The assigned coordinator's decision on a submitted request. Null until
  -- decided; then one of the three outcomes below. Holds only the *latest*
  -- decision -- a return-then-resubmit cycle overwrites it, on purpose (see
  -- S-14): this is a single current-state field, not an audit log.
  decision                   text,

  -- Required for reject and return, forbidden for approve -- see
  -- events_decision_reason_required below.
  decision_reason            text,

  -- Optional, meaningful only for return: a clarification or amendment note
  -- for the organiser. Never set for approve or reject.
  decision_comment           text,

  -- When the decision was made. Null until then, cleared again on resubmit
  -- alongside decision/decision_reason/decision_comment, the same way
  -- submitted_at is cleared-then-reset across a draft/submit cycle.
  decided_at                 timestamptz,

  -- When the request was submitted, and null while it is a draft. Together
  -- with organiser_id this is the record of who submitted and when.
  -- Not updated_at: that moves for any write, so it cannot be relied on as a
  -- submission time even though a submitted event is currently uneditable.
  submitted_at               timestamptz,
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),

  -- S-14: submitted means "awaiting a coordinator decision". The decision
  -- leads to rejected, returned, or -- S-36 -- planning: an approved request
  -- has passed the coordinator's check and venue/equipment planning is
  -- underway. There is no 'approved' status; approved is only ever the
  -- recorded decision (see the decision column).
  constraint events_status_allowed
    check (status in ('draft', 'submitted', 'planning', 'confirmed', 'cancelled', 'rejected', 'returned')),

  constraint events_name_not_blank
    check (name is null or btrim(name) <> ''),

  constraint events_purpose_not_blank
    check (purpose is null or btrim(purpose) <> ''),

  constraint events_venue_not_blank
    check (venue is null or btrim(venue) <> ''),

  constraint events_attendance_positive
    check (expected_attendance is null or expected_attendance > 0),

  -- The end date, if set, is never before the start date -- an event
  -- spanning midnight (end_date > start_date) is fine; end_date < start_date
  -- never is.
  constraint events_date_order
    check (start_date is null or end_date is null or end_date >= start_date),

  -- end_time only has to be after start_time when the event stays on one
  -- calendar day. A multi-day event (end_date > start_date) may legitimately
  -- end at a clock time earlier than it started.
  constraint events_time_order
    check (
      start_time is null or end_time is null
      or start_date is null or end_date is null
      or end_date > start_date
      or end_time > start_time
    ),

  constraint events_equipment_requests_object
    check (jsonb_typeof(equipment_requests) = 'object'),

  constraint events_room_layout_allowed
    check (room_layout is null or room_layout in (
      'theatre', 'classroom', 'boardroom', 'u_shape', 'banquet', 'cocktail'
    )),

  constraint events_required_facilities_allowed
    check (required_facilities <@ array[
      'projector', 'screen', 'sound_system', 'microphones', 'wifi', 'stage',
      'whiteboard', 'video_conferencing', 'catering_kitchen',
      'air_conditioning', 'parking'
    ]::text[]),

  constraint events_required_accessibility_allowed
    check (required_accessibility <@ array[
      'wheelchair_access', 'step_free_entrance', 'accessible_toilets', 'lift',
      'hearing_loop', 'accessible_parking'
    ]::text[]),

  -- Every status past draft has been submitted at least once -- including
  -- planning/rejected/returned, which are outcomes of a decision made on a
  -- submitted request, not a separate path around it. Only a draft has
  -- never been submitted.
  constraint events_submitted_at_present
    check (
      (status = 'draft' and submitted_at is null)
      or (status <> 'draft' and submitted_at is not null)
    ),

  constraint events_submitted_fields_required
    check (
      status = 'draft'
      or (
        name is not null
        and purpose is not null
        and start_date is not null
        and start_time is not null
        and end_date is not null
        and end_time is not null
        and expected_attendance is not null
      )
    ),

  -- decision is set exactly when a decision has been made -- draft and
  -- submitted (awaiting one) never carry one; planning/rejected/returned
  -- always do.
  constraint events_decision_matches_status
    check (
      (status in ('draft', 'submitted') and decision is null)
      or (status in ('planning', 'confirmed', 'cancelled', 'rejected', 'returned') and decision is not null)
    ),

  constraint events_decision_allowed
    check (decision is null or decision in ('approved', 'rejected', 'returned')),

  -- Reject and return both require a reason; approve never carries one --
  -- an approval is not a judgement call that needs defending in the record
  -- the way turning a request away does.
  constraint events_decision_reason_required
    check (
      (decision in ('rejected', 'returned') and decision_reason is not null and btrim(decision_reason) <> '')
      or (decision in ('approved') and decision_reason is null)
      or decision is null
    ),

  -- The clarification/amendment comment only makes sense alongside a
  -- return -- there is nothing to amend after an approval or a closed
  -- rejection.
  constraint events_decision_comment_scope
    check (decision = 'returned' or decision_comment is null),

  constraint events_decision_comment_not_blank
    check (decision_comment is null or btrim(decision_comment) <> ''),

  -- Mirrors events_submitted_at_present: decided_at is the record of when,
  -- present exactly when a decision is.
  constraint events_decided_at_present
    check (
      (decision is null and decided_at is null)
      or (decision is not null and decided_at is not null)
    ),

  constraint events_technical_support_details_not_blank
    check (
      technical_support_details is null
      or btrim(technical_support_details) <> ''
    ),

  constraint events_technical_support_state_consistent
    check (
      (
        technical_support_required = false
        and technical_support_details is null
        and assigned_technical_support_id is null
        and technical_support_assigned_at is null
      )
      or (
        technical_support_required = true
        and (
          (assigned_technical_support_id is null and technical_support_assigned_at is null)
          or (assigned_technical_support_id is not null and technical_support_assigned_at is not null)
        )
      )
    )
);

-- S-43 upgrade path for an existing events table. These statements are
-- intentionally idempotent so this canonical file can be applied to both an
-- existing project and a fresh one.
alter table events.events
  add column if not exists technical_support_required boolean not null default false,
  add column if not exists technical_support_details text,
  add column if not exists assigned_technical_support_id uuid,
  add column if not exists technical_support_assigned_at timestamptz;

alter table events.events drop constraint if exists events_status_allowed;
alter table events.events add constraint events_status_allowed
  check (status in ('draft', 'submitted', 'planning', 'confirmed', 'cancelled', 'rejected', 'returned'));

alter table events.events drop constraint if exists events_decision_matches_status;
alter table events.events add constraint events_decision_matches_status
  check (
    (status in ('draft', 'submitted') and decision is null)
    or (status in ('planning', 'confirmed', 'cancelled', 'rejected', 'returned') and decision is not null)
  );

alter table events.events
  drop constraint if exists events_technical_support_details_not_blank;
alter table events.events add constraint events_technical_support_details_not_blank
  check (
    technical_support_details is null
    or btrim(technical_support_details) <> ''
  );

alter table events.events
  drop constraint if exists events_technical_support_state_consistent;
alter table events.events add constraint events_technical_support_state_consistent
  check (
    (
      technical_support_required = false
      and technical_support_details is null
      and assigned_technical_support_id is null
      and technical_support_assigned_at is null
    )
    or (
      technical_support_required = true
      and (
        (assigned_technical_support_id is null and technical_support_assigned_at is null)
        or (assigned_technical_support_id is not null and technical_support_assigned_at is not null)
      )
    )
  );

-- Event access is scoped by the authenticated organiser, so this supports
-- owner-filtered reads and updates without scanning the full table.
create index if not exists events_events_organiser_id_idx
  on events.events (organiser_id);

-- The coordinator-load lookup filters by assigned_coordinator_id and status
-- together for every request that occupies the coordinator's time -- this is
-- that query's index. That means submitted (awaiting decision) or planning
-- (accepted, arrangements underway) -- returned and rejected are not live
-- commitments and never block a new request.
create index if not exists events_events_assigned_coordinator_id_idx
  on events.events (assigned_coordinator_id)
  where status in ('submitted', 'planning');

create index if not exists events_events_assigned_technical_support_id_idx
  on events.events (assigned_technical_support_id)
  where status in ('planning', 'confirmed')
    and assigned_technical_support_id is not null;

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
-- ---------------------------------------------------------------------------
-- Already have this table? `create table if not exists` above does nothing to
-- it, so run this instead. Safe to run twice.
--
--   alter table events.events
--     add column if not exists special_requirements text,
--     add column if not exists submitted_at         timestamptz;
--
--   -- Backfill before adding the constraint, or existing submitted rows
--   -- violate it. updated_at is the closest thing to a submission time for
--   -- rows that predate this column; a submitted event cannot be edited, so
--   -- for those it has not moved since.
--   update events.events
--      set submitted_at = updated_at
--    where status = 'submitted' and submitted_at is null;
--
--   alter table events.events
--     add constraint events_submitted_at_present
--     check (
--       (status = 'submitted' and submitted_at is not null)
--       or (status <> 'submitted' and submitted_at is null)
--     );
-- ---------------------------------------------------------------------------
--
-- S-12: already have the table without assigned_coordinator_id? Run this
-- instead. Safe to run twice. No backfill needed -- every existing row is
-- correctly null (unassigned).
--
--   alter table events.events
--     add column if not exists assigned_coordinator_id uuid;
--
--   create index if not exists events_events_assigned_coordinator_id_idx
--     on events.events (assigned_coordinator_id)
--     where status = 'submitted';
-- ---------------------------------------------------------------------------
--
-- S-14: already have the table without the coordinator decision? Run this
-- instead. Safe to run twice. No backfill needed -- every existing row is
-- either 'draft' or 'submitted', both still valid statuses, and decision
-- defaults to null, which is exactly right for a row nothing has decided on
-- yet.
--
--   alter table events.events
--     add column if not exists decision        text,
--     add column if not exists decision_reason  text,
--     add column if not exists decision_comment text,
--     add column if not exists decided_at       timestamptz;
--
--   alter table events.events drop constraint if exists events_status_allowed;
--   alter table events.events add constraint events_status_allowed
--     check (status in ('draft', 'submitted', 'approved', 'rejected', 'returned'));
--
--   alter table events.events drop constraint if exists events_submitted_at_present;
--   alter table events.events add constraint events_submitted_at_present
--     check (
--       (status = 'draft' and submitted_at is null)
--       or (status <> 'draft' and submitted_at is not null)
--     );
--
--   alter table events.events drop constraint if exists events_submitted_fields_required;
--   alter table events.events add constraint events_submitted_fields_required
--     check (
--       status = 'draft'
--       or (
--         name is not null and purpose is not null and start_date is not null
--         and start_time is not null and end_date is not null
--         and end_time is not null and expected_attendance is not null
--         and venue is not null
--       )
--     );
--
--   alter table events.events add constraint events_decision_matches_status
--     check (
--       (status in ('draft', 'submitted') and decision is null)
--       or (status in ('approved', 'rejected', 'returned') and decision is not null)
--     );
--   alter table events.events add constraint events_decision_allowed
--     check (decision is null or decision in ('approved', 'rejected', 'returned'));
--   alter table events.events add constraint events_decision_reason_required
--     check (
--       (decision in ('rejected', 'returned') and decision_reason is not null and btrim(decision_reason) <> '')
--       or (decision in ('approved') and decision_reason is null)
--       or decision is null
--     );
--   alter table events.events add constraint events_decision_comment_scope
--     check (decision = 'returned' or decision_comment is null);
--   alter table events.events add constraint events_decision_comment_not_blank
--     check (decision_comment is null or btrim(decision_comment) <> '');
--   alter table events.events add constraint events_decided_at_present
--     check (
--       (decision is null and decided_at is null)
--       or (decision is not null and decided_at is not null)
--     );
--
--   -- Safe to run even if the S-12 version of this index already exists:
--   -- `if not exists` means it is a no-op then, not an error, at the cost of
--   -- not updating that copy's WHERE clause on its own -- see below.
--   create index if not exists events_events_assigned_coordinator_id_idx
--     on events.events (assigned_coordinator_id)
--     where status in ('submitted', 'approved');
--
--   -- Only needed if the index already existed from S-12 (WHERE status =
--   -- 'submitted') -- `if not exists` above left that old definition alone.
--   -- Harmless either way: an index only ever affects query speed, never
--   -- correctness, so approved-event conflict checks were already correct
--   -- without this, just not using the index for them.
--   drop index if exists events_events_assigned_coordinator_id_idx;
--   create index events_events_assigned_coordinator_id_idx
--     on events.events (assigned_coordinator_id)
--     where status in ('submitted', 'approved');
-- ---------------------------------------------------------------------------
--
-- S-36: already have the table with the S-14 'approved' status? Run this
-- instead. Safe to run twice. An approval now moves an event to 'planning';
-- 'approved' stays only as the recorded decision, so existing approved rows
-- are moved across before the constraints stop allowing them.
--
--   alter table events.events drop constraint if exists events_status_allowed;
--   alter table events.events drop constraint if exists events_decision_matches_status;
--
--   update events.events set status = 'planning' where status = 'approved';
--
--   alter table events.events add constraint events_status_allowed
--     check (status in ('draft', 'submitted', 'planning', 'rejected', 'returned'));
--   alter table events.events add constraint events_decision_matches_status
--     check (
--       (status in ('draft', 'submitted') and decision is null)
--       or (status in ('planning', 'rejected', 'returned') and decision is not null)
--     );
--
--   drop index if exists events.events_events_assigned_coordinator_id_idx;
--   create index events_events_assigned_coordinator_id_idx
--     on events.events (assigned_coordinator_id)
--     where status in ('submitted', 'planning');
--
-- S-36: venue requirements on the event. Already have the table? Run this
-- instead. Safe to run twice. No backfill needed: existing rows get no
-- requirements, which is valid.
--
--   alter table events.events
--     add column if not exists room_layout            text,
--     add column if not exists required_facilities    text[] not null default '{}',
--     add column if not exists required_accessibility text[] not null default '{}';
--
--   alter table events.events drop constraint if exists events_room_layout_allowed;
--   alter table events.events add constraint events_room_layout_allowed
--     check (room_layout is null or room_layout in (
--       'theatre', 'classroom', 'boardroom', 'u_shape', 'banquet', 'cocktail'
--     ));
--   alter table events.events drop constraint if exists events_required_facilities_allowed;
--   alter table events.events add constraint events_required_facilities_allowed
--     check (required_facilities <@ array[
--       'projector', 'screen', 'sound_system', 'microphones', 'wifi', 'stage',
--       'whiteboard', 'video_conferencing', 'catering_kitchen',
--       'air_conditioning', 'parking'
--     ]::text[]);
--   alter table events.events drop constraint if exists events_required_accessibility_allowed;
--   alter table events.events add constraint events_required_accessibility_allowed
--     check (required_accessibility <@ array[
--       'wheelchair_access', 'step_free_entrance', 'accessible_toilets', 'lift',
--       'hearing_loop', 'accessible_parking'
--     ]::text[]);
--
--   -- venue is only a preference now, so a submitted event no longer needs one.
--   alter table events.events drop constraint if exists events_submitted_fields_required;
--   alter table events.events add constraint events_submitted_fields_required
--     check (
--       status = 'draft'
--       or (
--         name is not null and purpose is not null and start_date is not null
--         and start_time is not null and end_date is not null
--         and end_time is not null and expected_attendance is not null
--       )
--     );
--
-- S-36: the free-text accessibility notes are dropped -- accessibility is
-- given through required_accessibility, and special_requirements is the one
-- free-text field. Already have the table? Run this instead. Safe to run
-- twice. DESTRUCTIVE: any text in the column is lost.
--
--   alter table events.events drop column if exists accessibility_requirements;
-- ---------------------------------------------------------------------------

notify pgrst, 'reload schema';
