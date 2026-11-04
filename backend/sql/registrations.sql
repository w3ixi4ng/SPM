-- backend/sql/registrations.sql
--
-- S-51: who holds a place at which event. The service stores opaque event
-- and attendee ids; events and users remain the sources of truth for those.
--
-- Run this in the SQL Editor of BOTH dev and test projects, then add
-- `registrations` under Data API -> Settings -> Exposed schemas.

-- Rebuild from scratch. DESTRUCTIVE -- drops the schema and every row in it,
-- with no confirmation and no undo. Uncomment only against a project whose
-- data you are happy to lose.
-- drop schema if exists registrations cascade;

create schema if not exists registrations;

create table if not exists registrations.registrations (
  id          uuid primary key default gen_random_uuid(),
  event_id    uuid not null,
  attendee_id uuid not null,
  created_at  timestamptz not null default now(),

  -- One place per account per event. Also what turns a double-click, or two
  -- tabs registering at once, into a 409 rather than two places.
  constraint registrations_one_per_attendee unique (event_id, attendee_id)
);

grant usage on schema registrations to service_role;
grant all on all tables in schema registrations to service_role;
grant all on all sequences in schema registrations to service_role;

alter default privileges for role postgres in schema registrations
  grant all on tables to service_role;
alter default privileges for role postgres in schema registrations
  grant all on sequences to service_role;

alter table registrations.registrations enable row level security;

notify pgrst, 'reload schema';

-- BEGIN S-50 CAPACITY AND WAITING LIST
-- Existing installations: run through END S-50 in BOTH dev and test. Safe to
-- run repeatedly and data-preserving.

-- Attendees waiting for a place at a full event, in the order they joined.
create table if not exists registrations.waiting_list (
  id          uuid primary key default gen_random_uuid(),
  event_id    uuid not null,
  attendee_id uuid not null,
  created_at  timestamptz not null default now(),

  constraint waiting_list_one_per_attendee unique (event_id, attendee_id)
);

create index if not exists waiting_list_event_idx
  on registrations.waiting_list (event_id, created_at);

-- Takes a place only while the event has one. The capacity comes from the
-- caller (the event's expected attendance, owned by the events service); the
-- count and the insert happen here, under a per-event lock, so two people
-- registering for the last place at the same moment cannot both get it.
--   SP050 -- the event is full
--   23505 -- this Attendee already holds a place
create or replace function registrations.register(
  p_event_id    uuid,
  p_attendee_id uuid,
  p_capacity    integer
)
returns setof registrations.registrations
language plpgsql
set search_path = ''
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 50));

  if exists (
    select 1 from registrations.registrations
    where event_id = p_event_id and attendee_id = p_attendee_id
  ) then
    raise exception 'already registered' using errcode = '23505';
  end if;

  if (
    select count(*) from registrations.registrations where event_id = p_event_id
  ) >= p_capacity then
    raise exception 'event full' using errcode = 'SP050';
  end if;

  return query
    insert into registrations.registrations (event_id, attendee_id)
    values (p_event_id, p_attendee_id)
    returning *;
end;
$$;

-- The table was created after the grants at the top of this file ran on an
-- existing project, so grant it here too. Functions are executable by
-- PUBLIC by default; only the backend should call this one.
grant all on registrations.waiting_list to service_role;
revoke all on function registrations.register(uuid, uuid, integer) from public, anon, authenticated;
grant execute on function registrations.register(uuid, uuid, integer) to service_role;

alter table registrations.waiting_list enable row level security;

notify pgrst, 'reload schema';
-- END S-50 CAPACITY AND WAITING LIST

-- BEGIN S-53 WITHDRAW REGISTRATION
-- Existing installations: run through END S-53 in BOTH dev and test. Safe to
-- run repeatedly and data-preserving. Needs the S-50 block above.

