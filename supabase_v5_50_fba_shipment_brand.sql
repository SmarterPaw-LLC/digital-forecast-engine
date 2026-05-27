-- ============================================================================
-- Add `brand` column to fba_shipment_summaries (v5.50)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v5.50.
-- ============================================================================
-- Why: per-shipment .tsv detail uploads can derive brand from joined product
-- rows (each item's ASIN → products.brand). But the Shipment Summary CSV
-- (Manage FBA Shipments list) has no SKU detail, so we can't auto-detect
-- brand at summary-only time. v5.50 prompts for it at upload + stores here.
--
-- Schema:
--   • TEXT (free-form). Expected values are 'Meowijuana' / 'Doggijuana' /
--     'Kitty Ka-Zoom' (matching products.brand) or 'Mixed' when the user
--     marks the upload as containing multiple brands.
--   • Nullable. Pre-v5.50 rows leave it null; the dashboard derives a
--     display brand from the detail .tsv (when uploaded) for those.
--   • No CHECK constraint — brand list is set at the app layer, not the
--     DB, to avoid the same migration headache `sales_weekly_region_check`
--     caused us in v4.147 when EU was added.
--
-- v5.50 backfill workflow (handled by the app at upload time, not here):
--   1. Summary CSV upload → prompt brand → set on every uploaded row.
--   2. Detail .tsv upload → if the matched summary row has brand=null AND
--      every item resolves to the same products.brand, set brand on the
--      summary row.
--
-- Belt-and-suspenders: explicit GRANT to authenticated since alter table
-- doesn't change role-level grants (default privileges from
-- supabase_auth_setup.sql cover new tables but not new columns — though
-- column-level grants are inherited from table-level grants, so this is
-- defensive only).
-- ============================================================================

alter table fba_shipment_summaries
  add column if not exists brand text;

-- Verify
--   select brand, count(*)
--   from fba_shipment_summaries
--   group by brand
--   order by count(*) desc;
