# -*- coding: utf-8 -*-
"""v11.06 - the Auto Ship 5% is charged on AUTOSHIP revenue, not every unit.

Jason: "autoship cannot be assigned to every unit. not every unit is even
eligible."

The standing stack is not one rate. Four lines (Damages 2, Freight 1.5,
MDF/Coop 16, Satisfaction 2) are charged on EVERY invoice dollar. Auto Ship 5%
is charged on AUTOSHIP revenue only, and each SKU's autoship share runs 21% to
51% on the Chewy line - so charging it flat overstated the allowance on every
SKU, and by most on the ones that barely autoship at all.

Why the per-SKU share needs no approximation: within ONE SKU the autoship share
of UNITS *is* the share of REVENUE, because it is the same SKU at the same
price. The account level reconciles against the invoices:

    5% x 38.9% account autoship share   = 1.945%
    $6,210.11 invoiced / $318,910 rev   = 1.95%

The assertions that earn their keep:

  * A4 AN UNKNOWN SHARE FALLS BACK TO CHARGING THE LINE IN FULL, never to zero.
    Sell-through may not be loaded on the tab being rendered. Understating the
    allowance reads break-even LOWER than reality and makes a SKU that cannot
    pay look like it can - the same failure direction as v11.04, which is the
    one this codebase has already shipped once.

  * A6 THE ACCOUNT RECONCILIATION. Allocating 5% by per-SKU share must sum back
    to the account rate, or the split is moving money rather than placing it.

  * B3 NO CALLER PASSES THE FLAT RATE to a per-SKU econ function. That is the
    v11.05 shape of mistake: a correct number applied at the wrong grain.
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

def lift_const(name):
    i = js.index('const %s' % name)
    j = js.index(';', js.index('=', i))
    return js[i:j+1]


print('\n== A. the per-SKU standing rate, driven ==')

HARNESS = "\n".join([
    # Jason's real KKZ spread: 40.2% on Super Zoomies down to 21.1% on Spider.
    """
const chewyPnlSalesData = [
  { chewy_sku:'SZ', units_sold:5000, autoship_units:2000 },
  { chewy_sku:'SZ', units_sold:4496, autoship_units:1820 },   // -> 3820/9496 = 40.2%
  { chewy_sku:'SPIDER', units_sold:152, autoship_units:32 },  // -> 21.1%
  { chewy_sku:'NEVER',  units_sold:300, autoship_units:0   }, // -> 0%, not eligible
  { chewy_sku:'ALWAYS', units_sold:100, autoship_units:100 }, // -> 100%
  { chewy_sku:'ZEROVOL', units_sold:0, autoship_units:0 },    // no denominator
];
""",
    lift_const('CHEWY_STANDING_CATS'),
    lift_const('CHEWY_PROMO_CATS'),
    lift_const('CHEWY_CONDITIONAL_CATS'),
    fn('chewyAutoshipShareBySku'),
    fn('chewySkuStandingPct'),
    """
const STACK = { standingPct: 26.5, byCat: {
  damages:2, freight:1.5, coop_marketing:16, satisfaction_guarantee:2, autoship:5 } };
const out = {};
const sh = chewyAutoshipShareBySku();
out.shares = {};
Object.keys(sh).forEach(k => out.shares[k] = +(sh[k]*100).toFixed(1));
out.zeroVolExcluded = !Object.prototype.hasOwnProperty.call(sh, 'ZEROVOL');

const R = (sku) => +chewySkuStandingPct(STACK, sku, sh).toFixed(3);
out.sz      = R('SZ');
out.spider  = R('SPIDER');
out.never   = R('NEVER');
out.always  = R('ALWAYS');
out.unknown = R('NOT_ON_RECORD');
out.noMap   = +chewySkuStandingPct(STACK, 'SZ', null).toFixed(3);
out.noSku   = +chewySkuStandingPct(STACK, '', sh).toFixed(3);

// Account reconciliation: allocate by share, weight by units, sum back.
const rows = [['SZ',9496],['SPIDER',152],['NEVER',300],['ALWAYS',100]];
let wsum = 0, usum = 0, asu = 0, uu = 0;
rows.forEach(([k,u]) => { wsum += R(k)*u; usum += u;
  asu += (sh[k]||0)*u; uu += u; });
out.weightedRate   = +(wsum/usum).toFixed(3);
out.acctShare      = +(asu/uu).toFixed(4);
out.acctRateDirect = +(21.5 + 5*(asu/uu)).toFixed(3);

// a stack with NO autoship line must be untouched by the split
const noAs = { standingPct: 21.5, byCat: { damages:2, freight:1.5,
  coop_marketing:16, satisfaction_guarantee:2 } };
