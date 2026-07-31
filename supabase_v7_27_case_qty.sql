-- ============================================================================
-- Products: case_qty (units per case) — v7.27
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- Per-product "how many units are in a case" so the in-house production team
-- can plan by cases (their actual pack-out unit). Exposed on the Inventory
-- Planning table via new opt-in columns "Case Qty" + "Cases Needed" + "Units
-- Needed", and in the CSV export alongside the weekly needs breakdown.
--
-- Nullable — products without a case_qty just don't get a Cases Needed value
-- (Cases Needed cell shows "—"). No default because there's no sensible fleet-
-- wide default; case sizes vary widely (30 sprays vs 144 catnip cigars).
-- ============================================================================

alter table products
  add column if not exists case_qty integer;

comment on column products.case_qty is
  'Units per case for production pack-out (v7.27). Drives the Cases Needed column on Inventory Planning + the in-house production CSV export. Nullable when unknown / not applicable.';

-- Verify (post-run):
--   select brand, count(*) filter (where case_qty is not null) as with_case,
--          count(*) filter (where case_qty is null)     as missing_case
--   from products
--   where active = true
--   group by brand
--   order by brand;
