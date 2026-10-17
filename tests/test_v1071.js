
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

function _sharedQueryCompareKey(q) {
  try { return JSON.stringify({ name: q.name, sql: q.sql }); }
  catch (_) { return String(q && q.name); }
}
let _sharedQueryDbSnapshot = null;
let _sharedQueriesLoaded = false;
async function sharedQueriesSyncToDb(arr) {
  try {
    const sb = await getSB();
    let uid = null, email = null;
    try {
      const { data: { user } } = await sb.auth.getUser();
      if (user) { uid = user.id; email = user.email || null; }
    } catch (_) {}
    if (!uid) return;   // signed out: local only

    const prev = _sharedQueryDbSnapshot || {};
    const rows = [];
    const seen = {};
    for (const q of (arr || [])) {
      if (!q || !q.name) continue;
      const ser = _sharedQueryCompareKey(q);
      seen[q.name] = ser;
      if (prev[q.name] === ser) continue;              // unchanged
      rows.push({ name: q.name, sql: q.sql, updated_by: uid, updated_by_email: email });
    }
    const gone = Object.keys(prev).filter(nm => !(nm in seen));

    if (rows.length) {
      const { error } = await sb.from('shared_saved_queries').upsert(rows, { onConflict: 'name' });
      if (error) {
        if (/does not exist|schema cache/i.test(error.message || '')) {
          console.warn('shared_saved_queries table missing - run supabase_v10_71_shared_saved_queries.sql. Queries stay local until then.');
        } else {
          console.warn('sharedQueriesSyncToDb upsert:', error.message);
        }
        return;
      }
    }
    if (gone.length) {
      const { error } = await sb.from('shared_saved_queries').delete().in('name', gone);
      if (error) { console.warn('sharedQueriesSyncToDb delete:', error.message); return; }
    }
    // Only advance the snapshot once the writes actually landed.
    _sharedQueryDbSnapshot = seen;
  } catch (e) {
    console.warn('sharedQueriesSyncToDb error:', e.message || e);
  }
}
async function loadUserQueriesFromDb() {
  try {
    const sb = await getSB();
    const { data: { user } } = await sb.auth.getUser();
    if (!user) return;  // not signed in - stay on localStorage only

    const { data, error } = await sb.from('shared_saved_queries')
      .select('name, sql, updated_at, updated_by_email');
    if (error) {
      if (/does not exist|schema cache/i.test(error.message || '')) {
        console.warn('shared_saved_queries table missing - run supabase_v10_71_shared_saved_queries.sql. Queries stay local (per-browser) until then.');
      } else {
        console.warn('loadUserQueriesFromDb:', error.message);
      }
      return;
    }

    const shared = {};
    const snap   = {};
    for (const row of (data || [])) {
      const q = { name: row.name, sql: row.sql,
                  savedAt: row.updated_at, updatedByEmail: row.updated_by_email || null };
      shared[row.name] = q;
      snap[row.name]   = _sharedQueryCompareKey(q);
    }

    // v10.71 - MERGE, never replace. See the v9.67 note on the helpers above:
    // on the FIRST load after the migration this table is empty, and a replace
    // would wipe every query already saved in this browser.
    const priorSnap = _sharedQueryDbSnapshot;   // null on the first load of a session
    const merged    = Object.assign({}, shared);
    let publishedAny = false;

    for (const q of (dbUserQueries || [])) {
      if (!q || !q.name) continue;
      if (q.name in merged) continue;                      // shared copy wins
      if (priorSnap && (q.name in priorSnap)) continue;     // genuinely deleted by someone
      merged[q.name] = q;                                   // keep it
      publishedAny = true;                                  // and publish it below
    }

    // One-time migration of the OLD per-user column, so nobody's existing
    // queries are stranded when the library goes shared.
    try {
      const { data: prof } = await sb.from('user_profiles')
        .select('db_user_queries').eq('user_id', user.id).maybeSingle();
      const legacy = Array.isArray(prof && prof.db_user_queries) ? prof.db_user_queries : [];
      let migrated = 0;
      for (const q of legacy) {
        if (!q || !q.name) continue;
        if (q.name in merged) continue;                     // already have it
        if (priorSnap && (q.name in priorSnap)) continue;    // deleted from the shared set
        merged[q.name] = q;
        migrated++; publishedAny = true;
      }
      if (migrated) {
        console.log('[Query lib] Migrating ' + migrated + ' per-user queries into the shared library...');
        logAudit('query.migrate_shared', { count: migrated });
      }
    } catch (_) { /* legacy column may be gone; not fatal */ }

    _sharedQueryDbSnapshot = snap;
    _sharedQueriesLoaded   = true;

    dbUserQueries = Object.values(merged)
      .sort((a, b) => String(a.name).localeCompare(String(b.name)));
    try { localStorage.setItem('dbUserQueries', JSON.stringify(dbUserQueries)); } catch (_) {}

    // Publish anything that only existed locally, so the rest of the team gets
    // it. One-time per query: once it is in the table it is in the snapshot and
    // the diff leaves it alone.
    if (publishedAny) { try { await sharedQueriesSyncToDb(dbUserQueries); } catch (_) {} }

    // The active index is positional and the merge may have reordered things.
    // Re-point it by NAME so the editor keeps pointing at the same query.
    if (activeSavedQueryIdx >= 0 && _activeSavedQueryName) {
      const i = dbUserQueries.findIndex(q => q.name === _activeSavedQueryName);
      activeSavedQueryIdx = i;
    }
    renderSavedQueries();
  } catch (e) { console.warn('loadUserQueriesFromDb error:', e.message || e); }
}
async function persistUserQueries() {
  // Write to localStorage immediately (offline cache + fast first paint).
  try { localStorage.setItem('dbUserQueries', JSON.stringify(dbUserQueries)); } catch (_) {}
  // v10.71 - then push the DIFF to the shared table. Fire-and-forget: UI
  // updates never wait for the round-trip, and failures log without blocking.
  try { await sharedQueriesSyncToDb(dbUserQueries); }
  catch (e) { console.warn('persistUserQueries error:', e.message || e); }
}

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
