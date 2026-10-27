# -*- coding: utf-8 -*-
"""
v11.02 — ONE Chewy period control, shared by all five sub-tabs.

Jason: "give me a period picker like on amazon p&L, which should persist
across all chewy tabs."

There were FOUR period <select>s on the Chewy P&L and they had already
DRIFTED — Sales carried this-month / last-month and suppressed delta chips on
all-time; Cost and Break-Even had neither; Rebates resolved through a FIFTH
mechanism entirely (chewyPnlDateFilter, a boolean predicate that understood
only all / ytd / N-days and RETURNED TRUE for every other key). Four copies of
one control is the condition hard rule #1 exists to stop.

⚠ THE ASSERTION THAT EARNS ITS KEEP is the YoY REGRESSION GUARD. The Program
tab's year-over-year read compares the same calendar months one year apart.
The prior year sits OUTSIDE any window shorter than two years, so the obvious
implementation — window the rows, then pair what is left — makes that panel
permanently empty on every period Jason would actually pick. This suite
reproduces that implementation and proves it really does return yoy === null
where the shipped one returns the real figures.

⚠ THE SECOND ONE: a month only PARTLY covered by the window is shown and
flagged, never silently dropped (dropping it loses the current month-to-date,
the month a month-over-month tracker most needs) and never silently paired
(comparing a part-month against a full one is the distortion the YoY read
exists to remove).

⚠ THE THIRD: all-time is the one period that is NOT shared. Each tab floors at
its own feed's first day, because chewy_sales_weekly / chewy_ad_spend /
chewy_rebates start on different days. Covered in test_v1079 B4; this suite
pins the registry that makes it possible.
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
    """Slice one top-level function by brace balance, parameter list first."""
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


def obj_const(name):
    i = js.index('const %s = {' % name)
    return js[i:js.index('};', i) + 2]


def lit_const(name):
    i = js.index('const %s = ' % name)
    return js[i:js.index(';', i) + 1]


def strip_comments(text):
    """Blank line comments so a sweep asserts on LIVE CODE (the v10.93 shape)."""
    return re.sub(r'(?m)^\s*//.*$', '', re.sub(r'(?<!:)//[^\n]*', '', text))


# ===========================================================================
# A. the aggregator — driven as a PURE function
# ===========================================================================
print('\nA. chewyProgramMonthly under a window')

HARNESS = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });
const tt = (name, cond, got) => out.push({ name, pass: !!cond, got, want: true });

__AGG__

// ── fixture ────────────────────────────────────────────────────────────────
// Two calendar years of the same two months so the year-over-year pairing has
// something real to find, plus a third month in the current year only.
// Every figure is hand-checkable: 100 units a month, 10 of them ad-attributed.
const SALES = [], ADS = [];
const CONTRIB = { SKU1: 2 };
const BRANDS  = { SKU1: 'Meowijuana' };
function addMonth(m, units, adUnits) {
  SALES.push({ week_start: m + '-07', chewy_sku: 'SKU1', units, autoship: 0, merch_sales: units * 10 });
  ADS.push({ date: m + '-07', chewy_sku: 'SKU1', direct_units: adUnits, spend: 50,
             direct_sales: adUnits * 10, ntb_customers: adUnits, autoship_signups: 0 });
}
['2025-05', '2025-06', '2025-07'].forEach(m => addMonth(m, 100, 5));
['2026-05', '2026-06', '2026-07'].forEach(m => addMonth(m, 130, 25));

const base = { salesRows: SALES, adRows: ADS, contribBySku: CONTRIB, brandBySku: BRANDS };
const run = (o) => chewyProgramMonthly(Object.assign({}, base, o || {}));

// A1 — no window is the v11.01 behaviour, unchanged.
const unwindowed = run();
t('A1  no window shows every comparable month',
  unwindowed.months.map(r => r.month),
  ['2025-05', '2025-06', '2025-07', '2026-05', '2026-06', '2026-07']);
t('A1b and nothing is flagged partial', unwindowed.coverage.partialMonths, []);
t('A1c and coverage.window is null', unwindowed.coverage.window, null);

// A2 — the window scopes which months are SHOWN.
const w = run({ from: '2026-05-01', to: '2026-07-31' });
t('A2  the window selects whole months',
  w.months.map(r => r.month), ['2026-05', '2026-06', '2026-07']);
t('A2b totals recompute over the windowed months only', w.totals.totalUnits, 390);
t('A2c and the excluded months are NAMED, not just dropped',
  w.coverage.outsideWindow, ['2025-05', '2025-06', '2025-07']);

// ⚠ A3 — THE ASSERTION THAT EARNS ITS KEEP.
// The prior year is OUTSIDE this window by definition, so the YoY read has to
// reach past it. It must still find all three pairs.
t('A3  YoY survives a window that excludes the prior year',
  w.yoy && w.yoy.months, ['2026-05', '2026-06', '2026-07']);
t('A3b and pairs them against the right prior months',
  w.yoy && w.yoy.priorMonths, ['2025-05', '2025-06', '2025-07']);
t('A3c with the real figures', w.yoy && [w.yoy.unitsPrior, w.yoy.unitsNow], [300, 390]);

// A3d — the REGRESSION GUARD. Reproduce the obvious implementation (index the
// WINDOWED months, which is what windowing the rows would amount to) and prove
// it really does come up empty.
const naivePairs = w.months.filter(r => {
  const idx = {}; w.months.forEach(x => { idx[x.month] = x; });
  const [y, m] = r.month.split('-');
  return !!idx[(Number(y) - 1) + '-' + m];
});
t('A3d  the naive index-the-window implementation really does find nothing',
  naivePairs.length, 0);

// A4 — a part-month is SHOWN and FLAGGED, at either edge.
const p = run({ from: '2026-05-15', to: '2026-07-10' });
t('A4  months overlapping the window edge are kept',
  p.months.map(r => r.month), ['2026-05', '2026-06', '2026-07']);
t('A4b and flagged', p.months.map(r => !!r.partial), [true, false, true]);
t('A4c and named on the coverage line', p.coverage.partialMonths, ['2026-05', '2026-07']);

// ⚠ A5 — a part-month is HELD OUT of the pairing. Comparing a part-month
// against a full one is exactly the distortion the YoY read exists to remove.
// Windowed so TWO full months survive: the hold-out is then proven beside a
// LIVE read rather than collapsing into the no-read case A5b already covers.
const p2 = run({ from: '2026-04-20', to: '2026-07-10' });
t('A5  all three months are still shown', p2.months.map(r => r.month),
  ['2026-05', '2026-06', '2026-07']);
t('A5a with only the last flagged partial', p2.months.map(r => !!r.partial),
  [false, false, true]);
t('A5  only the full months pair', p2.yoy && p2.yoy.months, ['2026-05', '2026-06']);
t('A5a2 so the part-month is in the table but out of the YoY totals',
  [p2.totals.totalUnits, p2.yoy && p2.yoy.unitsNow], [390, 260]);
t('A5b and with fewer than 2 pairs there is no read at all',
  run({ from: '2026-06-15', to: '2026-07-10' }).yoy, null);

// A6 — a prior-year month that is itself partial also disqualifies the pair.
const q = run({ from: '2025-05-20', to: '2026-07-31' });
t('A6  a partial PRIOR month disqualifies its pair',
  q.yoy && q.yoy.months, ['2026-06', '2026-07']);

// A7 — month-end arithmetic, including February in a leap and a non-leap year.

const leap = chewyProgramMonthly({
  salesRows: [{ week_start: '2024-02-05', chewy_sku: 'S', units: 10, autoship: 0, merch_sales: 1 }],
  adRows:    [{ date: '2024-02-05', chewy_sku: 'S', direct_units: 1, spend: 1, direct_sales: 1 }],
  contribBySku: {}, brandBySku: {}, from: '2024-02-01', to: '2024-02-29',
});
t('A7  2024-02 is FULL through the 29th', leap.months.map(r => !!r.partial), [false]);
const leap28 = chewyProgramMonthly({
  salesRows: [{ week_start: '2024-02-05', chewy_sku: 'S', units: 10, autoship: 0, merch_sales: 1 }],
  adRows:    [{ date: '2024-02-05', chewy_sku: 'S', direct_units: 1, spend: 1, direct_sales: 1 }],
  contribBySku: {}, brandBySku: {}, from: '2024-02-01', to: '2024-02-28',
});
t('A7b and PARTIAL through the 28th of a leap February',
  leap28.months.map(r => !!r.partial), [true]);
const nonleap = chewyProgramMonthly({
  salesRows: [{ week_start: '2025-02-05', chewy_sku: 'S', units: 10, autoship: 0, merch_sales: 1 }],
  adRows:    [{ date: '2025-02-05', chewy_sku: 'S', direct_units: 1, spend: 1, direct_sales: 1 }],
  contribBySku: {}, brandBySku: {}, from: '2025-02-01', to: '2025-02-28',
});
t('A7c  2025-02 is FULL through the 28th', nonleap.months.map(r => !!r.partial), [false]);

// A8 — one-sided windows.
t('A8  a from-only window keeps everything after it',
  run({ from: '2026-01-01' }).months.map(r => r.month), ['2026-05', '2026-06', '2026-07']);
t('A8b a to-only window keeps everything before it',
  run({ to: '2025-12-31' }).months.map(r => r.month), ['2025-05', '2025-06', '2025-07']);

// A9 — the window excludes EVERY month: honest empty, not a throw.
const none = run({ from: '2030-01-01', to: '2030-12-31' });
t('A9  an empty window yields no months', none.months.length, 0);
t('A9b totals are zero, not NaN', [none.totals.totalUnits, none.totals.spend], [0, 0]);
t('A9c  null rather than Infinity for the ratios',
  [none.totals.tacosPct, none.totals.adSharePct], [null, null]);
t('A9d  no YoY read', none.yoy, null);
t('A9e  but the comparable months are still reported, so the panel can say so',
  none.coverage.comparable.length, 6);

// A10 — the window never reaches the brand filter or the comparable-months rule.
t('A10  brand still narrows both feeds under a window',
  run({ from: '2026-01-01', brand: 'Doggijuana' }).months.length, 0);

// A11 — no leaked NaN / Infinity anywhere in a windowed result.
const blob = JSON.stringify([w, p, p2, q, none]);
tt('A11  no NaN / Infinity / undefined leaked into a windowed result',
   !/NaN|Infinity/.test(blob), blob.slice(0, 200));

console.log(JSON.stringify(out));
'''

harness = HARNESS.replace('__AGG__', fn('chewyProgramMonthly'))
hp = os.path.join(SP, 'test_v1102_agg.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', hp], capture_output=True, text=True)
if r.returncode != 0:
    ok(False, 'aggregator harness ran', (r.stderr or '')[:1800])
else:
    rows = json.loads(r.stdout.strip().splitlines()[-1])
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


# ===========================================================================
# B. the shared control's own handlers — driven for real
# ===========================================================================
print('\nB. the shared period control')

H2 = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

let STORE = {};
const localStorage = {
  getItem: k => (k in STORE ? STORE[k] : null),
  setItem: (k, v) => { STORE[k] = String(v); },
};
const OPTIONS = ['last-week','wtd','mtd','last-month','qtd','last-quarter','last-year',
                 '7','30','60','90','180','365','ytd','all','custom'];
let EL = {};
function mkSelect(v) {
  return { value: v, options: OPTIONS.map(o => ({ value: o })) };
}
const document = { getElementById: id => (id in EL ? EL[id] : null) };
const window = {};
let chewyPnlView = 'sales';
let _pnlSuppressDeltas = false;
const chewyPnlSalesData = [{ week_start: '2025-02-03' }];
const chewyAdSpendData  = [{ date: '2025-01-15' }];
const chewyPnlData      = [{ invoice_date: '2024-11-20' }];
const pnlData = [];
let RENDERS = [];
// ⚠ the stub shadows the real console, so it has to keep .log - the
// harness reports through it. chewyRerenderActiveTab warns on an unknown
// renderer, which is why the stub exists at all.
const NLCH = String.fromCharCode(10);
const console = { warn: () => {}, log: (...a) => process.stdout.write(a.join(' ') + NLCH) };

__ALLTIMEFROM__
__CPDR__
__SOURCES__
__VALUE__
__SHARED__
__RENDERERS__
__RERENDER__
__ONCHANGE__
__ONCUSTOM__
__RESTORE__
__TIPS__
__STATE__

function reset(sel) {
  EL = {
    'chpnl-period': mkSelect(sel),
    'chpnl-custom-wrap': { style: { display: 'none' } },
    'chpnl-period-state': { textContent: '', title: '' },
    'chpnl-from': { value: '' }, 'chpnl-to': { value: '' },
  };
  RENDERS = [];
}
['renderChewyPnlSales','renderChewyPnlCost','renderChewyBreakeven',
 'renderChewyProgram','renderChewyPnl'].forEach(n => { window[n] = () => RENDERS.push(n); });

// B1 — picking a bounded period persists it and repaints the ACTIVE tab.
reset('90'); chewyPnlView = 'breakeven'; STORE = {};
onChewyPeriodChange();
t('B1  the choice is persisted per browser', STORE['chewyPnlPeriod'], '90');
t('B1b and the ACTIVE tab repaints, not a named one', RENDERS, ['renderChewyBreakeven']);

reset('30'); chewyPnlView = 'program'; onChewyPeriodChange();
t('B1c  every tab routes through the same registry', RENDERS, ['renderChewyProgram']);

// ⚠ B2 — picking "custom" must NOT repaint: the two date inputs fire that, or
// the table redraws against a half-entered range (the v10.79 rule).
reset('custom'); chewyPnlView = 'sales'; onChewyPeriodChange();
t('B2  custom does not repaint on the pick itself', RENDERS, []);
t('B2b but it opens the date inputs', EL['chpnl-custom-wrap'].style.display, 'flex');
reset('90'); onChewyPeriodChange();
t('B2c and closes them again', EL['chpnl-custom-wrap'].style.display, 'none');

// B3 — the from/to inputs are what repaint, and they persist too.
reset('custom'); chewyPnlView = 'cost';
EL['chpnl-from'].value = '2026-03-01'; EL['chpnl-to'].value = '2026-03-31';
onChewyPeriodCustomChange();
t('B3  a custom date repaints the active tab', RENDERS, ['renderChewyPnlCost']);
t('B3b and both dates persist',
  [STORE['chewyPnlFrom'], STORE['chewyPnlTo']], ['2026-03-01', '2026-03-31']);

// B4 — restore.
reset('365'); STORE = { chewyPnlPeriod: 'last-quarter' };
chewyPeriodRestore();
t('B4  the stored period is restored', EL['chpnl-period'].value, 'last-quarter');
reset('365'); STORE = { chewyPnlPeriod: 'this-month' };   // a key this control never offers
chewyPeriodRestore();
t('B4b an unoffered stored key falls back to the default rather than silently',
  EL['chpnl-period'].value, CHEWY_PERIOD_DEFAULT);
reset('365'); STORE = {};
chewyPeriodRestore();
t('B4c no stored value leaves the default in place', EL['chpnl-period'].value, '365');
reset('365'); STORE = { chewyPnlPeriod: 'custom', chewyPnlFrom: '2026-01-05', chewyPnlTo: '2026-02-05' };
chewyPeriodRestore();
t('B4d a restored custom range re-opens its inputs',
  [EL['chpnl-custom-wrap'].style.display, EL['chpnl-from'].value, EL['chpnl-to'].value],
  ['flex', '2026-01-05', '2026-02-05']);

// B5 — the readout. A control one scroll away from the table it scopes reads
// as ignored unless something says what it resolved to (the v10.99 lesson).
reset('custom'); chewyPnlView = 'rebates';
EL['chpnl-from'].value = '2026-01-01'; EL['chpnl-to'].value = '2026-03-31';
chewyPeriodRenderState();
t('B5  the readout names the resolved range AND the date column it filters',
  EL['chpnl-period-state'].textContent, '2026-01-01 → 2026-03-31 · invoice_date');
reset('custom'); chewyPnlView = 'breakeven';
EL['chpnl-from'].value = '2026-01-01'; EL['chpnl-to'].value = '2026-03-31';
chewyPeriodRenderState();
t('B5b and the column changes with the tab, because the five tabs filter five',
  EL['chpnl-period-state'].textContent, '2026-01-01 → 2026-03-31 · date');
t('B5c with the tab-specific scope in the tooltip',
  EL['chpnl-period-state'].title.indexOf('backfills autoship attribution') > -1, true);
reset('all'); chewyPnlView = 'sales'; chewyPeriodRenderState();
t('B5d all-time says so', EL['chpnl-period-state'].textContent.indexOf('all time') > -1, true);
t('B5e and floors at the sell-through feed, not a global one',
  EL['chpnl-period-state'].textContent.indexOf('2025-02-03') === 0, true);

// B6 — nothing throws when the panel has not rendered yet.
EL = {}; RENDERS = [];
let threw = null;
try { chewyPeriodRenderState(); chewyPeriodRestore(); onChewyPeriodChange(); }
catch (e) { threw = String(e && e.message); }
t('B6  the handlers no-op cleanly with no control in the DOM', threw, null);

// B7 — an unknown view falls back rather than silently rendering nothing.
reset('90'); chewyPnlView = 'nonsense'; onChewyPeriodChange();
t('B7  an unknown active view falls back to Sales', RENDERS, ['renderChewyPnlSales']);

console.log(JSON.stringify(out));
'''

TOKENS = [
    ('__ALLTIMEFROM__', fn('pnlAllTimeFrom')),
    ('__CPDR__', fn('computePnlDateRange')),
    ('__SOURCES__', obj_const('CHEWY_PERIOD_SOURCES') + '\n' + lit_const('CHEWY_PERIOD_DEFAULT')),
    ('__VALUE__', fn('chewyPeriodValue')),
    ('__SHARED__', fn('getChewyPnlDateRange')),
    ('__RENDERERS__', obj_const('CHEWY_PERIOD_RENDERERS')),
    ('__RERENDER__', fn('chewyRerenderActiveTab')),
    ('__ONCHANGE__', fn('onChewyPeriodChange')),
    ('__ONCUSTOM__', fn('onChewyPeriodCustomChange')),
    ('__RESTORE__', 'let _chewyPeriodRestored = false;\n' + fn('chewyPeriodRestore')),
    ('__TIPS__', obj_const('CHEWY_PERIOD_SCOPE_TIPS')),
    ('__STATE__', fn('chewyPeriodRenderState')),
]
h2 = H2
for tok, srcpart in TOKENS:
    assert h2.count(tok) == 1, 'token %s not unique' % tok
    h2 = h2.replace(tok, srcpart)
hp2 = os.path.join(SP, 'test_v1102_ctrl.js')
io.open(hp2, 'w', encoding='utf-8', newline='').write(h2)
r2 = subprocess.run(['node', hp2], capture_output=True, text=True)
if r2.returncode != 0:
    ok(False, 'control harness ran', (r2.stderr or '')[:1800])
else:
    rows2 = json.loads(r2.stdout.strip().splitlines()[-1])
    for row in rows2:
        ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


# ===========================================================================
# C. static — the consolidation, and that it cannot drift back
# ===========================================================================
print('\nC. static assertions')

live = strip_comments(js)

ok(len(re.findall(r'<select[^>]*id="chpnl-period"', src)) == 1,
   'C1  exactly one Chewy period <select> in the markup')
ok(len(re.findall(r'id="chpnl-custom-wrap"', src)) == 1,
   'C1b exactly one Chewy custom-range wrap')
for gone in ('chpnl-sales-period', 'chpnl-cost-period', 'chpnl-be-period',
             'chpnl-sales-from', 'chpnl-cost-from', 'chpnl-be-from',
             'chpnl-sales-to', 'chpnl-cost-to', 'chpnl-be-to'):
    ok(gone not in src, 'C2  %s is gone from the whole file' % gone)

# The option list is Amazon's, because that is the page Jason named (rule #4).
m = re.search(r'<select[^>]*id="chpnl-period".*?</select>', src, re.S)
chewy_opts = re.findall(r'<option value="([^"]*)"', m.group(0)) if m else []
m2 = re.search(r'<select[^>]*id="pnl-period".*?</select>', src, re.S)
amzn_opts = re.findall(r'<option value="([^"]*)"', m2.group(0)) if m2 else []
ok(chewy_opts == amzn_opts,
   'C3  the Chewy option list matches the Amazon P&L exactly', (chewy_opts, amzn_opts))
ok(len(chewy_opts) == 16, 'C3b sixteen options', len(chewy_opts))
ok(chewy_opts.index('all') == len(chewy_opts) - 2 and chewy_opts[-1] == 'custom',
   'C3c All time sits just before Custom range')
ok('selected' in re.search(r'<option value="365"[^>]*>', m.group(0)).group(0),
   'C4  365 is the default option in the markup')
ok(re.search(r"const CHEWY_PERIOD_DEFAULT = '365';", live),
   'C4b and the resolver agrees, so a missing control resolves the same window')

# ⚠ The fifth mechanism, and its one call site.
ok('function chewyPnlDateFilter(' not in live, 'C5  chewyPnlDateFilter is deleted')
ok('chewyPnlDateFilter(' not in live, 'C5b and nothing still calls it')
reb = fn('renderChewyPnl')
ok('getChewyRebatesDateRange()' in reb, 'C5c Rebates reads the shared range')
ok('r.invoice_date < _rbFrom' in reb and 'r.invoice_date > _rbTo' in reb,
   'C5d and filters with the same inline idiom as its sibling tabs')

# One reader of the control's value.
# Two sites touch the element, and only two: chewyPeriodValue reads its VALUE,
# chewyPeriodRestore needs the ELEMENT (to set it, and to check the stored key
# is still offered). ⚠ No RENDERER may read it directly - a tab reading the
# raw control could interpret the period differently from the shared resolver,
# which is precisely what the four old controls did.
reads = re.findall(r"getElementById\('chpnl-period'\)", live)
ok(len(reads) == 2, 'C6  exactly two sites touch the period control', len(reads))
ok("getElementById('chpnl-period')" in fn('chewyPeriodValue'),
   'C6b one is chewyPeriodValue, which reads the value')
ok("getElementById('chpnl-period')" in fn('chewyPeriodRestore'),
   'C6c the other is chewyPeriodRestore, which needs the element')
for _r in ('renderChewyPnlSales', 'renderChewyPnlCost', 'renderChewyBreakeven',
           'renderChewyProgram', 'renderChewyPnl'):
    ok("getElementById('chpnl-period')" not in fn(_r),
       'C6d no renderer reads the control directly: %s' % _r)

# Wrappers, so every existing call site still lands.
for name, key in (('getChewyPnlSalesDateRange', 'sales'),
                  ('getChewyPnlCostDateRange', 'cost'),
                  ('getChewyBreakevenDateRange', 'breakeven'),
                  ('getChewyProgramDateRange', 'program'),
                  ('getChewyRebatesDateRange', 'rebates')):
    ok("getChewyPnlDateRange('%s')" % key in fn(name),
       'C7  %s delegates to the shared resolver' % name)

# ⚠ computePnlDateRange stays purely additive for Amazon.
cpdr = fn('computePnlDateRange')
ok('Array.isArray(opts.allRows)' in cpdr,
   'C8  the all-time override is opt-in by an explicit array check')
ok(cpdr.index('Array.isArray(opts.allRows)') < cpdr.index('getPnlSource'),
   'C8b and is checked BEFORE the Amazon default, so the override actually wins')
ok("pnlAllTimeFrom(src.rows, 'week_start')" in cpdr,
   'C8c the Amazon path is untouched')
ok(not re.search(r'_pnlSuppressDeltas\s*=', cpdr),
   'C8d computePnlDateRange is still pure (the PDF builder loops period keys)')
ok('_pnlSuppressDeltas = (v ===' in fn('getChewyPnlDateRange'),
   'C8e the suppression flag is set in the DOM-reading entry point, as on Amazon')

# Restore + readout are wired at the one place every Chewy tab goes through.
sw = fn('switchChewyPnlView')
ok('if (!_chewyPeriodRestored) chewyPeriodRestore();' in sw,
   'C9  the stored period is restored on first entry into any Chewy tab')
ok('chewyPeriodRenderState();' in sw,
   'C9b and the readout refreshes when the tab (and its date column) changes')
ok(sw.index('chewyPeriodRenderState();') < sw.index('const picked'),
   'C9c before the tab renders, so the readout cannot describe the previous tab')
ok('_chewyPeriodRestored = true;' in fn('chewyPeriodRestore'),
   'C9d and the guard is set inside the restore, so it runs exactly once')

# Program is actually scoped by it — a live-looking control that does nothing
# on one tab is the v10.19 lesson.
rp = fn('renderChewyProgram')
ok('getChewyProgramDateRange()' in rp, 'C10  the Program tab reads the shared window')
ok('from: _pgWin.from, to: _pgWin.to,' in rp,
   'C10b and hands it to the aggregator')
agg = fn('chewyProgramMonthly')
ok('const winFrom = opts.from || null;' in agg and 'const winTo = opts.to || null;' in agg,
   'C10c which accepts it')
ok('allMonths.forEach(r => { idx[r.month] = r; });' in agg,
   'C10d ⚠ the YoY index is built over ALL comparable months, not the windowed set')
ok('const months = allMonths.filter(r => r.inWindow);' in agg,
   'C10e while only the windowed months are shown')
ok('if (r.partial) return false;' in agg,
   'C10f and a part-month is held out of the pairing')

# The partial month has to be visible as one.
ok('part-month at the window edge' in rp,
   'C11  partial months are named on the coverage line')
ok('r.partial' in rp and 'Held out of the year-over-year pairing' in rp,
   'C11b and marked in the table with a tooltip saying why')
ok('No comparable month falls inside this period' in rp,
   'C12  an empty window says so, rather than sending Jason to the Uploads page')
ok('res.coverage.comparable.length' in rp,
   'C12b distinguished by whether comparable months exist at all')

# Registry-driven, never a hardcoded span.
ok('colspan="12"' not in fn('loadChewyProgram'),
   'C13  no hardcoded colspan in the Program loader')

# ⚠ The standing uppercase-U sweep. JS has no \U escape, so it renders as
# literal text (v10.20 / v10.36 / v11.00). Asserted on LIVE CODE, with the
# guard-the-guard that the warning comments survive.
bad = re.findall(r'\\U[0-9a-fA-F]{8}', live)
ok(not bad, 'C14  no uppercase-U escapes in live code', bad[:4])
ok('\\U0001f501' in js or 'uppercase' in js.lower(),
   'C14b guard-the-guard: the documented warning about them survives in a comment')

# Provenance.
ok('v11.02' in src, 'C15  v11.02 provenance marker present')
for marker in ('v11.01', 'v11.00', 'v10.79', 'v10.19'):
    ok(marker in src, 'C15b earlier provenance marker preserved: %s' % marker)

print('')
if fails:
    print('v11.02  %d FAILED' % len(fails))
    for f in fails:
        print('   - ' + f)
    sys.exit(1)
print('v11.02  ALL GREEN')
