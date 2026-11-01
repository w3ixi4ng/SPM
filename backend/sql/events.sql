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
  assigned_coordinator_id         uuid,
  assigning_lead_id               uuid,
  -- S-84: the previous owner and monotonic version make a reassignment
  -- retryable across the events/notifications service boundary. The version
  -- also prevents a delayed old retry from reverting a newer transfer.
  previous_coordinator_id         uuid,
  coordinator_assignment_version integer not null default 0,

  -- S-43: requested by the assigned Coordinator during planning. The staff
  -- id is opaque: users remains the source of truth and no cross-schema
  -- foreign key is created.
  technical_support_required     boolean not null default false,
  technical_support_details      text,
  assigned_technical_support_id  uuid,
  technical_support_assigned_at  timestamptz,

  -- S-26: one event-level record of equipment-side preparation. The
  -- authenticated assigned Technical Support worker owns this transition.
  equipment_preparation_status     text not null default 'not_started',
  equipment_preparation_updated_by uuid,
  equipment_preparation_updated_at timestamptz,

  -- S-17: the assigned Technical Support's sign-off on the equipment
  -- arrangements. Null until given; cleared whenever the Coordinator changes
  -- the equipment requirements. Constraints are in the S-17 block below.
  technical_signoff_decision         text,
  technical_signoff_reason           text,
  technical_signoff_override_comment text,
  technical_signoff_by               uuid,
  technical_signoff_at               timestamptz,

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

  -- S-86: the current Operational Safety Check is independent of the Event
  -- Coordinator's original request decision above. A safety rejection is a
  -- rejection of the arrangements, not a rejection of the event request.
  safety_decision            text,
  safety_decision_reason     text,
  safety_officer_id          uuid,
  safety_decided_at          timestamptz,
  -- S-87: append-only audit records for every completed safety review. The
  -- current decision fields above may be cleared when revised arrangements
  -- are resubmitted; this history is never cleared or replaced.
  safety_review_history      jsonb not null default '[]'::jsonb,

  -- S-18: Coordinator-maintained planning information. Internal notes and
  -- edit history are returned only by assignment-scoped coordinator routes.
  contact_name               text,
  contact_email              text,
  contact_phone              text,
  internal_notes             text,
  edit_version               integer not null default 0,
  edit_history               jsonb not null default '[]'::jsonb,
  safety_recheck_required    boolean not null default false,

  -- S-51: whether attendees register, and when they may. No timezone: the
  -- period is Singapore wall-clock time, like the event's own dates and
  -- times. Null whenever registration is off. Constraints are in the S-51
  -- block at the end of this file.
  registration_required      boolean not null default false,
  registration_opens_at      timestamp without time zone,
  registration_closes_at     timestamp without time zone,
  -- S-50: set when the Organiser closes registration early, cleared when
  -- they reopen it. A real instant (timestamptz), unlike the period above:
  -- it records when they did it, not a time on the event's own calendar.
  registration_closed_at     timestamptz,

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
    check (status in (
      'draft', 'submitted', 'under_review', 'planning',
      'pending_safety_check', 'confirmed', 'preparation', 'safety_rejected',
      'safety_changes_requested', 'cancelled', 'rejected', 'returned'
    )),

  constraint events_name_not_blank
    check (name is null or btrim(name) <> ''),

  constraint events_purpose_not_blank
    check (purpose is null or btrim(purpose) <> ''),

  constraint events_contact_fields_not_blank
    check (
      (contact_name is null or btrim(contact_name) <> '')
      and (contact_email is null or btrim(contact_email) <> '')
      and (contact_phone is null or btrim(contact_phone) <> '')
      and (internal_notes is null or btrim(internal_notes) <> '')
    ),

  constraint events_edit_version_nonnegative check (edit_version >= 0),
  constraint events_edit_history_array check (jsonb_typeof(edit_history) = 'array'),

  constraint events_venue_not_blank
    check (venue is null or btrim(venue) <> ''),

  constraint events_attendance_positive
    check (expected_attendance is null or expected_attendance > 0),

  constraint events_equipment_preparation_status_allowed
    check (equipment_preparation_status in ('not_started', 'in_progress', 'ready')),

  constraint events_equipment_preparation_audit_valid
    check (
      (equipment_preparation_updated_by is null and equipment_preparation_updated_at is null)
      or (equipment_preparation_updated_by is not null and equipment_preparation_updated_at is not null)
    ),

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
  -- S-61: 'cancelled' may come before or after the request decision.
  constraint events_decision_matches_status
    check (
      (status in ('draft', 'submitted', 'under_review') and decision is null)
      or (status in (
        'planning', 'pending_safety_check', 'confirmed', 'preparation',
        'safety_rejected', 'safety_changes_requested', 'rejected', 'returned'
      ) and decision is not null)
      or status = 'cancelled'
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

  constraint events_safety_decision_allowed
    check (
      safety_decision is null
      or safety_decision in ('approved', 'rejected', 'changes_requested')
    ),

  constraint events_safety_review_history_array
    check (jsonb_typeof(safety_review_history) = 'array'),

  constraint events_safety_state_consistent
    check (
      (
        safety_decision is null
        and safety_decision_reason is null
        and safety_officer_id is null
        and safety_decided_at is null
        and status not in (
          'confirmed', 'preparation', 'safety_rejected', 'safety_changes_requested'
        )
      )
      or (
        safety_decision = 'approved'
        and safety_decision_reason is null
        and safety_officer_id is not null
        and safety_decided_at is not null
        and status in ('confirmed', 'preparation')
      )
      or (
        safety_decision = 'rejected'
        and safety_decision_reason is not null
        and btrim(safety_decision_reason) <> ''
        and safety_officer_id is not null
        and safety_decided_at is not null
        and status = 'safety_rejected'
      )
      or (
        safety_decision = 'changes_requested'
        and safety_decision_reason is not null
        and btrim(safety_decision_reason) <> ''
        and safety_officer_id is not null
        and safety_decided_at is not null
        and status = 'planning'
      )
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
    ),

  constraint events_coordinator_assignment_version_nonnegative
    check (coordinator_assignment_version >= 0),

  constraint events_previous_coordinator_distinct
    check (
      previous_coordinator_id is null
      or (
        assigned_coordinator_id is not null
        and previous_coordinator_id <> assigned_coordinator_id
      )
    )
);

-- S-84 upgrade path for existing projects. Already-assigned events start at
-- version 0; their first real reassignment moves to version 1.
alter table events.events
  add column if not exists previous_coordinator_id uuid,
  add column if not exists coordinator_assignment_version integer not null default 0,
  add column if not exists assigning_lead_id uuid;

alter table events.events
  drop constraint if exists events_coordinator_assignment_version_nonnegative;
alter table events.events add constraint events_coordinator_assignment_version_nonnegative
  check (coordinator_assignment_version >= 0);

alter table events.events
  drop constraint if exists events_previous_coordinator_distinct;
