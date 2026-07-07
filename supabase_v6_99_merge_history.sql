-- ============================================================================
-- Merge History + Undo (v6.99)
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- Every runMerge() call now writes a row here BEFORE the destructive parts of
-- the merge complete. `runUndoMerge(id)` reads the row and reverses the whole
-- operation:
--   1. Restores the duplicate product row from src_product_snapshot.
--   2. Reverts survivor's backfilled fields from tgt_product_before.
--   3. Reverses per-table master_id UPDATEs by row-PK (reassigned_ids).
--   4. Re-inserts destructively-removed rows (inventory / BOM /
--      product_cogs) from deleted_rows.
--   5. Marks the history row reversed=true so a second undo attempt fails
--      cleanly with a clear error message.
--
-- Snapshots are stored as JSONB so schema changes on the underlying tables
-- don't retroactively break the ability to undo old merges (worst case:
-- unknown columns are ignored on insert).
-- ============================================================================

create table if not exists merge_history (
  id                     bigserial primary key,
  merged_at              timestamptz not null default now(),
  merged_by              text,                            -- auth.email() at merge time
  src_master_id          text not null,                   -- the duplicate that was deleted
  src_title              text,
  tgt_master_id          text not null,                   -- the survivor that was kept
  tgt_title              text,
  -- Full JSON of the source product row as it existed pre-delete.
  -- Restored on undo via INSERT.
  src_product_snapshot   jsonb not null,
  -- Full JSON of the target product row BEFORE the backfill patch was applied.
  -- Used to compute the revert-patch: for every field in tgt_backfill_patch,
  -- write tgt_product_before[field] back onto the survivor.
  tgt_product_before     jsonb not null,
  -- The patch dict we applied to the survivor (asin, image_url, etc.).
  -- Redundant with tgt_product_before but makes the revert logic direct.
  tgt_backfill_patch     jsonb,
  -- {tablename: [row_pk_ids]} — which rows had their master_id (or
  -- bundle_master_id / component_master_id for bom) updated FROM
  -- src.master_id TO tgt.master_id. On undo we UPDATE those specific
  -- rows back to src.master_id.
  reassigned_ids         jsonb,
  -- {tablename: [row_json_full]} — rows that were destructively removed
  -- during merge. On undo, re-INSERT these back. Covers:
  --   • inventory       — deleted for src pre-delete
  --   • bom_src_bundle  — deleted when tgt won the BOM tiebreak
  --   • bom_src_component — reassigned; snapshotted for defensive rollback
  --   • bom_tgt_bundle  — deleted when src won the BOM tiebreak
  --   • product_cogs_src — merged in / deleted; snapshotted before write
  --   • product_cogs_tgt_before — snapshotted for null-restore
  deleted_rows           jsonb,
  -- Toggle set true when runUndoMerge succeeds. Prevents double-undo.
  reversed               boolean not null default false,
  reversed_at            timestamptz,
  reversed_by            text
);

create index if not exists idx_merge_history_at  on merge_history(merged_at desc);
create index if not exists idx_merge_history_src on merge_history(src_master_id);
create index if not exists idx_merge_history_tgt on merge_history(tgt_master_id);

-- RLS + grants — mirror every other data table (v6.47 hard rule).
alter table merge_history enable row level security;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname='public' and tablename='merge_history'
      and policyname='merge_history_authenticated_all'
  ) then
    create policy merge_history_authenticated_all
      on merge_history for all to authenticated using (true) with check (true);
  end if;
end $$;
grant select, insert, update, delete on table merge_history to authenticated;
grant usage, select on sequence merge_history_id_seq to authenticated;
revoke all on table merge_history from anon;

-- Verify (post-run):
--   select id, merged_at, src_master_id, tgt_master_id, reversed from merge_history order by merged_at desc limit 20;
