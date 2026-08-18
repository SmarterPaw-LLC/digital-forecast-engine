-- v7.54 — Add sales_saved_views JSONB column to user_profiles.
-- Backs the Units Sold page's Saved Reports feature (parity with the
-- forecast_saved_views + inventory_saved_views columns added in v4.100 / v4.166).
-- Localstorage still caches for fast first-paint; this column is the
-- cross-device canonical store keyed to the authenticated user.
--
-- Shape:
--   { "<report name>": {
--       cols: null,                          -- placeholder for future
--       filters: {
--         brand: '', cat: '', search: '',
--         period: '30', customFrom: '', customTo: '',
--         channels: { amazon_us: true, amazon_ca: true, shopify: true, chewy: true, walmart: true },
--         bundleAttr: false, hideBundles: false
--       },
--       chart: {
--         type: 'line' | 'bar' | 'stacked' | 'area',
--         tab:  'total' | 'channel'
--       },
--       sort: { col: 'period' | 'alltime', dir: 1 | -1 },
--       selection: ['SP-0001', 'SP-0042', ...]   -- master_ids
--     }, ...
--   }
--
-- Idempotent: uses `add column if not exists`. Safe to re-run.

alter table user_profiles
  add column if not exists sales_saved_views jsonb not null default '{}'::jsonb;

comment on column user_profiles.sales_saved_views is
  'Named saved reports for the Units Sold page (filters + selection + chart type). Added v7.54.';
