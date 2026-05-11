-- ============================================================================
-- product_cogs — Per-channel COGS lookup table
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- Replaces the single `products.cogs` column with a separate table holding
-- per-channel COGS values (Amazon, DTC/Shopify, Chewy). One row per product;
-- `master_id` is both PK and FK to `products`. Existing `products.cogs` values
-- are backfilled into `amazon_cogs` (every COGS recorded so far has come from
-- Amazon's SKU Economics report). `products.cogs` is KEPT but no longer read
-- by the dashboard — kept as a fallback / backup; can be dropped later.
-- ============================================================================

create table if not exists product_cogs (
  master_id    text primary key references products(master_id) on delete cascade,
  amazon_cogs  numeric(10,4),
  dtc_cogs     numeric(10,4),
  chewy_cogs   numeric(10,4),
  updated_at   timestamptz default now(),
  updated_by   uuid references auth.users on delete set null
);

create index if not exists product_cogs_amazon_idx on product_cogs(master_id) where amazon_cogs is not null;
create index if not exists product_cogs_dtc_idx    on product_cogs(master_id) where dtc_cogs    is not null;
create index if not exists product_cogs_chewy_idx  on product_cogs(master_id) where chewy_cogs  is not null;

-- Backfill: create one product_cogs row per product (1:1 with products).
-- Existing products.cogs values land in amazon_cogs. Products without a COGS
-- value get a row anyway with amazon_cogs=null — that way the table mirrors
-- products exactly and the COGS page UI is consistent. Re-runs are safe: the
-- on-conflict clause only updates rows that don't already have amazon_cogs set,
-- so any values entered post-migration are preserved.
insert into product_cogs (master_id, amazon_cogs, updated_at)
select master_id, cogs, now()
from products
on conflict (master_id) do update
  set amazon_cogs = coalesce(product_cogs.amazon_cogs, excluded.amazon_cogs),
      updated_at  = now();

-- Trigger: maintain updated_at + updated_by on each modification.
create or replace function bump_product_cogs_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end;
$$;

drop trigger if exists product_cogs_updated_at on product_cogs;
create trigger product_cogs_updated_at
  before insert or update on product_cogs
  for each row execute function bump_product_cogs_updated_at();

-- RLS — authenticated users have full access (matches the rest of the app).
alter table product_cogs enable row level security;
drop policy if exists "authenticated full access" on product_cogs;
create policy "authenticated full access" on product_cogs
  for all to authenticated using (true) with check (true);

-- Sequence grant safety (no sequences here since master_id is text, but stays
-- consistent with the rest of the schema's setup).

-- ──────────────────────────────────────────────────────────────────────────
-- Verify:
--   select count(*) from product_cogs;
--   select count(*) from product_cogs where amazon_cogs is not null;
-- ============================================================================
