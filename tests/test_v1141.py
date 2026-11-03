#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.41 - the GA4 Traffic view on the SEO page.

Jason: "do you have a stream of data to build this view into the SEO page?"
then "please continue with the seo tab".

  * A  the REAL seoFetchAll query builder. A 2-element filter still means
       .eq, so every pre-v11.41 caller is byte-identical; a 3-element one is
       [col, op, val].
  * B  the REAL seoTrWindow. YTD is Jan 1 of the CURRENT year, which is what
       the Looker report shows - not a trailing 365.
  * C  the REAL seoTrSum, and the prior-year shift being 364 days (52 whole
       weeks) rather than 365, so a Monday still lands on a Monday.
  * D  static wiring: the sub-tab strip, both search keys, the CSV route, and
       the landing-page table SAYING it is a ranking rather than a total.
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


# ---------------------------------------------------------------------------
# A. The widened fetcher.
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, '_v1141_a.js'), r"""
const out = { calls: [] };
// A query double that records which PostgREST verb each filter resolved to.
function mkQ() {
  const q = {
    _ops: [],
    select() { return q; },
    eq(c, v)  { q._ops.push(['eq', c, v]);  return q; },
    gte(c, v) { q._ops.push(['gte', c, v]); return q; },
    lte(c, v) { q._ops.push(['lte', c, v]); return q; },
    in(c, v)  { q._ops.push(['in', c, v]);  return q; },
    range() { return Promise.resolve({ data: [], error: null }); },
  };
  return q;
}
let LAST = null;
async function getSB() { return { from(t) { LAST = mkQ(); LAST._table = t; return LAST; } }; }
""" + fn('seoFetchAll') + r"""
(async () => {
  // the v11.40 shape - two elements - must still be .eq
  await seoFetchAll('gsc_query', [['property', 'smarterpaw'], ['snapshot_date', '2026-10-19']], 'query');
  out.a1 = LAST._ops;
  // the v11.41 shape
  await seoFetchAll('ga4_by_date', [['property','smarterpaw'], ['day','gte','2026-08-01'], ['day','lte','2026-11-02']], 'day');
  out.a2 = LAST._ops;
  // an unknown operator must fall back to eq rather than throwing or dropping
  await seoFetchAll('ga4_by_date', [['day', 'wat', 'x']], 'day');
  out.a3 = LAST._ops;
  await seoFetchAll('ga4_by_date', [['channel', 'in', ['a','b']]], 'channel');
  out.a4 = LAST._ops;
  console.log(JSON.stringify(out));
})();
""")

eq('A1 a 2-element filter is still .eq, exactly as before v11.41',
   A['a1'], [['eq', 'property', 'smarterpaw'], ['eq', 'snapshot_date', '2026-10-19']])
eq('A2 a 3-element filter resolves its operator',
   A['a2'], [['eq','property','smarterpaw'], ['gte','day','2026-08-01'], ['lte','day','2026-11-02']])
eq('A3 an unknown operator falls back to eq rather than dropping the filter',
   A['a3'], [['eq', 'day', 'x']])
eq('A4 in() is supported', A['a4'], [['in', 'channel', ['a', 'b']]])

# ---------------------------------------------------------------------------
# B. The window.
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, '_v1141_b.js'),
    'let PICK = "90";\n'
    'function mkEl(v){ return { value: v }; }\n'
    'const document = { getElementById: (id) => id === "seo-tr-period" ? mkEl(PICK) : null };\n'
    + fn('seoTrWindow') + r"""
const out = {};
const days = (a, b) => Math.round((new Date(b) - new Date(a)) / 864e5) + 1;
for (const p of ['28', '90', '180', '365']) { PICK = p; const w = seoTrWindow();
  out['b_' + p] = { span: days(w.from, w.to), label: w.label }; }
PICK = 'ytd';
const y = seoTrWindow();
out.b_ytd = { from: y.from, label: y.label, to_year: y.to.slice(0, 4) };
// an unknown value must not produce NaN dates
PICK = 'banana';
const z = seoTrWindow();
out.b_bad = { from: z.from, ok: !isNaN(new Date(z.from).getTime()) };
console.log(JSON.stringify(out));
""")

for p in ('28', '90', '180', '365'):
    eq('B1 "%s" resolves to exactly %s days inclusive' % (p, p), B['b_' + p]['span'], int(p))
eq('B1b and is labelled by what it is', B['b_90']['label'], 'Last 90 days')
ok(B['b_ytd']['from'].endswith('-01-01'), 'B2 YTD starts on Jan 1', B['b_ytd']['from'])
eq('B2b of the CURRENT year, not 365 days back',
   B['b_ytd']['from'][:4], B['b_ytd']['to_year'])
