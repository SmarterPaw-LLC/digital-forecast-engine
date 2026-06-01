-- ============================================================================
-- Pass B.2 final cutover — velocity_calculated view + sales_weekly cleanup
-- ============================================================================
-- VERIFIED against the user's existing view definition (`pg_get_viewdef`
-- output from 2026-06-01). My v6.1 first-draft was missing 7 columns —
-- this version preserves the full column set exactly, just adds the
-- UNION with shopify_sales_daily and switches `week_start` → `day` for the
-- date window math.
--
-- Original view (snapshot for rollback if needed):
--
--   SELECT master_id, region,
--       max(asin) AS asin,
--       max(shopify_sku) AS shopify_sku,
--       max(chewy_part_no) AS chewy_part_no,
--       round(sum(CASE WHEN week_start >= (CURRENT_DATE - '30 days'::interval)  THEN units_ordered ELSE 0 END)::numeric / 30::numeric,  4) AS v30,
--       round(sum(CASE WHEN week_start >= (CURRENT_DATE - '60 days'::interval)  THEN units_ordered ELSE 0 END)::numeric / 60::numeric,  4) AS v60,
--       round(sum(CASE WHEN week_start >= (CURRENT_DATE - '90 days'::interval)  THEN units_ordered ELSE 0 END)::numeric / 90::numeric,  4) AS v90,
--       round(sum(CASE WHEN week_start >= (CURRENT_DATE - '120 days'::interval) THEN units_ordered ELSE 0 END)::numeric / 120::numeric, 4) AS v120,
--       count(DISTINCT week_start)  AS weeks_of_data,
--       min(week_start)             AS data_from,
--       max(week_start)             AS data_to,
--       sum(units_ordered)          AS total_units,
--       max(uploaded_at)            AS last_uploaded
--   FROM sales_weekly
--   WHERE master_id IS NOT NULL
--   GROUP BY master_id, region;
--
-- Step 2 below replaces the FROM with a UNION CTE that pulls non-Shopify
-- rows from sales_weekly and Shopify rows from shopify_sales_daily. Every
-- output column is preserved with the same name + type + math.
-- ============================================================================

begin;

-- 2a. Rebuild `velocity_calculated` as a UNION over both sources.
create or replace view velocity_calculated as
with unified as (
  -- Amazon US/CA, Amazon EU markets, Chewy — from sales_weekly. Shopify
  -- channel excluded; its rows are deleted in step 2b below and going
  -- forward will only live in shopify_sales_daily.
  select
    master_id,
    region,
    asin,
    shopify_sku,
    chewy_part_no,
    week_start::date     as day,
    coalesce(units_ordered, 0) as units,
    uploaded_at
  from sales_weekly
  where master_id is not null
    and channel <> 'shopify'

  union all

  -- Shopify — from shopify_sales_daily (per-day grain). Region hardcoded
  -- to 'US' since Shopify isn't multi-region in this catalog. asin and
  -- chewy_part_no don't exist on this table, so NULL them out (the max()
  -- aggregate below picks the non-null value if any Amazon/Chewy row for
  -- the same master_id contributes one).
  select
    master_id,
    'US'::text           as region,
    null::text           as asin,
    shopify_sku,
    null::text           as chewy_part_no,
    day,
    coalesce(units_sold, 0) as units,
    uploaded_at
  from shopify_sales_daily
  where master_id is not null
)
select
  master_id,
  region,
  max(asin)          as asin,
  max(shopify_sku)   as shopify_sku,
  max(chewy_part_no) as chewy_part_no,
  round(sum(case when day >= (current_date - interval '30 days')  then units else 0 end)::numeric / 30::numeric,  4) as v30,
  round(sum(case when day >= (current_date - interval '60 days')  then units else 0 end)::numeric / 60::numeric,  4) as v60,
  round(sum(case when day >= (current_date - interval '90 days')  then units else 0 end)::numeric / 90::numeric,  4) as v90,
  round(sum(case when day >= (current_date - interval '120 days') then units else 0 end)::numeric / 120::numeric, 4) as v120,
  -- weeks_of_data: count distinct ISO weeks the unified stream covers.
  -- For sales_weekly rows day == week_start (a Monday), so date_trunc('week')
  -- yields that same Monday. For shopify_sales_daily rows day can be any
  -- date — date_trunc('week') rolls it back to that week's Monday. Both
  -- contribute consistently to a weeks-not-days count.
  count(distinct date_trunc('week', day)) as weeks_of_data,
  min(day)           as data_from,
  max(day)           as data_to,
  sum(units)         as total_units,
  max(uploaded_at)   as last_uploaded
from unified
group by master_id, region;

grant select on velocity_calculated to authenticated;

-- 2b. Delete legacy Shopify rows from sales_weekly. The new view excludes
-- them via the `channel <> 'shopify'` filter; the dashboard's
-- loadShopifyPnlTab + loadSalesAnalytics (v6.0 / v6.1) already source
-- Shopify exclusively from shopify_sales_daily. So nothing reads these
-- rows anymore — safe to delete.
delete from sales_weekly where channel = 'shopify';

-- ──────────────────────────────────────────────────────────────────────────
-- STEP 3 — Verify (run after commit)
-- ──────────────────────────────────────────────────────────────────────────
--
--   -- View returns rows for both Amazon (US/CA) AND Shopify-contributing
--   -- master_ids:
--   select region, count(*) from velocity_calculated group by region order by region;
--
--   -- Same shape check as your "before" snapshot — these should be
--   -- close to the pre-migration values (the underlying data is the same
--   -- post-dedupe, just sourced from a different table for Shopify):
--   select v.master_id, p.short_name, p.shopify_sku, v.region,
--          v.v30, v.v60, v.v90, v.v120, v.weeks_of_data
--   from velocity_calculated v
--   join products p on p.master_id = v.master_id
--   where p.shopify_sku is not null
--     and p.asin is null              -- Shopify-only, no Amazon
--     and v.v30 > 0
--   order by v.v30 desc
--   limit 10;
--
--   -- sales_weekly should have zero Shopify rows now:
--   select count(*) from sales_weekly where channel = 'shopify';  -- expect 0
--
-- ROLLBACK (if anything goes wrong):
--   Run the full original view definition from the comment block at top of
--   this file inside a CREATE OR REPLACE VIEW velocity_calculated AS ...
--   statement. That restores the pre-migration shape exactly.
-- ============================================================================

commit;
