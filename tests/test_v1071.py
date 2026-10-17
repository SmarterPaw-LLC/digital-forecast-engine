# -*- coding: utf-8 -*-
"""v10.71 - saved queries become a SHARED team library.

Jason: "if i save a query does it save it globally for all users?" -> no.
Then: "yes let me save it globally."

Ported from the pricing_scenarios pattern (v9.66) INCLUDING the v9.67 fix that
exists because v9.66 destroyed real work: the first shared loader REPLACED the
local map with whatever the table held, and on the first load after the
migration that table is EMPTY — so it wrote {} over every scenario anyone had
saved in their browser.

So the single most important assertion in this file is:

    an empty shared table must not delete anything.

Everything else is secondary. The snapshot (_sharedQueryDbSnapshot) is what
makes "deleted by someone else" distinguishable from "never seen"; it is null
on the first load of a session, which is precisely why a first load cannot
delete.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond: passed += 1; print('  ok  ' + name)
    else:    failed += 1; print('  FAIL  ' + name)

def fn(name, kw='function'):
    i = js.index('%s %s(' % (kw, name))
    j = js.index('{', i); d = 0; k = j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k+1]
        k += 1

# ---------------------------------------------------------------- A. static
print('\n== A. it is a SHARED table, not the per-user column ==')

loader = fn('loadUserQueriesFromDb', 'async function')
sync   = fn('sharedQueriesSyncToDb', 'async function')
persist= fn('persistUserQueries', 'async function')

ok("from('shared_saved_queries')" in loader, 'loader reads the shared table')
ok("from('shared_saved_queries')" in sync, 'sync writes the shared table')
ok(".eq('user_id', user.id)" not in sync,
   'the sync is NOT scoped to one user (that was the whole bug)')
ok("update({ db_user_queries" not in persist and "update({ db_user_queries" not in sync,
   'nothing writes the old per-user column any more')
ok("select('db_user_queries')" in loader,
   'the legacy per-user column is still READ once, for migration')
ok(js.count('function sharedQueriesSyncToDb') == 1, 'one sync function')
ok(js.count('function _sharedQueryCompareKey') == 1, 'one compare-key helper')
ok(len(re.findall(r'(?:let|const|var)\s+_sharedQueryDbSnapshot', js)) == 1,
   'one snapshot declaration')

print('\n== B. the v9.67 lesson is encoded, not just remembered ==')
ok('MERGE, never replace' in loader, 'the loader says so in as many words')
ok('priorSnap' in loader, 'it consults the prior snapshot')
ok('_sharedQueryDbSnapshot = null' in js,
   'the snapshot starts NULL (so a first load cannot delete)')
ok('onConflict:' in sync and "'name'" in sync, 'per-NAME upsert, not a blob replace')
ok(sync.index('_sharedQueryDbSnapshot = seen') > sync.index("delete().in('name', gone)"),
   'the snapshot advances only AFTER the writes land')
ck = fn('_sharedQueryCompareKey')
ok('updatedByEmail' not in ck and 'savedAt' not in ck,
   'provenance fields are excluded from the diff (else everything reads changed)')

print('\n== C. the migration is named, and the table is guarded ==')
ok('supabase_v10_71_shared_saved_queries.sql' in js,
   'a missing table names the migration file')
ok(os.path.exists(os.path.join(os.path.dirname(SRC),
   'supabase_v10_71_shared_saved_queries.sql')), 'the migration file exists')
sql = io.open(os.path.join(os.path.dirname(SRC),
      'supabase_v10_71_shared_saved_queries.sql'), encoding='utf-8').read()
ok('enable row level security' in sql, 'RLS enabled (v6.47 hard rule)')
ok('create policy' in sql and 'to authenticated' in sql, 'authenticated policy')
ok('revoke all on table shared_saved_queries from anon' in sql, 'anon revoked')
ok('grant select, insert, update, delete' in sql, 'authenticated granted')
ok('name              text primary key' in sql, 'name is the PK (one row per name)')

print('\n== D. the UI says it is shared ==')
ok('this library is shared' in js, 'the chip tooltip warns edits are team-wide')
ok('q.updatedByEmail' in js, 'the chip names who last saved it')
ok('SHARED - every signed-in user' in s, 'the label tooltip says it is shared')
ok('shared</span>' in s, 'a visible shared marker on the label')

# --------------------------------------------------------------- E. behaviour
print('\n== E. BEHAVIOUR (real sliced functions driven in node) ==')

HARNESS = r"""
// ---- stubs
let _store = {};
const localStorage = {
  getItem: k => (k in _store ? _store[k] : null),
  setItem: (k, v) => { _store[k] = String(v); },
};
let dbUserQueries = [];
let activeSavedQueryIdx = -1;
let _activeSavedQueryName = null;
let _rendered = 0;
function renderSavedQueries() { _rendered++; }
function logAudit() {}

