-- ============================================================================
-- Add `new_amazon_daily_units` to products
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.172.
-- ============================================================================
-- Stores the expected daily units a product will sell on Amazon while it's
-- flagged `new_product_amazon = true`. Used as a manual override for both:
--   • Inventory Planning — Amazon vel = this rate (flat, no seasonality):
--       base    = rate × horizon_days
--       reorder = reorder_qty_days × rate (fires when FBA-DOS < threshold)
--   • Demand Forecast — overrides blended_daily + disables seasonal multiplier
--     for this product. UI surfaces a 🆕 badge with tooltip explaining that
--     velocity + seasonality are bypassed for new-product launches.
--
-- Null / 0 → no override (treated as "rate not set" — falls back to historical).
-- Only meaningful when `new_product_amazon = true`.
-- ============================================================================

alter table products add column if not exists new_amazon_daily_units numeric(10,2);

-- Verify
--   select master_id, asin, new_product_amazon, new_amazon_daily_units
--   from products
--   where new_product_amazon = true;
