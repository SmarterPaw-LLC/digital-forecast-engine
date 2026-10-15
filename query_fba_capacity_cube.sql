-- ============================================================================
-- FBA CAPACITY CUBE CALCULATOR
-- Built 2026-10-15 for the Q4 restock vs AWD decision.
--
-- THE QUESTION THIS ANSWERS:
--   Amazon gives capacity limits in CUBIC FEET, but Caitlyn's send list is in
--   UNITS. Nobody has converted one to the other, so "not all units will be
--   able to be sent with capacity limits" is unquantified. This computes the
--   cube so the gap is a number instead of a guess.
--
-- Oct 2026 capacity limits (from Caitlyn, 2026-10-14):
--   Meowijuana US   800.05 cu ft @ 78%  ->  ~176 cu ft free   <- THE CONSTRAINT
--   Doggijuana US 1,093.91 cu ft @ 26%  ->  ~809 cu ft free
--   KittyKaZoom US  179.67 cu ft @ 60%  ->   ~72 cu ft free
--   Meowijuana CA     2.83 cu ft @ 36%  ->    ~1.8 cu ft free
--   KittyKaZoom CA    6.95 cu ft @ 104% ->  OVER, cannot send
--
-- DATA SOURCE: products.longest_side / median_side / shortest_side +
--   unit_of_dimension come from the Amazon FBA Fee Preview upload (v9.73/v9.75).
--   products.case_qty is hand-entered (v7.27). Any SKU missing either will show
--   up in the gaps section at the bottom and needs filling before the total is
--   trustworthy.
--
-- HOW TO RUN: Data -> Query Database, paste SECTION 1 (or 2), hit Run Query.
-- ============================================================================


-- ============================================================================
-- SECTION 1: Per-SKU cube reference for every Meowijuana US SKU
-- Gives you cu ft per unit and per case so you can multiply by any send qty.
-- ============================================================================

with dims as (
  select
    p.master_id,
    p.sp_sku,
    p.brand,
    p.asin,
    p.title,
    p.case_qty,
    p.product_size_tier,
    p.item_package_weight,
    p.unit_of_weight,
    p.longest_side,
    p.median_side,
    p.shortest_side,
    p.unit_of_dimension,
    -- Normalize to cubic feet. Amazon returns inches on most US rows but
    -- centimeters on some (see v9.79 -- mixed units in the same feed).
    case
      when p.longest_side is null or p.median_side is null or p.shortest_side is null
        then null
      when lower(coalesce(p.unit_of_dimension,'inches')) like 'cent%'
        or lower(coalesce(p.unit_of_dimension,'inches')) like 'cm%'
        then (p.longest_side * p.median_side * p.shortest_side) / 28316.846592
      when lower(p.unit_of_dimension) like 'milli%'
        or lower(p.unit_of_dimension) like 'mm%'
        then (p.longest_side * p.median_side * p.shortest_side) / 28316846.592
      else  -- inches (default)
        (p.longest_side * p.median_side * p.shortest_side) / 1728.0
    end as cuft_per_unit
  from products p
  where p.active = true
    and p.brand = 'Meowijuana'       -- <<< change brand here
    and p.asin is not null
)
select
  sp_sku,
  title,
  asin,
  product_size_tier                                        as size_tier,
  case_qty,
  round(longest_side::numeric, 2) || ' x ' ||
    round(median_side::numeric, 2) || ' x ' ||
    round(shortest_side::numeric, 2) || ' ' ||
    coalesce(unit_of_dimension, '?')                       as dims,
  round(item_package_weight::numeric, 2) || ' ' ||
    coalesce(unit_of_weight, '?')                          as unit_weight,
  round(cuft_per_unit::numeric, 4)                         as cuft_per_unit,
  case when case_qty > 0
       then round((cuft_per_unit * case_qty)::numeric, 3)
  end                                                      as cuft_per_case,
  -- How many units fit in 176 cu ft (the Meowi US headroom) if you sent
  -- ONLY this SKU. Sanity-check on whether a single line can even fit.
  case when cuft_per_unit > 0
       then floor(176.0 / cuft_per_unit)
  end                                                      as units_in_176_cuft,
  -- Data-completeness flags
  case
    when cuft_per_unit is null and case_qty is null then 'NO DIMS + NO CASE QTY'
    when cuft_per_unit is null                      then 'NO DIMS (upload Fee Preview)'
    when case_qty is null or case_qty = 0           then 'NO CASE QTY (set on product card)'
    else 'ok'
  end                                                      as data_status
from dims
order by cuft_per_unit desc nulls last;


