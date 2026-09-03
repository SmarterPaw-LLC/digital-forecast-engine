-- v8.13 — Capture Sponsored Products ad-ATTRIBUTED sales per ASIN per week.
--
-- WHY: Amazon SKU Economics report has TWO columns per row for Sponsored
-- Products: "Sponsored Products charge total" (SPEND — we already read this
-- into sponsored_products_total) and "Sponsored Products sales total" (the
-- ad-ATTRIBUTED revenue — the sales Amazon credits to SP ad clicks in the
-- 7-day-post-click window). We were only reading the spend column, which
-- meant every ROAS calc in the app was TROAS (Total ROAS = net_sales ÷ ad_spend,
-- which conflates organic + ad-driven revenue) rather than real ad ROAS.
--
-- After this migration + parser update + re-upload of historical files, the
-- Scenario Modeling panel switches to real per-product ad ROAS (Amazon's
-- attributed sales ÷ Amazon's ad spend) for its extra-revenue projections.
-- Numbers will drop substantially for products where organic drives most sales.
--
-- BACKFILL: existing sku_economics rows will have sponsored_products_sales_total = 0
-- because the column didn't exist when those weeks were uploaded. The
-- scenario panel handles this cleanly: rows with no attributed_sales fall
-- back to a labeled "est ROAS" (TROAS × 0.30 heuristic, rendered in orange)
-- while rows with fresh data show real ROAS. NO RE-UPLOAD REQUIRED —
-- coverage grows organically as new weekly uploads land. The panel header
-- displays a coverage % chip (v8.14) so you can see at a glance how much
-- of the current view is real vs estimated.
--
-- Same column added to sku_economics_eu — the EU report has the same
-- "Sponsored Products sales total" column.

alter table sku_economics
  add column if not exists sponsored_products_sales_total numeric(14,4) default 0;

alter table sku_economics_eu
  add column if not exists sponsored_products_sales_total numeric(14,4) default 0;

comment on column sku_economics.sponsored_products_sales_total is
  'Sponsored Products ad-ATTRIBUTED sales per ASIN per week (from Amazon SKU Economics "Sponsored Products sales total"). Used for real ad ROAS = sales / spend in the Scenario Modeling panel. NOT the same as net_sales — that includes organic + ad-driven, this is only what Amazon credits to SP ad clicks.';

comment on column sku_economics_eu.sponsored_products_sales_total is
  'Sponsored Products ad-ATTRIBUTED sales per ASIN per week (EU). See sku_economics.sponsored_products_sales_total for detail. v8.13.';
