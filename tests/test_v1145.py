#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.45 - the upload coverage grid.

Jason: "i should see the relevance uploads with checkmarks next to them, where
applicable, by region and brand ... If any report is out of freshness zone, it
should not show the checkmark and should instead show the most recent date of
an upload"

  * A  freshness by GRAIN. A monthly feed is not late at 20 days and a daily
       one is, so the window is derived from the date field unless the source
       declares its own.
  * B  the axes are the ones the source ACTUALLY has. Inventing a region axis
       for a table with no region column is a grid of permanently blank cells.
  * C  one bounded scan, then a targeted probe per empty cell - so a feed that
       stopped reporting in March reads as March, not as never.
  * D  THE THREE MARKS. Fresh is a check, stale is THE DATE, never-uploaded is
       a dash. A stale cell rendering blank would read as never-uploaded,
       which is the confusion the grid exists to remove.
  * E  static: no second source registry, and one hook rather than seven.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0


def ok(cond, name, got=None):
    global passed, failed
    if cond:
        passed += 1; print('  ok    ' + name)
    else:
        failed += 1
        print('  FAIL  ' + name + ('' if got is None else '   got=' + ascii(got)))


def eq(name, got, want):
    ok(got == want, name, None if got == want else '%s want %s' % (ascii(got), ascii(want)))


def _balance(i):
    k, n = i, len(js)
    depth, started, prev = 0, False, ''
    while k < n:
        c = js[k]
        if c == '/' and k + 1 < n and js[k + 1] == '/':
            while k < n and js[k] != '\n':
                k += 1
            continue
        if c == '/' and k + 1 < n and js[k + 1] == '*':
            k = js.index('*/', k) + 2
            continue
        if c == '/' and prev in '(,=:[!&|?{};+-*%~^<>':
            k += 1
            while k < n:
                if js[k] == '\\':
                    k += 2; continue
                if js[k] == '[':
                    while k < n and js[k] != ']':
                        k += 2 if js[k] == '\\' else 1
                if js[k] == '/':
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = 'x'
            continue
        if c in '"\'`':
            q = c; k += 1
            while k < n:
                if js[k] == '\\':
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = 'x'
            continue
        if c == '{':
            depth += 1; started = True
        elif c == '}':
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise RuntimeError('unbalanced slice at %d' % i)


def fn(name):
    i = js.index('function %s(' % name)
    head = 'async ' if js[max(0, i - 6):i] == 'async ' else ''
    k = js.index('(', i)
    depth = 0
    while k < len(js):
        if js[k] == '(': depth += 1
        elif js[k] == ')':
            depth -= 1
            if depth == 0: break
        k += 1
    brace = js.index('{', k)
    return head + js[i:brace] + _balance(brace)


def const_obj(name):
    i = js.index('const %s = {' % name)
    return 'const %s = %s;' % (name, _balance(js.index('{', i)))


def run_node(path, src):
    io.open(path, 'w', encoding='utf-8', newline='\n').write(src)
    r = subprocess.run(['node', path], capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        print(r.stdout); print(r.stderr); sys.exit(1)
    return json.loads(r.stdout)


UH = r"""
const UH_SOURCES = {
  t_both:    { dateField: 'snapshot_date', regionField: 'region',
               regionOptions: ['US','CA'], brandField: 'brand',
               brandOptions: ['Meowijuana','Doggijuana'] },
  t_region:  { dateField: 'week_start', regionField: 'region',
               regionOptions: ['US','CA'], brandField: null },
  t_none:    { dateField: 'day', regionField: null, brandField: null },
  t_month:   { dateField: 'reporting_month', regionField: null, brandField: null },
  t_year:    { dateField: 'year', regionField: null, brandField: null },
  t_declare: { dateField: 'day', freshDays: 3, regionField: null, brandField: null },
  t_nodate:  { regionField: null, brandField: null },
};
function esc2(v) { return String(v == null ? '' : v); }
"""

# ---------------------------------------------------------------------------
# A / B. Windows and axes.
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, '_v1145_a.js'),
    UH + fn('uploadFreshDays') + '\n' + fn('uploadCoverageAxes') + '\n' + r"""
const out = {};
out.a = {};
for (const t of ['t_both','t_region','t_none','t_month','t_year','t_declare','t_nodate'])
  out.a[t] = uploadFreshDays(t);
out.a_unknown = uploadFreshDays('not_a_table');
out.b_both   = uploadCoverageAxes('t_both');
out.b_region = uploadCoverageAxes('t_region');
out.b_none   = uploadCoverageAxes('t_none');
out.b_unknown = uploadCoverageAxes('nope');
console.log(JSON.stringify(out));
""")

