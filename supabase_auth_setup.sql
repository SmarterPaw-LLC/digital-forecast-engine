-- ============================================================================
-- SmarterPaw Forecast Dashboard — Auth + Audit Log Setup
-- Run this ONCE in Supabase → SQL Editor → New query → paste → Run
-- ============================================================================
-- Adds:
--   1. user_profiles  — links auth.users to app-side info (email, full name, role)
--   2. audit_log      — who-did-what trail
--   3. RLS policies   — every existing data table is now authenticated-only;
--                       anon role can no longer read or write.
--   4. Trigger        — auto-creates a user_profiles row whenever a new auth user signs up
--   5. Helper RPCs    — invite_user, log_action
-- ============================================================================

-- ──────────────────────────────────────────────────────────────────────────
-- 1. user_profiles
-- ──────────────────────────────────────────────────────────────────────────
create table if not exists user_profiles (
  user_id      uuid primary key references auth.users on delete cascade,
  email        text not null,
  full_name    text,
  role         text not null default 'admin' check (role in ('admin','editor','viewer')),
  created_at   timestamptz default now(),
  last_seen_at timestamptz
);

create index if not exists user_profiles_email_idx on user_profiles(email);

-- ──────────────────────────────────────────────────────────────────────────
-- 2. audit_log
-- ──────────────────────────────────────────────────────────────────────────
create table if not exists audit_log (
  id         bigserial primary key,
  ts         timestamptz default now(),
  user_id    uuid references auth.users on delete set null,
  user_email text,
  action     text not null,        -- e.g. 'upload_sku_economics', 'product.create', 'product.delete'
  details    jsonb default '{}'::jsonb
);

create index if not exists audit_log_ts_idx     on audit_log(ts desc);
create index if not exists audit_log_action_idx on audit_log(action);
create index if not exists audit_log_user_idx   on audit_log(user_id);

-- ──────────────────────────────────────────────────────────────────────────
-- 3. Auto-create user_profiles row on signup
-- ──────────────────────────────────────────────────────────────────────────
create or replace function handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into user_profiles (user_id, email, full_name, role)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', new.email),
    'admin'  -- every invited user is admin (per current SmarterPaw policy)
  )
  on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();

-- ──────────────────────────────────────────────────────────────────────────
-- 4. log_action — convenience RPC used by the dashboard to write audit entries
-- ──────────────────────────────────────────────────────────────────────────
create or replace function log_action(p_action text, p_details jsonb default '{}'::jsonb)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_email text;
begin
  if auth.uid() is null then return; end if;  -- ignore unauthenticated calls
  select email into v_email from auth.users where id = auth.uid();
  insert into audit_log (user_id, user_email, action, details)
  values (auth.uid(), v_email, p_action, coalesce(p_details, '{}'::jsonb));
end;
$$;

grant execute on function log_action(text, jsonb) to authenticated;

-- ──────────────────────────────────────────────────────────────────────────
-- 5. Row-Level Security on every data table
--    Strategy: enable RLS, allow authenticated role full access, deny anon entirely.
--    (Everyone with an account is an admin per Jason's policy. If we later add
--    editor/viewer distinctions, narrow the per-table policies then.)
-- ──────────────────────────────────────────────────────────────────────────
do $$
declare
  t text;
  tables text[] := array[
    'products', 'sales_weekly', 'sku_economics', 'inventory',
    'bom', 'chewy_forecasts', 'categories', 'channel_listings'
  ];
begin
  foreach t in array tables loop
    -- Only act on tables that actually exist in this DB.
    if exists (select 1 from information_schema.tables where table_schema='public' and table_name=t) then
      execute format('alter table public.%I enable row level security;', t);
      execute format('drop policy if exists "authenticated full access" on public.%I;', t);
      execute format(
        'create policy "authenticated full access" on public.%I
           for all to authenticated using (true) with check (true);', t
      );
    end if;
  end loop;
end$$;

-- user_profiles: every authenticated user can read all profiles; users can update only their own row.
alter table user_profiles enable row level security;
drop policy if exists "profiles select all"        on user_profiles;
drop policy if exists "profiles update own"        on user_profiles;
drop policy if exists "profiles insert via trigger" on user_profiles;
create policy "profiles select all"  on user_profiles for select to authenticated using (true);
create policy "profiles update own"  on user_profiles for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
-- INSERT happens via the on_auth_user_created trigger (security definer); no policy needed for clients.

-- audit_log: authenticated users can read everything. Writes go through log_action RPC only.
alter table audit_log enable row level security;
drop policy if exists "audit select all" on audit_log;
create policy "audit select all" on audit_log for select to authenticated using (true);

-- ──────────────────────────────────────────────────────────────────────────
-- 6. Backfill profiles for any users that already exist (e.g. you signed up
--    via the Supabase dashboard before running this script).
-- ──────────────────────────────────────────────────────────────────────────
insert into user_profiles (user_id, email, full_name, role)
select id, email, coalesce(raw_user_meta_data->>'full_name', raw_user_meta_data->>'name', email), 'admin'
from auth.users
on conflict (user_id) do nothing;

-- ──────────────────────────────────────────────────────────────────────────
-- Done. Verify:
--   select count(*) from user_profiles;        -- should match auth.users count
--   select * from audit_log order by ts desc;  -- empty until first action
-- ============================================================================
