-- ============================================================================
-- One-time migration — fix the Amazon week_start off-by-7-days bug
-- Run ONCE in Supabase → SQL Editor AFTER deploying v4.91.
-- ============================================================================
-- Bug history: before v4.91, the SKU Economics parser used ISO 8601 week
-- semantics (Sunday = day 7 = LAST day of its week). Amazon's reports use
-- Sun-Sat weeks (Sunday = day 1 = FIRST day). The parser mapped every
-- Amazon Sun-Sat week to the Monday of the ISO week ENDING on that
-- Sunday — six days BEFORE the actual week's start. Result: every Amazon
-- row in sku_economics and sales_weekly is keyed by a week_start that is
-- exactly 7 days earlier than the actual reporting week.
--
-- Example: Amazon's "Aug 3-9, 2025 (Sun-Sat)" file landed at
-- week_start = '2025-07-28' instead of the intuitive '2025-08-04'.
-- ============================================================================
-- PREVIEW FIRST. Sanity-check the row counts + date ranges before running
-- the UPDATE so you know what's about to move.
-- ============================================================================

-- Step 1 — How many rows are affected, and what date range:
select
  'sku_economics' as table_name,
  count(*) as rows,
  min(week_start) as earliest,
  max(week_start) as latest
from sku_economics
union all
select
  'sales_weekly amazon_us/ca',
  count(*),
  min(week_start),
  max(week_start)
from sales_weekly
where channel in ('amazon_us', 'amazon_ca');

-- Step 2 — Spot-check a specific ASIN (replace the asin literal with one of
-- yours). week_start should currently be the Monday 6 days BEFORE the
-- Sunday of your actual file. After the migration it'll be the Monday
-- of the Mon-Sun week overlapping Amazon's Sun-Sat week.
-- select asin, region, week_start, net_units_sold
-- from sku_economics
-- where asin = 'B0XXXXXXXX'
-- order by week_start;

-- ============================================================================
-- Step 3 — THE FIX. Shifts every Amazon-channel row forward by 7 days.
-- Safe to run because every row moves by the same amount, so the unique
-- keys (asin, region, week_start) and (channel, asin, coalesce(shopify_sku,''),
-- week_start) stay collision-free.
--
-- Wrapped in a transaction so you can roll back if the post-update
-- spot-check looks wrong.
-- ============================================================================

begin;

update sku_economics
  set week_start = week_start + interval '7 days';

update sales_weekly
  set week_start = week_start + interval '7 days'
  where channel in ('amazon_us', 'amazon_ca');

-- Step 4 — Verify before committing. Re-run Step 1 / Step 2 spot-checks
-- inside this transaction (Supabase SQL Editor keeps the transaction open
-- between sequential statements within the same query block).
-- If everything looks right:
commit;
-- If something looks wrong, run instead:
-- rollback;

-- ============================================================================
-- Notes
-- ----------------------------------------------------------------------------
-- • This migration ONLY touches Amazon channels. Shopify and Chewy uploaders
--   use independent parsers and may or may not have the same bug — if you
--   suspect they do, run separate audits first.
-- • After running, re-open the dashboard with v4.91 deployed. New Amazon
--   uploads will land at the correct Monday automatically.
-- • Audit log: this UPDATE doesn't write to audit_log (it's a one-shot
--   schema-level migration). Note the migration date for your records.
-- ============================================================================