let DB = {};            // name -> { sql, updated_at, updated_by_email }
let LEGACY = [];        // user_profiles.db_user_queries
let SIGNED_IN = true;
let TABLE_MISSING = false;
let WRITE_FAILS = false;
const CALLS = { upsert: [], delete: [] };

function getSB() {
  return Promise.resolve({
    auth: { getUser: () => Promise.resolve({
      data: { user: SIGNED_IN ? { id: 'u1', email: 'jason@example.com' } : null } }) },
    from(tbl) {
      return {
        select(cols) {
          if (tbl === 'shared_saved_queries') {
            if (TABLE_MISSING) return Promise.resolve({ data: null, error: { message: 'relation "shared_saved_queries" does not exist' } });
            return Promise.resolve({ data: Object.entries(DB).map(([name, v]) => ({
              name, sql: v.sql, updated_at: v.updated_at, updated_by_email: v.updated_by_email })), error: null });
          }
          // user_profiles legacy read
          return { eq: () => ({ maybeSingle: () => Promise.resolve({ data: { db_user_queries: LEGACY }, error: null }) }) };
        },
        upsert(rows) {
          CALLS.upsert.push(rows.map(r => r.name).sort());
          if (TABLE_MISSING) return Promise.resolve({ error: { message: 'schema cache' } });
          if (WRITE_FAILS)   return Promise.resolve({ error: { message: 'boom' } });
          for (const r of rows) DB[r.name] = { sql: r.sql, updated_at: '2026-10-17T00:00:00Z', updated_by_email: r.updated_by_email };
          return Promise.resolve({ error: null });
        },
        delete() { return { in: (_c, names) => {
          CALLS.delete.push([...names].sort());
          if (WRITE_FAILS) return Promise.resolve({ error: { message: 'boom' } });
          for (const nm of names) delete DB[nm];
          return Promise.resolve({ error: null });
        } }; },
      };
    },
  });
}

__COMPAREKEY__
__SYNC__
__LOADER__
__PERSIST__

const names = () => dbUserQueries.map(q => q.name).sort();
const out = {};
function reset(local, db, legacy) {
  dbUserQueries = JSON.parse(JSON.stringify(local || []));
  DB = JSON.parse(JSON.stringify(db || {}));
  LEGACY = JSON.parse(JSON.stringify(legacy || []));
  _sharedQueryDbSnapshot = null; _sharedQueriesLoaded = false;
  SIGNED_IN = true; TABLE_MISSING = false; WRITE_FAILS = false;
  CALLS.upsert = []; CALLS.delete = []; _store = {};
  activeSavedQueryIdx = -1; _activeSavedQueryName = null;
}
const Q = (n, sql) => ({ name: n, sql: sql || ('select ' + n), savedAt: '2026-01-01T00:00:00Z' });

