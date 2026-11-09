-- ============================================================================
-- Amazon Monthly Inventory Storage Fees  (v11.79)
-- Run ONCE in Supabase -> SQL Editor. Idempotent.
-- ============================================================================
-- WHY
-- ----
-- v11.72 measured it: 7 of 13 months report $0.00 storage, which is
-- impossible, because storage is a MONTHLY bill. US, by month:
--
--   2026-05 / 07 / 09 / 10   $0.00
--   2026-06                  $1,410.88
--   2026-08                  $476.14
--
-- Over May-Oct we report $1,887 against ~$5,844 implied by the volume
-- actually held, so we capture about a third - and October reads $0.00, the
-- month Amazon's rate triples. The real US figure is plausibly $20-30k, which
-- is the same order as the whole 5% fee target rather than a rounding error.
--
-- The cause is that `sku_economics.fba_storage_fee_total` is whatever the SKU
-- Economics report happened to carry for that week, and storage is not billed
-- weekly. This table is the actual bill: Seller Central -> Reports ->
-- Fulfilment -> Monthly Inventory Storage Fees (SP-API report type
-- GET_FBA_STORAGE_FEE_CHARGES_DATA), one row per SKU per month, with the
-- charged amount on it.
--
-- ============================================================================
-- /!\ THIS DOES NOT REPLACE sku_economics.fba_storage_fee_total
-- ============================================================================
-- Two feeds will now carry a number called "storage", which is exactly the
-- rule 3a trap. They are NOT the same measure and must never be summed:
--
--   sku_economics.fba_storage_fee_total   what the weekly econ report
--                                         attributed to that week. Partial,
--                                         and zero in most months.
--   amazon_storage_fees.estimated_monthly_storage_fee
--                                         the monthly bill for that SKU.
--
-- When the P&L reads this table for a month, it must STOP reading the other
-- one for the same month, or the month double-counts. Whichever consumer is
-- wired first owns that decision explicitly and says so on the label; see the
-- v11.70 Fees tab, which is where this lands.
--
-- ============================================================================
-- /!\ THE HEADER SPELLING IS NOT GUARANTEED, SO THE PARSER NORMALISES
-- ============================================================================
-- Amazon has shipped this report with hyphenated headers
-- (`average-quantity-on-hand`) and with underscored ones
-- (`average_quantity_on_hand`), and the set has grown over time (the
-- utilisation surcharge and the inventory-discount columns are recent). The
-- column names below are the NORMALISED form - lower case, underscores - and
-- the uploader maps onto them case-insensitively, treating `-` and `_` and a
-- space as the same character.
--
-- `extra jsonb` catches any header the uploader could not place, so the first
-- real file cannot silently drop a column we did not anticipate. It is a
-- STAGING AREA, not a home: anything that turns up in it gets promoted to a
-- real column in the next release, and the uploader reports what landed there
-- rather than swallowing it.
--
-- ============================================================================
-- /!\ THE GRAIN IS A MONTH, AND THE MONTH COMES FROM THE FILE
-- ============================================================================
-- Unlike walmart_ad_campaign (v11.25), this report DOES carry its own period:
-- `month_of_charge`. It is never supplied by the operator, so there is no
-- uploader prompt and no way to stamp the wrong month onto a file.
--
-- month_of_charge is stored as 'YYYY-MM' text, matching amazon_sp_search_term
-- and walmart_ad_campaign, so one `inWindow` rule covers every monthly feed.
-- charge_date is the DERIVED last day of that month, stored so anything that
-- wants a real date column has one.
--
-- ============================================================================
-- /!\ region, NOT country_code
-- ============================================================================
-- The file calls it `country_code`. Every other table here calls it `region`
-- and the whole app filters on that word, so it lands as `region` (rule #3:
-- reuse the app's vocabulary rather than importing a second one). The source
-- header is recorded in this comment so the mapping is not a mystery.
--
-- ============================================================================

create table if not exists amazon_storage_fees (
  id                               bigserial primary key,

  -- period
  month_of_charge                  text        not null,   -- 'YYYY-MM', from the file
  charge_date                      date,                   -- derived: last day of that month

  -- identity
  asin                             text,
  fnsku                            text,
  seller_sku                       text,
  product_name                     text,
  master_id                        text,                   -- resolved against products at upload
  region                           text        not null default 'US',  -- file: country_code
  fulfillment_center               text,

  -- what was held
  average_quantity_on_hand         numeric,
  average_quantity_pending_removal numeric,
  average_quantity_customer_orders numeric,
  estimated_total_item_volume      numeric,
  item_volume                      numeric,
  volume_units                     text,                   -- cubic feet / cubic metres
  product_size_tier                text,
  dangerous_goods_storage_type     text,

  -- dimensions, as the file reports them
  longest_side                     numeric,
  median_side                      numeric,
  shortest_side                    numeric,
  measurement_units                text,
  weight                           numeric,
  weight_units                     text,

  -- the bill
  base_rate                        numeric,
  utilization_surcharge_rate       numeric,
  storage_utilization_ratio        numeric,
  storage_utilization_ratio_units  text,
  currency                         text,
  estimated_monthly_storage_fee    numeric,                -- THE number this table exists for
  total_incremental_fee            numeric,
  breakdown_incentive_fee_discount numeric,
  eligible_for_inventory_discount  text,
  qualifies_for_inventory_discount text,

  -- anything the uploader could not place (see the header note)
  extra                            jsonb,

  uploaded_at                      timestamptz not null default now()
);

-- Columns added after the first run land here rather than in the create.
alter table amazon_storage_fees add column if not exists charge_date                      date;
alter table amazon_storage_fees add column if not exists master_id                        text;
alter table amazon_storage_fees add column if not exists seller_sku                       text;
alter table amazon_storage_fees add column if not exists average_quantity_customer_orders numeric;
alter table amazon_storage_fees add column if not exists utilization_surcharge_rate       numeric;
alter table amazon_storage_fees add column if not exists storage_utilization_ratio        numeric;
alter table amazon_storage_fees add column if not exists storage_utilization_ratio_units  text;
alter table amazon_storage_fees add column if not exists total_incremental_fee            numeric;
alter table amazon_storage_fees add column if not exists breakdown_incentive_fee_discount numeric;
alter table amazon_storage_fees add column if not exists eligible_for_inventory_discount  text;
alter table amazon_storage_fees add column if not exists qualifies_for_inventory_discount text;
alter table amazon_storage_fees add column if not exists dangerous_goods_storage_type     text;
alter table amazon_storage_fees add column if not exists extra                            jsonb;

-- ============================================================================
-- /!\ THE UNIQUE KEY INCLUDES fulfillment_center AND THE DG TYPE
-- ============================================================================
-- One SKU is charged separately per warehouse it sits in, and separately again
-- per dangerous-goods storage type, so (month, region, sku) is NOT unique and
-- an upsert on it would silently keep one row of several and under-report the
-- bill - the v11.72 defect in a new form. The coalesce chain keeps a file with
-- a blank fulfillment centre from collapsing every row onto one key.
create unique index if not exists amazon_storage_fees_uniq
  on amazon_storage_fees (
    month_of_charge, region,
    coalesce(fnsku, ''), coalesce(asin, ''), coalesce(seller_sku, ''),
    coalesce(fulfillment_center, ''), coalesce(dangerous_goods_storage_type, '')
  );

create index if not exists amazon_storage_fees_month_idx  on amazon_storage_fees (month_of_charge);
create index if not exists amazon_storage_fees_master_idx on amazon_storage_fees (master_id);
create index if not exists amazon_storage_fees_asin_idx   on amazon_storage_fees (asin);
create index if not exists amazon_storage_fees_up_idx     on amazon_storage_fees (uploaded_at desc);

comment on table amazon_storage_fees is
  'Amazon Monthly Inventory Storage Fees, one row per SKU per fulfilment centre per month. The actual bill. Never sum alongside sku_economics.fba_storage_fee_total for the same month - see supabase_v11_79_storage_fees.sql.';
comment on column amazon_storage_fees.estimated_monthly_storage_fee is
  'Amazon''s own figure for that SKU''s storage charge that month. "Estimated" is Amazon''s word, kept verbatim; it settles on the monthly statement.';
comment on column amazon_storage_fees.extra is
  'Headers the uploader could not place. A staging area, not a home: anything here is promoted to a real column in the next release.';
comment on column amazon_storage_fees.region is
  'The file calls this country_code. Stored under the app''s own word so one region filter covers every feed.';

-- ─────────────────────────── RLS ───────────────────────────
-- The app connects with the anon KEY but then SIGNS IN, so every statement it
-- runs arrives as `authenticated` - which is why the policy is written for
-- that role and not for anon. Same shape as every other table here.
alter table amazon_storage_fees enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'amazon_storage_fees'
      and policyname = 'amazon_storage_fees_authenticated_all'
  ) then
    create policy amazon_storage_fees_authenticated_all
      on amazon_storage_fees for all to authenticated using (true) with check (true);
  end if;
end $$;

grant select, insert, update, delete on table amazon_storage_fees to authenticated;
grant usage, select on sequence amazon_storage_fees_id_seq to authenticated;

-- Verify: rowsecurity = true and exactly one policy.
-- select tablename, rowsecurity from pg_tables
--   where schemaname='public' and tablename='amazon_storage_fees';
-- select tablename, policyname, roles from pg_policies
--   where schemaname='public' and tablename='amazon_storage_fees';
