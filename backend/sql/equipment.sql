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

create index if not exists equipment_equipment_type_idx
  on equipment.equipment (lower(type));

create index if not exists equipment_equipment_selection_idx
  on equipment.equipment (operational_status, lifecycle_status, lower(type));

grant usage on schema equipment to service_role;
grant all on all tables in schema equipment to service_role;
grant all on all sequences in schema equipment to service_role;

alter default privileges for role postgres in schema equipment
  grant all on tables to service_role;
alter default privileges for role postgres in schema equipment
  grant all on sequences to service_role;

alter table equipment.equipment enable row level security;

notify pgrst, 'reload schema';
