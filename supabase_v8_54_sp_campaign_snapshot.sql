-- v8.54 — Sponsored Products Campaign snapshot for auction diagnostics.
-- Jason: "i cannot be clicking into screens for 15 products" — needs a
-- batch upload path for campaign-level impression share diagnostics so
-- he can see across the whole catalog which products are budget-throttled,
-- which are bid-constrained, and which have unclaimed auction slack.
--
-- Source: advertising.amazon.com → Campaigns → filter to Sponsored Products,
-- customize columns to include impression share metrics, then download
-- (CSV or XLSX). The export is campaign-level (one row per campaign,
-- aggregated across the visible date range).
--
-- One row per (campaign_name, advertiser_account_name, region, reporting_month).
-- reporting_month is the last day of the window the export covered — the
-- uploader prompts for the date. Amazon exports aggregate across the range,
-- so re-downloading a longer/shorter range doesn't collide because we key
-- by the month the user assigns.
--
-- Idempotent — safe to re-run.

create table if not exists amazon_sp_campaign_snapshot (
  id                             bigserial primary key,
  campaign_name                  text not null,
  campaign_id                    text,
  advertiser_account_name        text,
  region                         text default 'US',
  ad_product                     text default 'sponsored_products',
  reporting_month                text not null,   -- YYYY-MM
  reporting_date                 date,             -- last day of the range for reference
  status                         text,             -- Enabled / Paused / Archived
  daily_budget                   numeric,
  spend                          numeric,
  impressions                    integer,
  clicks                         integer,
  ctr_pct                        numeric,
  cpc                            numeric,
  sales                          numeric,
  orders                         integer,
  units_sold                     integer,
  acos_pct                       numeric,
  roas                           numeric,
  -- Auction diagnostics — the whole point of this table.
  impression_share_pct                    numeric,
  top_of_search_impression_share_pct      numeric,
  impression_share_lost_to_budget_pct     numeric,
  impression_share_lost_to_rank_pct       numeric,
  -- Free-form JSON stash for any columns Amazon adds later.
  raw_extra                      jsonb,
  currency                       text default 'USD',
  uploaded_at                    timestamptz default now()
);

create unique index if not exists amazon_sp_campaign_snapshot_uniq
  on amazon_sp_campaign_snapshot (
    coalesce(campaign_id, ''),
    coalesce(campaign_name, ''),
    coalesce(advertiser_account_name, ''),
    region,
    reporting_month
  );

create index if not exists amazon_sp_campaign_snapshot_month_idx
  on amazon_sp_campaign_snapshot (reporting_month);

alter table amazon_sp_campaign_snapshot enable row level security;

drop policy if exists amazon_sp_campaign_snapshot_all on amazon_sp_campaign_snapshot;
create policy amazon_sp_campaign_snapshot_all
  on amazon_sp_campaign_snapshot for all
  to authenticated
  using (true) with check (true);

grant select, insert, update, delete on amazon_sp_campaign_snapshot to authenticated;
grant usage, select on sequence amazon_sp_campaign_snapshot_id_seq to authenticated;
revoke all on amazon_sp_campaign_snapshot from anon;

comment on table amazon_sp_campaign_snapshot is
  'v8.54 SP campaign-level snapshot for impression share auction diagnostics. One row per campaign per reporting_month. Sourced from advertising.amazon.com Campaign Manager column export.';
comment on column amazon_sp_campaign_snapshot.impression_share_lost_to_budget_pct is
  'Direct signal for budget throttling — if >30%, campaign is capping out before end of day.';
comment on column amazon_sp_campaign_snapshot.impression_share_lost_to_rank_pct is
  'Direct signal for bid competitiveness — if >50%, bids are losing the auction to competitors.';