-- Gives up an Attendee's place and, in the same step, hands it to whoever has
-- waited longest (join time, then id -- the S-52 order). Takes the same
-- per-event lock as registrations.register, so a withdrawal and a
-- registration can't both claim the freed place. At most one Attendee is
-- promoted, and only while a place is genuinely free: an event whose expected
-- attendance was lowered below its places promotes no one.
--   SP053 -- this Attendee holds no place at this event
-- Returns {"withdrawn": <row>, "promoted": <row> | null}.
create or replace function registrations.withdraw(
  p_event_id    uuid,
  p_attendee_id uuid,
  p_capacity    integer
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_withdrawn registrations.registrations;
  v_next      registrations.waiting_list;
  v_promoted  registrations.registrations;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 50));

  delete from registrations.registrations
  where event_id = p_event_id and attendee_id = p_attendee_id
  returning * into v_withdrawn;

  if v_withdrawn.id is null then
    raise exception 'not registered' using errcode = 'SP053';
  end if;

  if (
    select count(*) from registrations.registrations where event_id = p_event_id
  ) < p_capacity then
    delete from registrations.waiting_list
    where id = (
      select id from registrations.waiting_list
      where event_id = p_event_id
      order by created_at, id
      limit 1
    )
    returning * into v_next;

    if v_next.id is not null then
      insert into registrations.registrations (event_id, attendee_id)
      values (p_event_id, v_next.attendee_id)
      returning * into v_promoted;
    end if;
  end if;

  return jsonb_build_object(
    'withdrawn', to_jsonb(v_withdrawn),
    'promoted', case when v_promoted.id is null then null else to_jsonb(v_promoted) end
  );
end;
$$;

revoke all on function registrations.withdraw(uuid, uuid, integer) from public, anon, authenticated;
grant execute on function registrations.withdraw(uuid, uuid, integer) to service_role;

notify pgrst, 'reload schema';
-- END S-53 WITHDRAW REGISTRATION

-- BEGIN S-55 WAITING LIST OFFERS
-- Existing installations: run through END S-55 in BOTH dev and test. Safe to
-- run repeatedly and data-preserving. Needs the S-50 and S-53 blocks above.
--
-- A freed place is offered to whoever has waited longest, never given: only
-- their own acceptance registers them. While the offer is open it counts as
-- a taken place, so no one else -- newcomer or further down the line -- can
-- take it. There is no expiry; declining passes it on.

-- Set when this entry was offered a freed place; null while still waiting.
alter table registrations.waiting_list
  add column if not exists offered_at timestamptz;

-- Places held plus open offers: what a capacity is measured against.
create or replace function registrations.places_claimed(p_event_id uuid)
returns bigint
language sql
stable
set search_path = ''
as $$
  select
    (select count(*) from registrations.registrations where event_id = p_event_id)
    + (select count(*) from registrations.waiting_list
       where event_id = p_event_id and offered_at is not null);
$$;

-- Offers the place to the first entry not yet offered one, if a place is
-- genuinely free. Callers hold the per-event lock.
create or replace function registrations.offer_next(p_event_id uuid, p_capacity integer)
returns registrations.waiting_list
language plpgsql
set search_path = ''
as $$
declare
  v_offered registrations.waiting_list;
begin
  if registrations.places_claimed(p_event_id) < p_capacity then
    update registrations.waiting_list
    set offered_at = now()
    where id = (
      select id from registrations.waiting_list
      where event_id = p_event_id and offered_at is null
      order by created_at, id
      limit 1
    )
    returning * into v_offered;
  end if;
  return v_offered;
end;
$$;

-- S-50's register, now counting open offers as taken.
--   SP050 -- the event is full
--   23505 -- this Attendee already holds a place
create or replace function registrations.register(
  p_event_id    uuid,
  p_attendee_id uuid,
  p_capacity    integer
)
returns setof registrations.registrations
language plpgsql
set search_path = ''
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 50));

  if exists (
    select 1 from registrations.registrations
    where event_id = p_event_id and attendee_id = p_attendee_id
  ) then
    raise exception 'already registered' using errcode = '23505';
  end if;

  if registrations.places_claimed(p_event_id) >= p_capacity then
    raise exception 'event full' using errcode = 'SP050';
  end if;

  return query
    insert into registrations.registrations (event_id, attendee_id)
    values (p_event_id, p_attendee_id)
    returning *;
