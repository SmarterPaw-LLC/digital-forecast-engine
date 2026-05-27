-- ============================================================================
-- Add `db_user_queries` column to user_profiles (v5.38)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v5.38.
-- ============================================================================
-- Stores each user's saved Query Database queries as a JSONB array of
-- {name, sql, savedAt} objects. Same pattern as inventory_saved_views /
-- forecast_saved_views — per-user, RLS-gated, accessed via the Supabase
-- client with the user's JWT.
--
-- Default '[]' so newly-onboarded users get an empty list rather than null
-- (saves a null check in the app code).
-- ============================================================================

alter table user_profiles
  add column if not exists db_user_queries jsonb default '[]'::jsonb;

-- Verify
--   select user_id, jsonb_array_length(coalesce(db_user_queries,'[]'::jsonb)) as n_queries
--   from user_profiles order by n_queries desc;
