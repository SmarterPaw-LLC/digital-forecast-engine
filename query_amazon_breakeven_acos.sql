-- ============================================================================
-- Amazon all-in cost + break-even ACOS / ROAS  (per ASIN, US)
-- Feeds the Amazon financial-controls tool.
-- Run in Data -> Query Database, then hit "Download CSV" in the results header.
--
-- TUNE THE THREE VALUES IN params BELOW:
--   win_days      trailing window for fee rates + realized price (90 = a quarter)
--   fin_rate      annual cost of capital, e.g. 0.12 for 12 pct. 0 = column reads 0.
--   soh_target_mo months of cover you want to hold (drives Excess Stock)
--
-- v2 changes:
--   + removal fees, AWD storage/transport folded into the cost stack
--   + FBA reimbursement applied as a credit
--   + Amazon's own net_proceeds_total exposed as a reconciliation check
--   + non-SP ad spend (Sponsored Brands / Display / DSP / TV) folded into
--     Actual Ad Spend and Actual ACOS, per ASIN
--   + Low Volume flag so sub-25-unit SKUs are not misread as unprofitable
-- ============================================================================
with params as (
  select 90              as win_days,
         0.00::numeric   as fin_rate,
         2.0::numeric    as soh_target_mo,
         25::int         as min_units_for_confidence
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
         -- v2: removal + Amazon Warehousing & Distribution were missing from v1
         sum(coalesce(se.removal_fee_total,0))                 as removal_fees,
         sum(coalesce(se.awd_storage_fee_total,0)
           + coalesce(se.awd_transport_fee_total,0))           as awd_fees,
         -- v2: reimbursement is a CREDIT, it reduces net cost
         sum(coalesce(se.fba_reimbursement_total,0))           as reimbursement,
         -- v2: Amazon's own figure, used as a reconciliation check below
         sum(coalesce(se.net_proceeds_total,0))                as amzn_net_proceeds,
         sum(coalesce(se.sponsored_products_total,0))          as sp_ad_spend,
         min(se.week_start)                                    as first_week,
         max(se.week_start)                                    as last_week
  from sku_economics se cross join params p
  where se.region = 'US'
    and se.week_start >= current_date - p.win_days
  group by se.asin
),

