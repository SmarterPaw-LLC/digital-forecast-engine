-- ============================================================================
-- Per-user tab access + admin role management  (v9.82)
-- Run ONCE in Supabase -> SQL Editor.
-- ============================================================================
-- WHAT THIS IS, AND WHAT IT IS NOT
-- --------------------------------
-- This adds a per-user list of which top-level tabs the dashboard SHOWS, plus
-- the ability for an admin to change another user's role.
--
-- !! IMPORTANT !! Hiding a tab is a UI-scoping feature, NOT data security.
-- Every data table in this app currently carries:
--     for all to authenticated using (true) with check (true)
-- so ANY signed-in user can still read and write ANY table by calling the API
-- directly (or from the browser console). Hiding the P&L tab removes it from
-- the nav; it does not stop a determined user from reading P&L rows.
--
-- If you need a user who genuinely CANNOT see a dataset, that is a different
-- (larger) job: per-table RLS policies keyed on user_profiles.role, replacing
-- the blanket `using (true)` policies. Say the word and that can be built --
-- but do not rely on tab visibility for it in the meantime.
-- ============================================================================

-- ── 1. visible_tabs -----------------------------------------------------
-- NULL  = this user sees every tab (the default; nobody gets locked out by
--         the migration). A JSON array = the explicit allow-list.
alter table user_profiles add column if not exists visible_tabs jsonb;

comment on column user_profiles.visible_tabs is
  'NULL = all tabs. Otherwise a JSON array of tab ids, e.g. ["products","pnl"]. UI scoping only - NOT a security boundary; see supabase_v9_82_tab_access.sql.';

-- ── 2. admin check helper ------------------------------------------------
-- SECURITY DEFINER so it can read user_profiles WITHOUT re-entering that
-- table's own RLS policies. A plain subquery inside a user_profiles policy
-- would recurse (policy -> select -> policy -> ...) and error out.
create or replace function is_app_admin()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists (
    select 1 from user_profiles
    where user_id = auth.uid() and role = 'admin'
  );
$$;

revoke all on function is_app_admin() from public, anon;
grant execute on function is_app_admin() to authenticated;

-- ── 3. let admins update ANY profile ------------------------------------
-- The original setup only had "profiles update own", so an admin could not
-- change someone else's role or tab list. Both policies coexist: a normal
-- user still updates their own row, an admin updates anyone's.
drop policy if exists "profiles update admin" on user_profiles;
create policy "profiles update admin" on user_profiles
  for update to authenticated
  using (is_app_admin())
  with check (is_app_admin());

-- ── 4. never let the last admin be demoted ------------------------------
-- Enforced in the database, not just the UI: an admin who demotes themselves
-- while they are the only admin would lock EVERYONE out of user management
-- permanently, with no way back in short of editing rows by hand in Supabase.
create or replace function prevent_last_admin_demotion()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  remaining int;
begin
  if (TG_OP = 'UPDATE' and OLD.role = 'admin' and NEW.role <> 'admin')
     or (TG_OP = 'DELETE' and OLD.role = 'admin') then
    select count(*) into remaining
      from user_profiles
      where role = 'admin' and user_id <> OLD.user_id;
    if remaining = 0 then
      raise exception
        'Cannot remove the last admin. Promote another user to admin first.'
        using errcode = 'check_violation';
    end if;
  end if;
  return case when TG_OP = 'DELETE' then OLD else NEW end;
end;
$$;

drop trigger if exists trg_prevent_last_admin_demotion on user_profiles;
create trigger trg_prevent_last_admin_demotion
  before update or delete on user_profiles
  for each row execute function prevent_last_admin_demotion();

-- ── 5. verify ------------------------------------------------------------
select email,
       role,
       coalesce(visible_tabs::text, 'ALL TABS') as tabs,
       last_seen_at
from user_profiles
order by role, email;
