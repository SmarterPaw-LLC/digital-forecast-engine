-- v8.96 — Amazon Ads Bulk Sheet snapshots + diff engine.
-- Stores the full state of every campaign / ad group / keyword / target /
-- negative from Amazon's Bulk Operations XLSX export. Uploading multiple
-- snapshots over time lets us DIFF them to produce a real change log —
-- unlike the v8.95 inferred model which had false positives from auto-bidding.
--
-- Data source: advertising.amazon.com/bulk-operations → Download campaigns.
-- File format: XLSX with 'Sponsored Products Campaigns' sheet.
-- Entity types seen: Campaign / Ad Group / Product Ad / Keyword /
-- Product Targeting / Negative Keyword / Negative Product Targeting /
-- Bidding Adjustment / Campaign Negative Keyword.

create table if not exists amazon_ads_bulk_upload (
  id uuid primary key default gen_random_uuid(),
  uploaded_at timestamptz not null default now(),
  uploaded_by text,
  filename text,
  snapshot_date date,          -- extracted from filename or user prompt
  region text not null default 'US',
  product text,                -- 'Sponsored Products' / 'Sponsored Brands'
  row_count int
);

create index if not exists amazon_ads_bulk_upload_date_idx on amazon_ads_bulk_upload(snapshot_date desc);

alter table amazon_ads_bulk_upload enable row level security;
create policy amazon_ads_bulk_upload_authenticated on amazon_ads_bulk_upload for all to authenticated using (true) with check (true);
grant select, insert, update, delete on amazon_ads_bulk_upload to authenticated;
revoke all on amazon_ads_bulk_upload from anon;

create table if not exists amazon_ads_bulk_snapshot (
  id bigserial primary key,
  upload_id uuid not null references amazon_ads_bulk_upload(id) on delete cascade,
  snapshot_date date,             -- denormalized for query speed

  -- Entity identity
  product text,                   -- 'Sponsored Products' / etc.
  entity text,                    -- 'Campaign' / 'Ad Group' / 'Keyword' / 'Product Targeting' / 'Product Ad' / 'Negative Keyword' / 'Negative Product Targeting' / 'Bidding Adjustment' / 'Campaign Negative Keyword'
  campaign_id text,
  ad_group_id text,
  portfolio_id text,
  ad_id text,
  keyword_id text,
  product_targeting_id text,

  -- Names for readable diff output
  campaign_name text,
  ad_group_name text,
  portfolio_name text,
  keyword_text text,

  -- Settings that we DIFF (skip performance metrics like impressions/clicks/spend)
  state text,                     -- enabled / paused / archived
  daily_budget numeric,
  bid numeric,
  ad_group_default_bid numeric,
  match_type text,                -- broad / phrase / exact
  bidding_strategy text,          -- legacyForSales / autoForSales / manual
  placement text,                 -- placementTop / placementProductPage / placementRestOfSearch
  percentage numeric,             -- for bidding adjustments
  product_targeting_expression text,
  targeting_type text,            -- Manual / Auto
  sku text,
  start_date text,
  end_date text,
  asin text                       -- from 'ASIN (Informational only)' column, useful for grouping
);

create index if not exists amazon_ads_bulk_snapshot_upload_idx on amazon_ads_bulk_snapshot(upload_id);
create index if not exists amazon_ads_bulk_snapshot_entity_idx on amazon_ads_bulk_snapshot(entity, campaign_id, ad_group_id, keyword_id, product_targeting_id, ad_id);
create index if not exists amazon_ads_bulk_snapshot_date_idx on amazon_ads_bulk_snapshot(snapshot_date desc);

alter table amazon_ads_bulk_snapshot enable row level security;
create policy amazon_ads_bulk_snapshot_authenticated on amazon_ads_bulk_snapshot for all to authenticated using (true) with check (true);
grant select, insert, update, delete on amazon_ads_bulk_snapshot to authenticated;
revoke all on amazon_ads_bulk_snapshot from anon;
