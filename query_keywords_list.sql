-- ============================================================================
-- KEYWORDS BY PRODUCT, WITH ORGANIC vs PAID SPLIT
--
-- Paste this whole file and hit Run. It returns KEYWORDS - one row per
-- (product, keyword) for the latest month each product has data.
--
-- (query_keywords_organic_vs_paid.sql SECTION 0 is the coverage check - it
--  tells you WHICH products can be split and has no keyword column. This file
--  is the actual list.)
--
-- Columns:
--   keyword              the customer search term
--   market_search_volume how often the whole market searched it that month
--   total_clicks         clicks on YOUR listing from that query (organic + paid)
--   paid_clicks          clicks Sponsored Products paid for on that exact term
--   organic_clicks       total - paid, clamped at 0
--   organic_share_pct    share of your clicks that were NOT paid for
--   split_flag           quick read on whether paid is carrying the keyword
--
-- Trust notes:
--   TRAFFIC (impressions / clicks) is a clean subtraction - both sides count
--   events on the same query.
--   PURCHASES is APPROXIMATE: SQP uses Amazon's attribution, SP uses a 7-day
--   window, so the purchase split can drift. Clamped at 0 because paid can
--   exceed total across differing windows.
--   SQP ASIN view is CAPPED AT THE TOP 100 QUERIES per ASIN per month, so this
--   is your top-100 keyword list, not the full long tail.
--   Products with no SP data show paid 0 / organic = total ("ORGANIC ONLY").
--   Products with no SQP data CANNOT appear here at all - there is no keyword
--   list for them. Run the coverage query to see which those are.
-- ============================================================================

with latest as (
  select asin, region, max(reporting_month) as reporting_month
  from amazon_query_performance_asin
  where view_type = 'asin' and asin is not null
  group by asin, region
),
-- One search term is commonly hit by several campaigns / ad groups / match
-- types, so collapse SP to one row per (asin, region, month, term) first.
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

  -- ---- TRAFFIC: the trustworthy half
  q.clicks_asin_count                                           as total_clicks,
  coalesce(sp.paid_clicks, 0)                                   as paid_clicks,
  greatest(q.clicks_asin_count - coalesce(sp.paid_clicks, 0), 0) as organic_clicks,
  case when q.clicks_asin_count > 0
       then round(100.0 * greatest(q.clicks_asin_count - coalesce(sp.paid_clicks, 0), 0)
                  / q.clicks_asin_count, 1) end                 as organic_share_pct,

  -- ---- your share of the whole market's clicks on this query
  q.clicks_total_count                                          as market_clicks,
  case when q.clicks_total_count > 0
       then round(100.0 * q.clicks_asin_count / q.clicks_total_count, 1) end
                                                                as your_click_share_pct,

  -- ---- PURCHASES: approximate, see header
  q.purchases_asin_count                                        as total_purchases,
  coalesce(sp.paid_orders, 0)                                   as paid_purchases,
  greatest(q.purchases_asin_count - coalesce(sp.paid_orders, 0), 0)
                                                                as organic_purchases_approx,

  -- ---- paid economics on this keyword
  round(coalesce(sp.paid_spend, 0)::numeric, 2)                 as paid_spend,
  case when coalesce(sp.paid_spend, 0) > 0
       then round((coalesce(sp.paid_sales, 0) / sp.paid_spend)::numeric, 2) end
                                                                as paid_roas,

  case
    when sp.term is null                                then 'ORGANIC ONLY - not advertised'
    when coalesce(sp.paid_clicks, 0) = 0                then 'advertised, no paid clicks'
    when sp.paid_clicks >= q.clicks_asin_count          then 'ALL PAID - no organic pull'
    when sp.paid_clicks >= 0.5 * q.clicks_asin_count    then 'mostly paid'
    else 'mostly organic'
  end                                                           as split_flag

from amazon_query_performance_asin q
join latest l
  on  l.asin            = q.asin
  and l.region          = q.region
  and l.reporting_month = q.reporting_month
left join sp
  on  sp.asin            = q.asin
  and sp.region          = q.region
  and sp.reporting_month = q.reporting_month
  and sp.term            = lower(btrim(regexp_replace(q.search_query, '\s+', ' ', 'g')))
left join products p  on p.master_id = q.master_id
left join products pa on q.master_id is null and pa.asin = q.asin
where q.view_type = 'asin'
order by 3, q.clicks_asin_count desc nulls last
