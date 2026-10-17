-- ===========================================================================
-- v10.71 — Shared saved queries
-- ===========================================================================
-- Jason: "if i save a query does it save it globally for all users?" -> no,
-- it did not. Then: "yes let me save it globally."
--
-- Saved queries lived in user_profiles.db_user_queries (jsonb, one blob per
-- user), so a query one person wrote was invisible to everyone else. This
-- makes them a SHARED table - every signed-in user sees and can edit the same
-- set, like a team library.
--
-- Same shape as pricing_scenarios (v9.66), which is the only other genuinely
-- shared library in the app. Deliberately NOT the user_profiles pattern the
-- saved-VIEW systems use (forecast_saved_views, inventory_saved_views, ...) -
-- those are personal preferences. A saved query is a piece of work you want
-- colleagues to run, so it is one shared row per name.
--
-- The old user_profiles.db_user_queries column is LEFT IN PLACE. The app reads
-- it once on first load after this migration and publishes anything it finds
-- into this table, so nobody's existing queries are stranded. Dropping it is a
-- separate decision once every user has loaded the app at least once.
--
-- Run once in Supabase -> SQL Editor. Idempotent.
-- ===========================================================================

create table if not exists shared_saved_queries (
  name              text primary key,
  sql               text        not null,
  updated_at        timestamptz not null default now(),
  updated_by        uuid        references auth.users(id) on delete set null,
  updated_by_email  text
);

comment on table  shared_saved_queries is 'Shared Query Database library. Visible to and editable by every authenticated user.';
comment on column shared_saved_queries.sql is 'The SELECT / WITH statement, exactly as typed in the editor.';
comment on column shared_saved_queries.updated_by_email is 'Who last saved it - surfaced in the UI so a shared edit is attributable.';

-- Keep updated_at honest without relying on the client.
create or replace function shared_saved_queries_touch() returns trigger as $$
begin
  new.updated_at := now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists shared_saved_queries_touch_trg on shared_saved_queries;
create trigger shared_saved_queries_touch_trg
  before update on shared_saved_queries
  for each row execute function shared_saved_queries_touch();

-- RLS: every authenticated user reads and writes the shared set.
-- (Hard rule since v6.47: enable RLS + a policy + grants on every new table,
--  and revoke anon. The grant alone is not enough; the linter checks RLS.)
alter table shared_saved_queries enable row level security;

drop policy if exists shared_saved_queries_auth_all on shared_saved_queries;
create policy shared_saved_queries_auth_all
  on shared_saved_queries for all
  to authenticated
  using (true)
  with check (true);

grant select, insert, update, delete on table shared_saved_queries to authenticated;
revoke all on table shared_saved_queries from anon;

-- Verify
-- select name, updated_by_email, updated_at,
--        left(replace(sql, E'\n', ' '), 60) as preview
--   from shared_saved_queries order by updated_at desc;
