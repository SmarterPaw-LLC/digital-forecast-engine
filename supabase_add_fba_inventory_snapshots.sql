-- ============================================================================
-- Add `fba_inventory_snapshots` table
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.154.
-- ============================================================================
-- Stores point-in-time snapshots of the Amazon "Manage FBA Inventory" report
-- (the afn-* columns). Uploaded on a cadence (weekly) so the dashboard can
-- chart inventory burn-down over time and track inbound→fulfillable
-- transitions. The report has no internal date, so the uploader prompts for
-- a snapshot_date (defaults to upload day).
--
-- Region is prompted at upload (US/CA) since the report is per-marketplace
-- and carries no region column. Brand is prompted only to assign newly
-- auto-created SP-TEMP products for ASINs not yet in the catalog.
-- ============================================================================

create table if not exists fba_inventory_snapshots (
  id                              bigserial primary key,
  snapshot_date                   date not null,
  master_id                       text references products(master_id) on delete cascade,
  sku                             text,
  fnsku                           text,
  asin                            text not null,
  region                          text not null default 'US',   -- 'US' | 'CA'
  -- afn-* position fields (Amazon Fulfilled Network)
  mfn_fulfillable_quantity        int default 0,   -- merchant-fulfilled backup stock
  afn_warehouse_quantity          int default 0,
  afn_fulfillable_quantity        int default 0,   -- AVAILABLE TO SELL (key metric)
  afn_unsellable_quantity         int default 0,
  afn_reserved_quantity           int default 0,
  afn_total_quantity              int default 0,
  afn_inbound_working_quantity    int default 0,
  afn_inbound_shipped_quantity    int default 0,
  afn_inbound_receiving_quantity  int default 0,
  afn_researching_quantity        int default 0,
  afn_reserved_future_supply      int default 0,
  afn_future_supply_buyable       int default 0,
  uploaded_at                     timestamptz default now(),
  unique (asin, region, snapshot_date)
);

create index if not exists idx_fba_snap_master  on fba_inventory_snapshots(master_id);
create index if not exists idx_fba_snap_date     on fba_inventory_snapshots(snapshot_date);
create index if not exists idx_fba_snap_asin_reg on fba_inventory_snapshots(asin, region);

-- RLS + grants — mirror every other data table.
alter table fba_inventory_snapshots enable row level security;
drop policy if exists "fba_snap select" on fba_inventory_snapshots;
drop policy if exists "fba_snap insert" on fba_inventory_snapshots;
drop policy if exists "fba_snap update" on fba_inventory_snapshots;
drop policy if exists "fba_snap delete" on fba_inventory_snapshots;
create policy "fba_snap select" on fba_inventory_snapshots for select using (auth.role() = 'authenticated');
create policy "fba_snap insert" on fba_inventory_snapshots for insert with check (auth.role() = 'authenticated');
create policy "fba_snap update" on fba_inventory_snapshots for update using (auth.role() = 'authenticated');
create policy "fba_snap delete" on fba_inventory_snapshots for delete using (auth.role() = 'authenticated');
grant all on fba_inventory_snapshots to authenticated;
grant usage, select on sequence fba_inventory_snapshots_id_seq to authenticated;

-- Verify
--   select snapshot_date, region, count(*) from fba_inventory_snapshots
--   group by snapshot_date, region order by snapshot_date desc;
