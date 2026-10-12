# -*- coding: utf-8 -*-
"""
v10.12 — shared P&L trend-chart engine.

Default state on every P&L page is now a TOTAL sales line (no selection
needed), with a line / stacked-area toggle that breaks that total out by
product. One engine drives all four pages so the behaviour cannot drift.

Slices the REAL pnlTrendSeries / pnlSlotAdd / pnlChartMode / pnlTrendSubtitle
out of index.html and drives them.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(os.path.dirname(HERE), 'index.html')
src = io.open(INDEX, encoding='utf-8', newline='').read()
js = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', src, re.S), key=len)


def fn(name):
    for pat in (r'\nfunction %s\s*\(' % re.escape(name),
                r'\nasync function %s\s*\(' % re.escape(name)):
        m = re.search(pat, js)
        if m:
            break
    else:
        raise SystemExit('FAIL: cannot find %s' % name)
    # Balance the PARAMETER list first. `function f({ a, b })` destructures, so
    # naively taking the first `{` after the name grabs the parameter pattern
    # and truncates the function at its closing brace.
    k = m.end() - 1                     # at '('
    pdepth = 0
    while k < len(js):
        if js[k] == '(':
            pdepth += 1
        elif js[k] == ')':
            pdepth -= 1
            if pdepth == 0:
                break
        k += 1
    i = js.index('{', k)
    depth, j = 0, i
    while j < len(js):
        if js[j] == '{':
            depth += 1
        elif js[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return js[m.start() + 1:j + 1]


m = re.search(r'\n(const PNL_CHART_TOPN = \d+;)', js)
if not m:
    raise SystemExit('FAIL: cannot find PNL_CHART_TOPN')

SLICES = [
    m.group(1),
    fn('pnlChartMode'),
    fn('pnlSlotAdd'),
    fn('pnlTrendSeries'),
    fn('pnlTrendSubtitle'),
]

HARNESS = r'''
const _ls = {};
const localStorage = { getItem: k => (k in _ls ? _ls[k] : null), setItem: (k,v) => { _ls[k] = String(v); } };

__SLICES__

let pass = 0, fail = 0; const failures = [];
function ok(c, label, extra) { if (c) pass++; else { fail++; failures.push(label + (extra ? ' :: ' + extra : '')); } }
function near(a, b, label, eps) {
  eps = eps == null ? 1e-9 : eps;
  ok(a != null && Math.abs(a - b) < eps, label, 'expected ' + b + ', got ' + (a == null ? 'null' : a));
}
const COLORS = ['#c1','#c2','#c3','#c4','#c5','#c6','#c7','#c8','#c9','#c10'];

// Three products over three weeks. Sales chosen so totals are trivial to
// check by hand, and so one product has a HOLE in the middle week.
const W = ['2026-09-07','2026-09-14','2026-09-21'];
const perProd = {
  A: { '2026-09-07': { netSales: 100, units: 10, cogs: 40 },
       '2026-09-14': { netSales: 200, units: 20, cogs: 80 },
       '2026-09-21': { netSales: 300, units: 30, cogs: 120 } },
  B: { '2026-09-07': { netSales:  50, units:  5, cogs: 10 },
       '2026-09-21': { netSales:  70, units:  7, cogs: 14 } },   // no week 2
  C: { '2026-09-14': { netSales:  10, units:  1, cogs:  9 } },
};
const MIDS = ['A','B','C'];
const metricSales = s => s.netSales;
const metricMarginPct = s => (s.netSales > 0 ? ((s.netSales - s.cogs) / s.netSales * 100) : null);
const labelOf = m => 'Product ' + m;
const base = { perProd, buckets: W, mids: MIDS, colors: COLORS, labelOf };

// ═════════ A. the default state: no selection, line mode -> ONE total ════════
const A = pnlTrendSeries(Object.assign({}, base, { metricOf: metricSales, mode: 'line', selectionActive: false }));
ok(A.datasets.length === 1, 'A1 default state is a single series', 'got ' + A.datasets.length);
ok(/^Total/.test(A.datasets[0].label), 'A1 labelled Total', A.datasets[0].label);
ok(A.datasets[0].label.indexOf('3 products') >= 0, 'A1 names the product count', A.datasets[0].label);
near(A.datasets[0].data[0], 150, 'A2 wk1 total = 100 + 50');
near(A.datasets[0].data[1], 210, 'A2 wk2 total = 200 + 10 (B absent)');
near(A.datasets[0].data[2], 370, 'A2 wk3 total = 300 + 70');
ok(A.datasets[0].fill === false, 'A3 line mode does not fill');
ok(A.mode === 'line', 'A3 mode stays line');

// A4 — a bucket where NOTHING sold is a gap, not a fabricated zero.
const A4 = pnlTrendSeries(Object.assign({}, base, {
  buckets: W.concat(['2026-09-28']), metricOf: metricSales, mode: 'line', selectionActive: false }));
ok(A4.datasets[0].data[3] === null, 'A4 empty bucket is null in line mode, not 0');

// ═════════ B. selection + line = one line per selected product ══════════════
const B = pnlTrendSeries(Object.assign({}, base, {
  mids: ['A','B'], metricOf: metricSales, mode: 'line', selectionActive: true }));
ok(B.datasets.length === 2, 'B1 one series per selected product', 'got ' + B.datasets.length);
ok(B.datasets.map(d => d.label).join('|') === 'Product A|Product B', 'B1 labels', B.datasets.map(d=>d.label).join('|'));
ok(B.datasets[1].data[1] === null, 'B2 a product with no row that week is a gap');
ok(B.datasets.every(d => d.fill === false), 'B3 no fill in line mode');

// ═════════ C. stacked mode ══════════════════════════════════════════════════
const C = pnlTrendSeries(Object.assign({}, base, { metricOf: metricSales, mode: 'stacked', selectionActive: false }));
ok(C.mode === 'stacked', 'C1 stacked mode');
ok(C.datasets.length === 3, 'C1 one band per product', 'got ' + C.datasets.length);
// C2 — THE stacking contract. Chart.js chains area fills: the first band fills
// to the origin and every later one fills to the band BELOW it. `fill:true`
// instead fills every band to zero and the upper ones paint over the lower
// ones — the exact v4.135 Units Sold bug.
ok(C.datasets[0].fill === 'origin', 'C2 first band fills to origin', String(C.datasets[0].fill));
ok(C.datasets.slice(1).every(d => d.fill === '-1'), 'C2 later bands fill to the one below');
// C3 — a hole must be 0 in a stacked band, or the fill chain breaks and the
// bands above it detach.
ok(C.datasets.every(d => d.data.every(v => v !== null)), 'C3 no nulls inside stacked bands');
const bandB = C.datasets.find(d => d.label === 'Product B');
near(bandB.data[1], 0, 'C3 B missing week 2 becomes 0, not null');
// C4 — the bands sum to the same total the line mode shows.
for (let i = 0; i < W.length; i++) {
  const stackSum = C.datasets.reduce((a, d) => a + (d.data[i] || 0), 0);
  near(stackSum, A.datasets[0].data[i], 'C4 stacked bands sum to the total at week ' + (i+1));
}
// C5 — biggest product at the base so the stack has a stable foundation.
ok(C.datasets[0].label === 'Product A', 'C5 largest product is the bottom band', C.datasets[0].label);
ok(C.datasets[C.datasets.length-1].label === 'Product C', 'C5 smallest on top');
// C6 — bands are near-opaque so they read as layers, not a haze.
ok(C.datasets.every(d => /d9$/.test(d.backgroundColor)), 'C6 stacked bands are near-opaque');
ok(A.datasets[0].backgroundColor.endsWith('22'), 'C6 line mode stays translucent');

// ═════════ D. top-N + Other, so a 300-SKU page is still readable ════════════
const many = {}; const manyMids = [];
for (let i = 0; i < 25; i++) {
  const id = 'P' + i;
  manyMids.push(id);
  // P0 biggest .. P24 smallest
  many[id] = { [W[0]]: { netSales: (25 - i) * 10, units: 1, cogs: 0 } };
}
const D = pnlTrendSeries({ perProd: many, buckets: [W[0]], mids: manyMids, metricOf: metricSales,
                           colors: COLORS, labelOf, mode: 'stacked', selectionActive: false });
ok(D.datasets.length === PNL_CHART_TOPN + 1, 'D1 top-N bands plus one Other', 'got ' + D.datasets.length);
ok(/^Other/.test(D.datasets[D.datasets.length-1].label), 'D1 last band is Other');
ok(D.datasets[D.datasets.length-1].label.indexOf('17 SKUs') >= 0, 'D1 Other names the tail size',
   D.datasets[D.datasets.length-1].label);
ok(D.datasets[0].label === 'Product P0', 'D2 biggest SKU leads', D.datasets[0].label);
// D3 — Other must carry the remainder exactly; the stack still equals the total.
const grand = manyMids.reduce((a, id) => a + many[id][W[0]].netSales, 0);
const dSum = D.datasets.reduce((a, d) => a + (d.data[0] || 0), 0);
near(dSum, grand, 'D3 top-N + Other still sums to the grand total');
// D4 — an explicit selection is never truncated, however long.
const D4 = pnlTrendSeries({ perProd: many, buckets: [W[0]], mids: manyMids, metricOf: metricSales,
                            colors: COLORS, labelOf, mode: 'stacked', selectionActive: true });
ok(D4.datasets.length === 25, 'D4 a 25-product SELECTION is not rolled into Other', 'got ' + D4.datasets.length);
ok(!D4.datasets.some(d => /^Other/.test(d.label)), 'D4 no Other band when the user picked the set');

// ═════════ E. percentages: recomputed, never averaged, never stacked ════════
// Week 1: A margin 60% on 100, B margin 80% on 50. The SALES-WEIGHTED answer
// is (150-50)/150 = 66.67%, NOT the 70% a naive average of 60 and 80 gives.
const E = pnlTrendSeries(Object.assign({}, base, { metricOf: metricMarginPct, mode: 'line', selectionActive: false, isPct: true }));
near(E.datasets[0].data[0], 100/150*100, 'E1 total % recomputed from summed components', 1e-9);
ok(Math.abs(E.datasets[0].data[0] - 70) > 1, 'E1-REGRESSION it is NOT the naive average of the two margins',
   'got ' + E.datasets[0].data[0]);
// E2 — stacking a percentage is meaningless, so it degrades to lines and says so.
const E2 = pnlTrendSeries(Object.assign({}, base, { metricOf: metricMarginPct, mode: 'stacked', selectionActive: false, isPct: true }));
ok(E2.mode === 'line', 'E2 stacked + percentage falls back to line', E2.mode);
ok(/do not sum/.test(E2.note), 'E2 and explains why', E2.note);
ok(E.note === '', 'E2 no note when nothing was overridden');

// ═════════ F. pnlSlotAdd ════════════════════════════════════════════════════
const acc = {};
pnlSlotAdd(acc, { a: 1, b: 2, label: 'skip-me' });
pnlSlotAdd(acc, { a: 10, c: 5 });
ok(acc.a === 11 && acc.b === 2 && acc.c === 5, 'F1 numeric fields sum', JSON.stringify(acc));
ok(!('label' in acc), 'F1 non-numeric fields are skipped');
ok(pnlSlotAdd(acc, null) === acc, 'F2 a null slot is a no-op');
const accNew = {}; pnlSlotAdd(accNew, { x: 3 });
ok(accNew.x === 3, 'F3 works from empty');

// ═════════ G. mode persistence ══════════════════════════════════════════════
ok(pnlChartMode() === 'line', 'G1 default mode is line');
_ls.pnlChartMode = 'stacked';
ok(pnlChartMode() === 'stacked', 'G2 reads a stored stacked');
_ls.pnlChartMode = 'nonsense';
ok(pnlChartMode() === 'line', 'G3 a junk stored value degrades to line');
delete _ls.pnlChartMode;

// ═════════ H. subtitle ══════════════════════════════════════════════════════
const h1 = pnlTrendSubtitle({ selectionActive: false, midCount: 42, bandCount: 1, buckets: 13,
                              from: '2026-07-01', to: '2026-09-30', mode: 'line', note: '', bucketNoun: 'week' });
ok(h1.indexOf('all 42 products') >= 0, 'H1 names the unselected scope', h1);
ok(h1.indexOf('total') >= 0, 'H1 says total', h1);
ok(h1.indexOf('13 weeks') >= 0, 'H1 bucket count', h1);
const h2 = pnlTrendSubtitle({ selectionActive: true, midCount: 1, bandCount: 1, buckets: 1,
                              from: 'a', to: 'b', mode: 'stacked', note: 'n', bucketNoun: 'week', extra: 'US' });
ok(h2.indexOf('1 product selected') >= 0, 'H2 singular product', h2);
ok(h2.indexOf('1 week') >= 0 && h2.indexOf('1 weeks') < 0, 'H2 singular bucket', h2);
ok(h2.indexOf('stacked') >= 0 && h2.indexOf('1 band') >= 0, 'H2 shape', h2);
ok(h2.indexOf('US') >= 0 && h2.indexOf('n') >= 0, 'H2 extra + note carried', h2);

// ═════════ I. degenerate inputs must not throw ══════════════════════════════
let threw = null;
try {
  pnlTrendSeries({ perProd: {}, buckets: [], mids: [], metricOf: metricSales, colors: COLORS, labelOf, mode: 'line', selectionActive: false });
  pnlTrendSeries({ perProd: {}, buckets: W, mids: ['ZZ'], metricOf: metricSales, colors: COLORS, labelOf, mode: 'stacked', selectionActive: true });
  pnlTrendSeries(Object.assign({}, base, { metricOf: () => undefined, mode: 'stacked', selectionActive: false }));
  pnlTrendSeries(Object.assign({}, base, { mids: ['A'], metricOf: metricSales, mode: 'stacked', selectionActive: true }));
} catch (e) { threw = e.message; }
ok(threw === null, 'I1 degenerate inputs do not throw', threw);
// I2 — more products than colors must keep cycling, not run off the end.
const I2 = pnlTrendSeries({ perProd: many, buckets: [W[0]], mids: manyMids, metricOf: metricSales,
                            colors: ['#a','#b'], labelOf, mode: 'stacked', selectionActive: true });
ok(I2.datasets.every(d => d.borderColor === '#a' || d.borderColor === '#b'), 'I2 colors cycle');

console.log('\n  v10.12: ' + pass + ' passed, ' + fail + ' failed');
if (fail) { failures.forEach(f => console.log('    FAIL ' + f)); process.exit(1); }
'''

harness = HARNESS.replace('__SLICES__', '\n\n'.join(SLICES))
tmpdir = tempfile.mkdtemp(prefix='v1012_')
jsp = os.path.join(tmpdir, 'test_v1012.js')
io.open(jsp, 'w', encoding='utf-8', newline='').write(harness)

print('=== v10.12 behaviour tests ===')
r = subprocess.run([os.environ.get('NODE', 'node'), jsp], capture_output=True, text=True)
sys.stdout.write(r.stdout)
sys.stderr.write(r.stderr)
if r.returncode != 0:
    sys.exit(r.returncode)

print('\n=== v10.12 static assertions ===')
sfail = []


def sok(cond, label):
    print(('  ok: ' if cond else '  FAIL: ') + label)
    if not cond:
        sfail.append(label)


# One engine, four consumers — not four copies.
for f in ('pnlTrendSeries', 'pnlTrendRender', 'pnlSlotAdd', 'pnlChartMode',
          'pnlInjectChartModeToggle', 'pnlTrendSubtitle'):
    # One regex, not count('function X(') + count('async function X(') —
    # the second string CONTAINS the first, so that double-counts an async fn.
    sok(len(re.findall(r'(?:async\s+)?function\s+%s\s*\(' % re.escape(f), js)) == 1,
        'exactly one %s definition' % f)
sok(js.count('pnlTrendSeries({') == 4, 'all four P&L pages call the shared series builder')
sok(js.count('pnlTrendRender({') == 4, 'all four P&L pages call the shared renderer')
sok(js.count('pnlInjectChartModeToggle(') == 5, 'toggle injected on all four pages (+1 definition)')

# Every page has a mode-toggle host and a canvas.
for pid in ('pnl', 'spnl', 'wmpnl', 'chpnl'):
    sok('id="%s-chart-mode-host"' % pid in src, '%s has a mode-toggle host' % pid)
    sok('id="%s-chart-canvas"' % pid in src, '%s has a chart canvas' % pid)

# THE behaviour change: no page may still hide its chart purely because
# nothing is selected.
for guard in ('if (!pnlSelectedMids || pnlSelectedMids.size === 0) {',
              'if (!shopifyPnlSelectedMids.size) {',
              'if (!walmartPnlSelectedMids.size) {'):
    sok(guard not in js, 'hide-when-nothing-selected guard removed: %r' % guard[:40])
for v in ('pnlVisibleMids', 'shopifyPnlVisibleMids', 'walmartPnlVisibleMids'):
    sok('(%s || [])' % v in js, '%s is the no-selection fallback' % v)

# Stacking contract.
sok("fill: mode === 'stacked' ? (i === 0 ? 'origin' : '-1') : false" in js,
    "stacked bands chain fills (origin then -1), not fill:true")
sok('stacked, ticks:' in js or 'x: { stacked' in js, 'axes receive the stacked flag')

# COGS must be accumulated as dollars on every page (a rate cannot be summed).
sok(js.count('// COGS as DOLLARS so summed slots stay correct') == 2,
    'Shopify + Walmart accumulate COGS dollars')
sok('slot.cogs        += (getActivePnlCogs(mid) || 0)' in js, 'Amazon accumulates COGS dollars')
sok("slot.cogs     += pu.cogs * (r.units || 0)" in js, 'Chewy accumulates COGS dollars')

# Chewy got a chart at all.
sok('async function updateChewyPnlChart()' in js, 'Chewy P&L has a trend chart')
sok('updateChewyPnlChart().catch(console.warn)' in js, 'Chewy chart renders with the Sales table')

# No dead code left from the cutover.
sok('legacy render below retained' not in js, 'no dead legacy render left behind')

# Provenance, NOT the version chip - see tests/README.md. Asserting the
# literal chip makes every PAST suite fail on the next release.
sok(src.count('v10.12 —') >= 1, "v10.12's own provenance markers survive")
for marker in ('v10.11 —', 'v10.10 —', 'v10.4 —'):
    sok(marker in src, 'earlier provenance marker preserved: %s' % marker.split(' ')[0])

print('\n  static: %d failed' % len(sfail))
if sfail:
    sys.exit(1)
print('\n  v10.12 ALL GREEN')
