-- ============================================================================
-- v10.75 - backfill every column an earlier migration declared but never got run
-- ============================================================================
-- Found by auditing all 33 `create table if not exists` and all 80
-- `add column if not exists` targets across supabase_*.sql against the live
-- database. Every table exists. Six columns did not; five of those are real
-- gaps, collected here so there is ONE file to run instead of three.
--
-- (The sixth, inventory.fulfillment_amazon, is absent BY DESIGN - v4.196 moved
--  it to products.fulfillment_amazon and drops the inventory copy. Verified
--  products.fulfillment_amazon is present. Nothing to do.)
--
-- ⚠ ORDER MATTERS FOR THE FIRST ONE. Deploy index.html v10.75 BEFORE running
--   this. Until v10.75, the saved-view loaders did a blind replace:
--
--       salesSavedViews = data.sales_saved_views;
--       localStorage.setItem('salesSavedViews', ...);
--
--   The columns below default to '{}'::jsonb. An empty object is truthy and
--   passes `typeof === 'object'`, so on the first load after this migration
--   the old code would overwrite both the in-memory map and the on-disk cache
--   with {} - permanently destroying any report saved while the column was
--   missing. That is the v9.66 bug; v9.67 fixed it for the shared query
--   library and the saved-view loaders never got the same treatment.
--   v10.75 makes the loader MERGE and publish browser-only views instead.
--
-- Idempotent throughout (`add column if not exists`). Safe to re-run.
-- No RLS or GRANT work needed: a new column on an existing table inherits
-- that table's row-level security policies and role grants.
-- ============================================================================

begin;

-- ---------------------------------------------------------------- 1. v7.54
-- Units Sold -> Saved reports. Cross-device store for the Units Sold page's
-- named reports (filters + selection + chart type + sort + layout).
-- Was declared in supabase_v7_54_sales_saved_views.sql; never run.
alter table user_profiles
  add column if not exists sales_saved_views jsonb not null default '{}'::jsonb;

comment on column user_profiles.sales_saved_views is
  'Named saved reports for the Units Sold page (filters + selection + chart type). Added v7.54, backfilled v10.75.';

-- --------------------------------------------------------------- 2. v10.58
-- Chewy P&L -> Customize columns / saved views. Note the dashboard currently
-- only WRITES this column (chewyPersistSavedViews); there is no read-back
-- loader yet, so cross-device sync lands when one is added. Creating the
-- column now stops the console warning and starts capturing the data.
alter table user_profiles
  add column if not exists chewy_saved_views jsonb not null default '{}'::jsonb;

comment on column user_profiles.chewy_saved_views is
  'Named saved views for the Chewy P&L sub-tabs (column sets). Added v10.58, backfilled v10.75.';

-- ---------------------------------------------------------------- 3. v4.74
-- COGS page -> dismissible "missing COGS" alerts. These let an operator mute
-- the warning for a channel a product genuinely is not sold on. Declared in
-- supabase_product_cogs_setup.sql, which was run BEFORE these three columns
-- were appended to that file - so product_cogs exists but the flags do not.
-- (amazon_eu_dismissed IS present; it came from supabase_add_sku_economics_eu.sql,
--  which was run later. That split is the tell.)
-- Without these, the ✕ dismiss button on the COGS page fails on write.
alter table product_cogs
  add column if not exists amazon_dismissed boolean not null default false;

alter table product_cogs
  add column if not exists dtc_dismissed boolean not null default false;

alter table product_cogs
  add column if not exists chewy_dismissed boolean not null default false;

comment on column product_cogs.amazon_dismissed is
  'Operator muted the missing-Amazon-COGS alert for this product. Added v4.74, backfilled v10.75.';
comment on column product_cogs.dtc_dismissed is
  'Operator muted the missing-DTC-COGS alert for this product. Added v4.74, backfilled v10.75.';
comment on column product_cogs.chewy_dismissed is
  'Operator muted the missing-Chewy-COGS alert for this product. Added v4.74, backfilled v10.75.';

commit;

-- ============================================================================
-- Verify: expect 5 rows back, one per column added above.
-- ============================================================================
select table_name, column_name, data_type, column_default
from information_schema.columns
where (table_name = 'user_profiles' and column_name in ('sales_saved_views', 'chewy_saved_views'))
   or (table_name = 'product_cogs'  and column_name in ('amazon_dismissed', 'dtc_dismissed', 'chewy_dismissed'))
order by table_name, column_name;
