-- ============================================================================
-- Per-product Seasonality — adds three columns to `products`
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- The dashboard previously used hardcoded `SEED.curves` (one curve per
-- category, baked into index.html) for the weekly seasonal multiplier on
-- forecasts. v4.75 adds the ability to compute a per-product curve from the
-- product's actual sales_weekly history and override the category default.
--
-- Columns:
--   sea_method        — how to source the weekly multiplier:
--                       'category-default' (default, uses SEED.curves)
--                       'calculated'        (uses sea_curve_calculated)
--                       'manual'            (uses sea_curve_manual)
--   sea_curve_calculated — JSON { "1": 1.2, "2": 1.1, ..., "52": 0.8 }
--   sea_curve_manual     — JSON same shape; user-edited override
--   sea_min_weeks        — minimum weeks of sales data required before the
--                          calculated curve is considered reliable enough to
--                          apply. Below this, fall back to category default.
--                          Lets you tag new launches with a high threshold
--                          (e.g. 52) and known-seasonal items with a low one
--                          (e.g. 12) so the system doesn't apply a noisy curve
--                          before there's enough data to compute one.
-- ============================================================================

alter table products add column if not exists sea_method            text default 'category-default'
  check (sea_method in ('category-default','calculated','manual'));
alter table products add column if not exists sea_curve_calculated  jsonb;
alter table products add column if not exists sea_curve_manual      jsonb;
alter table products add column if not exists sea_min_weeks         integer default 26;
alter table products add column if not exists sea_calculated_at     timestamptz;
alter table products add column if not exists sea_weeks_of_data     integer;

-- Per-product seasonal designation (v4.77). Lets you tag a product as
-- broadly-seasonal or sharp-seasonal-limited and have the right SEED curve
-- apply without depending on `category_id` pointing at a `seasonal_limited`
-- categories row. Precedence in `getEffectiveCurveForProduct`:
--    1. sea_method='calculated' or 'manual' (with weeks_of_data >= sea_min_weeks)
--    2. seasonal_type ('seasonal' / 'seasonal_limited' / 'flat')
--    3. category default (existing SEED.curves[category_name] lookup)
--
-- Values:
--   'standard'         — default; use category curve (same as no flag)
--   'seasonal'         — use SEED.curves.seasonal (moderate peak)
--   'seasonal_limited' — use SEED.curves.seasonal_limited (sharp narrow peak)
--   'flat'             — multiplier of 1.0 every week (good for new launches
--                        you don't want seasonality to distort yet)
alter table products add column if not exists seasonal_type text default 'standard'
  check (seasonal_type in ('standard','seasonal','seasonal_limited','flat'));

-- No backfill needed — existing rows default to 'category-default' / 'standard'
-- which preserves current behavior (SEED.curves lookup via category).