out.noAsLine = +chewySkuStandingPct(noAs, 'NEVER', sh).toFixed(3);
console.log(JSON.stringify(out));
""",
])

hpath = os.path.join(SP, 'test_v1106.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
r = subprocess.run(['node', hpath], capture_output=True, text=True)
if r.returncode != 0:
    print('HARNESS FAILED:\n' + (r.stderr or '')[:2500]); sys.exit(1)
res = json.loads(r.stdout)

# --- A1  shares -------------------------------------------------------------
eq('A1a Super Zoomies reads 40.2% autoship, summed across weeks',
   res['shares']['SZ'], 40.2)
eq('A1b Spider reads 21.1%', res['shares']['SPIDER'], 21.1)
eq('A1c a SKU with no autoship at all reads 0%', res['shares']['NEVER'], 0.0)
ok(res['zeroVolExcluded'],
   'A1d  a SKU with zero units is EXCLUDED, not divided by zero')

# --- A2  the rate scales with the share -------------------------------------
# 21.5 sitewide + 5 x share
eq('A2a Super Zoomies: 21.5 + 5x0.40228 = 23.511', res['sz'], 23.511)
eq('A2b Spider: 21.5 + 5x0.2105 = 22.553', res['spider'], 22.553)
eq('A2c a SKU with NO autoship carries the sitewide lines only', res['never'], 21.5)
eq('A2d a 100%-autoship SKU carries the full 26.5', res['always'], 26.5)
ok(res['never'] < res['spider'] < res['sz'] < res['always'],
   'A2e  the rate is monotonic in the autoship share')

# --- A3  the eligibility point Jason raised ---------------------------------
ok(res['never'] == 26.5 - 5,
   'A3  an ineligible SKU is not charged the autoship line AT ALL', res['never'])

# --- A4  unknown falls back to the FULL charge ------------------------------
print('\n-- A4 the safe direction: unknown share charges the line in FULL --')
eq('A4a a SKU not on the sell-through record charges the full stack',
   res['unknown'], 26.5)
eq('A4b no share map at all charges the full stack', res['noMap'], 26.5)
eq('A4c an empty sku charges the full stack', res['noSku'], 26.5)
ok(res['unknown'] > res['sz'],
   'A4d  the fallback is the EXPENSIVE direction, never the cheap one')

# --- A5  a stack with no autoship line is untouched -------------------------
eq('A5  a stack carrying no autoship line is returned unchanged',
   res['noAsLine'], 21.5)

# --- A6  THE RECONCILIATION -------------------------------------------------
print('\n-- A6 the account reconciliation: the split places money, never moves it --')
ok(abs(res['weightedRate'] - res['acctRateDirect']) < 0.01,
   'A6a units-weighted per-SKU rates sum back to the account rate',
   (res['weightedRate'], res['acctRateDirect']))
ok(abs(res['weightedRate'] - (21.5 + 5 * res['acctShare'])) < 0.001,
   'A6b  and equal 21.5 + 5 x the account autoship share',
   res['weightedRate'])


print('\n== B. every per-SKU econ call site uses the per-SKU rate ==')

ok(js.count('function chewyAutoshipShareBySku(') == 1,
   'B1a chewyAutoshipShareBySku defined once')
ok(js.count('function chewySkuStandingPct(') == 1,
   'B1b chewySkuStandingPct defined once')

for caller in ('renderChewyPnlCost', 'chewyProgramContribBySku', 'renderChewyBreakeven'):
    body = fn(caller)
    ok('chewySkuStandingPct(' in body,
       'B2  %s resolves a PER-SKU rate' % caller)
    ok('chewyAutoshipShareBySku()' in body,
       'B2b %s builds the share map' % caller)

# The v11.05 shape of mistake: a correct number at the wrong grain.
for caller, econ in (('renderChewyPnlCost', 'chewyVendorUnitEcon'),
                     ('chewyProgramContribBySku', 'chewyVendorUnitEcon'),
                     ('renderChewyBreakeven', 'chewyBreakevenEcon')):
    body = fn(caller)
    _i = body.index(econ + '('); _k = body.index('(', _i); _d = 0
    while True:
        if body[_k] == '(': _d += 1
        elif body[_k] == ')':
            _d -= 1
            if _d == 0: break
        _k += 1
    seg = body[_i:_k+1]
    ok('chewySkuStandingPct' in seg,
       'B3  %s passes the per-SKU rate into %s' % (caller, econ))
    ok(not re.search(r'[,{]\s*standingPct\s*[,}]', seg),
       'B3b %s no longer passes the bare flat standingPct' % caller)

# The share map must be built ONCE per render, not per row - 150 SKUs x a full
# walk of sell-through would be quadratic.
for caller in ('renderChewyPnlCost', 'chewyProgramContribBySku', 'renderChewyBreakeven'):
    ok(fn(caller).count('chewyAutoshipShareBySku()') == 1,
       'B4  %s builds the share map exactly once' % caller)

helper = fn('chewySkuStandingPct')
ok('return base' in helper and 'hasOwnProperty' in helper,
   'B5  the unknown-share fallback is explicit, not an accident of arithmetic')
ok('Math.max(0,' in helper,
   'B6  and the rate can never go negative')
share_fn = fn('chewyAutoshipShareBySku')
ok('Math.min(1,' in share_fn,
   'B7  a share above 1 is clamped (autoship units can exceed units on a restated week)')


print('\n' + '-' * 58)
print('v11.06: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
