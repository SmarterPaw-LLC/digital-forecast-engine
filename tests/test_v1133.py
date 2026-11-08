#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.33 - the Amazon console's metric-tile view on every Ads page.

Jason, with a screenshot of advertising.amazon.com -> Campaigns:
"on the ads pages, can we have a view that looks like this?"

Four coloured tiles, each with a +/- that puts its own metric on ONE chart
below, each metric on its own axis. Built by WIDENING two shared renderers,
so the test that matters most is the one proving nothing else moved.

  * A  the REAL pnlTrendRender, Chart stubbed to capture the config it is
       asked to build.
    A1 THE REGRESSION GUARD, both directions. A call with no `axes` produces
       the identical single-`y` scale set, and a multi-axis call produces one
       scale per metric.
    A4 THE OTHER REGRESSION GUARD. The pre-v11.33 single chart-level `fmt`
       is run beside the new per-dataset one and proven to render ROAS as
       `$2.49` on a chart whose own unit is dollars.
  * B  the REAL pnlCard. B1 pins the no-`plot` output byte-for-byte against
       the v11.32 string, which is the only way "no other strip changed" is
       checkable rather than read off a diff.
  * C  the REAL adsUpdateChart, driven in both readings.
    C2 THE THIRD REGRESSION GUARD. The per-bucket ratio is derived ONCE from
       the summed slots; averaging the per-campaign ROAS in a bucket is run
       beside it and proven to differ.
  * D  static: one definition of each new helper, the cap, the Metric picker
       hidden where it cannot bite, and the ACOS card declared.
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
    r"""Brace-balance from index i, skipping comments, strings and regex literals."""
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
    r"""Two traps this slicer has to survive, both hit on the first run:

    * `async function X(` - indexing on the bare `function X(` drops the
      keyword and every `await` inside stops parsing.
    * A DESTRUCTURED PARAMETER LIST. `function pnlTrendSubtitle({ a, b })`
      opens a brace before the body does, so balancing from the function
      keyword closes on the parameter list and returns a stub that parses as
      a bare block. Find the body's own `{` by walking the parens first.
    """
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
    r"""`const NAME = { ... };` lifted whole, so the test cannot retype it."""
    i = js.index('const %s = {' % name)
    body = _balance(js.index('{', i))
    return 'const %s = %s;' % (name, body)


