-- ===========================================================================
-- v11.36 - GA4 traffic archive (SEO/Traffic tab, phase 1)
-- ===========================================================================
-- Jason, pointing at a Looker Studio "GA4 - Top of Funnel DTC" report:
--   "do you have a stream of data to build this view into the SEO page?"
--
-- Yes. smarterpaw-blog/ga4_pull.py has been authenticated against GA4 property
-- 363832203 since June 2026 and still refreshes without a prompt. It had run
-- exactly ONCE (2026-06-18, 61 days) while GSC had 59 snapshots loaded, so the
-- pipeline existed and the archive did not. These tables are the archive.
--
-- The pull script and its OAuth token STAY in smarterpaw-blog, where they
-- already work. load_ga4.py in this project reads ga4-data/<date>/ by path.
-- That is the same split supabase_v10_73_gsc_seo.sql established for GSC, and
-- the `property` vocabulary is deliberately identical ('smarterpaw',
-- 'kittykazoom') so one picker can drive both feeds.
--
-- Backfilled 2026-11-02: 2023-06-22 .. 2026-11-02, 1,230 days, 194,957 rows.
--
-- ---------------------------------------------------------------------------
-- WHY THESE ARE UPSERT TABLES AND NOT SNAPSHOT TABLES
-- ---------------------------------------------------------------------------
-- gsc_query is keyed per snapshot because each GSC pull is a 16-month trailing
-- AGGREGATE whose avg_position means something different in every pull. GA4 is
-- not like that: a day's figures are settled within ~48h and never restate, so
-- storing them 60 times would be storing the same numbers 60 times.
--
-- So every table here is keyed on (property, <grain>) and UPSERTED, the
-- gsc_by_date pattern. The newest pull wins. `snapshot_date` records which
-- pull last wrote the row, so provenance survives without a row per pull.
--
-- ---------------------------------------------------------------------------
-- TWO COLUMNS MUST NEVER BE SUMMED ACROSS ROWS
-- ---------------------------------------------------------------------------
-- total_users and purchasers are DE-DUPLICATED WITHIN THEIR OWN ROW'S PERIOD.
-- A visitor who returns on Tuesday is one user for the month and two across two
-- daily rows. Measured on Oct 2026, period total vs sum of the 31 day rows:
--
--     sessions          16,292  ->  16,331   +0.24%
--     total_users       14,401  ->  15,284   +6.13%   <-- NEVER SUM
--     new_users         14,013  ->  14,013    0.00%
--     engaged_sessions   7,335  ->   7,283   -0.71%
--     revenue         8,485.01  -> 8,485.01   0.00%
--     transactions         354  ->     354    0.00%
--     purchasers           350  ->     357   +2.00%   <-- NEVER SUM
--     key_events         4,030  ->   4,030    0.00%
--
-- They carry no `_day` suffix on purpose: the same column exists in
-- ga4_by_date and in ga4_by_month, so a suffix naming one grain would be false
-- in the other table. The rule lives in these comments and on the dashboard
-- column, not in a name that is wrong half the time.
--
-- ---------------------------------------------------------------------------
-- AND THAT IS WHY ga4_by_month EXISTS
-- ---------------------------------------------------------------------------
-- GA4 estimates sessions per request, so summing days does not reproduce what
-- it reports for the same span, and the gap widens with the window:
--
--     1 month        16,292  ->  16,331   +0.24%
--     3 months       46,233  ->  46,414   +0.39%
--     10 months     131,726  -> 133,050   +1.01%
--     1,230 days    681,779  -> 696,346   +2.14%
--
-- GA4 de-duplicates inside whatever window it is asked for, so a month row is
-- EXACT for that month - users included. Verified 2026-11-02 against the API's
-- own period query for October on all seven metrics, to the cent.
--
-- Month-aligned windows (MTD, last month, a quarter) read off ga4_by_month and
-- are exact. An arbitrary window sums ga4_by_date and is within ~1%, and the
-- card should SAY which of the two it did rather than quietly disagreeing with
-- GA4. Summing several month rows re-introduces the same drift as summing
-- days, so the anchor is exact per month, not per multi-month span.
--
-- ---------------------------------------------------------------------------
-- LANDING PAGE SESSIONS DO NOT RECONCILE TO SITEWIDE, BY ~7%
-- ---------------------------------------------------------------------------
-- Same window (Oct 2026), sitewide 16,292 sessions:
--     date                 16,331   +0.24%
--     date x channel       16,316   +0.15%
--     date x device        16,323   +0.19%
--     landing page         17,394   +6.76%   <-- cannot be a top line
--
-- And across the full history 144,689 of 814,238 landing-page sessions (17.8%)
-- land in GA4's own '(not set)' bucket, where it could not resolve the first
-- pageview. A further 74 rows carry a genuinely EMPTY landing_page, all from
-- the property's first weeks in 2023; the loader stores what GA4 said and does
-- not merge the two, because '(not set)' and '' are different GA4 states.
--
-- So ga4_by_date_landing_page answers WHICH PAGE EARNS THE VISIT. It must
-- never be the source of a Sessions figure sitting beside the sitewide card -
-- two numbers on one screen that cannot both be true.
--
-- There is no '(other)' bucket: checked over 10 months / 34,732 rows, so the
-- page list is complete rather than cardinality-capped.
--
-- ---------------------------------------------------------------------------
-- NOT STORED, DELIBERATELY
-- ---------------------------------------------------------------------------
-- engagement_rate   is EXACTLY engaged_sessions / sessions (drift 0.00e+00,
--                   measured by device on Oct 2026). Derive it at read time;
--                   a stored ratio beside its own inputs is two numbers free
--                   to disagree.
-- purchase_revenue  is IDENTICAL to revenue on this property. One column.
-- source/medium     ga4_pull.py still writes by_source_medium.csv for ad-hoc
--                   work, but it is a PERIOD AGGREGATE WITH NO DATE COLUMN.
--                   Loading that would put a figure in the database whose
--                   window is whatever the last pull happened to use - the
--                   v11.22 trap. Channel group is the rolled-up version of the
--                   same thing and IS at date grain. If source/medium detail
--                   is ever wanted, pull it at date grain and give it a table.
--
-- Run once in Supabase -> SQL Editor. Idempotent.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. One row per (property, snapshot_date). The provenance record.
-- ---------------------------------------------------------------------------
create table if not exists ga4_snapshots (
  id              bigserial primary key,
  property        text        not null,          -- 'smarterpaw' | 'kittykazoom'
  property_id     text,                          -- GA4 numeric property, e.g. '363832203'
  site            text,                          -- 'smarterpaw.com'
  snapshot_date   date        not null,          -- the ga4-data/<date>/ folder
  window_start    date,                          -- what the pull asked GA4 for
  window_end      date,
  pulled_at       timestamptz,                   -- from the pull's own meta.json
  date_rows       integer     not null default 0,
  month_rows      integer     not null default 0,
  channel_rows    integer     not null default 0,
  device_rows     integer     not null default 0,
  page_rows       integer     not null default 0,
  loaded_at       timestamptz not null default now(),
  unique (property, snapshot_date)
);