alter table events.events add constraint events_previous_coordinator_distinct
  check (
    previous_coordinator_id is null
    or (
      assigned_coordinator_id is not null
      and previous_coordinator_id <> assigned_coordinator_id
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

-- S-86/S-87 upgrade path. The four scalar fields form the current decision;
-- S-87 adds an append-only JSON history so resubmission can clear the current
-- blocker without deleting its audit record.
alter table events.events
  add column if not exists safety_decision text,
  add column if not exists safety_decision_reason text,
  add column if not exists safety_officer_id uuid,
  add column if not exists safety_decided_at timestamptz,
  add column if not exists safety_review_history jsonb not null default '[]'::jsonb;

-- Preserve pre-S-87 current decisions as review 1 before any lifecycle
-- migration. Reapplying the file is harmless because only empty histories are
-- backfilled.
update events.events
set safety_review_history = jsonb_build_array(
  jsonb_build_object(
    'review_number', 1,
    'decision', safety_decision,
    'reason', safety_decision_reason,
    'safety_officer_id', safety_officer_id,
    'decided_at', safety_decided_at
  )
)
where safety_decision is not null
  and safety_review_history = '[]'::jsonb;

alter table events.events drop constraint if exists events_safety_review_history_array;
alter table events.events add constraint events_safety_review_history_array
  check (jsonb_typeof(safety_review_history) = 'array');

alter table events.events drop constraint if exists events_status_allowed;
alter table events.events add constraint events_status_allowed
  check (status in (
    'draft', 'submitted', 'under_review', 'planning',
    'pending_safety_check', 'confirmed', 'preparation', 'safety_rejected',
    'safety_changes_requested', 'cancelled', 'rejected', 'returned'
  ));

alter table events.events drop constraint if exists events_decision_matches_status;
alter table events.events add constraint events_decision_matches_status
  check (
    (status in ('draft', 'submitted', 'under_review') and decision is null)
    or (status in (
      'planning', 'pending_safety_check', 'confirmed', 'preparation',
      'safety_rejected', 'safety_changes_requested', 'cancelled',
      'rejected', 'returned'
    ) and decision is not null)
  );

alter table events.events drop constraint if exists events_safety_decision_allowed;
alter table events.events add constraint events_safety_decision_allowed
  check (
    safety_decision is null
    or safety_decision in ('approved', 'rejected', 'changes_requested')
  );

alter table events.events drop constraint if exists events_safety_state_consistent;
-- Existing S-86 change requests used the transient status below. S-87 makes
-- their return automatic while the preserved current decision marks why the
-- event is back in planning.
update events.events
set status = 'planning'
where status = 'safety_changes_requested'
  and safety_decision = 'changes_requested';

-- S-17: the Coordinator now submits a planning event for the Operational
-- Safety Check, which moves it to pending_safety_check -- the stage S-86 used
-- `confirmed` for. Only the Safety Officer's approval makes it `confirmed`
-- (S-86 approved it to `preparation`). `preparation` stays allowed for a
-- later story but nothing sets it now. Both updates match nothing once run.
update events.events
set status = 'pending_safety_check'
where status = 'confirmed'
  and safety_decision is null;

update events.events
set status = 'confirmed'
where status = 'preparation'
  and safety_decision = 'approved';

alter table events.events add constraint events_safety_state_consistent
  check (
    (
      safety_decision is null
      and safety_decision_reason is null
      and safety_officer_id is null
      and safety_decided_at is null
      and status not in (
        'confirmed', 'preparation', 'safety_rejected', 'safety_changes_requested'
      )
    )
    or (
      safety_decision = 'approved'
      and safety_decision_reason is null
      and safety_officer_id is not null
      and safety_decided_at is not null
      and status in ('confirmed', 'preparation')
    )
    or (
      safety_decision = 'rejected'
      and safety_decision_reason is not null
      and btrim(safety_decision_reason) <> ''
      and safety_officer_id is not null
      and safety_decided_at is not null
      and status = 'safety_rejected'
    )
    or (
      safety_decision = 'changes_requested'
      and safety_decision_reason is not null
      and btrim(safety_decision_reason) <> ''
      and safety_officer_id is not null
      and safety_decided_at is not null
      and status = 'planning'
    )
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

-- S-62 upgrade path. Safe to run repeatedly. An Organiser's cancellation
-- request is stored on the event: one per event, all three fields set
-- together or none. Requesting never changes status -- the event is only
-- cancelled once a later review completes it.
alter table events.events
  add column if not exists cancellation_reason text,
  add column if not exists cancellation_requested_at timestamptz,
  add column if not exists cancellation_requested_by uuid;

alter table events.events
  drop constraint if exists events_cancellation_request_consistent;
alter table events.events add constraint events_cancellation_request_consistent
  check (
    (
      cancellation_reason is null
      and cancellation_requested_at is null
      and cancellation_requested_by is null
    )
    or (
      cancellation_reason is not null
      and btrim(cancellation_reason) <> ''
      and char_length(cancellation_reason) <= 1000
      and cancellation_requested_at is not null
      and cancellation_requested_by is not null
    )
  );

-- S-61 upgrade path. Safe to run repeatedly. The assigned Coordinator's
-- decision on the cancellation request -- the latest one only; a new request
-- after a decline clears it. Approving sets status 'cancelled'; declining
-- leaves status alone and needs a reason.
alter table events.events
  add column if not exists cancellation_decision text,
  add column if not exists cancellation_decision_reason text,
  add column if not exists cancellation_decided_by uuid,
  add column if not exists cancellation_decided_at timestamptz;

alter table events.events
  drop constraint if exists events_cancellation_decision_consistent;
alter table events.events add constraint events_cancellation_decision_consistent
  check (
    (
      cancellation_decision is null
      and cancellation_decision_reason is null
      and cancellation_decided_by is null
      and cancellation_decided_at is null
    )
    or (
      cancellation_requested_at is not null
      and cancellation_decided_by is not null
      and cancellation_decided_at is not null
      and (
        (cancellation_decision = 'approved' and cancellation_decision_reason is null
          and status = 'cancelled')
        or (cancellation_decision = 'declined'
          and cancellation_decision_reason is not null
          and btrim(cancellation_decision_reason) <> ''
          and char_length(cancellation_decision_reason) <= 1000)
      )
    )
  );

-- S-61: an event can be cancelled before the Coordinator has decided on the
-- request itself (submitted, under_review), so 'cancelled' no longer
-- requires a request decision. Includes S-87's pending_safety_check, so this
-- must stay after the S-86/S-87 block, which defines the rule without it.
alter table events.events drop constraint if exists events_decision_matches_status;
alter table events.events add constraint events_decision_matches_status
  check (
    (status in ('draft', 'submitted', 'under_review') and decision is null)
    or (status in (
      'planning', 'pending_safety_check', 'confirmed', 'preparation',
      'safety_rejected', 'safety_changes_requested', 'rejected', 'returned'
    ) and decision is not null)
    or status = 'cancelled'
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

-- S-17 changed both predicates below. `create index if not exists` keeps an
-- existing index's old predicate, so each is dropped and rebuilt.
drop index if exists events.events_events_assigned_technical_support_id_idx;
create index events_events_assigned_technical_support_id_idx
  on events.events (assigned_technical_support_id)
  where status in ('planning', 'pending_safety_check', 'confirmed', 'preparation')
    and assigned_technical_support_id is not null;

drop index if exists events.events_events_pending_safety_review_idx;
create index events_events_pending_safety_review_idx
  on events.events (updated_at)
  where status = 'pending_safety_check' and safety_decision is null;

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

-- S-88: requests belong to Events. The Lead snapshot preserves the
-- supervisory scope even after the Coordinator changes. Historical events
-- without assigning_lead_id are deliberately not backfilled or exposed.
create table if not exists events.reassignment_requests (
  id uuid primary key default gen_random_uuid(),
  -- Deliberately no cascade: request history survives event removal.
  event_id uuid not null,
  event_name text not null,
  requester_id uuid not null,
  assigning_lead_id uuid not null,
  assignment_version integer not null,
  reason text not null check (btrim(reason) <> ''),
  status text not null default 'pending' check (status in ('pending', 'actioned')),
  created_at timestamptz not null default now(),
  actioned_at timestamptz,
  constraint reassignment_action_time_check check (
    (status = 'pending' and actioned_at is null)
    or (status = 'actioned' and actioned_at is not null)
  )
);
alter table events.reassignment_requests
  drop constraint if exists reassignment_requests_event_id_fkey;
create unique index if not exists reassignment_one_pending_per_event
  on events.reassignment_requests(event_id) where status = 'pending';
create index if not exists reassignment_requester_history
  on events.reassignment_requests(requester_id, created_at desc);
create index if not exists reassignment_lead_history
  on events.reassignment_requests(assigning_lead_id, created_at desc);

-- Lock the event while checking the submitted request, so a concurrent S-84
-- transfer cannot leave a new request pending for its former owner.
create or replace function events.validate_reassignment_request()
returns trigger language plpgsql security invoker as $$
declare current_event events.events%rowtype;
begin
  select * into current_event from events.events where id = new.event_id for update;
  if not found or current_event.assigned_coordinator_id is distinct from new.requester_id
     or current_event.assigning_lead_id is null
     or current_event.assigning_lead_id is distinct from new.assigning_lead_id
     or current_event.coordinator_assignment_version is distinct from new.assignment_version
     or current_event.status not in ('submitted','planning','pending_safety_check','confirmed','returned') then
    raise exception 'Event assignment changed or has no responsible Lead' using errcode = '23514';
  end if;
  new.reason := btrim(new.reason);
  new.event_name := coalesce(current_event.name, 'Untitled event');
  return new;
end;
$$;
drop trigger if exists reassignment_request_validate on events.reassignment_requests;
create trigger reassignment_request_validate before insert on events.reassignment_requests
  for each row execute function events.validate_reassignment_request();

-- S-84's successful compare-and-set update is the only actioning event.
-- This runs in the same transaction as the event update, so failure or a
-- losing concurrent write cannot mark a request actioned.
create or replace function events.action_reassignment_request()
returns trigger language plpgsql security invoker as $$
begin
  if old.assigned_coordinator_id is not null
     and new.assigned_coordinator_id is distinct from old.assigned_coordinator_id then
    update events.reassignment_requests
       set status = 'actioned', actioned_at = now()
     where event_id = old.id and requester_id = old.assigned_coordinator_id
       and assignment_version = old.coordinator_assignment_version
       and status = 'pending';
  end if;
  return new;
end;
$$;
drop trigger if exists events_action_reassignment_request on events.events;
create trigger events_action_reassignment_request
  after update of assigned_coordinator_id on events.events
  for each row execute function events.action_reassignment_request();

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
alter table events.reassignment_requests enable row level security;

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

-- S-26 migration for an existing Events table. Safe to run repeatedly.
alter table events.events
  add column if not exists equipment_preparation_status text not null default 'not_started',
  add column if not exists equipment_preparation_updated_by uuid,
  add column if not exists equipment_preparation_updated_at timestamptz;

alter table events.events drop constraint if exists events_equipment_preparation_status_allowed;
alter table events.events add constraint events_equipment_preparation_status_allowed
  check (equipment_preparation_status in ('not_started', 'in_progress', 'ready'));
alter table events.events drop constraint if exists events_equipment_preparation_audit_valid;
alter table events.events add constraint events_equipment_preparation_audit_valid
  check (
    (equipment_preparation_updated_by is null and equipment_preparation_updated_at is null)
    or (equipment_preparation_updated_by is not null and equipment_preparation_updated_at is not null)
  );

-- BEGIN S-18 DATA-PRESERVING MIGRATION
-- Existing installations: run through END S-18 in BOTH dev and test.
begin;
-- Remove the legacy form before any ADD COLUMN with a default can rewrite an
-- old row and make PostgreSQL evaluate that outdated constraint.
alter table events.events drop constraint if exists events_safety_state_consistent;

-- S-18 migration for an existing Events table. Safe to run repeatedly and
-- data-preserving. The row version makes update-plus-history optimistic and
-- atomic in one conditional statement.
alter table events.events
  add column if not exists contact_name text,
  add column if not exists contact_email text,
  add column if not exists contact_phone text,
  add column if not exists internal_notes text,
  add column if not exists edit_version integer not null default 0,
  add column if not exists edit_history jsonb not null default '[]'::jsonb,
  add column if not exists safety_recheck_required boolean not null default false;

alter table events.events drop constraint if exists events_contact_fields_not_blank;
alter table events.events add constraint events_contact_fields_not_blank
  check (
    (contact_name is null or btrim(contact_name) <> '')
    and (contact_email is null or btrim(contact_email) <> '')
    and (contact_phone is null or btrim(contact_phone) <> '')
    and (internal_notes is null or btrim(internal_notes) <> '')
  );
alter table events.events drop constraint if exists events_edit_version_nonnegative;
alter table events.events add constraint events_edit_version_nonnegative
  check (edit_version >= 0);
alter table events.events drop constraint if exists events_edit_history_array;
alter table events.events add constraint events_edit_history_array
  check (jsonb_typeof(edit_history) = 'array');

-- S-18 submits a materially revised event into the S-17 pending safety stage.
-- Reinstall the canonical S-17 safety constraint so older projects accept the
-- transition while preserving the current lifecycle rules for new writes.
alter table events.events add constraint events_safety_state_consistent
  check (
    (
      safety_decision is null
      and safety_decision_reason is null
      and safety_officer_id is null
      and safety_decided_at is null
      and status not in (
        'confirmed', 'preparation', 'safety_rejected', 'safety_changes_requested'
      )
    )
    or (
      safety_decision = 'approved'
      and safety_decision_reason is null
      and safety_officer_id is not null
      and safety_decided_at is not null
      and status in ('confirmed', 'preparation')
    )
    or (
      safety_decision = 'rejected'
      and safety_decision_reason is not null
      and btrim(safety_decision_reason) <> ''
      and safety_officer_id is not null
      and safety_decided_at is not null
      and status = 'safety_rejected'
    )
    or (
      safety_decision = 'changes_requested'
      and safety_decision_reason is not null
      and btrim(safety_decision_reason) <> ''
      and safety_officer_id is not null
      and safety_decided_at is not null
      and status = 'planning'
    )
  ) not valid;

-- S-17 Technical Support sign-off. Safe to run repeatedly. Approve carries an
-- override comment only when it was given over an S-44 shortage; decline
-- always carries a reason. Who and when are set together with the decision.
alter table events.events
  add column if not exists technical_signoff_decision text,
  add column if not exists technical_signoff_reason text,
  add column if not exists technical_signoff_override_comment text,
  add column if not exists technical_signoff_by uuid,
  add column if not exists technical_signoff_at timestamptz;

alter table events.events drop constraint if exists events_technical_signoff_valid;
alter table events.events add constraint events_technical_signoff_valid
  check (
    (
      technical_signoff_decision is null
      and technical_signoff_reason is null
      and technical_signoff_override_comment is null
      and technical_signoff_by is null
      and technical_signoff_at is null
    )
    or (
      technical_signoff_decision = 'approved'
      and technical_signoff_reason is null
      and (
        technical_signoff_override_comment is null
        or (btrim(technical_signoff_override_comment) <> ''
            and char_length(technical_signoff_override_comment) <= 500)
      )
      and technical_signoff_by is not null
      and technical_signoff_at is not null
    )
    or (
      technical_signoff_decision = 'declined'
      and technical_signoff_reason is not null
      and btrim(technical_signoff_reason) <> ''
      and char_length(technical_signoff_reason) <= 500
      and technical_signoff_override_comment is null
      and technical_signoff_by is not null
      and technical_signoff_at is not null
    )
  );

notify pgrst, 'reload schema';
commit;
-- END S-18 DATA-PRESERVING MIGRATION

-- BEGIN S-51 REGISTRATION PERIOD
-- Existing installations: run through END S-51 in BOTH dev and test. Safe to
-- run repeatedly and data-preserving: every existing event gets registration
-- off and no period.
begin;
alter table events.events
  add column if not exists registration_required boolean not null default false,
  add column if not exists registration_opens_at timestamp without time zone,
  add column if not exists registration_closes_at timestamp without time zone;

-- Registration off means no period; a period, once both ends are set, is a
-- real interval. Closing before the event starts is checked by the service,
-- which already has the event's start in hand.
alter table events.events drop constraint if exists events_registration_period_valid;
alter table events.events add constraint events_registration_period_valid
  check (
    (
      not registration_required
      and registration_opens_at is null
      and registration_closes_at is null
    )
    or (
      registration_required
      and (
        registration_opens_at is null
        or registration_closes_at is null
        or registration_closes_at > registration_opens_at
      )
    )
  );

-- The public listing reads confirmed events only.
create index if not exists events_events_status_idx on events.events (status);

notify pgrst, 'reload schema';
commit;
-- END S-51 REGISTRATION PERIOD

-- BEGIN S-50 CLOSE REGISTRATION EARLY
-- Existing installations: run through END S-50 in BOTH dev and test. Safe to
-- run repeatedly and data-preserving: every existing event stays open.
begin;
alter table events.events
  add column if not exists registration_closed_at timestamptz;

-- Only an event that takes registrations can have it closed.
alter table events.events drop constraint if exists events_registration_closed_needs_registration;
alter table events.events add constraint events_registration_closed_needs_registration
  check (registration_closed_at is null or registration_required);

notify pgrst, 'reload schema';
commit;
-- END S-50 CLOSE REGISTRATION EARLY

-- BEGIN S-82 EVENT CHANGE HISTORY
-- Every installation: run through END S-82 in BOTH dev and test. Safe to run
-- repeatedly and data-preserving: it adds a table and backfills it from what
-- existing events already record, once per event.
begin;

-- One row per significant action on an event: who (actor), what (action,
-- details) and when (occurred_at, server time). Append-only -- see the
-- revoke and trigger below. actor_id has no foreign key: users live in the
-- users schema, and an entry outlives the account that made it.
create table if not exists events.event_history (
  id          bigint generated always as identity primary key,
  event_id    uuid not null references events.events (id) on delete cascade,
  -- Null only for a backfilled entry whose actor was never stored.
  actor_id    uuid,
  actor_role  text,
  category    text not null check (category in (
    'submission', 'review', 'assignment', 'edit', 'venue', 'equipment', 'safety'
  )),
  action      text not null check (btrim(action) <> ''),
  details     jsonb not null default '{}'::jsonb check (jsonb_typeof(details) = 'object'),
  occurred_at timestamptz not null default now(),
  constraint event_history_actor_has_role
    check (actor_id is null or actor_role is not null)
);
create index if not exists event_history_event_occurred
  on events.event_history (event_id, occurred_at desc, id desc);

-- Entries cannot be edited or deleted (S-82 AC4). The default privileges
-- above grant service_role everything on new tables, so take the writes
-- back. The trigger also stops the table owner, e.g. from the SQL Editor.
revoke update, delete, truncate on events.event_history from service_role, anon, authenticated;
grant select, insert on events.event_history to service_role;

-- A delete is allowed only as the cascade from deleting the event itself,
-- which has already removed the event row by the time this runs.
create or replace function events.event_history_append_only()
returns trigger language plpgsql as $$
begin
  if tg_op = 'DELETE'
     and not exists (select 1 from events.events where id = old.event_id) then
    return old;
  end if;
  raise exception 'Event history entries cannot be changed or deleted'
    using errcode = '42501';
end;
$$;
drop trigger if exists event_history_append_only on events.event_history;
create trigger event_history_append_only
  before update or delete on events.event_history
  for each row execute function events.event_history_append_only();

alter table events.event_history enable row level security;

-- Events created before S-82 get the history their own columns can prove.
-- Skips any event that already has an entry, backfilled or live, so it runs
-- once per event however often it is called and never doubles a live entry. Who decided a request was never stored,
-- so those entries have no actor. Returns the number of entries added.
create or replace function events.backfill_event_history(p_event_id uuid default null)
returns integer language plpgsql as $$
declare added integer;
begin
  with todo as (
    select e.* from events.events e
    where (p_event_id is null or e.id = p_event_id)
      and not exists (select 1 from events.event_history h where h.event_id = e.id)
  ),
  rows as (
    select id as event_id, organiser_id as actor_id, 'event_organiser' as actor_role,
           'submission' as category, 'submitted' as action,
           jsonb_build_object('backfilled', true) as details, submitted_at as occurred_at
      from todo where submitted_at is not null
    union all
    select id, null, null, 'review', 'request_' || decision,
           jsonb_build_object('reason', decision_reason, 'comment', decision_comment, 'backfilled', true),
           decided_at
      from todo where decision is not null and decided_at is not null
    union all
    select t.id, (r ->> 'changed_by')::uuid, 'event_coordinator', 'edit', 'edited',
           jsonb_build_object('changes', r -> 'changes', 'backfilled', true),
           (r ->> 'changed_at')::timestamptz
      from todo t, jsonb_array_elements(t.edit_history) r
    union all
    select t.id, (r ->> 'safety_officer_id')::uuid, 'safety_officer', 'safety',
           'safety_' || (r ->> 'decision'),
           jsonb_build_object('reason', r ->> 'reason', 'backfilled', true),
           (r ->> 'decided_at')::timestamptz
      from todo t, jsonb_array_elements(t.safety_review_history) r
    union all
    select q.event_id, q.requester_id, 'event_coordinator', 'assignment', 'reassignment_requested',
           jsonb_build_object('reason', q.reason, 'backfilled', true), q.created_at
      from events.reassignment_requests q join todo t on t.id = q.event_id
    union all
    select id, cancellation_requested_by, 'event_organiser', 'review', 'cancellation_requested',
           jsonb_build_object('reason', cancellation_reason, 'backfilled', true),
           cancellation_requested_at
      from todo where cancellation_requested_by is not null and cancellation_requested_at is not null
    union all
    select id, cancellation_decided_by, 'event_coordinator', 'review',
           'cancellation_' || cancellation_decision,
           jsonb_build_object('reason', cancellation_decision_reason, 'backfilled', true),
           cancellation_decided_at
      from todo where cancellation_decided_by is not null and cancellation_decided_at is not null
    union all
    select id, technical_signoff_by, 'technical_support', 'equipment',
           'technical_signoff_' || technical_signoff_decision,
           jsonb_build_object('reason', technical_signoff_reason, 'backfilled', true),
           technical_signoff_at
      from todo where technical_signoff_by is not null and technical_signoff_at is not null
    union all
    select id, equipment_preparation_updated_by, 'technical_support', 'equipment',
           'equipment_preparation_changed',
           jsonb_build_object('from', null, 'to', equipment_preparation_status, 'backfilled', true),
           equipment_preparation_updated_at
      from todo where equipment_preparation_updated_by is not null
  )
  insert into events.event_history (event_id, actor_id, actor_role, category, action, details, occurred_at)
  select event_id, actor_id, actor_role, category, action, details, occurred_at from rows;
  get diagnostics added = row_count;
  return added;
end;
$$;
revoke execute on function events.backfill_event_history(uuid) from public, anon, authenticated;
grant execute on function events.backfill_event_history(uuid) to service_role;

select events.backfill_event_history();

notify pgrst, 'reload schema';
commit;
-- END S-82 EVENT CHANGE HISTORY

-- BEGIN S-59 EVENT CHANGE REQUESTS
-- Apply this data-preserving block in BOTH dev and test. Requests remain in
-- Events ownership; equipment item IDs and quantities are comparison data,
-- never writes to equipment.requirements.
begin;

create table if not exists events.change_requests (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references events.events(id) on delete cascade,
  requested_by uuid not null,
  submitted_at timestamptz not null default now(),
  status text not null default 'pending',
  expected_event_updated_at timestamptz not null,
  accepted_values jsonb not null,
  proposed_values jsonb not null,
  accepted_equipment jsonb not null default '[]'::jsonb,
  proposed_equipment jsonb not null default '[]'::jsonb,
  resolved_at timestamptz,
  constraint change_requests_status_allowed
    check (status in ('pending', 'accepted', 'rejected')),
  constraint change_requests_resolution_matches_status
    check ((status = 'pending') = (resolved_at is null)),
  constraint change_requests_values_objects
    check (jsonb_typeof(accepted_values) = 'object'
      and jsonb_typeof(proposed_values) = 'object'),
  constraint change_requests_equipment_arrays
    check (jsonb_typeof(accepted_equipment) = 'array'
      and jsonb_typeof(proposed_equipment) = 'array')
);

-- One outstanding request, with resolved rows retained as history.
create unique index if not exists change_requests_one_pending_per_event
  on events.change_requests(event_id) where status = 'pending';
create index if not exists change_requests_event_history
  on events.change_requests(event_id, submitted_at desc);

-- Lock the event while checking its owner, lifecycle and accepted version.
-- The Events service supplies requested_by from verified Auth and only its
-- trusted composite can reach the insert route; this trigger repeats the
-- storage-side checks so concurrent submissions cannot bypass them.
create or replace function events.validate_change_request()
returns trigger language plpgsql security invoker
set search_path = events, pg_temp
as $$
declare
  current_event events.events%rowtype;
begin
  select * into current_event from events.events
    where id = new.event_id for update;
  if not found then
    raise exception 'Event not found' using errcode = '23503';
  end if;
  if current_event.organiser_id is distinct from new.requested_by then
    raise exception 'Event not owned by requester' using errcode = '42501';
  end if;
  if current_event.status not in (
    'submitted', 'under_review', 'returned', 'planning',
    'pending_safety_check', 'confirmed', 'preparation'
  ) then
    raise exception 'Event cannot receive a change request'
      using errcode = '23514';
  end if;
  if current_event.updated_at is distinct from new.expected_event_updated_at then
    raise exception 'Event changed before request submission'
      using errcode = '23514';
  end if;

  new.accepted_values := jsonb_build_object(
    'start_date', current_event.start_date,
    'start_time', current_event.start_time,
    'end_date', current_event.end_date,
    'end_time', current_event.end_time,
    'expected_attendance', current_event.expected_attendance,
    'venue', current_event.venue,
    'special_requirements', current_event.special_requirements,
    'room_layout', current_event.room_layout,
    'required_facilities', to_jsonb(current_event.required_facilities),
    'required_accessibility', to_jsonb(current_event.required_accessibility)
  );
  if new.accepted_values = new.proposed_values
     and new.accepted_equipment = new.proposed_equipment then
    raise exception 'Change request has no changed values'
      using errcode = '23514';
  end if;
  new.submitted_at := now();
  new.status := 'pending';
  new.resolved_at := null;
  return new;
end;
$$;

drop trigger if exists change_request_validate on events.change_requests;
create trigger change_request_validate before insert on events.change_requests
  for each row execute function events.validate_change_request();

alter table events.change_requests enable row level security;
grant usage on schema events to service_role;
grant all on events.change_requests to service_role;
-- Existing events schema default grants cover future tables; explicit grant
-- above is still required when this table is added after the prior grants.
notify pgrst, 'reload schema';
commit;
-- END S-59 EVENT CHANGE REQUESTS

-- BEGIN S-69 CANCEL A SAFETY-CHECKED EVENT
-- Existing installations: run through END S-69 in BOTH dev and test. Safe to
-- run repeatedly and data-preserving.
--
-- S-62 lets an Organiser ask to cancel a confirmed event, and S-61 lets the
-- Coordinator approve it, but the S-17 rule above only allowed a
-- safety-approved event to be `confirmed` or `preparation`, so approving
-- failed with 23514. Cancelling keeps the Safety Officer's decision as it was
-- -- it is history, like the Coordinator's -- so `cancelled` is allowed in
-- the two branches where the check has been decided and the event can still
-- be cancelled. A safety-rejected event is not cancellable (S-62), so its
-- branch is unchanged.
alter table events.events drop constraint if exists events_safety_state_consistent;
alter table events.events add constraint events_safety_state_consistent
  check (
    (
      safety_decision is null
      and safety_decision_reason is null
      and safety_officer_id is null
      and safety_decided_at is null
      and status not in (
        'confirmed', 'preparation', 'safety_rejected', 'safety_changes_requested'
      )
    )
    or (
      safety_decision = 'approved'
      and safety_decision_reason is null
      and safety_officer_id is not null
      and safety_decided_at is not null
      and status in ('confirmed', 'preparation', 'cancelled')
    )
    or (
      safety_decision = 'rejected'
      and safety_decision_reason is not null
      and btrim(safety_decision_reason) <> ''
      and safety_officer_id is not null
      and safety_decided_at is not null
      and status = 'safety_rejected'
    )
    or (
      safety_decision = 'changes_requested'
      and safety_decision_reason is not null
      and btrim(safety_decision_reason) <> ''
      and safety_officer_id is not null
      and safety_decided_at is not null
      and status in ('planning', 'cancelled')
    )
  ) not valid;

notify pgrst, 'reload schema';
-- END S-69 CANCEL A SAFETY-CHECKED EVENT

-- BEGIN S-89 COORDINATOR CANCELS WITHOUT AN ALTERNATIVE VENUE
-- Existing installations: run through END S-89 in BOTH dev and test. Safe to
-- run repeatedly and data-preserving.
--
-- The assigned Coordinator cancels an event that venue unavailability affects
-- and for which no alternative venue was found. The record stays on the event:
-- why, what alternatives were considered with the Organiser, which affected
-- bookings justified it, who and when (all set by the service).
-- venue_cancellation_previous_status keeps what the S-82 history entry needs,
-- so that entry can be written -- or retried -- from the row alone.
-- venue_cancellation_completed_at is set only once the history entry exists,
-- every booking was released and the Organiser and Attendees were notified;
-- until then the event is cancelled but the operation is still to be
-- finished.
begin;

alter table events.events
  add column if not exists venue_cancellation_reason text,
  add column if not exists venue_cancellation_alternatives text,
  add column if not exists venue_cancellation_booking_ids uuid[],
  add column if not exists venue_cancelled_by uuid,
  add column if not exists venue_cancelled_at timestamptz,
  add column if not exists venue_cancellation_previous_status text,
  add column if not exists venue_cancellation_completed_at timestamptz;

alter table events.events
  drop constraint if exists events_venue_cancellation_consistent;
alter table events.events add constraint events_venue_cancellation_consistent
  check (
    (
      venue_cancellation_reason is null
      and venue_cancellation_alternatives is null
      and venue_cancellation_booking_ids is null
      and venue_cancelled_by is null
      and venue_cancelled_at is null
      and venue_cancellation_previous_status is null
      and venue_cancellation_completed_at is null
    )
    or (
      status = 'cancelled'
      and btrim(venue_cancellation_reason) <> ''
      and char_length(venue_cancellation_reason) <= 1000
      and btrim(venue_cancellation_alternatives) <> ''
      and char_length(venue_cancellation_alternatives) <= 1000
      and cardinality(venue_cancellation_booking_ids) > 0
      and venue_cancelled_by is not null
      and venue_cancelled_at is not null
      and venue_cancellation_previous_status in (
        'planning', 'pending_safety_check', 'confirmed', 'preparation',
        'safety_changes_requested'
      )
      and (venue_cancellation_completed_at is null
           or venue_cancellation_completed_at >= venue_cancelled_at)
      -- One cancellation path per event: never also an approved S-61 request.
      and cancellation_decision is distinct from 'approved'
    )
  );

-- One S-82 entry per S-89 cancellation, so the history step can be retried
-- without ever writing a second one. A partial index: other actions may
-- repeat freely.
create unique index if not exists event_history_one_venue_cancellation
  on events.event_history (event_id)
  where action = 'cancelled_venue_unavailable';

notify pgrst, 'reload schema';
commit;
-- END S-89 COORDINATOR CANCELS WITHOUT AN ALTERNATIVE VENUE

-- BEGIN S-60 SIGNIFICANT CHANGE REVIEW
-- Data-preserving migration. Apply this block in BOTH DEV and TEST only after
-- the developer reviews the source. Existing requests and event records stay.
begin;

alter table events.change_requests
  add column if not exists impacts jsonb not null default '[]'::jsonb,
  add column if not exists impact_version integer not null default 0,
  add column if not exists operation_id uuid,
  add column if not exists impact_acknowledged_at timestamptz,
  add column if not exists reviewed_by uuid,
  add column if not exists decision_reason text;

alter table events.events
  add column if not exists s60_edit_impacts jsonb not null default '[]'::jsonb,
  add column if not exists s60_edit_impact_version integer not null default 0;

alter table events.change_requests drop constraint if exists change_requests_status_allowed;
alter table events.change_requests add constraint change_requests_status_allowed
  check (status in ('pending', 'applying', 'accepted', 'rejected'));
alter table events.change_requests drop constraint if exists change_requests_resolution_matches_status;
alter table events.change_requests add constraint change_requests_resolution_matches_status
  check ((status in ('pending', 'applying')) = (resolved_at is null));
alter table events.change_requests drop constraint if exists change_requests_impacts_array;
alter table events.change_requests add constraint change_requests_impacts_array
  check (jsonb_typeof(impacts) = 'array');
alter table events.change_requests drop constraint if exists change_requests_impact_version_nonnegative;
alter table events.change_requests add constraint change_requests_impact_version_nonnegative
  check (impact_version >= 0);
drop index if exists events.change_requests_one_pending_per_event;
create unique index if not exists change_requests_one_outstanding_per_event
  on events.change_requests(event_id) where status in ('pending', 'applying');
create unique index if not exists change_requests_operation_unique
  on events.change_requests(operation_id) where operation_id is not null;

-- The preview is built across service APIs. This transaction locks Events'
-- owned event and request, then saves exactly what the Coordinator acknowledged
-- before any accepted value is changed. It cannot grant authority over another
-- service's records.
create or replace function events.prepare_change_acceptance(
  p_request_id uuid, p_coordinator_id uuid, p_operation_id uuid,
  p_impacts jsonb, p_expected_updated_at timestamptz
)
returns setof events.change_requests language plpgsql security invoker
set search_path = events, pg_temp as $$
declare r events.change_requests%rowtype; e events.events%rowtype; request_event_id uuid;
begin
  if jsonb_typeof(p_impacts) is distinct from 'array' or p_operation_id is null then
    raise exception 'Invalid impact assessment' using errcode = '23514';
  end if;
  select event_id into request_event_id from events.change_requests where id = p_request_id;
  if not found then raise exception 'Change request not found' using errcode = 'P0002'; end if;
  select * into e from events.events where id = request_event_id for update;
  select * into r from events.change_requests where id = p_request_id for update;
  if not found then raise exception 'Change request not found' using errcode = 'P0002'; end if;
  if e.assigned_coordinator_id is distinct from p_coordinator_id then
    raise exception 'Not assigned Coordinator' using errcode = '42501';
  end if;
  if r.status = 'applying' and r.operation_id = p_operation_id then
    return next r; return;
  end if;
  if r.status <> 'pending' or e.updated_at is distinct from p_expected_updated_at
     or e.updated_at is distinct from r.expected_event_updated_at then
    raise exception 'Change request is stale' using errcode = '23514';
  end if;
  update events.change_requests set status = 'applying', operation_id = p_operation_id,
      impacts = p_impacts, impact_acknowledged_at = now(), reviewed_by = p_coordinator_id,
      impact_version = impact_version + 1
    where id = p_request_id returning * into r;
  return next r;
end;
$$;

-- Finalise only after the Equipment owner confirms its idempotent batch. The
-- request, accepted Events fields, lifecycle and immutable audit commit in one
-- Events transaction. An interrupted response can safely be read/retried.
create or replace function events.complete_change_acceptance(
  p_request_id uuid, p_coordinator_id uuid, p_operation_id uuid
)
returns setof events.change_requests language plpgsql security invoker
set search_path = events, pg_temp as $$
declare r events.change_requests%rowtype; e events.events%rowtype; next_status text; request_event_id uuid;
begin
  select event_id into request_event_id from events.change_requests where id = p_request_id;
  if not found then raise exception 'Change request not found' using errcode = 'P0002'; end if;
  select * into e from events.events where id = request_event_id for update;
  select * into r from events.change_requests where id = p_request_id for update;
  if not found then raise exception 'Change request not found' using errcode = 'P0002'; end if;
  if r.status = 'accepted' and r.operation_id = p_operation_id then return next r; return; end if;
  if r.status <> 'applying' or r.operation_id is distinct from p_operation_id
     or e.assigned_coordinator_id is distinct from p_coordinator_id
     or e.updated_at is distinct from r.expected_event_updated_at then
    raise exception 'Change request is stale' using errcode = '23514';
  end if;
  next_status := case when e.status in ('confirmed','preparation','pending_safety_check')
    then 'planning' else e.status end;
  perform set_config('events.s60_operation', p_operation_id::text, true);
  update events.events set
    start_date = (r.proposed_values->>'start_date')::date,
    start_time = (r.proposed_values->>'start_time')::time,
    end_date = (r.proposed_values->>'end_date')::date,
    end_time = (r.proposed_values->>'end_time')::time,
    expected_attendance = (r.proposed_values->>'expected_attendance')::integer,
    venue = r.proposed_values->>'venue',
    special_requirements = r.proposed_values->>'special_requirements',
    room_layout = r.proposed_values->>'room_layout',
    required_facilities = array(select jsonb_array_elements_text(r.proposed_values->'required_facilities')),
    required_accessibility = array(select jsonb_array_elements_text(r.proposed_values->'required_accessibility')),
    status = next_status,
    safety_recheck_required = case when next_status = 'planning' and e.status <> next_status then true
                                   else e.safety_recheck_required end,
    safety_decision = case when e.status <> next_status then null else e.safety_decision end,
    safety_decision_reason = case when e.status <> next_status then null else e.safety_decision_reason end,
    safety_officer_id = case when e.status <> next_status then null else e.safety_officer_id end,
    safety_decided_at = case when e.status <> next_status then null else e.safety_decided_at end,
    edit_version = e.edit_version + 1
    where id = e.id;
  update events.change_requests set status = 'accepted', resolved_at = now()
    where id = p_request_id returning * into r;
  insert into events.event_history(event_id, actor_id, actor_role, category, action, details)
    values (e.id, p_coordinator_id, 'event_coordinator', 'review', 'change_request_accepted',
      jsonb_build_object('request_id', p_request_id, 'before', r.accepted_values,
                         'after', r.proposed_values, 'impacts', r.impacts));
  return next r;
end;
$$;

create or replace function events.reject_change_request(
  p_request_id uuid, p_coordinator_id uuid, p_reason text
)
returns setof events.change_requests language plpgsql security invoker
set search_path = events, pg_temp as $$
declare r events.change_requests%rowtype; e events.events%rowtype; request_event_id uuid;
begin
  if nullif(btrim(p_reason), '') is null then
    raise exception 'Reason is required' using errcode = '23514';
  end if;
  select event_id into request_event_id from events.change_requests where id = p_request_id;
  if not found then raise exception 'Change request not found' using errcode = 'P0002'; end if;
  select * into e from events.events where id = request_event_id for update;
  select * into r from events.change_requests where id = p_request_id for update;
  if not found then raise exception 'Change request not found' using errcode = 'P0002'; end if;
  if e.assigned_coordinator_id is distinct from p_coordinator_id then
    raise exception 'Not assigned Coordinator' using errcode = '42501';
  end if;
  if r.status <> 'pending' then
    raise exception 'Change request is no longer pending' using errcode = '23514';
  end if;
  update events.change_requests set status = 'rejected', resolved_at = now(),
      reviewed_by = p_coordinator_id, decision_reason = btrim(p_reason)
    where id = p_request_id returning * into r;
  insert into events.event_history(event_id, actor_id, actor_role, category, action, details)
    values (e.id, p_coordinator_id, 'event_coordinator', 'review', 'change_request_rejected',
      jsonb_build_object('request_id', p_request_id, 'reason', btrim(p_reason)));
  return next r;
end;
$$;

-- The composite verifies owner-backed evidence first. This function repeats
-- assignment, version and state checks and appends review evidence atomically.
create or replace function events.resolve_change_impact(
  p_request_id uuid, p_coordinator_id uuid, p_impact_id text,
  p_expected_version integer, p_action text, p_evidence jsonb
)
returns setof events.change_requests language plpgsql security invoker
set search_path = events, pg_temp as $$
declare r events.change_requests%rowtype; e events.events%rowtype; item jsonb; request_event_id uuid;
        next_impacts jsonb := '[]'::jsonb; found_item boolean := false;
begin
  if nullif(btrim(p_action), '') is null or jsonb_typeof(p_evidence) is distinct from 'object' then
    raise exception 'Resolution action and evidence are required' using errcode = '23514';
  end if;
  select event_id into request_event_id from events.change_requests where id = p_request_id;
  if not found then raise exception 'Change request not found' using errcode = 'P0002'; end if;
  select * into e from events.events where id = request_event_id for update;
  select * into r from events.change_requests where id = p_request_id for update;
  if not found then raise exception 'Change request not found' using errcode = 'P0002'; end if;
  if e.assigned_coordinator_id is distinct from p_coordinator_id then
    raise exception 'Not assigned Coordinator' using errcode = '42501';
  end if;
  if r.status <> 'accepted' or r.impact_version <> p_expected_version then
    raise exception 'Impact review changed' using errcode = '23514';
  end if;
  for item in select value from jsonb_array_elements(r.impacts) loop
    if item->>'id' = p_impact_id then
      if item->>'status' <> 'outstanding' then
        raise exception 'Impact is already resolved' using errcode = '23514';
      end if;
      found_item := true;
      item := item || jsonb_build_object('status','resolved','resolution_action',btrim(p_action),
        'evidence',p_evidence,'resolved_by',p_coordinator_id,'resolved_at',now());
    end if;
    next_impacts := next_impacts || jsonb_build_array(item);
  end loop;
  if not found_item then raise exception 'Impact not found' using errcode = 'P0002'; end if;
  update events.change_requests set impacts = next_impacts, impact_version = impact_version + 1
    where id = p_request_id returning * into r;
  insert into events.event_history(event_id, actor_id, actor_role, category, action, details)
    values(e.id,p_coordinator_id,'event_coordinator','review','change_impact_resolved',
      jsonb_build_object('request_id',p_request_id,'impact_id',p_impact_id,
                         'action',btrim(p_action),'evidence',p_evidence));
  return next r;
end;
$$;

-- The composite and atomic routes both show a readable 409. This trigger is
-- the final guard for a concurrent or direct planning -> safety transition.
create or replace function events.guard_unresolved_change_impacts()
returns trigger language plpgsql security invoker
set search_path = events, pg_temp as $$
begin
  if new.status = 'pending_safety_check' and old.status is distinct from new.status
     and (exists (
       select 1 from events.change_requests r,
            lateral jsonb_array_elements(r.impacts) impact
       where r.event_id = new.id and r.status = 'accepted'
         and impact->>'status' = 'outstanding'
     ) or exists (
       select 1 from jsonb_array_elements(new.s60_edit_impacts) impact
       where impact->>'status' = 'outstanding'
     )) then
    raise exception 'Resolve change impacts before safety submission'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

-- While acceptance is applying Equipment's batch, no unrelated Events write
-- may change the baseline or assignment and strand the operation. Only the
-- matching finalisation RPC can update the row.
create or replace function events.guard_change_operation()
returns trigger language plpgsql security invoker
set search_path = events, pg_temp as $$
declare target_event_id uuid;
begin
  target_event_id := case when tg_op = 'DELETE' then old.id else new.id end;
  if exists (
    select 1 from events.change_requests
    where event_id = target_event_id and status = 'applying'
      and operation_id::text is distinct from nullif(current_setting('events.s60_operation', true), '')
  ) then
    raise exception 'Event change acceptance is in progress' using errcode = '23514';
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end;
$$;
drop trigger if exists events_guard_change_operation on events.events;
create trigger events_guard_change_operation before update or delete on events.events
  for each row execute function events.guard_change_operation();

create or replace function events.resolve_edit_impact(
  p_event_id uuid, p_coordinator_id uuid, p_impact_id text,
  p_expected_version integer, p_action text, p_evidence jsonb
)
returns setof events.events language plpgsql security invoker
set search_path = events, pg_temp as $$
declare e events.events%rowtype; item jsonb; next_impacts jsonb := '[]'::jsonb;
        found_item boolean := false;
begin
  if nullif(btrim(p_action), '') is null or jsonb_typeof(p_evidence) is distinct from 'object' then
    raise exception 'Resolution action and evidence are required' using errcode = '23514';
  end if;
  select * into e from events.events where id = p_event_id for update;
  if not found then raise exception 'Event not found' using errcode = 'P0002'; end if;
  if e.assigned_coordinator_id is distinct from p_coordinator_id then
    raise exception 'Not assigned Coordinator' using errcode = '42501';
  end if;
  if e.s60_edit_impact_version <> p_expected_version then
    raise exception 'Impact review changed' using errcode = '23514';
  end if;
  for item in select value from jsonb_array_elements(e.s60_edit_impacts) loop
    if item->>'id' = p_impact_id then
      if item->>'status' <> 'outstanding' then
        raise exception 'Impact is already resolved' using errcode = '23514';
      end if;
      found_item := true;
      item := item || jsonb_build_object('status','resolved','resolution_action',btrim(p_action),
        'evidence',p_evidence,'resolved_by',p_coordinator_id,'resolved_at',now());
    end if;
    next_impacts := next_impacts || jsonb_build_array(item);
  end loop;
  if not found_item then raise exception 'Impact not found' using errcode = 'P0002'; end if;
  update events.events set s60_edit_impacts = next_impacts,
    s60_edit_impact_version = s60_edit_impact_version + 1
    where id = p_event_id returning * into e;
  insert into events.event_history(event_id,actor_id,actor_role,category,action,details)
    values(p_event_id,p_coordinator_id,'event_coordinator','review','change_impact_resolved',
      jsonb_build_object('impact_id',p_impact_id,'action',btrim(p_action),'evidence',p_evidence));
  return next e;
end;
$$;
drop trigger if exists events_guard_unresolved_change_impacts on events.events;
create trigger events_guard_unresolved_change_impacts before update on events.events
  for each row execute function events.guard_unresolved_change_impacts();

revoke execute on function events.prepare_change_acceptance(uuid,uuid,uuid,jsonb,timestamptz)
  from public, anon, authenticated;
revoke execute on function events.complete_change_acceptance(uuid,uuid,uuid)
  from public, anon, authenticated;
revoke execute on function events.reject_change_request(uuid,uuid,text)
  from public, anon, authenticated;
revoke execute on function events.resolve_change_impact(uuid,uuid,text,integer,text,jsonb)
  from public, anon, authenticated;
grant execute on function events.prepare_change_acceptance(uuid,uuid,uuid,jsonb,timestamptz) to service_role;
grant execute on function events.complete_change_acceptance(uuid,uuid,uuid) to service_role;
grant execute on function events.reject_change_request(uuid,uuid,text) to service_role;
grant execute on function events.resolve_change_impact(uuid,uuid,text,integer,text,jsonb) to service_role;
revoke execute on function events.resolve_edit_impact(uuid,uuid,text,integer,text,jsonb)
  from public, anon, authenticated;
grant execute on function events.resolve_edit_impact(uuid,uuid,text,integer,text,jsonb) to service_role;
notify pgrst, 'reload schema';
commit;
-- END S-60 SIGNIFICANT CHANGE REVIEW
