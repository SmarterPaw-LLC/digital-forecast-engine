# -*- coding: utf-8 -*-
"""
v11.01 — account-level Chewy program efficiency.

Jason: "i also want to not only consider this as performance ads - there are
new customers coming into and providing organic lift. we need to look at
program efficiency at the account level."

The Break-Even tab scores Chewy's own click attribution, which covers ~11% of
the units that actually sell. It structurally cannot answer "does the PROGRAM
pay?". This tab rolls the two feeds up by month:

    organic units = total sell-through - ad-attributed units

⚠ THE ASSERTION THAT EARNS ITS KEEP is the COMPARABLE-MONTHS rule. The
sell-through feed runs about two months behind the ad report (the v9.88 lag),
so a month with ads but no sell-through yet would compute
`organic = 0 - adUnits`, i.e. a large NEGATIVE organic figure, and the most
recent months would read as organic volume collapsing. That is a reporting
artefact that looks exactly like a real collapse. Only months present in BOTH
feeds may appear, and the lagging tail is NAMED rather than silently dropped.

⚠ THE SECOND ONE: year-over-year, not before/after. A before/after on the ad
ramp credits the ads with every seasonal and merchandising move in between.
Comparing the SAME CALENDAR MONTHS one year apart strips the seasonality out.
It still cannot separate ads from category growth, which is why the panel says
directional rather than causal — asserted, so the hedge cannot be dropped.

⚠ Contribution is summed at each SKU's OWN contribution per unit, never at a
blended average, and `pricedUnits` records how many units actually had an
economics row so the coverage is stated rather than assumed.
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
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, 'index.html')
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
    i = js.index('{', m.end() - 1)
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


# ═════════ A. the tab exists and is wired end to end ═════════
print('\nA. static — the sub-tab, panel, basis line and loader')

ok('id="chpnl-tab-program"' in src, 'A  Program sub-tab button exists')
ok('id="chpnl-view-program"' in src, 'A  Program panel exists')
ok("switchChewyPnlView('program')" in src, 'A  the button switches to it')
ok("{ key: 'program', panel: 'chpnl-view-program', btn: 'chpnl-tab-program'" in js,
   'A  registered in the TABS registry so the strip can route to it')
ok("program: ['Does the PROGRAM pay?" in js, 'A  carries a basis line (the v10.54 rule)')
ok('function loadChewyProgram' in js, 'A  has a loader')
ok('function renderChewyProgram' in js, 'A  has a renderer')
ok('function chewyProgramMonthly' in js, 'A  the arithmetic is a separate pure function')

# One glyph one concept (rule #2). The scales must not already mean something
# else, and no glyph may appear twice inside the Chewy strip.
strip = src[src.index('id="chpnl-tab-sales"'): src.index('id="chpnl-tab-basis"')]
glyphs = re.findall(r'>\s*([^\x00-\x7f])\s+[A-Z]', strip)
ok(len(glyphs) == len(set(glyphs)), 'A  no glyph repeats inside the Chewy sub-tab strip', glyphs)
ok(src.count('⚖') == 1, 'A  the scales glyph is used exactly once in the file',
   src.count('⚖'))

# Every data-bearing view must be exportable from the top-bar button.
ok('function downloadChewyProgramCSV' in js, 'A  has a CSV exporter')
ok("if (cv === 'program') return downloadChewyProgramCSV();" in js,
   'A  and the top-bar CSV button routes to it')

# Reuses the two caches the Sales and Break-Even tabs already fill rather than
# adding a third loader (hard rule #1).
LOAD = fn('loadChewyProgram')
ok('chewyPnlSalesData' in LOAD, 'A  loader reuses the Sales tab sell-through cache')
ok('loadChewyAdSpend' in LOAD, 'A  loader reuses the ad-spend loader')
ok('from(' not in LOAD, 'A  REGRESSION GUARD: no third hand-rolled query in the loader')

# Module-scope registry, like the other three Chewy tabs (v10.58), so the
# v10.53 vocabulary sweep can reach its labels.
ok('const CHEWY_PROGRAM_COLUMNS = [' in js, 'A  columns live in a module-scope registry')
REND = fn('renderChewyProgram')
ok('const COLS = CHEWY_PROGRAM_COLUMNS;' in REND,
   'A  the renderer reads that registry rather than a local copy')
REG = js[js.index('const CHEWY_PROGRAM_COLUMNS = ['):]
REG = REG[:REG.index(chr(10) + '];')]
PROG_LABELS = re.findall(r"label: '([^']*)'", REG)
VOCAB = js[js.index('const CHEWY_MEASURE_VOCAB'):]
VOCAB = VOCAB[:VOCAB.index(chr(10) + '};')]
for lbl in PROG_LABELS:
    ok("'%s':" % lbl in VOCAB, 'A  %r is declared in CHEWY_MEASURE_VOCAB' % lbl)
# Reused vocabulary rather than coined (rule #3): these three already had a
# meaning on the Sales tab and must NOT have been renamed here.
for lbl in ('Units', 'Ad Units', 'Autoship %', 'Merch Sales', 'Vendor Contrib'):
    ok(lbl in PROG_LABELS, 'A  reuses the existing label %r rather than coining one' % lbl)

# No hardcoded colspan: it must track the registry (the v10.82 rule).
ok('colspan="12"' not in REND and 'colspan="12"' not in LOAD,
   'A  no hardcoded colspan in the panel or its loader')
ok('CHEWY_PROGRAM_COLUMNS.length' in LOAD, 'A  the loader placeholder spans the registry')

# The hedge on the incrementality read is load-bearing and must stay.
ok('directional' in REND.lower(), 'A  the renderer states the read is directional')
ok('not causal' in REND.lower() or 'NOT CAUSAL' in REND,
   'A  and that it is not causal')

# Literal uppercase-U escapes are not JS escapes (the v10.36 trap). Scan LIVE
# code only - index.html carries a comment that quotes one to document a bug.
_BS = chr(92)
_UPAT = re.escape(_BS) + 'U0001[0-9a-fA-F]{4}'
ok(re.search(_UPAT, re.sub(r'//[^\n]*', '', js)) is None,
   'A  no literal uppercase-U escape survives in LIVE code')


# ═════════ B. behaviour — the real aggregator ═════════
print('\nB. behaviour — chewyProgramMonthly (the real function)')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok    ' + label); }
  else { F++; console.log('  FAIL  ' + label + ' - got ' + g + ', want ' + w); }
};
const near = (label, got, want, tol) => {
  if (got != null && Math.abs(got - want) <= (tol || 0.005)) { P++; console.log('  ok    ' + label); }
  else { F++; console.log('  FAIL  ' + label + ' - got ' + got + ', want ~' + want); }
};

AGG

const CONTRIB = { A: 2.00, B: 1.00 };          // $/unit
const BRANDS  = { A: 'Meowijuana', B: 'Kitty Ka-Zoom' };

// ── Hand-checkable base case. Two SKUs, two months.
//   2026-01: A 100u + B 50u = 150 units, retail 1000, contribution 100*2 + 50*1 = 250
//            ads: A 30u / $60, B 10u / $40  -> 40 ad units, $100 spend
//            organic 110, ad share 26.667%, TACOS 10%, program net 150
const sales = [
  { chewy_sku: 'A', week_start: '2026-01-05', units: 100, autoship: 40, merch_sales: 700 },
  { chewy_sku: 'B', week_start: '2026-01-19', units: 50,  autoship: 10, merch_sales: 300 },
  { chewy_sku: 'A', week_start: '2026-02-02', units: 200, autoship: 90, merch_sales: 1400 },
];
const ads = [
  { chewy_sku: 'A', date: '2026-01-07', direct_units: 30, spend: 60, direct_sales: 210, ntb_customers: 12, autoship_signups: 4 },
  { chewy_sku: 'B', date: '2026-01-20', direct_units: 10, spend: 40, direct_sales: 60,  ntb_customers: 3,  autoship_signups: 1 },
  { chewy_sku: 'A', date: '2026-02-11', direct_units: 70, spend: 150, direct_sales: 490, ntb_customers: 25, autoship_signups: 9 },
];
let r = chewyProgramMonthly({ salesRows: sales, adRows: ads, contribBySku: CONTRIB, brandBySku: BRANDS });
t('two comparable months', r.months.map(m => m.month), ['2026-01', '2026-02']);
const m1 = r.months[0];
t('total units sum across weeks + SKUs', m1.totalUnits, 150);
t('ad-attributed units', m1.adUnits, 40);
t('organic = total - ad-attributed', m1.organicUnits, 110);
near('ad share %', m1.adSharePct, 26.6667, 0.001);
t('autoship units', m1.autoshipUnits, 50);
near('autoship share %', m1.autoshipSharePct, 33.3333, 0.001);
t('retail sell-through', m1.retail, 1000);
t('contribution is summed at each SKU own rate', m1.contribution, 250);
t('spend', m1.spend, 100);
t('program net = contribution - spend', m1.programNet, 150);
near('TACOS = spend / retail', m1.tacosPct, 10);
t('NTB rolls up', m1.ntb, 15);
t('autoship signups roll up', m1.signups, 5);

// ── Totals.
t('totals span the comparable months only', r.totals.monthCount, 2);
t('total units', r.totals.totalUnits, 350);
t('total contribution', r.totals.contribution, 650);
t('total spend', r.totals.spend, 250);
t('total program net', r.totals.programNet, 400);
near('spend as a share of contribution', r.totals.spendShareOfContribPct, 250 / 650 * 100, 0.01);

// ══ THE COMPARABLE-MONTHS RULE ════════════════════════════════════════════
// The sell-through feed lags the ad report by about two months. A month with
// ads but no sell-through would compute organic = 0 - adUnits, so the most
// recent months would read as organic volume collapsing - a reporting artefact
// that looks exactly like a real collapse.
const lagAds = ads.concat([
  { chewy_sku: 'A', date: '2026-03-04', direct_units: 90, spend: 200, direct_sales: 630, ntb_customers: 30, autoship_signups: 10 },
]);
let lag = chewyProgramMonthly({ salesRows: sales, adRows: lagAds, contribBySku: CONTRIB, brandBySku: BRANDS });
t('a month with ads but no sell-through is EXCLUDED', lag.months.map(m => m.month), ['2026-01', '2026-02']);
t('and it is NAMED rather than silently dropped', lag.coverage.adOnly, ['2026-03']);
t('its spend is NOT in the totals (would overstate TACOS)', lag.totals.spend, 250);
t('no month reports a large negative organic figure',
  lag.months.every(m => m.organicUnits >= 0), true);
// The mirror: sell-through with no ads is excluded and named too, so a
// pre-ramp month cannot dilute TACOS to look artificially efficient.
const earlySales = sales.concat([
  { chewy_sku: 'A', week_start: '2025-11-03', units: 400, autoship: 150, merch_sales: 2800 },
]);
let early = chewyProgramMonthly({ salesRows: earlySales, adRows: ads, contribBySku: CONTRIB, brandBySku: BRANDS });
t('a month with sell-through but no ads is EXCLUDED', early.months.map(m => m.month), ['2026-01', '2026-02']);
t('and named', early.coverage.sellOnly, ['2025-11']);

// ⚠ A genuine feed disagreement is still surfaced, NOT clamped. Clamping
// organic at 0 would hide that the two feeds disagree for a month.
let dis = chewyProgramMonthly({
  salesRows: [{ chewy_sku: 'A', week_start: '2026-01-05', units: 10, autoship: 0, merch_sales: 70 }],
  adRows: [{ chewy_sku: 'A', date: '2026-01-07', direct_units: 25, spend: 50, direct_sales: 175 }],
  contribBySku: CONTRIB, brandBySku: BRANDS });
t('a real feed disagreement shows negative organic rather than being clamped',
  dis.months[0].organicUnits, -15);

// ── Contribution coverage is reported, not assumed.
let unpriced = chewyProgramMonthly({ salesRows: sales, adRows: ads,
  contribBySku: { A: 2.00 }, brandBySku: BRANDS });   // B has no economics row
t('an unpriced SKU still adds UNITS', unpriced.totals.totalUnits, 350);
t('but adds no contribution', unpriced.totals.contribution, 100 * 2 + 200 * 2);
t('and pricedUnits records the coverage', unpriced.totals.pricedUnits, 300);
near('priced share %', unpriced.totals.pricedSharePct, 300 / 350 * 100, 0.01);

// ── Brand filter narrows BOTH feeds, or organic would be computed against a
// total that still contained the other brand.
let kkz = chewyProgramMonthly({ salesRows: sales, adRows: ads, contribBySku: CONTRIB,
  brandBySku: BRANDS, brand: 'Kitty Ka-Zoom' });
t('brand filter: only that brand months', kkz.months.map(m => m.month), ['2026-01']);
t('brand filter: units', kkz.totals.totalUnits, 50);
t('brand filter: ad units', kkz.totals.adUnits, 10);
t('brand filter: organic', kkz.totals.organicUnits, 40);
t('brand filter: spend', kkz.totals.spend, 40);
t('brand filter: contribution at that SKU own rate', kkz.totals.contribution, 50);

// ══ YEAR-OVER-YEAR INCREMENTALITY ═════════════════════════════════════════
// Same calendar months one year apart. Built so the arithmetic is checkable:
//   2025-06: 1000 units, 100 ad units, $500 spend
//   2025-07: 1000 units, 100 ad units, $500 spend
//   2026-06: 1400 units, 500 ad units, $3000 spend
//   2026-07: 1400 units, 500 ad units, $3000 spend
//   delta units 800, delta ad units 800 -> incrementality 100%
//   contribution/unit 2.00 -> incremental contribution 1600 vs delta spend 5000
//   incremental ROI 32%, net -3400
const mk = (mo, u, au, sp) => ([
  { chewy_sku: 'A', week_start: mo + '-05', units: u, autoship: 0, merch_sales: u * 7 },
  { chewy_sku: 'A', date: mo + '-07', direct_units: au, spend: sp, direct_sales: au * 7, ntb_customers: au / 2 },
]);
const yrSales = [], yrAds = [];
for (const [mo, u, au, sp] of [['2025-06', 1000, 100, 500], ['2025-07', 1000, 100, 500],
                               ['2026-06', 1400, 500, 3000], ['2026-07', 1400, 500, 3000]]) {
  const [s1, a1] = mk(mo, u, au, sp);
  yrSales.push(s1); yrAds.push(a1);
}
let y = chewyProgramMonthly({ salesRows: yrSales, adRows: yrAds, contribBySku: { A: 2.00 }, brandBySku: { A: 'Meowijuana' } }).yoy;
t('yoy pairs the same calendar months', [y.months, y.priorMonths],
  [['2026-06', '2026-07'], ['2025-06', '2025-07']]);
t('yoy delta units', y.deltaUnits, 800);
t('yoy delta ad units', y.deltaAdUnits, 800);
t('yoy delta organic', y.deltaOrganic, 0);
t('yoy delta spend', y.deltaSpend, 5000);
near('incrementality = delta units / delta ad units', y.incrementalityPct, 100);
near('contribution per unit', y.contributionPerUnit, 2.00);
near('incremental contribution', y.incrementalContribution, 1600);
near('incremental ROI', y.incrementalRoiPct, 32);
near('net on the ramp', y.incrementalNet, -3400);

// Pure attribution shift: total flat while attribution grows -> 0%.
const shiftSales = [], shiftAds = [];
for (const [mo, u, au, sp] of [['2025-06', 1000, 100, 500], ['2025-07', 1000, 100, 500],
                               ['2026-06', 1000, 600, 3000], ['2026-07', 1000, 600, 3000]]) {
  const [s1, a1] = mk(mo, u, au, sp);
  shiftSales.push(s1); shiftAds.push(a1);
}
let shift = chewyProgramMonthly({ salesRows: shiftSales, adRows: shiftAds, contribBySku: { A: 2.00 }, brandBySku: { A: 'Meowijuana' } }).yoy;
near('flat total + growing attribution -> 0% incrementality', shift.incrementalityPct, 0);
t('and organic absorbs the whole shift', shift.deltaOrganic, -1000);

// Shrinking total while attribution grows -> NEGATIVE, not hidden.
const dropSales = [], dropAds = [];
for (const [mo, u, au, sp] of [['2025-06', 1000, 100, 500], ['2025-07', 1000, 100, 500],
                               ['2026-06', 800, 600, 3000], ['2026-07', 800, 600, 3000]]) {
  const [s1, a1] = mk(mo, u, au, sp);
  dropSales.push(s1); dropAds.push(a1);
}
let drop = chewyProgramMonthly({ salesRows: dropSales, adRows: dropAds, contribBySku: { A: 2.00 }, brandBySku: { A: 'Meowijuana' } }).yoy;
t('a shrinking total gives NEGATIVE incrementality rather than 0',
  drop.incrementalityPct < 0, true);

// ⚠ Divide-by-noise guard: a flat or shrinking ad-attributed base makes the
// ratio meaningless, so it must come back null rather than a huge number.
const sameSales = [], sameAds = [];
for (const [mo, u, au, sp] of [['2025-06', 1000, 100, 500], ['2025-07', 1000, 100, 500],
                               ['2026-06', 1400, 100, 500], ['2026-07', 1400, 100, 500]]) {
  const [s1, a1] = mk(mo, u, au, sp);
  sameSales.push(s1); sameAds.push(a1);
}
let same = chewyProgramMonthly({ salesRows: sameSales, adRows: sameAds, contribBySku: { A: 2.00 }, brandBySku: { A: 'Meowijuana' } }).yoy;
t('flat attribution -> incrementality null, not a divide-by-noise number',
  same.incrementalityPct, null);
t('and incremental ROI is null when spend did not move', same.incrementalRoiPct, null);

// Fewer than two same-month pairs -> no yoy block at all.
t('one month of history -> no yoy read',
  chewyProgramMonthly({ salesRows: sales, adRows: ads, contribBySku: CONTRIB, brandBySku: BRANDS }).yoy, null);

// ── Degenerate shapes must not throw or leak NaN.
const shapes = [
  { label: 'both feeds empty', o: { salesRows: [], adRows: [] } },
  { label: 'sales only', o: { adRows: [] } },
  { label: 'ads only', o: { salesRows: [] } },
  { label: 'no contribution map', o: { contribBySku: {} } },
  { label: 'no brand map with a brand filter', o: { brandBySku: {}, brand: 'Meowijuana' } },
  { label: 'null opts fields', o: { salesRows: null, adRows: null, contribBySku: null, brandBySku: null } },
  { label: 'rows with no date', o: { salesRows: [{ chewy_sku: 'A', units: 5 }], adRows: [{ chewy_sku: 'A', spend: 1 }] } },
  { label: 'zero retail (TACOS undefined)', o: { salesRows: [{ chewy_sku: 'A', week_start: '2026-01-05', units: 10, merch_sales: 0 }] } },
  { label: 'junk numerics', o: { salesRows: [{ chewy_sku: 'A', week_start: '2026-01-05', units: 'x', merch_sales: null }] } },
];
for (const sh of shapes) {
  let res = null, threw = false;
  try { res = chewyProgramMonthly(Object.assign({ salesRows: sales, adRows: ads, contribBySku: CONTRIB, brandBySku: BRANDS }, sh.o)); }
  catch (err) { threw = true; }
  const nums = res ? [res.totals.totalUnits, res.totals.contribution, res.totals.spend,
                      res.totals.programNet, res.totals.adSharePct, res.totals.tacosPct] : [];
  const leaked = nums.some(v => typeof v === 'number' && !isFinite(v));
  t('degenerate: ' + sh.label + ' - no throw, no NaN/Infinity', [threw, leaked], [false, false]);
}
// A zero-retail month must report TACOS as null, not Infinity.
let zr = chewyProgramMonthly({
  salesRows: [{ chewy_sku: 'A', week_start: '2026-01-05', units: 10, merch_sales: 0 }],
  adRows: [{ chewy_sku: 'A', date: '2026-01-07', direct_units: 2, spend: 50 }],
  contribBySku: CONTRIB, brandBySku: BRANDS });
t('zero retail -> TACOS null, never Infinity', zr.months[0].tacosPct, null);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""

code = harness.replace('AGG', fn('chewyProgramMonthly'))
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
    fh.write(code)
    path = fh.name
try:
    r = subprocess.run(['node', path], capture_output=True, text=True, encoding='utf-8')
    print(r.stdout.rstrip())
    if r.stderr.strip():
        print(r.stderr.strip()[:2000])
    ok(r.returncode == 0, 'B  node behaviour suite passed')
finally:
    os.unlink(path)


# ═════════ C. the shared-contribution chain ═════════
print('\nC. static — one contribution chain, not a fourth copy')

CB = fn('chewyProgramContribBySku')
# The Cost and Break-Even tabs both derive contribution the same way. A fourth
# copy of that arithmetic is how the v10.4 two-Trend-columns mistake happened,
# so this must call the shared helpers rather than re-deriving.
for h in ('chewyAllowanceStack', 'chewyCatalogFor', 'chewyCatalogPricePerEach',
          'chewyPnlCogs', 'chewyVendorUnitEcon'):
    ok(h + '(' in CB, 'C  reuses %s rather than re-deriving' % h)
ok('* (1 -' not in CB and '*(1-' not in CB,
   'C  REGRESSION GUARD: no inline allowance arithmetic (that is the helper job)')

# The CSV must name its own scope, including the hedge on the yoy figure.
CSV = fn('downloadChewyProgramCSV')
ok('# Chewy program efficiency' in CSV, 'C  CSV carries a context header')
ok('feed lag' in CSV, 'C  CSV names the lagging months when there are any')
ok('priced on' in CSV, 'C  CSV states the contribution coverage')
ok('DIRECTIONAL' in CSV, 'C  CSV repeats that the yoy read is directional')
ok('promptCsvName' in CSV, 'C  routes through the shared filename prompt')
ok('ufeff' in CSV, 'C  writes a UTF-8 BOM so Excel reads the encoding')
# Export must read a SNAPSHOT of what rendered, never recompute (the v8.00
# rule): a recompute could silently disagree with the panel it claims to export.
ok('chewyProgramExport' in CSV, 'C  exports the render snapshot')
ok('chewyProgramMonthly(' not in CSV,
   'C  REGRESSION GUARD: the exporter does NOT recompute behind the panel')

print('\n' + '=' * 60)
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v11.01 — all green')
