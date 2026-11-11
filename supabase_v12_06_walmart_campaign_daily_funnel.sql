-- ============================================================================
-- Walmart campaign x day — the funnel columns  (v12.06)
-- Run ONCE in Supabase -> SQL Editor. Idempotent. Additive only.
-- ============================================================================
-- The Custom builder DOES offer Total Product Detail Page Views and Total Add
-- to Cart, at the same 3 / 14 / 30 Day variants as every other conversion
-- measure. v12.05 was built before that was known.
--
-- With these two, `walmart_ad_campaign_daily` carries everything the
-- Advertiser export carries AND breaks it out by campaign - so the funnel
-- (Impressions -> Clicks -> Page Views -> Add to Cart -> Orders) is readable
-- per campaign per day for the first time.
--
-- ⚠ They settle like every other conversion column: in the first file the
-- newest day reported 0 page views against real clicks on three campaigns and
-- the literal `null` on two more. The upsert is what lets a re-pull correct
-- them.
-- ============================================================================

alter table walmart_ad_campaign_daily add column if not exists dpv bigint;
alter table walmart_ad_campaign_daily add column if not exists atc bigint;

comment on column walmart_ad_campaign_daily.dpv is
  'Total Product Detail Page Views at the row''s attribution window. Settles upward for a day or two.';
comment on column walmart_ad_campaign_daily.atc is
  'Total Add to Cart at the row''s attribution window. Settles the same way.';

-- Nothing else changes: the unique index, the RLS policy and the grants from
-- supabase_v12_05_walmart_ad_campaign_daily.sql all still apply.
--
-- Verify:
-- select column_name from information_schema.columns
--  where table_name='walmart_ad_campaign_daily' and column_name in ('dpv','atc');
