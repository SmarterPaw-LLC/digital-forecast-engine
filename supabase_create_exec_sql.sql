-- ============================================================================
-- SmarterPaw Forecast Dashboard — read-only SQL function for the Query tab
-- ============================================================================
-- Install: open Supabase project -> SQL Editor -> New query -> paste this whole
-- file -> Run. You only need to do this once per project (or after a reset).
--
-- What it does: lets the dashboard's Query Database tab run arbitrary
-- SELECT / WITH queries against your data, returning rows as JSON.
--
-- Safety:
--   1. SECURITY INVOKER (NOT definer) — query runs with the caller's
--      privileges. Anon role only has read access to your tables, so this
--      can't escalate.
--   2. SET LOCAL transaction_read_only = on — Postgres itself rejects any
--      write attempt (INSERT / UPDATE / DELETE / DDL / TRUNCATE), even if
--      smuggled in via WITH ... INSERT or function calls. This is the
--      authoritative guard, not the string check.
--   3. String prefix check on SELECT/WITH is just a fast-fail for obvious
--      misuse and a clearer error message.
-- ============================================================================

create or replace function exec_sql(query text)
returns json
language plpgsql
security invoker
as $$
declare
  result json;
  trimmed text := trim(query);
  upper_head text := upper(left(trimmed, 6));
begin
  if upper_head not in ('SELECT', 'WITH  ', 'WITH(', 'WITH ') and left(upper(trimmed), 5) <> 'WITH ' then
    raise exception 'Only SELECT and WITH queries are permitted (got: %)', left(trimmed, 20);
  end if;

  -- Hard guard: any write attempt inside the query will error out.
  set local transaction_read_only = on;

  execute 'select coalesce(json_agg(t), ''[]''::json) from (' || query || ') t' into result;
  return result;
end;
$$;

-- Allow the anon role (used by the dashboard with the public anon key) to call it.
grant execute on function exec_sql(text) to anon;

-- Optional: also allow authenticated role if you ever add Supabase auth.
grant execute on function exec_sql(text) to authenticated;
