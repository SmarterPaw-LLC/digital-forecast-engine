-- v8.04 — Amazon P&L Action Items / Change Log.
-- A persistent tracker for decisions on ad-spend adjustments, PDP fixes,
-- creative launches, pauses, etc. Each row is a proposal → sent to agency →
-- eventually in-effect → completed. Baseline snapshot captures the metrics at
-- flag time so we can measure actual impact after the change takes hold.
--
-- Flagged from the Page Performance sub-view (quadrant tables + the new Top
-- Action Items panel) OR ad hoc from the Change Log sub-view.

create table if not exists pnl_action_items (
  id                bigserial primary key,
  master_id         text references products(master_id) on delete cascade,
  asin              text,
  region            text default 'US',
  action_type       text not null check (action_type in (
                       'increase_ad_spend',
                       'decrease_ad_spend',
                       'pause_ads',
                       'launch_creative',
                       'fix_pdp',
                       'other'
                     )),
  delta_pct         numeric,          -- signed % change (+50 = +50% ad spend, -30 = -30%)
  target_ad_spend   numeric,          -- optional absolute target ($) — filled from baseline × (1 + delta/100)
  rationale         text,
  status            text not null default 'draft' check (status in (
                       'draft',
                       'sent_to_agency',
                       'in_effect',
                       'completed',
                       'cancelled'
                     )),
  baseline_snapshot jsonb,            -- {sessions, page_views, conv_pct, ad_spend, net_sales, contrib_profit, contrib_pct, period_days, snapshot_at, region, period_from, period_to}
  effective_date    date,             -- when the change is expected to take effect
  review_date       date,             -- when to check back on impact
  notes             text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create index if not exists pnl_action_items_master_idx on pnl_action_items(master_id);
create index if not exists pnl_action_items_status_idx on pnl_action_items(status);
create index if not exists pnl_action_items_created_idx on pnl_action_items(created_at desc);

-- Keep updated_at fresh on every UPDATE via a trigger (matches the v6.62
-- pattern used by user_profiles / product_cogs / etc.).
create or replace function pnl_action_items_touch_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists pnl_action_items_touch on pnl_action_items;
create trigger pnl_action_items_touch
  before update on pnl_action_items
  for each row execute function pnl_action_items_touch_updated_at();

-- RLS + grants (v6.47 hard rule).
alter table pnl_action_items enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'pnl_action_items'
      and policyname = 'pnl_action_items_authenticated'
  ) then
    create policy "pnl_action_items_authenticated"
      on pnl_action_items
      for all
      to authenticated
      using (true)
      with check (true);
  end if;
end $$;

grant select, insert, update, delete on table pnl_action_items to authenticated;
grant usage, select on sequence pnl_action_items_id_seq to authenticated;
revoke all on table pnl_action_items from anon;

comment on table pnl_action_items is
  'Amazon P&L action items / change log (v8.04). Persistent tracker of ad-spend + creative + PDP decisions flagged from the Page Performance sub-view. baseline_snapshot freezes the metrics at flag time so post-change impact can be measured. Status flow: draft → sent_to_agency → in_effect → completed (or cancelled). Emitted as agency handoff CSV.';
comment on column pnl_action_items.baseline_snapshot is
  'JSON snapshot of the metrics that motivated the change: sessions, page_views, conv_pct, ad_spend, net_sales, contrib_profit, contrib_pct, period_days, snapshot_at, region, period_from, period_to. Enables actual-vs-baseline comparison once the change is in effect.';
comment on column pnl_action_items.delta_pct is
  'Signed % change from the baseline for this action_type. +50 = +50% ad spend, -30 = -30%. Null when action_type is qualitative (pause_ads, launch_creative, fix_pdp, other) — use notes instead.';
