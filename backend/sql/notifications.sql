-- backend/sql/notifications.sql
--
-- Persistent in-app notifications. The service stores opaque user and event
-- ids; users and events remain the sources of truth for those entities.
--
-- Run this in the SQL Editor of BOTH dev and test projects, then add
-- `notifications` under Data API -> Settings -> Exposed schemas.

-- Rebuild from scratch. DESTRUCTIVE -- drops the schema and every row in it,
-- with no confirmation and no undo. Uncomment only against a project whose
-- data you are happy to lose.
-- drop schema if exists notifications cascade;

create schema if not exists notifications;

create table if not exists notifications.notifications (
  id                bigint generated always as identity primary key,
  recipient_id      uuid not null,
  event_id          uuid not null,
  event_name        text not null,
  kind              text not null,
  message           text not null,
  deduplication_key text not null unique,
  created_at        timestamptz not null default now(),

  constraint notifications_event_name_not_blank
    check (btrim(event_name) <> ''),
  constraint notifications_message_not_blank
    check (btrim(message) <> ''),
  constraint notifications_deduplication_key_not_blank
    check (btrim(deduplication_key) <> ''),
  constraint notifications_kind_allowed
    check (kind in ('event_assignment', 'event_reassignment', 'venue_unavailable', 'equipment_unavailable', 'venue_hold_expiry', 'registration_confirmation', 'waiting_list_promotion', 'waiting_list_offer', 'event_cancelled', 'waiting_list_joined', 'registration_withdrawn', 'waiting_list_offer_declined', 'event_cancelled_by_coordinator', 'event_request_decision', 'event_schedule_changed', 'safety_check_outcome', 'venue_booking_decision'))
);

-- BEGIN S-74 REGISTRATION UPDATES
-- Upgrade path for an existing notifications table: S-84 added
-- event_reassignment, S-77 venue_unavailable, S-81 venue_hold_expiry, S-49
-- registration_confirmation, S-53 waiting_list_promotion, S-55
-- waiting_list_offer, S-69 event_cancelled, and S-74 waiting_list_joined,
-- registration_withdrawn and waiting_list_offer_declined. Keep S-71's
-- equipment_unavailable kind too, so rerunning the complete SQL file never
-- installs an older constraint over newer rows. Safe to run twice; run in
-- BOTH dev and test.
alter table notifications.notifications
  drop constraint if exists notifications_kind_allowed;
alter table notifications.notifications add constraint notifications_kind_allowed
  check (kind in ('event_assignment', 'event_reassignment', 'venue_unavailable', 'equipment_unavailable', 'venue_hold_expiry', 'registration_confirmation', 'waiting_list_promotion', 'waiting_list_offer', 'event_cancelled', 'waiting_list_joined', 'registration_withdrawn', 'waiting_list_offer_declined', 'event_cancelled_by_coordinator', 'event_request_decision', 'event_schedule_changed', 'safety_check_outcome', 'venue_booking_decision'));

notify pgrst, 'reload schema';
-- END S-74 REGISTRATION UPDATES

-- BEGIN S-71 EQUIPMENT AVAILABILITY NOTIFICATION
-- Existing installations: run this block in BOTH dev and test. Safe to
-- repeat; it changes only the allowed notification-kind constraint and keeps
-- every notification kind already present in shared Sprint 4 deployments.
alter table notifications.notifications
  drop constraint if exists notifications_kind_allowed;
alter table notifications.notifications add constraint notifications_kind_allowed
  check (kind in ('event_assignment', 'event_reassignment', 'venue_unavailable', 'equipment_unavailable', 'venue_hold_expiry', 'registration_confirmation', 'waiting_list_promotion', 'waiting_list_offer', 'event_cancelled', 'waiting_list_joined', 'registration_withdrawn', 'waiting_list_offer_declined', 'event_cancelled_by_coordinator', 'event_request_decision', 'event_schedule_changed', 'safety_check_outcome', 'venue_booking_decision'));

notify pgrst, 'reload schema';
-- END S-71 EQUIPMENT AVAILABILITY NOTIFICATION

-- BEGIN S-89 EVENT CANCELLED BY COORDINATOR
-- Existing installations: run this block in BOTH dev and test. Safe to
-- repeat; it changes only the allowed notification-kind constraint. The
-- Organiser is told when the Coordinator cancels their event because no
-- alternative venue was found. The last four kinds are S-63's, already in the
-- shared projects before S-63 merges; leaving them out fails with 23514.
alter table notifications.notifications
  drop constraint if exists notifications_kind_allowed;
alter table notifications.notifications add constraint notifications_kind_allowed
  check (kind in ('event_assignment', 'event_reassignment', 'venue_unavailable', 'equipment_unavailable', 'venue_hold_expiry', 'registration_confirmation', 'waiting_list_promotion', 'waiting_list_offer', 'event_cancelled', 'waiting_list_joined', 'registration_withdrawn', 'waiting_list_offer_declined', 'event_cancelled_by_coordinator', 'event_request_decision', 'event_schedule_changed', 'safety_check_outcome', 'venue_booking_decision'));

notify pgrst, 'reload schema';
-- END S-89 EVENT CANCELLED BY COORDINATOR

-- Every inbox query filters by recipient and shows newest first.
create index if not exists notifications_recipient_created_idx
  on notifications.notifications (recipient_id, created_at desc);

grant usage on schema notifications to service_role;
grant all on all tables in schema notifications to service_role;
grant all on all sequences in schema notifications to service_role;

alter default privileges for role postgres in schema notifications
  grant all on tables to service_role;
alter default privileges for role postgres in schema notifications
  grant all on sequences to service_role;

alter table notifications.notifications enable row level security;

notify pgrst, 'reload schema';