end;
$$;

-- S-53's withdraw, now offering the freed place instead of filling it.
--   SP053 -- this Attendee holds no place at this event
-- Returns {"withdrawn": <row>, "offered": <waiting-list row> | null}.
create or replace function registrations.withdraw(
  p_event_id    uuid,
  p_attendee_id uuid,
  p_capacity    integer
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_withdrawn registrations.registrations;
  v_offered   registrations.waiting_list;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 50));

  delete from registrations.registrations
  where event_id = p_event_id and attendee_id = p_attendee_id
  returning * into v_withdrawn;

  if v_withdrawn.id is null then
    raise exception 'not registered' using errcode = 'SP053';
  end if;

  v_offered := registrations.offer_next(p_event_id, p_capacity);

  return jsonb_build_object(
    'withdrawn', to_jsonb(v_withdrawn),
    'offered', case when v_offered.id is null then null else to_jsonb(v_offered) end
  );
end;
$$;

-- The invited Attendee takes the held place. No capacity check: the offer
-- already holds it.
--   SP055 -- this Attendee has no open offer for this event
create or replace function registrations.accept_offer(
  p_event_id    uuid,
  p_attendee_id uuid
)
returns setof registrations.registrations
language plpgsql
set search_path = ''
as $$
declare
  v_entry registrations.waiting_list;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 50));

  delete from registrations.waiting_list
  where event_id = p_event_id and attendee_id = p_attendee_id
    and offered_at is not null
  returning * into v_entry;

  if v_entry.id is null then
    raise exception 'no open offer' using errcode = 'SP055';
  end if;

  return query
    insert into registrations.registrations (event_id, attendee_id)
    values (p_event_id, p_attendee_id)
    returning *;
end;
$$;

-- The invited Attendee passes: they leave the waiting list and the place is
-- offered to the next in line.
--   SP055 -- this Attendee has no open offer for this event
-- Returns {"declined": <waiting-list row>, "offered": <waiting-list row> | null}.
create or replace function registrations.decline_offer(
  p_event_id    uuid,
  p_attendee_id uuid,
  p_capacity    integer
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_declined registrations.waiting_list;
  v_offered  registrations.waiting_list;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 50));

  delete from registrations.waiting_list
  where event_id = p_event_id and attendee_id = p_attendee_id
    and offered_at is not null
  returning * into v_declined;

  if v_declined.id is null then
    raise exception 'no open offer' using errcode = 'SP055';
  end if;

  v_offered := registrations.offer_next(p_event_id, p_capacity);

  return jsonb_build_object(
    'declined', to_jsonb(v_declined),
    'offered', case when v_offered.id is null then null else to_jsonb(v_offered) end
  );
end;
$$;

revoke all on function registrations.places_claimed(uuid) from public, anon, authenticated;
revoke all on function registrations.offer_next(uuid, integer) from public, anon, authenticated;
revoke all on function registrations.register(uuid, uuid, integer) from public, anon, authenticated;
revoke all on function registrations.withdraw(uuid, uuid, integer) from public, anon, authenticated;
revoke all on function registrations.accept_offer(uuid, uuid) from public, anon, authenticated;
revoke all on function registrations.decline_offer(uuid, uuid, integer) from public, anon, authenticated;
grant execute on function registrations.places_claimed(uuid) to service_role;
grant execute on function registrations.offer_next(uuid, integer) to service_role;
grant execute on function registrations.register(uuid, uuid, integer) to service_role;
grant execute on function registrations.withdraw(uuid, uuid, integer) to service_role;
grant execute on function registrations.accept_offer(uuid, uuid) to service_role;
grant execute on function registrations.decline_offer(uuid, uuid, integer) to service_role;

notify pgrst, 'reload schema';
-- END S-55 WAITING LIST OFFERS

