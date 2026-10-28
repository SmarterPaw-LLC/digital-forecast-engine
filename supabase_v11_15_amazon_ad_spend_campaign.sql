-- ============================================================================
-- amazon_ad_spend.campaign  (v11.15)
-- Run ONCE in Supabase -> SQL Editor. Idempotent.
-- ============================================================================
-- WHY
-- ----
-- The Ads sub-tab on each P&L is campaign-level. amazon_ad_spend already
-- carries daily spend / impressions / clicks / purchases / attributed_sales
-- for EVERY ad product (SP + SB + SD + DSP + TV) from the weekly unified
-- report, so adding `Campaign name` as a dimension to that existing export
-- gives campaign grain across all ad types with no new upload cadence.
--
-- amazon_sp_campaign_snapshot is NOT the source for that view: it is a
-- single-month rollup with no per-row date, Sponsored Products only.
--
-- ============================================================================
-- /!\ THE UNIQUE INDEX HAS TO MOVE WITH THE GRAIN
-- ============================================================================
-- amazon_ad_spend_uniq was
--   (date, region, ad_product, coalesce(asin,''), coalesce(advertiser_brand,''))
-- Two campaigns advertising the SAME ASIN on the same day in the same
-- marketplace are the normal case, not an edge case. Adding the column while
-- leaving that index alone means the second campaign's row is a unique
-- violation, the insert chunk throws, and the WHOLE upload fails after the
-- DELETE has already run -- emptying the window it was replacing.
--
-- So the index is rebuilt to include coalesce(campaign,''). Widening a unique
-- key can only ever reduce collisions, so existing rows satisfy the new index
-- by construction and no data has to be cleaned first.
--
-- The new index is created BEFORE the old one is dropped, so there is never a
-- moment where the table has no uniqueness guard.
--
-- ============================================================================
-- /!\ HISTORICAL ROWS CARRY campaign = NULL, AND THAT MUST BE SHOWN
-- ============================================================================
-- Every row uploaded before the export carried the column has no campaign and
-- never will -- Amazon's report builder cannot retrofit a dimension onto spend
-- that was already pulled without it. A campaign-level view must therefore
-- carry an explicit "(no campaign)" bucket rather than filtering nulls out:
-- dropping them would silently understate total spend on the exact page built
-- to judge whether the spend pays. Re-uploading a window backfills it.
-- ============================================================================

alter table amazon_ad_spend
  add column if not exists campaign text;

-- Replace-on-reupload key, now at campaign grain.
create unique index if not exists amazon_ad_spend_uniq_v2
  on amazon_ad_spend (
    date, region, ad_product,
    coalesce(asin,''), coalesce(advertiser_brand,''), coalesce(campaign,'')
  );

drop index if exists amazon_ad_spend_uniq;

-- The Ads view groups by campaign over a date window.
create index if not exists amazon_ad_spend_campaign_idx
  on amazon_ad_spend (campaign, date) where campaign is not null;

-- Verify (post-run):
--   select count(*) filter (where campaign is not null) as with_campaign,
--          count(*) filter (where campaign is null)     as without_campaign
--   from amazon_ad_spend;
--
--   -- after a re-upload, the campaign-carrying window and its spend:
--   select min(date) as from_d, max(date) as to_d,
--          count(distinct campaign) as campaigns,
--          round(sum(spend)::numeric, 2) as spend
--   from amazon_ad_spend where campaign is not null;
--
--   -- the index that must be gone, and the one that must be there:
--   select indexname from pg_indexes
--   where tablename = 'amazon_ad_spend' and indexname like '%uniq%';
