-- ============================================================================
-- v4.161 — move reorder threshold + qty from `inventory` to `products`
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- v4.160 stored these on `inventory` (per asin+region), which gated PO
-- recommendations to ASIN products. The actual model is:
--   * Reorder values are per-PRODUCT (one manufacturer PO covers all
--     channels — Shopify, Chewy, Amazon).
--   * Amazon's unique trait is two inventory locations (warehouse + FBA),
--     handled automatically by `total_onhand = fba_avail + inbound + warehouse`
--     in records-build. Non-Amazon products' total_onhand is just warehouse.
--
-- So the fields belong on `products`. This migration:
--   1. Adds reorder_threshold_days + reorder_qty_days to products (def 90)
--   2. Backfills any per-product values from existing inventory rows
--      (uses the max across regions in case they differ)
--   3. Leaves the inventory columns in place — harmless, removable later.
-- ============================================================================

alter table products add column if not exists reorder_threshold_days int default 90;
alter table products add column if not exists reorder_qty_days       int default 90;

-- Backfill from inventory (only where products has the default 90).
-- If both US + CA rows exist with different values, take the max — keeps the
-- more conservative buffer.
update products p
   set reorder_threshold_days = sub.threshold,
       reorder_qty_days       = sub.qty_days
  from (
    select master_id,
           max(reorder_threshold_days) as threshold,
           max(reorder_qty_days)       as qty_days
      from inventory
     where master_id is not null
       and (reorder_threshold_days is not null or reorder_qty_days is not null)
     group by master_id
  ) sub
 where p.master_id = sub.master_id
   and p.reorder_threshold_days = 90
   and p.reorder_qty_days       = 90;

-- Verify
--   select count(*) total,
--          sum(case when reorder_threshold_days != 90 then 1 else 0 end) custom_threshold,
--          sum(case when reorder_qty_days       != 90 then 1 else 0 end) custom_qty
--   from products;
