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
  storage_location   text,
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
  constraint equipment_storage_location_valid
    check (
      storage_location is null
      or (btrim(storage_location) <> '' and char_length(storage_location) <= 200)
    ),
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

-- BEGIN S-92 DATA-PRESERVING MIGRATION
-- Existing installations: run this entire block in BOTH dev and test.
-- Existing catalogue rows keep a null location until Technical Support records
-- one. The location is descriptive metadata and is not used by availability.
begin;

alter table equipment.equipment
  add column if not exists storage_location text;

alter table equipment.equipment
  drop constraint if exists equipment_storage_location_valid;
alter table equipment.equipment add constraint equipment_storage_location_valid
  check (
    storage_location is null
    or (btrim(storage_location) <> '' and char_length(storage_location) <= 200)
  );

notify pgrst, 'reload schema';
commit;
-- END S-92 DATA-PRESERVING MIGRATION

-- BEGIN S-60 VERSIONED REQUIREMENT BATCH
-- Data-preserving; apply in DEV and TEST after developer review. No cross-
-- schema foreign keys or reads: event_id and actor_id remain opaque UUIDs.
begin;

create table if not exists equipment.change_operations (
  id uuid primary key,
  event_id uuid not null,
  actor_id uuid not null,
  baseline jsonb not null check (jsonb_typeof(baseline) = 'array'),
  proposed jsonb not null check (jsonb_typeof(proposed) = 'array'),
  original_rows jsonb not null check (jsonb_typeof(original_rows) = 'array'),
  status text not null check (status in ('applied','finalized','aborted')),
  created_at timestamptz not null default now(),
  finished_at timestamptz
);
create unique index if not exists equipment_one_applied_change_per_event
  on equipment.change_operations(event_id) where status = 'applied';
create index if not exists equipment_change_operations_event
  on equipment.change_operations(event_id, created_at desc);

-- All existing Equipment requirement paths, including S-18's audited RPCs,
-- respect an active S-60 operation. The matching operation's batch/abort may
-- write within its own transaction; direct callers cannot set this GUC over
-- the exposed HTTP routes.
create or replace function equipment.guard_change_operation()
returns trigger language plpgsql security invoker
set search_path = equipment, pg_temp as $$
declare p_event_id uuid;
begin
  p_event_id := case when tg_op = 'DELETE' then old.event_id else new.event_id end;
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 60));
  if exists (
    select 1 from equipment.change_operations
    where event_id = p_event_id and status = 'applied'
      and id::text is distinct from nullif(current_setting('equipment.s60_operation', true), '')
  ) then
    raise exception 'Requirement change is in progress' using errcode = '23514';
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end;
$$;
drop trigger if exists equipment_requirements_change_operation on equipment.requirements;
create trigger equipment_requirements_change_operation
  before insert or update or delete on equipment.requirements
  for each row execute function equipment.guard_change_operation();

create or replace function equipment.apply_change_batch(
  p_operation_id uuid, p_event_id uuid, p_actor_id uuid,
  p_baseline jsonb, p_proposed jsonb
)
returns setof equipment.change_operations language plpgsql security invoker
set search_path = equipment, pg_temp as $$
declare op equipment.change_operations%rowtype; current_rows jsonb; current_snapshot jsonb;
        item jsonb; old_quantity integer; new_quantity integer; item_id uuid;
begin
  if jsonb_typeof(p_baseline) is distinct from 'array'
     or jsonb_typeof(p_proposed) is distinct from 'array' then
    raise exception 'Invalid equipment snapshot' using errcode = '23514';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 60));
  select * into op from equipment.change_operations where id = p_operation_id for update;
  if found then
    if op.event_id is distinct from p_event_id or op.actor_id is distinct from p_actor_id
       or op.baseline is distinct from p_baseline or op.proposed is distinct from p_proposed
       or op.status not in ('applied','finalized') then
      raise exception 'Operation conflicts with previous use' using errcode = '23514';
    end if;
    return next op; return;
  end if;
  select coalesce(jsonb_agg(to_jsonb(r) order by r.equipment_item_id), '[]'::jsonb)
    into current_rows from equipment.requirements r where event_id = p_event_id;
  select coalesce(jsonb_agg(jsonb_build_object('equipment_item_id',x->>'equipment_item_id',
      'required_quantity',(x->>'required_quantity')::integer) order by x->>'equipment_item_id'), '[]'::jsonb)
    into current_snapshot from jsonb_array_elements(current_rows) x;
  if current_snapshot is distinct from p_baseline then
    raise exception 'Equipment requirements changed' using errcode = '23514';
  end if;
  if (select count(*) from jsonb_array_elements(p_proposed)) is distinct from
     (select count(distinct x->>'equipment_item_id') from jsonb_array_elements(p_proposed) x) then
    raise exception 'Duplicate equipment item' using errcode = '23514';
  end if;
  for item in select value from jsonb_array_elements(p_proposed) loop
    item_id := (item->>'equipment_item_id')::uuid;
    new_quantity := (item->>'required_quantity')::integer;
    if new_quantity is null or new_quantity < 1 then
      raise exception 'Invalid equipment quantity' using errcode = '23514';
    end if;
    if not exists (select 1 from equipment.equipment
                   where id = item_id and lifecycle_status = 'active'
                     and operational_status = 'available')
       and not exists (select 1 from jsonb_array_elements(p_baseline) b
                       where (b->>'equipment_item_id')::uuid = item_id
                         and (b->>'required_quantity')::integer = new_quantity) then
      raise exception 'Changed equipment item is unavailable' using errcode = '23514';
    end if;
  end loop;
  insert into equipment.change_operations(id,event_id,actor_id,baseline,proposed,original_rows,status)
    values(p_operation_id,p_event_id,p_actor_id,p_baseline,p_proposed,current_rows,'applied')
    returning * into op;
  perform set_config('equipment.s60_operation', p_operation_id::text, true);
  for item in select value from jsonb_array_elements(p_baseline) loop
    item_id := (item->>'equipment_item_id')::uuid;
    if not exists (select 1 from jsonb_array_elements(p_proposed) p
                   where (p->>'equipment_item_id')::uuid = item_id) then
      delete from equipment.requirements where event_id = p_event_id and equipment_item_id = item_id;
      insert into equipment.requirement_changes(event_id,equipment_item_id,action,before_quantity,after_quantity,changed_by)
        values(p_event_id,item_id,'removed',(item->>'required_quantity')::integer,null,p_actor_id);
    end if;
  end loop;
  for item in select value from jsonb_array_elements(p_proposed) loop
    item_id := (item->>'equipment_item_id')::uuid;
    new_quantity := (item->>'required_quantity')::integer;
    select required_quantity into old_quantity from equipment.requirements
      where event_id = p_event_id and equipment_item_id = item_id;
    if old_quantity is distinct from new_quantity then
      insert into equipment.requirements(event_id,equipment_item_id,required_quantity,recorded_by_coordinator_id)
        values(p_event_id,item_id,new_quantity,p_actor_id)
        on conflict(event_id,equipment_item_id) do update
          set required_quantity = excluded.required_quantity,
              recorded_by_coordinator_id = excluded.recorded_by_coordinator_id,
              updated_at = now();
      insert into equipment.requirement_changes(event_id,equipment_item_id,action,before_quantity,after_quantity,changed_by)
        values(p_event_id,item_id,case when old_quantity is null then 'created' else 'updated' end,
               old_quantity,new_quantity,p_actor_id);
    end if;
  end loop;
  return next op;
