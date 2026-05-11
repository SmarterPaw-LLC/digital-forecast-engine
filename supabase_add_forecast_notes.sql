-- ============================================================================
-- Add `forecast_notes` text column to products
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.99.
-- ============================================================================
-- Lets users annotate individual products from the Forecast tab — short
-- free-form notes about expected demand changes, seasonality reminders,
-- supply caveats, etc. Edited inline in the Forecast tab's new Notes column.
-- Distinct from products.notes (which is general admin / merge-tool history).
-- ============================================================================

alter table products add column if not exists forecast_notes text;

-- No backfill needed — column defaults to NULL.
