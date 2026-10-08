-- ════════════════════════════════════════════════════════════════════════════
-- v10.10 — supplier lead time + safety stock as PRODUCT-level defaults
-- ════════════════════════════════════════════════════════════════════════════
-- Jason: "I don't know where the lead time 60d is even set for the product
-- (it should be set on the product card)."
--
-- He could not find it because it was never set. `lead_time` lived only on
-- `inventory` (per asin × region, edited in the Inventory row editor), and when
-- it was null the status math silently substituted a hardcoded 60 days. The
-- same for safety stock at 14.
--
-- These two columns make the default real, visible and editable on the product
-- card. Resolution order, most specific first:
--
--     inventory.lead_time_days   (a single region overrides)
--  →  products.lead_time_days    (this column — the product's normal supplier terms)
--  →  60                         (built-in fallback, still, but now the tooltip says so)
--
-- ⚠ These drive the SUPPLIER → warehouse decision only: "Status by → Warehouse
-- stock" and "In-house production", where Reorder Point = lead + safety.
-- They are deliberately NOT part of Amazon FBA status. Sending stock you
-- already own to Amazon is a different decision with its own per-region
-- trigger, `reorder_threshold_days`. Before v10.10 the Amazon tier used
-- lead + safety, which is the bug this release fixes.
--
-- Run ONCE in Supabase → SQL Editor. Idempotent (add column if not exists), so
-- re-running is a no-op. Nothing is backfilled: a null here keeps today's
-- behaviour exactly (the 60 / 14 fallback), so no row changes tier until the
-- value is actually set.
-- ════════════════════════════════════════════════════════════════════════════

alter table products
  add column if not exists lead_time_days integer,
  add column if not exists safety_stock   integer;

comment on column products.lead_time_days is
  'v10.10 — supplier lead time in days (PO placed → stock in our warehouse), product-level default. inventory.lead_time_days overrides it per region; null falls back to 60. Drives Warehouse / In-house status only, NOT Amazon FBA (that uses reorder_threshold_days).';
comment on column products.safety_stock is
  'v10.10 — safety buffer in days added to lead time for the Reorder Point, product-level default. inventory.safety_stock overrides it per region; null falls back to 14.';

-- No RLS or GRANT changes needed: new columns on an existing table inherit the
-- policies and table-level grants already on `products`.

-- ── verify ──────────────────────────────────────────────────────────────────
-- select column_name, data_type, is_nullable
--   from information_schema.columns
--  where table_name = 'products' and column_name in ('lead_time_days','safety_stock');
--
-- -- which products still rely on the built-in fallback:
-- select master_id, short_name, lead_time_days, safety_stock
--   from products where active = true and lead_time_days is null order by short_name;
