-- ============================================================================
-- Walmart Connect ads feed  (v11.25)
-- Run ONCE in Supabase -> SQL Editor. Idempotent.
-- ============================================================================
-- WHY
-- ----
-- The Ads sub-tab exists on the Amazon and Chewy P&Ls and has had nothing to
-- show on Walmart, because there was no ads feed at all. Jason exported the
-- two Walmart Connect Ad Center downloads (the cloud icon above each table on
-- /sp/view/allcampaigns and /sp/view/allkeywords), which is what this pair of
-- tables is shaped from.
--
-- ============================================================================
-- /!\ THE GRAIN IS MONTHLY, AND THE FILE DOES NOT SAY WHICH MONTH
-- ============================================================================
-- Neither export carries a reporting date. The campaign file has Start Date
-- and End Date, but those are the CAMPAIGN's own schedule ("2026-03-25" /
-- "No end date"), not the window the metrics cover. The keyword file has no
-- date column whatsoever. Every row is one aggregate over whatever range the
-- console's date picker happened to be set to when the file was downloaded.
--
-- So reporting_month is supplied BY THE OPERATOR at upload time and stamped
-- onto every row. Jason: "i'll have to indicate in the uploader what month the
-- report is for."
--
-- This is the amazon_sp_search_term shape, not the amazon_ad_spend shape, and
-- it carries the same consequence: a daily period control cannot filter this
-- feed precisely. A month is IN when it OVERLAPS the window, and the coverage
-- line states which months it resolved to. See ADS_CHANNELS.walmart.inWindow.
--
-- reporting_date is the period END (the last day of reporting_month), stored
-- so anything that wants a real date column has one. It is DERIVED, never
-- read from the file, because the file has nothing to derive it from.
--
-- ============================================================================
-- /!\ OMNI IS A SECOND SALES BASIS, NOT A BIGGER VERSION OF THE FIRST
-- ============================================================================
-- Walmart attributes IN-STORE purchases back to an online ad click, which
-- neither Amazon nor Chewy report. The export carries both bases side by side:
--
--   Total Attributed Sales / Orders / Units Sold   online only
--   In-Store Attributed Sales / Orders / Units     physical stores
--   RoAS                                           online sales / spend
--   Omni ROAS                                      (online + in-store) / spend
--
-- They are stored as separate columns rather than summed, because summing
-- would destroy the only thing that makes the distinction readable: on the
-- September file, SBV reports 2.19 RoAS and 2.40 Omni ROAS, and the gap IS the
-- in-store contribution. A single blended figure would silently change what
-- "ROAS" means on this one channel (rule 3a).
--
-- `Omni ROAS` is Walmart's own word for it and is reused verbatim rather than
-- coining a new one (rule #3).
--
-- ============================================================================
-- /!\ A KEYWORD WITH NO DELIVERY HAS BLANK METRICS, NOT ZERO
-- ============================================================================
-- 132 of the 189 rows in the September keyword export have EMPTY metric cells
-- rather than 0 -- newly added targets that have not served yet. Those are
-- real, enabled keywords carrying a real bid, so they are kept (the bid is the
-- reason someone opens this tab), and the empty cells land as NULL rather than
-- as a fabricated 0. The ads renderer's existing zero-spend filter is what
-- hides them, so no new control is needed.
--
-- ============================================================================

-- ─────────────────────────── campaigns ───────────────────────────
create table if not exists walmart_ad_campaign (
  id                bigserial primary key,
  reporting_month   text        not null,          -- 'YYYY-MM', from the uploader
  reporting_date    date,                          -- derived: last day of that month
  account           text        not null,          -- Walmart ad account the file came from
  region            text        not null default 'US',
  campaign_id       text,
  campaign          text,
  campaign_type     text,                          -- Sponsored Products (Auto) / (Manual) / Sponsored Video
  campaign_status   text,                          -- Live / Paused / Completed / Proposal ...
  advertiser_brand  text,                          -- derived from the campaign name, null when unknown
  bidding_strategy  text,
  daily_budget      numeric,
  total_budget      numeric,
  start_date        date,                          -- the CAMPAIGN's schedule, not the window
  end_date          date,
  impressions       bigint,
  clicks            bigint,
  spend             numeric,
  sales             numeric,                       -- Total Attributed Sales (online)
  orders            bigint,
  units             bigint,
  dpv               bigint,                        -- Total Product Detail Page Views
  atc               bigint,                        -- Total Add To Cart
  in_store_sales    numeric,
  in_store_units    bigint,
  in_store_orders   bigint,
  uploaded_at       timestamptz not null default now()
);

alter table walmart_ad_campaign add column if not exists reporting_date   date;
alter table walmart_ad_campaign add column if not exists advertiser_brand text;
alter table walmart_ad_campaign add column if not exists bidding_strategy text;
alter table walmart_ad_campaign add column if not exists total_budget     numeric;
alter table walmart_ad_campaign add column if not exists dpv              bigint;
alter table walmart_ad_campaign add column if not exists atc              bigint;
alter table walmart_ad_campaign add column if not exists in_store_sales   numeric;
alter table walmart_ad_campaign add column if not exists in_store_units   bigint;
alter table walmart_ad_campaign add column if not exists in_store_orders  bigint;

-- One row per campaign per month per account. campaign_id is the stable
-- identity; the name and the status both change under it. The coalesce chain
-- keeps a file with a blank id from collapsing every such row onto one key.
create unique index if not exists walmart_ad_campaign_uniq
  on walmart_ad_campaign (
    reporting_month, region, coalesce(account, ''),
    coalesce(campaign_id, ''), coalesce(campaign, '')
  );

create index if not exists walmart_ad_campaign_month_idx on walmart_ad_campaign (reporting_month);
create index if not exists walmart_ad_campaign_brand_idx on walmart_ad_campaign (advertiser_brand);

-- ─────────────────────────── keywords ───────────────────────────
create table if not exists walmart_ad_keyword (
  id                bigserial primary key,
  reporting_month   text        not null,
  reporting_date    date,
  account           text        not null,
  region            text        not null default 'US',
  keyword_id        text,
  keyword           text,
  match_type        text,                          -- exact / phrase / broad
  status            text,                          -- enabled / disabled (the KEYWORD's own)
  bid               numeric,
  suggested_bid     numeric,
  campaign_id       text,
  campaign          text,
  campaign_status   text,
  ad_group_id       text,
  ad_group          text,
  ad_group_status   text,
  advertiser_brand  text,
  impressions       bigint,
  clicks            bigint,
  spend             numeric,
  sales             numeric,
  orders            bigint,
  units             bigint,
  dpv               bigint,
  atc               bigint,
  in_store_sales    numeric,
  in_store_units    bigint,
  in_store_orders   bigint,
  uploaded_at       timestamptz not null default now()
);

alter table walmart_ad_keyword add column if not exists reporting_date   date;
alter table walmart_ad_keyword add column if not exists advertiser_brand text;
alter table walmart_ad_keyword add column if not exists suggested_bid    numeric;
alter table walmart_ad_keyword add column if not exists dpv              bigint;
alter table walmart_ad_keyword add column if not exists atc              bigint;
alter table walmart_ad_keyword add column if not exists in_store_sales   numeric;
alter table walmart_ad_keyword add column if not exists in_store_units   bigint;
alter table walmart_ad_keyword add column if not exists in_store_orders  bigint;

-- keyword_id is unique per (keyword, match type) in the export, so it alone is
-- the identity. keyword and match_type ride along in the key so that a file
-- with a blank id still separates its rows instead of colliding on ''.
create unique index if not exists walmart_ad_keyword_uniq
  on walmart_ad_keyword (
    reporting_month, region, coalesce(account, ''),
    coalesce(keyword_id, ''), coalesce(keyword, ''), coalesce(match_type, '')
  );

create index if not exists walmart_ad_keyword_month_idx    on walmart_ad_keyword (reporting_month);
create index if not exists walmart_ad_keyword_campaign_idx on walmart_ad_keyword (campaign_id);

-- ─────────────────────────── RLS + grants ───────────────────────────
-- /!\ RLS WITH NO POLICY DENIES EVERYTHING. That is the secure default doing
-- its job, and it is what produced
--   new row violates row-level security policy for table "walmart_ad_campaign"
-- on the first upload.
--
-- Checked against the live database rather than guessed, because the obvious
-- diagnosis was wrong on both counts:
--   pg_tables.rowsecurity    ALREADY true  - Supabase turns RLS on for a new
--                            table by itself, so the alter below is a no-op
--                            that only matters on a database that does not.
--   role_table_grants        `authenticated` ALREADY had all seven privileges
--                            from Supabase's default privileges.
--   pg_policies              EMPTY. This was the whole problem.
--
-- The app connects with the anon KEY but then SIGNS IN, so every statement it
-- runs arrives as `authenticated` - which is why the policy is written for
-- that role and not for anon. Same shape as every other table here; see
-- supabase_v11_08_walmart_catalog.sql.
alter table walmart_ad_campaign enable row level security;
alter table walmart_ad_keyword  enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'walmart_ad_campaign'
      and policyname = 'walmart_ad_campaign_authenticated_all'
  ) then
    create policy walmart_ad_campaign_authenticated_all
      on walmart_ad_campaign for all to authenticated using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'walmart_ad_keyword'
      and policyname = 'walmart_ad_keyword_authenticated_all'
  ) then
    create policy walmart_ad_keyword_authenticated_all
      on walmart_ad_keyword for all to authenticated using (true) with check (true);
  end if;
end $$;

grant select, insert, update, delete on table walmart_ad_campaign to authenticated;
grant select, insert, update, delete on table walmart_ad_keyword  to authenticated;
grant usage, select on sequence walmart_ad_campaign_id_seq to authenticated;
grant usage, select on sequence walmart_ad_keyword_id_seq  to authenticated;

-- Verify: both tables should report rowsecurity = true and one policy each.
-- select tablename, rowsecurity from pg_tables
--   where schemaname='public' and tablename like 'walmart_ad_%';
-- select tablename, policyname, roles from pg_policies
--   where schemaname='public' and tablename like 'walmart_ad_%';