-- ============================================================================
-- SECTION 2: Send-list cube total
--
-- EDIT THE VALUES BLOCK with the actual send quantities, then run.
-- Quantities below are Caitlyn's 2026-10-14 recommendation with Jason's
-- annotations applied (the higher of the two where he asked for more).
--
-- Matching is on sp_sku. Replace the placeholder SKUs with the real ones from
-- SECTION 1's output -- I do not have the SP SKU mapping for these titles.
-- ============================================================================

/*
with send_list (sp_sku, send_units, note) as (values
  -- sp_sku,        units,  note
  ('REPLACE-01',     3500,  'Catnip Spray 3oz -- Jason: 30d seasonal closer to 3,500. CANNOT go AWD (dangerous goods)'),
  ('REPLACE-02',     2000,  'Meowi Waui -- Jason: ok for next 30 days if space low. AWD-eligible'),
  ('REPLACE-03',      540,  'Buds -- Jason: may need 2-3x the 180 rec, highly seasonal. AWD-eligible'),
  ('REPLACE-04',      144,  'Silvervine Sticks -- Jason: may need 2-3x the 48 rec'),
  ('REPLACE-05',      300,  'Spray Trio -- Jason: more like 300 based on trends. CANNOT go AWD'),
  ('REPLACE-06',      250,  'PurrEffect Trio'),
  ('REPLACE-07',      168,  'Rollies Single'),
  ('REPLACE-08',       60,  'Rollies 2pk'),
  ('REPLACE-09',       50,  'Crunchy Munchie'),
  ('REPLACE-10',       24,  'Whack N Roll'),
  ('REPLACE-11',       60,  'Jump N Jamb Squid'),
  ('REPLACE-12',       24,  'Feline Frost -- Jason: ok for next 30 days if space low')
),
dims as (
  select
    p.sp_sku,
    p.title,
    p.case_qty,
    case
      when p.longest_side is null or p.median_side is null or p.shortest_side is null
        then null
      when lower(coalesce(p.unit_of_dimension,'inches')) like 'cent%'
        or lower(coalesce(p.unit_of_dimension,'inches')) like 'cm%'
        then (p.longest_side * p.median_side * p.shortest_side) / 28316.846592
      else (p.longest_side * p.median_side * p.shortest_side) / 1728.0
    end as cuft_per_unit
  from products p
  where p.active = true
),
joined as (
  select
    s.sp_sku,
    coalesce(d.title, '(SKU NOT FOUND)')          as title,
    s.send_units,
    d.case_qty,
    d.cuft_per_unit,
    round((s.send_units * d.cuft_per_unit)::numeric, 2) as send_cuft,
    case when d.case_qty > 0
         then ceil(s.send_units::numeric / d.case_qty)
    end                                            as cases,
    s.note
  from send_list s
  left join dims d on d.sp_sku = s.sp_sku
)
select
  sp_sku, title, send_units, case_qty, cases,
  round(cuft_per_unit::numeric, 4) as cuft_per_unit,
  send_cuft,
  round((100.0 * send_cuft / nullif(sum(send_cuft) over (), 0))::numeric, 1) as pct_of_send_cube,
  note
from joined
union all
select
  'TOTAL', '', sum(send_units), null, sum(cases), null, sum(send_cuft),
  100.0,
  'vs 176 cu ft Meowi US headroom -> ' ||
    case when sum(send_cuft) > 176 then 'OVER BY ' || round((sum(send_cuft) - 176)::numeric, 1) || ' cu ft'
         else round((176 - sum(send_cuft))::numeric, 1) || ' cu ft to spare' end
from joined
order by send_cuft desc nulls last;
*/


-- ============================================================================
-- SECTION 3: Data gaps -- which SKUs block the cube math
-- Run this first. If it returns rows, SECTION 2's total is understated.
-- ============================================================================

/*
select
  p.brand,
  p.sp_sku,
  p.title,
  p.asin,
  p.case_qty,
  p.longest_side, p.median_side, p.shortest_side, p.unit_of_dimension,
  case
    when p.longest_side is null and (p.case_qty is null or p.case_qty = 0)
      then 'BOTH MISSING -- upload Fee Preview + set case qty'
    when p.longest_side is null
      then 'DIMS MISSING -- upload FBA Fee Preview for this brand account'
    else 'CASE QTY MISSING -- set on the product card (Products -> edit)'
  end as fix
from products p
where p.active = true
  and p.asin is not null
  and p.brand in ('Meowijuana','Doggijuana','Kitty Ka-Zoom')
  and (p.longest_side is null or p.case_qty is null or p.case_qty = 0)
order by p.brand, p.sp_sku;
*/