end;
$$;

create or replace function equipment.finish_change_batch(p_operation_id uuid)
returns setof equipment.change_operations language plpgsql security invoker
set search_path = equipment, pg_temp as $$
declare op equipment.change_operations%rowtype;
begin
  select * into op from equipment.change_operations where id = p_operation_id for update;
  if not found then raise exception 'Operation not found' using errcode = 'P0002'; end if;
  if op.status = 'aborted' then raise exception 'Operation was aborted' using errcode = '23514'; end if;
  if op.status = 'applied' then
    update equipment.change_operations set status = 'finalized', finished_at = now()
      where id = p_operation_id returning * into op;
  end if;
  return next op;
end;
$$;

-- Used only if Events rejected finalisation. The complete current snapshot
-- must still match this operation's proposed values; otherwise leave the
-- operation incomplete for manual reconciliation rather than lose a new edit.
create or replace function equipment.abort_change_batch(p_operation_id uuid)
returns setof equipment.change_operations language plpgsql security invoker
set search_path = equipment, pg_temp as $$
declare op equipment.change_operations%rowtype; current_snapshot jsonb; original jsonb;
begin
  select * into op from equipment.change_operations where id = p_operation_id for update;
  if not found then raise exception 'Operation not found' using errcode = 'P0002'; end if;
  if op.status = 'finalized' then raise exception 'Finalized operation cannot abort' using errcode = '23514'; end if;
  if op.status = 'aborted' then return next op; return; end if;
  select coalesce(jsonb_agg(jsonb_build_object('equipment_item_id',r.equipment_item_id,
      'required_quantity',r.required_quantity) order by r.equipment_item_id), '[]'::jsonb)
    into current_snapshot from equipment.requirements r where event_id = op.event_id;
  if current_snapshot is distinct from op.proposed then
    raise exception 'Equipment changed; manual reconciliation required' using errcode = '23514';
  end if;
  perform set_config('equipment.s60_operation', p_operation_id::text, true);
  delete from equipment.requirements where event_id = op.event_id;
  for original in select value from jsonb_array_elements(op.original_rows) loop
    insert into equipment.requirements(id,event_id,equipment_item_id,required_quantity,
      recorded_by_coordinator_id,created_at,updated_at)
    values ((original->>'id')::uuid,op.event_id,(original->>'equipment_item_id')::uuid,
      (original->>'required_quantity')::integer,(original->>'recorded_by_coordinator_id')::uuid,
      (original->>'created_at')::timestamptz,(original->>'updated_at')::timestamptz);
  end loop;
  update equipment.change_operations set status='aborted',finished_at=now()
    where id=p_operation_id returning * into op;
  return next op;
end;
$$;

alter table equipment.change_operations enable row level security;
grant all on equipment.change_operations to service_role;
revoke execute on function equipment.apply_change_batch(uuid,uuid,uuid,jsonb,jsonb) from public,anon,authenticated;
revoke execute on function equipment.finish_change_batch(uuid) from public,anon,authenticated;
revoke execute on function equipment.abort_change_batch(uuid) from public,anon,authenticated;
grant execute on function equipment.apply_change_batch(uuid,uuid,uuid,jsonb,jsonb) to service_role;
grant execute on function equipment.finish_change_batch(uuid) to service_role;
grant execute on function equipment.abort_change_batch(uuid) to service_role;
notify pgrst, 'reload schema';
commit;
-- END S-60 VERSIONED REQUIREMENT BATCH
