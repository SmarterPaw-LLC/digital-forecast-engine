-- ============================================================================
-- KEYWORDS: ORGANIC vs PAID TRAFFIC                        (2026-10-17)
--
-- There is no organic/paid split anywhere in the app today. It IS derivable,
-- because the two keyword tables measure different populations:
--
--   amazon_query_performance_asin  (SQP, ASIN view) = TOTAL  (organic + paid)
--   amazon_sp_search_term          (SP Search Term) = PAID   (Sponsored Products only)
--
--   organic = total - paid,  clamped at 0
--
-- That subtraction already exists in the dashboard (pnlGrowthComputeEmpiricalUplift,
-- v8.50) but only at the ASIN level, summed across keywords, and only to derive
-- the paid->organic uplift %. It is never shown per keyword.
--
-- ============================ READ THIS BEFORE QUOTING ======================
-- 1. TRAFFIC (impressions / clicks) is the trustworthy half. Both sides are
--    simple event counts on the same query, so the subtraction is clean.
-- 2. PURCHASES is APPROXIMATE. SQP purchases use Amazon's own attribution;
--    SP orders_7d is a 7-day window. Different windows, so the purchase split
--    can drift. Treat organic_purchases as indicative, not exact.
-- 3. Paid can EXCEED total on a given row (attribution-window mismatch), which
--    is why every organic figure is clamped with greatest(..., 0).
-- 4. SP rows are SUMMED per (asin, month, term) first - one search term is
--    commonly hit by several campaigns / ad groups / match types.
-- 5. Only (asin, month) pairs present in BOTH tables can be split. Run
--    SECTION 0 first; it tells you exactly which products qualify.
--
-- HOW TO RUN: Data -> Query Database, paste this whole file, Run Query.
-- (v10.68+ strips the parked sections automatically. To run a different
--  section, comment out the live one and uncomment the one you want.)
-- ============================================================================


-- ============================================================================
-- SECTION 0: Coverage -- which products can actually be split?
-- Run this FIRST. `splittable` = has BOTH SQP ASIN-view and SP data for the
-- same month. Anything else cannot produce an organic/paid split at all.
-- ============================================================================

with sqp as (
  select asin, region, reporting_month,
         count(*)                         as sqp_keywords,
         sum(clicks_asin_count)           as sqp_clicks
  from amazon_query_performance_asin
  where view_type = 'asin' and asin is not null
  group by asin, region, reporting_month
),
sp as (
  select asin, region, reporting_month,
         count(distinct lower(btrim(customer_search_term))) as sp_keywords,
         sum(clicks)                                        as sp_clicks
  from amazon_sp_search_term
  where asin is not null
  group by asin, region, reporting_month
)
select
  coalesce(p.brand, '(not in catalog)')                     as brand,
  coalesce(p.sp_sku, '')                                    as sp_sku,
  coalesce(p.short_name, p.title, '(not in catalog)')       as product,
  coalesce(sqp.asin, sp.asin)                               as asin,
  coalesce(sqp.region, sp.region)                           as region,
  coalesce(sqp.reporting_month, sp.reporting_month)         as month,
  sqp.sqp_keywords,
  sqp.sqp_clicks                                            as total_clicks,
  sp.sp_keywords,
  sp.sp_clicks                                              as paid_clicks,
  case
    when sqp.asin is not null and sp.asin is not null then 'SPLITTABLE'
    when sqp.asin is not null then 'SQP only - no paid data, cannot split'
    else 'SP only - no SQP, cannot see organic'
  end                                                       as status
from sqp
full outer join sp
  on  sp.asin            = sqp.asin
  and sp.region          = sqp.region
  and sp.reporting_month = sqp.reporting_month
left join products p on p.asin = coalesce(sqp.asin, sp.asin)
order by status, brand, product, month desc;


-- ============================================================================
-- SECTION 1: THE DELIVERABLE -- per keyword, organic vs paid.
-- Latest month per ASIN so it reads as one current list.
-- ============================================================================

