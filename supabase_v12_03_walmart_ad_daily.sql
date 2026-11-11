-- ============================================================================
-- Walmart Connect — ADVERTISER DAILY PERFORMANCE  (v12.03)
-- Run ONCE in Supabase -> SQL Editor. Idempotent.
-- ============================================================================
-- WHY
-- ----
-- Jason: "i want to upload walmart ads on a weekly basis. i found a new report
-- here. i need to be able to drive performance for walmart ads"
--
-- Ad Center -> Reports -> Advertiser -> Report type: Daily performance.
-- ONE ROW PER DAY, with the date ON the row.
--
-- That is the single thing v11.25's two feeds do not have. walmart_ad_campaign
-- and walmart_ad_keyword stamp an operator-supplied MONTH onto every row,
-- because those exports carry no reporting date at all — which is why the
-- Walmart ad grain has been stuck at monthly since v11.67 and why a weekly
-- upload rhythm was not possible. This feed fixes the grain.
--
-- ============================================================================
-- /!\ IT HAS NO CAMPAIGN DIMENSION, AND THE TWO FEEDS MUST NEVER BE SUMMED
-- ============================================================================
-- This is the ADVERTISER total. It can say how the account is pacing day by
-- day; it cannot say which campaign to change.
--
--   walmart_ad_campaign   monthly,  per campaign   the LEVERS
--   walmart_ad_daily      daily,    per account    the PACING
--
-- They are the SAME DOLLARS at two grains. Adding them together double-counts
-- every dollar — the exact shape of the v11.79 storage trap, where two feeds
-- carried a number called "storage" and only one of them could be read for a
-- given month. Nothing in the app sums across these two tables, and nothing
-- should start to: the Daily area is its own sub-tab for that reason.
--
-- ⚠ They will also not tie out exactly even at the same window. The daily
-- report is pulled under a stated ATTRIBUTION SETTING (the console's
-- "Attribution: 14 days attribution" selector) and the campaign export under
-- whatever that selector said when IT was downloaded. A gap between the two is
-- a fact about attribution windows, not a loading error.
--
-- ============================================================================
-- /!\ NO BRAND DIMENSION EITHER
-- ============================================================================
-- advertiser_brand is resolved from the ACCOUNT name, which is the only brand
-- fact a row of this report carries. It is NOT the campaign-name resolution
-- walmart_ad_campaign uses, and it is weaker: the "Kitty Ka-Zoom (SmarterPaw
-- LLC)" account carries Doggijuana campaigns inside it, so an account total
-- cannot be split by brand. The Daily view therefore IGNORES the page's Brand
-- control and says so on its coverage line, rather than silently reporting the
-- whole account under one brand's name.
--
-- ============================================================================
-- /!\ THE DERIVED COLUMNS ARE DELIBERATELY NOT STORED
-- ============================================================================
-- The export carries Average CPC, CTR and ROAS. All three are derivable from
-- the columns beside them, and a stored copy is a second spelling of one
-- number (rule 3a) that cannot be summed: a week of daily CTRs does not add up
-- to the week's CTR. adsDeriveRow derives all three from the window totals,
-- exactly as it does for walmart_ad_campaign — which stores none of them
-- either.
--
-- ============================================================================
-- /!\ THE TRAILING DAYS RESTATE
-- ============================================================================
-- In the first file we saw, the newest day reported 243 clicks and $235.70 of
-- sales with ZERO page views and ZERO add-to-cart. Those are reported zeros,
-- not blanks, and they settle upward over the following days.
--
-- So the write is an UPSERT on (date, region, account): a weekly upload that
-- overlaps the previous one must be able to CORRECT days it already wrote.
-- Every key column is NOT NULL, so this is a plain unique index that PostgREST
-- can target — unlike walmart_ad_campaign, whose coalesce() index is the whole
-- reason Architecture Rule #5 exists.
--
-- ============================================================================
-- /!\ NO master_id, SO THE MERGE AUDIT IS A NO-OP
-- ============================================================================
-- This table carries no product key of any kind (Walmart puts the item
-- dimension in a separate Item report), so runMerge / SP-TEMP promotion /
-- doRestore have nothing to reassign in it and MERGE_MASTER_ID_TABLES gains no
-- row. Audited, not assumed — recorded here so the next reader does not
-- re-derive it.
-- ============================================================================

create table if not exists walmart_ad_daily (
  id               bigserial primary key,

  -- The three key columns. NOT NULL so the unique index below is plain.
  date             date        not null,
  region           text        not null default 'US',
  account          text        not null,

  advertiser_brand text,

  -- Flows. Every one of these sums over a window.
  impressions      bigint,
  clicks           bigint,
  spend            numeric(12,2) not null default 0,
  sales            numeric(12,2),
  dpv              bigint,
  atc              bigint,
  in_store_sales   numeric(12,2),

  uploaded_at      timestamptz not null default now()
);

-- One row per advertiser account per day. A second Walmart ad account (a
-- display program, or a per-brand account) lands beside this one rather than
-- overwriting it.
create unique index if not exists walmart_ad_daily_uniq
  on walmart_ad_daily (date, region, account);

create index if not exists walmart_ad_daily_date_idx   on walmart_ad_daily (date desc);
create index if not exists walmart_ad_daily_region_idx on walmart_ad_daily (region, date desc);

-- The app always signs in, so the grants go to `authenticated` — the same
-- posture every other table in this database has (v11.84). No service_role
-- grant is added here; nothing in this database has one.
grant select, insert, update, delete on walmart_ad_daily to authenticated;
grant usage, select on sequence walmart_ad_daily_id_seq to authenticated;

comment on table  walmart_ad_daily is
  'Walmart Connect Advertiser -> Daily performance export. ADVERTISER TOTAL, one row per day. Never sum with walmart_ad_campaign: same dollars, two grains.';
comment on column walmart_ad_daily.in_store_sales is
  'In-store purchases Walmart attributed back to an online ad click. A SECOND BASIS, stored beside the online figure and never folded into it (v11.25).';
comment on column walmart_ad_daily.dpv is
  'Total Product Detail Page Views. Restates upward for a few days after the date — the newest day in an export can report 0 against real clicks.';
