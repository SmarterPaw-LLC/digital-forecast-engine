-- ============================================================================
-- One-time migration — fix the Amazon week_start off-by-7-days bug
-- Run ONCE in Supabase → SQL Editor AFTER deploying v4.91+.
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
--
-- TWO-PASS PATTERN — required because Postgres checks the unique constraint
-- (asin, region, week_start) per-row during UPDATE. A naive single-statement
-- `set week_start = week_start + interval '7 days'` triggers a transient
-- collision when Row A's new key happens to equal Row B's old key (which
-- is about to shift too, but Postgres hasn't gotten there yet). Solution:
-- (1) shift every row +10000 days into the future (no collisions because
-- nothing exists 27 years out), then (2) shift back by 9993 days for a
-- net +7-day delta. After both passes, every row is at its corrected key
-- and the unique constraint is satisfied.
-- ============================================================================
-- PREVIEW FIRST.
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

-- Step 2 — Spot-check a specific ASIN to see what's there before:
-- select asin, region, week_start, net_units_sold
-- from sku_economics
-- where asin = 'B0XXXXXXXX'
-- order by week_start;

-- ============================================================================
-- Step 3 — THE FIX. Two-pass shift to dodge transient unique violations.
-- Wrapped in a transaction so you can roll back if the post-update
-- spot-check looks wrong.
-- ============================================================================

begin;

-- Pass 1: shift every row 10000 days (~27 years) into the future.
-- Uniqueness preserved because every row moves by the same amount, and no
-- existing row has a week_start ~27 years in the future to collide with.
update sku_economics
  set week_start = week_start + 10000;

update sales_weekly
  set week_start = week_start + 10000
  where channel in ('amazon_us', 'amazon_ca');

-- Pass 2: shift back 9993 days. Net delta from original = +7 days.
-- Again uniqueness preserved because every row moves by the same amount.
update sku_economics
  set week_start = week_start - 9993;

update sales_weekly
  set week_start = week_start - 9993
  where channel in ('amazon_us', 'amazon_ca');

-- Step 4 — Verify. Re-run Step 1 (date range should be 7 days later than
-- before) and Step 2 (the spot-checked ASIN's weeks should now read as
-- Mondays of the Mon-Sun weeks overlapping Amazon's Sun-Sat reporting weeks).
-- If everything looks right:
commit;
-- If something looks wrong:
-- rollback;

-- ============================================================================
-- Notes
-- ----------------------------------------------------------------------------
-- • Net effect: every (asin, region, week_start) key in sku_economics and
--   every Amazon (channel, asin, week_start) key in sales_weekly is +7 days.
-- • Relative ordering of rows is preserved — your time series stays intact;
--   only the calendar label on each week shifts forward by one week.
-- • This does NOT touch shopify or chewy rows. Shopify has its own date
--   bug — see supabase_fix_shopify_week_dates.sql.
-- • After running, re-open the dashboard with v4.91+ deployed. New Amazon
--   uploads will land at the correct Monday automatically.
-- ============================================================================