/*
with latest as (
  select asin, region, max(reporting_month) as reporting_month
  from amazon_query_performance_asin
  where view_type = 'asin' and asin is not null
  group by asin, region
),
-- One search term is commonly hit by several campaigns / ad groups / match
-- types, so collapse SP to one row per (asin, region, month, term) FIRST.
sp as (
  select
    asin, region, reporting_month,
    lower(btrim(regexp_replace(customer_search_term, '\s+', ' ', 'g'))) as term,
    sum(impressions) as paid_impressions,
    sum(clicks)      as paid_clicks,
    sum(orders_7d)   as paid_orders,
    sum(spend)       as paid_spend,
    sum(sales_7d)    as paid_sales
  from amazon_sp_search_term
  where asin is not null
  group by 1, 2, 3, 4
)
select
  coalesce(p.brand, pa.brand)                                   as brand,
  coalesce(p.sp_sku, pa.sp_sku)                                 as sp_sku,
  coalesce(p.short_name, p.title, pa.short_name, pa.title)      as product,
  q.asin,
  q.reporting_month                                             as month,
  q.search_query                                                as keyword,
  q.search_query_volume                                         as market_search_volume,

  -- ---- TRAFFIC (trustworthy: both sides are event counts on this query)
  q.impressions_asin_count                                      as total_impressions,
  coalesce(sp.paid_impressions, 0)                              as paid_impressions,
  greatest(q.impressions_asin_count - coalesce(sp.paid_impressions, 0), 0)
                                                                as organic_impressions,

  q.clicks_asin_count                                           as total_clicks,
  coalesce(sp.paid_clicks, 0)                                   as paid_clicks,
  greatest(q.clicks_asin_count - coalesce(sp.paid_clicks, 0), 0) as organic_clicks,

  case when q.clicks_asin_count > 0
       then round(100.0 * greatest(q.clicks_asin_count - coalesce(sp.paid_clicks, 0), 0)
                  / q.clicks_asin_count, 1) end                 as organic_click_share_pct,

  -- ---- PURCHASES (approximate: differing attribution windows, see header)
  q.purchases_asin_count                                        as total_purchases,
  coalesce(sp.paid_orders, 0)                                   as paid_purchases,
  greatest(q.purchases_asin_count - coalesce(sp.paid_orders, 0), 0)
                                                                as organic_purchases_approx,

  -- ---- paid economics on this keyword
  round(coalesce(sp.paid_spend, 0)::numeric, 2)                 as paid_spend,
  round(coalesce(sp.paid_sales, 0)::numeric, 2)                 as paid_sales,
  case when coalesce(sp.paid_spend, 0) > 0
       then round((coalesce(sp.paid_sales, 0) / sp.paid_spend)::numeric, 2) end
                                                                as paid_roas,

  case
    when sp.term is null                      then 'ORGANIC ONLY - not advertised'
    when coalesce(sp.paid_clicks, 0) = 0      then 'advertised, no paid clicks'
    when sp.paid_clicks >= q.clicks_asin_count then 'ALL PAID - no organic pull'
    else 'mixed'
  end                                                           as split_flag

from amazon_query_performance_asin q
join latest l
  on l.asin = q.asin and l.region = q.region and l.reporting_month = q.reporting_month
left join sp
  on  sp.asin            = q.asin
  and sp.region          = q.region
  and sp.reporting_month = q.reporting_month
  and sp.term            = lower(btrim(regexp_replace(q.search_query, '\s+', ' ', 'g')))
left join products p  on p.master_id = q.master_id
left join products pa on q.master_id is null and pa.asin = q.asin
where q.view_type = 'asin'
order by 1, 3, q.clicks_asin_count desc nulls last;
*/


-- ============================================================================
-- SECTION 2: Per-product rollup -- how much of this product's traffic is organic?
-- One row per product. The headline number for "are we buying our own demand?"
-- ============================================================================

