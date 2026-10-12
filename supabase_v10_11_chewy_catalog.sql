-- v10.11 — Chewy vendor-portal catalog: the COST TO CHEWY (our wholesale price).
--
-- Jason: "i need to be able to upload this file - it's from chewy vendor
-- portal ... note that the purchase UOM indicates whether the Cost is by case
-- or each, so this needs to be factored into the chewy P&L"
--
-- Source: Chewy Vendor Portal → "Catalog Details" export. Despite the .csv
-- extension the file is UTF-16LE + TAB-delimited, with a junk spacer row
-- ABOVE the real header. Columns:
--   Chewy SKU · Chewy Parent Part Number · UPC · Brand · Vendor Part Number
--   · Item Name · Published · Discontinued · Discontinued Date
--   · Discontinued Reason · Cost · MSRP · MAP · Purchase UOM · MOQ
--   · Product URL
--
-- ⚠ `cost` IS QUOTED PER `purchase_uom`, NOT PER EACH.
-- On the sample export 106 of 127 rows are UOM='CS' (case) and 21 are 'EA'.
-- A case row's cost must be divided by the case pack to get a per-unit price
-- — e.g. CF007 cost 54.00/CS ÷ 12 = $4.50 each against a $9.99 MSRP.
-- The case pack is NOT in this file; it comes from `products.case_qty`
-- (v7.27). `moq` is a MINIMUM ORDER QUANTITY (1 / 6 / 24 on the sample) and
-- is NOT the case pack — do not substitute it.
--
-- One CURRENT row per Chewy SKU (upsert on re-upload). This is a catalog
-- state export, not a time series; if cost-change history is ever needed, add
-- a snapshot_date to the unique index the way chewy_forecasts does.
--
-- Idempotent — safe to re-run.

create table if not exists chewy_catalog (
  id                       bigserial primary key,
  master_id                text references products(master_id) on delete set null,
  chewy_sku                text not null,
  chewy_parent_part_number text,
  upc                      text,
  brand                    text,
  vendor_part_number       text,
  item_name                text,
  published                boolean,
  discontinued             boolean,
  discontinued_date        date,
  discontinued_reason      text,
  cost                     numeric(12,4),     -- per purchase_uom, NOT per each
  msrp                     numeric(12,2),
  map_price                numeric(12,2),     -- "MAP" is reserved-ish; renamed
  purchase_uom             text,              -- 'CS' | 'EA' (verbatim from Chewy)
  moq                      integer,           -- minimum order qty, NOT case pack
  product_url              text,
  uploaded_at              timestamptz not null default now()
);

-- One current row per Chewy SKU. Re-uploading the export refreshes in place.
create unique index if not exists chewy_catalog_uniq
  on chewy_catalog (chewy_sku);

create index if not exists chewy_catalog_master_idx
  on chewy_catalog (master_id);

create index if not exists chewy_catalog_vpn_idx
  on chewy_catalog (vendor_part_number);

-- RLS + grants — mirrors every other v4.60+ table (authenticated full access,
-- anon locked out per the v4.60 / v6.47 hard rule).
alter table chewy_catalog enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'chewy_catalog'
      and policyname = 'chewy_catalog_authenticated'
  ) then
    create policy "chewy_catalog_authenticated"
      on chewy_catalog
      for all
      to authenticated
      using (true)
      with check (true);
  end if;
end $$;

grant select, insert, update, delete on table chewy_catalog to authenticated;
grant usage, select on sequence chewy_catalog_id_seq to authenticated;
revoke all on table chewy_catalog from anon;

comment on table chewy_catalog is
  'Chewy Vendor Portal "Catalog Details" export. Added v10.11. `cost` is what Chewy pays us (our wholesale price) quoted per `purchase_uom` — divide by products.case_qty when purchase_uom = CS to get a per-unit price.';
comment on column chewy_catalog.cost is
  'Chewy''s cost = our wholesale price, PER purchase_uom. CS = per case (divide by products.case_qty); EA = per each.';
comment on column chewy_catalog.purchase_uom is
  'CS (case) or EA (each), verbatim from Chewy. Determines whether `cost` needs dividing by the case pack.';
comment on column chewy_catalog.moq is
  'Minimum order quantity from Chewy (1 / 6 / 24 observed). NOT the case pack — do not use it to normalise cost.';
comment on column chewy_catalog.map_price is
  'Chewy''s MAP (minimum advertised price). Column renamed from "MAP" to avoid confusion with the SQL/PG map-ish terminology.';
