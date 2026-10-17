-- ============================================================================
-- ALL PAID KEYWORDS  (Sponsored Products search terms)
--
-- Paste this whole file and hit Run. One row per product + search term for the
-- latest month each product has ad data. Sorted by spend, biggest first.
--
-- Covers EVERY advertised product, not just the three that also have organic
-- keyword data. Source is amazon_sp_search_term (Amazon Ads -> Reports ->
-- Sponsored Products -> Search Term Report), which is paid activity only.
--
-- "keyword" is the CUSTOMER SEARCH TERM, what the shopper actually typed. What
-- we bid on to match it is summarised as match_types / campaigns / bid_targets,
-- because one search term is commonly matched by several keywords, ad groups
-- and match types.
--
-- PERFORMANCE NOTE: the first version of this used a correlated subquery to
-- find each product's latest month, which re-ran once per row and timed out.
-- This version resolves latest-month ONCE in a CTE and joins it, and groups on
-- coalesce(asin,'') so the existing unique index can actually be used.
--
-- TO SEE EVERY MONTH: delete the one line marked [LATEST ONLY] below.
-- ============================================================================

with latest as (
  -- One row per (product, region). coalesce(asin,'') matches the leading
  -- expression of amazon_sp_search_term_uniq, and keeps rows with no ASIN
  -- (auto / catch-all targeting) instead of dropping them on a NULL compare.
  select coalesce(asin, '') as akey,
         region,
         max(reporting_month) as mo
  from amazon_sp_search_term
  group by coalesce(asin, ''), region
),
agg as (
  -- Collapse to one row per (product, region, month, search term) BEFORE
  -- touching the products table, so the join runs against the small set.
  select
    coalesce(t.asin, '')                                           as akey,
    max(t.master_id)                                               as master_id,
    t.region,
    t.reporting_month,
    lower(btrim(regexp_replace(t.customer_search_term, '\s+', ' ', 'g')))
                                                                   as keyword,
    string_agg(distinct t.match_type, ', ')                        as match_types,
    count(distinct t.campaign_name)                                as campaigns,
    count(distinct t.targeting)                                    as bid_targets,
    sum(t.impressions)                                             as impressions,
    sum(t.clicks)                                                  as clicks,
    sum(t.spend)                                                   as spend,
    sum(t.orders_7d)                                               as orders,
    sum(t.units_7d)                                                as units,
    sum(t.sales_7d)                                                as sales
  from amazon_sp_search_term t
  join latest l on l.akey = coalesce(t.asin, '') and l.region = t.region and l.mo = t.reporting_month  -- [LATEST ONLY] delete this whole line
  group by 1, 3, 4, 5
)
select
  coalesce(p.brand, pa.brand, '(unattributed)')                 as brand,
  coalesce(p.sp_sku, pa.sp_sku, '')                             as sp_sku,
  coalesce(p.short_name, p.title, pa.short_name, pa.title,
           '(no ASIN - auto / catch-all targeting)')            as product,
  a.akey                                                        as asin,
  a.region,
  a.reporting_month                                             as month,

  a.keyword,
  a.match_types,
  a.campaigns,
  a.bid_targets,

  -- ---- traffic
  a.impressions,
  a.clicks,
  case when a.impressions > 0
       then round(100.0 * a.clicks / a.impressions, 2) end       as ctr_pct,

  -- ---- cost
  round(a.spend::numeric, 2)                                    as spend,
  case when a.clicks > 0
       then round((a.spend / a.clicks)::numeric, 2) end          as avg_cpc,

  -- ---- return
  a.orders,
  a.units,
  round(a.sales::numeric, 2)                                    as sales,
  case when a.clicks > 0
       then round(100.0 * a.orders / a.clicks, 1) end            as cvr_pct,
  case when a.orders > 0
       then round((a.spend / a.orders)::numeric, 2) end          as cost_per_order,
  case when a.spend > 0
       then round((a.sales / a.spend)::numeric, 2) end           as roas,
  case when a.sales > 0
       then round(100.0 * a.spend / a.sales, 1) end              as acos_pct,

  case
    when a.clicks = 0        then 'no clicks - impressions only'
    when a.orders = 0        then 'SPEND, NO ORDERS'
    when a.spend > a.sales   then 'losing money'
    else 'profitable'
  end                                                           as flag

from agg a
left join products p  on p.master_id = a.master_id
left join products pa on a.master_id is null and pa.asin = nullif(a.akey, '')
order by a.spend desc nulls last
