-- backend/sql/equipment.sql
--
-- S-39 equipment catalogue. One row represents an equipment type/pool, not
-- an individually serialized physical unit.
--
-- Run in BOTH dev and test projects, then expose `equipment` under
-- Data API -> Settings -> Exposed schemas.

-- Rebuild from scratch. DESTRUCTIVE -- uncomment only against a project whose
-- equipment data may be discarded.
-- drop schema if exists equipment cascade;

create schema if not exists equipment;

create table if not exists equipment.equipment (
  id                 uuid primary key default gen_random_uuid(),
  type               text not null,
  description        text,
  total_quantity     integer not null,
  operational_status text not null default 'available',
  lifecycle_status   text not null default 'active',
  created_by         uuid not null,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),

  constraint equipment_type_not_blank
    check (btrim(type) <> ''),
  constraint equipment_description_not_blank
    check (description is null or btrim(description) <> ''),
  constraint equipment_total_quantity_positive
    check (total_quantity > 0),
  constraint equipment_operational_status_allowed
    check (operational_status in ('available', 'unavailable', 'maintenance')),
  constraint equipment_lifecycle_status_allowed
    check (lifecycle_status in ('active', 'retired'))
);

-- S-40. The equipment service owns the event-to-equipment relationship. The
-- event id is opaque because events belongs to another service; the equipment
-- item foreign key stays within this service's schema.
create table if not exists equipment.requirements (
  id                             uuid primary key default gen_random_uuid(),
  event_id                       uuid not null,
  equipment_item_id              uuid not null
    references equipment.equipment(id) on delete restrict,
  required_quantity              integer not null,
  recorded_by_coordinator_id     uuid not null,
  created_at                     timestamptz not null default now(),
  updated_at                     timestamptz not null default now(),

  constraint equipment_requirements_quantity_positive
    check (required_quantity > 0),
  constraint equipment_requirements_event_item_unique
    unique (event_id, equipment_item_id)
);

-- BEGIN S-18 DATA-PRESERVING MIGRATION
-- Existing installations: run from this marker through END S-18 in BOTH dev
-- and test. Every statement is safe to repeat.
begin;
-- S-18: append-only requirement history for future S-82 aggregation. The
-- event id remains opaque; Equipment owns both the requirement and its audit.
create table if not exists equipment.requirement_changes (
  id                 uuid primary key default gen_random_uuid(),
  event_id           uuid not null,
  equipment_item_id  uuid not null,
  action             text not null,
  before_quantity    integer,
  after_quantity     integer,
  changed_by         uuid not null,
  changed_at         timestamptz not null default now(),
  constraint equipment_requirement_changes_action_allowed
    check (action in ('created', 'updated', 'removed'))
);

create or replace function equipment.save_requirement_with_history(
  p_event_id uuid,
  p_equipment_item_id uuid,
  p_required_quantity integer,
  p_changed_by uuid
)
returns setof equipment.requirements
language plpgsql
security definer
set search_path = equipment, pg_temp
as $$
declare
  old_quantity integer;
  saved equipment.requirements%rowtype;
begin
  select required_quantity into old_quantity
    from equipment.requirements
   where event_id = p_event_id and equipment_item_id = p_equipment_item_id
   for update;

  insert into equipment.requirements (
    event_id, equipment_item_id, required_quantity,
    recorded_by_coordinator_id, updated_at
  ) values (
    p_event_id, p_equipment_item_id, p_required_quantity, p_changed_by, now()
  )
  on conflict (event_id, equipment_item_id) do update
    set required_quantity = excluded.required_quantity,
        recorded_by_coordinator_id = excluded.recorded_by_coordinator_id,
        updated_at = now()
  returning * into saved;

  if old_quantity is distinct from p_required_quantity then
    insert into equipment.requirement_changes (
      event_id, equipment_item_id, action, before_quantity, after_quantity, changed_by
    ) values (
      p_event_id, p_equipment_item_id,
      case when old_quantity is null then 'created' else 'updated' end,
      old_quantity, p_required_quantity, p_changed_by
    );
  end if;
  return next saved;
end;
$$;

create or replace function equipment.delete_requirement_with_history(
  p_event_id uuid,
  p_equipment_item_id uuid,
  p_changed_by uuid
)
returns setof equipment.requirements
language plpgsql
security definer
set search_path = equipment, pg_temp
as $$
declare
  removed equipment.requirements%rowtype;
begin
  delete from equipment.requirements
   where event_id = p_event_id and equipment_item_id = p_equipment_item_id
  returning * into removed;
  if not found then return; end if;

  insert into equipment.requirement_changes (
    event_id, equipment_item_id, action, before_quantity, after_quantity, changed_by
  ) values (
    p_event_id, p_equipment_item_id, 'removed', removed.required_quantity, null, p_changed_by
  );
  return next removed;
end;
$$;

create index if not exists equipment_equipment_type_idx
  on equipment.equipment (lower(type));

create index if not exists equipment_equipment_selection_idx
  on equipment.equipment (operational_status, lifecycle_status, lower(type));

create index if not exists equipment_requirements_event_id_idx
  on equipment.requirements (event_id, created_at);

grant usage on schema equipment to service_role;
grant all on all tables in schema equipment to service_role;
grant all on all sequences in schema equipment to service_role;

alter default privileges for role postgres in schema equipment
  grant all on tables to service_role;
alter default privileges for role postgres in schema equipment
  grant all on sequences to service_role;

alter table equipment.equipment enable row level security;
alter table equipment.requirements enable row level security;
alter table equipment.requirement_changes enable row level security;

revoke execute on function equipment.save_requirement_with_history(uuid, uuid, integer, uuid)
  from public, anon, authenticated;
revoke execute on function equipment.delete_requirement_with_history(uuid, uuid, uuid)
  from public, anon, authenticated;
grant execute on function equipment.save_requirement_with_history(uuid, uuid, integer, uuid)
  to service_role;
grant execute on function equipment.delete_requirement_with_history(uuid, uuid, uuid)
  to service_role;

notify pgrst, 'reload schema';
commit;
-- END S-18 DATA-PRESERVING MIGRATION
