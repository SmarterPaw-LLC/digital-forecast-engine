-- v11.08 — Walmart catalog: the COST TO WALMART (our wholesale price).
--
-- Jason: "just build a tool and i'll upload to match each. we only need to do
-- this once ... the upload function should give a modal that matches the item
-- in the sheet to the item in the products table."
--
-- Source: our own sales ledger, "Walmart Items Sales YTD.xlsx" —
--   Customer ID · Name · Item ID · Item Description · Qty · Amount
-- Customer 253 = Walmart USA. One row per CASE SKU shipped year to date.
--
-- ⚠ THE FILE IS AT CASE GRAIN; `products` IS AT EACH GRAIN.
-- Jason: "its because these are case SKUs and not each SKUs, our system only
-- has each skus." So several rows map to ONE master_id — KC211 (24/case) and
-- KC211-01 (6/case) are the same fish toy, and MKC110 is a master case of
-- inner cases. Those are not competing costs; they are one cost at different
-- pack configurations, which the data confirms: KC211 reads $3.0942 per each
-- and KC211-01 reads $3.1092, a rounding difference on the case price.
--
-- ⚠ COST PER EACH IS DERIVED, NEVER AVERAGED ACROSS ROWS.
--     cost_per_each(master_id) = SUM(amount) / SUM(qty_cases * pack)
-- Averaging the row-level figures would weight a 1,428-case line the same as
-- a 70,560-each one. The view below does the weighting; nothing stores a
-- per-each number that could drift from the rows it came from.
--
-- `pack` is NOT reliably in the description ("MINI TUFFER - KEBAB - 24 PK/"
-- parses, "ZOOM STICKS MASTER CASE" does not), so the uploader asks for it
-- and stores what the operator confirmed. The crosswalk is the durable part:
-- once a case SKU is mapped, the next YTD file needs no manual step.
--
-- Idempotent — safe to re-run.

create table if not exists walmart_catalog (
  id                bigserial primary key,
  walmart_case_sku  text    not null,              -- OUR internal code: DC001 / KC210-01 / MKC110
  master_id         text    references products(master_id) on delete set null,
  item_description  text,                          -- as it appears on the ledger
  pack              integer,                       -- EACHES per case; null until confirmed
  qty_cases         numeric(14,2),                 -- cases shipped in the uploaded period
  amount            numeric(14,2),                 -- dollars invoiced for those cases
  -- Per-case price as invoiced. Stored because it is what the document says;
  -- per-each is derived in walmart_cost_per_each so the two cannot disagree.
  cost_per_case     numeric(12,4),
  is_fee_line       boolean default false,         -- KD001 "Walmart SideKick" @ $0.01 — not a product
  period_start      date,
  period_end        date,
  source            text    default 'walmart-items-sales-ytd',
  uploaded_at       timestamptz not null default now(),
  unique (walmart_case_sku)
);

create index if not exists walmart_catalog_master_idx
  on walmart_catalog(master_id) where master_id is not null;

-- The ONE place per-each cost is computed. Rows with no pack or no master_id
-- are excluded rather than defaulted, so an unmapped case SKU reads as absent
-- instead of silently contributing a wrong denominator.
create or replace view walmart_cost_per_each as
select
  w.master_id,
  sum(w.amount)                                            as amount,
  sum(w.qty_cases * w.pack)                                as eaches,
  round(sum(w.amount) / nullif(sum(w.qty_cases * w.pack), 0), 4) as cost_per_each,
  count(*)                                                 as case_skus,
  max(w.uploaded_at)                                       as uploaded_at
from walmart_catalog w
where w.master_id is not null
  and coalesce(w.is_fee_line, false) = false
  and w.pack > 0
  and w.qty_cases > 0
group by w.master_id;

-- RLS + grants (v6.47 hard rule).
alter table walmart_catalog enable row level security;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname='public' and tablename='walmart_catalog'
      and policyname='walmart_catalog_authenticated_all'
  ) then
    create policy walmart_catalog_authenticated_all
      on walmart_catalog for all to authenticated using (true) with check (true);
  end if;
end $$;
grant select, insert, update, delete on table walmart_catalog to authenticated;
grant usage, select on sequence walmart_catalog_id_seq to authenticated;
grant select on walmart_cost_per_each to authenticated;
revoke all on table walmart_catalog from anon;

-- Verify (post-run):
--   select count(*) from walmart_catalog;
--   select * from walmart_cost_per_each order by cost_per_each desc limit 10;
--   -- unmapped rows still needing a product:
--   select walmart_case_sku, item_description from walmart_catalog
--   where master_id is null and coalesce(is_fee_line,false) = false;
