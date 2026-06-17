-- ============================================================================
-- Walmart 1P sales — table + name→product mapping (v6.50)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v6.50.
-- ============================================================================
-- SmarterPaw sells to Walmart as a 1P vendor (Retail Link). The "Ecom Sales"
-- export is weekly, one row per (item, walmart_calendar_week), with:
--   walmart_calendar_week (YYYYWW) · vendor_number · item_description_2
--   ("ONLINE ONLY") · item_name (TRUNCATED all-caps name — the only identifier;
--   NO ASIN/UPC/GTIN) · vendor_name · shipped_based_net_sales · shipped_based_qty.
--
-- Two tables:
--   1. walmart_sales_weekly — the sales rows (units + net sales per item-week).
--   2. walmart_item_map      — maps the fragile truncated item_name → master_id.
--      Separate table (not a products column) because Walmart truncates names
--      and they drift; a map table cleanly handles N names → 1 product and
--      keeps it off the heavily-used products flows. The importer writes here
--      once (fuzzy-suggested, user-confirmed); future uploads auto-match.
--
-- ⚠ RLS is enabled on BOTH tables here — do NOT skip it (see the v6.47 incident
--   where shopify_sales_daily shipped without RLS and got flagged publicly
--   accessible). authenticated-full-access policy mirrors every other table.
-- Idempotent — IF NOT EXISTS guards + policy/grant guards.
-- ============================================================================

-- ── 1. Sales rows ──────────────────────────────────────────────────────────
create table if not exists walmart_sales_weekly (
  id                    bigint generated always as identity primary key,
  master_id             text,              -- resolved via walmart_item_map; null until mapped
  walmart_item_name     text not null,     -- raw truncated name from the report (match key)
  vendor_number         text,
  item_description_2    text,              -- e.g. 'ONLINE ONLY'
  walmart_calendar_week integer not null,  -- YYYYWW (e.g. 202546)
  week_start            date not null,     -- Monday of that week (cross-channel alignment)
  units                 integer       default 0,   -- shipped_based_quantity (can be negative = returns)
  net_sales             numeric(12,2) default 0,    -- shipped_based_net_sales (can be negative)
  source                text default 'walmart',
  uploaded_at           timestamptz default now()
);

-- Plain-column unique index (no functional expression) → upsert-safe, but the
-- parser still uses DELETE+INSERT per Architecture Rule #5 as the safe default.
create unique index if not exists walmart_sales_weekly_uniq
  on walmart_sales_weekly (walmart_item_name, walmart_calendar_week);
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

-- ── 2. Name → product mapping ────────────────────────────────────────────────
create table if not exists walmart_item_map (
  walmart_item_name text primary key,      -- raw truncated name (one row per distinct Walmart name)
  master_id         text not null references products(master_id) on delete cascade,
  created_at        timestamptz default now(),
  updated_at        timestamptz default now()
);
create index if not exists walmart_item_map_master_idx on walmart_item_map (master_id);

alter table walmart_item_map enable row level security;
do $$
begin
  if not exists (select 1 from pg_policies where schemaname='public'
    and tablename='walmart_item_map' and policyname='walmart_item_map_authenticated_all') then
    create policy walmart_item_map_authenticated_all
      on walmart_item_map for all to authenticated using (true) with check (true);
  end if;
end $$;
grant select, insert, update, delete on table walmart_item_map to authenticated;
revoke all on table walmart_item_map from anon;

-- Verify:
--   select count(*), min(week_start), max(week_start) from walmart_sales_weekly;
--   select * from walmart_item_map order by walmart_item_name;
