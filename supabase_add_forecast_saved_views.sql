-- ============================================================================
-- Add `forecast_saved_views` JSONB column to user_profiles
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.100.
-- ============================================================================
-- Stores each user's saved column-visibility presets for the Forecast tab.
-- Shape: `{ "View Name 1": ["col1", "col2", ...], "View Name 2": [...] }`.
-- Empty default so new users start with no views (they can save their own).
--
-- Previously stored in localStorage only (per-browser, per-device, not
-- synced). With this column, views follow the user across devices and
-- survive browser data clears.
-- ============================================================================

alter table user_profiles add column if not exists forecast_saved_views jsonb default '{}'::jsonb;

-- The existing RLS policies on user_profiles already permit each user to
-- update their own row (per the v4.60 auth setup), so no new policy needed:
--   "profiles update own" — auth.uid() = user_id

-- ──────────────────────────────────────────────────────────────────────────
-- Verify
--   select user_id, email, forecast_saved_views from user_profiles;
-- ============================================================================
