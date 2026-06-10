-- ============================================================================
-- Enable RLS on shopify_sales_daily (v6.47) — SECURITY FIX
-- Run ONCE in Supabase → SQL Editor. Safe to re-run (idempotent).
-- ============================================================================
-- WHY
-- ----
-- Supabase flagged `rls_disabled_in_public` on `shopify_sales_daily`
-- (project yjcnuyoaemlipvuinptp) on 2026-06-08. It's the ONE table that
-- slipped through the v5.98 cutover: `supabase_v5_98_shopify_sales_daily.sql`
-- created the table + granted DML to `authenticated`, but never enabled
-- Row-Level Security and never created a policy. Without RLS, the table is
-- exposed via the Data API to the public anon key (embedded in the dashboard
-- HTML), so "anyone with the project URL can read, edit, and delete" the daily
-- Shopify sales rows.
--
-- Every other table in this project (products, sales_weekly, sku_economics,
-- inventory, bom, chewy_forecasts, categories, channel_listings, product_cogs,
-- sku_economics_eu, fba_inventory_snapshots, fba_shipments,
-- fba_shipment_summaries, inventory_events, user_profiles, audit_log) already
-- has RLS enabled + an authenticated-only policy. This brings
-- shopify_sales_daily in line.
--
-- WHAT THIS DOES
-- --------------
-- 1. Enables Row-Level Security on the table.
-- 2. Adds an authenticated-full-access policy (mirrors inventory_events —
--    the dashboard talks to Supabase with each signed-in user's JWT, so this
--    keeps every existing read/write working with no app change).
-- 3. Belt-and-suspenders: revokes any anon-role grant on the table (matches
--    supabase_revoke_anon_grants.sql intent) and re-affirms the authenticated
--    grant. RLS is the real gate; the revoke just removes dead-weight access.
--
-- Deploying this does NOT break the dashboard — authenticated requests pass
-- the policy. No index.html change is needed.
-- ============================================================================

alter table shopify_sales_daily enable row level security;

-- authenticated full access (USING true + WITH CHECK true). Policy-create has
-- no IF NOT EXISTS in older Postgres, so guard via pg_policies.
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'shopify_sales_daily'
      and policyname = 'shopify_sales_daily_authenticated_all'
  ) then
    create policy shopify_sales_daily_authenticated_all
      on shopify_sales_daily for all to authenticated
      using (true) with check (true);
  end if;
end $$;

-- Defense in depth: anon should never touch this table.
revoke all on table shopify_sales_daily from anon;

-- Re-affirm the dashboard role's access (no-op if already granted).
grant select, insert, update, delete on table shopify_sales_daily to authenticated;

-- ============================================================================
-- Verify (should return rowsecurity = true, and one authenticated policy):
--   select relrowsecurity from pg_class where relname = 'shopify_sales_daily';
--   select policyname, roles, cmd from pg_policies
--   where tablename = 'shopify_sales_daily';
-- ============================================================================
