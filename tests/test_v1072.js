
let dbUserQueries = [];
let activeSavedQueryIdx = -1;
let _activeSavedQueryName = null;
let _sharedQueryDbSnapshot = null;
const SENT = { upserts: [], deletes: [] };

function qToast() {}
function logAudit() {}
function renderSavedQueries() {}
function setActiveSavedQuery(idx) {
  activeSavedQueryIdx = (typeof idx === 'number' && idx >= 0 && idx < dbUserQueries.length) ? idx : -1;
  _activeSavedQueryName = activeSavedQueryIdx >= 0 ? dbUserQueries[activeSavedQueryIdx].name : null;
}
function _sharedQueryCompareKey(q) { return JSON.stringify({ name: q.name, sql: q.sql }); }
// Mirrors the real v10.71 diff: changed -> upsert, vanished -> delete.
async function persistUserQueries() {
  const prev = _sharedQueryDbSnapshot || {};
  const seen = {};
  for (const q of dbUserQueries) {
    const ser = _sharedQueryCompareKey(q);
    seen[q.name] = ser;
    if (prev[q.name] !== ser) SENT.upserts.push(q.name);
  }
  SENT.deletes.push(...Object.keys(prev).filter(n => !(n in seen)));
  _sharedQueryDbSnapshot = seen;
}

let PROMPT = null, CONFIRM = true;
function prompt() { return PROMPT; }
function confirm() { return CONFIRM; }

async function renameUserQuery(idx) {
  const q = dbUserQueries[idx];
  if (!q) return;
  const oldName = q.name;
  const next = (prompt(`Rename saved query "${oldName}" to:`, oldName) || '').trim();
  if (!next || next === oldName) return;

  // A name clash would create two rows fighting over one primary key, so the
  // conflicting entry is dropped rather than left to collide on the upsert.
  const clashIdx = dbUserQueries.findIndex((x, i) => i !== idx && x.name === next);
  if (clashIdx >= 0 && !confirm(`A saved query named "${next}" already exists. Overwrite it?`)) return;
  if (clashIdx >= 0) {
    dbUserQueries.splice(clashIdx, 1);
    if (clashIdx < idx) idx -= 1;
    // Keep the active pointer honest after the splice.
    if (clashIdx === activeSavedQueryIdx)      activeSavedQueryIdx = -1;
    else if (clashIdx < activeSavedQueryIdx)   activeSavedQueryIdx -= 1;
  }

  dbUserQueries[idx] = Object.assign({}, dbUserQueries[idx],
    { name: next, savedAt: new Date().toISOString() });

  await persistUserQueries();
  // setActiveSavedQuery re-derives _activeSavedQueryName from the array, which
  // now holds the new name, and re-renders the chips + Save button label.
  setActiveSavedQuery(activeSavedQueryIdx);
  qToast(`\u2713 Renamed to '${next}'.`);
  logAudit('query.rename', { from: oldName, to: next });
}

const out = {};
function reset(activeIdx) {
  dbUserQueries = [
    { name: 'alpha', sql: 'A', savedAt: 'x' },
    { name: 'beta',  sql: 'B', savedAt: 'x' },
    { name: 'gamma', sql: 'C', savedAt: 'x' },
  ];
  _sharedQueryDbSnapshot = {};
  for (const q of dbUserQueries) _sharedQueryDbSnapshot[q.name] = _sharedQueryCompareKey(q);
  SENT.upserts = []; SENT.deletes = [];
  setActiveSavedQuery(activeIdx);
}
const names = () => dbUserQueries.map(q => q.name);

(async () => {
  // 1. plain rename
  reset(0); PROMPT = 'alpha renamed'; CONFIRM = true;
  await renameUserQuery(0);
  out.plain = { names: names(), activeIdx: activeSavedQueryIdx, activeName: _activeSavedQueryName,
                upserts: [...SENT.upserts], deletes: [...SENT.deletes] };

  // 2. cancelled
  reset(0); PROMPT = null; await renameUserQuery(0);
  out.cancelled = { names: names(), upserts: [...SENT.upserts], deletes: [...SENT.deletes] };

  // 3. unchanged
  reset(0); PROMPT = 'alpha'; await renameUserQuery(0);
  out.unchanged = { names: names(), upserts: [...SENT.upserts] };

  // 4. whitespace only
  reset(0); PROMPT = '   '; await renameUserQuery(0);
  out.blank = { names: names(), upserts: [...SENT.upserts] };

  // 5. trims
  reset(0); PROMPT = '  trimmed  '; await renameUserQuery(0);
  out.trimmed = { names: names() };

  // 6. collision declined
  reset(0); PROMPT = 'beta'; CONFIRM = false; await renameUserQuery(0);
  out.collisionDeclined = { names: names(), upserts: [...SENT.upserts], deletes: [...SENT.deletes] };

  // 7. collision accepted - the clash target is dropped
  reset(2); PROMPT = 'beta'; CONFIRM = true; await renameUserQuery(0);
  out.collisionAccepted = { names: names(), activeIdx: activeSavedQueryIdx,
                            activeName: _activeSavedQueryName, deletes: [...SENT.deletes] };

  // 8. the clash target IS the active query
  reset(1); PROMPT = 'beta'; CONFIRM = true; await renameUserQuery(0);
  out.ateActive = { names: names(), activeIdx: activeSavedQueryIdx, activeName: _activeSavedQueryName };

  // 9. renaming a non-existent index is a no-op
  reset(0); PROMPT = 'zzz'; await renameUserQuery(99);
  out.badIndex = { names: names(), upserts: [...SENT.upserts] };

  console.log(JSON.stringify(out));
})();
