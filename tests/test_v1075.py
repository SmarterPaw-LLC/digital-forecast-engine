# -*- coding: utf-8 -*-
"""v10.75 - saved-view loaders MERGE; an empty remote can never wipe local.

Jason: "reports that i have saved on the units sold page do not appear. is this
not saved to the backend?"

Two faults compounded:

  1. user_profiles.sales_saved_views was never created (the v7.54 migration was
     not run). salesPersistSavedViews writes localStorage FIRST and Supabase
     second, so every save landed locally and the DB write warned to console.
     Per-browser only. That is the literal answer: no, not to the backend.

  2. THE ONE THAT WOULD HAVE EATEN THE DATA. salesLoadSavedViewsFromDb did a
     blind replace:

         salesSavedViews = data.sales_saved_views;
         localStorage.setItem('salesSavedViews', ...);

     After the migration runs, the column defaults to '{}'::jsonb. An empty
     object is TRUTHY and passes `typeof === 'object'`, so the branch fires and
     overwrites the in-memory map AND the on-disk cache with {}. Running the
     SQL first would have permanently destroyed any surviving reports.

     This is the v9.66 bug verbatim - "that table is empty on the first load
     after the migration, so it wrote {} over everything anyone had saved".
     v9.67 fixed it for the shared query library. All FIVE saved-view loaders
     still carried it.

The assertions that earn their keep:

  * THE REGRESSION GUARD runs the pre-v10.75 logic and proves it really does
    return {} for a populated local set. Without it, "we fixed the wipe" is a
    claim about code that nobody re-checks. It also pins the actual mechanism
    (an empty object is truthy) rather than the symptom.

  * MERGE DIRECTION. Remote wins a name collision (it is the cross-device
    canonical copy) while a local-only name survives AND is published. Both
    directions, because getting either backwards is silent: one resurrects
    stale views forever, the other loses work.

  * THE ERROR PATH TOUCHES NOTHING. While the column is missing, the local
    cache is the only copy that exists. A loader that "helpfully" normalises
    on error is a loader that deletes.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name, got=None):
    global passed, failed
    if cond: passed += 1; print('  ok    ' + name)
    else:    failed += 1; print('  FAIL  %s%s' % (name, '' if got is None else '  got: %r' % (got,)))

def fn(name, kw='function'):
    i = js.index('%s %s(' % (kw, name))
    j = js.index('{', i); d = 0; k = j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k+1]
        k += 1

def const_array(name):
    """Slice `const NAME = [ ... ];` by balancing brackets."""
    i = js.index('const %s = [' % name)
    j = js.index('[', i); d = 0; k = j
    while True:
        if js[k] == '[': d += 1
        elif js[k] == ']':
            d -= 1
            if d == 0: return js[i:k+1] + ';'
        k += 1

STORES = [
    ('fcLoadSavedViewsFromDb',        'forecast_saved_views',   'fcSavedViews'),
    ('ipLoadSavedViewsFromDb',        'inventory_saved_views',  'ipSavedViews'),
    ('prodLoadSavedViewsFromDb',      'products_saved_views',   'prodSavedViews'),
    ('salesLoadSavedViewsFromDb',     'sales_saved_views',      'salesSavedViews'),
    ('pnlGrowthLoadSavedViewsFromDb', 'pnl_growth_saved_views', 'pnlGrowthSavedViews'),
]

print('\n== A. consolidation: one loader, five wrappers ==')
ok(js.count('async function loadSavedViewStore(') == 1,
   'exactly one loadSavedViewStore definition')
ok(js.count('const SAVED_VIEW_STORES = [') == 1,
   'exactly one SAVED_VIEW_STORES registry')

for fname, col, var in STORES:
    body = fn(fname, 'async function')
    ok("loadSavedViewStore('%s')" % col in body,
       '%s delegates to the shared loader' % fname)
    # The whole point: the blind replace must be gone from every copy.
    ok(('%s = data.%s' % (var, col)) not in js,
       'no blind replace survives for %s' % var)

print('\n== B. registry wiring (a wrong name here fails only at runtime) ==')
reg = const_array('SAVED_VIEW_STORES')
for fname, col, var in STORES:
    ok("col: '%s'" % col in reg, 'registry declares %s' % col)
    ok('%s' % var in reg,        'registry reads/writes %s' % var)
# v10.8 class: a persist name that does not exist is valid JS and fails only
# when a user actually has a browser-only view to publish.
for m in re.finditer(r'persist:\s*\(\)\s*=>\s*([A-Za-z_$][\w$]*)\(', reg):
    name = m.group(1)
    ok(('async function %s(' % name) in js or ('function %s(' % name) in js,
       'persist target %s() is defined' % name)

print('\n== C. BEHAVIOUR: the real sliced loader driven in node ==')

HARNESS = r'''
// ---- stubs ---------------------------------------------------------------
let fcSavedViews = {}, ipSavedViews = {}, prodSavedViews = {};
let salesSavedViews = {}, pnlGrowthSavedViews = {};

const lsStore = {};
const localStorage = {
  getItem: k => (k in lsStore ? lsStore[k] : null),
  setItem: (k, v) => { lsStore[k] = String(v); },
};
const document = { getElementById: () => null };

const persistLog = [];
async function fcPersistSavedViews()        { persistLog.push(['Forecast', JSON.parse(JSON.stringify(fcSavedViews))]); }
async function ipPersistSavedViews()        { persistLog.push(['Inventory Planning', JSON.parse(JSON.stringify(ipSavedViews))]); }
async function prodPersistSavedViews()      { persistLog.push(['Products', JSON.parse(JSON.stringify(prodSavedViews))]); }
async function salesPersistSavedViews()     { persistLog.push(['Units Sold', JSON.parse(JSON.stringify(salesSavedViews))]); }
async function pnlGrowthPersistSavedViews() { persistLog.push(['Growth Model', JSON.parse(JSON.stringify(pnlGrowthSavedViews))]); }

const auditLog = [];
function logAudit(a, b) { auditLog.push([a, b]); }

let SCENARIO = { signedIn: true, response: { data: {}, error: null } };
async function getSB() {
  return {
    auth: { getUser: async () => ({ data: { user: SCENARIO.signedIn ? { id: 'u1' } : null } }) },
    from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => SCENARIO.response }) }) }),
  };
}
const console2 = { warn: () => {}, log: () => {} };
const console = console2;

// ---- the REAL sliced code ------------------------------------------------
__REPAINT__
__REGISTRY__
__STOREFN__
__LOADER__

// ---- scenarios -----------------------------------------------------------
const R = {};
const COL = 'sales_saved_views';
const reset = (local) => {
  salesSavedViews = JSON.parse(JSON.stringify(local));
  lsStore['salesSavedViews'] = JSON.stringify(local);
  persistLog.length = 0; auditLog.length = 0;
};
const LOCAL2 = { 'YTD Juananip': { tag: 'local-a' }, 'Q4 Chewy': { tag: 'local-b' } };

(async () => {
  // S1 - migration not run: the error path must touch NOTHING.
  reset(LOCAL2);
  SCENARIO = { signedIn: true, response: { data: null, error: { message: 'column user_profiles.sales_saved_views does not exist' } } };
  await loadSavedViewStore(COL);
  R.s1_local  = salesSavedViews;
  R.s1_ls     = JSON.parse(lsStore['salesSavedViews']);
  R.s1_writes = persistLog.length;

  // S2 - THE BUG: column now exists and defaults to {}.
  reset(LOCAL2);
  SCENARIO = { signedIn: true, response: { data: { sales_saved_views: {} }, error: null } };
  await loadSavedViewStore(COL);
  R.s2_local     = salesSavedViews;
  R.s2_ls        = JSON.parse(lsStore['salesSavedViews']);
  R.s2_published = persistLog.map(p => p[0]);
  R.s2_pubNames  = persistLog.length ? Object.keys(persistLog[0][1]).sort() : [];
  R.s2_audit     = auditLog.map(a => a[0]);

  // S3 - union; remote wins a name collision, local-only survives + publishes.
  reset({ A: { tag: 'local-A' }, B: { tag: 'local-B' } });
  SCENARIO = { signedIn: true, response: { data: { sales_saved_views: { A: { tag: 'REMOTE-A' }, C: { tag: 'remote-C' } } }, error: null } };
  await loadSavedViewStore(COL);
  R.s3_keys  = Object.keys(salesSavedViews).sort();
  R.s3_Atag  = salesSavedViews.A.tag;
  R.s3_Btag  = salesSavedViews.B.tag;
  R.s3_pub   = persistLog.length;

  // S4 - remote only, nothing local: no spurious publish.
  reset({});
  SCENARIO = { signedIn: true, response: { data: { sales_saved_views: { X: { tag: 'remote-X' } } }, error: null } };
  await loadSavedViewStore(COL);
  R.s4_keys = Object.keys(salesSavedViews);
  R.s4_pub  = persistLog.length;

  // S5 - signed out: untouched.
  reset(LOCAL2);
  SCENARIO = { signedIn: false, response: { data: { sales_saved_views: {} }, error: null } };
  await loadSavedViewStore(COL);
  R.s5_keys = Object.keys(salesSavedViews).sort();
  R.s5_pub  = persistLog.length;

  // S6 - REGRESSION GUARD: reproduce the pre-v10.75 blind replace.
  const oldLoader = (remote, local) => {
    // verbatim shape of the old branch
    if (remote && typeof remote === 'object') return remote;
    return local;
  };
  R.s6_oldWipes   = Object.keys(oldLoader({}, LOCAL2)).length;
  R.s6_emptyTruthy = !!{};

  // S7 - the registry covers every store, and each one is independently keyed.
  R.s7_cols = SAVED_VIEW_STORES.map(x => x.col);

  process.stdout.write(JSON.stringify(R));
})();
'''

HARNESS = HARNESS.replace('__REPAINT__',  fn('savedViewRepaintPopup'))
HARNESS = HARNESS.replace('__REGISTRY__', const_array('SAVED_VIEW_STORES'))
HARNESS = HARNESS.replace('__STOREFN__',  fn('savedViewStore'))
HARNESS = HARNESS.replace('__LOADER__',   fn('loadSavedViewStore', 'async function'))

hp = os.path.join(SP, '_v1075_harness.js')
io.open(hp, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hp], capture_output=True, text=True)
if res.returncode != 0:
    print('  FAIL  harness did not run:\n' + (res.stderr or '')[:1500])
    failed += 1
    R = {}
else:
    R = json.loads(res.stdout)

if R:
    print('\n  -- S1 migration not run: local cache is the ONLY copy --')
    ok(sorted(R['s1_local'].keys()) == ['Q4 Chewy', 'YTD Juananip'],
       'error path leaves the in-memory map untouched', R['s1_local'])
    ok(sorted(R['s1_ls'].keys()) == ['Q4 Chewy', 'YTD Juananip'],
       'error path leaves localStorage untouched', R['s1_ls'])
    ok(R['s1_writes'] == 0, 'error path writes nothing back', R['s1_writes'])

    print('\n  -- S2 THE BUG: empty remote must not wipe a populated local --')
    ok(sorted(R['s2_local'].keys()) == ['Q4 Chewy', 'YTD Juananip'],
       'empty remote does NOT wipe the in-memory map', R['s2_local'])
    ok(sorted(R['s2_ls'].keys()) == ['Q4 Chewy', 'YTD Juananip'],
       'empty remote does NOT wipe localStorage', R['s2_ls'])
    ok(R['s2_published'] == ['Units Sold'],
       'browser-only reports are published to Supabase', R['s2_published'])
    ok(R['s2_pubNames'] == ['Q4 Chewy', 'YTD Juananip'],
       'the publish carries BOTH reports', R['s2_pubNames'])
    ok('saved_views.publish_local' in R['s2_audit'],
       'the promotion is recorded in the audit log', R['s2_audit'])

    print('\n  -- S3 merge direction (both ways, because both are silent) --')
    ok(R['s3_keys'] == ['A', 'B', 'C'], 'merged set is the union', R['s3_keys'])
    ok(R['s3_Atag'] == 'REMOTE-A', 'remote wins a name collision', R['s3_Atag'])
    ok(R['s3_Btag'] == 'local-B',  'local-only name survives', R['s3_Btag'])
    ok(R['s3_pub'] == 1, 'local-only name triggers a publish', R['s3_pub'])

    print('\n  -- S4 / S5 no spurious writes --')
    ok(R['s4_keys'] == ['X'], 'remote-only set loads cleanly', R['s4_keys'])
    ok(R['s4_pub'] == 0, 'nothing local -> no publish', R['s4_pub'])
    ok(sorted(R['s5_keys']) == ['Q4 Chewy', 'YTD Juananip'],
       'signed out leaves local untouched', R['s5_keys'])
    ok(R['s5_pub'] == 0, 'signed out writes nothing', R['s5_pub'])

    print('\n  -- S6 REGRESSION GUARD: prove the old code really did wipe --')
    ok(R['s6_oldWipes'] == 0,
       'pre-v10.75 blind replace returned {} over 2 saved reports', R['s6_oldWipes'])
    ok(R['s6_emptyTruthy'] is True,
       'the mechanism: an empty object is TRUTHY, so the old branch fired')

    print('\n  -- S7 every store is registered --')
    ok(sorted(R['s7_cols']) == sorted([c for _, c, _ in STORES]),
       'all five saved-view columns are in the registry', R['s7_cols'])

try: os.remove(hp)
except Exception: pass

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
