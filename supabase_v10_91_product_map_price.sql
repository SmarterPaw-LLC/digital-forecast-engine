-- v10.91 — MAP (Minimum Advertised Price) on products.
--
-- Jason: "i need a new dim on the product table for MAP"
--
-- Named map_price, NOT map: "map" is close enough to reserved/ambiguous SQL
-- that chewy_catalog already took the same decision in v10.11, and keeping
-- one name for one concept across both tables means a future join reads
-- cleanly (products.map_price vs chewy_catalog.map_price = ours vs theirs).
--
-- Nullable with no default on purpose: MAP is a policy some products have
-- and some do not, so NULL means "no MAP set" and 0 would be a real (and
-- nonsensical) floor of $0.00. Every read in the app treats null as "—".
--
-- Idempotent — safe to re-run.

alter table products
  add column if not exists map_price numeric(12,2);

comment on column products.map_price is
  'Minimum Advertised Price (USD, per unit). The lowest price this product '
  'may be ADVERTISED at. NULL = no MAP policy for this product. Distinct '
  'from msrp (list price) and wholesale (what we charge a reseller); a MAP '
  'typically sits between the two. Compare with chewy_catalog.map_price, '
  'which is the MAP Chewy records on their side.';

-- Sanity check: partial index so "which products have a MAP" stays cheap
-- without paying for the (common) null rows.
create index if not exists products_map_price_idx
  on products (map_price)
  where map_price is not null;
