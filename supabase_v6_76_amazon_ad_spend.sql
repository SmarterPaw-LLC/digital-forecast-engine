-- ============================================================================
-- Amazon Ads — non-SP per-product spend (v6.76)
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- WHY
-- ----
-- The Amazon SKU Economics report tracks Sponsored Products ad spend per ASIN
-- (sku_economics.sponsored_products_total). But it does NOT include the other
-- Amazon ad types — Sponsored Brands, Sponsored Display, Sponsored TV, or
-- Amazon DSP. Those run through a separate billing system (Amazon Ads) and
-- their spend is invisible in the P&L today, overstating Net Proceeds by
-- ~$14k+ per 60-day window for SmarterPaw's account profile.
--
-- This table captures that missing spend per (date, ad_product, ASIN). The
-- per-ASIN granularity comes from Amazon Ads → Reports → Create report with
-- Advertised product ID as a dimension. Sponsored TV + most DSP rows will
-- have asin=null (those ad types are audience-level, not ASIN-targeted) —
-- those land as brand-level spend rolled up under advertiser_brand.
--
-- The P&L:
--   • SQL Economics' sponsored_products_total continues to drive SP ad spend
--     per ASIN — UNCHANGED.
--   • This table layers on SB/SD/DSP/TV spend. ASIN-matched rows extend the
--     per-product Ad Spend column; ASIN-blank rows feed a brand-level pool
--     that's surfaced as an "Other (brand-level)" line in the P&L scorecards.
-- ============================================================================

create table if not exists amazon_ad_spend (
  id                  bigserial primary key,
  date                date    not null,           -- daily grain
  region              text    not null,           -- 'US','CA','MX','EU/UK',… (resolved from marketplace + country)
  ad_product          text    not null,           -- 'sponsored_brands' | 'sponsored_display' | 'sponsored_tv' | 'dsp'
  advertiser_brand    text,                       -- 'Meowijuana' | 'Doggijuana' | 'Kitty Ka-Zoom' (normalized from Advertiser account name)
  asin                text,                       -- nullable — DSP/TV are audience-level
  master_id           text,                       -- nullable — resolved at import via products lookup
  marketplace         text,                       -- raw 'AMAZON.COM' / 'AMAZON.CA' for audit
  spend               numeric(12,4) not null default 0,
  impressions         integer default 0,
  clicks              integer default 0,
  purchases           integer default 0,
  attributed_sales    numeric(12,4) default 0,
  currency            text default 'USD',
  source              text default 'amazon-ads-unified',
  uploaded_at         timestamptz default now()
);

-- Unique key for replace-on-reupload. Functional `coalesce()` because asin AND
-- advertiser_brand are both nullable in different ad-product cases — without
-- coalesce, Postgres treats nulls as distinct and we'd accumulate duplicates
-- on every re-upload of the same period. Architecture Rule #5: parser MUST
-- use DELETE+INSERT (not upsert) — Supabase upsert silently degrades against
-- functional indexes.
create unique index if not exists amazon_ad_spend_uniq
  on amazon_ad_spend (date, region, ad_product, coalesce(asin,''), coalesce(advertiser_brand,''));

create index if not exists amazon_ad_spend_date_idx     on amazon_ad_spend (date);
create index if not exists amazon_ad_spend_asin_idx     on amazon_ad_spend (asin)      where asin      is not null;
create index if not exists amazon_ad_spend_master_idx   on amazon_ad_spend (master_id) where master_id is not null;
create index if not exists amazon_ad_spend_brand_idx    on amazon_ad_spend (advertiser_brand, date);

-- RLS — authenticated only (mirrors v6.47 lesson; never leave a new table
-- with RLS disabled even though Postgres-level grants exist).
alter table amazon_ad_spend enable row level security;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname='public' and tablename='amazon_ad_spend'
      and policyname='amazon_ad_spend_authenticated_all'
  ) then
    create policy amazon_ad_spend_authenticated_all
      on amazon_ad_spend for all to authenticated using (true) with check (true);
  end if;
end $$;
grant select, insert, update, delete on table amazon_ad_spend to authenticated;
grant usage, select on sequence amazon_ad_spend_id_seq to authenticated;
revoke all on table amazon_ad_spend from anon;

-- Verify (post-run):
--   select ad_product, count(*), round(sum(spend)::numeric, 2) as total_spend
--   from amazon_ad_spend group by 1 order by 1;
--
--   select advertiser_brand, ad_product,
--          count(*) filter (where asin is not null) as asin_matched,
--          count(*) filter (where asin is null)     as asin_blank
--   from amazon_ad_spend group by 1,2 order by 1,2;
