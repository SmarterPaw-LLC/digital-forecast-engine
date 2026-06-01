-- ============================================================================
-- Audit + dedupe sales_weekly across ALL channels (v5.97)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v5.97.
-- ============================================================================
-- WHY
-- ----
-- v5.96 deduped channel='shopify' rows after the user surfaced 3x duplication
-- in Fruit Sticks weekly totals. The root cause — upserts with plain-column
-- onConflict against sales_weekly's functional `coalesce(shopify_sku, '')`
-- unique index silently degrading to plain INSERT — also affected two other
-- code paths discovered in the v5.97 audit:
--
--   1. parseSalesWeekly (Amazon basic-sales upload, line 4163 pre-fix) —
--      affects rows written via the per-brand-per-region Amazon slots
--      (NOT the SKU Economics path; that one has always used DELETE+INSERT).
--   2. doRestore (backup restore, line 20092 pre-fix) — affects any
--      sales_weekly rows touched by a restore operation.
--
-- This SQL is broader than v5.96's. It audits + dedupes across ALL channels
-- using the EXACT same partition key as the unique index expression:
--   (channel, asin, coalesce(shopify_sku, ''), week_start)
--
-- so the dedupe matches whatever the index would have considered conflicts.
--
-- IDEMPOTENT — running this after v5.96 (Shopify-only) is safe: Shopify
-- duplicates are already gone; this finds nothing for those, only cleans
-- any Amazon / Chewy / EU duplicates that exist.
-- ============================================================================

begin;

-- Audit: how many duplicate groups per channel + the row counts?
-- ----------------------------------------------------------------------------
-- Run as a SELECT first (without the DELETE) to see what would be cleaned.
-- Uncomment to inspect before committing:
--
--   select channel,
--          count(*) - count(distinct (asin, coalesce(shopify_sku,''), week_start)) as dup_rows,
--          count(*) as total_rows,
--          count(distinct (asin, coalesce(shopify_sku,''), week_start)) as unique_keys
--   from sales_weekly
--   group by channel
--   order by dup_rows desc, channel;
--
--   select channel, asin, shopify_sku, week_start, count(*) as row_count,
--          min(uploaded_at) as first, max(uploaded_at) as last
--   from sales_weekly
--   group by channel, asin, shopify_sku, week_start
--   having count(*) > 1
--   order by row_count desc, channel, week_start
--   limit 100;

-- The dedupe. Partition key matches the actual functional unique index
-- expression: (channel, asin, coalesce(shopify_sku, ''), week_start).
-- Tie-break by uploaded_at desc (keep newest) then ctid desc (deterministic
-- for the rare same-microsecond case).
delete from sales_weekly
 using (
   select ctid,
          row_number() over (
            partition by channel, asin, coalesce(shopify_sku, ''), week_start
            order by uploaded_at desc nulls last, ctid desc
          ) as rn
   from sales_weekly
 ) ranked
 where sales_weekly.ctid = ranked.ctid
   and ranked.rn > 1;

-- Verify: every (channel, asin, coalesce(shopify_sku,''), week_start) tuple
-- should now appear exactly once.
-- ----------------------------------------------------------------------------
--   select channel, asin, shopify_sku, week_start, count(*)
--   from sales_weekly
--   group by channel, asin, shopify_sku, week_start
--   having count(*) > 1;
--   -- expected: zero rows returned

commit;

-- ============================================================================
-- After commit:
--   1. Deploy index.html v5.97 (parseSalesWeekly Amazon path + doRestore both
--      now use DELETE+INSERT — matches parseShopifySales + parseSkuEconomics).
--   2. Architecture Rule #5 is now enforced uniformly across every code path
--      that writes to sales_weekly.
--   3. The dashboard P&L totals will reflect correctly. If any Amazon weeks
--      look different than expected, that's the dedupe taking effect (same
--      "keep most recent uploaded_at" rule that affected Shopify weeks).
-- ============================================================================
