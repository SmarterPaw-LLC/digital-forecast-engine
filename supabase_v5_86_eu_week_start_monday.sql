-- ============================================================================
-- Shift sku_economics_eu.week_start from native-Sunday → Monday (v5.86)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v5.86.
-- ============================================================================
-- WHY
-- ----
-- v4.144 introduced sku_economics_eu and (intentionally at the time) kept
-- week_start on the native Sunday from Amazon's EU SKU Economics report. This
-- diverged from sku_economics (US/CA), which has always Monday-shifted via
-- dateToMondayLocal(). The two-convention setup quietly broke renderPnl's
-- date filter at any boundary that lands on a Monday — most visibly the
-- "Last 7 days" period when today is itself a Monday:
--
--   getPnlDateRange() → from = 'YYYY-MM-25' (Mon), to = 'YYYY-MM-01' (Mon)
--   US/CA week 5/24–5/30 stored at week_start = 2026-05-25 → PASSES filter
--   EU    week 5/24–5/30 stored at week_start = 2026-05-24 → FAILS filter
--
-- v5.86 brings sku_economics_eu in line with sku_economics. After this
-- migration, every period filter / week join / velocity rollup behaves the
-- same across US, CA, and EU/UK — no region-specific date math.
--
-- WHAT THIS DOES
-- ---------------
-- 1. Adds one day to every existing week_start in sku_economics_eu so each
--    row shifts from its native Sunday to the next Monday (the same Monday
--    its US/CA twin would have used had it gone through dateToMondayLocal).
-- 2. The unique key (asin, region, week_start) holds — every row shifts by
--    the same +1 day, so no collisions are introduced.
-- 3. sales_weekly EU rows are NOT touched here. parseEuSkuEconomics has
--    written sales_weekly with Monday week_starts since v4.144
--    (dateToMondayLocal(startD, true), line ~6757) — only sku_economics_eu
--    was on the Sunday convention.
--
-- SAFETY
-- -------
-- • Wrapped in a transaction. If anything looks off in the verify query
--   below, ROLLBACK before COMMIT.
-- • Idempotent guard: the WHERE clause uses a marker to skip already-Monday
--   rows in case this is run twice. (Sunday = extract(dow ...) = 0.)
-- • Run after deploying nothing — the app does NOT need to be down. New
--   uploads go through the updated v5.86 parser which writes Monday
--   directly. In-flight uploads during the migration window will at worst
--   produce a row that gets shifted twice — guarded against by the dow=0
--   check.
-- ============================================================================

begin;

-- Preview (read-only): how many rows will shift?
-- ----------------------------------------------------------------------------
-- Uncomment to inspect before committing:
--
--   select count(*) as rows_to_shift
--   from sku_economics_eu
--   where extract(dow from week_start) = 0;   -- 0 = Sunday
--
--   select region, week_start, count(*)
--   from sku_economics_eu
--   where extract(dow from week_start) = 0
--   group by region, week_start
--   order by week_start desc, region;

update sku_economics_eu
   set week_start = week_start + interval '1 day'
 where extract(dow from week_start) = 0;   -- only shift Sunday rows

-- Verify post-migration: every row should now be on a Monday.
-- ----------------------------------------------------------------------------
--   select extract(dow from week_start) as dow, count(*)
--   from sku_economics_eu
--   group by dow;
--   -- expected: dow=1, count=<all rows>

commit;

-- ============================================================================
-- After commit:
--   1. Deploy index.html v5.86 (parseEuSkuEconomics now writes Monday).
--   2. P&L "Last 7 days" with EU selected should now show data matching
--      US/CA — no off-by-one filtering.
--   3. Any saved P&L queries with custom date ranges are unaffected (they
--      use the same > / < operators that just started matching correctly).
-- ============================================================================
