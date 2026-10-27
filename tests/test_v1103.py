# -*- coding: utf-8 -*-
"""
v11.03 — the Chewy Program tab gets the Amazon P&L's scorecard + chart shape.

Jason: "i need to see this data in a way i can measure yoy and month over
month. make it similar to the scorecard and line chart views on the amazon
p&l. keep the table as a expand/collapse section."

⚠ THE ASSERTION THAT EARNS ITS KEEP is the TOTALS REGRESSION GUARD. v11.03
factored the inline totals block into `totalsOver(rows)` so the scorecards'
comparison bases roll up with the identical arithmetic. Two hand-written
roll-ups would be two chances to disagree about what Program Net means, and
the only way to make "identical" a checkable claim rather than something read
off a diff is to run the v11.01 block and the shipped one over the same rows
and require a byte-identical result.

⚠ THE SECOND ONE: the prior-year overlay reads the FULL month series, not the
windowed one. The same trap as the YoY index — a window under two years
contains no prior year, so reading the twin from `months` would draw an empty
dashed line on every period anyone would actually pick.

⚠ THE THIRD: the TOTAL row was twelve HAND-ORDERED cells under a
registry-driven header. Adding the MoM column would have slid every footer
value under the wrong heading, silently. It is keyed now, and this suite
fails if a registry column ever lacks a footer cell.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, 'index.html')
SP = tempfile.gettempdir()
src = io.open(INDEX, encoding='utf-8', newline='').read()
js = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', src, re.S), key=len)

fails = []


def ok(cond, label, got=None):
    if cond:
        print('  ok    ' + label)
    else:
        print('  FAIL  ' + label + ('' if got is None else '  got: %r' % (got,)))
        fails.append(label)


def fn(name):
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), js)
    if not m:
        raise SystemExit('FAIL: cannot find %s' % name)
    k = js.index('(', m.end() - 1)
    d = 0
    while True:
        if js[k] == '(':
            d += 1
        elif js[k] == ')':
            d -= 1
            if d == 0:
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


def arr_const(name):
    i = js.index('const %s = [' % name)
    d, k = 0, js.index('[', i)
    while k < len(js):
        if js[k] == '[':
            d += 1
        elif js[k] == ']':
            d -= 1
            if d == 0:
                break
        k += 1
    return js[i:k + 2]


def obj_const(name):
    i = js.index('const %s = {' % name)
    return js[i:js.index('};', i) + 2]


def strip_comments(t):
    return re.sub(r'(?m)^\s*//.*$', '', re.sub(r'(?<!:)//[^\n]*', '', t))


def run_node(name, body):
    p = os.path.join(SP, name)
    io.open(p, 'w', encoding='utf-8', newline='').write(body)
    r = subprocess.run(['node', p], capture_output=True, text=True)
    if r.returncode != 0:
        ok(False, '%s harness ran' % name, (r.stderr or '')[:2000])
        return []
    return json.loads(r.stdout.strip().splitlines()[-1])


# ===========================================================================
# A. the aggregator
# ===========================================================================
print('\nA. chewyProgramMonthly: totals, MoM, comparison bases')

H1 = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

__AGG__

const SALES = [], ADS = [];
function add(m, units, adUnits) {
  SALES.push({ week_start: m + '-07', chewy_sku: 'S', units, autoship: Math.round(units * 0.4), merch_sales: units * 10 });
  ADS.push({ date: m + '-07', chewy_sku: 'S', direct_units: adUnits, spend: 50,
             direct_sales: adUnits * 10, ntb_customers: adUnits, autoship_signups: 10 });
}
['2025-05','2025-06','2025-07','2025-08'].forEach((m,i) => add(m, 100 + i * 10, 5));
['2026-05','2026-06','2026-07','2026-08'].forEach((m,i) => add(m, 150 + i * 10, 30));
const base = { salesRows: SALES, adRows: ADS, contribBySku: { S: 2 }, brandBySku: {} };
const run = o => chewyProgramMonthly(Object.assign({}, base, o || {}));

// ⚠ A1 — THE REGRESSION GUARD. Reproduce the v11.01 inline totals block and
// require a byte-identical result from the factored totalsOver.
const r0 = run();
function v1101Totals(months) {
  const sum = (k) => months.reduce((t, r) => t + (Number(r[k]) || 0), 0);
  const totals = {
    monthCount: months.length,
    totalUnits: sum('totalUnits'), adUnits: sum('adUnits'),
    organicUnits: sum('organicUnits'), autoshipUnits: sum('autoshipUnits'),
    retail: sum('retail'), contribution: sum('contribution'),
    pricedUnits: sum('pricedUnits'), spend: sum('spend'), ntb: sum('ntb'),
  };
  totals.programNet = totals.contribution - totals.spend;
  totals.adSharePct = totals.totalUnits > 0 ? (totals.adUnits / totals.totalUnits) * 100 : null;
  totals.organicSharePct = totals.totalUnits > 0 ? (totals.organicUnits / totals.totalUnits) * 100 : null;
  totals.autoshipSharePct = totals.totalUnits > 0 ? (totals.autoshipUnits / totals.totalUnits) * 100 : null;
  totals.tacosPct = totals.retail > 0 ? (totals.spend / totals.retail) * 100 : null;
  totals.spendShareOfContribPct = totals.contribution > 0 ? (totals.spend / totals.contribution) * 100 : null;
  totals.pricedSharePct = totals.totalUnits > 0 ? (totals.pricedUnits / totals.totalUnits) * 100 : null;
  return totals;
}
t('A1  totalsOver is byte-identical to the v11.01 inline block',
  JSON.stringify(r0.totals), JSON.stringify(v1101Totals(r0.months)));
t('A1b and over a WINDOWED subset too',
  (() => { const w = run({ from: '2026-06-01', to: '2026-08-31' });
           return JSON.stringify(w.totals) === JSON.stringify(v1101Totals(w.months)); })(), true);

// A2 — month-over-month on units.
const mom = {}; r0.months.forEach(r => { mom[r.month] = r.momPct == null ? null : +r.momPct.toFixed(2); });
t('A2  MoM is computed against the previous CALENDAR month',
  [mom['2025-06'], mom['2025-07']], [10, 9.09]);
t('A2b the first month of the series has none', mom['2025-05'], null);
t('A2c ⚠ null ACROSS A FEED GAP - 2026-05 does not follow 2025-08',
  mom['2026-05'], null);
t('A2d and the month after a gap resumes normally', mom['2026-06'], 6.67);

// A2e — a part-month has no MoM, and neither does the month after it.
const pm = run({ from: '2026-05-15', to: '2026-08-31' });
const momp = {}; pm.months.forEach(r => { momp[r.month] = r.momPct; });
t('A2e a part-month reports no MoM - fewer days is not a decline', momp['2026-05'], null);
t('A2f and nor does the month whose predecessor is a part-month', momp['2026-06'], null);

// A3 — the prior-YEAR basis.
const c = r0.compare;
t('A3  compare.year pairs the same calendar months a year apart',
  [c.year.months, c.year.priorMonths],
  [['2026-05','2026-06','2026-07','2026-08'], ['2025-05','2025-06','2025-07','2025-08']]);
t('A3b with totals on both sides', [c.year.prior.totalUnits, c.year.now.totalUnits], [460, 660]);
// ⚠ A3c caught a REAL defect, not a wrong expectation. `complete` was false
// here and the scorecard note turned that into "part-months held out" - but
// nothing is a part-month on all time. The four 2025 months are unpaired
// because 2024 is not on record. Two plain counts now, and the note states
// them instead of naming a cause it cannot know.
t('A3c the note counts what paired, and names no cause it cannot know',
  [c.year.paired, c.year.candidates], [4, 8]);
t('A3d a part-month window reduces the candidates, not the pairs',
  (() => { const x = run({ from: '2026-05-15', to: '2026-08-31' });
           return [x.compare.year.paired, x.compare.year.candidates]; })(), [3, 3]);

// A4 — the prior-PERIOD basis: the block of months immediately before.
// ⚠ A4 needs its own CONTIGUOUS fixture. The main one jumps 2025-08 ->
// 2026-05, so a three-month window shifted back three months lands on months
// that are not on record - real behaviour, asserted separately at A4c, but
// not what A4 is about.
const CS = [], CA = [];
['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06','2026-07','2026-08']
  .forEach((m, i) => {
    CS.push({ week_start: m + '-07', chewy_sku: 'S', units: 100 + i * 10, autoship: 0, merch_sales: 1000 });
    CA.push({ date: m + '-07', chewy_sku: 'S', direct_units: 10, spend: 50, direct_sales: 100 });
  });
const cont = o => chewyProgramMonthly(Object.assign(
  { salesRows: CS, adRows: CA, contribBySku: { S: 2 }, brandBySku: {} }, o || {}));
const cq = cont({ from: '2026-06-01', to: '2026-08-31' });
t('A4  compare.period shifts back by the window length',
  [cq.compare.period.months, cq.compare.period.priorMonths],
  [['2026-06','2026-07','2026-08'], ['2026-03','2026-04','2026-05']]);
t('A4b with the prior block\u2019s own totals',
  [cq.compare.period.prior.totalUnits, cq.compare.period.now.totalUnits], [390, 480]);
t('A4c and a month whose shifted twin is not on record is simply not paired',
  run({ from: '2026-06-01', to: '2026-08-31' }).compare.period.months, ['2026-08']);
const q = run({ from: '2026-06-01', to: '2026-08-31' });

// ⚠ A5 — the point of the whole design: prevYear survives a window that
// contains no prior year, because it pairs MONTHS out of the data.
const w365 = run({ from: '2025-11-01', to: '2026-10-31' });
t('A5  compare.year survives a 12-month window',
  w365.compare.year && w365.compare.year.months,
  ['2026-05','2026-06','2026-07','2026-08']);
t('A5b with figures identical to the all-time read',
  [JSON.stringify(w365.compare.year.now), JSON.stringify(w365.compare.year.prior)],
  [JSON.stringify(r0.compare.year.now), JSON.stringify(r0.compare.year.prior)]);
t('A5b2 only the candidate count differs, because the window holds fewer months',
  [w365.compare.year.candidates, r0.compare.year.candidates], [4, 8]);
t('A5c while compare.period correctly finds nothing before the series',
  run({ from: '2025-05-01', to: '2025-08-31' }).compare.period, null);

// A6 — part-months are held out of BOTH bases.
t('A6  a part-month is not paired by either basis',
  [pm.compare.year.months.indexOf('2026-05'), pm.months.map(r => r.month).indexOf('2026-05')],
  [-1, 0]);

// A7 — the full series is returned for the chart's prior-year overlay.
t('A7  allMonths is the FULL comparable series, not the windowed one',
  [q.allMonths.length, q.months.length], [8, 3]);
t('A7b and the windowed months are the same row objects, not copies',
  q.months.every(r => q.allMonths.indexOf(r) > -1), true);

// A8 — degenerate: a window with nothing in it.
const none = run({ from: '2030-01-01', to: '2030-12-31' });
t('A8  an empty window has no comparison basis at all',
  [none.compare.year, none.compare.period], [null, null]);
t('A8b and leaks no NaN / Infinity',
  /NaN|Infinity/.test(JSON.stringify([r0, q, pm, none, w365])), false);

console.log(JSON.stringify(out));
'''
for row in run_node('test_v1103_agg.js', H1.replace('__AGG__', fn('chewyProgramMonthly'))):
    ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


# ===========================================================================
# B. the chart
# ===========================================================================
print('\nB. the monthly trend chart')

H2 = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

let CFG = null, DESTROYED = 0;
async function pnlTrendRender(cfg) { CFG = cfg; return { destroy: () => { DESTROYED++; } }; }
let chewyProgramChartInstance = null;
let EL = {};
const document = { getElementById: id => (id in EL ? EL[id] : null) };
const console = { warn: () => {}, log: (...a) => process.stdout.write(a.join(' ') + String.fromCharCode(10)) };

__COLS__
__UNITS__
__FILL__
__CHART__

function reset(metric, ly) {
  CFG = null;
  EL = {
    'chpnl-pg-chart-panel': { style: { display: 'none' } },
    'chpnl-pg-chart-metric': { value: metric, dataset: {}, innerHTML: '' },
    'chpnl-pg-chart-ly': { checked: !!ly },
    'chpnl-pg-chart-title': { textContent: '' },
    'chpnl-pg-chart-sub': { textContent: '' },
  };
}
const MONTHS = ['2026-05','2026-06','2026-07'];
const ALL = ['2025-05','2025-06','2025-07','2026-05','2026-06','2026-07'].map((m, i) => ({
  month: m, totalUnits: 100 + i * 10, spend: 50 + i, tacosPct: 2 + i, partial: false,
}));
const res = { months: ALL.filter(r => MONTHS.includes(r.month)), allMonths: ALL,
              coverage: { partialMonths: [] } };

(async () => {
  // B1 — month buckets, one series, through the SHARED renderer.
  reset('totalUnits', false); await updateChewyProgramChart(res);
  t('B1  buckets are YYYY-MM months', CFG.buckets, MONTHS);
  t('B1b one dataset with the registry label',
    [CFG.datasets.length, CFG.datasets[0].label], [1, 'Units']);
  t('B1c line mode, # unit, not a percentage', [CFG.mode, CFG.unit, CFG.isPct], ['line', '#', false]);
  t('B1d the panel is shown', EL['chpnl-pg-chart-panel'].style.display, 'block');
  t('B1e the title names the metric', EL['chpnl-pg-chart-title'].textContent, 'Units · monthly trend');

  // ⚠ B2 — the prior-year overlay is read from the FULL series and plotted on
  // THIS year's buckets. Reading it from res.months would leave it empty on
  // every window under two years - the same trap the YoY index has.
  reset('totalUnits', true); await updateChewyProgramChart(res);
  t('B2  the overlay adds a second dataset', CFG.datasets.length, 2);
  t('B2b dashed, so it cannot be mistaken for this year', CFG.datasets[1].borderDash, [5, 4]);
  t('B2c plotted on THIS year’s buckets', CFG.buckets, MONTHS);
  t('B2d with the PRIOR year’s values, taken from allMonths',
    CFG.datasets[1].data, [100, 110, 120]);
  t('B2e and the subtitle says how many matched',
    EL['chpnl-pg-chart-sub'].textContent.indexOf('prior year on 3 of 3') > -1, true);

  // B2f — reading the twin from the windowed set would have produced nothing.
  const windowedOnly = { months: res.months, allMonths: res.months, coverage: { partialMonths: [] } };
  reset('totalUnits', true); await updateChewyProgramChart(windowedOnly);
  t('B2f  the naive windowed-only lookup really does find no prior year',
    CFG.datasets.length, 1);
  t('B2g and says so rather than drawing an empty dashed line',
    EL['chpnl-pg-chart-sub'].textContent.indexOf('no prior-year months on record') > -1, true);

  // B3 — a percentage metric flips isPct and the unit.
  reset('tacosPct', false); await updateChewyProgramChart(res);
  t('B3  a percentage metric is flagged as one', [CFG.isPct, CFG.unit], [true, '%']);
  t('B3b and labelled from the registry, not a second list', CFG.datasets[0].label, 'TACOS');

  // B4 — no months: hide the panel and destroy the instance rather than
  // leaving a stale chart describing a different window.
  reset('totalUnits', false);
  chewyProgramChartInstance = { destroy: () => { DESTROYED++; } };
  await updateChewyProgramChart({ months: [], allMonths: [], coverage: { partialMonths: [] } });
  t('B4  an empty window hides the panel', EL['chpnl-pg-chart-panel'].style.display, 'none');
  t('B4b and destroys the stale instance', DESTROYED > 0, true);
  t('B4c without calling the renderer', CFG, null);

  // B5 — the metric picker is built from the table's registry.
  reset('totalUnits', false);
  chewyProgramFillMetricPicker();
  const opts = (EL['chpnl-pg-chart-metric'].innerHTML.match(/value="([^"]+)"/g) || [])
    .map(s => s.slice(7, -1));
  t('B5  every registry column except Month is plottable',
    opts, CHEWY_PROGRAM_COLUMNS.filter(c => c.k !== 'month').map(c => c.k));
  t('B5b and it is not rebuilt on every render',
    (() => { EL['chpnl-pg-chart-metric'].innerHTML = 'X'; chewyProgramFillMetricPicker();
             return EL['chpnl-pg-chart-metric'].innerHTML; })(), 'X');

  // B6 — a null in the series is a GAP, never a zero that reads as a crash.
  const holed = { months: [{ month: '2026-05', totalUnits: 10 }, { month: '2026-06' },
                           { month: '2026-07', totalUnits: 30 }],
                  allMonths: [], coverage: { partialMonths: [] } };
  reset('totalUnits', false); await updateChewyProgramChart(holed);
  t('B6  a missing value is null, not 0', CFG.datasets[0].data, [10, null, 30]);
  t('B6b and the line spans it rather than breaking', CFG.datasets[0].spanGaps, true);

  console.log(JSON.stringify(out));
})();
'''
h2 = H2
for tok, part in (('__COLS__', arr_const('CHEWY_PROGRAM_COLUMNS')),
                  ('__UNITS__', obj_const('CHEWY_PROGRAM_CHART_UNITS')),
                  ('__FILL__', fn('chewyProgramFillMetricPicker')),
                  ('__CHART__', fn('updateChewyProgramChart'))):
    assert h2.count(tok) == 1, 'token %s not unique' % tok
    h2 = h2.replace(tok, part)
for row in run_node('test_v1103_chart.js', h2):
    ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


# ===========================================================================
# C. the neutral delta chip
# ===========================================================================
print('\nC. pnlDeltaChip gains a neutral verdict')

H3 = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });
let _pnlSuppressDeltas = false;
__CHIP__
const col = h => (h.match(/color:(var\(--[a-z0-9-]+\)|#[0-9a-f]+)/) || [])[1];

// ⚠ C1 — the existing verdicts must be untouched. This is the regression half.
t('C1  goodWhenUp true + rising is still green', col(pnlDeltaChip(110, 100, true, false, 'p')), 'var(--sp-green)');
t('C1b goodWhenUp true + falling is still red',  col(pnlDeltaChip(90, 100, true, false, 'p')),  'var(--sp-red)');
t('C1c goodWhenUp false + rising is still red',  col(pnlDeltaChip(110, 100, false, false, 'p')), 'var(--sp-red)');
t('C1d goodWhenUp false + falling is still green', col(pnlDeltaChip(90, 100, false, false, 'p')), 'var(--sp-green)');
t('C1e flat is still neutral', col(pnlDeltaChip(100, 100, true, false, 'p')), 'var(--text3)');

// C2 — the new mode: direction without a verdict.
t('C2  null verdict rising is neutral', col(pnlDeltaChip(110, 100, null, false, 'p')), 'var(--text3)');
t('C2b null verdict falling is neutral', col(pnlDeltaChip(90, 100, null, false, 'p')), 'var(--text3)');
t('C2c but the DIRECTION is still shown', pnlDeltaChip(110, 100, null, false, 'p').indexOf('▲ +10.0%') > -1, true);
t('C2d and the fall too', pnlDeltaChip(90, 100, null, false, 'p').indexOf('▼ -10.0%') > -1, true);

// C3 — points mode and the suppression flag are unaffected.
t('C3  points mode still reports points', pnlDeltaChip(12, 10, null, true, 'p').indexOf('+2.0 pts') > -1, true);
_pnlSuppressDeltas = true;
t('C3b the all-time suppression still wins over every verdict',
  [pnlDeltaChip(110, 100, null, false, 'p'), pnlDeltaChip(110, 100, true, false, 'p')], ['', '']);
_pnlSuppressDeltas = false;
t('C3c both zero still renders nothing', pnlDeltaChip(0, 0, null, false, 'p'), '');

console.log(JSON.stringify(out));
'''
for row in run_node('test_v1103_chip.js', H3.replace('__CHIP__', fn('pnlDeltaChip'))):
    ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


# ===========================================================================
# D. the CSV, driven for real
# ===========================================================================
print('\nD. the export')

H4 = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });
let TEXT = '';
function promptCsvName(d) { return d; }
function Blob(parts) { TEXT = parts.join(''); }
const URL = { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} };
const document = { createElement: () => ({ style: {}, click: () => {}, remove: () => {} }),
                   body: { appendChild: () => {} } };
function logAudit() {}
let chewyProgramExport = null;
__CSV__

const months = [
  { month: '2026-05', totalUnits: 100, adUnits: 10, organicUnits: 90, adSharePct: 10,
    autoshipUnits: 40, autoshipSharePct: 40, retail: 1000, contribution: 200, spend: 50,
    programNet: 150, tacosPct: 5, ntb: 8, signups: 3, pricedUnits: 100, pricedSharePct: 100,
    momPct: null, partial: false },
  { month: '2026-06', totalUnits: 110, adUnits: 12, organicUnits: 98, adSharePct: 10.9,
    autoshipUnits: 44, autoshipSharePct: 40, retail: 1100, contribution: 220, spend: 55,
    programNet: 165, tacosPct: 5, ntb: 9, signups: 3, pricedUnits: 110, pricedSharePct: 100,
    momPct: 10, partial: true },
];
chewyProgramExport = { brand: '', res: {
  months, totals: { totalUnits: 210, adUnits: 22, organicUnits: 188, adSharePct: 10.5,
    autoshipUnits: 84, autoshipSharePct: 40, retail: 2100, contribution: 420, spend: 105,
    programNet: 315, tacosPct: 5, ntb: 17, pricedUnits: 210, pricedSharePct: 100 },
  yoy: null,
  coverage: { adOnly: [], sellOnly: [], comparable: ['2026-04','2026-05','2026-06'],
              partialMonths: ['2026-06'], outsideWindow: ['2026-04'],
              window: { from: '2026-05-10', to: '2026-06-20' } },
} };
downloadChewyProgramCSV();
const lines = TEXT.replace(/^﻿/, '').split('\n');
const hdr = lines.find(l => l.startsWith('month,'));
const body = lines.filter(l => /^2026-/.test(l));
const total = lines.find(l => l.startsWith('TOTAL,'));

// ⚠ D1 — a header wider than its rows is the commonest silent CSV defect.
t('D1  every data row has exactly as many fields as the header',
  body.map(l => l.split(',').length).concat([total.split(',').length]),
  body.map(() => hdr.split(',').length).concat([hdr.split(',').length]));
t('D1b and the two new columns are present',
  [hdr.indexOf('units_mom_pct') > -1, hdr.indexOf('part_month') > -1], [true, true]);
t('D2  the MoM value lands in its own column',
  body[1].split(',')[hdr.split(',').indexOf('units_mom_pct')], '10.00');
t('D2b and the part-month flag in its own',
  [body[0].split(',')[hdr.split(',').indexOf('part_month')],
   body[1].split(',')[hdr.split(',').indexOf('part_month')]], ['', 'yes']);
t('D3  the window is stated so the file can be re-derived',
  TEXT.indexOf('# period window: 2026-05-10 to 2026-06-20') > -1, true);
t('D3b naming how many of the comparable months it covers',
  TEXT.indexOf('2 of 3 comparable months') > -1, true);
t('D3c and the part-months at its edge',
  TEXT.indexOf('# part-months at the window edge') > -1 && TEXT.indexOf('2026-06') > -1, true);

console.log(JSON.stringify(out));
'''
for row in run_node('test_v1103_csv.js', H4.replace('__CSV__', fn('downloadChewyProgramCSV'))):
    ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


# ===========================================================================
# E. static
# ===========================================================================
print('\nE. static assertions')

live = strip_comments(js)
rp = fn('renderChewyProgram')

# ⚠ The footer had to become keyed before a column could be added.
ok('const TCELLS = {' in rp, 'E1  the TOTAL row is a keyed map')
ok("COLS.map(c => TCELLS[c.k]" in rp,
   'E1b emitted from the same filtered list as the header')
cols = re.findall(r"\{ k: '([a-zA-Z]+)'", arr_const('CHEWY_PROGRAM_COLUMNS'))
tcells = re.findall(r"^\s{12}([a-zA-Z]+):", rp[rp.index('const TCELLS = {'):], re.M)
missing = [c for c in cols if c not in tcells]
ok(not missing, 'E1c every registry column has a footer cell', missing)
bcells = rp[rp.index('const CELLS = {'):rp.index('const TCELLS = {')]
bmissing = [c for c in cols if (c + ':') not in bcells]
ok(not bmissing, 'E1d and a body cell', bmissing)
ok(len(cols) == 13, 'E1e thirteen Program columns', len(cols))
ok('Units MoM %' in js, 'E1f the MoM column exists')
ok("'Units MoM %':" in js, 'E1g and is declared in CHEWY_MEASURE_VOCAB')

# ⚠ The all-time suppression override, saved AND restored.
ok('const _savedSuppress = _pnlSuppressDeltas;' in rp and '_pnlSuppressDeltas = !cmp;' in rp,
   'E2  the all-time delta suppression is overridden from whether a pair exists')
ok('_pnlSuppressDeltas = _savedSuppress;' in rp,
   'E2b and restored, so no other surface inherits it')
ok(rp.index('_pnlSuppressDeltas = !cmp;') < rp.index('_pnlSuppressDeltas = _savedSuppress;'),
   'E2c in that order')
ok(rp.count('_pnlSuppressDeltas') == 3,
   'E2d and touched nowhere else in the renderer', rp.count('_pnlSuppressDeltas'))

# The chart goes through the shared renderer and reads the full series.
ch = fn('updateChewyProgramChart')
ok('pnlTrendRender({' in ch, 'E3  the chart calls the shared renderer')
ok('new Chart(' not in ch, 'E3b and never constructs its own')
ok('res.allMonths' in ch,
   'E3c ⚠ the prior-year overlay reads the FULL series, not the windowed one')
ok("CHEWY_PROGRAM_COLUMNS.find(c => c.k === k)" in ch,
   'E3d the metric label comes from the table registry (rule 3a)')
ok('CHEWY_PROGRAM_COLUMNS' in fn('chewyProgramFillMetricPicker'),
   'E3e and so does the picker, rather than a second metric list')

# The chart panel is the app's one chart-panel look, not a second one.
panel = re.search(r'<div id="chpnl-pg-chart-panel".*?</div>\s*</div>\s*</div>\s*</div>', src, re.S)
ok(panel is not None, 'E4  the chart panel exists')
if panel:
    p = panel.group(0)
    for frag in ('class="ds"', 'class="ds-hdr"', 'class="ds-body"', 'ds-title', 'ds-sub',
                 '<canvas id="chpnl-pg-chart-canvas">'):
        ok(frag in p, 'E4b chart panel reuses %s' % frag)
    ok('mode-host' not in p,
       'E4c no Stacked/Bands toggle - these series are not product bands (v10.19)')

# Expand/collapse, with the count in the summary so the collapsed state says
# what is inside.
ok('<details id="chpnl-pg-table"' in src, 'E5  the table is an expand/collapse section')
det = src[src.index('<details id="chpnl-pg-table"'):src.index('</details>', src.index('<details id="chpnl-pg-table"'))]
ok('<summary' in det, 'E5b with a summary')
ok('id="chpnl-pg-row-count"' in det[:det.index('</summary>')],
   'E5c and the row-count line inside it, so the collapsed state still states the scope')
ok('ontoggle="onChewyProgramTableToggle()"' in det, 'E5d the open state is tracked')
ok('fitTableWrapsSoon' in fn('onChewyProgramTableToggle'),
   'E5e and the table re-fits on open - it measures 0 while collapsed (v10.85)')
ok('chewyProgramTableOpen' in fn('chewyProgramRestoreTableState'),
   'E5f and the choice persists per browser')

# The comparison basis.
ok('chpnl-pg-cmp-year' in src and 'chpnl-pg-cmp-period' in src,
   'E6  both comparison bases are offered')
ok("return 'year';" in fn('chewyProgramCompareBasis'),
   'E6b year is the default - pairing the same months a year apart is this tab’s thesis')
ok("cmp.paired + ' of ' + cmp.candidates" in rp,
   'E6c2 the note states the paired counts rather than naming a cause')
ok('cmp.complete' not in rp,
   'E6c3 and the conflated complete flag is gone')
ok('chpnl-pg-cmp-note' in src and 'cmpNote.textContent' in rp,
   'E6c a basis that could not be built is SAID, not five silently missing chips')
ok("dChip('spend', null)" in rp,
   'E6d ⚠ Ad Spend is NEUTRAL - a red chip there reads as "cut it"')
ok("dChip('adSharePct', null, true)" in rp,
   'E6e and so is Ad Share, which cannot tell growth from attribution shift')
ok("dChip('tacosPct', false, true)" in rp and "dChip('programNet', true)" in rp,
   'E6f while TACOS and Program Net keep a real verdict')

# The month bucket format.
tr = fn('pnlTrendRender')
ok('if (d === undefined) return' in tr,
   'E7  a month bucket is formatted rather than producing 5/undefined/26')
ok('${+mo}/${+d}/${y.slice(2)}' in tr, 'E7b and day buckets are unchanged')

# Standing sweeps.
bad = re.findall(r'\\U[0-9a-fA-F]{8}', live)
ok(not bad, 'E8  no uppercase-U escapes in live code', bad[:4])
ok('uppercase' in js.lower(), 'E8b guard-the-guard: the documented warning survives')
ok('v11.03' in src, 'E9  v11.03 provenance marker present')
for marker in ('v11.02', 'v11.01', 'v10.54', 'v10.19'):
    ok(marker in src, 'E9b earlier provenance marker preserved: %s' % marker)

print('')
if fails:
    print('v11.03  %d FAILED' % len(fails))
    for f in fails:
        print('   - ' + f)
    sys.exit(1)
print('v11.03  ALL GREEN')
