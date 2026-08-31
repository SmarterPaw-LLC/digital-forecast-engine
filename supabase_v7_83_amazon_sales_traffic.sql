-- v7.83 — Amazon Business Reports: Detail Page Sales and Traffic by Child Item.
-- Two tables:
--   1. amazon_sales_traffic  — one row per (asin, region, week_start) — Sun→Sat weekly.
--      Direct join to sku_economics + amazon_ad_spend on (asin, region, week_start).
--   2. amazon_sales_traffic_snapshot — one row per (asin, region, period_start, period_end)
--      Arbitrary date ranges (YTD, QTD, monthly). Used for backfill + portfolio-level
--      analysis when weekly resolution isn't needed.
--
-- Uploader routes based on period length: exactly 7 days Sun-Sat → weekly table;
-- anything else → snapshot table. Same CSV format for both.
--
-- Data source: Seller Central → Reports → Business Reports → By ASIN →
-- Detail Page Sales and Traffic by Child Item. Per-marketplace (US, CA, UK,
-- DE, FR, IT, ES, NL, MX, AU, JP — same 11-option region set as SKU Economics).
--
-- Consumer + B2B columns are both captured. Only consumer surfaced on the
-- Amazon P&L page for now (v7.83); B2B available in the DB for future work.

-- ══════════════════════════════════════════════════════════════════════════
-- 1. WEEKLY TABLE
-- ══════════════════════════════════════════════════════════════════════════

create table if not exists amazon_sales_traffic (
  id                    bigserial primary key,
  master_id             text references products(master_id) on delete cascade,
  asin                  text not null,
  parent_asin           text,
  region                text not null,
  week_start            date not null,          -- Monday (matches sku_economics)
  title                 text,
  -- Consumer metrics
  sessions              integer not null default 0,
  page_views            integer not null default 0,
  buy_box_pct           numeric(6,3),           -- 0-100 (Featured Offer %)
  units_ordered         integer not null default 0,
  unit_session_pct      numeric(7,4),           -- 0-100 (per-ASIN conversion)
  ordered_sales         numeric(14,2) not null default 0,
  total_order_items     integer not null default 0,
  -- B2B metrics (Amazon Business)
  sessions_b2b          integer not null default 0,
  page_views_b2b        integer not null default 0,
  buy_box_pct_b2b       numeric(6,3),
  units_ordered_b2b     integer not null default 0,
  unit_session_pct_b2b  numeric(7,4),
  ordered_sales_b2b     numeric(14,2) not null default 0,
  total_order_items_b2b integer not null default 0,
  uploaded_at           timestamptz not null default now()
);

-- One row per (asin, region, week) — plain-column unique index (no functional
-- coalesce), so PostgREST onConflict works cleanly with plain upsert if needed.
-- Parser still uses DELETE+INSERT per Architecture Rule #5.
create unique index if not exists amazon_sales_traffic_uniq
  on amazon_sales_traffic (asin, region, week_start);

create index if not exists amazon_sales_traffic_master_idx
  on amazon_sales_traffic (master_id);
create index if not exists amazon_sales_traffic_week_idx
  on amazon_sales_traffic (week_start);
create index if not exists amazon_sales_traffic_region_idx
  on amazon_sales_traffic (region);

-- RLS + grants (v6.47 hard rule)
alter table amazon_sales_traffic enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'amazon_sales_traffic'
      and policyname = 'amazon_sales_traffic_authenticated'
  ) then
    create policy "amazon_sales_traffic_authenticated"
      on amazon_sales_traffic
      for all
      to authenticated
      using (true)
      with check (true);
  end if;
end $$;

grant select, insert, update, delete on table amazon_sales_traffic to authenticated;
grant usage, select on sequence amazon_sales_traffic_id_seq to authenticated;
revoke all on table amazon_sales_traffic from anon;

comment on table amazon_sales_traffic is
  'Amazon Detail Page Sales and Traffic (by Child ASIN), weekly Sun-Sat. Feeds the Amazon P&L page''s conversion / sessions columns and unlocks per-ASIN ad-spend analysis when joined with sku_economics + amazon_ad_spend on (asin, region, week_start). v7.83.';
comment on column amazon_sales_traffic.unit_session_pct is
  'Unit Session % = units ordered / sessions × 100. Per-ASIN conversion rate. THE primary signal for ad-spend decisions.';
comment on column amazon_sales_traffic.buy_box_pct is
  'Featured Offer (Buy Box) %. When below 100%, some traffic sees a competitor''s offer as featured — real ceiling on conversion regardless of PDP quality.';

-- ══════════════════════════════════════════════════════════════════════════
-- 2. SNAPSHOT TABLE (arbitrary date ranges — YTD, QTD, monthly backfill)
-- ══════════════════════════════════════════════════════════════════════════

create table if not exists amazon_sales_traffic_snapshot (
  id                    bigserial primary key,
  master_id             text references products(master_id) on delete cascade,
  asin                  text not null,
  parent_asin           text,
  region                text not null,
  period_start          date not null,
  period_end            date not null,
  title                 text,
  -- Consumer metrics
  sessions              integer not null default 0,
  page_views            integer not null default 0,
  buy_box_pct           numeric(6,3),
  units_ordered         integer not null default 0,
  unit_session_pct      numeric(7,4),
  ordered_sales         numeric(14,2) not null default 0,
  total_order_items     integer not null default 0,
  -- B2B metrics
  sessions_b2b          integer not null default 0,
  page_views_b2b        integer not null default 0,
  buy_box_pct_b2b       numeric(6,3),
  units_ordered_b2b     integer not null default 0,
  unit_session_pct_b2b  numeric(7,4),
  ordered_sales_b2b     numeric(14,2) not null default 0,
  total_order_items_b2b integer not null default 0,
  uploaded_at           timestamptz not null default now(),
  check (period_end >= period_start)
);

create unique index if not exists amazon_sales_traffic_snapshot_uniq
  on amazon_sales_traffic_snapshot (asin, region, period_start, period_end);

create index if not exists amazon_sales_traffic_snapshot_master_idx
  on amazon_sales_traffic_snapshot (master_id);
create index if not exists amazon_sales_traffic_snapshot_period_idx
  on amazon_sales_traffic_snapshot (period_start, period_end);
create index if not exists amazon_sales_traffic_snapshot_region_idx
  on amazon_sales_traffic_snapshot (region);

alter table amazon_sales_traffic_snapshot enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'amazon_sales_traffic_snapshot'
      and policyname = 'amazon_sales_traffic_snapshot_authenticated'
  ) then
    create policy "amazon_sales_traffic_snapshot_authenticated"
      on amazon_sales_traffic_snapshot
      for all
      to authenticated
      using (true)
      with check (true);
  end if;
end $$;

grant select, insert, update, delete on table amazon_sales_traffic_snapshot to authenticated;
grant usage, select on sequence amazon_sales_traffic_snapshot_id_seq to authenticated;
revoke all on table amazon_sales_traffic_snapshot from anon;

comment on table amazon_sales_traffic_snapshot is
  'Amazon Detail Page Sales and Traffic — arbitrary-period snapshots (YTD, QTD, monthly, custom range). Used for portfolio-level analysis and backfilling before weekly cadence begins. v7.83.';
