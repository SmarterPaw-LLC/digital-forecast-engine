-- ============================================================================
-- Move `fulfillment_amazon` from inventory → products (master-level, v4.196)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v4.196.
-- ============================================================================
-- Supersedes v4.195. In practice every product is FBM in all regions or FBA
-- in all regions — the per-region storage we added in v4.195 was buying us
-- theoretical flexibility we'll never use. Moving the flag to products.* makes
-- it editable from BOTH the Product modal and the Inventory edit modal, and
-- gets rid of the MIXED-region tooltips that confused the UX.
--
-- Idempotent. Safe to run whether you ran v4.195 or not:
--   • If inventory.fulfillment_amazon exists, values are carried over to
--     products.fulfillment_amazon (any FBM in any region → product is FBM)
--     then the inventory column is dropped.
--   • If it doesn't exist, products gets the default 'FBA' for all rows.
-- ============================================================================

-- 1. Add the new column on products (master-level).
alter table products add column if not exists fulfillment_amazon text default 'FBA';
update products set fulfillment_amazon = 'FBA' where fulfillment_amazon is null;

-- 2. Migrate any per-region values we set in v4.195. Rule: if ANY region of
--    the master_id was FBM, the product is FBM. (Practically all-or-nothing
--    anyway for Jason's catalog.)
do $$ begin
  if exists (
    select 1 from information_schema.columns
    where table_name = 'inventory' and column_name = 'fulfillment_amazon'
  ) then
    update products p
    set fulfillment_amazon = 'FBM'
    from inventory i
    where i.master_id = p.master_id
      and upper(i.fulfillment_amazon) = 'FBM';
    -- 3. Drop the old per-region column.
    alter table inventory drop constraint if exists inventory_fulfillment_amazon_chk;
    alter table inventory drop column if exists fulfillment_amazon;
  end if;
end $$;

-- 4. Add a check constraint to products.fulfillment_amazon.
do $$ begin
  if not exists (
    select 1 from pg_constraint where conname = 'products_fulfillment_amazon_chk'
  ) then
    alter table products add constraint products_fulfillment_amazon_chk
      check (upper(fulfillment_amazon) in ('FBA', 'FBM'));
  end if;
end $$;

-- Verify
--   select fulfillment_amazon, count(*) from products group by 1;
