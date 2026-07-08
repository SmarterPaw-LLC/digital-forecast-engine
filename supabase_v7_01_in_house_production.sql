-- ============================================================================
-- Add `in_house_production` flag to products (v7.01)
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- Master-level boolean marking a product as manufactured / assembled in-house
-- (as opposed to sourced from an external supplier). Drives:
--   • Product edit modal — checkbox next to Bundle? / Active? / Seasonal?
--   • Inventory Planning filter — "🏭 In-house only" quick filter.
--   • Inventory Planning column — selectable via the 📋 View picker.
--   • CSV export — participates via the standard column-export pipeline.
--
-- Defaults false so no existing product changes behavior; operator opts in
-- per SKU via the modal.
-- ============================================================================

alter table products
  add column if not exists in_house_production boolean not null default false;

comment on column products.in_house_production is
  'true when the product is manufactured / assembled in-house (v7.01). Master-level; drives the In-house filter + column on Inventory Planning.';

create index if not exists products_in_house_idx
  on products(in_house_production) where in_house_production = true;

-- Verify (post-run):
--   select count(*) filter (where in_house_production) as in_house,
--          count(*) filter (where not in_house_production) as external
--   from products;
