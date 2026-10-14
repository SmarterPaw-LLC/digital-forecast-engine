-- v10.58 — Chewy column saved views, per user.
--
-- Same shape as forecast_saved_views (v4.100) / inventory_saved_views (v4.166)
-- / products_saved_views (v7.23): Supabase is canonical, localStorage is a
-- fast first-paint cache. Until this runs, the picker still works but the views
-- stay per-browser and the console logs a warning naming this file.
--
-- Idempotent. Run once in Supabase → SQL Editor.

alter table public.user_profiles
  add column if not exists chewy_saved_views jsonb not null default '{}'::jsonb;

comment on column public.user_profiles.chewy_saved_views is
  'Per-user saved column sets for the Chewy P&L tabs. Shape: {sales|cost|breakeven: {viewName: {hiddenCols: [...] | null, savedAt}}}. hiddenCols null means "no explicit choice" (use the registry default), which is NOT the same as [] ("show everything").';
