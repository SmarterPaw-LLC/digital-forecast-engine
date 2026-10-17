-- ============================================================================
-- ALL PAID KEYWORDS  (Sponsored Products search terms)
--
-- Paste this whole file and hit Run. One row per product + search term for the
-- latest month each product has ad data. Sorted by spend, biggest first.
--
-- This covers EVERY advertised product, not just the three that also have
-- organic keyword data. Source is amazon_sp_search_term (Amazon Ads -> Reports
-- -> Sponsored Products -> Search Term Report), which is paid activity only.
--
-- "keyword" here is the CUSTOMER SEARCH TERM, what the shopper actually typed.
-- That is the one that matters for performance. What we bid on to match it is
-- summarised as match_types / campaigns / bid_targets, because one search term
-- is commonly matched by several keywords, ad groups and match types.
--
-- TO SEE EVERY MONTH instead of just the latest: delete the whole
-- "where t.reporting_month = (...)" block near the bottom.
-- ============================================================================

select
  coalesce(p.brand, pa.brand, '(unattributed)')                 as brand,
  coalesce(p.sp_sku, pa.sp_sku, '')                             as sp_sku,
  coalesce(p.short_name, p.title, pa.short_name, pa.title,
           '(no ASIN - auto / catch-all targeting)')            as product,
  coalesce(t.asin, '')                                          as asin,
  t.region,
  t.reporting_month                                             as month,

  lower(btrim(regexp_replace(t.customer_search_term, '\s+', ' ', 'g')))
                                                                as keyword,

  -- what we bid on to match that term, rolled up
  string_agg(distinct t.match_type, ', ')                       as match_types,
  count(distinct t.campaign_name)                               as campaigns,
  count(distinct t.targeting)                                   as bid_targets,

  -- ---- traffic
  sum(t.impressions)                                            as impressions,
  sum(t.clicks)                                                 as clicks,
  case when sum(t.impressions) > 0
       then round(100.0 * sum(t.clicks) / sum(t.impressions), 2) end as ctr_pct,

  -- ---- cost
  round(sum(t.spend)::numeric, 2)                               as spend,
  case when sum(t.clicks) > 0
       then round((sum(t.spend) / sum(t.clicks))::numeric, 2) end as avg_cpc,

  -- ---- return
  sum(t.orders_7d)                                              as orders,
  sum(t.units_7d)                                               as units,
  round(sum(t.sales_7d)::numeric, 2)                            as sales,
  case when sum(t.clicks) > 0
       then round(100.0 * sum(t.orders_7d) / sum(t.clicks), 1) end as cvr_pct,
  case when sum(t.orders_7d) > 0
       then round((sum(t.spend) / sum(t.orders_7d))::numeric, 2) end as cost_per_order,
  case when sum(t.spend) > 0
       then round((sum(t.sales_7d) / sum(t.spend))::numeric, 2) end as roas,
  case when sum(t.sales_7d) > 0
       then round(100.0 * sum(t.spend) / sum(t.sales_7d), 1) end as acos_pct,

  case
    when sum(t.clicks) = 0              then 'no clicks - impressions only'
    when sum(t.orders_7d) = 0           then 'SPEND, NO ORDERS'
    when sum(t.spend) > sum(t.sales_7d) then 'losing money'
    else 'profitable'
  end                                                           as flag

from amazon_sp_search_term t
left join products p  on p.master_id = t.master_id
left join products pa on t.master_id is null and pa.asin = t.asin

-- Latest month per (product, region). `is not distinct from` so rows with no
-- ASIN (auto / catch-all targeting) are handled instead of dropped by NULL.
where t.reporting_month = (
  select max(x.reporting_month)
  from amazon_sp_search_term x
  where x.asin is not distinct from t.asin
    and x.region = t.region
)

group by 1, 2, 3, 4, 5, 6, 7
order by spend desc nulls last