(async () => {
  // 1. THE v9.66 DATA-LOSS SCENARIO: empty shared table, local work present.
  reset([Q('alpha'), Q('beta')], {}, []);
  await loadUserQueriesFromDb();
  out.emptyTable = { kept: names(), publishedToDb: Object.keys(DB).sort() };

  // 2. shared copy wins on a name collision
  reset([Q('alpha', 'LOCAL')], { alpha: { sql: 'REMOTE', updated_at: 'x', updated_by_email: 'pat@x' } }, []);
  await loadUserQueriesFromDb();
  out.collision = { sql: dbUserQueries.find(q => q.name === 'alpha').sql,
                    by: dbUserQueries.find(q => q.name === 'alpha').updatedByEmail };

  // 3. genuine remote delete IS honoured on a SECOND load
  reset([], { alpha: { sql: 'a', updated_at: 'x', updated_by_email: null },
              beta:  { sql: 'b', updated_at: 'x', updated_by_email: null } }, []);
  await loadUserQueriesFromDb();           // snapshot now knows alpha+beta
  const afterFirst = names();
  delete DB.beta;                           // someone else deleted it
  await loadUserQueriesFromDb();
  out.remoteDelete = { afterFirst, afterSecond: names() };

  // 4. a name NEVER seen is kept, even on a later load
  reset([], { alpha: { sql: 'a', updated_at: 'x', updated_by_email: null } }, []);
  await loadUserQueriesFromDb();
  dbUserQueries.push(Q('brandnew'));        // saved locally after the load
  delete DB.alpha;                          // and alpha removed remotely
  await loadUserQueriesFromDb();
  out.neverSeen = { kept: names(), inDb: Object.keys(DB).sort() };

  // 5. legacy per-user column migrates in
  reset([], {}, [Q('legacy1'), Q('legacy2')]);
  await loadUserQueriesFromDb();
  out.legacy = { kept: names(), publishedToDb: Object.keys(DB).sort() };

  // 6. sync pushes only what CHANGED
  reset([], { alpha: { sql: 'a', updated_at: 'x', updated_by_email: null },
              beta:  { sql: 'b', updated_at: 'x', updated_by_email: null } }, []);
  await loadUserQueriesFromDb();
  CALLS.upsert = [];
  dbUserQueries.find(q => q.name === 'beta').sql = 'b-EDITED';
  await persistUserQueries();
  out.diffOnly = { upserts: CALLS.upsert };

  // 7. deleting locally deletes remotely
  reset([], { alpha: { sql: 'a', updated_at: 'x', updated_by_email: null },
              beta:  { sql: 'b', updated_at: 'x', updated_by_email: null } }, []);
  await loadUserQueriesFromDb();
  CALLS.delete = [];
  dbUserQueries = dbUserQueries.filter(q => q.name !== 'beta');
  await persistUserQueries();
  out.localDelete = { deletes: CALLS.delete, dbNames: Object.keys(DB).sort() };

  // 8. a FAILED write must not advance the snapshot
  reset([], { alpha: { sql: 'a', updated_at: 'x', updated_by_email: null } }, []);
  await loadUserQueriesFromDb();
  const snapBefore = JSON.stringify(_sharedQueryDbSnapshot);
  WRITE_FAILS = true;
  dbUserQueries.push(Q('gamma'));
  await persistUserQueries();
  out.failedWrite = { snapshotUnchanged: JSON.stringify(_sharedQueryDbSnapshot) === snapBefore };

  // 9. signed out -> local only, zero writes
  reset([Q('alpha')], {}, []);
  SIGNED_IN = false;
  await loadUserQueriesFromDb();
  await persistUserQueries();
  out.signedOut = { kept: names(), upserts: CALLS.upsert.length, dbEmpty: Object.keys(DB).length === 0 };

  // 10. missing table -> local survives untouched
  reset([Q('alpha'), Q('beta')], {}, []);
  TABLE_MISSING = true;
  await loadUserQueriesFromDb();
  out.missingTable = { kept: names() };

  // 11. active query survives a reorder (tracked by name)
  reset([], { zzz: { sql: 'z', updated_at: 'x', updated_by_email: null },
              aaa: { sql: 'a', updated_at: 'x', updated_by_email: null } }, []);
  await loadUserQueriesFromDb();
  const zIdx = dbUserQueries.findIndex(q => q.name === 'zzz');
  activeSavedQueryIdx = zIdx; _activeSavedQueryName = 'zzz';
  DB.mmm = { sql: 'm', updated_at: 'x', updated_by_email: null };   // shifts order
  await loadUserQueriesFromDb();
  out.activeTracking = {
    stillPointsAtZzz: activeSavedQueryIdx >= 0 &&
      dbUserQueries[activeSavedQueryIdx] && dbUserQueries[activeSavedQueryIdx].name === 'zzz',
    order: names(),
  };

  console.log(JSON.stringify(out));
})();
"""
HARNESS = (HARNESS
  .replace('__COMPAREKEY__', ck)
  .replace('__SYNC__', 'let _sharedQueryDbSnapshot = null;\nlet _sharedQueriesLoaded = false;\n' + sync)
  .replace('__LOADER__', loader)
  .replace('__PERSIST__', persist))

hpath = os.path.join(SP, 'test_v1071.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
r = subprocess.run(['node', hpath], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr[:3000]); sys.exit(1)
# the harness logs the migration notice to stdout before the payload, so take
# the LAST non-empty line rather than the whole stream.
R = json.loads([ln for ln in r.stdout.splitlines() if ln.strip()][-1])

print('\n-- 1. THE data-loss scenario (v9.66 destroyed real work here) --')
ok(R['emptyTable']['kept'] == ['alpha', 'beta'],
   'an EMPTY shared table deletes NOTHING local')
ok(R['emptyTable']['publishedToDb'] == ['alpha', 'beta'],
   '  and publishes the local work up to the shared set')

print('\n-- 2-4. merge semantics --')
ok(R['collision']['sql'] == 'REMOTE', 'the shared copy wins a name collision')
ok(R['collision']['by'] == 'pat@x', '  and carries the saver attribution')
ok(R['remoteDelete']['afterFirst'] == ['alpha', 'beta'], 'first load pulls both')
ok(R['remoteDelete']['afterSecond'] == ['alpha'],
   "a name we HAD seen and is now gone IS removed (a real delete propagates)")
ok(R['neverSeen']['kept'] == ['brandnew'],
   'a never-seen local name is KEPT while a previously-seen one is dropped')
ok('brandnew' in R['neverSeen']['inDb'], '  and the new one is published')

print('\n-- 5. legacy per-user migration --')
ok(R['legacy']['kept'] == ['legacy1', 'legacy2'], 'old per-user queries are pulled in')
ok(R['legacy']['publishedToDb'] == ['legacy1', 'legacy2'], '  and published as shared')

print('\n-- 6-8. the sync is a DIFF, and it is honest --')
ok(R['diffOnly']['upserts'] == [['beta']],
   'only the CHANGED query is upserted (not the whole library)')
ok(R['localDelete']['deletes'] == [['beta']], 'a local delete removes the shared row')
ok(R['localDelete']['dbNames'] == ['alpha'], '  and only that row')
ok(R['failedWrite']['snapshotUnchanged'],
   'a FAILED write does not advance the snapshot (else the delete is lost)')

print('\n-- 9-11. degraded modes --')
ok(R['signedOut']['kept'] == ['alpha'], 'signed out: local queries survive')
ok(R['signedOut']['upserts'] == 0 and R['signedOut']['dbEmpty'],
   '  and nothing is written')
ok(R['missingTable']['kept'] == ['alpha', 'beta'],
   'missing table: local queries survive untouched')
ok(R['activeTracking']['stillPointsAtZzz'],
   'the active query survives a reorder (tracked by name, not index)')

# ------------------------------------------------------------------- report
print('\n%s' % ('-' * 58))
print('v10.71: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
