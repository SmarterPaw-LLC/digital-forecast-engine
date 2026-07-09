-- ============================================================================
-- Top Products flag (v7.08)
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- Boolean flag on products to mark a "shortlist" of top-attention SKUs. Drives
-- the ⭐ Top Products collapsible panel at the top of Inventory Planning,
-- Products, and Amazon P&L pages (initial rollout). Clicking any chip in that
-- panel narrows the current page to that product. Persists cross-session.
--
-- Defaults false so no existing product changes behavior; operator opts in
-- per SKU via the modal (checkbox next to In-house / Active / Seasonal).
-- ============================================================================

alter table products
  add column if not exists is_top_product boolean not null default false;

comment on column products.is_top_product is
  'true when the SKU is on the ⭐ Top Products shortlist (v7.08). Master-level; drives the collapsible top-of-page filter panel.';

create index if not exists products_top_idx
  on products(is_top_product) where is_top_product = true;

-- Verify (post-run):
--   select count(*) filter (where is_top_product) as top,
--          count(*) filter (where not is_top_product) as rest
--   from products;
