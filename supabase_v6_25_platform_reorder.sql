-- ============================================================================
-- Per-platform reorder settings — Shopify + Chewy (v6.25)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v6.25.
-- ============================================================================
-- The new "Reorder Setup" tab on the Inventory Planning page lets the user set
-- a reorder trigger (threshold, in days of supply) + reorder qty (in days of
-- supply) PER PLATFORM:
--
--   • Amazon US / CA / EU-UK  → already stored per-region on `inventory`
--                               (reorder_threshold_days / reorder_qty_days,
--                               added in supabase_v5_1_per_region_amazon_settings.sql)
--   • Shopify (DTC, US-only)  → NEW master-level columns on `products` below
--   • Chewy   (US-only)       → NEW master-level columns on `products` below
--
-- Shopify + Chewy are single-region channels, so their reorder settings live
-- at the product (master) level rather than per inventory (asin, region) row.
--
-- All nullable — null means "unset" (the Reorder Setup grid shows "—"). These
-- are operator-maintained settings; the Amazon reorder math is unchanged.
--
-- Idempotent — IF NOT EXISTS guards.
-- ============================================================================

alter table products
  add column if not exists reorder_threshold_days_shopify numeric,
  add column if not exists reorder_qty_days_shopify       numeric,
  add column if not exists reorder_threshold_days_chewy   numeric,
  add column if not exists reorder_qty_days_chewy         numeric;

-- Verify:
--   select column_name, data_type from information_schema.columns
--   where table_name = 'products' and column_name like 'reorder_%'
--   order by column_name;
