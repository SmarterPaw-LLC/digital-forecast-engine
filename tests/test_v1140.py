#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.40 - the incomplete-reporting band on the Seasonality chart.

Jason, with a screenshot of the green actuals line falling off a cliff:
"i need that indicator on the trend line. chewy sales are now showing and
that's causing the slump."

Chewy ends 2026-09-28 while Shopify runs to 2026-11-02, so the last five weeks
of that line are missing a channel carrying 25-50% of the product's volume. It
reads as collapsing demand; it is a reporting lag.

  * A  the REAL salesLatestByChannelMap. It was only ever assigned inside
       updateSalesChart, so opening Seasonality first left the band silently
       undrawn - the v10.19 case, failing exactly where it is most needed.
  * B  the REAL plugin, with a recording canvas. B1 is the no-movement guard:
       absent bandEndWeek the band still runs to the plot edge, so the two
       Units Sold charts are byte-identical.
  * C  static: one new opt-in, the weeks array indexes 1:1 with the chart's
       labels, and the band stops at the last ACTUAL week rather than over
       the 17-week projection.
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
# A. The dataset-wide latest-reported map.
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, '_v1140_a.js'),
    'let salesLatestByChannel = {};\nlet salesData = {};\n'
    + fn('salesLatestByChannelMap') + '\n' + r"""
const out = {};
// Chewy's newest row is on SP-0999, NOT on the product being charted - which
// is the whole point of the map being dataset-wide.
salesData = {
  'SP-0124': [
    { channel: 'shopify', week_start: '2026-11-02', units_ordered: 4 },
    { channel: 'shopify', week_start: '2026-10-26', units_ordered: 106 },
    { channel: 'chewy',   week_start: '2026-09-28', units_ordered: 33 },
  ],
  'SP-0999': [
    { channel: 'chewy',   week_start: '2026-10-05', units_ordered: 11 },
    { channel: 'walmart', week_start: '2026-08-31', units_ordered: 2 },
    { channel: null,      week_start: '2026-11-02', units_ordered: 9 },   // no channel
    { channel: 'shopify', week_start: null,         units_ordered: 9 },   // no week
  ],
};
out.a1 = salesLatestByChannelMap();
out.a2_cachedSame = salesLatestByChannelMap() === out.a1 ? false : true;  // value-equal, see a2b
salesData['SP-0124'].push({ channel: 'shopify', week_start: '2027-01-04', units_ordered: 1 });
out.a2b_notRecomputed = salesLatestByChannelMap().shopify;   // still the cached answer

// a timestamped week_start must not break the string compare
salesLatestByChannel = {};
salesData = { X: [
  { channel: 'chewy', week_start: '2026-09-28T00:00:00+00:00' },
  { channel: 'chewy', week_start: '2026-08-31' },
] };
out.a3 = salesLatestByChannelMap();

// empty / absent salesData is not an answer, and must not throw
salesLatestByChannel = {};
salesData = {};
out.a4 = salesLatestByChannelMap();
salesLatestByChannel = {};
salesData = null;
out.a5 = salesLatestByChannelMap();
console.log(JSON.stringify(out));
""")

eq('A1 dataset-wide max per channel', A['a1'],
   {'shopify': '2026-11-02', 'chewy': '2026-10-05', 'walmart': '2026-08-31'})
ok('null' not in A['a1'] and None not in A['a1'],
   'A1b a row with no channel is skipped, not filed under null')
eq('A2 a second call does not recompute', A['a2b_notRecomputed'], '2026-11-02')
eq('A3 a timestamped week_start still compares as a date', A['a3'], {'chewy': '2026-09-28'})
eq('A4 an empty dataset yields an empty map, not a throw', A['a4'], {})
eq('A5 nor does a missing one', A['a5'], {})

# updateSalesChart must still own the authoritative sweep, or the two could
# answer differently depending on which ran first.
ok('salesLatestByChannel = latestByChannel;' in js,
   'A6 updateSalesChart still assigns the map from its own sweep')