eq('B2c labelled as itself', B['b_ytd']['label'], 'Year to date')
ok(B['b_bad']['ok'], 'B3 an unknown period still yields a real date, not NaN', B['b_bad'])

# ---------------------------------------------------------------------------
# C. Summing, and the prior-year shift.
# ---------------------------------------------------------------------------
C = run_node(os.path.join(SP, '_v1141_c.js'), fn('seoTrSum') + r"""
const out = {};
out.c1 = seoTrSum([
  { sessions: 10, new_users: 4, revenue: 1.5, transactions: 1 },
  { sessions: '5', new_users: null, revenue: '2.25' },
]);
out.c2 = seoTrSum([]);
// a row carrying a field this scope does not have must contribute 0, not NaN
out.c3 = seoTrSum([{ sessions: 3, total_users: undefined, purchasers: 'x' }]);
out.c3_finite = Object.values(out.c3).every(Number.isFinite);
console.log(JSON.stringify(out));
""")

eq('C1 sessions sum across string and number rows', C['c1']['sessions'], 15)
eq('C1b and so does revenue', round(C['c1']['revenue'], 2), 3.75)
eq('C1c a null metric contributes 0', C['c1']['new_users'], 4)
eq('C2 an empty scope is all zeros, not empty', C['c2']['sessions'], 0)
ok(C['c3_finite'], 'C3 no NaN escapes a row with missing or junk fields', C['c3'])

_load = fn('loadSeoTraffic')
ok('364' in _load, 'C4 the prior-year window shifts 364 days')
ok('365' not in re.sub(r'(?m)^\s*//.*$', '', _load),
   'C4b and NOT 365 - a one-day slip puts a weekend against a weekday')
ok('52 whole weeks' in js,
   'C4c with the reason recorded beside it, in the comment above the function')

# ---------------------------------------------------------------------------
# D. Static wiring.
# ---------------------------------------------------------------------------
def nocomment(t):
    t = re.sub(r'/\*[\s\S]*?\*/', '', t)
    return re.sub(r'(?m)^\s*//.*$', '', t)

for f in ('switchSeoView', 'seoTrEnsureShell', 'loadSeoTraffic', 'renderSeoTraffic',
          'downloadSeoTrafficCSV', 'seoTrRenderPages', 'seoTrWindow', 'seoTrSum'):
    eq('D1 exactly one %s' % f, js.count('function %s(' % f), 1)

_sw = fn('switchSeoView')
ok('subtabApply' in _sw, 'D2 the strip goes through the shared chokepoint (hard rule #1)')
ok('globalSearchSyncFromTarget' in _sw,
   'D2b and the top bar re-aims at the view on screen (the v10.3 defect)')

ok("seo_keywords:  { id: 'seo-search' }" in js, 'D3 the Keywords search is mapped')
ok("seo_traffic:   { id: 'seo-tr-search' }" in js, 'D3b and the Traffic search separately')
ok('return `seo_${' in js, 'D3c globalSearchCurrentKey resolves the sub-view')

_csv = fn('exportCSV')
ok("seoView === 'traffic'" in _csv, 'D4 the top-bar CSV reaches the Traffic table')
_dl = fn('downloadSeoTrafficCSV')
for bit in ('w.label', 'chanPick', 'RANKING'):
    ok(bit in _dl, 'D4b the export states its %s' % bit)

# THE HONESTY LINE. Landing-page sessions run ~7% over sitewide and ~18% land
# in (not set); the table has to say so where it is read, not only in the SQL.
_pages = fn('seoTrRenderPages')
ok('a ranking, not a total' in _pages,
   'D5 the landing-page count line says it is a ranking')
ok('no landing page on record' in _pages,
   'D5b and names the (not set) share rather than hiding it')

# The two views must not both be visible, and Keywords is the default.
ok('id="seo-view-traffic" style="display:none"' in s,
   'D6 Traffic starts hidden')
# v11.42 re-point: Jason asked for the tabs swapped, so Traffic leads and is
# the one that starts active. Keywords keeps its button, without the on class.
ok('class="subtab on" id="seo-tab-traffic"' in s,
   'D6b Traffic is the tab that starts active (v11.42)')
ok('<button class="subtab" id="seo-tab-keywords"' in s,
   'D6c and Keywords is still there, just not active')
ok(s.index('id="seo-tab-traffic"') < s.index('id="seo-tab-keywords"'),
   'D6d with Traffic first in the strip')

ok("ga4_by_date:              { icon:" in js, 'D7 DATA_SOURCES declares the GA4 feed')
eq('D8 version chip', len(re.findall(r'>v11\.\d+ \u00b7 [\d-]+<', s)), 1)

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