eq('A1 a weekly feed is fresh for 14 days', A['a']['t_region'], 14)
eq('A2 a MONTHLY feed is not late at 20 days', A['a']['t_month'], 45)
eq('A3 an annual one gets a year', A['a']['t_year'], 400)
eq('A4 a daily feed and a snapshot get 10', [A['a']['t_none'], A['a']['t_both']], [10, 10])
eq('A5 a source that DECLARES its own window wins', A['a']['t_declare'], 3)
eq('A6 an unknown table still returns a number, not NaN', A['a_unknown'], 10)

eq('B1 both axes come from the declared options',
   [A['b_both']['rows'], A['b_both']['cols']],
   [['US', 'CA'], ['Meowijuana', 'Doggijuana']])
eq('B2 a region-only source gets ONE unlabelled column',
   [A['b_region']['rows'], A['b_region']['cols']], [['US', 'CA'], [None]])
eq('B3 a source with neither gets ONE cell, not an invented grid',
   [A['b_none']['rows'], A['b_none']['cols']], [[None], [None]])
eq('B3b which still answers "is this fresh?"', A['b_none']['dateField'], 'day')
eq('B4 an unknown table degrades to one cell rather than throwing',
   [A['b_unknown']['rows'], A['b_unknown']['cols']], [[None], [None]])

# ---------------------------------------------------------------------------
# C. The fetch.
# ---------------------------------------------------------------------------
C = run_node(os.path.join(SP, '_v1145_c.js'),
    UH + 'const QUERIES = [];\nlet SCAN = []; let PROBE = {}; let THROW = false;\n'
    + r"""
function mkQ(table) {
  const q = { _eq: {}, _limit: null };
  q.select = () => q; q.order = () => q;
  q.limit = (n) => { q._limit = n; return q; };
  q.eq = (c, v) => { q._eq[c] = v; return q; };
  q.then = (res, rej) => {
    QUERIES.push({ limit: q._limit, eq: { ...q._eq } });
    if (THROW) return Promise.reject(new Error('boom')).then(res, rej);
    if (q._limit === 1) {
      const k = (q._eq.region || '') + '|' + (q._eq.brand || '');
      const d = PROBE[k];
      return Promise.resolve({ data: d ? [{ snapshot_date: d }] : [] }).then(res, rej);
    }
    return Promise.resolve({ data: SCAN }).then(res, rej);
  };
  return q;
}
async function getSB() { return { from: (t) => mkQ(t) }; }
console.warn = () => {};
""" + fn('uploadCoverageAxes') + '\n' + fn('uploadCoverageFetch') + '\n' + r"""
const out = {};
(async () => {
  // Newest first, so the FIRST appearance of a combination is its latest.
  SCAN = [
    { snapshot_date: '2026-11-03', region: 'US', brand: 'Meowijuana' },
    { snapshot_date: '2026-11-02', region: 'US', brand: 'Meowijuana' },
    { snapshot_date: '2026-10-20', region: 'US', brand: 'Doggijuana' },
    { snapshot_date: null,         region: 'CA', brand: 'Meowijuana' },
  ];
  PROBE = { 'CA|Meowijuana': '2026-03-01' };   // stopped reporting in March
  QUERIES.length = 0;
  out.c1 = await uploadCoverageFetch('t_both');
  out.c1_queries = QUERIES.length;
  out.c1_probes = QUERIES.filter(q => q.limit === 1).map(q => q.eq);

  // A failing scan returns NOTHING and does not throw.
  THROW = true; QUERIES.length = 0;
  let threw = false;
  try { out.c2 = await uploadCoverageFetch('t_both'); } catch (e) { threw = true; }
  out.c2_threw = threw;
  THROW = false;

  // A source with no date field cannot be probed at all.
  QUERIES.length = 0;
  out.c3 = await uploadCoverageFetch('t_nodate');
  out.c3_queries = QUERIES.length;
  console.log(JSON.stringify(out));
})();
""")

eq('C1 the newest row per combination wins', C['c1']['US|Meowijuana'], '2026-11-03')
eq('C1b a second combination in the same scan', C['c1']['US|Doggijuana'], '2026-10-20')
eq('C2 a cell the scan missed is PROBED, not left blank',
   C['c1']['CA|Meowijuana'], '2026-03-01')