-- BEGIN S-58 RECORDED WITHDRAWALS
-- Existing installations: run through END S-58 in BOTH dev and test, after
-- the S-55 block. Safe to run repeatedly and data-preserving.
--
-- A withdrawal used to leave no trace: the place row is deleted. The
-- Attendee's dashboard now lists the event as "Withdrawn", so giving up a
-- place (withdraw) or an offered one (decline_offer) records it here, in the
-- same locked step. One row per Attendee per event; withdrawing again from
-- the same event moves its withdrawn_at forward.

create table if not exists registrations.withdrawals (
  id           uuid primary key default gen_random_uuid(),
  event_id     uuid not null,
  attendee_id  uuid not null,
  withdrawn_at timestamptz not null default now(),

  constraint withdrawals_one_per_attendee unique (event_id, attendee_id)
);

create index if not exists withdrawals_attendee_idx
  on registrations.withdrawals (attendee_id, withdrawn_at);

grant all on registrations.withdrawals to service_role;
alter table registrations.withdrawals enable row level security;

-- Records that this Attendee gave up their place at this event.
create or replace function registrations.record_withdrawal(
  p_event_id    uuid,
  p_attendee_id uuid
)
returns void
language sql
set search_path = ''
as $$
  insert into registrations.withdrawals (event_id, attendee_id)
  values (p_event_id, p_attendee_id)
  on conflict (event_id, attendee_id) do update set withdrawn_at = now();
$$;

-- S-55's withdraw, now also recording the withdrawal.
--   SP053 -- this Attendee holds no place at this event
-- Returns {"withdrawn": <row>, "offered": <waiting-list row> | null}.
create or replace function registrations.withdraw(
  p_event_id    uuid,
  p_attendee_id uuid,
  p_capacity    integer
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_withdrawn registrations.registrations;
  v_offered   registrations.waiting_list;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 50));

  delete from registrations.registrations
  where event_id = p_event_id and attendee_id = p_attendee_id
  returning * into v_withdrawn;

  if v_withdrawn.id is null then
    raise exception 'not registered' using errcode = 'SP053';
  end if;

  perform registrations.record_withdrawal(p_event_id, p_attendee_id);
  v_offered := registrations.offer_next(p_event_id, p_capacity);

  return jsonb_build_object(
    'withdrawn', to_jsonb(v_withdrawn),
    'offered', case when v_offered.id is null then null else to_jsonb(v_offered) end
  );
end;
$$;

-- S-55's decline_offer, now also recording the withdrawal.
--   SP055 -- this Attendee has no open offer for this event
-- Returns {"declined": <waiting-list row>, "offered": <waiting-list row> | null}.
create or replace function registrations.decline_offer(
  p_event_id    uuid,
  p_attendee_id uuid,
  p_capacity    integer
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_declined registrations.waiting_list;
  v_offered  registrations.waiting_list;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 50));

  delete from registrations.waiting_list
  where event_id = p_event_id and attendee_id = p_attendee_id
    and offered_at is not null
  returning * into v_declined;

  if v_declined.id is null then
    raise exception 'no open offer' using errcode = 'SP055';
  end if;

  perform registrations.record_withdrawal(p_event_id, p_attendee_id);
  v_offered := registrations.offer_next(p_event_id, p_capacity);

  return jsonb_build_object(
    'declined', to_jsonb(v_declined),
    'offered', case when v_offered.id is null then null else to_jsonb(v_offered) end
  );
end;
$$;

revoke all on function registrations.record_withdrawal(uuid, uuid) from public, anon, authenticated;
revoke all on function registrations.withdraw(uuid, uuid, integer) from public, anon, authenticated;
revoke all on function registrations.decline_offer(uuid, uuid, integer) from public, anon, authenticated;
grant execute on function registrations.record_withdrawal(uuid, uuid) to service_role;
grant execute on function registrations.withdraw(uuid, uuid, integer) to service_role;
grant execute on function registrations.decline_offer(uuid, uuid, integer) to service_role;

notify pgrst, 'reload schema';
-- END S-58 RECORDED WITHDRAWALS
