-- ============================================================================
-- Rename `chewy_part_no` → `chewy_sku` across the schema
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.90.
-- ============================================================================
-- Affects two tables:
--   • products.chewy_part_no       → products.chewy_sku
--   • chewy_forecasts.chewy_part_no → chewy_forecasts.chewy_sku
--
-- Postgres handles dependent objects (indexes, unique constraints, foreign
-- keys, views) automatically on RENAME COLUMN — the column reference in the
-- unique constraint `(chewy_part_no, forecast_month, upload_date)` becomes
-- `(chewy_sku, forecast_month, upload_date)` without any extra work.
--
-- Reversible: re-run with the rename arguments swapped if you need to roll
-- back. Data values are not touched.
-- ============================================================================

alter table products         rename column chewy_part_no to chewy_sku;
alter table chewy_forecasts  rename column chewy_part_no to chewy_sku;

-- ──────────────────────────────────────────────────────────────────────────
-- Verify
--   \d products              -- should show `chewy_sku` column
--   \d chewy_forecasts       -- unique constraint should reference chewy_sku
-- ============================================================================