ok({'region': 'CA', 'brand': 'Meowijuana'} in C['c1_probes'],
   'C2b and the probe is scoped to that cell', C['c1_probes'])
eq('C2c a null date is not treated as a date', 'CA|Doggijuana' in C['c1'], False)
eq('C3 a failing read returns nothing', C['c2'], {})
ok(C['c2_threw'] is False, 'C3b and does not throw - decoration cannot break the page')
eq('C4 a source with no date field issues no queries at all', C['c3_queries'], 0)

# ---------------------------------------------------------------------------
# D. THE THREE MARKS.
# ---------------------------------------------------------------------------
D = run_node(os.path.join(SP, '_v1145_d.js'),
    UH + fn('uploadFreshDays') + '\n' + fn('uploadCoverageAxes') + '\n'
    + fn('uploadCoverageHtml') + '\n' + r"""
const out = {};
const iso = (n) => { const d = new Date(); d.setDate(d.getDate() - n);
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
const FRESH = iso(2), STALE = iso(60);
out.d1 = uploadCoverageHtml('t_both', {
  'US|Meowijuana': FRESH, 'US|Doggijuana': STALE, 'CA|Meowijuana': FRESH });
out.d1_stale = STALE;
out.d2 = uploadCoverageHtml('t_none', {});
out.d3 = uploadCoverageHtml('t_none', { '|': FRESH });
console.log(JSON.stringify(out));
""")

eq('D1 a fresh cell is a CHECKMARK', D['d1'].count('&#10003;'), 2)
ok(D['d1_stale'] in D['d1'],
   'D2 a STALE cell shows the most recent date, exactly as asked')
ok('&#10003;' not in D['d1'].split(D['d1_stale'])[0].split('<td')[-1],
   'D2b and no checkmark beside it')
eq('D3 a cell never uploaded is a DASH, not a blank', D['d1'].count('&#8212;'), 1)
ok('Meowijuana' in D['d1'] and 'US' in D['d1'],
   'D4 both axes are labelled')
ok('<th' in D['d1'], 'D4b with real header cells')
ok('&#8212;' in D['d2'], 'D5 an empty single-cell source reads as never uploaded')
ok('&#10003;' in D['d3'], 'D5b and a fresh one as a check')
ok('var(--sp-green)' in D['d3'] and 'var(--orange)' in D['d1'],
   'D6 fresh is green, stale is orange')
ok('Nothing has ever been uploaded' in D['d2'],
   'D7 the dash says what it means on hover')

# ---------------------------------------------------------------------------
# E. Static wiring.
# ---------------------------------------------------------------------------
def nocomment(t):
    t = re.sub(r'/\*[\s\S]*?\*/', '', t)
    return re.sub(r'(?m)^\s*//.*$', '', t)
code = nocomment(js)

for f in ('uploadFreshDays', 'uploadCoverageAxes', 'uploadCoverageFetch',
          'uploadCoverageHtml', 'uploadCoverageHost', 'renderUploadCoverage',
          'renderAllUploadCoverage'):
    eq('E1 exactly one %s' % f, code.count('function %s(' % f), 1)

# NO SECOND REGISTRY. The grid reads the two that already describe a source.
ok('UH_SOURCES[table]' in code, 'E2 it reads UH_SOURCES for the dims')
ok('DZ_RECENT_SOURCES[dzId]' in code, 'E2b and DZ_RECENT_SOURCES for the card')
ok(not re.search(r'const UPLOAD_COVERAGE\w*\s*=', code),
   'E2c and declares no second description of the same 22 sources')

# ONE hook, in the function every caller already uses.
eq('E3 hooked exactly once', code.count('renderAllUploadCoverage();'), 1)
ok('renderAllUploadCoverage();' in nocomment(fn('renderAllDzRecentUploads')),
   'E3b inside the rail renderer, not beside each of its seven call sites')
ok('try {' in nocomment(fn('renderAllDzRecentUploads')),
   'E3c and guarded, so a failing grid cannot take the rails down')

_host = fn('uploadCoverageHost')
ok('z-index:2' in _host,
   'E4 the grid sits above the file input that overlays the card (v11.34)')
ok('.dz-last' in _host, 'E4b and lands under the last-upload line')

eq('E5 version chip', len(re.findall(r'>v11\.45 \u00b7 [\d-]+<', s)), 1)

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