# ---------------------------------------------------------------------------
# B. The band, drawn for real.
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, '_v1140_b.js'),
    'const SALES_CHANNELS = { shopify: { label: "Shopify DTC", color: "#06b6d4" },'
    ' chewy: { label: "Chewy", color: "#a855f7" } };\n'
    'let salesLatestByChannel = { shopify: "2026-11-02", chewy: "2026-09-28" };\n'
    + fn('salesCoverage') + '\n'
    + 'const salesFmtWk = (wk) => wk || "-";\n'
    + 'function salesHatchPattern() { return null; }\n'
    + 'function salesCovMissingAt(cov, wk) { return []; }\n'
    + const_obj('salesCoveragePlugin') + '\n' + r"""
const out = {};
// 10 history weeks then 4 projected ones, 10px apart, plot 0..140.
const weeks = [];
for (let i = 0; i < 14; i++) {
  const d = new Date(2026, 7, 31); d.setDate(d.getDate() + 7 * i);
  weeks.push(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`);
}
function mkChart() {
  const rects = [], lines = [];
  const ctx = {
    save(){}, restore(){}, beginPath(){ this._p = []; },
    rect(x,y,w,h){ rects.push([Math.round(x),Math.round(y),Math.round(w),Math.round(h)]); },
    fill(){}, moveTo(x,y){ this._m=[x,y]; }, lineTo(x,y){ lines.push([Math.round(this._m[0]),Math.round(x)]); },
    stroke(){}, setLineDash(){}, fillRect(){}, fillText(){}, measureText(t){ return { width: t.length * 5 }; },
    createPattern(){ return null; },
    set font(v){}, set textBaseline(v){}, set textAlign(v){},
    set fillStyle(v){}, set strokeStyle(v){}, set lineWidth(v){},
  };
  return { ctx, rects, lines,
    chartArea: { left: 0, right: 140, top: 0, bottom: 50 },
    scales: { x: { getPixelForValue: (i) => i * 10 } } };
}
function draw(cov) {
  const c = mkChart();
  salesCoveragePlugin.afterDatasetsDraw(c, null, { cov });
  return { rects: c.rects, lines: c.lines };
}

const base = salesCoverage(weeks, ['shopify', 'chewy'], salesLatestByChannel);
out.b0_firstGap = base.firstGapWeek;
out.b0_stale = base.channels.filter(c => c.firstGap).map(c => c.ch);

// B1 NO bandEndWeek -> runs to the plot edge, exactly as Units Sold does
out.b1 = draw({ ...base });
// B2 bandEndWeek set -> stops midway after that week
out.b2 = draw({ ...base, bandEndWeek: weeks[9] });
// B3 an UNKNOWN bandEndWeek falls back to the plot edge rather than vanishing
out.b3 = draw({ ...base, bandEndWeek: '1999-01-04' });
// B4 a band that would end before it starts draws nothing at all
out.b4 = draw({ ...base, bandEndWeek: weeks[0] });
// B5 no gap at all -> nothing drawn
salesLatestByChannel = { shopify: '2027-01-01', chewy: '2027-01-01' };
out.b5 = draw(salesCoverage(weeks, ['shopify', 'chewy'], salesLatestByChannel));
salesLatestByChannel = { shopify: '2026-11-02', chewy: '2026-09-28' };
console.log(JSON.stringify(out));
""")

eq('B0 the gap opens the week after Chewy stops', B['b0_firstGap'], '2026-10-05')
eq('B0b every channel has unreported weeks on a chart that projects forward',
   B['b0_stale'], ['shopify', 'chewy'])
eq('B0c but only Chewy is LAGGING, so only Chewy gets a boundary line',
   B['b2']['lines'], [[45, 45]])
eq('B0d unbounded, both boundaries draw - Units Sold unchanged',
   len(B['b1']['lines']), 2)
ok(len(B['b1']['rects']) >= 1, 'B1 a band is drawn with no right edge set')
eq('B1b THE NO-MOVEMENT GUARD: it still runs to the plot edge',
   [B['b1']['rects'][0][0], B['b1']['rects'][0][0] + B['b1']['rects'][0][2]], [45, 140])
eq('B2 bandEndWeek stops it mid-chart',
   [B['b2']['rects'][0][0], B['b2']['rects'][0][0] + B['b2']['rects'][0][2]], [45, 95])
ok(B['b2']['rects'][0][2] < B['b1']['rects'][0][2],
   'B2b which is narrower than the unbounded band')
eq('B3 an unknown right edge falls back to the plot edge, not to nothing',
   [B['b3']['rects'][0][0], B['b3']['rects'][0][0] + B['b3']['rects'][0][2]], [45, 140])
eq('B4 a band ending before it starts draws nothing', B['b4']['rects'], [])
eq('B5 and a fully-reported chart draws nothing', B['b5']['rects'], [])

# ---------------------------------------------------------------------------
# C. Static wiring.
# ---------------------------------------------------------------------------
def nocomment(t):
    t = re.sub(r'/\*[\s\S]*?\*/', '', t)
    return re.sub(r'(?m)^\s*//.*$', '', t)

code = nocomment(js)
eq('C1 exactly one new opt-in', code.count('plugins: [salesCoveragePlugin]'), 1)
eq('C1b the two Units Sold opt-ins are untouched',
   code.count('plugins: [salesCoveragePlugin, CHART_HTML_LEGEND]'), 2)

_fit = fn('seaRenderFitChart')
_fitcode = nocomment(_fit)
ok('keys.concat(futureDates.map(_seaIso))' in _fitcode,
   'C2 the weeks array is history + projection, indexing 1:1 with `labels`')
ok('const labels = [...keys.map(k => fmt(new Date(k))), ...futureDates.map(fmt)];' in _fitcode,
   'C2b which is exactly how `labels` is built - the pairing this depends on')
ok('_seaCov.bandEndWeek = keys.length ? keys[keys.length - 1] : null;' in _fitcode,
   'C3 the band stops at the last ACTUAL week')
ok('salesLatestByChannelMap()' in _fitcode,
   'C4 and reads the map through the function, not the bare global')
ok('spCoverage: { cov: _seaCov }' in _fitcode, 'C5 the cov reaches the plugin')

_plug = const_obj('salesCoveragePlugin')
ok('bandEndWeek' in nocomment(_plug), 'C6 the plugin honours a right edge')
ok('bandEnd' in nocomment(_plug) and 'ca.right' in nocomment(_plug),
   'C6b defaulting to the plot edge')

eq('C7 version chip', s.count('>v11.43 \u00b7 2026-11-02<'), 1)
eq('C7b exactly one chip', len(re.findall(r'>v11\.\d+ \u00b7 [\d-]+<', s)), 1)

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
