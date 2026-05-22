-- ============================================================================
-- Add `fba_shipments` table
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.155.
-- ============================================================================
-- Stores inbound FBA shipment history — the source for "cadence learning"
-- (how often you ship + typical quantities per SKU). Built around the
-- per-shipment .tsv packing-list export (e.g. FBA19CJKP303.tsv) since the
-- account has no bulk "Inbound Shipment Items" report. Upload one file per
-- shipment; dedup is on (shipment_id, sku) so re-uploads are idempotent.
--
-- created_date is parsed from the shipment Name string
--   "FBA STA (04/29/2026 20:25)-MEM2"  →  2026-04-29
-- region is inferred from the destination FC (Canadian FCs start with a
-- Y-prefix airport code; everything else defaults US).
-- ============================================================================

create table if not exists fba_shipments (
  id                  bigserial primary key,
  shipment_id         text not null,
  shipment_name       text,
  created_date        date,
  ship_to             text,          -- destination fulfilment center (e.g. MEM2)
  master_id           text references products(master_id) on delete set null,
  sku                 text,
  asin                text,
  fnsku               text,
  quantity_shipped    int default 0,
  quantity_received   int default 0, -- not in the packing-list export; reserved for future
  status              text,
  region              text default 'US',
  uploaded_at         timestamptz default now(),
  unique (shipment_id, sku)
);

create index if not exists idx_fba_ship_master on fba_shipments(master_id);
create index if not exists idx_fba_ship_created on fba_shipments(created_date);
create index if not exists idx_fba_ship_asin on fba_shipments(asin);

alter table fba_shipments enable row level security;
drop policy if exists "fba_ship select" on fba_shipments;
drop policy if exists "fba_ship insert" on fba_shipments;
drop policy if exists "fba_ship update" on fba_shipments;
drop policy if exists "fba_ship delete" on fba_shipments;
create policy "fba_ship select" on fba_shipments for select using (auth.role() = 'authenticated');
create policy "fba_ship insert" on fba_shipments for insert with check (auth.role() = 'authenticated');
create policy "fba_ship update" on fba_shipments for update using (auth.role() = 'authenticated');
create policy "fba_ship delete" on fba_shipments for delete using (auth.role() = 'authenticated');
grant all on fba_shipments to authenticated;
grant usage, select on sequence fba_shipments_id_seq to authenticated;

-- Verify
--   select created_date, count(distinct shipment_id) as shipments,
--          sum(quantity_shipped) as units
--   from fba_shipments group by created_date order by created_date desc;
