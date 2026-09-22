-- v9.00 — Growth Model saved strategies (planning-side saved views).
-- Stores per-user JSONB map of {viewName: {settings…}} so a strategy config
-- like "Aggressive push" / "Conservative floor" / "Blend 50/50" can be named,
-- saved, and applied across products.
--
-- Same architecture as forecast_saved_views (v4.100) and inventory_saved_views
-- (v4.166): Supabase canonical, localStorage cache for fast first paint.

alter table user_profiles
  add column if not exists pnl_growth_saved_views jsonb not null default '{}'::jsonb;

-- No index needed — this column is read/written as a whole blob per user row,
-- not filtered/queried at the field level. Existing user_profiles PK on
-- user_id covers the access path.

comment on column user_profiles.pnl_growth_saved_views is
  'Per-user saved Growth Model strategy presets. Keys = user-supplied view names. Values = {horizonMonths, targetShareEndPct, upliftPct, cpcInflationExp, maxMonthlyTacosPct, enforceTacosCeiling, annualMarketGrowthPct, portfolioRollup, savedAt}. Loaded on init via pnlGrowthLoadSavedViewsFromDb, cached to localStorage for fast subsequent loads.';
