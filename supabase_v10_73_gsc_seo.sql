-- ===========================================================================
-- v10.73 - Google Search Console archive (SEO tab, phase 1)
-- ===========================================================================
-- Jason: "we will build an seo tab in the digital forecast engine as a unified
-- keyword tracker tool."
--
-- The daily GSC pulls archived in smarterpaw-blog/gsc-data/ and
-- kitty-kazoom-blog/gsc-data/ since May 2026 are already a longitudinal
-- position-and-impressions database for every query either site surfaces on.
-- That is a rank tracker built out of Google's own numbers rather than scraped
-- estimates - it just has never been queryable. These tables make it so.
--
-- The pull scripts and their OAuth tokens STAY in the two blog repos where
-- they already work. The loader in this project reads their gsc-data/<date>/
-- snapshot folders by path. Nothing about the daily pull changes.
--
-- ---------------------------------------------------------------------------
-- WHY THERE IS AN IMPRESSIONS FLOOR
-- ---------------------------------------------------------------------------
-- Measured on the 2026-10-19 SmarterPaw snapshot: 112,657 queries, of which
--   impressions >= 3  -> 30,230 (26.8%)
--   impressions >= 10 -> 13,308 (11.8%)
-- So ~88% of rows are 1-2 impression noise over a SIXTEEN MONTH window. Each
-- pull is a trailing-window snapshot, not a delta, so consecutive snapshots
-- overlap almost entirely and storing the raw tail 59 times over is mostly
-- storing nothing 59 times. Counted across ALL 109 archived snapshots
-- (59 smarterpaw + 50 kittykazoom), not extrapolated:
--
--   floor   gsc_query    gsc_query_page   TOTAL (incl. pages)
--   0       6,323,402     9,844,871       16.26 M
--   3       1,691,358     2,746,454        4.53 M
--   10        734,270     1,194,433        2.02 M
--
-- The floor is a LOADER argument, recorded per snapshot in gsc_snapshots so a
-- row's provenance is never ambiguous. Use 10 for smarterpaw.com; use 0 for
-- kittykazoom, whose entire latest snapshot is only 1,020 queries and would be
-- gutted by any floor at all.
--
-- Run once in Supabase -> SQL Editor. Idempotent.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. One row per (property, snapshot_date). The provenance record.
-- ---------------------------------------------------------------------------
create table if not exists gsc_snapshots (
  id                bigserial primary key,
  property          text        not null,          -- 'smarterpaw' | 'kittykazoom'
  site_url          text,                          -- 'sc-domain:smarterpaw.com'
  snapshot_date     date        not null,          -- the gsc-data/<date>/ folder
  window_start      date,                          -- min(by_date day) in the pull
  window_end        date,                          -- max(by_date day) in the pull
  impressions_floor integer     not null default 0,-- what the loader applied
  query_rows        integer     not null default 0,
  page_rows         integer     not null default 0,
  query_page_rows   integer     not null default 0,
  loaded_at         timestamptz not null default now(),
  unique (property, snapshot_date)
);

comment on table  gsc_snapshots is 'One row per GSC pull folder. Records the impressions floor the loader applied, so a row never has ambiguous provenance.';
comment on column gsc_snapshots.impressions_floor is 'Rows below this were NOT loaded. 0 = everything. Changing it means reloading that snapshot.';

-- ---------------------------------------------------------------------------
-- 2. Per query, per snapshot. The rank tracker.
-- ---------------------------------------------------------------------------
create table if not exists gsc_query (
  snapshot_id   bigint  not null references gsc_snapshots(id) on delete cascade,
  property      text    not null,   -- denormalised: every filter leads with it
  snapshot_date date    not null,
  query         text    not null,
  clicks        integer not null default 0,
  impressions   integer not null default 0,
  ctr_pct       numeric(8,4),
  avg_position  numeric(8,2),
  primary key (snapshot_id, query)
);

comment on table gsc_query is 'Per-query performance per pull. position is the metric that makes this a rank tracker.';

create index if not exists gsc_query_prop_date_idx on gsc_query (property, snapshot_date);
-- The time-series lookup: one query across every snapshot.
create index if not exists gsc_query_series_idx    on gsc_query (property, query, snapshot_date);
-- Striking-distance scans: position band within a snapshot, biggest first.
create index if not exists gsc_query_pos_idx       on gsc_query (property, snapshot_date, avg_position)
  where impressions > 0;

