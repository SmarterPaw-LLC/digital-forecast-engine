-- ============================================================================
-- Dedupe sales_weekly shopify rows (v5.96)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v5.96.
-- ============================================================================
-- WHY
-- ----
-- parseShopifySales (pre-v5.96) used Supabase's upsert with
-- `onConflict: 'channel,asin,shopify_sku,week_start'`. The actual unique
-- index on sales_weekly is
--   (channel, asin, coalesce(shopify_sku, ''), week_start)
-- — a FUNCTIONAL index with coalesce() on shopify_sku. Postgres's ON
-- CONFLICT requires the constraint expression to match EXACTLY; a plain-
-- column spec doesn't match the functional expression. So every Shopify
-- upload silently degraded from upsert to plain insert, appending duplicate
-- rows instead of replacing existing ones.
--
-- Architecture Rule #5 in CLAUDE.md called this out for Amazon
-- (parseSkuEconomics uses DELETE+INSERT to avoid the exact same problem) —
-- Shopify was missed when first wired up.
--
-- User diagnostic that surfaced this:
--   week_start  shopify_sku  units  revenue   uploaded_at
--   2026-04-27  CF130        3      $25.48    2026-05-11 21:15  ← first upload
--   2026-04-27  CF130        3      $25.48    2026-06-01 18:41  ← duplicate
--   2026-04-27  CF130        3      $25.48    2026-06-01 19:07  ← duplicate
--   (similar across every week)
--
-- WHAT THIS DOES
-- ---------------
-- For each (channel='shopify', shopify_sku, week_start) group, keep only
-- the row with the most recent uploaded_at and delete the rest. Targets
-- only channel='shopify' — Amazon rows are untouched (they were never
-- affected; parseSkuEconomics has always used DELETE+INSERT).
--
-- SAFETY
-- -------
-- • Transaction-wrapped. Run the preview query first to confirm the row
--   counts make sense before committing.
-- • Idempotent — running twice is a no-op (after first pass, no duplicate
--   groups exist).
-- • Tie-break: when multiple rows share the SAME uploaded_at (extremely
--   unlikely; would require two uploads in the same microsecond), ctid
--   provides a stable tiebreaker so the dedup is deterministic.
-- ============================================================================

begin;

-- Preview: how many duplicates exist per (shopify_sku, week_start)?
-- ----------------------------------------------------------------------------
-- Uncomment to inspect before committing:
--
--   select shopify_sku, week_start, count(*) as row_count,
--          min(uploaded_at) as first_upload, max(uploaded_at) as last_upload
--   from sales_weekly
--   where channel = 'shopify'
--   group by shopify_sku, week_start
--   having count(*) > 1
--   order by row_count desc, shopify_sku, week_start;

-- The dedupe itself. ctid is Postgres's physical row pointer — guaranteed
-- unique per row, doesn't require a primary key column on the table.
delete from sales_weekly
 using (
   select ctid,
          row_number() over (
            partition by channel, shopify_sku, week_start
            order by uploaded_at desc nulls last, ctid desc
          ) as rn
   from sales_weekly
   where channel = 'shopify'
 ) ranked
 where sales_weekly.ctid = ranked.ctid
   and ranked.rn > 1;

-- Verify post-dedupe: every (shopify_sku, week_start) should now have
-- exactly one row.
-- ----------------------------------------------------------------------------
--   select shopify_sku, week_start, count(*)
--   from sales_weekly
--   where channel = 'shopify'
--   group by shopify_sku, week_start
--   having count(*) > 1;
--   -- expected: zero rows returned

commit;

-- ============================================================================
-- After commit:
--   1. Deploy index.html v5.96 (parseShopifySales now uses DELETE+INSERT).
--   2. Future Shopify uploads will replace existing weeks cleanly, no more
--      duplicates accumulating.
--   3. The dashboard Shopify P&L should immediately reflect correct totals
--      (no more 3x inflation from dupe rows).
-- ============================================================================
