-- ============================================================================
-- Product "seasonal" flag (v6.39)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v6.39.
-- ============================================================================
-- Marks products that sell during a specific season (e.g. Christmas toys).
-- Surfaced as a checkbox on the Products table + product modal, and flows into
-- the seasonality calculation:
--
--   • Stockout correction is DISABLED for seasonal products — their off-season
--     near-zero weeks (and the sharp season-end drop) are REAL demand, not
--     supply gaps, so they must NOT be excluded from the curve.
--   • When a seasonal product has no calculated curve of its own, the fallback
--     uses the `seasonal_limited` curve template (a sharp, concentrated peak)
--     instead of the flat-ish category default.
--
-- Default false — existing products are unaffected.
-- Idempotent — IF NOT EXISTS guard.
-- ============================================================================

alter table products
  add column if not exists seasonal boolean not null default false;

-- Verify:
--   select master_id, short_name, seasonal from products where seasonal = true;