comment on table  ga4_snapshots is 'One row per GA4 pull folder. The series tables are upserted rather than snapshot-scoped, so this is the only record that a pull happened and what window it covered.';
comment on column ga4_snapshots.window_end is 'What the pull REQUESTED. The last day actually carrying data can be earlier; read max(day) from ga4_by_date for that.';

-- ---------------------------------------------------------------------------
-- 2. The authoritative daily series.
-- ---------------------------------------------------------------------------
create table if not exists ga4_by_date (
  property         text    not null,
  day              date    not null,
  sessions         integer not null default 0,
  total_users      integer not null default 0,   -- de-duped within THIS DAY; never sum
  new_users        integer not null default 0,
  engaged_sessions integer not null default 0,
  revenue          numeric(14,4) not null default 0,
  transactions     integer not null default 0,
  purchasers       integer not null default 0,   -- de-duped within THIS DAY; never sum
  key_events       integer not null default 0,
  snapshot_date    date,
  updated_at       timestamptz not null default now(),
  primary key (property, day)
);

comment on table  ga4_by_date is 'Sitewide GA4 metrics per day, deduped across pulls. Newest pull wins.';
comment on column ga4_by_date.total_users is 'Users unique to THIS DAY. Summing across days double-counts returning visitors (+6.13% measured over Oct 2026). For a window total, read ga4_by_month or query GA4 for that window.';
comment on column ga4_by_date.purchasers is 'Purchasers unique to THIS DAY. Never sum (+2.00% measured over Oct 2026). transactions IS additive and is the figure a conversion rate should use.';
comment on column ga4_by_date.sessions is 'Summing days runs +0.24% over a month and +2.14% over 1,230 days against what GA4 reports for the same span. Month-aligned windows should read ga4_by_month instead.';
comment on column ga4_by_date.revenue is 'numeric(14,4), not (12,2): 2dp would round each of 1,230 rows before summing and break the exact reconciliation against GA4 that revenue currently has.';

