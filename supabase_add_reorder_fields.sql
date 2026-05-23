-- ============================================================================
-- Per-SKU reorder threshold + qty (inventory) + new/deprecated flags (products)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.160.
-- ============================================================================
-- inventory.reorder_threshold_days  — when projected DOS hits this number,
--                                     a PO must be in motion. Default 90.
-- inventory.reorder_qty_days        — how many days of forward seasonal
--                                     demand each PO should cover. Default 90.
-- products.new_product_amazon       — flag for limited-history launches.
--                                     Visual marker; doesn't change math
--                                     automatically (forecast unreliable —
--                                     eyeball PO size manually).
-- products.deprecated_product_amazon — flag for SKUs being phased out.
--                                     PO planner returns order qty 0 + no
--                                     PO date + "Deprecated" status badge.
--
-- Existing rows get the defaults — no backfill needed.
-- ============================================================================

alter table inventory add column if not exists reorder_threshold_days int default 90;
alter table inventory add column if not exists reorder_qty_days       int default 90;

alter table products  add column if not exists new_product_amazon         boolean default false;
alter table products  add column if not exists deprecated_product_amazon  boolean default false;

-- Verify
--   select count(*) total,
--          count(reorder_threshold_days) with_threshold,
--          count(reorder_qty_days)       with_qty
--   from inventory;
--   select count(*) total,
--          sum(case when new_product_amazon then 1 else 0 end)        new_count,
--          sum(case when deprecated_product_amazon then 1 else 0 end) deprecated_count
--   from products;
