-- ============================================================================
-- Add `fba_shipment_summaries` table
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.167.
-- ============================================================================
-- Stores the SHIPMENT-LEVEL rollup from the "Inbound Shipments" CSV export
-- (Manage FBA Shipments → Download CSV of the shipments LIST).
--
-- Different from `fba_shipments` which stores per-SKU line-item detail from
-- the per-shipment .tsv packing-list. Summary CSV gives us:
--   • Units expected vs Units located  → shrinkage / extras / claims
--   • Status (Closed / Receiving / Working)  → in-flight tracking
--   • Last updated date  → when Amazon last touched the shipment
--
-- Joined to fba_shipments on shipment_id for the FBA Shipments viewer.
-- ============================================================================

create table if not exists fba_shipment_summaries (
  shipment_id      text primary key,
  shipment_name    text,
  created_date     date,
  last_updated     date,
  ship_to          text,
  region           text default 'US',
  sku_count        int,
  units_expected   int default 0,
  units_located    int default 0,
  status           text,
  uploaded_at      timestamptz default now()
);

create index if not exists idx_fba_ship_sum_created on fba_shipment_summaries(created_date);
create index if not exists idx_fba_ship_sum_status on fba_shipment_summaries(status);

alter table fba_shipment_summaries enable row level security;
drop policy if exists "fba_ship_sum select" on fba_shipment_summaries;
drop policy if exists "fba_ship_sum insert" on fba_shipment_summaries;
drop policy if exists "fba_ship_sum update" on fba_shipment_summaries;
drop policy if exists "fba_ship_sum delete" on fba_shipment_summaries;
create policy "fba_ship_sum select" on fba_shipment_summaries for select using (auth.role() = 'authenticated');
create policy "fba_ship_sum insert" on fba_shipment_summaries for insert with check (auth.role() = 'authenticated');
create policy "fba_ship_sum update" on fba_shipment_summaries for update using (auth.role() = 'authenticated');
create policy "fba_ship_sum delete" on fba_shipment_summaries for delete using (auth.role() = 'authenticated');
grant all on fba_shipment_summaries to authenticated;

-- Verify
--   select status, count(*) shipments, sum(units_expected) expected,
--          sum(units_located) located, sum(units_expected - units_located) lost
--   from fba_shipment_summaries group by status;