-- ---------------------------------------------------------------------------
-- 3. THE MONTH ANCHOR. Exact where the daily series can only be close.
-- ---------------------------------------------------------------------------
create table if not exists ga4_by_month (
  property         text    not null,
  month            text    not null,             -- 'YYYY-MM', the app's existing monthly format
  sessions         integer not null default 0,
  total_users      integer not null default 0,   -- de-duped within THIS MONTH; exact
  new_users        integer not null default 0,
  engaged_sessions integer not null default 0,
  revenue          numeric(14,4) not null default 0,
  transactions     integer not null default 0,
  purchasers       integer not null default 0,   -- de-duped within THIS MONTH; exact
  key_events       integer not null default 0,
  snapshot_date    date,
  updated_at       timestamptz not null default now(),
  primary key (property, month)
);

comment on table  ga4_by_month is 'GA4 metrics per calendar month, queried AS a month so every figure is exact for that month including the de-duplicated user counts. Summing several month rows re-introduces the same drift as summing days.';
comment on column ga4_by_month.month is 'YYYY-MM, matching reporting_month on the Walmart and Amazon monthly tables. No derived month_start/month_end column: a stored derived date is a second number free to drift, and to_date(month || ''-01'', ''YYYY-MM-DD'') is one expression away.';

-- ---------------------------------------------------------------------------
-- 4. Channel group, at both grains.
-- ---------------------------------------------------------------------------
create table if not exists ga4_by_date_channel (
  property         text    not null,
  day              date    not null,
  channel          text    not null,             -- GA4 sessionDefaultChannelGroup, verbatim
  sessions         integer not null default 0,
  total_users      integer not null default 0,
  new_users        integer not null default 0,
  engaged_sessions integer not null default 0,
  revenue          numeric(14,4) not null default 0,
  transactions     integer not null default 0,
  purchasers       integer not null default 0,
  key_events       integer not null default 0,
  snapshot_date    date,
  updated_at       timestamptz not null default now(),
  primary key (property, day, channel)
);

comment on column ga4_by_date_channel.channel is 'GA4''s own sessionDefaultChannelGroup string, stored verbatim and never remapped. 15 values on record including AI Assistant. A channel we do not recognise must show up AS ITSELF rather than be bucketed (the v11.14 rule).';

-- One channel across time. The PK leads with day, so this is the other axis.
create index if not exists ga4_by_date_channel_ch_idx
  on ga4_by_date_channel (property, channel, day);

create table if not exists ga4_by_month_channel (
  property         text    not null,
  month            text    not null,
  channel          text    not null,
  sessions         integer not null default 0,
  total_users      integer not null default 0,
  new_users        integer not null default 0,
  engaged_sessions integer not null default 0,
  revenue          numeric(14,4) not null default 0,
  transactions     integer not null default 0,
  purchasers       integer not null default 0,
  key_events       integer not null default 0,
  snapshot_date    date,
  updated_at       timestamptz not null default now(),
  primary key (property, month, channel)
);

comment on table ga4_by_month_channel is 'The month anchor, per channel. 509 rows. Exists so a channel-filtered card can be exact for a month-aligned window instead of summing days.';

