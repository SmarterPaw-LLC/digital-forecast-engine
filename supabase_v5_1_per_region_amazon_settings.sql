-- ============================================================================
-- Per-region Amazon PO settings on inventory (v5.1)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v5.1.
-- ============================================================================
-- Moves these five fields from master-level (products) to per-region
-- (inventory):
--   • reorder_threshold_days
--   • reorder_qty_days
--   • new_product_amazon
--   • deprecated_product_amazon
--   • new_amazon_daily_units
--
-- Why: a SKU can legitimately have different PO cycles + lifecycle states
-- per Amazon marketplace. US might be "launch" (new=true, rate=30/d) while
-- CA is mature historical. Without per-region storage, the FBA reorder
-- simulation, multi-event scheduling, and 🆕 launch override couldn't
-- distinguish.
--
-- Strategy: dual-write for safety. The `products.*` columns are KEPT
-- in place as master-level defaults — the app reads `coalesce(inv.X, p.X)`
-- so an inventory row without an override falls back to the product-level
-- value. New regions (UK / DE / FR / etc.) that haven't been touched still
-- inherit the master defaults until explicitly overridden.
--
-- Idempotent: re-running is safe.
-- ============================================================================

-- 1. Add the columns.
alter table inventory add column if not exists reorder_threshold_days    int;
alter table inventory add column if not exists reorder_qty_days          int;
alter table inventory add column if not exists new_product_amazon        boolean;
alter table inventory add column if not exists deprecated_product_amazon boolean;
alter table inventory add column if not exists new_amazon_daily_units    numeric(10,2);

-- 2. Backfill from products. coalesce() preserves any per-region value
-- that might already exist (e.g., from a partial re-run).
update inventory i set
  reorder_threshold_days    = coalesce(i.reorder_threshold_days,    p.reorder_threshold_days),
  reorder_qty_days          = coalesce(i.reorder_qty_days,          p.reorder_qty_days),
  new_product_amazon        = coalesce(i.new_product_amazon,        p.new_product_amazon,        false),
  deprecated_product_amazon = coalesce(i.deprecated_product_amazon, p.deprecated_product_amazon, false),
  new_amazon_daily_units    = coalesce(i.new_amazon_daily_units,    p.new_amazon_daily_units)
from products p
where i.master_id = p.master_id;

-- Verify
--   select region,
--          count(*) total,
--          count(*) filter (where new_product_amazon)        new_count,
--          count(*) filter (where deprecated_product_amazon) dep_count,
--          avg(reorder_threshold_days)::numeric(10,1)        avg_threshold,
--          avg(reorder_qty_days)::numeric(10,1)              avg_qty
--   from inventory group by region order by region;
