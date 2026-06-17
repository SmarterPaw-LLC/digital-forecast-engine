-- ============================================================================
-- Walmart 1P — item # as product ID (v6.51, SUPERSEDES v6.50)
-- Run ONCE in Supabase → SQL Editor. Safe to run whether or not v6.50 ran.
-- ============================================================================
-- The updated "Ecom Sales" export now carries a STABLE walmart_item_number
-- (e.g. 678996643) + a full product_name. So instead of mapping the fragile
-- truncated item_name via a side table, we store the item # as a real product
-- identifier on products.walmart_item_id (like asin / shopify_sku / chewy_sku)
-- and match on it. product_name drives the fuzzy suggestion at import time.
--
-- This DROPS the v6.50 tables (walmart_item_map + walmart_sales_weekly) and
-- recreates walmart_sales_weekly with the new columns. Safe to drop: no real
-- Walmart data has been imported yet (Phase 1 was still in testing). After
-- this, re-import the new CSV via the 🛒 Walmart card.
--
-- ⚠ RLS enabled + authenticated-all policy + anon revoke (v6.47 lesson).
-- Idempotent.
-- ============================================================================

-- ── 0. Drop the v6.50 objects (obsolete) ────────────────────────────────────
drop table if exists walmart_item_map;
drop table if exists walmart_sales_weekly;

-- ── 1. Product ID field: the Walmart item number ────────────────────────────
alter table products add column if not exists walmart_item_id text;
create index if not exists products_walmart_item_id_idx
  on products (walmart_item_id) where walmart_item_id is not null;

-- ── 2. Sales rows (keyed on the stable item number) ─────────────────────────
create table walmart_sales_weekly (
  id                    bigint generated always as identity primary key,
  master_id             text,              -- resolved via products.walmart_item_id; null until mapped
  walmart_item_number   text,              -- stable Walmart item # (the match key)
  walmart_item_name     text,              -- truncated all-caps name (display)
  product_name          text,              -- full product name (display / fuzzy match source)
  vendor_number         text,
  item_description_2    text,              -- e.g. 'ONLINE ONLY'
  walmart_calendar_week integer not null,  -- YYYYWW (e.g. 202546)
  week_start            date not null,     -- Monday of that week (cross-channel alignment)
  units                 integer       default 0,   -- shipped_based_quantity (negative = returns)
  net_sales             numeric(12,2) default 0,    -- shipped_based_net_sales (can be negative)
  source                text default 'walmart',
  uploaded_at           timestamptz default now()
);

-- Plain-column unique index → upsert-safe; parser still DELETE+INSERTs (Rule #5).
-- Keyed on the stable item number. (Nulls are distinct in Postgres, so the rare
-- number-less fallback row never collides.)
create unique index if not exists walmart_sales_weekly_uniq
  on walmart_sales_weekly (walmart_item_number, walmart_calendar_week);
create index if not exists walmart_sales_weekly_master_idx
  on walmart_sales_weekly (master_id) where master_id is not null;
create index if not exists walmart_sales_weekly_week_idx
  on walmart_sales_weekly (week_start);

alter table walmart_sales_weekly enable row level security;
do $$
begin
  if not exists (select 1 from pg_policies where schemaname='public'
    and tablename='walmart_sales_weekly' and policyname='walmart_sales_weekly_authenticated_all') then
    create policy walmart_sales_weekly_authenticated_all
      on walmart_sales_weekly for all to authenticated using (true) with check (true);
  end if;
end $$;
grant select, insert, update, delete on table walmart_sales_weekly to authenticated;
revoke all on table walmart_sales_weekly from anon;

-- Verify:
--   select count(*), min(week_start), max(week_start) from walmart_sales_weekly;
--   select master_id, walmart_item_id, short_name from products where walmart_item_id is not null;
