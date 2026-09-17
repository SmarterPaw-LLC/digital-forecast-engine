-- v8.44 — Growth Model tables (Amazon P&L → Growth Model sub-view).
-- Two tables feed the per-SKU unit-sales growth simulator:
--   1. amazon_query_performance_asin — Amazon Brand Analytics "Search Query
--      Performance (ASIN view)". Per-ASIN × per-query × per-month share-of-voice
--      + funnel metrics (impressions/clicks/cart adds/purchases and share %).
--      Market-side data — tells us total keyword volume + our current share.
--   2. amazon_sp_search_term — Amazon Ads Sponsored Products "Search Term Report".
--      Actual per-keyword CPC / spend / attributed sales for our advertised
--      SKUs. Ads-side data — tells us what we're actually paying to get share.
-- The Growth Model joins the two on (asin, month, keyword) to model the
-- keyword-level ad spend needed to hit a target monthly unit count.
--
-- Both tables are monthly grain, per-ASIN, per-query. RLS enabled + authenticated
-- policy + anon revoke (v6.47 hard rule). Idempotent — safe to re-run.

-- ============================================================================
-- 1. amazon_query_performance_asin — Brand Analytics SQP (ASIN view)
-- ============================================================================
-- Source: Seller Central → Brand Analytics → Search Query Performance →
-- ASIN view → Monthly. CSV headers vary; parser resolves via alias lookup.
-- Header row 1 encodes the ASIN + year + month; subsequent rows are per-query.

create table if not exists amazon_query_performance_asin (
  id                             bigserial primary key,
  asin                           text not null,
  master_id                      text references products(master_id) on delete cascade,
  region                         text not null default 'US',
  reporting_month                text not null,           -- 'YYYY-MM'
  reporting_date                 date not null,           -- period end from source
  search_query                   text not null,
  search_query_score             integer,
  search_query_volume            integer,

  impressions_total_count        bigint,
  impressions_asin_count         bigint,
  impressions_asin_share_pct     numeric(7,3),

  clicks_total_count             bigint,
  clicks_rate_pct                numeric(10,3),
  clicks_asin_count              bigint,
  clicks_asin_share_pct          numeric(7,3),
  clicks_price_median            numeric(10,2),
  clicks_asin_price_median       numeric(10,2),
  clicks_same_day_shipping       bigint,
  clicks_1d_shipping             bigint,
  clicks_2d_shipping             bigint,

  cart_adds_total_count          bigint,
  cart_adds_rate_pct             numeric(10,3),
  cart_adds_asin_count           bigint,
  cart_adds_asin_share_pct       numeric(7,3),
  cart_adds_price_median         numeric(10,2),
  cart_adds_asin_price_median    numeric(10,2),
  cart_adds_same_day_shipping    bigint,
  cart_adds_1d_shipping          bigint,
  cart_adds_2d_shipping          bigint,

  purchases_total_count          bigint,
  purchases_rate_pct             numeric(10,3),
  purchases_asin_count           bigint,
  purchases_asin_share_pct       numeric(7,3),
  purchases_price_median         numeric(10,2),
  purchases_asin_price_median    numeric(10,2),
  purchases_same_day_shipping    bigint,
  purchases_1d_shipping          bigint,
  purchases_2d_shipping          bigint,

  uploaded_at                    timestamptz not null default now()
);

-- Plain-column unique index → upsert-safe by (asin, region, month, query).
-- Parser still writes via DELETE+INSERT scoped to (asin, region, month) for
-- consistency with sales_weekly convention (Architecture Rule #5).
create unique index if not exists amazon_query_performance_asin_uniq
  on amazon_query_performance_asin (asin, region, reporting_month, search_query);

create index if not exists amazon_query_performance_asin_master_idx
  on amazon_query_performance_asin (master_id) where master_id is not null;

create index if not exists amazon_query_performance_asin_month_idx
  on amazon_query_performance_asin (reporting_month, region);

alter table amazon_query_performance_asin enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname='public'
      and tablename='amazon_query_performance_asin'
      and policyname='amazon_query_performance_asin_authenticated'
  ) then
    create policy amazon_query_performance_asin_authenticated
      on amazon_query_performance_asin for all to authenticated
      using (true) with check (true);
  end if;
