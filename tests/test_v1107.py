# -*- coding: utf-8 -*-
"""v11.07 - the YoY prior-year side accepts a month with no ads.

Jason: "i don't know why your kitty kazoom is missing august and sept last
year."

KKZ ads ran May/June 2025, went dark July 2025 through February 2026, and came
back in March 2026. The v11.01 comparable-months rule keeps only months present
in BOTH feeds, so the dark months never entered the index and could not pair
with their 2026 twins. The KKZ incrementality read ran on 3 months, not 5.

That rule is right for the ROLL-UP - a pre-ramp month would dilute TACOS and
make the program look artificially efficient - and it still governs `months`
and `totals`. It is WRONG as a baseline filter: a zero-ad prior-year month is
the cleanest counterfactual an incrementality read can have, and excluding it
threw away exactly what the panel exists to measure.

The assertions that earn their keep:

  * A2 THE REGRESSION GUARD. It reproduces the pre-v11.07 index against Jason's
    exact KKZ shape and proves it really did find 3 pairs where the fix finds 5.

  * A4 THE CURRENT SIDE STILL REQUIRES ADS. Only the prior side relaxes. A
    current month with no ads has nothing to measure, and letting it in would
    turn the panel into a plain sell-through comparison wearing an ad label.

  * A6 THE ROLL-UP IS UNCHANGED. `months` and `totals` must still be built from
    the comparable set, or the pre-ramp dilution the original rule guards
    against comes straight back on the TACOS figure.
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

def eq(name, got, want):
    ok(got == want, name, None if got == want else got)

def fn(name, kw='function'):
    i = js.index('%s %s(' % (kw, name))
    k = js.index('(', i); d = 0
    while True:
        if js[k] == '(': d += 1
        elif js[k] == ')':
            d -= 1
            if d == 0: break
        k += 1
    j = js.index('{', k); d = 0; k = j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k+1]
        k += 1


print('\n== A. Jason\'s exact KKZ shape, driven through the real aggregator ==')

# Sell-through every month 2025-05 .. 2026-09.
# Ads: 2025-05, 2025-06, 2025-07 (rows but ZERO spend), then 2026-03 .. 2026-09.
# That 2025-07 zero-spend month is why the live tab read 3 and not 2.
FIXTURE = """
const SELL = [], ADS = [];
const MO = [];
for (let y = 2025, m = 5; !(y === 2026 && m === 10); ) {
  MO.push(y + '-' + String(m).padStart(2,'0'));
  m++; if (m === 13) { m = 1; y++; }
}
MO.forEach((mo, i) => {
  SELL.push({ week_start: mo + '-07', chewy_sku: 'S', units: 1000 + i * 10,
              units_sold: 1000 + i * 10, autoship: 400, autoship_units: 400,
              merch_sales: 10000 });
});
const AD_MONTHS = ['2025-05','2025-06','2025-07',
                   '2026-03','2026-04','2026-05','2026-06','2026-07','2026-08','2026-09'];
AD_MONTHS.forEach(mo => {
  const dark = mo.startsWith('2025');
  ADS.push({ date: mo + '-07', chewy_sku: 'S',
             direct_units: dark ? (mo === '2025-07' ? 0 : 30) : 600,
             spend: dark ? (mo === '2025-07' ? 0 : 150) : 1500,
             direct_sales: dark ? 300 : 6000,
             ntb_customers: dark ? 25 : 700, autoship_signups: dark ? 3 : 100,
             chewy_list_price: 10 });
});
const run = (o) => chewyProgramMonthly(Object.assign({
  salesRows: SELL, adRows: ADS, contribBySku: { S: 2 }, brandBySku: {} }, o || {}));
"""

HARNESS = "\n".join([
    fn('chewyProgramMonthly'),
    FIXTURE,
    """
const out = {};
const W = { from: '2025-10-27', to: '2026-10-27' };
const r = run(W);
out.yoyMonths      = r.yoy ? r.yoy.months : null;
out.yoyPriorMonths = r.yoy ? r.yoy.priorMonths : null;
out.yoyCount       = r.yoy ? r.yoy.monthCount : 0;
out.unitsPrior     = r.yoy ? r.yoy.unitsPrior : null;
out.adUnitsPrior   = r.yoy ? r.yoy.adUnitsPrior : null;
out.organicPrior   = r.yoy ? r.yoy.organicPrior : null;

// THE REGRESSION GUARD: rebuild the pre-v11.07 index (comparable months only)
// and pair against it exactly as v11.06 did.
const comparableSet = new Set(r.allMonths.map(x => x.month));
const oldPairs = r.months.filter(x => {
  if (x.partial) return false;
  const [y, m] = x.month.split('-');
  return comparableSet.has((Number(y) - 1) + '-' + m);
});
out.oldPairCount  = oldPairs.length;
out.oldPairMonths = oldPairs.map(x => x.month);

