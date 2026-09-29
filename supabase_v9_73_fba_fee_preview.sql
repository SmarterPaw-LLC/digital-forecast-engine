-- ============================================================================
-- Amazon FBA Fee Preview  (v9.73)
-- Run ONCE in Supabase -> SQL Editor.
-- ============================================================================
-- WHY
-- ----
-- The break-even ACOS model can show the FBA fee Amazon CHARGED, but not the
-- fee Amazon SAYS it should charge. That gap is where size-tier mis-measurement
-- hides, and it is the "Should be FBA Fee" column the financial-controls tool
-- asks for.
--
-- Amazon's Fee Preview report carries all of it: longest / median / shortest
-- side, length and girth, package weight, the assigned product size tier, and
-- Amazon's own expected fulfillment fee per unit. So no fee-tier lookup table
-- has to be built or maintained. Amazon publishes the answer.
--
-- Seller Central -> Reports -> Fulfillment -> Payments -> Fee Preview
--
-- IMPORTANT: this report is PER SELLER CENTRAL ACCOUNT. SmarterPaw runs one
-- account per brand, so a single export covers one brand only. Upload the
-- Meowijuana, Doggijuana and Kitty Ka-Zoom exports separately. A single file
-- CAN span marketplaces (the amazon-store column carries US / CA / ...), so
-- region is derived per row rather than picked at upload.
--
-- The file has no date column. The uploader prompts for a snapshot date so
-- successive pulls accumulate rather than overwrite, which lets fee changes
-- be tracked over time.
-- ============================================================================

create table if not exists fba_fee_preview (
  id                       bigserial primary key,
  snapshot_date            date not null,          -- picked at upload; report carries no date
  sku                      text not null,          -- merchant SKU (MSKU) - the report's true grain
  fnsku                    text,
  asin                     text,
  master_id                text references products(master_id) on delete set null,
  amazon_store             text,                   -- raw 'US' / 'CA' / ... from the report
  region                   text,                   -- normalized to match every other table
  product_name             text,
  product_group            text,
  brand                    text,                   -- Amazon's brand field
  fulfilled_by             text,                   -- 'Amazon' (AFN) vs merchant

  your_price               numeric(12,4),
  sales_price              numeric(12,4),

  -- dimensions + weight: the inputs the size tier is assigned from
  longest_side             numeric(12,4),
  median_side              numeric(12,4),
  shortest_side            numeric(12,4),
  length_and_girth         numeric(12,4),
  unit_of_dimension        text,
  item_package_weight      numeric(12,4),
  unit_of_weight           text,
  product_size_tier        text,

  currency                 text,

  -- current fee estimates
  estimated_fee_total                     numeric(12,4),
  estimated_referral_fee_per_unit         numeric(12,4),
  estimated_variable_closing_fee          numeric(12,4),
  estimated_order_handling_fee_per_order  numeric(12,4),
  estimated_pick_pack_fee_per_unit        numeric(12,4),
  estimated_weight_handling_fee_per_unit  numeric(12,4),
  expected_fulfillment_fee_per_unit       numeric(12,4),  -- <- "Should be FBA Fee"

  -- forward-looking fee estimates (populated by Amazon ahead of rate changes)
  estimated_future_fee                            numeric(12,4),
  estimated_future_order_handling_fee_per_order   numeric(12,4),
  estimated_future_pick_pack_fee_per_unit         numeric(12,4),
  estimated_future_weight_handling_fee_per_unit   numeric(12,4),
  expected_future_fulfillment_fee_per_unit        numeric(12,4),

  uploaded_at              timestamptz default now()
);

-- Plain-column unique index (NO coalesce) so upsert with onConflict works.
-- Architecture Rule #5: a functional unique index silently degrades upsert
-- into a plain insert and duplicates rows on every re-upload. sku is NOT NULL
-- and the parser skips blank-sku rows, so no coalesce is needed here.
create unique index if not exists fba_fee_preview_uniq
  on fba_fee_preview (sku, amazon_store, snapshot_date);

create index if not exists fba_fee_preview_asin_idx      on fba_fee_preview (asin);
create index if not exists fba_fee_preview_master_idx    on fba_fee_preview (master_id);
create index if not exists fba_fee_preview_snapshot_idx  on fba_fee_preview (snapshot_date desc);
create index if not exists fba_fee_preview_region_idx    on fba_fee_preview (region);

-- RLS + grants (v6.47 hard rule: every new table gets all three).
alter table fba_fee_preview enable row level security;

drop policy if exists fba_fee_preview_authenticated_all on fba_fee_preview;
create policy fba_fee_preview_authenticated_all
  on fba_fee_preview for all to authenticated
  using (true) with check (true);

grant select, insert, update, delete on table fba_fee_preview to authenticated;
grant usage, select on sequence fba_fee_preview_id_seq to authenticated;
revoke all on table fba_fee_preview from anon;
