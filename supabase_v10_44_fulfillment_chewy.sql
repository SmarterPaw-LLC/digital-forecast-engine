-- v10.44 — Chewy fulfillment as a COGS building block.
--
-- Jason: "what is chewy pulling from for cogs? the cogs field is empty. we
-- should default chewy fulfilment to $.03"
--
-- Before this, `chewy_cogs` was the ONLY channel total with no building blocks
-- behind it, so it stayed null on every product and chewyPnlCogs() silently
-- fell back down the chain: chewy_cogs -> landed_cost -> dtc_cogs ->
-- amazon_cogs. The Chewy P&L and Break-Even were therefore costing Chewy units
-- at bare landed cost, with no fulfillment in them at all — which makes every
-- Chewy margin and every break-even ROAS read BETTER than reality.
--
-- With this column, chewy_cogs derives the same way amazon_cogs does:
--     chewy_cogs = landed_cost + fulfillment_chewy + production_labor
--
-- ⚠ DEFAULT 0.03 applies to EXISTING rows too (Postgres 11+ backfills a
-- non-volatile default on ADD COLUMN), which is the intent — $0.03 is the
-- fleet-wide starting point, overridable per product. The explicit UPDATE
-- below makes the file idempotent on a re-run and on any row that was
-- inserted with an explicit NULL.
--
-- Idempotent. Safe to re-run.

alter table product_cogs
  add column if not exists fulfillment_chewy numeric(12,4) default 0.03;

update product_cogs
   set fulfillment_chewy = 0.03
 where fulfillment_chewy is null;

comment on column product_cogs.fulfillment_chewy is
  'Per-unit cost to get the unit to Chewy (1P ship-to-DC). Building block: chewy_cogs = landed_cost + fulfillment_chewy + production_labor. Defaults to 0.03.';

-- No RLS / grant work needed: a new column on an existing table inherits both.