// The roll-up must be unchanged: comparable months only.
out.rollupMonths = r.months.map(x => x.month);
out.allMonths    = r.allMonths.map(x => x.month);

// A current month with NO ads must never enter the current side.
out.currentHasDarkMonth = r.months.some(x => x.month >= '2025-08' && x.month <= '2026-02');

// compare.year uses the same relaxed baseline, so "vs last year" means one thing.
out.cmpYearPaired     = r.compare && r.compare.year ? r.compare.year.paired : null;
out.cmpYearCandidates = r.compare && r.compare.year ? r.compare.year.candidates : null;
console.log(JSON.stringify(out));
""",
])

hpath = os.path.join(SP, 'test_v1107.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hpath], capture_output=True, text=True)
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:2500]); sys.exit(1)
R = json.loads(res.stdout)

# --- A1  the fix finds all five -------------------------------------------
eq('A1a the YoY read now pairs FIVE months', R['yoyCount'], 5)
eq('A1b and they are May through September 2026',
   R['yoyMonths'], ['2026-05','2026-06','2026-07','2026-08','2026-09'])
eq('A1c against their 2025 twins, including the two DARK months',
   R['yoyPriorMonths'], ['2025-05','2025-06','2025-07','2025-08','2025-09'])

# --- A2  THE REGRESSION GUARD ---------------------------------------------
print('\n-- A2 the regression guard: prove the old index really found 3 --')
eq('A2a the pre-v11.07 index pairs only THREE months', R['oldPairCount'], 3)
eq('A2b namely May to July 2026, exactly what the live tab showed',
   R['oldPairMonths'], ['2026-05','2026-06','2026-07'])
ok(R['yoyCount'] > R['oldPairCount'],
   'A2c  and the fix strictly widens the baseline, never narrows it')

# --- A3  the dark months carry real sell-through, zero ads ----------------
# prior units = 1000..1040 over 2025-05..09 (i = 0..4) = 5000 + 10*(0+1+2+3+4)
eq('A3a the prior side totals every month, dark ones included',
   R['unitsPrior'], 5100)
# ad units: 30 (May) + 30 (Jun) + 0 (Jul) + nothing for Aug/Sep
eq('A3b a dark month contributes ZERO ad units, not a gap', R['adUnitsPrior'], 60)
eq('A3c so its volume lands in organic where it belongs',
   R['organicPrior'], R['unitsPrior'] - R['adUnitsPrior'])

# --- A4  only the PRIOR side relaxes --------------------------------------
print('\n-- A4 the current side still requires ads --')
ok(R['currentHasDarkMonth'] is False,
   'A4a a zero-ad month never enters the CURRENT side')
for m in ('2025-08','2025-09','2025-10','2025-11','2025-12','2026-01','2026-02'):
    ok(m not in R['allMonths'],
       'A4b  %s stays out of the comparable set' % m)

# --- A5  the roll-up is untouched -----------------------------------------
print('\n-- A5 the roll-up still obeys the comparable-months rule --')
ok(all(m in R['allMonths'] for m in R['rollupMonths']),
   'A5a every rolled-up month is a comparable month')
ok(not any(m >= '2025-08' and m <= '2026-02' for m in R['rollupMonths']),
   'A5b  so a pre-ramp month cannot dilute TACOS', R['rollupMonths'])

# --- A6  compare.year uses the same baseline ------------------------------
ok(R['cmpYearPaired'] >= 5,
   'A6  compare.year pairs on the same relaxed baseline, so "vs last year" '
   'means one thing across the panel', R['cmpYearPaired'])


print('\n== B. static ==')
body = fn('chewyProgramMonthly')
ok('const priorIdx' in body, 'B1  priorIdx is built')
ok(body.count('priorIdx[') >= 3,
   'B2  and every prior-year lookup reads it', body.count('priorIdx['))
ok("prior = idx[" not in body and "return idx[" not in body,
   'B3  no prior-year lookup still reads the comparable-only index')
ok('noAdsInPeriod' in body,
   'B4  a relaxed baseline month is FLAGGED, so a caller can say why it has no spend')
ok(body.index('const comparable') < body.index('const priorIdx'),
   'B5  priorIdx is derived after the comparable set, not instead of it')
ok('sellMonths.forEach' in body,
   'B6  the relaxed side is built from SELL months, which is the baseline universe')

print('\n' + '-' * 58)
print('v11.07: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