-- ---------------------------------------------------------------------------
-- 3. Per page, per snapshot. Small (about 1.7k rows a pull) - no floor needed.
-- ---------------------------------------------------------------------------
create table if not exists gsc_page (
  snapshot_id   bigint  not null references gsc_snapshots(id) on delete cascade,
  property      text    not null,
  snapshot_date date    not null,
  page          text    not null,
  clicks        integer not null default 0,
  impressions   integer not null default 0,
  ctr_pct       numeric(8,4),
  avg_position  numeric(8,2),
  primary key (snapshot_id, page)
);

create index if not exists gsc_page_prop_date_idx on gsc_page (property, snapshot_date);
create index if not exists gsc_page_series_idx    on gsc_page (property, page, snapshot_date);

-- ---------------------------------------------------------------------------
-- 4. Which page Google ties to which query. Cannibalisation + coverage.
-- ---------------------------------------------------------------------------
create table if not exists gsc_query_page (
  snapshot_id   bigint  not null references gsc_snapshots(id) on delete cascade,
  property      text    not null,
  snapshot_date date    not null,
  query         text    not null,
  page          text    not null,
  clicks        integer not null default 0,
  impressions   integer not null default 0,
  ctr_pct       numeric(8,4),
  avg_position  numeric(8,2),
  primary key (snapshot_id, query, page)
);

comment on table gsc_query_page is 'Query-to-page mapping. A query with several competing pages is cannibalisation; a high-impression query whose best page is a poor fit is a content gap.';

create index if not exists gsc_qp_prop_date_idx on gsc_query_page (property, snapshot_date);
create index if not exists gsc_qp_query_idx     on gsc_query_page (property, query, snapshot_date);
create index if not exists gsc_qp_page_idx      on gsc_query_page (property, page, snapshot_date);

-- ---------------------------------------------------------------------------
-- 5. Sitewide daily series. DIFFERENT GRAIN ON PURPOSE.
-- ---------------------------------------------------------------------------
-- Every pull reports the same trailing dates, so this is keyed on (property,
-- date) rather than per-snapshot and UPSERTED. The newest pull wins, because
-- GSC data firms up for ~3 days after the fact. That yields one clean daily
-- series instead of 59 overlapping copies of it.
create table if not exists gsc_by_date (
  property      text    not null,
  day           date    not null,          -- named `day` like shopify_sales_daily.day
  clicks        integer not null default 0,
  impressions   integer not null default 0,
  ctr_pct       numeric(8,4),
  avg_position  numeric(8,2),
  snapshot_date date,                      -- which pull last wrote this row
  updated_at    timestamptz not null default now(),
  primary key (property, day)
);

comment on table gsc_by_date is 'Sitewide clicks/impressions per day, deduped across pulls. Newest pull wins; GSC revises the last ~3 days.';

create index if not exists gsc_by_date_prop_idx on gsc_by_date (property, day desc);

-- ---------------------------------------------------------------------------
-- 6. RLS + grants.
-- ---------------------------------------------------------------------------
-- Hard rule since v6.47: enable RLS + a policy + grants on every new table, and
-- revoke anon. The grant alone is not enough; the Supabase linter checks RLS.
--
-- Also note Supabase's 2026-10-30 change: from that date new tables in `public`
-- no longer get Data API access automatically and REQUIRE an explicit grant in
-- the same migration. This project has always done that, so nothing changes -
-- but unlike Supabase's example we grant to `authenticated` only and revoke
-- anon, because the dashboard is behind a login and anon has no business here.
do $$
declare t text;
begin
  foreach t in array array['gsc_snapshots','gsc_query','gsc_page','gsc_query_page','gsc_by_date']
  loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists %I on %I', t || '_auth_all', t);
    execute format(
      'create policy %I on %I for all to authenticated using (true) with check (true)',
      t || '_auth_all', t);
    execute format('grant select, insert, update, delete on table %I to authenticated', t);
    execute format('revoke all on table %I from anon', t);
  end loop;
end $$;

-- gsc_snapshots.id is a bigserial, so the sequence needs a grant too or the
-- loader's INSERT fails with "permission denied for sequence".
grant usage, select on all sequences in schema public to authenticated;

-- Verify
-- select property, count(*) snapshots, min(snapshot_date), max(snapshot_date),
--        sum(query_rows) query_rows
--   from gsc_snapshots group by property order by property;