-- v2: Sponsored Brands / Display / DSP / Sponsored TV bill through Amazon Ads,
-- not Seller Central, so they are absent from sku_economics entirely. Only
-- ASIN-attributed rows can be allocated to a SKU; DSP and Sponsored TV are
-- audience-level and carry a null ASIN, so they stay out of this table by
-- design rather than being spread across SKUs on an invented rule.
ads as (
  select ad.asin,
         sum(ad.spend) as nonsp_ad_spend
  from amazon_ad_spend ad cross join params p
  where ad.region = 'US'
    and ad.asin is not null
    and ad.ad_product <> 'sponsored_products'
    and ad.date >= current_date - p.win_days
  group by ad.asin
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

-- Amazon's FBA Fee Preview: dimensions, weight, assigned size tier and
-- Amazon's OWN expected fulfillment fee. That last field is "Should be FBA
-- Fee" directly, so no fee-tier lookup has to be maintained here.
-- Latest snapshot per ASIN wins. Coverage is per Seller Central account, so a
-- brand whose export has not been uploaded comes back null rather than wrong.
feeprev as (
  select distinct on (fp.asin)
         fp.asin,
         fp.expected_fulfillment_fee_per_unit          as should_be_fba_fee,
         fp.expected_future_fulfillment_fee_per_unit   as future_fba_fee,
         fp.estimated_referral_fee_per_unit            as expected_referral_fee,
         fp.product_size_tier,
         fp.item_package_weight, fp.unit_of_weight,
         fp.longest_side, fp.median_side, fp.shortest_side, fp.unit_of_dimension,
         fp.snapshot_date                              as fee_snapshot_date
  from fba_fee_preview fp
  where fp.region = 'US'
    and fp.asin is not null
  order by fp.asin, fp.snapshot_date desc
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
    fpv.should_be_fba_fee,
    fpv.future_fba_fee, fpv.expected_referral_fee,
    fpv.product_size_tier, fpv.item_package_weight, fpv.unit_of_weight,
    fpv.longest_side, fpv.median_side, fpv.shortest_side, fpv.unit_of_dimension,
    fpv.fee_snapshot_date,
    round(e.referral_fee / nullif(e.net_units,0), 4)            as referral_pu,
    -- COGS + logistics bucket. v2 adds removal + AWD and nets the
    -- reimbursement credit, so this is now the full landed-to-shelf cost.
    round(coalesce(pc.amazon_cogs,0)
        + (e.inbound_fees + e.storage_fees + e.removal_fees
           + e.awd_fees - e.reimbursement)
          / nullif(e.net_units,0), 4)                           as cogs_ship_storage,
    coalesce(pc.amazon_cogs,0)                                  as unit_cogs_only,
    -- audit columns so each added component stays visible
    round(e.removal_fees   / nullif(e.net_units,0), 4)          as removal_pu,
    round(e.awd_fees       / nullif(e.net_units,0), 4)          as awd_pu,
    round(e.reimbursement  / nullif(e.net_units,0), 4)          as reimb_pu,
    round(e.inbound_fees   / nullif(e.net_units,0), 4)          as inbound_pu,
    round(e.storage_fees   / nullif(e.net_units,0), 4)          as storage_pu,
    round(e.amzn_net_proceeds / nullif(e.net_units,0), 4)       as amzn_np_pu,
    s.snapshot_date, s.fba_available, s.fba_inbound, s.soh_total,
    round(v.units_per_day, 3)                                   as units_per_day,
    round(v.units_per_month_3mo_avg, 1)                         as units_per_month_3mo,
    round(s.soh_total / nullif(v.units_per_month_3mo_avg,0), 2) as stock_cover_months,
    round(e.sp_ad_spend, 2)                                     as sp_ad_spend,
    round(coalesce(a.nonsp_ad_spend,0), 2)                      as nonsp_ad_spend,
    round(e.sp_ad_spend + coalesce(a.nonsp_ad_spend,0), 2)      as total_ad_spend,
    round((e.sp_ad_spend + coalesce(a.nonsp_ad_spend,0))
          / nullif(e.net_sales,0) * 100, 2)                     as actual_acos_pct,
    pr.fin_rate, pr.soh_target_mo, pr.min_units_for_confidence
  from econ e
  cross join params pr
  join products p on p.asin = e.asin
  left join product_cogs pc on pc.master_id = p.master_id
  left join vel v on v.master_id = p.master_id
  left join soh s on s.asin = e.asin
  left join ads a on a.asin = e.asin
  left join feeprev fpv on fpv.asin = e.asin
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
        + coalesce(c.finance_cost_adj,0), 4)                    as total_cost,
    -- Reconciliation: Amazon's own net proceeds per unit vs what our fee
    -- capture implies. A delta near zero means we are capturing every fee
    -- Amazon charged. A persistent gap means a fee line is still missing.
    round(c.price
        - coalesce(c.refund_cost_pu,0) - coalesce(c.amzn_fba_fee,0)
        - coalesce(c.referral_pu,0)    - coalesce(c.inbound_pu,0)
        - coalesce(c.storage_pu,0)     - coalesce(c.removal_pu,0)
        - coalesce(c.awd_pu,0)         + coalesce(c.reimb_pu,0)
        - (c.sp_ad_spend / nullif(c.net_units,0)), 4)           as derived_np_pu
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
  round(amzn_fba_fee - should_be_fba_fee, 4)                as "FBA Fee Variance",
  referral_pu          as "Referral Fees",
  cogs_ship_storage    as "COGS+Shipping+Storage",
  finance_cost_adj     as "Finance cost Adjustment",
  total_cost           as "Total Cost",
  round(price - total_cost, 4)                              as "Non-Ad Profit",
  round((price - total_cost) / nullif(price,0) * 100, 2)    as "Break Even ACOS pct",
  round(price / nullif(price - total_cost, 0), 2)           as "Break Even ROAS",
  case when net_units < min_units_for_confidence
       then 'LOW VOLUME - cost per unit unreliable' else '' end as "Confidence Flag",
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
  sp_ad_spend          as "Ad Spend SP",
  nonsp_ad_spend       as "Ad Spend non-SP",
  total_ad_spend       as "Actual Ad Spend window",
  actual_acos_pct      as "Actual ACOS pct",
  -- product dimensions + size tier, from Amazon FBA Fee Preview
  product_size_tier    as "Size Tier",
  item_package_weight  as "Pkg Weight",
  unit_of_weight       as "Weight Unit",
  longest_side         as "Longest Side",
  median_side          as "Median Side",
  shortest_side        as "Shortest Side",
  unit_of_dimension    as "Dim Unit",
  future_fba_fee       as "Expected Future FBA Fee",
  expected_referral_fee as "Expected Referral Fee",
  fee_snapshot_date    as "Fee Preview As Of",
    -- audit / reconciliation block
  inbound_pu           as "aud Inbound per unit",
  storage_pu           as "aud Storage per unit",
  removal_pu           as "aud Removal per unit",
  awd_pu               as "aud AWD per unit",
  reimb_pu             as "aud Reimbursement per unit",
  amzn_np_pu           as "aud Amzn Net Proceeds per unit",
  derived_np_pu        as "aud Derived Net Proceeds per unit",
  round(derived_np_pu - amzn_np_pu, 4)                      as "aud Recon Delta",
  net_units            as "Net Units window",
  round(net_sales,2)   as "Net Sales window",
  first_week           as "Window Start",
  last_week            as "Window End"
from final
where net_units > 0
order by brand, net_sales desc
