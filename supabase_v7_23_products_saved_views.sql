-- ============================================================================
-- Products page: Saved Views (v7.23)
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- Per-user JSONB blob for the Products page saved-view library. Same shape as
-- inventory_saved_views (v4.166) + forecast_saved_views (v4.100) — each view
-- captures column visibility, sort, and every filter dimension. localStorage
-- keeps a fast first-paint cache; this column is the canonical source that
-- follows the user across browsers + devices.
--
-- Schema of the JSONB value:
--   {
--     "<View Name>": {
--       "cols":       ["brand","title","sp_sku",...],
--       "sortKey":    "title",
--       "sortDir":    1,                            // 1 = asc, -1 = desc
--       "filters": {
--         "brand":         "Meowijuana",
--         "filter":        "seasonal",              // prodFilter dropdown
--         "search":        "catnip",
--         "lifecycleView": false,
--         "catFilter":     ["Toys","Consumables"],  // array (null = all)
--         "subcatFilter":  ["Bubbles","Sprays"]     // array (null = all)
--       }
--     },
--     ...
--   }
-- ============================================================================

alter table user_profiles
  add column if not exists products_saved_views jsonb not null default '{}'::jsonb;

comment on column user_profiles.products_saved_views is
  'Per-user saved views for the Products page (v7.23). Mirrors inventory_saved_views / forecast_saved_views. Keys are view names, values are {cols, sortKey, sortDir, filters}.';

-- Verify (post-run):
--   select user_id, jsonb_object_keys(products_saved_views) as view_name
--   from user_profiles
--   where products_saved_views <> '{}'::jsonb;
