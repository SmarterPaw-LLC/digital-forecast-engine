-- ============================================================================
-- Walmart Connect — CAMPAIGN x DAY  (v12.05)
-- Run ONCE in Supabase -> SQL Editor. Idempotent.
-- ============================================================================
-- WHY
-- ----
-- Jason: "i need to be able to drive performance for walmart ads"
--
-- Ad Center -> Reports -> Custom -> saved report "Campaign x Day - 14d".
--   Split:   Date (Day) · Campaign Type Name · Campaign Name
--   Measure: Impressions · Clicks · Ad Spend
--            Total Units Sold / Orders / Total Sales Rev.  - 14 Day
--            In-store Attributed Sales - 14 Days
--            New-to-Brand Orders / Sales - 14 Days
--
-- This is the feed the Walmart ads work has been missing since v11.25. The
-- Campaigns and Keywords exports carry NO reporting date, so the uploader has
-- to ask which month a file covers and stamp it on every row - which is why
-- the campaign grain has been monthly, and why a campaign going sideways was
-- invisible until month end.
--
-- ============================================================================
-- /!\ IT RECONCILES TO walmart_ad_daily, AND THAT WAS CHECKED FIRST
-- ============================================================================
-- Summing the five campaigns on each of the seven days in the first file
-- reproduces the Advertiser export's own daily figures EXACTLY:
--
--   spend   Nov 04 $155.65 · 05 $161.49 · 06 $181.39 · 07 $190.83
--           Nov 08 $177.51 · 09 $154.48 · 10 $158.09   (total $1,179.44)
--   sales   Nov 04 $430.00 · Nov 10 $235.70
--
-- So the two feeds are the SAME DOLLARS at two breakdowns, exactly as
-- walmart_ad_daily is to walmart_ad_campaign. NEVER SUM ACROSS THEM.
--
--   walmart_ad_daily           day,  advertiser total   pacing
--   walmart_ad_campaign_daily  day,  per campaign       the levers      <- this
--   walmart_ad_campaign        month, per campaign      history + settings
--
-- ============================================================================
-- /!\ THE ATTRIBUTION WINDOW IS STORED ON THE ROW
-- ============================================================================
-- Every conversion measure in the Custom builder comes in 3 / 14 / 30 Day
-- variants, and the header names which one: `Orders - 14 Day`. 14 is the
-- choice, because it matches the Advertiser report's own selector ("Attribution:
-- 14 days attribution") - which is what makes the tie-out above possible - and
-- it is Walmart Connect's default.
--
-- It is stored rather than assumed so a 30-day pull cannot silently blend with
-- these rows: it lands as its own row and nothing averages the two. The parser
-- REFUSES a file whose measures do not all carry the same window, because one
-- 3-day Orders column beside a 14-day Sales column makes CPA and ROAS describe
-- different populations in the same row with nothing on screen saying so.
--
-- ============================================================================
-- /!\ A LITERAL `null` IN THIS EXPORT IS A REPORTED ZERO
-- ============================================================================
-- Walmart writes the TEXT `null` into Units / Orders / Sales on some rows and
-- `0` into the same columns on other rows of the SAME campaign. Blank-means-
-- null is v11.25's rule and the right default, but it is wrong here, and the
-- tie-out above is the evidence: the daily sums match to the cent only when
-- those cells count as zero.
--
-- It matters which way: stored as null, `SP - KW - MIXED - DOGGIJUANA` shows a
-- blank ROAS on the days it spent $3.00 and returned nothing - hiding a loser
-- behind what reads as missing data. Stored as 0 it reads 0.00x, which is the
-- fact. The parser converts the literal only for this feed.
--
-- ============================================================================
-- /!\ NO BRAND COLUMN IN THE FILE
-- ============================================================================
-- Walmart's own Brand dimension splits Sponsored Brand Video across the brand
-- and an `unknown` bucket - campaign 5640253 appeared under BOTH - so it is not
-- a reliable key. advertiser_brand is resolved from the CAMPAIGN NAME through
-- adsAdvertiserToBrand, which is what walmart_ad_campaign already does and
-- what makes "SP - KW - MIXED - DOGGIJUANA" file under Doggijuana inside the
-- Kitty Ka-Zoom account.
--
-- ============================================================================
-- /!\ NO master_id — the merge audit is a no-op (v11.90)
-- ============================================================================
-- Walmart puts the item dimension in a separate Item report, so this table
-- carries no product key and MERGE_MASTER_ID_TABLES gains no row. Audited.
-- ============================================================================

create table if not exists walmart_ad_campaign_daily (
  id               bigserial primary key,

  date             date        not null,
  region           text        not null default 'US',
  account          text        not null,
  campaign         text        not null,

  campaign_type    text,
  advertiser_brand text,

  -- ⚠ Which attribution window the conversion columns below were pulled at.
  -- Part of nothing's key, but on every row, so a mixed table is visible.
  attribution_days smallint    not null default 14,

  impressions      bigint,
  clicks           bigint,
  spend            numeric(12,2) not null default 0,
  units            bigint,
  orders           bigint,
  sales            numeric(12,2),
  in_store_sales   numeric(12,2),
  ntb_orders       bigint,
  ntb_sales        numeric(12,2),

  uploaded_at      timestamptz not null default now()
);

-- One row per campaign per day per account. ⚠ attribution_days is NOT in the
-- key: re-pulling the same days at 30-day REPLACES them rather than doubling
-- the spend, which is the safer failure. The column then shows what landed.
create unique index if not exists walmart_ad_campaign_daily_uniq
  on walmart_ad_campaign_daily (date, region, account, campaign);

create index if not exists walmart_ad_campaign_daily_date_idx
  on walmart_ad_campaign_daily (date desc);
create index if not exists walmart_ad_campaign_daily_camp_idx
  on walmart_ad_campaign_daily (campaign, date desc);

-- ─────────────────────────── RLS + grants ───────────────────────────
-- /!\ RLS WITH NO POLICY DENIES EVERYTHING, and the grants alone are not
-- enough. v12.03 shipped without the policy and the first upload failed with
-- `new row violates row-level security policy`. Supabase turns RLS on for a
-- new table by itself; pg_policies being empty is the whole problem.
--
-- The app connects with the anon KEY but then SIGNS IN, so every statement
-- arrives as `authenticated`. Hard rule since v6.47.
alter table walmart_ad_campaign_daily enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'walmart_ad_campaign_daily'
      and policyname = 'walmart_ad_campaign_daily_authenticated_all'
  ) then
    create policy walmart_ad_campaign_daily_authenticated_all
      on walmart_ad_campaign_daily for all to authenticated using (true) with check (true);
  end if;
end $$;

grant select, insert, update, delete on table walmart_ad_campaign_daily to authenticated;
grant usage, select on sequence walmart_ad_campaign_daily_id_seq to authenticated;

comment on table walmart_ad_campaign_daily is
  'Walmart Connect Custom report, Campaign x Day. Never sum with walmart_ad_daily or walmart_ad_campaign: same dollars, different breakdowns.';
comment on column walmart_ad_campaign_daily.attribution_days is
  'The conversion window the file was pulled at, read from the measure headers (e.g. "Orders - 14 Day"). 14 matches the Advertiser report and is what the two feeds tie out on.';
comment on column walmart_ad_campaign_daily.in_store_sales is
  'In-store ATTRIBUTED sales (advertised + halo). A SECOND BASIS, never folded into sales (v11.25).';

-- Verify:
-- select tablename, rowsecurity from pg_tables where tablename='walmart_ad_campaign_daily';
-- select policyname from pg_policies where tablename='walmart_ad_campaign_daily';
