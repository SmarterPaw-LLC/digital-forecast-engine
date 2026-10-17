-- ============================================================================
-- CHEWY MARGIN AUDIT  --  "is the break-even data accurate?"
-- Built 2026-10-17.
--
-- Chewy BE ROAS = Chewy list price / contribution per unit, where
--   wholesale/each    = chewy_catalog.cost  (/ case_qty when purchase_uom = CS)
--   net to us         = wholesale x (1 - standing allowance %)
--   contribution/unit = net to us - COGS
--
-- A HIGH break-even therefore means a SMALL contribution, which has exactly
-- three possible causes. This query separates them so you can tell a real
-- margin problem from a data problem:
--
--   1. COGS TOO HIGH.  chewyPnlCogs() resolves
--        chewy_cogs -> landed_cost -> dtc_cogs -> amazon_cogs
--      Only the FIRST is a true Chewy cost. dtc_cogs carries DTC shipping +
--      pick/pack + overhead; amazon_cogs carries the FBA fulfilment fee. Neither
--      applies to a 1P pallet going to a Chewy DC, so either fallback OVERSTATES
--      Chewy cost and craters the margin. Column `cogs_source` below names which
--      one each SKU is actually using.
--
--   2. WHOLESALE TOO LOW.  A CS-priced row divided by a case_qty that is too
--      LARGE (or missing entirely) understates what Chewy pays us per each.
--      Columns `case_qty` / `uom` / `wholesale_per_each` expose it.
--
--   3. ALLOWANCES TOO HIGH.  The standing floor is summed from chewy_rebates.
--      Known gap (v10.51): FTAS trade-allowance lines carry their rate in the
--      rebate NAME, not in rebate_pct_rate, so they contribute 0% -- that makes
--      margins read BETTER than reality, not worse.
--
-- HOW TO RUN: Data -> Query Database, paste ONE section, Run Query.
-- (The runner wraps your query as a subquery, so paste one section at a time.)
-- ============================================================================


-- ============================================================================
-- SECTION 1: Which COGS field is each Chewy SKU actually using?
-- If `cogs_source` is anything other than 'chewy_cogs', that SKU's margin is
-- being computed off a cost that does not belong to Chewy.
-- ============================================================================

select
  p.brand,
  p.sp_sku,
  p.title,
  p.chewy_sku,
  p.case_qty,
  cc.purchase_uom                                            as uom,
  round(cc.cost::numeric, 4)                                 as catalog_cost,
  -- wholesale per each: CS rows divide by the case pack, EA rows are already per each
  case
    when cc.cost is null then null
    when upper(coalesce(cc.purchase_uom, 'EA')) like 'CS%'
      then case when coalesce(p.case_qty, 0) > 0
                then round((cc.cost / p.case_qty)::numeric, 4) end
    else round(cc.cost::numeric, 4)
  end                                                        as wholesale_per_each,
  round(pc.chewy_cogs::numeric,  4)                          as chewy_cogs,
  round(pc.landed_cost::numeric, 4)                          as landed_cost,
  round(pc.dtc_cogs::numeric,    4)                          as dtc_cogs,
  round(pc.amazon_cogs::numeric, 4)                          as amazon_cogs,
  -- the coalesce chain chewyPnlCogs() walks, made visible
  case
    when pc.chewy_cogs  is not null then 'chewy_cogs'
    when pc.landed_cost is not null then 'landed_cost   <- no fulfilment in it'
    when pc.dtc_cogs    is not null then 'dtc_cogs      <- WRONG: carries DTC ship + overhead'
    when pc.amazon_cogs is not null then 'amazon_cogs   <- WRONG: carries the FBA fee'
    else                                 'NONE          <- margin cannot be computed'
  end                                                        as cogs_source,
  round(coalesce(pc.chewy_cogs, pc.landed_cost, pc.dtc_cogs, pc.amazon_cogs)::numeric, 4)
                                                             as cogs_in_use,
  -- what the margin looks like at a 26.5% standing floor
  case
    when cc.cost is null then null
    when upper(coalesce(cc.purchase_uom,'EA')) like 'CS%' and coalesce(p.case_qty,0) = 0 then null
    else round((
      (case when upper(coalesce(cc.purchase_uom,'EA')) like 'CS%'
            then cc.cost / p.case_qty else cc.cost end) * (1 - 0.265)
      - coalesce(pc.chewy_cogs, pc.landed_cost, pc.dtc_cogs, pc.amazon_cogs, 0)
    )::numeric, 4)
  end                                                        as contribution_per_unit
from products p
join chewy_catalog cc on cc.chewy_sku = p.chewy_sku
left join product_cogs pc on pc.master_id = p.master_id
where p.active = true
  and p.chewy_sku is not null
order by
  case
    when pc.chewy_cogs is not null then 4
    when pc.landed_cost is not null then 3
    when pc.dtc_cogs is not null then 2
    when pc.amazon_cogs is not null then 1
    else 0
  end,                        -- worst data first
  p.brand, p.sp_sku;


-- ============================================================================
-- SECTION 2: One-line summary -- how many SKUs are on a wrong-channel COGS?
-- This is the number that answers "is the data accurate" in one row.
-- ============================================================================

/*
select
  count(*)                                                                  as chewy_skus,
  count(*) filter (where pc.chewy_cogs is not null)                         as using_chewy_cogs_ok,
  count(*) filter (where pc.chewy_cogs is null and pc.landed_cost is not null)
                                                                            as using_landed_no_fulfilment,
  count(*) filter (where pc.chewy_cogs is null and pc.landed_cost is null
                     and pc.dtc_cogs is not null)                           as using_DTC_cogs_WRONG,
  count(*) filter (where pc.chewy_cogs is null and pc.landed_cost is null
                     and pc.dtc_cogs is null and pc.amazon_cogs is not null)
                                                                            as using_AMAZON_cogs_WRONG,
  count(*) filter (where coalesce(pc.chewy_cogs, pc.landed_cost, pc.dtc_cogs, pc.amazon_cogs) is null)
                                                                            as no_cogs_at_all,
  count(*) filter (where upper(coalesce(cc.purchase_uom,'EA')) like 'CS%'
                     and coalesce(p.case_qty,0) = 0)                        as case_priced_missing_case_qty
from products p
join chewy_catalog cc on cc.chewy_sku = p.chewy_sku
left join product_cogs pc on pc.master_id = p.master_id
where p.active = true and p.chewy_sku is not null;
*/


-- ============================================================================
-- SECTION 3: The allowance stack -- what is actually in the 26.5% floor?
-- Confirms the floor is built from real invoice rates, and shows the FTAS
-- lines that parse rate-less (they contribute 0%, so the floor is if anything
-- UNDERSTATED, which flatters the margin rather than hurting it).
-- ============================================================================

/*
select
  rebate_name,
  max(rebate_pct_rate)                                as pct_rate,
  count(*)                                            as invoice_lines,
  round(sum(amount)::numeric, 2)                      as total_billed,
  min(invoice_date)                                   as first_seen,
  max(invoice_date)                                   as last_seen,
  case when max(rebate_pct_rate) is null
       then 'RATE-LESS -- contributes 0% to the floor (rate lives in the name)'
       else 'in the floor' end                        as in_floor
from chewy_rebates
group by rebate_name
order by max(rebate_pct_rate) desc nulls last, total_billed desc;
*/
