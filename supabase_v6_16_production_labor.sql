-- ============================================================================
-- Add `production_labor` to product_cogs (v6.16)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v6.16.
-- ============================================================================
-- New building-block column that feeds BOTH amazon_cogs and dtc_cogs sums:
--
--   amazon_cogs = landed_cost + fulfillment_amazon + production_labor
--   dtc_cogs    = landed_cost + overhead_dtc + fulfillment_dtc
--                 + shipping_cost + production_labor
--
-- Treated identically to landed_cost / fulfillment_* / overhead_dtc by the
-- COGS page's auto-derive logic and bundle BOM auto-sum (shipping_cost
-- stays the lone "flat per bundle, not summed from components" exception).
--
-- Default null — the dashboard's sumOrNull helper treats null as "skip"
-- (matches existing building-block behavior), so unset rows don't get
-- their amazon_cogs / dtc_cogs clobbered to 0.
--
-- Idempotent — IF NOT EXISTS guard.
-- ============================================================================

alter table product_cogs
  add column if not exists production_labor numeric;

-- Verify:
--   select column_name, data_type from information_schema.columns
--   where table_name = 'product_cogs' order by ordinal_position;