end $$;

grant select, insert, update, delete on table amazon_query_performance_asin to authenticated;
grant usage, select on sequence amazon_query_performance_asin_id_seq to authenticated;
revoke all on table amazon_query_performance_asin from anon;

comment on table amazon_query_performance_asin is
  'v8.44 Amazon Brand Analytics Search Query Performance (ASIN view). Per-ASIN/per-query/per-month share-of-voice + funnel metrics. Feeds Growth Model on Amazon P&L.';


-- ============================================================================
-- 2. amazon_sp_search_term — Sponsored Products Search Term Report
-- ============================================================================
-- Source: advertising.amazon.com → Reports → Create report → Sponsored Products
-- → Search Term Report → Monthly rollup. Parser is alias-tolerant for column
-- header variants because Amazon has renamed these fields multiple times.

create table if not exists amazon_sp_search_term (
  id                             bigserial primary key,
  asin                           text,                    -- advertised ASIN; may be null for pure auto-target rows
  master_id                      text references products(master_id) on delete cascade,
  region                         text not null default 'US',
  reporting_month                text not null,           -- 'YYYY-MM'
  reporting_date                 date,                    -- period end
  campaign_name                  text,
  ad_group_name                  text,
  targeting                      text,                    -- keyword targeting text ('cat nip spray', 'broad-<term>', etc.)
  match_type                     text,                    -- BROAD | PHRASE | EXACT | AUTO
  customer_search_term           text not null,           -- actual query that triggered the ad
  impressions                    bigint default 0,
  clicks                         bigint default 0,
  ctr_pct                        numeric(10,3),
  cpc                            numeric(10,4),
  spend                          numeric(12,2) default 0,
  sales_7d                       numeric(12,2) default 0,  -- 7-day attributed sales
  orders_7d                      bigint default 0,
  units_7d                       bigint default 0,
  acos_pct                       numeric(10,3),
  roas                           numeric(10,4),
  cvr_pct                        numeric(10,3),
  currency                       text default 'USD',
  uploaded_at                    timestamptz not null default now()
);

-- Functional unique index (uses coalesce for nullable disambiguators). Writes
-- MUST use DELETE+INSERT per Architecture Rule #5 — upsert with plain-column
-- onConflict silently degrades against functional indexes.
create unique index if not exists amazon_sp_search_term_uniq
  on amazon_sp_search_term (
    coalesce(asin,''),
    region,
    reporting_month,
    customer_search_term,
    coalesce(match_type,''),
    coalesce(campaign_name,''),
    coalesce(ad_group_name,'')
  );

create index if not exists amazon_sp_search_term_master_idx
  on amazon_sp_search_term (master_id) where master_id is not null;

create index if not exists amazon_sp_search_term_month_idx
  on amazon_sp_search_term (reporting_month, region);

create index if not exists amazon_sp_search_term_asin_month_idx
  on amazon_sp_search_term (asin, reporting_month) where asin is not null;

alter table amazon_sp_search_term enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname='public'
      and tablename='amazon_sp_search_term'
      and policyname='amazon_sp_search_term_authenticated'
  ) then
    create policy amazon_sp_search_term_authenticated
      on amazon_sp_search_term for all to authenticated
      using (true) with check (true);
  end if;
end $$;

grant select, insert, update, delete on table amazon_sp_search_term to authenticated;
grant usage, select on sequence amazon_sp_search_term_id_seq to authenticated;
revoke all on table amazon_sp_search_term from anon;

comment on table amazon_sp_search_term is
  'v8.44 Amazon Ads Sponsored Products Search Term Report. Per-keyword CPC/spend/attributed sales. Joins amazon_query_performance_asin on (asin, month, keyword) for Growth Model CPC calibration.';
