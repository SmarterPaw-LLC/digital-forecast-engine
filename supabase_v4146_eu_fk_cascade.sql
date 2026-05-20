-- ============================================================================
-- v4.146 — sku_economics_eu.master_id FK → ON DELETE CASCADE
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- The v4.139 migration created the FK with default NO ACTION semantics, which
-- means deleting a product blocks if any sku_economics_eu rows still reference
-- it. v4.145 patched the merge tool to manually reassign the FK before
-- deleting the duplicate; v4.146 fixes the schema so direct product deletes
-- (Products tab → Delete button) also work without manual cleanup.
--
-- Fresh installs from v4.146 onward get CASCADE built in via the updated
-- `supabase_add_sku_economics_eu.sql`. This patch is only needed if you
-- previously ran the original v4.139 version.
--
-- Idempotent — safe to re-run. Drops the constraint if present (under any
-- existing name) and re-adds it with the correct cascade behavior.
-- ============================================================================

do $$
declare
  cname text;
begin
  -- Find any existing FK from sku_economics_eu.master_id → products.master_id,
  -- regardless of the constraint name (Postgres sometimes auto-renames).
  select conname into cname
  from pg_constraint c
  join pg_class t on t.oid = c.conrelid
  where t.relname = 'sku_economics_eu'
    and c.contype = 'f'
    and 'master_id' = any (
      select attname from pg_attribute
      where attrelid = c.conrelid and attnum = any (c.conkey)
    );
  if cname is not null then
    execute format('alter table sku_economics_eu drop constraint %I', cname);
  end if;
end $$;

alter table sku_economics_eu
  add constraint sku_economics_eu_master_id_fkey
  foreign key (master_id) references products(master_id) on delete cascade;

-- Verify
--   select conname, confdeltype from pg_constraint
--   where conrelid = 'sku_economics_eu'::regclass and contype = 'f';
--   -- confdeltype = 'c' means ON DELETE CASCADE ✓
