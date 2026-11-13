-- v12.36 — a place to type the Chewy cost when the export does not list the SKU
--
-- Jason: "i can't set the cost per case for chewy on the 'cost to chewy' tab.
--         when i click on the row it opens the card. the card has no place to
--         set this"
--
-- He is right, and it is the blocker behind the v12.35 finding: 35 Chewy SKUs
-- are still selling and are absent from the uploaded Catalog Details export
-- (last pulled 2026-10-12, 127 rows). Until now the ONLY source of a Chewy
-- cost was that upload, so those 35 priced at nothing on the Cost to Chewy
-- tab, in the Chewy P&L and in the Units Sold "Our Revenue" measure — about
-- 7,800 units and $92k of retail over the trailing year.
--
-- ⚠ THIS IS A FALLBACK, NOT AN OVERRIDE. chewy_catalog always wins. These two
-- columns are consulted only when Chewy's own file has no row for the SKU, so
-- the next Catalog Details upload silently takes over and nothing has to be
-- un-typed. The app marks a hand-priced row wherever it shows the figure.
--
-- ⚠ AND IT LIVES ON `products`, NOT IN `chewy_catalog`. Writing our own number
-- into the upload table would (a) be erased by the next upload with no trace,
-- and (b) destroy the Cost to Chewy tab's catalog-coverage audit, whose whole
-- job is to report which SKUs the export is missing. On `products` it is our
-- number, plainly ours, and the audit still reports the SKU as absent from the
-- export — which it is.
--
-- Shaped like the catalog's own pair (cost + purchase UOM) so the SAME
-- chewyCatalogPricePerEach division applies: cost ÷ products.case_qty on a CS
-- row, cost as-is on an EA row. A second spelling of that division is how the
-- card and the tab start disagreeing.

alter table public.products
  add column if not exists chewy_cost     numeric,
  add column if not exists chewy_cost_uom text;

comment on column public.products.chewy_cost is
  'v12.36 — FALLBACK Chewy vendor cost, typed on the product card. Used only '
  'when chewy_catalog has no row for this product''s chewy_sku; the export '
  'always wins. Quoted per chewy_cost_uom (CS = per case, divided by '
  'case_qty; EA = per each).';

comment on column public.products.chewy_cost_uom is
  'v12.36 — purchase UOM for chewy_cost: CS (per case, divide by case_qty) or '
  'EA (per each). Mirrors chewy_catalog.purchase_uom so one division serves '
  'both sources.';

-- No RLS change: `products` already carries its policy and grants.
--
-- Check:
--   select master_id, chewy_sku, chewy_cost, chewy_cost_uom, case_qty
--   from products where chewy_cost is not null order by master_id;
