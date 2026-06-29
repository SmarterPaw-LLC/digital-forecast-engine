-- ============================================================================
-- Digital Sales Tracker — channel × month forecast vs actual (v6.78)
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- WHY
-- ----
-- Jason maintains a weekly-updated Excel tracker at
-- `Updated - SmarterPaw Digital Sales Tracker By Channel.xlsx`. The `LookerData`
-- sheet of that file is the normalized view — one row per (channel, year,
-- month) with Forecast + Actual revenue.
--
-- Channels are brand-and-region-specific labels: "Meow DTC", "Doggi Amazon CA
-- (USD)", "Kazoom Chewy", "Meow Wholesale (w/Faire)", etc. — 21 channels in
-- the current sheet covering 4 channel types (DTC / Amazon / Chewy /
-- Wholesale) and 3 brands (Meow / Doggi / Kazoom).
--
-- The new Digital Sales page lets Jason toggle between two data sources:
--   1. SPREADSHEET MODE (this table) — reads what he manually tracks; includes
--      channels we don't otherwise have data for (Wholesale via Faire).
--   2. LIVE MODE — aggregates sales_weekly + shopify_sales_daily +
--      walmart_sales_weekly to derive Actuals automatically. Forecast still
--      comes from this table.
--
-- Eventual plan: switch to pure-live once all channels have native sources.
-- ============================================================================

create table if not exists digital_sales_tracker (
  id              bigserial primary key,
  channel         text not null,                 -- 'Meow DTC', 'Doggi Amazon CA (USD)', …
  channel_type    text,                          -- 'DTC' | 'Amazon' | 'Chewy' | 'Wholesale'
  brand           text,                          -- 'Meow' | 'Doggi' | 'Kazoom' (sheet's labels, not products.brand)
  year            integer not null,
  month           integer not null,              -- 1..12
  forecast        numeric(12,2) default 0,
  actual          numeric(12,2) default 0,
  source          text default 'spreadsheet',
  uploaded_at     timestamptz default now()
);

create unique index if not exists digital_sales_tracker_uniq
  on digital_sales_tracker (channel, year, month);

create index if not exists digital_sales_tracker_year_idx
  on digital_sales_tracker (year, month);
create index if not exists digital_sales_tracker_brand_idx
  on digital_sales_tracker (brand, channel_type);

-- RLS (v6.47 hard rule — enable + policy on every new table).
alter table digital_sales_tracker enable row level security;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname='public' and tablename='digital_sales_tracker'
      and policyname='digital_sales_tracker_authenticated_all'
  ) then
    create policy digital_sales_tracker_authenticated_all
      on digital_sales_tracker for all to authenticated using (true) with check (true);
  end if;
end $$;
grant select, insert, update, delete on table digital_sales_tracker to authenticated;
grant usage, select on sequence digital_sales_tracker_id_seq to authenticated;
revoke all on table digital_sales_tracker from anon;

-- Verify (post-run):
--   select channel, channel_type, brand, count(*) months
--   from digital_sales_tracker
--   where year = extract(year from current_date)
--   group by 1,2,3 order by 2,3,1;