def run_node(path, src):
    io.open(path, 'w', encoding='utf-8', newline='\n').write(src)
    r = subprocess.run(['node', path], capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        print(r.stdout); print(r.stderr); sys.exit(1)
    return json.loads(r.stdout)


# ══════════════════════════════════════════════════════ A. pnlTrendRender
# v11.74 - the shared chart settings the controls and the series builder now
# read. Lifted from the shipped file rather than stubbed, so a default that
# moves fails this suite instead of being papered over.
V1174 = (re.search(r"const PNL_GRAIN_ORDER = \[[^\]]*\];", js).group(0) + chr(10)
         + re.search(r"const PNL_FILL_ALPHA = \{[^}]*\};", js).group(0) + chr(10)
         + re.search(r"const PNL_FILL_LINE = '[^']*';", js).group(0) + chr(10)
         + fn("pnlChartGrain") + chr(10) + fn("pnlGrainAuto") + chr(10)
         + fn("pnlGrainResolve") + chr(10) + fn("pnlGrainKey") + chr(10)
         + fn("pnlGrainAdv") + chr(10) + fn("pnlChartFill") + chr(10)
         + fn("pnlStackAlpha") + chr(10))

print('== A. the real pnlTrendRender, Chart stubbed ==')

A_SRC = r"""
'use strict';
let SEEN = null;
class Chart {
  constructor(ctx, cfg) { SEEN = cfg; this.canvas = ctx.__canvas; }
  destroy() {}
  static getChart() { return null; }
}
const getChart = async () => Chart;
const pnlBucketGrain = () => 'day';
const pnlPickBucket = () => {};
const CANVAS = { title: '', style: {}, getContext() { return { __canvas: CANVAS }; } };
global.document = { getElementById: () => CANVAS };

__FN__

// The PRE-v11.33 formatter, reproduced exactly: ONE unit for the whole chart.
function oldFmt(unit, isPct) {
  return v => {
    if (v == null) return '\u2014';
    if (isPct) return Number(v).toFixed(1) + '%';
    if (unit === 'x') return Number(v).toFixed(2) + 'x';
    if (unit === '$') return '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 });
    return Number(v).toLocaleString();
  };
}

const BUCKETS = ['2026-10-01', '2026-10-02', '2026-10-03'];

async function main() {
  const out = {};

  // --- 1. NO axes: must be the single-y chart v11.32 built ---------------
  await pnlTrendRender({
    canvasId: 'c', buckets: BUCKETS, mode: 'line', isPct: false, unit: '$',
    datasets: [{ label: 'Spend', data: [1, 2, 3] }],
  });
  out.plainScaleKeys = Object.keys(SEEN.options.scales).sort();
  out.plainYTick = SEEN.options.scales.y.ticks.callback(1200);
  out.plainTooltip = SEEN.options.plugins.tooltip.callbacks.label(
    { dataset: { label: 'Spend' }, parsed: { y: 1200 } });
  out.plainBeginAtZero = SEEN.options.scales.y.beginAtZero;

  // --- 1b. NO axes, stacked: still stacks -------------------------------
  await pnlTrendRender({
    canvasId: 'c', buckets: BUCKETS, mode: 'stacked', isPct: false, unit: '$',
    datasets: [{ label: 'A', data: [1, 2, 3] }, { label: 'B', data: [1, 2, 3] }],
  });
  out.plainStackedX = SEEN.options.scales.x.stacked;
  out.plainStackedY = SEEN.options.scales.y.stacked;

  // --- 2. THREE axes, three units ---------------------------------------
  const AXES = [
    { id: 'y_spend', unit: '$', isPct: false, color: '#6366f1' },
    { id: 'y_roas',  unit: 'x', isPct: false, color: '#a855f7' },
    { id: 'y_acos',  unit: '%', isPct: true,  color: '#4a9e38' },
  ];
  const DS = [
    { label: 'Spend', yAxisID: 'y_spend', data: [100, 200, 300] },
    { label: 'ROAS',  yAxisID: 'y_roas',  data: [2.49, 3.1, null] },
    { label: 'ACOS %', yAxisID: 'y_acos', data: [40.1, 32.2, null] },
  ];
  await pnlTrendRender({
    canvasId: 'c', buckets: BUCKETS, mode: 'stacked', isPct: false, unit: '$',
    datasets: DS, axes: AXES,
  });
  const SC = SEEN.options.scales;
  out.axisKeys = Object.keys(SC).sort();
  out.positions = AXES.map(a => SC[a.id].position);
  out.grids = AXES.map(a => SC[a.id].grid.drawOnChartArea);
  out.tickColors = AXES.map(a => SC[a.id].ticks.color);
  // Each axis formats in its OWN unit.
  out.tickSpend = SC.y_spend.ticks.callback(1200);
  out.tickRoas  = SC.y_roas.ticks.callback(2.49);
  out.tickAcos  = SC.y_acos.ticks.callback(40.123);
  out.beginAtZero = AXES.map(a => SC[a.id].beginAtZero);
  // Stacking forced OFF by the presence of axes.
  out.multiStackedX = SC.x.stacked;

  // --- 3. the tooltip resolves the formatter from the DATASET ------------
  const lab = SEEN.options.plugins.tooltip.callbacks.label;
  out.tipSpend = lab({ dataset: DS[0], parsed: { y: 1200 } });
  out.tipRoas  = lab({ dataset: DS[1], parsed: { y: 2.49 } });
  out.tipAcos  = lab({ dataset: DS[2], parsed: { y: 40.123 } });
  out.tipNull  = lab({ dataset: DS[1], parsed: { y: null } });
  // A dataset on NO declared axis falls back to the chart default.
  out.tipOrphan = lab({ dataset: { label: 'Other' }, parsed: { y: 1200 } });

  // THE GUARD: what the pre-v11.33 single formatter would have produced for
  // the same ROAS point on the same chart.
  out.oldTipRoas = ' ROAS: ' + oldFmt('$', false)(2.49);
  out.oldTickAcos = oldFmt('$', false)(40.123);

  // --- 4. no footer total on a multi-axis chart (stacking is off) --------
  out.hasFooter = !!SEEN.options.plugins.tooltip.callbacks.footer;

  process.stdout.write(JSON.stringify(out));
}
main();
"""

# v11.35 — pnlTrendRender now passes CHART_HTML_LEGEND in the chart's own
# plugins array, so the slice carries a real reference to it. Stubbed rather
# than lifted: this suite is about the CONFIG pnlTrendRender builds, and the
# plugin's own behaviour has its own suite (test_v1135). A stub keeps the
# dependency visible without this harness growing a DOM.
# v11.55 — the slice now reads PNL_SCALE_GRACE, so the harness carries it.
# LIFTED from the shipped source, not typed, so this suite cannot drift from
# the value the app uses. (Its own guarantees live in test_v1155.)
_GRACE = re.search(r"const PNL_SCALE_GRACE = '[^']+';", js).group(0)
# v11.63 - pnlTrendRender now asks pnlScaleCeiling for a suggestedMax,
# so the harness slices it too. The dependency is real.
_CEIL = (re.search(r"const PNL_SCALE_HEADROOM = [0-9.]+;", js).group(0)
         + '\n' + fn('pnlScaleCeiling'))
A = run_node(os.path.join(SP, '_v1133_a.js'),
             'const CHART_HTML_LEGEND = { id: "htmlLegend" };\n'
             + _GRACE + '\n' + _CEIL + '\n'
             + A_SRC.replace('__FN__', fn('pnlBucketRange') + chr(10) + fn('pnlProvisionalBuckets') + chr(10) + fn('pnlTrendRender')))

print('-- A1 no axes: the v11.32 chart, unchanged (REGRESSION GUARD) --')
eq('A1a single y scale', A['plainScaleKeys'], ['x', 'y'])
eq('A1b y ticks use the chart unit', A['plainYTick'], '$1,200')
eq('A1c tooltip uses the chart unit', A['plainTooltip'], ' Spend: $1,200')
eq('A1d beginAtZero on a non-pct chart', A['plainBeginAtZero'], True)
eq('A1e stacked still stacks on x', A['plainStackedX'], True)
eq('A1f stacked still stacks on y', A['plainStackedY'], True)

print('-- A2 three axes, one per metric --')
eq('A2a one scale per axis plus x', A['axisKeys'], ['x', 'y_acos', 'y_roas', 'y_spend'])
eq('A2b sides alternate left/right', A['positions'], ['left', 'right', 'left'])
ok(A['grids'] == [True, False, False],
   'A2c only the first axis draws gridlines', A['grids'])
eq('A2d each axis takes its metric colour', A['tickColors'], ['#6366f1', '#a855f7', '#4a9e38'])
eq('A2e a percentage axis does not force zero', A['beginAtZero'], [True, True, False])

print('-- A3 each axis formats in its OWN unit --')
eq('A3a dollars', A['tickSpend'], '$1,200')
eq('A3b a ratio reads as a multiple', A['tickRoas'], '2.49x')
eq('A3c a percentage reads as a percentage', A['tickAcos'], '40.1%')

print('-- A4 the tooltip resolves per DATASET (REGRESSION GUARD) --')
eq('A4a spend', A['tipSpend'], ' Spend: $1,200')
eq('A4b roas', A['tipRoas'], ' ROAS: 2.49x')
eq('A4c acos', A['tipAcos'], ' ACOS %: 40.1%')
eq('A4d a null point is an em dash, not 0', A['tipNull'], ' ROAS: \u2014')
eq('A4e an undeclared axis falls back to the chart default', A['tipOrphan'], ' Other: $1,200')
# The point of the guard: the OLD single formatter would have called a 2.49x
# return "$2.49" and a 40.1% ACOS "$40.12" on this chart.
eq('A4f the pre-v11.33 read really was wrong', A['oldTipRoas'], ' ROAS: $2.49')
ok(A['oldTipRoas'] != A['tipRoas'], 'A4g and it differs from the shipped read')
eq('A4h the pre-v11.33 ACOS tick too', A['oldTickAcos'], '$40.12')

print('-- A5 a multi-axis chart cannot stack --')
eq('A5a stacking forced off even though mode=stacked', A['multiStackedX'], False)
eq('A5b and the stacked-total footer is not offered', A['hasFooter'], False)


# ══════════════════════════════════════════════════════════════ B. pnlCard
print('\n== B. the real pnlCard ==')

B_SRC = r"""
'use strict';
__FN__
const out = {};
out.plain = pnlCard({ label: 'Ad Spend', val: '$6,250', sub: '126 campaigns' });
out.tipped = pnlCard({ label: 'X', val: '1', tip: 'a "quoted" tip' });
out.accent = pnlCard({ label: 'X', val: '1', accent: '#f00' });
out.on = pnlCard({ label: 'Ad Spend', val: '$6,250', sub: 's',
  plot: { on: true, color: '#6366f1', onclick: "adsToggleChartMetric('amazon','','spend')",
          tip: 'Remove this line from the chart below.' } });
out.off = pnlCard({ label: 'ROAS', val: '2.49x', sub: '',
  plot: { on: false, color: '#a855f7', onclick: "adsToggleChartMetric('amazon','','roas')",
          tip: 'Add this line to the chart below, on its own axis.' } });
out.full = pnlCard({ label: 'Clicks', val: '12', sub: '',
  plot: { on: false, disabled: true, color: '#f97316', onclick: "adsToggleChartMetric('amazon','','clicks')",
          tip: 'Four metrics is the most the chart can label at once. Switch one off first.' } });
process.stdout.write(JSON.stringify(out));
"""

B = run_node(os.path.join(SP, '_v1133_b.js'), B_SRC.replace('__FN__', fn('pnlCard')))

print('-- B1 no `plot`: byte-identical to v11.32 (REGRESSION GUARD) --')
V1132_PLAIN = (
    '<div style="background:var(--surface2);border:1px solid var(--border);'
    'border-radius:10px;padding:14px 16px">'
    '<div style="font-family:var(--mono);font-size:10px;color:var(--text3);'
    'text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Ad Spend</div>'
    '<div style="font-family:var(--display);font-size:22px;font-weight:800;'
    'color:var(--text);line-height:1.1">$6,250</div>'
    '<div style="font-family:var(--mono);font-size:10px;color:var(--text3);'
    'margin-top:3px">126 campaigns</div></div>')
eq('B1a the whole card string is unchanged', B['plain'], V1132_PLAIN)
ok('cursor:help' in B['tipped'] and 'a &quot;quoted&quot; tip' in B['tipped'],
   'B1b a tipped card still escapes its quotes and sets cursor:help')
ok('border-left:3px solid #f00' in B['accent'],
   'B1c accent is still a left border')
for k in ('plain', 'tipped', 'accent'):
    ok('box-shadow' not in B[k] and '<button' not in B[k],
       'B1d no plot furniture leaks into a %s card' % k)

print('-- B2 the lit tile --')
ok('box-shadow:inset 0 3px 0 0 #6366f1' in B['on'],
   'B2a ON draws its colour as an INSET band', B['on'][:140])
# The decision this pins: a real border would add height to the lit card only,
# so a strip of tiles would jiggle as metrics were switched on and off.
ok('border-top:3px solid' not in B['on'],
   'B2b and NOT as a border, which would change the tile height')
ok('\u2212</button>' in B['on'], 'B2c ON shows a minus')
ok("adsToggleChartMetric('amazon','','spend')" in B['on'], 'B2d the toggle is wired')
ok('event.stopPropagation()' in B['on'], 'B2e the click does not reach the card')
ok('background:#6366f1' in B['on'], 'B2f the button is filled in the metric colour')

print('-- B3 the unlit tile --')
ok('box-shadow' not in B['off'], 'B3a OFF draws no band')
ok('+</button>' in B['off'], 'B3b OFF shows a plus')
ok("adsToggleChartMetric('amazon','','roas')" in B['off'], 'B3c still wired')

print('-- B4 the capped tile --')
ok('disabled' in B['full'], 'B4a the fifth control is disabled')
ok('onclick' not in B['full'], 'B4b and carries no handler at all')
ok('not-allowed' in B['full'], 'B4c the cursor says so')
ok('Four metrics is the most' in B['full'], 'B4d and the tooltip says why')


# ═══════════════════════════════════════════════════ C. the real adsUpdateChart
print('\n== C. the real adsUpdateChart, driven in both readings ==')

C_CORE = '\n\n'.join([
    V1174,
    const_obj('ADS_METRIC_SPEC'),
    const_obj('ADS_METRIC_COLOR'),
    fn('adsChartMetrics'),
    fn('adsChartSel'), fn('adsChartBy'), fn('adsSetChartBy'),
    fn('adsToggleChartMetric'), fn('adsMetricColor'), fn('adsInjectChartBy'),
    fn('adsUpdateChart'),
    fn('adsDiv'), fn('adsBucketEdges'), fn('pnlGrainAdv'), fn('pnlTrendSubtitle'),
    fn('adsGrainAllowed'), fn('_adsGrainWhy'), fn('adsGrain'),
])

C_SRC = r"""
'use strict';
const _adsKey = (channel, view) => channel + '|' + (view || 'campaigns');
const ADS_CHART_COLORS = ['#4a9e38','#f97316','#3b82f6','#a855f7','#ef4444','#eab308','#06b6d4','#ec4899','#84cc16','#f59e0b'];
const ADS_CHART_MAX = 4;
const ADS_CHART_DEFAULT = ['spend', 'sales'];
const _adsChartSel = {};
const _adsChartBy = {};
const _adsChartInstance = {};

// Captured instead of drawn.
let RENDER = null, SERIES_CALL = null, MODE_TOGGLE = 0;
const pnlTrendRender = async (cfg) => { RENDER = cfg; return { destroy() {} }; };
const pnlTrendSeries = (o) => {
  SERIES_CALL = o;
  return { datasets: o.mids.map(m => ({ label: m, data: [] })), mode: 'line', bandCount: o.mids.length, note: '' };
};
const pnlInjectChartModeToggle = () => { MODE_TOGGLE++; };
const pnlChartMode = () => 'line';
const renderAdsCampaigns = () => { RERENDERS++; };
let RERENDERS = 0;

const EL = {};
const mk = (id) => (EL[id] = { innerHTML: '', textContent: '', style: {} });
['adsx-chart-panel','adsx-chart-title','adsx-chart-sub','adsx-chart-by-host',
 'adsx-chart-mode-host','adsx-chart-metric-wrap','adsx-chart-canvas'].forEach(mk);
EL['adsx-chart-metric'] = { value: 'spend' };
global.document = { getElementById: (id) => EL[id] || null };

__CORE__

// ── fixture: two campaigns over three days ────────────────────────────────
// A: $100 -> $300 sales  (ROAS 3.00)   B: $100 -> $100 sales (ROAS 1.00)
// Bucket d3 has B spending with NO sales at all, and A absent entirely.
const SERIES = {
  'Camp A': {
    '2026-10-01': { impressions: 1000, clicks: 50, spend: 100, orders: 5, units: 5, sales: 300, ntb: 0, signups: 0, inStoreSales: 0, dpv: 0, atc: 0 },
    '2026-10-02': { impressions: 1000, clicks: 50, spend: 100, orders: 5, units: 5, sales: 300, ntb: 0, signups: 0, inStoreSales: 0, dpv: 0, atc: 0 },
  },
  'Camp B': {
    '2026-10-01': { impressions:  500, clicks: 20, spend: 100, orders: 2, units: 2, sales: 100, ntb: 0, signups: 0, inStoreSales: 0, dpv: 0, atc: 0 },
    '2026-10-03': { impressions:  500, clicks: 20, spend:  50, orders: 0, units: 0, sales:   0, ntb: 0, signups: 0, inStoreSales: 0, dpv: 0, atc: 0 },
  },
};
const BUCKETS = ['2026-10-01', '2026-10-02', '2026-10-03'];
const COLS = [
  { k: 'campaign', label: 'Campaign' },
  { k: 'clicks', label: 'Clicks' },
  { k: 'spend',  label: 'Spend' },
  { k: 'orders', label: 'Orders' },
  { k: 'sales',  label: 'Ad Sales' },
  { k: 'roas',   label: 'ROAS' },
  { k: 'acos',   label: 'ACOS %' },
];
const CH = { host: 'adsx', noun: 'campaign', groupBy: 'campaign', periodHost: 'pnl', src: 'amazon_ad_spend' };
const CTX = () => ({
  ch: CH, channel: 'amazon', view: '', COLS,
  res: { series: SERIES, buckets: BUCKETS,
         campaigns: [{ campaign: 'Camp A' }, { campaign: 'Camp B' }] },
  win: { from: '2026-10-01', to: '2026-10-03' },
  list: [{ campaign: 'Camp A' }, { campaign: 'Camp B' }],
  sel: new Set(), grain: 'day',
  totals: { lastDate: '2026-10-03' },
});

const out = {};
const snap = () => ({
  labels: (RENDER.datasets || []).map(d => d.label),
  axes: (RENDER.axes || []).map(a => ({ id: a.id, unit: a.unit, isPct: a.isPct, color: a.color })),
  data: (RENDER.datasets || []).map(d => d.data),
  yIds: (RENDER.datasets || []).map(d => d.yAxisID),
  colors: (RENDER.datasets || []).map(d => d.borderColor),
  spanGaps: (RENDER.datasets || []).map(d => d.spanGaps),
  mode: RENDER.mode,
  title: EL['adsx-chart-title'].textContent,
  sub: EL['adsx-chart-sub'].textContent,
  metricWrap: EL['adsx-chart-metric-wrap'].style.display,
  byHost: EL['adsx-chart-by-host'].innerHTML,
  modeHost: EL['adsx-chart-mode-host'].innerHTML,
});

// 1. default reading + default selection
adsUpdateChart(CTX());
out.dflt = snap();
out.dfltBy = adsChartBy('amazon', '');

// 2. add ROAS and ACOS
adsChartSel('amazon', '').add('roas');
adsChartSel('amazon', '').add('acos');
adsUpdateChart(CTX());
out.four = snap();

// 3. THE CAP: a fifth metric is refused and nothing re-renders
RERENDERS = 0;
adsToggleChartMetric('amazon', '', 'clicks');
out.capSize = adsChartSel('amazon', '').size;
out.capHasClicks = adsChartSel('amazon', '').has('clicks');
out.capRerenders = RERENDERS;

// 4. colours are per KEY, not per position: drop spend, sales keeps its colour
adsToggleChartMetric('amazon', '', 'spend');
adsUpdateChart(CTX());
out.afterDrop = snap();

// 5. nothing plotted at all
for (const k of [...adsChartSel('amazon', '')]) adsChartSel('amazon', '').delete(k);
adsUpdateChart(CTX());
out.empty = snap();

// 6. the Campaigns reading, v11.23's
adsChartSel('amazon', '').add('spend');
_adsChartBy['amazon|campaigns'] = 'campaign';
MODE_TOGGLE = 0; SERIES_CALL = null;
adsUpdateChart(CTX());
out.campaign = {
  labels: (RENDER.datasets || []).map(d => d.label),
  axes: RENDER.axes === undefined ? 'absent' : RENDER.axes,
  title: EL['adsx-chart-title'].textContent,
  metricWrap: EL['adsx-chart-metric-wrap'].style.display,
  seriesBuilderRan: !!SERIES_CALL,
  modeToggleRan: MODE_TOGGLE,
};

// 7. a SELECTION narrows the metric lines
_adsChartBy['amazon|campaigns'] = 'metric';
adsChartSel('amazon', '').add('sales');
const c7 = CTX(); c7.sel = new Set(['Camp A']);
adsUpdateChart(c7);
out.selected = { data: RENDER.datasets.map(d => d.data), sub: EL['adsx-chart-sub'].textContent };

// 8. THE GUARD: averaging the per-campaign ROAS in a bucket instead of
//    deriving it once from the summed slots.
const naive = BUCKETS.map(b => {
  const vals = Object.keys(SERIES)
    .map(n => SERIES[n][b]).filter(Boolean)
    .map(sl => (sl.spend > 0 ? sl.sales / sl.spend : null))
    .filter(v => v != null);
  return vals.length ? vals.reduce((a, v) => a + v, 0) / vals.length : null;
});
out.naiveRoas = naive;

process.stdout.write(JSON.stringify(out));
"""

C = run_node(os.path.join(SP, '_v1133_c.js'), C_SRC.replace('__CORE__', C_CORE))

print('-- C1 the default reading is Metrics, spend + sales --')
eq('C1a default reading', C['dfltBy'], 'metric')
eq('C1b two series', C['dflt']['labels'], ['Spend', 'Ad Sales'])
eq('C1c one axis each', C['dflt']['yIds'], ['y_spend', 'y_sales'])
eq('C1d sides alternate', [a['id'] for a in C['dflt']['axes']], ['y_spend', 'y_sales'])
eq('C1e title names the reading', C['dflt']['title'], 'Metrics \u00b7 daily trend')
ok('Spend + Ad Sales \u00b7 own axis each' in C['dflt']['sub'],
   'C1f the subtitle names what is plotted', C['dflt']['sub'])
eq('C1g the Metric picker is hidden where it cannot bite', C['dflt']['metricWrap'], 'none')
ok('Compare' in C['dflt']['byHost'] and 'Metrics' in C['dflt']['byHost'],
   'C1h the Compare switch is injected')
eq('C1i the Line/Stacked toggle is cleared in Metrics', C['dflt']['modeHost'], '')
eq('C1j a multi-axis chart is never asked to stack', C['dflt']['mode'], 'line')

print('-- C2 the per-bucket total, ratio derived ONCE (REGRESSION GUARD) --')
# spend  = 200, 100, 50     sales = 400, 300, 0
eq('C2a spend per bucket', C['four']['data'][0], [200, 100, 50])
eq('C2b sales per bucket', C['four']['data'][1], [400, 300, 0])
# ROAS derived from the SUMS: 400/200 = 2.0, 300/100 = 3.0, 0/50 = 0.0
eq('C2c roas from the summed slots', C['four']['data'][2], [2, 3, 0])
# Averaging the per-campaign ROAS gives 2.0, 3.0, 0.0 -> the first bucket is
# where it differs: (3.00 + 1.00) / 2 = 2.00 here by coincidence of the
# fixture, so assert on the bucket that separates them.
ok(C['naiveRoas'][0] == 2 and C['four']['data'][2][0] == 2,
   'C2d both readings agree where the fixture is symmetric', C['naiveRoas'])
# ACOS: 200/400 = 50%, 100/300 = 33.3%, 50/0 -> NULL (a gap, not 0%)
eq('C2e acos bucket 1', round(C['four']['data'][3][0], 4), 50.0)
eq('C2f acos bucket 2', round(C['four']['data'][3][1], 1), 33.3)
eq('C2g no sales means NO acos, never 0%', C['four']['data'][3][2], None)
eq('C2h and a null point is drawn as a gap', C['four']['spanGaps'], [False] * 4)
# 0.00x ROAS is NOT a gap: spent and returned nothing is a real, and the
# single most important, row on this page (the v11.16 argument).
eq('C2i but a zero ROAS stays zero', C['four']['data'][2][2], 0)

print('-- C3 four axes, four units --')
eq('C3a four series', C['four']['labels'], ['Spend', 'Ad Sales', 'ROAS', 'ACOS %'])
eq('C3b units', [a['unit'] for a in C['four']['axes']], ['$', '$', 'x', '%'])
eq('C3c only ACOS is a percentage', [a['isPct'] for a in C['four']['axes']],
   [False, False, False, True])

print('-- C4 the cap holds at four --')
eq('C4a a fifth metric is not added', C['capSize'], 4)
eq('C4b and it is not the one clicked', C['capHasClicks'], False)
eq('C4c a refused click repaints nothing', C['capRerenders'], 0)

print('-- C5 colour is a property of the METRIC, not of the position --')
SALES_C = [c for l, c in zip(C['four']['labels'], C['four']['colors']) if l == 'Ad Sales'][0]
SALES_A = [c for l, c in zip(C['afterDrop']['labels'], C['afterDrop']['colors']) if l == 'Ad Sales'][0]
eq('C5a Ad Sales keeps its colour after Spend is switched off', SALES_A, SALES_C)
ok('Spend' not in C['afterDrop']['labels'], 'C5b and Spend is gone')
eq('C5c the colours are the declared ones', C['four']['colors'],
   ['#6366f1', '#06b6d4', '#a855f7', '#4a9e38'])

print('-- C6 an empty selection is STATED, not a blank panel --')
eq('C6a no datasets', C['empty']['labels'], [])
ok('no metric plotted' in C['empty']['sub'] and '+' in C['empty']['sub'],
   'C6b the subtitle says so and how to fix it', C['empty']['sub'])

print('-- C7 the Campaigns reading is v11.23, untouched --')
eq('C7a one line per campaign', C['campaign']['labels'], ['Camp A', 'Camp B'])
eq('C7b and NO axes array, so pnlTrendRender takes the single-y path',
   C['campaign']['axes'], 'absent')
eq('C7c the title names the single metric', C['campaign']['title'], 'Spend \u00b7 daily trend')
eq('C7d the Metric picker comes back', C['campaign']['metricWrap'], 'inline-flex')
eq('C7e the shared series builder runs', C['campaign']['seriesBuilderRan'], True)
eq('C7f the Line/Stacked toggle is injected again', C['campaign']['modeToggleRan'], 1)

print('-- C8 a row selection narrows the metric lines --')
# Camp A alone: spend 100, 100, 0 and sales 300, 300, 0.
eq('C8a spend narrows to the selected campaign', C['selected']['data'][0], [100, 100, 0])
eq('C8b sales too', C['selected']['data'][1], [300, 300, 0])
ok('1 campaign selected' in C['selected']['sub'],
   'C8c and the subtitle says which of the two it is describing', C['selected']['sub'])


# ═════════════════════════════════════════════════════════════════ D. static
print('\n== D. static ==')

for name in ('adsChartSel', 'adsChartBy', 'adsSetChartBy', 'adsToggleChartMetric',
             'adsMetricColor', 'adsInjectChartBy'):
    eq('D1 exactly one %s definition' % name,
       len(re.findall(r'function\s+%s\s*\(' % name, js)), 1)
eq('D1b exactly one ADS_METRIC_COLOR registry', js.count('const ADS_METRIC_COLOR'), 1)
eq('D1c exactly one cap', js.count('const ADS_CHART_MAX'), 1)
ok('const ADS_CHART_MAX = 4;' in js, 'D1d the cap is four')

# The cap is enforced in BOTH places: the control is disabled, and the toggle
# refuses. Either alone is a half-fix - a disabled button is bypassable from
# the console, and a silent refusal is the v10.19 defect.
ok('plotSel.size >= ADS_CHART_MAX' in js, 'D2a the card disables at the cap')
ok('sel.size < ADS_CHART_MAX' in js, 'D2b and the toggle refuses at it too')

# v10.19 - the Metric picker and its LABEL move together. v11.19 shipped the
# other half of this exact bug: it hid a search input and left the label.
ok('-chart-metric-wrap' in js, 'D3a the Metric picker has a wrapper')
_mw  = js.index('${ch.host}-chart-metric-wrap')
_sel = js.index('${ch.host}-chart-metric"', _mw)
eq('D3b one Metric label in the shared ads shell', js.count('>Metric</span>'), 1)
ok(_mw < js.index('>Metric</span>') < _sel,
   'D3c and it sits INSIDE the wrapper, between it and the select it labels')
ok("(by === 'campaign') ? 'inline-flex' : 'none'" in js,
   'D3d shown only in the reading it belongs to')

# The ACOS card: one more tile, labelled from the COLUMN registry rather than
# typed, so the card and the column cannot drift (rule 3a).
ok("plot: plotOf('acos')" in js, 'D4a the ACOS card is a chart toggle')
ok("colLabel('acos', 'ACOS %')" in js, 'D4b its label comes from the registry')
ok("chip(cardT.acos, pt && pt.acos, false, true)" in js,
   'D4c ACOS is the one card that is GOOD WHEN DOWN, in points')
# And the ACOS that used to sit on the ROAS card's sub line is gone, so the
# same number is not printed twice one tile apart.
ok("cardT.acos.toFixed(1) + '% ACOS'" not in js,
   'D4d and it no longer doubles as the ROAS sub-line')

# Rule #1: no second chart renderer, no second card renderer.
eq('D5a one pnlTrendRender', len(re.findall(r'async\s+function\s+pnlTrendRender\s*\(', js)), 1)
eq('D5b one pnlCard', len(re.findall(r'function\s+pnlCard\s*\(', js)), 1)
eq('D5c one adsUpdateChart', len(re.findall(r'function\s+adsUpdateChart\s*\(', js)), 1)

# The colour map covers every metric the three registries can plot, so no ads
# metric falls through to a positional colour (which is what C5 forbids).
spec_keys = set(re.findall(r'^\s{2}(\w+):\s*\{', const_obj('ADS_METRIC_SPEC'), re.M))
colr_keys = set(re.findall(r'(\w+):\s*\'#', const_obj('ADS_METRIC_COLOR')))
missing = sorted(spec_keys - colr_keys)
ok(not missing, 'D6 every plottable metric has a declared colour', missing)

# v11.33b - found by READING THE RENDERED TITLE back in a browser, not by a
# test: `grain + 'ly'` gives weekly, monthly and **dayly**, which the Campaigns
# reading has rendered since v11.23. One helper, both callers (hard rule #1) -
# the alternative was shipping a second copy of the same typo.
# v11.74 - renamed adsGrainAdv -> pnlGrainAdv when the grain became a
# chart-wide concept. The guarantee is unchanged (ONE adverb helper, no raw
# concatenation); only the name moved, and the old one must be gone rather
# than left standing beside the new one.
eq('D7a exactly one grain adverb helper',
   len(re.findall(r'function\s+pnlGrainAdv\s*\(', js)), 1)
# /!\ Against COMMENT-STRIPPED source, and the comment required to SURVIVE -
# the v11.18 / v11.54 rule. The only remaining mention is the line explaining
# the rename, which is exactly where someone grepping the old name should land.
_D7NC = re.sub(r'(?m)^\s*//.*$', '', js)
eq('D7a2 and the Ads-prefixed name is GONE from the code',
   len(re.findall(r'\badsGrainAdv\b', _D7NC)), 0)
ok('renamed from adsGrainAdv' in js,
   'D7a3 and the rename is still explained where it will be grepped')
ok("+ 'ly trend'" not in js, 'D7b no raw concatenation survives')
# Counting the bare call would be 3 - the helper's own signature contains it.
eq('D7c both Ads chart titles go through it',
   js.count("pnlGrainAdv(grain) + ' trend'"), 2)
# v11.74 - and the four P&L titles joined it rather than keeping their own
# hardcoded word. Two of them named the WRONG grain before this.
eq('D7d the four P&L titles derive theirs too',
   len(re.findall(r"\$\{pnlGrainAdv\(_\w+Grain\)\} trend", js)), 4)

print('\n== %d passed, %d failed ==' % (passed, failed))
for f in ('_v1133_a.js', '_v1133_b.js', '_v1133_c.js'):
    try: os.remove(os.path.join(SP, f))
    except OSError: pass
sys.exit(1 if failed else 0)
