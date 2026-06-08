-- ============================================================================
-- Inventory events — extra-stock drivers (v6.26)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v6.26.
-- ============================================================================
-- An "event" is a known demand spike that requires building extra stock ahead
-- of time — e.g. Amazon Prime Day. Each event specifies:
--
--   • when the event happens          (event_start / event_end — display only)
--   • when the extra need hits planning (drain_start — the date the additional
--                                        need enters the inventory-planning math)
--   • how much extra to build          (extra_days — extra DAYS OF SUPPLY, i.e.
--                                        extra_days × the product's daily velocity)
--   • who it applies to                (scope_type/scope_value: all | brand |
--                                        channel, PLUS hand-picked
--                                        include/exclude master_id lists)
--
-- Example (Amazon Prime Day 2026):
--   event_start 2026-06-23, event_end 2026-06-26, drain_start 2026-05-27,
--   extra_days 30, scope_type 'channel', scope_value 'amazon'.
--
-- The dashboard adds eventExtra = extra_days × velocity into the inventory
-- planning Need for any horizon that reaches drain_start, and badges the row.
--
-- Idempotent — IF NOT EXISTS guards + policy/grant guards.
-- ============================================================================

create table if not exists inventory_events (
  id                 bigint generated always as identity primary key,
  name               text not null,
  event_start        date,
  event_end          date,
  drain_start        date not null,
  extra_days         numeric not null default 30,
  scope_type         text not null default 'all',      -- 'all' | 'brand' | 'channel'
  scope_value        text,                              -- brand name OR 'amazon'|'shopify'|'chewy'
  include_master_ids jsonb not null default '[]'::jsonb,
  exclude_master_ids jsonb not null default '[]'::jsonb,
  active             boolean not null default true,
  created_at         timestamptz default now(),
  updated_at         timestamptz default now()
);

alter table inventory_events enable row level security;

-- authenticated full access (mirrors every other data table — see CLAUDE.md
-- "Setup notes — Supabase RLS + table GRANTs").
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'inventory_events'
      and policyname = 'inventory_events_authenticated_all'
  ) then
    create policy inventory_events_authenticated_all
      on inventory_events for all to authenticated
      using (true) with check (true);
  end if;
end $$;

grant select, insert, update, delete on table inventory_events to authenticated;

-- Verify:
--   select * from inventory_events order by drain_start;
