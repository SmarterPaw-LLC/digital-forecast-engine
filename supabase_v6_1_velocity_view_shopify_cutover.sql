-- ============================================================================
-- Pass B.2 final cutover — velocity_calculated view + sales_weekly cleanup (v6.1)
-- ============================================================================
--
-- ⚠ READ THIS BEFORE RUNNING ⚠
-- ---------------------------------------------------------------------------
-- This migration replaces the `velocity_calculated` Postgres VIEW with a new
-- definition that UNIONs `sales_weekly` (non-shopify) + `shopify_sales_daily`,
-- then deletes the legacy `channel='shopify'` rows from `sales_weekly`.
--
-- The view replacement is the only piece I'm guessing on — I don't have
-- visibility into the CURRENT view's exact definition. Step 1 below dumps it
-- so you can compare. If the existing view has additional columns / different
-- math / different filtering than my replacement assumes, edit the new
-- CREATE OR REPLACE VIEW statement to match BEFORE committing this txn.
--
-- ──────────────────────────────────────────────────────────────────────────
-- STEP 1 — Dump the current view definition (RUN FIRST, READ-ONLY)
-- ──────────────────────────────────────────────────────────────────────────
-- Run this SELECT on its own (NOT inside the transaction below). Copy the
-- output somewhere safe — it's your rollback if anything breaks.
--
--   select pg_get_viewdef('velocity_calculated', true);
--
-- The output should be a SELECT statement aggregating sales_weekly into v30,
-- v60, v90, v120 buckets. My replacement adds shopify_sales_daily as a second
-- source via UNION ALL. Make sure my version returns the SAME columns + types
-- the original did. The dashboard's hot paths read:
--   • master_id, region, v30, v60, v90, v120 (line ~4192)
--   • + weeks_of_data (referenced in the saved Velocity SQL at ~10635)
--
-- ──────────────────────────────────────────────────────────────────────────
-- STEP 2 — Apply the cutover (transaction-wrapped)
-- ──────────────────────────────────────────────────────────────────────────

begin;

-- 2a. New `velocity_calculated` view — UNIONs sales_weekly (non-shopify)
--     + shopify_sales_daily into a unified per-day stream, then aggregates
--     into the v30/v60/v90/v120 buckets per (master_id, region).
--
--     Shopify rows: region hardcoded to 'US' (Shopify isn't multi-region in
--     this catalog). Day is the bucket date directly.
--
--     Amazon/Chewy/EU rows: week_start cast to day. A weekly row of 100
--     units that started on day D counts the full 100 toward any window
--     where day >= D. This matches the pre-v6.1 view behavior (weekly bucket
--     attributed to its start date).
--
--     `weeks_of_data` is computed as count of distinct ISO weeks the unified
--     stream covers — survives the granularity mix because date_trunc('week')
--     buckets both daily and weekly rows correctly.
create or replace view velocity_calculated as
with unified as (
  select
    master_id,
    region,
    week_start::date as day,
    coalesce(units_ordered, 0) as units
  from sales_weekly
  where master_id is not null
    and channel <> 'shopify'

  union all

  select
    master_id,
    'US'::text as region,
    day,
    coalesce(units_sold, 0) as units
  from shopify_sales_daily
  where master_id is not null
)
select
  master_id,
  region,
  coalesce(sum(units) filter (where day >= current_date - interval '30 days')  / 30.0,  0)::numeric as v30,
  coalesce(sum(units) filter (where day >= current_date - interval '60 days')  / 60.0,  0)::numeric as v60,
  coalesce(sum(units) filter (where day >= current_date - interval '90 days')  / 90.0,  0)::numeric as v90,
  coalesce(sum(units) filter (where day >= current_date - interval '120 days') / 120.0, 0)::numeric as v120,
  count(distinct date_trunc('week', day))::integer as weeks_of_data
from unified
group by master_id, region;

grant select on velocity_calculated to authenticated;

-- 2b. Delete legacy Shopify rows from sales_weekly. The dashboard's
--     loadSalesAnalytics (v6.1) and loadShopifyPnlTab (v6.0) both source
--     Shopify exclusively from `shopify_sales_daily` now. The view above
--     also excludes sales_weekly.channel='shopify'. So these rows aren't
--     read by anything — safe to delete.
delete from sales_weekly where channel = 'shopify';

-- ──────────────────────────────────────────────────────────────────────────
-- STEP 3 — Verify (run after commit)
-- ──────────────────────────────────────────────────────────────────────────
-- Quick sanity checks:
--
--   -- View returns rows for both Amazon (region='US' or 'CA') AND Shopify-
--   -- contributing master_ids:
--   select region, count(*) from velocity_calculated group by region;
--
--   -- Shopify-bearing SKUs should have non-zero v30 if they sold recently:
--   select v.master_id, p.short_name, v.region, v.v30, v.v60, v.v90, v.v120
--   from velocity_calculated v
--   join products p on p.master_id = v.master_id
--   where p.shopify_sku is not null
--   order by v.v30 desc limit 20;
--
--   -- sales_weekly should have zero Shopify rows:
--   select count(*) from sales_weekly where channel = 'shopify';
--   -- expected: 0
--
-- If the Forecast tab or Inventory Planning shows blank velocity after this
-- runs, the view's column shape is the most likely culprit — paste the
-- output of `pg_get_viewdef` above and we can fix it.
-- ============================================================================

commit;
