-- ============================================================================
-- Create shopify_sales_daily — daily-grain Shopify sales (v5.98 Pass A)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v5.98.
-- ============================================================================
-- WHY
-- ----
-- `sales_weekly` was built around Amazon's natively-weekly SKU Economics
-- report. Forcing Shopify into a weekly grain creates two problems:
--
--   1. Calendar months don't align with weeks → "May 2026 sales" requires
--      summing 4-5 weeks that mostly fall in May; boundary weeks like
--      4/27-5/3 either get attributed wrong or get pro-rated.
--   2. Shopify can natively export at any grain (day, week, month, quarter).
--      The new ShopifyQL ("FROM sales SHOW ... WHERE line_type='product' ...")
--      pulls richer per-row data (sales_channel, gross_sales, discounts,
--      returns, taxes, total_sales, product_variant_title, product_id,
--      product_title_at_time_of_sale) — fields the existing 4-column
--      sales_weekly schema can't hold.
--
-- Solution: a Shopify-native daily-grain table that captures the full field
-- set and supports any read-side period (week, month, custom range) via
-- simple BETWEEN clauses. Amazon + Chewy + EU stay on sales_weekly because
-- their native exports are weekly.
--
-- WHAT THIS DOES (Pass A — write side only)
-- ------------------------------------------
-- 1. Creates `shopify_sales_daily` with all richer-query fields.
-- 2. Creates a PLAIN-column unique index — NO `coalesce()` this time.
--    sales_channel defaults to '' at the parser level for the rare null case
--    so upsert with plain-column onConflict would work cleanly (lessons
--    learned from v5.96/v5.97 Architecture Rule #5). The parser writes via
--    DELETE+INSERT regardless, as the safe default.
-- 3. Indexes by (day) and (master_id) for fast period + product lookups.
-- 4. DOES NOT touch sales_weekly yet — existing Shopify rows there stay
--    intact during the transition. velocity_calculated keeps working off
--    them. Pass B (next migration) will delete those rows + rewrite the
--    view + cut over the read-side surfaces.
-- ============================================================================

create table if not exists shopify_sales_daily (
  id                       bigserial primary key,
  master_id                text,            -- nullable for unmatched SKUs
  shopify_sku              text not null,
  shopify_product_id       text,            -- Shopify's internal product_id (numeric, stored as text)
  variant_title            text,            -- e.g. "Small" / "Red" / null when single-variant
  title_at_time_of_sale    text,            -- historical product title at the time of sale
  vendor                   text,            -- raw vendor string for brand mapping
  sales_channel            text not null default '',  -- "Online Store" / "POS" / "Wholesale" / "" if unknown
  day                      date not null,

  units_sold               integer       default 0,
  gross_sales              numeric(12,2) default 0,
  discounts                numeric(12,2) default 0,
  returns                  numeric(12,2) default 0,
  net_sales                numeric(12,2) default 0,
  taxes                    numeric(12,2) default 0,
  total_sales              numeric(12,2) default 0,

  source                   text default 'shopify',
  uploaded_at              timestamptz default now()
);

-- Plain-column unique index — no functional expression. sales_channel
-- defaults to '' so all rows have a non-null value, which means plain-column
-- onConflict would match this index cleanly (no v5.96-style silent
-- degradation). DELETE+INSERT pattern is still used by the parser per
-- Architecture Rule #5, but the design here is upsert-safe by default.
create unique index if not exists shopify_sales_daily_uniq
  on shopify_sales_daily (shopify_sku, day, sales_channel);

-- Lookup indexes for the P&L tab + velocity calculations.
create index if not exists shopify_sales_daily_day_idx
  on shopify_sales_daily (day);
create index if not exists shopify_sales_daily_master_idx
  on shopify_sales_daily (master_id)
  where master_id is not null;

-- Grant the dashboard's role access (mirrors the convention used for
-- sales_weekly + sku_economics).
grant select, insert, update, delete on shopify_sales_daily to authenticated;
grant usage, select on sequence shopify_sales_daily_id_seq to authenticated;

-- ============================================================================
-- After commit:
--   1. Deploy index.html v5.98 (parseShopifySales now writes to this table).
--   2. Run a new Shopify upload using the richer ShopifyQL query (see the
--      CLAUDE.md v5.98 entry for the canonical query format).
--   3. Verify rows landed:
--        select count(*), min(day), max(day) from shopify_sales_daily;
--        select shopify_sku, sales_channel, sum(units_sold), sum(net_sales)
--        from shopify_sales_daily
--        group by shopify_sku, sales_channel
--        order by sum(net_sales) desc limit 20;
--   4. Pass B (next migration) will:
--        a. Delete existing channel='shopify' rows from sales_weekly.
--        b. Rewrite the velocity_calculated view to UNION sales_weekly
--           (non-shopify) + shopify_sales_daily (per-day).
--        c. The dashboard read-side surfaces (Shopify P&L, Forecast salesData,
--           Units Sold) get updated in the same code release.
-- ============================================================================
