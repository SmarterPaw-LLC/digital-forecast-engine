-- v8.46 — COGS Modeling: schedule one future revision per product.
-- Jason: "for the cogs page, i need to add the concept of COGS modeling.
-- We have current COGS inventory that we are changing suppliers at a
-- future date - so i need to be able to set, per product, an effective
-- date for new COGS cost."
--
-- Scope: ONE scheduled future revision per product (not a full timeline).
-- If the timeline pattern becomes necessary later, we upgrade to a
-- history table; v1 stays additive on product_cogs so the modal UX is
-- simple and no downstream reader has to know about time-varying values.
--
-- Adds 12 columns to product_cogs:
--   10 next_* cost fields (mirrors the current schema)
--   next_effective_date — date the future values kick in
--   next_note — free-text describing the change (e.g. "Switching to
--               Golden State Foods supplier — 3¢/unit cheaper landed")
--
-- Idempotent — safe to re-run.

alter table product_cogs
  add column if not exists next_landed_cost         numeric,
  add column if not exists next_fulfillment_amazon  numeric,
  add column if not exists next_fulfillment_dtc     numeric,
  add column if not exists next_overhead_dtc        numeric,
  add column if not exists next_shipping_cost       numeric,
  add column if not exists next_production_labor    numeric,
  add column if not exists next_amazon_cogs         numeric,
  add column if not exists next_amazon_cogs_eu      numeric,
  add column if not exists next_dtc_cogs            numeric,
  add column if not exists next_chewy_cogs          numeric,
  add column if not exists next_effective_date      date,
  add column if not exists next_note                text;

create index if not exists product_cogs_next_effective_idx
  on product_cogs (next_effective_date)
  where next_effective_date is not null;

comment on column product_cogs.next_effective_date is
  'v8.46 date the scheduled future COGS values take effect. When null, no future revision is scheduled.';
comment on column product_cogs.next_note is
  'v8.46 free-text note describing the scheduled change (e.g. "new supplier as of Nov 1").';
