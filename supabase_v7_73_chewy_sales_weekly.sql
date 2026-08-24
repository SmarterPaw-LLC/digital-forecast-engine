-- v7.73 — Chewy weekly actuals ingest table.
-- Separate from `chewy_forecasts` (forward-looking Chewy PO forecast) and
-- separate from `sales_weekly` (Amazon + Shopify actuals) because Chewy sends
-- extra dimensions (Autoship split, PDP OOS%) and the existing sales_weekly
-- unique index `(channel, asin, coalesce(shopify_sku,''), week_start)` would
-- collapse every Chewy row (asin=NULL, shopify_sku=NULL) to one key per week
-- — collisions across products.
--
-- Data source: Chewy "MJ_Sales_Snapshot_W_*.xlsx" — weekly rollup per SKU,
-- Mon→Sun weeks (matches app convention exactly, no timezone gymnastics).
-- Columns from Chewy: Brand · SKU (numeric) · Name · FY · Week Start Date
-- · Week End Date · Merch Sales · Units Sold · AS units sold · PDP OOS%.
--
-- Idempotent — safe to re-run.

create table if not exists chewy_sales_weekly (
  id              bigserial primary key,
  master_id       text references products(master_id) on delete cascade,
  chewy_sku       text not null,
  week_start      date not null,
  week_end        date,
  fy              integer,
  units_sold      integer not null default 0,
  autoship_units  integer not null default 0,
  merch_sales     numeric(12,2) not null default 0,
  pdp_oos_pct     numeric(6,3),
  region          text not null default 'US',
  uploaded_at     timestamptz not null default now(),
  check (upper(region) = 'US')     -- Chewy is US-only per SmarterPaw convention
);

-- Uniqueness: one row per (chewy_sku, week_start). Multiple weeks per SKU
-- coexist; re-uploading a week overwrites via delete+insert.
create unique index if not exists chewy_sales_weekly_uniq
  on chewy_sales_weekly (chewy_sku, week_start);

create index if not exists chewy_sales_weekly_master_idx
  on chewy_sales_weekly (master_id);

create index if not exists chewy_sales_weekly_week_idx
  on chewy_sales_weekly (week_start);

-- RLS + grants — mirrors every other v4.60+ table (authenticated full access,
-- anon locked out per v4.60 hard rule).
alter table chewy_sales_weekly enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'chewy_sales_weekly'
      and policyname = 'chewy_sales_weekly_authenticated'
  ) then
    create policy "chewy_sales_weekly_authenticated"
      on chewy_sales_weekly
      for all
      to authenticated
      using (true)
      with check (true);
  end if;
end $$;

grant select, insert, update, delete on table chewy_sales_weekly to authenticated;
grant usage, select on sequence chewy_sales_weekly_id_seq to authenticated;
revoke all on table chewy_sales_weekly from anon;

comment on table chewy_sales_weekly is
  'Chewy weekly sell-through actuals (Meowijuana + Doggijuana + KKZ as they arrive). Added v7.73. Distinct from chewy_forecasts (forward Chewy PO forecast) and sales_weekly (Amazon + Shopify actuals).';
comment on column chewy_sales_weekly.autoship_units is
  'Chewy Autoship (subscription) units — subset of units_sold. ~44% share on the initial Meowijuana snapshot; worth tracking as a subscription-retention indicator.';
comment on column chewy_sales_weekly.pdp_oos_pct is
  'Product Detail Page out-of-stock percentage for that week (Chewy-reported).';
