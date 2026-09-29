-- ============================================================================
-- Amazon all-in cost + break-even ACOS / ROAS  (per ASIN, US)
-- Feeds the Amazon financial-controls tool.
-- Run in Data -> Query Database, then hit "Copy CSV" in the results header.
--
-- TUNE THE THREE VALUES IN params BELOW:
--   win_days      trailing window for fee rates + realized price (90 = a quarter)
--   fin_rate      annual cost of capital, e.g. 0.12 for 12 pct. 0 = column reads 0.
--   soh_target_mo months of cover you want to hold (drives Excess Stock)
-- ============================================================================
with params as (
  select 90              as win_days,
         0.00::numeric   as fin_rate,
         2.0::numeric    as soh_target_mo
),

econ as (
  select se.asin,
         sum(se.units_sold)                                    as units_sold,
         sum(se.units_returned)                                as units_returned,
         sum(se.net_units_sold)                                as net_units,
         sum(se.net_sales)                                     as net_sales,
         sum(se.fba_fulfillment_fee_total)                     as fba_fee,
         sum(se.referral_fee_total)                            as referral_fee,
         sum(coalesce(se.referral_fee_refunds_total,0)
           + coalesce(se.refund_admin_fee_total,0))            as refund_cost,
         sum(coalesce(se.fba_storage_fee_total,0)
           + coalesce(se.aged_inventory_fee_total,0)
           + coalesce(se.storage_util_surcharge,0)
           + coalesce(se.low_inventory_fee_total,0))           as storage_fees,
         sum(coalesce(se.inbound_placement_fee_total,0)
           + coalesce(se.inbound_transport_fee_total,0))       as inbound_fees,
         sum(coalesce(se.sponsored_products_total,0))          as ad_spend_actual,
         min(se.week_start)                                    as first_week,
         max(se.week_start)                                    as last_week
  from sku_economics se cross join params p
  where se.region = 'US'
    and se.week_start >= current_date - p.win_days
  group by se.asin
),

vel as (
  select sw.master_id,
         sum(sw.units_ordered) / 90.0    as units_per_day,
         sum(sw.units_ordered) / 3.0     as units_per_month_3mo_avg
  from sales_weekly sw
  where sw.channel like 'amazon%'
    and sw.region = 'US'
    and sw.week_start >= current_date - 90
  group by sw.master_id
),

soh as (
  select distinct on (fis.asin)
         fis.asin,
         fis.snapshot_date,
         coalesce(fis.afn_fulfillable_quantity,0)              as fba_available,
         coalesce(fis.afn_inbound_working_quantity,0)
           + coalesce(fis.afn_inbound_shipped_quantity,0)
           + coalesce(fis.afn_inbound_receiving_quantity,0)    as fba_inbound,
         coalesce(fis.afn_fulfillable_quantity,0)
           + coalesce(fis.afn_reserved_quantity,0)
           + coalesce(fis.afn_inbound_working_quantity,0)
           + coalesce(fis.afn_inbound_shipped_quantity,0)
           + coalesce(fis.afn_inbound_receiving_quantity,0)    as soh_total
  from fba_inventory_snapshots fis
  where fis.region = 'US'
  order by fis.asin, fis.snapshot_date desc
),

base as (
  select
    p.sp_sku, p.asin, p.brand, p.title, p.msrp,
    e.first_week, e.last_week, e.net_units, e.net_sales,
    round(e.net_sales / nullif(e.net_units,0), 2)               as price,
    round(e.units_returned::numeric
          / nullif(e.units_sold,0) * 100, 2)                    as refunds_pct,
    round(e.refund_cost  / nullif(e.net_units,0), 4)            as refund_cost_pu,
    round(e.fba_fee      / nullif(e.net_units,0), 4)            as amzn_fba_fee,
    null::numeric                                               as should_be_fba_fee,
    round(e.referral_fee / nullif(e.net_units,0), 4)            as referral_pu,
    round(coalesce(pc.amazon_cogs,0)
        + (e.inbound_fees + e.storage_fees)
          / nullif(e.net_units,0), 4)                           as cogs_ship_storage,
    coalesce(pc.amazon_cogs,0)                                  as unit_cogs_only,
    s.snapshot_date, s.fba_available, s.fba_inbound, s.soh_total,
    round(v.units_per_day, 3)                                   as units_per_day,
    round(v.units_per_month_3mo_avg, 1)                         as units_per_month_3mo,
    round(s.soh_total / nullif(v.units_per_month_3mo_avg,0), 2) as stock_cover_months,
    round(e.ad_spend_actual, 2)                                 as ad_spend_actual,
    round(e.ad_spend_actual / nullif(e.net_sales,0) * 100, 2)   as actual_acos_pct,
    pr.fin_rate, pr.soh_target_mo
  from econ e
  cross join params pr
  join products p on p.asin = e.asin
  left join product_cogs pc on pc.master_id = p.master_id
  left join vel v on v.master_id = p.master_id
  left join soh s on s.asin = e.asin
  where p.active is not false
),

costed as (
  select b.*,
    round(b.unit_cogs_only * b.fin_rate
          * (coalesce(b.stock_cover_months,0) * 30.0 / 365.0), 4) as finance_cost_adj
  from base b
),

final as (
  select c.*,
    round(coalesce(c.refund_cost_pu,0) + coalesce(c.amzn_fba_fee,0)
        + coalesce(c.referral_pu,0)    + coalesce(c.cogs_ship_storage,0)
        + coalesce(c.finance_cost_adj,0), 4)                    as total_cost
  from costed c
)

select
  sp_sku               as "SKU",
  asin                 as "ASIN",
  brand                as "Brand",
  title                as "Product Title",
  price                as "Price",
  msrp                 as "MSRP list",
  refunds_pct          as "Refunds pct",
  refund_cost_pu       as "Refund Cost",
  amzn_fba_fee         as "AMZN FBA Fee",
  should_be_fba_fee    as "Should be FBA Fee",
  referral_pu          as "Referral Fees",
  cogs_ship_storage    as "COGS+Shipping+Storage",
  finance_cost_adj     as "Finance cost Adjustment",
  total_cost           as "Total Cost",
  round(price - total_cost, 4)                              as "Non-Ad Profit",
  round((price - total_cost) / nullif(price,0) * 100, 2)    as "Break Even ACOS pct",
  round(price / nullif(price - total_cost, 0), 2)           as "Break Even ROAS",
  units_per_day        as "Daily Sales Velocity",
  units_per_month_3mo  as "Avg Units per Month 3mo",
  soh_total            as "SOH total",
  fba_available        as "SOH Available",
  fba_inbound          as "SOH Inbound",
  snapshot_date        as "SOH As Of",
  stock_cover_months   as "Stock Cover Months",
  soh_target_mo        as "SOH Target Assumption Months",
  round(units_per_month_3mo * soh_target_mo, 0)                 as "SOH Target Units",
  round(soh_total - (units_per_month_3mo * soh_target_mo), 0)   as "Excess Stock",
  ad_spend_actual      as "Actual Ad Spend window",
  actual_acos_pct      as "Actual ACOS pct",
  net_units            as "Net Units window",
  round(net_sales,2)   as "Net Sales window",
  first_week           as "Window Start",
  last_week            as "Window End"
from final
where net_units > 0
order by brand, net_sales desc
