-- v10.36 — Chewy Ads per-SKU daily spend.
--
-- Source: Chewy Ads → Reports → "Promoted products", Group by = Day.
-- That report is the ONLY one carrying per-SKU spend with a date, and it spans
-- every advertiser (Meowijuana / Kitty Ka-Zoom / Doggijuana) in one file —
-- the Performance → Products UI export is per-advertiser and has no date.
--
-- ⚠ LTV ROAS does NOT exist at SKU level. Chewy only reports it per campaign
-- (Campaign Performance report). The SKU-level stand-in is
-- direct_sales + autoship_actualized_sales, which is REALISED revenue rather
-- than a model — weaker than true LTV, but honest. Columns are named for what
-- they are so nothing downstream can mistake one for the other.
--
-- ⚠ `direct_sales` is Chewy's RETAIL revenue (what the customer paid Chewy),
-- not what Chewy pays us. Break-even therefore compares retail-side ROAS
-- against our wholesale-side contribution; see the Break-Even tab.
--
-- Idempotent. Safe to re-run.

create table if not exists chewy_ad_spend (
  id                        bigserial primary key,
  date                      date        not null,
  advertiser                text        not null,          -- Meowijuana / Kitty Ka-Zoom / Doggijuana
  chewy_sku                 text        not null,          -- "Promoted Product" — joins products.chewy_sku
  campaign_id               text        not null,
  campaign                  text,
  campaign_type             text,                          -- Chewy Max / Sponsored Brand / Sponsored Product
  campaign_status           text,
  product_name              text,
  category                  text,
  chewy_list_price          numeric(12,2),                 -- retail price Chewy showed
  impressions               bigint      default 0,
  clicks                    bigint      default 0,
  spend                     numeric(14,2) default 0,
  direct_units              numeric(14,2) default 0,
  direct_sales              numeric(14,2) default 0,        -- RETAIL $, not our revenue
  total_orders              numeric(14,2) default 0,
  ntb_customers             numeric(14,2) default 0,
  autoship_signups          numeric(14,2) default 0,
  autoship_actualized_sales numeric(14,2) default 0,
  autoship_actualized_orders numeric(14,2) default 0,
  master_id                 text        references products(master_id) on delete set null,
  uploaded_at               timestamptz not null default now()
);

-- Plain-column unique index (NO coalesce) so upsert works and Architecture
-- Rule #5 does not apply. campaign_id is never null in the export, and a SKU
-- can legitimately appear under several campaigns on the same day.
create unique index if not exists chewy_ad_spend_uniq
  on chewy_ad_spend (date, advertiser, chewy_sku, campaign_id);

create index if not exists chewy_ad_spend_sku_date on chewy_ad_spend (chewy_sku, date);
create index if not exists chewy_ad_spend_master    on chewy_ad_spend (master_id);
create index if not exists chewy_ad_spend_date      on chewy_ad_spend (date);

-- RLS + grants, per the v6.47 hard rule: enable RLS, add an authenticated
-- policy, grant to authenticated, revoke anon. The grant alone is not enough —
-- RLS is what the Supabase linter checks.
alter table chewy_ad_spend enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'chewy_ad_spend'
      and policyname = 'chewy_ad_spend_authenticated_all'
  ) then
    create policy chewy_ad_spend_authenticated_all on chewy_ad_spend
      for all to authenticated using (true) with check (true);
  end if;
end $$;

grant select, insert, update, delete on table chewy_ad_spend to authenticated;
grant usage, select on sequence chewy_ad_spend_id_seq to authenticated;
revoke all on table chewy_ad_spend from anon;
