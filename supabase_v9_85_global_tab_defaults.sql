-- ============================================================================
-- Global (org-wide) default tab access  (v9.85)
-- Run ONCE in Supabase -> SQL Editor. Requires supabase_v9_82_tab_access.sql
-- to have been run first (it creates is_app_admin()).
-- ============================================================================
-- Adds an org-wide DEFAULT tab set, so you don't have to configure every user
-- one at a time. Resolution order for what a user sees:
--
--   1. user_profiles.visible_tabs  -- a non-empty array = explicit per-user
--                                     override, wins over everything
--   2. app_settings.default_visible_tabs  -- the org-wide default
--   3. every tab                   -- when neither is set (today's behaviour)
--
-- NULL on a user now means "inherit the global default" rather than "all tabs".
-- Nothing changes until you actually set a global default, because an unset
-- global falls through to every tab.
--
-- !! Same caveat as v9.82 !! This is UI scoping, NOT data security. Every data
-- table is still `for all to authenticated using (true)`, so any signed-in user
-- can read any table directly through the API. Hiding tabs tidies the nav; it
-- does not restrict data.
-- ============================================================================

-- ── 1. settings table ----------------------------------------------------
create table if not exists app_settings (
  key         text primary key,
  value       jsonb,
  updated_at  timestamptz not null default now(),
  updated_by  uuid references auth.users
);

comment on table app_settings is
  'Org-wide key/value settings. key=default_visible_tabs -> jsonb array of tab ids (NULL/absent = every tab). UI scoping only - NOT a security boundary.';

-- ── 2. RLS: everyone signed in READS, only admins WRITE ------------------
-- Every user has to read the default to build their own nav, so SELECT is open
-- to authenticated. Writes are admin-only. Postgres OR's permissive policies,
-- so the broad select policy + the admin-only "for all" policy together mean:
-- read = any authenticated user, write = admins.
alter table app_settings enable row level security;

drop policy if exists "app_settings read"        on app_settings;
drop policy if exists "app_settings write admin" on app_settings;

create policy "app_settings read" on app_settings
  for select to authenticated using (true);

create policy "app_settings write admin" on app_settings
  for all to authenticated
  using (is_app_admin())
  with check (is_app_admin());

grant select, insert, update, delete on table app_settings to authenticated;
revoke all on table app_settings from anon;

-- ── 3. keep updated_at honest -------------------------------------------
create or replace function app_settings_touch()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end;
$$;

drop trigger if exists trg_app_settings_touch on app_settings;
create trigger trg_app_settings_touch
  before insert or update on app_settings
  for each row execute function app_settings_touch();

-- ── 4. restate what NULL means on the per-user column --------------------
comment on column user_profiles.visible_tabs is
  'NULL = inherit app_settings.default_visible_tabs (which itself falls back to every tab). A non-empty JSON array = explicit per-user override, e.g. ["products","pnl"]. UI scoping only - NOT a security boundary; see supabase_v9_82_tab_access.sql.';

-- ── 5. verify ------------------------------------------------------------
select coalesce((select value::text from app_settings where key = 'default_visible_tabs'),
                'NOT SET (= every tab)') as global_default_tabs;

select email,
       role,
       case when visible_tabs is null then 'inherits global default'
            else visible_tabs::text end as tabs
from user_profiles
order by role, email;
