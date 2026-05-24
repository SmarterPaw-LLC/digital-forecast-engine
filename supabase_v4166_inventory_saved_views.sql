-- ============================================================================
-- Add `inventory_saved_views` JSONB column to user_profiles
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.166.
-- ============================================================================
-- Stores each user's saved column-visibility + filter presets for the
-- Inventory Planning page. Shape mirrors forecast_saved_views:
--   { "View Name 1": { cols, sortKey, sortDir, filters }, ... }
--
-- Previously the Inventory page had no column-visibility or saved views at
-- all — all 19 columns were always visible and sort was a single key kept
-- in memory. v4.166 adds the View popup matching the Forecast page pattern.
-- ============================================================================

alter table user_profiles add column if not exists inventory_saved_views jsonb default '{}'::jsonb;

-- Existing RLS policies on user_profiles already permit each user to update
-- their own row (per the v4.60 auth setup), so no new policy needed.

-- ──────────────────────────────────────────────────────────────────────────
-- Verify
--   select user_id, email, inventory_saved_views from user_profiles;
-- ============================================================================
