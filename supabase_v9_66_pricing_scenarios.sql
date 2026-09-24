-- ===========================================================================
-- v9.66 — Shared pricing scenarios
-- ===========================================================================
-- Jason: "saved scenarios should show for all users."
--
-- Pricing scenarios lived only in localStorage, so they were per-browser and
-- per-device: nobody else on the team could see a price plan someone had built,
-- and clearing site data lost it. This makes them a SHARED table - every signed
-- in user sees and can edit the same set, like a team library.
--
-- Note this is deliberately NOT the user_profiles pattern used by the other
-- saved-view systems (forecast_saved_views, inventory_saved_views, etc). Those
-- are per-user preferences. A pricing scenario is a piece of work you want
-- colleagues to open, so it is one shared row per name.
--
-- Run once in Supabase -> SQL Editor. Idempotent.
-- ===========================================================================

create table if not exists pricing_scenarios (
  name              text primary key,
  payload           jsonb       not null,
  images_dropped    boolean     not null default false,
  updated_at        timestamptz not null default now(),
  updated_by        uuid        references auth.users(id) on delete set null,
  updated_by_email  text
);

comment on table  pricing_scenarios is 'Shared New Product Launch pricing scenarios. Visible to every authenticated user.';
comment on column pricing_scenarios.payload is 'Full scenario snapshot: cogs, size, pack, target contribution, fee assumptions, competitors (with variants), notes.';
comment on column pricing_scenarios.images_dropped is 'True when competitor screenshots were stripped before saving to keep the row a sensible size. Prices, sizes and notes are intact.';

-- Keep updated_at honest without relying on the client.
create or replace function pricing_scenarios_touch() returns trigger as $$
begin
  new.updated_at := now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists pricing_scenarios_touch_trg on pricing_scenarios;
create trigger pricing_scenarios_touch_trg
  before update on pricing_scenarios
  for each row execute function pricing_scenarios_touch();

-- RLS: every authenticated user reads and writes the shared set.
-- (Hard rule since v6.47: enable RLS + a policy + grants on every new table,
--  and revoke anon. The grant alone is not enough; the linter checks RLS.)
alter table pricing_scenarios enable row level security;

drop policy if exists pricing_scenarios_auth_all on pricing_scenarios;
create policy pricing_scenarios_auth_all
  on pricing_scenarios for all
  to authenticated
  using (true)
  with check (true);

grant select, insert, update, delete on table pricing_scenarios to authenticated;
revoke all on table pricing_scenarios from anon;

-- Verify
-- select name, images_dropped, updated_by_email, updated_at
--   from pricing_scenarios order by updated_at desc;
