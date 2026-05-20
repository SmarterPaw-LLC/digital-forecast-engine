-- ============================================================================
-- v4.147 — sales_weekly region + channel CHECK constraints: allow EU values
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- The original sales_weekly schema has CHECK constraints that whitelist the
-- allowed values for `region` (US / CA / MX) and `channel` (amazon_us /
-- amazon_ca / shopify / chewy). v4.144 started inserting EU rows with
-- region in {GB, DE, FR, IT, ES, NL} and channel in {amazon_gb, amazon_de,
-- amazon_fr, amazon_it, amazon_es, amazon_nl} — the existing constraints
-- reject those inserts with:
--   "new row for relation sales_weekly violates check constraint
--    sales_weekly_region_check"
--
-- This patch drops the constraints (under whatever names they have) and
-- re-adds them with the EU values included. Idempotent — safe to re-run.
-- ============================================================================

-- ── REGION ─────────────────────────────────────────────────────────────
do $$
declare cname text;
begin
  -- Find the current region CHECK constraint by name pattern.
  select conname into cname from pg_constraint
  where conrelid = 'sales_weekly'::regclass
    and contype  = 'c'
    and conname  ilike '%region%';
  if cname is not null then
    execute format('alter table sales_weekly drop constraint %I', cname);
  end if;
end $$;

alter table sales_weekly add constraint sales_weekly_region_check
  check (region in ('US', 'CA', 'MX', 'GB', 'DE', 'FR', 'IT', 'ES', 'NL'));

-- ── CHANNEL ────────────────────────────────────────────────────────────
do $$
declare cname text;
begin
  select conname into cname from pg_constraint
  where conrelid = 'sales_weekly'::regclass
    and contype  = 'c'
    and conname  ilike '%channel%';
  if cname is not null then
    execute format('alter table sales_weekly drop constraint %I', cname);
  end if;
end $$;

alter table sales_weekly add constraint sales_weekly_channel_check
  check (channel in (
    'amazon_us', 'amazon_ca', 'amazon_mx',
    'amazon_gb', 'amazon_de', 'amazon_fr', 'amazon_it', 'amazon_es', 'amazon_nl',
    'shopify',   'chewy'
  ));

-- Verify
--   select conname, pg_get_constraintdef(oid) from pg_constraint
--   where conrelid = 'sales_weekly'::regclass and contype = 'c';
