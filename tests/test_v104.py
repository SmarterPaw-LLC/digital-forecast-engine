# -*- coding: utf-8 -*-
"""v10.4 — one trend on the Demand Forecast page, and saved column sets migrate."""
import io, os, re, sys, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
RAW = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

fc = js[js.index('const FC_COLUMNS'):js.index('const FC_DEFAULT_VISIBLE')]

a = js.index('(function migrateFcTrendColumn()')
b = js.index('})();', a) + 5
MIGRATE = js[a:b]

static = [
    ('the legacy v60/v90 Trend column is gone from the Forecast registry',
     "key:'trend'" not in fc),
    ('  and no stub was left behind', '__trend_legacy_removed' not in js),
    ('exactly one blended trend column remains',
     len([m for m in re.finditer(r"\{\s*key:\s*'vel_trend'", fc)]) == 1),
    ('  and it defaults ON', re.search(r"key:'vel_trend'[^\n]*default:true", fc) is not None),
    ('the detail panel reads the real engine',
     'ipVelTrendLabel(fcVelTrendFor(r)).txt}</div>' in js),
    ('the trend-mix rollup reads the real engine',
     'const lbl = ipVelTrendLabel(fcVelTrendFor(r)).txt;' in js),
    ('  and no longer counts the legacy string',
     "trendCounts[r.trend || '\u2014 Steady']" not in js),
    ('rec.trend is still computed (the SEED fixture and other readers use it)',
     'rec.trend =' in js or 'c.trend =' in js),

    # ---- v10.4b: the Forecast table sorts via c.get, not c.sortVal ----
    ('fcCompare still skips columns with no `get` (so `get` is REQUIRED to sort)',
     'if (!c || !c.get) continue;' in js),
    ('all 5 blended FC trend columns define `get`',
     all(('get:     r => %s' % e) in fc for e in
         ['fcVelTrendFor(r).now', 'fcVelTrendFor(r).prev', 'fcVelTrendFor(r).delta',
          'velTrendSortVal(fcVelTrendFor(r))'])
     and 'get:     r => { const p = fcVelTrendFor(r).pct;' in fc),
    ('  and none of them still carry only `sortVal`',
     'sortVal: r => fcVelTrendFor(r)' not in fc
     and 'sortVal: r => velTrendSortVal(fcVelTrendFor(r))' not in fc),
    ('the per-channel generator carries BOTH names (one object, two registries)',
     'sortVal: r => velTrendSortVal(ipVelTrendForKeys(r, [_c.key])),' in js
     and 'get:     r => velTrendSortVal(ipVelTrendForKeys(r, [_c.key])),' in js),
    ('  Inventory Planning still sorts via sortVal (unchanged)',
     'sortVal: r => velTrendSortVal(ipVelTrendFor(r)),' in js),
]

HARNESS = r"""
let STORE = {};
const localStorage = {
  getItem: (k) => (k in STORE) ? STORE[k] : null,
  setItem: (k, v) => { STORE[k] = String(v); },
};
let fcVisibleCols = [];
function fcSaveVisible() { try { localStorage.setItem('fcVisibleCols', JSON.stringify(fcVisibleCols)); } catch {} }
function runMigration() { __MIGRATE__ }

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}

console.log('\n== A. A column set saved before v10.2 keeps a Trend column ==');
STORE = {};
fcVisibleCols = ['brand', 'title', 'adj_daily', 'trend', 'need30'];
runMigration();
t('the dead `trend` key is dropped', !fcVisibleCols.includes('trend'), fcVisibleCols);
t('`vel_trend` takes its place', fcVisibleCols.includes('vel_trend'), fcVisibleCols);
t('  IN THE SAME SLOT (column order is preserved)',
  fcVisibleCols.indexOf('vel_trend') === 3, fcVisibleCols);
t('nothing else moved',
  JSON.stringify(fcVisibleCols) === JSON.stringify(['brand','title','adj_daily','vel_trend','need30']),
  fcVisibleCols);
t('the set is persisted', JSON.parse(STORE['fcVisibleCols']).includes('vel_trend'));
t('the flag is set so it runs once', STORE['fcTrendMigratedV104'] === '1');

console.log('\n== B. REGRESSION GUARD: without the migration they lose Trend entirely ==');
// The legacy key no longer exists in the registry, so fcVisibleColumns() would
// filter it out, and vel_trend was never in their saved list.
const preMigration = ['brand', 'title', 'adj_daily', 'trend', 'need30'];
t('a pre-v10.2 set contains neither a live trend key nor vel_trend',
  !preMigration.includes('vel_trend'), preMigration);

console.log('\n== C. A set that never had Trend still gets the new column ==');
STORE = {};
fcVisibleCols = ['brand', 'title', 'need30'];
runMigration();
t('vel_trend is appended', fcVisibleCols.includes('vel_trend'), fcVisibleCols);
t('  at the end, not inserted mid-set',
  fcVisibleCols[fcVisibleCols.length - 1] === 'vel_trend', fcVisibleCols);

console.log('\n== D. It runs exactly once ==');
STORE = {};
fcVisibleCols = ['trend'];
runMigration();
const after = fcVisibleCols.slice();
fcVisibleCols = fcVisibleCols.filter(k => k !== 'vel_trend');   // user deliberately hides it
runMigration();
t('a deliberate later hide is NOT undone', !fcVisibleCols.includes('vel_trend'), fcVisibleCols);
t('  (first run had added it)', after.includes('vel_trend'), after);

console.log('\n== E. Both keys present is de-duped, not doubled ==');
STORE = {};
fcVisibleCols = ['title', 'trend', 'vel_trend', 'need30'];
runMigration();
t('vel_trend appears once', fcVisibleCols.filter(k => k === 'vel_trend').length === 1, fcVisibleCols);
t('trend is gone', !fcVisibleCols.includes('trend'), fcVisibleCols);

console.log('\n== F. Already-migrated users are untouched ==');
STORE = { fcTrendMigratedV104: '1' };
fcVisibleCols = ['title', 'need30'];
runMigration();
t('no column is injected on a later load',
  JSON.stringify(fcVisibleCols) === JSON.stringify(['title','need30']), fcVisibleCols);

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
"""

# Strip the IIFE wrapper so the body can be re-run per case.
body = MIGRATE
# The slice already stops before the IIFE's closing `})();`, so the function
# body is balanced as-is. (An earlier `.rstrip('}')` here ate the closing brace
# of the trailing `} catch {}` and produced unparseable JS.)
body = body[body.index('{', body.index('migrateFcTrendColumn()')) + 1 : body.rindex('})();')].rstrip()

static_js = '\n'.join("t(%r, %s);" % (n, 'true' if v else 'false') for n, v in static)
out = (HARNESS.replace('__MIGRATE__', body)
              .replace("console.log('\\n== A.",
                       "console.log('\\n== 0. Static assertions against the shipped source ==');\n"
                       + static_js + "\nconsole.log('\\n== A."))
p = os.path.join(SP, 'test_v104.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(out)
print('harness %d chars' % len(out))
sys.exit(subprocess.call(['node', p]))
