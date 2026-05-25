-- ============================================================================
-- Add `fulfillment_amazon` to inventory (per asin + region)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.195.
-- ============================================================================
-- Flags whether each Amazon inventory row is FBA (Amazon ships from FBA) or
-- FBM (Merchant ships from own warehouse). Stored per-region because a
-- product can be FBM in US and FBA in CA (or vice versa).
--
-- Math impact when 'FBM':
--   • amazon.base    = Amazon vel × horizon  (continuous warehouse draw)
--   • amazon.reorder = 0                     (no warehouse→FBA replenishment)
--   • Need TOTAL counts Amazon's base in the warehouse drain (like Shopify)
--   • Need BASE sum includes amazon.base for FBM (was excluded for FBA)
--   • Status in 'Amazon FBA' mode reads "n/a (FBM)" — no FBA pool to score
--   • Action rollup checks only Warehouse pool — no FBA shipment ever needed
--
-- Existing rows get 'FBA' (the prior assumption). Flip to 'FBM' per row via
-- the Inventory edit modal's new "Amazon fulfillment" dropdown.
-- ============================================================================

alter table inventory add column if not exists fulfillment_amazon text default 'FBA';

-- Make sure existing rows that picked up NULL get the default.
update inventory set fulfillment_amazon = 'FBA' where fulfillment_amazon is null;

-- Lightweight check; allow lowercase too just in case (we'll normalize in app code).
do $$ begin
  if not exists (
    select 1 from pg_constraint where conname = 'inventory_fulfillment_amazon_chk'
  ) then
    alter table inventory add constraint inventory_fulfillment_amazon_chk
      check (upper(fulfillment_amazon) in ('FBA', 'FBM'));
  end if;
end $$;

-- Verify
--   select fulfillment_amazon, count(*) from inventory group by 1;
