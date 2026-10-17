# -*- coding: utf-8 -*-
"""v10.72 - rename a saved query.

Jason: "i can't rename queries." Correct. Forecast (fcRenameView), Inventory
(ipRenameView) and P&L (pnlRenameView) all gained a rename in v4.129; the Query
Database library was missed and only ever had load + delete. Renaming meant
save-as under a new name then delete the old one, which on the SHARED library
(v10.71) is two team-visible edits for what should be one.

Two things are worth guarding:

  1. `name` is the PRIMARY KEY of shared_saved_queries, so a rename is a
     DELETE + INSERT server-side. The v10.71 diff handles that without any
     special-casing, and this test pins that it really does - if the sync ever
     stopped emitting the delete, the old row would linger forever and the
     library would slowly fill with orphans.

  2. The active-query pointer is POSITIONAL. Dropping a conflicting entry
     shifts indices underneath it, and the nastiest case is when the entry
     being dropped IS the active one.
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

print('\n== A. parity with the other saved-view libraries ==')
for f in ['fcRenameView', 'ipRenameView', 'pnlRenameView', 'renameUserQuery']:
    ok(js.count('function %s(' % f) == 1, '%s defined once' % f)
ok(len(re.findall(r'renameUserQuery\s*\(', js)) >= 2,
   'renameUserQuery is both defined AND wired to a chip (v10.8 class)')

ren = fn('renameUserQuery', 'async function')
ok('prompt(' in ren, 'prompts for the new name')
ok('oldName' in ren and 'next === oldName' in ren, 'no-ops on an unchanged name')
ok(".trim()" in ren, 'trims the input')
ok('confirm(' in ren, 'confirms before overwriting a conflicting name')
ok('logAudit' in ren, 'writes an audit entry')
ok('await persistUserQueries()' in ren,
   'persists through the SHARED sync, not a local-only write')

print('\n== B. the chip renders it ==')
render = fn('renderSavedQueries')
ok("ren.textContent = '\u270e'" in render, 'a pencil button is rendered')
ok('chip.appendChild(ren)' in render, '  and appended to the chip')
ok(render.index('chip.appendChild(load)') < render.index('chip.appendChild(ren)')
   < render.index('chip.appendChild(del)'),
   '  positioned between load and delete')
ok('e.stopPropagation(); renameUserQuery(i)' in render,
   'clicking rename does not also load the query')
ok('library is shared' in render,
   'the tooltip warns the rename is team-wide')

print('\n== C. BEHAVIOUR (real sliced handler driven in node) ==')

HARNESS = r"""
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

__RENAME__

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
"""
HARNESS = HARNESS.replace('__RENAME__', ren)
hpath = os.path.join(SP, 'test_v1072.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
r = subprocess.run(['node', hpath], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr[:2500]); sys.exit(1)
R = json.loads([ln for ln in r.stdout.splitlines() if ln.strip()][-1])

print('\n-- the rename itself --')
ok(R['plain']['names'] == ['alpha renamed', 'beta', 'gamma'], 'the name changes in place')
ok(R['plain']['activeIdx'] == 0 and R['plain']['activeName'] == 'alpha renamed',
   'the active pointer follows the rename')

print('\n-- PK rename = delete + insert on the shared table --')
ok(R['plain']['deletes'] == ['alpha'], 'the OLD name is deleted server-side')
ok(R['plain']['upserts'] == ['alpha renamed'], '  and only the NEW name is upserted')

print('\n-- the no-ops really are no-ops --')
for key, label in [('cancelled', 'cancelling'), ('unchanged', 'an unchanged name'),
                   ('blank', 'a whitespace-only name'), ('badIndex', 'a bad index')]:
    ok(R[key]['names'] == ['alpha', 'beta', 'gamma'], '%s changes nothing' % label)
    ok(R[key]['upserts'] == [], '  and writes nothing')
ok(R['cancelled']['deletes'] == [], 'cancelling deletes nothing')
ok(R['trimmed']['names'] == ['trimmed', 'beta', 'gamma'], 'surrounding whitespace is trimmed')

print('\n-- collisions --')
ok(R['collisionDeclined']['names'] == ['alpha', 'beta', 'gamma'],
   'declining an overwrite changes nothing')
ok(R['collisionDeclined']['deletes'] == [], '  and deletes nothing')
ok(R['collisionAccepted']['names'] == ['beta', 'gamma'],
   'accepting drops the clash target so two rows cannot fight over one PK')
ok(R['collisionAccepted']['activeName'] == 'gamma',
   '  the active query is still the right one after indices shift')
ok(R['collisionAccepted']['activeIdx'] == 1,
   '  and its index was decremented, not left stale')
ok(sorted(R['collisionAccepted']['deletes']) == ['alpha'],
   '  the vanished old name is deleted server-side')
ok(R['ateActive']['activeIdx'] == -1 and R['ateActive']['activeName'] is None,
   'when the clash target IS the active query, active clears instead of pointing at a ghost')

print('\n%s' % ('-' * 58))
print('v10.72: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
