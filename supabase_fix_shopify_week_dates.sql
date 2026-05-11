-- ============================================================================
-- One-time migration — consolidate Shopify week_start values onto Mondays
-- Run ONCE in Supabase → SQL Editor AFTER deploying v4.92.
-- ============================================================================
-- Bug history: before v4.92, the Shopify daily-→-weekly aggregator used
-- `new Date(dayString)` for parsing the per-row Day column. JS interprets
-- ISO strings ("2025-08-04") as UTC midnight but reads getDay/getDate in
-- LOCAL time — so in non-UTC timezones the parser saw the "wrong" day,
-- aggregated rows under shifted week_start values, and the resulting key
-- depended on the CSV date format. Different uploads scattered rows
-- across multiple buggy week_starts (e.g. Mondays as 2025-07-29 Tue,
-- 2025-08-04 Mon, 2025-08-05 Tue — all for what should have been ONE
-- canonical week).
--
-- Fix: collapse every shopify row's week_start onto the Monday of its
-- Mon-Sun ISO week using Postgres `date_trunc('week', ...)` (ISO weeks,
-- Mon-Sun), then group + sum any rows that now share the same canonical
-- (channel, asin, shopify_sku, week_start) key.
-- ============================================================================
-- PREVIEW FIRST.
-- ============================================================================

-- Step 1 — How fragmented is the current data? Distinct day-of-week
-- distribution for shopify week_start values:
select extract(dow from week_start) as day_of_week,
       to_char(week_start, 'Day')   as day_name,
       count(*)                      as rows
  from sales_weekly
 where channel = 'shopify'
 group by 1, 2
 order by 1;

-- Step 2 — Spot-check a specific SKU. The same SKU likely has rows at
-- multiple non-Monday week_starts that should have been one Monday week.
-- Replace 'YOUR-SHOPIFY-SKU' with a real one.
-- select shopify_sku, week_start, units_ordered, revenue
--   from sales_weekly
--  where channel = 'shopify' and shopify_sku = 'YOUR-SHOPIFY-SKU'
--  order by week_start;

-- Step 3 — Preview the consolidated rows. Each (asin, shopify_sku) gets
-- one row per Mon-Sun week with units/revenue SUMMED across all the
-- buggy scattered week_starts that fell inside that week.
with consolidated as (
  select
    channel, asin, shopify_sku, region,
    date_trunc('week', week_start)::date as new_week_start,
    sum(units_ordered)     as units_ordered,
    sum(coalesce(revenue, 0)) as revenue
  from sales_weekly
  where channel = 'shopify'
  group by channel, asin, shopify_sku, region, date_trunc('week', week_start)::date
)
select count(*)                                  as consolidated_rows,
       min(new_week_start)                        as earliest_week,
       max(new_week_start)                        as latest_week,
       sum(units_ordered)                         as total_units
  from consolidated;

-- ============================================================================
-- Step 4 — THE FIX. Atomically: delete all shopify rows, then re-insert
-- consolidated ones. Wrapped in a transaction so a failed verify can be
-- rolled back.
-- ============================================================================

begin;

-- 4a — snapshot the consolidated view into a TEMP table
create temp table shopify_consolidated as
  select
    'shopify'::text  as channel,
    asin,
    shopify_sku,
    region,
    date_trunc('week', week_start)::date as week_start,
    sum(units_ordered)        as units_ordered,
    sum(coalesce(revenue, 0)) as revenue,
    -- Preserve a representative master_id (any of the source rows' master_id;
    -- they should all be the same per shopify_sku post-promotion).
    max(master_id)            as master_id
  from sales_weekly
  where channel = 'shopify'
  group by asin, shopify_sku, region, date_trunc('week', week_start)::date;

-- 4b — wipe the old shopify rows
delete from sales_weekly where channel = 'shopify';

-- 4c — insert the consolidated rows
insert into sales_weekly (channel, asin, shopify_sku, region, week_start, units_ordered, revenue, master_id)
  select channel, asin, shopify_sku, region, week_start, units_ordered, revenue, master_id
    from shopify_consolidated;

-- Step 5 — Verify before committing. Re-run Step 1 (DOW distribution) —
-- should now show only day_of_week = 1 (Monday). If everything looks right:
commit;
-- If something is off, run instead:
-- rollback;

-- ============================================================================
-- Notes
-- ----------------------------------------------------------------------------
-- • `date_trunc('week', ...)` uses ISO weeks (Mon-Sun), so every post-
--   migration week_start is a Monday. Matches the v4.92 parser's new
--   behavior for fresh uploads.
-- • Daily granularity is GONE — the original CSVs already had per-day
--   rows but the dashboard only stored weekly aggregates. This migration
--   re-buckets those weekly aggregates into the correct Mon-Sun week, but
--   if a daily row's original parse landed it in the "wrong" weekly
--   bucket (e.g. Sunday Aug 10 attributed to weekStart 2025-08-05 instead
--   of 2025-08-11), the per-day fidelity can't be reconstructed without
--   re-uploading the original daily CSV. For high-precision needs,
--   re-upload the daily files after deploying v4.92.
-- • If you have raw Shopify daily CSVs preserved (Settings → Audit Log →
--   filter to upload events), re-uploading them with v4.92 in place is
--   the cleanest path; it will produce correct weekly aggregates from
--   scratch (and the delete+insert path in the parser cleanly replaces
--   the existing rows).
-- ============================================================================
