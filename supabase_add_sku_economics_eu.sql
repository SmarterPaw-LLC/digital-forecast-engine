-- ============================================================================
-- Add `sku_economics_eu` table + `amazon_cogs_eu` column on product_cogs
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.139.
-- ============================================================================
-- Hosts Amazon EU SKU Economics data (GB / DE / FR / IT / ES / NL markets).
-- Kept separate from `sku_economics` because:
--   • Fee taxonomy differs (Digital Services Fees, Fuel surcharge — no US
--     parallel; conversely no Inbound/Aged/Removal/Storage Util in EU).
--   • Native currencies are GBP + EUR, not CAD/USD.
--   • week_start is the report's native Sunday (Sun-Sat), NOT Monday-shifted
--     like sku_economics. Isolated to this table, documented in the column.
--
-- Also adds `amazon_cogs_eu` to product_cogs so EU shipments can carry a
-- distinct COGS (EU freight + import duties differ from US/CA fulfillment).
-- ============================================================================

create table if not exists sku_economics_eu (
  id                                            bigserial primary key,
  master_id                                     text references products(master_id) on delete cascade,
  asin                                          text not null,
  region                                        text not null,    -- 'GB' | 'DE' | 'FR' | 'IT' | 'ES' | 'NL'
  week_start                                    date not null,    -- Sunday (Amazon EU report's native start)
  currency                                      text not null,    -- 'GBP' | 'EUR'
  parent_asin                                   text,
  fnsku                                         text,
  msku                                          text,
  -- Volume + revenue
  average_sales_price                           numeric default 0,
  units_sold                                    numeric default 0,
  units_returned                                numeric default 0,
  net_units_sold                                numeric default 0,
  gross_sales                                   numeric default 0,
  net_sales                                     numeric default 0,
  -- Fee lines (EU-specific set per the v4.139 weekly report format)
  base_fulfilment_fee_total                     numeric default 0,
  digital_services_fee_fba_fulfilment_total     numeric default 0,
  digital_services_fee_selling_total            numeric default 0,
  fuel_logistics_surcharge_total                numeric default 0,
  fba_fulfilment_fees_total                     numeric default 0,
  referral_fee_total                            numeric default 0,
  sponsored_products_total                      numeric default 0,
  -- Amazon's pre-computed bottom line (present in EU report; absent from US/CA)
  net_proceeds_total                            numeric default 0,
  net_proceeds_per_unit                         numeric default 0,
  source                                        text default 'eu_sku_economics',
  uploaded_at                                   timestamptz default now(),
  unique (asin, region, week_start)
);

create index if not exists idx_skuecon_eu_master      on sku_economics_eu(master_id);
create index if not exists idx_skuecon_eu_region_week on sku_economics_eu(region, week_start);

-- ──────────────────────────────────────────────────────────────────────────
-- RLS + grants — mirrors the auth setup pattern for all other data tables.
-- ──────────────────────────────────────────────────────────────────────────
alter table sku_economics_eu enable row level security;

drop policy if exists "sku_economics_eu select" on sku_economics_eu;
drop policy if exists "sku_economics_eu insert" on sku_economics_eu;
drop policy if exists "sku_economics_eu update" on sku_economics_eu;
drop policy if exists "sku_economics_eu delete" on sku_economics_eu;

create policy "sku_economics_eu select" on sku_economics_eu for select using (auth.role() = 'authenticated');
create policy "sku_economics_eu insert" on sku_economics_eu for insert with check (auth.role() = 'authenticated');
create policy "sku_economics_eu update" on sku_economics_eu for update using (auth.role() = 'authenticated');
create policy "sku_economics_eu delete" on sku_economics_eu for delete using (auth.role() = 'authenticated');

grant all on sku_economics_eu to authenticated;
grant usage, select on sequence sku_economics_eu_id_seq to authenticated;

-- ──────────────────────────────────────────────────────────────────────────
-- product_cogs — add EU COGS dimension + dismissal flag (mirrors the v4.64
-- amazon_cogs / dtc_cogs / chewy_cogs pattern).
-- ──────────────────────────────────────────────────────────────────────────
alter table product_cogs add column if not exists amazon_cogs_eu     numeric;
alter table product_cogs add column if not exists amazon_eu_dismissed boolean default false;

-- Verify
--   select count(*) as eu_rows from sku_economics_eu;
--   select master_id, amazon_cogs, amazon_cogs_eu from product_cogs limit 5;
