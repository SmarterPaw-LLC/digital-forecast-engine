-- v12.27 — Ads campaign notes / timeline events.
--
-- Jason: "i need a 'notes' section that i can set per campaign level, with an
-- event that appears on the timeline. for instance, i just changed the kitty
-- ka zoom manual campaign to dynamic bidding today, and i want to record that
-- change"
--
-- WHY THIS IS NOT pnl_action_items (v8.04). That table is PRODUCT-scoped
-- (master_id → products, ASIN, region), its action_type enum is about ad
-- spend and PDPs on Amazon, and it carries a draft → sent_to_agency →
-- in_effect workflow. A campaign-level "switched to dynamic bidding on
-- 2026-11-12" is a different object: no product, no workflow, and the thing
-- that matters is the DATE it lands on the chart. Bending one into the other
-- would give one table two meanings (rule 3a).
--
-- A note with no campaign is an ACCOUNT-level event and draws on every
-- campaign's timeline. A note with a campaign draws only on that one.

create table if not exists ads_campaign_notes (
  id          bigserial primary key,
  channel     text not null,              -- 'walmart' | 'amazon' | 'chewy'
  account     text,                       -- null = applies to every account
  campaign    text,                       -- null = account-level event
  note_date   date not null,              -- the day it happened: this is what the chart plots
  kind        text not null default 'change' check (kind in (
                 'change',        -- a setting changed (bidding, budget, targeting)
                 'creative',      -- new or retired creative
                 'budget',        -- budget moved
                 'test',          -- a test started or ended
                 'external',      -- something outside our control (promo, stockout, price)
                 'observation'    -- a note, no action
               )),
  note        text not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists ads_campaign_notes_scope_idx
  on ads_campaign_notes(channel, note_date desc);
create index if not exists ads_campaign_notes_campaign_idx
  on ads_campaign_notes(channel, campaign);

-- Keep updated_at fresh (the v6.62 / v8.04 pattern).
create or replace function ads_campaign_notes_touch_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists ads_campaign_notes_touch on ads_campaign_notes;
create trigger ads_campaign_notes_touch
  before update on ads_campaign_notes
  for each row execute function ads_campaign_notes_touch_updated_at();

-- /!\ RLS + A POLICY + GRANTS. Hard rule since v6.47, and v12.03 shipped a
-- table without the POLICY — Supabase enables RLS on a new table by itself,
-- `authenticated` already holds the privileges from default grants, so the
-- grants are the no-op half and the policy is the half that matters. Without
-- it the first upload fails with:
--
--     new row violates row-level security policy for table "ads_campaign_notes"
alter table ads_campaign_notes enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
     where schemaname = 'public'
       and tablename  = 'ads_campaign_notes'
       and policyname = 'ads_campaign_notes_all'
  ) then
    create policy ads_campaign_notes_all on ads_campaign_notes
      for all to authenticated using (true) with check (true);
  end if;
end $$;

grant select, insert, update, delete on ads_campaign_notes to authenticated;
grant usage, select on sequence ads_campaign_notes_id_seq to authenticated;
