-- v8.45 — Extend amazon_query_performance_asin to also hold Brand View rows.
-- Same funnel metrics (impressions/clicks/cart_adds/purchases + count + share %),
-- but the identity is the brand ("Meowijuana") rather than a specific ASIN.
-- Adds:
--   view_type — 'asin' | 'brand' (which view the row came from)
--   brand     — brand name, populated on Brand View rows
--
-- The existing impressions_*_count / impressions_*_share_pct columns hold
-- WHICHEVER identity's count + share the source file reports (ASIN's or
-- brand's) — column semantics adjust based on view_type. The parser writes
-- both formats into the same numeric columns, so downstream analytics reads
-- one shape.
--
-- Idempotent — safe to re-run.

alter table amazon_query_performance_asin
  add column if not exists view_type text not null default 'asin' check (view_type in ('asin', 'brand')),
  add column if not exists brand text;

-- Existing rows are ASIN view (backfill default already covers it).

-- Unique index needs to distinguish (asin, month, query) rows from (brand,
-- month, query) rows — the ASIN can be NULL on brand rows and brand can be
-- NULL on ASIN rows, and the search_query overlaps. Drop the old plain
-- unique index and replace with one that includes coalesce fallbacks so
-- both view types coexist without collision.
drop index if exists amazon_query_performance_asin_uniq;

create unique index if not exists amazon_query_performance_asin_uniq
  on amazon_query_performance_asin (
    view_type,
    coalesce(asin, ''),
    coalesce(brand, ''),
    region,
    reporting_month,
    search_query
  );

create index if not exists amazon_query_performance_asin_brand_idx
  on amazon_query_performance_asin (brand, reporting_month) where brand is not null;

comment on column amazon_query_performance_asin.view_type is
  'v8.45 which SQP view the row came from: asin (per-listing SoV) or brand (per-brand SoV)';
comment on column amazon_query_performance_asin.brand is
  'v8.45 brand name; populated when view_type=brand';
