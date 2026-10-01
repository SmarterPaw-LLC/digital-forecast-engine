-- ============================================================================
-- Product dimensions, weight and size tier on `products`  (v9.75)
-- Run ONCE in Supabase -> SQL Editor.
-- ============================================================================
-- WHY
-- ----
-- fba_fee_preview is a time series: one row per (sku, marketplace, snapshot).
-- That is right for tracking how Amazon's measurements and fees change, but it
-- is awkward for every other part of the app, which works per product.
--
-- These columns put Amazon's CURRENT measurement on the product record so the
-- Products page, the product modal and any future query can read dims without
-- joining and de-duplicating a snapshot table.
--
-- IMPORTANT: these are AMAZON'S measurements, not ours. They are what Amazon
-- bases the fulfillment fee on, which is exactly why they are worth holding.
-- The Fee Preview uploader refreshes them on every upload, so a manual edit
-- here will be overwritten. If we ever want OUR OWN measured dims (to dispute
-- Amazon's), those belong in a separate pair of columns.
--
-- Region: US wins when a product has rows for several marketplaces, since the
-- break-even model is US. Falls back to whatever marketplace exists.
-- ============================================================================

alter table products add column if not exists item_package_weight numeric(12,4);
alter table products add column if not exists unit_of_weight      text;
alter table products add column if not exists longest_side        numeric(12,4);
alter table products add column if not exists median_side         numeric(12,4);
alter table products add column if not exists shortest_side       numeric(12,4);
alter table products add column if not exists length_and_girth    numeric(12,4);
alter table products add column if not exists unit_of_dimension   text;
alter table products add column if not exists product_size_tier   text;
alter table products add column if not exists dims_source         text;
alter table products add column if not exists dims_updated_at     timestamptz;

create index if not exists products_size_tier_idx on products (product_size_tier);

-- ── Backfill from the latest Fee Preview snapshot per ASIN ──────────────────
-- distinct on (asin) with US preferred, then newest snapshot.
with latest as (
  select distinct on (fp.asin)
         fp.asin,
         fp.item_package_weight, fp.unit_of_weight,
         fp.longest_side, fp.median_side, fp.shortest_side,
         fp.length_and_girth, fp.unit_of_dimension,
         fp.product_size_tier, fp.snapshot_date
  from fba_fee_preview fp
  where fp.asin is not null and fp.asin <> ''
  order by fp.asin, (fp.region = 'US') desc, fp.snapshot_date desc
)
update products p
   set item_package_weight = l.item_package_weight,
       unit_of_weight      = l.unit_of_weight,
       longest_side        = l.longest_side,
       median_side         = l.median_side,
       shortest_side       = l.shortest_side,
       length_and_girth    = l.length_and_girth,
       unit_of_dimension   = l.unit_of_dimension,
       product_size_tier   = l.product_size_tier,
       dims_source         = 'fba_fee_preview',
       dims_updated_at     = l.snapshot_date::timestamptz
  from latest l
 where p.asin = l.asin;

-- ── Verify ─────────────────────────────────────────────────────────────────
select count(*) filter (where product_size_tier is not null)   as with_tier,
       count(*) filter (where item_package_weight is not null) as with_weight,
       count(*) filter (where longest_side is not null)        as with_dims,
       count(*)                                                as total_products
from products;
