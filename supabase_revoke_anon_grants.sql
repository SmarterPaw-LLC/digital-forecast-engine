-- ============================================================================
-- Defense-in-depth: revoke anon role DML on every table in public schema.
-- Run ONCE in Supabase → SQL Editor. Safe + idempotent.
-- ============================================================================
-- Why this exists:
--   The SmarterPaw dashboard requires login (v4.60+); no feature relies on
--   anonymous access. RLS policies on every table already gate access to
--   authenticated users — but 8 older tables (pre-v4.60: bom, categories,
--   channel_listings, chewy_forecasts, inventory, products, sales_weekly,
--   sku_economics) still hold the original "everyone gets everything" anon
--   grants from before the auth migration locked things down.
--
--   Today the RLS policies block anon at the row level, so the grants are
--   dead weight. But defense in depth: if a policy is ever misconfigured
--   (e.g., USING (true) by accident), the grant means anon would immediately
--   get full read/write. Removing the grant takes anon out of the picture
--   entirely so policy misconfigurations on the authenticated-only tables
--   can't leak data to the public anon key.
--
-- What this does NOT touch:
--   • authenticated grants — every table keeps its full DML to authenticated
--   • RLS policies — unchanged
--   • REFERENCES / TRIGGER / TRUNCATE on anon — these aren't data access
--     and don't matter (TRUNCATE requires table ownership in practice)
--   • Anything in storage, auth, or graphql_public schemas
--
-- Reversible: if you ever decide to expose a specific table to anon, add
-- a per-table `grant ... on table foo to anon;` after running this.
-- ============================================================================

-- 1. Revoke DML on all CURRENT tables in public from anon.
revoke select, insert, update, delete on all tables in schema public from anon;

-- 2. Lock down FUTURE tables too. ALTER DEFAULT PRIVILEGES applies to
--    anything created from now on by the role that runs this migration
--    (typically postgres / supabase admin). Pairs with the existing
--    "grant ... to authenticated" default-privilege rule from
--    supabase_auth_setup.sql so the policy is bidirectional: new tables
--    get authenticated access automatically AND anon access denied
--    automatically.
alter default privileges in schema public
  revoke select, insert, update, delete on tables from anon;

-- 3. Same for sequences — anon shouldn't be able to advance ID sequences
--    on tables it can't insert into anyway.
revoke usage, select, update on all sequences in schema public from anon;
alter default privileges in schema public
  revoke usage, select, update on sequences from anon;

-- 4. Verify. Run after the revokes — should show only metadata-grade grants
--    (REFERENCES / TRIGGER / TRUNCATE) for anon on every table.
--
--   select t.table_name,
--          string_agg(distinct p.privilege_type, ', ' order by p.privilege_type)
--            filter (where p.grantee = 'anon') as anon_grants
--   from information_schema.tables t
--   left join information_schema.role_table_grants p
--     on p.table_schema = t.table_schema and p.table_name = t.table_name
--   where t.table_schema = 'public' and t.table_type = 'BASE TABLE'
--   group by t.table_name order by t.table_name;

-- 5. Side-effect to expect: the dashboard's login screen still works
--    (Supabase Auth doesn't go through PostgREST). Sign-up / sign-in /
--    sign-out / password reset are all auth.* RPC calls, unaffected by
--    public-schema grants. Once a user is authenticated, their JWT carries
--    the `authenticated` role context and every existing data fetch
--    continues working as before.
