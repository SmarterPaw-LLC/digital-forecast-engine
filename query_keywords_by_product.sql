-- ============================================================================
-- KEYWORDS BY PRODUCT, WITH SEARCH VOLUME            (for Blake, 2026-10-17)
--
-- Source: amazon_query_performance_asin -- the Brand Analytics "Search Query
-- Performance" report, ASIN view, uploaded via Data -> Uploads -> SQP.
-- One row per (ASIN, reporting_month, search_query).
--
-- NOTE ON COVERAGE: this table only holds ASINs whose SQP ASIN-VIEW report has
-- actually been uploaded. The BRAND-view upload is a different grain (per
-- brand, not per ASIN) and does NOT populate the per-product list below.
-- Run SECTION 0 first to see what is actually covered before promising a list.
--
-- HOW TO RUN: Data -> Query Database, paste ONE section, Run Query, then
-- Download CSV. (The runner wraps the query as a subquery, so one at a time.)
-- ============================================================================


-- ============================================================================
-- SECTION 0: Coverage -- which products do we actually have keyword data for?
-- Run this FIRST. It answers "can we give Blake a complete list, or a partial one".
-- ============================================================================

select
  q.view_type,
  count(distinct q.asin)                        as asins_covered,
  count(distinct q.reporting_month)             as months,
  min(q.reporting_month)                        as earliest,
  max(q.reporting_month)                        as latest,
  count(*)                                      as keyword_rows,
  count(distinct q.search_query)                as distinct_keywords
from amazon_query_performance_asin q
group by q.view_type
order by q.view_type;


-- ============================================================================
-- SECTION 1: THE DELIVERABLE -- keywords by product with search volume.
-- Latest month per ASIN, so one clean current list rather than every month.
-- ============================================================================

/*
with latest as (
  select asin, max(reporting_month) as reporting_month
  from amazon_query_performance_asin
  where view_type = 'asin'
  group by asin
)
select
  p.brand,
  p.sp_sku,
  coalesce(p.short_name, p.title)                       as product,
  q.asin,
  q.reporting_month,
  q.search_query                                        as keyword,
  q.search_query_volume                                 as search_volume,
  q.search_query_score                                  as query_score,
  q.impressions_total_count                             as market_impressions,
  q.impressions_asin_count                              as our_impressions,
  q.impressions_asin_share_pct                          as our_impression_share_pct,
  q.clicks_total_count                                  as market_clicks,
  q.clicks_asin_count                                   as our_clicks,
  q.purchases_total_count                               as market_purchases,
  q.purchases_asin_count                                as our_purchases,
  q.clicks_price_median                                 as market_median_price,
  -- the two derived columns Blake will want next
  case when q.clicks_total_count > 0
       then round(100.0 * q.purchases_total_count / q.clicks_total_count, 2) end
                                                        as market_cvr_pct,
  case when q.impressions_total_count > 0
       then round(100.0 * q.clicks_total_count / q.impressions_total_count, 2) end
                                                        as market_ctr_pct
from amazon_query_performance_asin q
join latest l
  on l.asin = q.asin and l.reporting_month = q.reporting_month
left join products p on p.asin = q.asin
where q.view_type = 'asin'
order by p.brand, product, q.search_query_volume desc nulls last;
*/


-- ============================================================================
-- SECTION 2: Top 25 keywords per product (a shorter list to actually read)
-- ============================================================================

/*
with latest as (
  select asin, max(reporting_month) as reporting_month
  from amazon_query_performance_asin
  where view_type = 'asin'
  group by asin
),
ranked as (
  select
    q.*,
    row_number() over (partition by q.asin order by q.search_query_volume desc nulls last) as rn
  from amazon_query_performance_asin q
  join latest l on l.asin = q.asin and l.reporting_month = q.reporting_month
  where q.view_type = 'asin'
)
select
  p.brand,
  p.sp_sku,
  coalesce(p.short_name, p.title)        as product,
  r.asin,
  r.rn                                   as rank,
  r.search_query                         as keyword,
  r.search_query_volume                  as search_volume,
  r.impressions_asin_share_pct           as our_impression_share_pct,
  r.purchases_asin_count                 as our_purchases,
  r.purchases_total_count                as market_purchases
from ranked r
left join products p on p.asin = r.asin
where r.rn <= 25
order by p.brand, product, r.rn;
*/


-- ============================================================================
-- SECTION 3: Keyword volume rolled up across the catalog
-- "Which search terms are biggest for us overall" -- dedupes a keyword that
-- several of our ASINs rank on.
-- ============================================================================

/*
with latest as (
  select asin, max(reporting_month) as reporting_month
  from amazon_query_performance_asin
  where view_type = 'asin'
  group by asin
)
select
  q.search_query                                  as keyword,
  max(q.search_query_volume)                      as search_volume,
  count(distinct q.asin)                          as our_asins_on_it,
  sum(q.impressions_asin_count)                   as our_impressions,
  sum(q.purchases_asin_count)                     as our_purchases,
  max(q.purchases_total_count)                    as market_purchases,
  round(avg(q.impressions_asin_share_pct), 2)     as avg_our_impression_share_pct,
  string_agg(distinct coalesce(p.sp_sku, q.asin), ', ' order by coalesce(p.sp_sku, q.asin)) as skus
from amazon_query_performance_asin q
join latest l on l.asin = q.asin and l.reporting_month = q.reporting_month
left join products p on p.asin = q.asin
where q.view_type = 'asin'
group by q.search_query
order by max(q.search_query_volume) desc nulls last
limit 500;
*/
