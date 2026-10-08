-- ════════════════════════════════════════════════════════════════════════════
-- v10.6 — per-user, per-page category / sub-category visibility
-- ════════════════════════════════════════════════════════════════════════════
-- Jason: "on each page i would like the ability to show/hide certain categories
-- and subcategories by default. this should be configurable per user and should
-- save across sessions."
--
-- Run ONCE in Supabase → SQL Editor. Idempotent (add column if not exists), so
-- re-running is a no-op.
--
-- Until this runs, the feature still works for the current browser via its
-- localStorage cache and the console logs a warning naming this file — the
-- selection just won't follow the user to another browser or device.
--
-- Shape of the JSONB (keys are page keys from CATVIS_PAGES in index.html, plus
-- the reserved '_global'):
--
--   {
--     "_global":     { "cats": ["Sprays","Treats"], "subcats": null },
--     "pnl_amazon":  { "cats": null,                "subcats": null },
--     "inventory":   { "cats": ["Sprays"],          "subcats": ["3 oz"] }
--   }
--
--   • null              → no filter on that axis (show everything)
--   • array of strings  → show ONLY these values
--   • key PRESENT with both null → an explicit "show all on this page",
--     which deliberately differs from the key being ABSENT (inherit _global).
--     The app relies on that distinction, so do not "clean up" all-null keys.
-- ════════════════════════════════════════════════════════════════════════════

alter table user_profiles
  add column if not exists category_visibility jsonb not null default '{}'::jsonb;

comment on column user_profiles.category_visibility is
  'v10.6 — per-page category/sub-category visibility scope for this user. Keys are page keys plus the reserved _global. Value {cats, subcats}: null = no filter, array = show only these. Key present with both null = explicit show-all override; key absent = inherit _global.';

-- No RLS or GRANT changes needed: user_profiles already has RLS enabled with
-- "users can update their own row", and the authenticated role already holds
-- table-level DML on it (see supabase_auth_setup.sql §5b). A new column on an
-- existing table inherits both.

-- ── verify ──────────────────────────────────────────────────────────────────
-- select column_name, data_type, column_default, is_nullable
--   from information_schema.columns
--  where table_name = 'user_profiles' and column_name = 'category_visibility';
--
-- select user_id, category_visibility from user_profiles;