/*
with latest as (
  select asin, region, max(reporting_month) as reporting_month
  from amazon_query_performance_asin
  where view_type = 'asin' and asin is not null
  group by asin, region
),
sp as (
  select asin, region, reporting_month,
         lower(btrim(regexp_replace(customer_search_term, '\s+', ' ', 'g'))) as term,
         sum(clicks) as paid_clicks, sum(orders_7d) as paid_orders, sum(spend) as paid_spend
  from amazon_sp_search_term
  where asin is not null
  group by 1, 2, 3, 4
)
select
  coalesce(p.brand, pa.brand)                               as brand,
  coalesce(p.sp_sku, pa.sp_sku)                             as sp_sku,
  coalesce(p.short_name, p.title, pa.short_name, pa.title)  as product,
  q.asin,
  q.reporting_month                                         as month,
  count(*)                                                  as keywords,
  count(*) filter (where sp.term is null)                   as organic_only_keywords,
  sum(q.clicks_asin_count)                                  as total_clicks,
  sum(coalesce(sp.paid_clicks, 0))                          as paid_clicks,
  greatest(sum(q.clicks_asin_count) - sum(coalesce(sp.paid_clicks, 0)), 0)
                                                            as organic_clicks,
  case when sum(q.clicks_asin_count) > 0
       then round(100.0 * greatest(sum(q.clicks_asin_count) - sum(coalesce(sp.paid_clicks, 0)), 0)
                  / sum(q.clicks_asin_count), 1) end        as organic_click_share_pct,
  round(sum(coalesce(sp.paid_spend, 0))::numeric, 2)        as paid_spend
from amazon_query_performance_asin q
join latest l
  on l.asin = q.asin and l.region = q.region and l.reporting_month = q.reporting_month
left join sp
  on  sp.asin = q.asin and sp.region = q.region
  and sp.reporting_month = q.reporting_month
  and sp.term = lower(btrim(regexp_replace(q.search_query, '\s+', ' ', 'g')))
left join products p  on p.master_id = q.master_id
left join products pa on q.master_id is null and pa.asin = q.asin
where q.view_type = 'asin'
group by 1, 2, 3, 4, 5
order by organic_click_share_pct nulls last;
*/


-- ============================================================================
-- SECTION 3: Where paid is doing ALL the work.
-- Keywords with real paid volume and little or no organic pull. These are the
-- ones that stop producing the moment you stop paying.
-- ============================================================================

/*
with latest as (
  select asin, region, max(reporting_month) as reporting_month
  from amazon_query_performance_asin
  where view_type = 'asin' and asin is not null
  group by asin, region
),
sp as (
  select asin, region, reporting_month,
         lower(btrim(regexp_replace(customer_search_term, '\s+', ' ', 'g'))) as term,
         sum(clicks) as paid_clicks, sum(spend) as paid_spend, sum(sales_7d) as paid_sales
  from amazon_sp_search_term
  where asin is not null
  group by 1, 2, 3, 4
)
select
  coalesce(p.brand, pa.brand)                               as brand,
  coalesce(p.short_name, p.title, pa.short_name, pa.title)  as product,
  q.asin,
  q.search_query                                            as keyword,
  q.search_query_volume                                     as market_search_volume,
  q.clicks_asin_count                                       as total_clicks,
  sp.paid_clicks,
  greatest(q.clicks_asin_count - sp.paid_clicks, 0)         as organic_clicks,
  round(100.0 * sp.paid_clicks / nullif(q.clicks_asin_count, 0), 1) as paid_click_share_pct,
  round(sp.paid_spend::numeric, 2)                          as paid_spend,
  case when sp.paid_spend > 0
       then round((sp.paid_sales / sp.paid_spend)::numeric, 2) end as paid_roas
from amazon_query_performance_asin q
join latest l
  on l.asin = q.asin and l.region = q.region and l.reporting_month = q.reporting_month
join sp
  on  sp.asin = q.asin and sp.region = q.region
  and sp.reporting_month = q.reporting_month
  and sp.term = lower(btrim(regexp_replace(q.search_query, '\s+', ' ', 'g')))
left join products p  on p.master_id = q.master_id
left join products pa on q.master_id is null and pa.asin = q.asin
where q.view_type = 'asin'
  and sp.paid_clicks >= 5
  and sp.paid_clicks >= 0.8 * q.clicks_asin_count
order by sp.paid_spend desc nulls last
limit 200;
*/