-- ---------------------------------------------------------------------------
-- 5. Device category.
-- ---------------------------------------------------------------------------
create table if not exists ga4_by_date_device (
  property         text    not null,
  day              date    not null,
  device           text    not null,             -- desktop | mobile | tablet | smart tv
  sessions         integer not null default 0,
  total_users      integer not null default 0,
  new_users        integer not null default 0,
  engaged_sessions integer not null default 0,
  revenue          numeric(14,4) not null default 0,
  transactions     integer not null default 0,
  purchasers       integer not null default 0,
  key_events       integer not null default 0,
  snapshot_date    date,
  updated_at       timestamptz not null default now(),
  primary key (property, day, device)
);

comment on table ga4_by_date_device is 'Device split per day. Reconciles to ga4_by_date within 0.19% over a month, so it is safe to sum. engagement_rate per device is engaged_sessions / sessions, derived.';

-- ---------------------------------------------------------------------------
-- 6. Landing page x channel. THE SEO TABLE - and a ranking, not a total.
-- ---------------------------------------------------------------------------
create table if not exists ga4_by_date_landing_page (
  property         text    not null,
  day              date    not null,
  landing_page     text    not null,             -- may be '(not set)' or ''
  channel          text    not null,
  sessions         integer not null default 0,
  new_users        integer not null default 0,
  engaged_sessions integer not null default 0,
  revenue          numeric(14,4) not null default 0,
  transactions     integer not null default 0,
  snapshot_date    date,
  updated_at       timestamptz not null default now(),
  primary key (property, day, landing_page, channel)
);

comment on table  ga4_by_date_landing_page is 'Which page earned the session, by channel. Sessions here run ~6.8% above sitewide and 17.8% sit in (not set), so this ranks pages and must never supply a Sessions figure shown beside the sitewide card.';
comment on column ga4_by_date_landing_page.landing_page is 'GA4''s landingPage, verbatim. ''(not set)'' is GA4''s own value for a session whose first pageview it could not resolve; '''' is a different state seen only in the property''s first weeks (74 rows, 1,318 sessions). They are NOT merged. Longest on record is 202 chars, well inside the btree key limit.';
comment on column ga4_by_date_landing_page.new_users is 'No total_users or purchasers column here: a de-duplicated count per page per day is a number nobody can roll up. The additive metrics only.';

-- The SEO access pattern: one channel (Organic Search) across the window.
create index if not exists ga4_lp_channel_idx
  on ga4_by_date_landing_page (property, channel, day);
-- One page across time.
create index if not exists ga4_lp_page_idx
  on ga4_by_date_landing_page (property, landing_page, day);

-- ---------------------------------------------------------------------------
-- 7. RLS + grants.
-- ---------------------------------------------------------------------------
-- Hard rule since v6.47: enable RLS + a policy + grants on every new table, and
-- revoke anon. The grant alone is not enough; the Supabase linter checks RLS.
--
-- Supabase's 2026-10-30 change means a new table in `public` no longer gets
-- Data API access automatically and REQUIRES the explicit grant below. This
-- project has always granted to `authenticated` only and revoked anon, because
-- the dashboard is behind a login and anon has no business here.
do $$
declare t text;
begin
  foreach t in array array['ga4_snapshots','ga4_by_date','ga4_by_month',
                           'ga4_by_date_channel','ga4_by_month_channel',
                           'ga4_by_date_device','ga4_by_date_landing_page']
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

-- ga4_snapshots.id is a bigserial, so the sequence needs a grant too or the
-- loader's INSERT fails with "permission denied for sequence".
grant usage, select on all sequences in schema public to authenticated;

-- ---------------------------------------------------------------------------
-- Verify
-- ---------------------------------------------------------------------------
-- select property, count(*) days, min(day), max(day), sum(sessions) sessions
--   from ga4_by_date group by property order by property;
--
-- -- the anchor against the daily series, per month (expect the daily sum high)
-- select m.month, m.sessions anchor, d.sessions sum_of_days,
--        round((d.sessions - m.sessions) * 100.0 / m.sessions, 2) drift_pct
--   from ga4_by_month m
--   join (select property, to_char(day,'YYYY-MM') month, sum(sessions) sessions
--           from ga4_by_date group by 1,2) d
--     on d.property = m.property and d.month = m.month
--  where m.property = 'smarterpaw'
--  order by m.month desc limit 12;
