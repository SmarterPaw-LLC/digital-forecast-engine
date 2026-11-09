-- ============================================================================
-- Amazon Monthly Inventory Storage Fees - the REAL column set  (v11.87)
-- Run ONCE in Supabase -> SQL Editor. Idempotent.
-- ============================================================================
-- WHY
-- ----
-- v11.79 built this table's column list WITHOUT a sample file, because there
-- was none on disk and Amazon does not publish the schema. It said so, and it
-- put `extra jsonb` underneath to catch whatever it got wrong.
--
-- Jason supplied a real September 2026 export (2,357 rows, US + CA). 28 of its
-- 34 columns matched. These are the six that did not.
--
-- ============================================================================
-- /!\ TWO OF THEM WERE MY NAMES, NOT AMAZON'S
-- ============================================================================
--   guessed                            actual
--   total_incremental_fee              total_incentive_fee_amount
--   breakdown_incentive_fee_discount   breakdown_incentive_fee_amount
--
-- And the second one is NOT NUMERIC. It reads `COVID-19:0.0057` - a label and
-- an amount in one field. Stored numeric it would have parsed to NULL on every
-- row that had one, silently, which is the exact class of defect this table
-- was created to fix. It is text.
--
-- The two guessed columns are DROPPED rather than left beside the real ones:
-- the table holds zero rows, so nothing is lost, and a column nobody writes is
-- a column someone later reads as empty-meaning-zero.
--
-- ============================================================================
-- /!\ AND FOUR COLUMNS SPLIT THE BILL IN A WAY WORTH HAVING
-- ============================================================================
--   est_base_msf        the base monthly storage fee
--   est_sus             the Storage Utilisation Surcharge
--   avg_qty_for_sus     the average quantity the surcharge was computed on
--   est_vol_for_sus     the volume it was computed on
--
-- Checked on all 2,357 rows of the real file:
--
--     est_base_msf + est_sus = estimated_monthly_storage_fee,  0 mismatches
--
-- That split is the point. The base fee is a rate on volume held and moves
-- only when the product or the stock does; the SURCHARGE is what you pay for
-- holding too much for too long, and it is avoidable. A single total cannot
-- tell those apart, which is what the Fees tab needs to rank by (v11.70's
-- lever vocabulary: `rate` versus `avoidable`).
--
-- On this file est_sus is 0.00 on every row - September is before the Q4
-- window. That is a fact about the month, not about the column.
-- ============================================================================

alter table amazon_storage_fees add column if not exists est_base_msf    numeric;
alter table amazon_storage_fees add column if not exists est_sus         numeric;
alter table amazon_storage_fees add column if not exists avg_qty_for_sus numeric;
alter table amazon_storage_fees add column if not exists est_vol_for_sus numeric;

alter table amazon_storage_fees add column if not exists total_incentive_fee_amount     numeric;
-- Text, not numeric: it carries `COVID-19:0.0057`, a label and an amount.
alter table amazon_storage_fees add column if not exists breakdown_incentive_fee_amount text;

-- The two guessed names. Safe to drop: the table has never held a row, and
-- `if exists` makes this a no-op on a database where they were never created.
alter table amazon_storage_fees drop column if exists total_incremental_fee;
alter table amazon_storage_fees drop column if exists breakdown_incentive_fee_discount;

comment on column amazon_storage_fees.est_base_msf is
  'The base monthly storage fee, before the utilisation surcharge. est_base_msf + est_sus = estimated_monthly_storage_fee (verified on 2,357 real rows).';
comment on column amazon_storage_fees.est_sus is
  'The Storage Utilisation Surcharge. The AVOIDABLE half of the bill: it is charged for holding too much for too long, where the base fee is a rate on volume held.';
comment on column amazon_storage_fees.breakdown_incentive_fee_amount is
  'TEXT, not numeric. Amazon writes a label and an amount together, e.g. COVID-19:0.0057.';
comment on column amazon_storage_fees.extra is
  'Headers the uploader could not place. A staging area, not a home. Emptied in v11.87 once a real file named the six it had been catching.';

-- Verify: the four new numerics, the text one, and the two guesses gone.
-- select column_name, data_type from information_schema.columns
--   where table_schema='public' and table_name='amazon_storage_fees'
--   and column_name in ('est_base_msf','est_sus','avg_qty_for_sus','est_vol_for_sus',
--                       'total_incentive_fee_amount','breakdown_incentive_fee_amount',
--                       'total_incremental_fee','breakdown_incentive_fee_discount')
--   order by 1;
