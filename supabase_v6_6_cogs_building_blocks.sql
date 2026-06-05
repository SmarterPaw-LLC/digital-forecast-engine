-- ============================================================================
-- COGS building blocks (v6.6)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v6.6.
-- ============================================================================
-- Adds the cost decomposition columns the user requested:
--
--   landed_cost          — raw cost of goods landed (FOB + freight + duty)
--   overhead_dtc         — allocated DTC overhead per unit
--   fulfillment_dtc      — DTC fulfillment cost per unit (3PL pick/pack)
--   fulfillment_amazon   — Amazon fulfillment cost per unit (typically FBA fee)
--   shipping_cost        — outbound DTC shipping cost per unit
--
-- Derived totals (recomputed by the COGS page on building-block edit):
--   amazon_cogs = landed_cost + fulfillment_amazon
--   dtc_cogs    = landed_cost + overhead_dtc + fulfillment_dtc + shipping_cost
--
-- The existing amazon_cogs and dtc_cogs columns stay in the schema. They're
-- the authoritative read path for every downstream consumer (P&L, Forecast,
-- Inventory Planning) and continue to be directly editable in case the user
-- wants to override the computed total (one-off pricing scenarios, partial
-- data, etc.). The COGS page just keeps them in sync with the building
-- blocks on edit.
--
-- amazon_cogs_eu and chewy_cogs are NOT touched. They remain manually
-- editable in the COGS page UI — these channels don't have the same cost
-- structure decomposition as DTC + Amazon US/CA.
--
-- Safe to run multiple times — IF NOT EXISTS guards all five columns.
-- ============================================================================

alter table product_cogs
  add column if not exists landed_cost        numeric,
  add column if not exists overhead_dtc       numeric,
  add column if not exists fulfillment_dtc    numeric,
  add column if not exists fulfillment_amazon numeric,
  add column if not exists shipping_cost      numeric;

-- Verify (optional, run separately):
--   select column_name, data_type from information_schema.columns
--   where table_name = 'product_cogs' order by ordinal_position;
