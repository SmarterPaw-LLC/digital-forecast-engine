# -*- coding: utf-8 -*-
"""v11.04 - period-matched Chewy allowances.

Jason, on the Break-Even cost stack: "i don't think that is right. its based
on promotions we run (the rebates tab)."

He was pointing at something real. The invoices say MDF/Coop is structurally a
STANDING allowance (agreement 100-17384, charged on the full purchase base,
same implied base as Damages / Freight / Satisfaction in every period) rather
than promo funding - every actual promo is its own DEAL-xxxxxx with its own
date range. But chasing that down surfaced the defect underneath:

  THE STANDING STACK IS NOT STATIC, and the model treated it as static.

  2026-03-02 .. 2026-04-05   Damages, Auto Ship                     7.00%
  2026-04-06 .. 2026-05-03   Damages                                2.00%
  2026-05-04 .. 2026-05-31   Damages, Auto Ship                     7.00%
  2026-06-01 .. 2026-08-30   + Freight, MDF/Coop, Satisfaction     26.50%
  2026-08-31 .. 2026-10-04   same, Auto Ship not yet invoiced      21.50%

v11.05 ⚠ THE v11.04 PREMISE WAS WRONG AND THESE ASSERTIONS INVERTED.
v11.04 read "P2-P4 carry only a Damages line" as "the standing rate was 2%
then". Jason: "this did not change, i just only have the rebate invoices going
back to that date." The terms were always the full stack; the early periods are
INCOMPLETE UPLOADS. Blending them conflated MISSING INVOICES with a LOWER RATE,
and it failed in the DANGEROUS direction - a lower allowance overstates
contribution and reads break-even LOWER than reality, so a SKU that cannot pay
looks like it can. The flat rate was right all along.

What survives is the COVERAGE read: how much of a window has invoice backing,
as a provenance caveat that never touches the maths.

chewyPricingDeriveAllowances takes the LATEST rate per rebate name and applies
it to every unit in every window, so a 364-day window charged 26.50% against
months Chewy actually billed at 2-7%. That is 60 to 180 points of break-even
on the Chewy line, on the exact figure Blake challenged.

The assertions that earn their keep:

  * A5 THE REGRESSION GUARD. It reproduces the pre-v11.04 flat-rate lookup and
    proves it really did charge 26.5% on a week Chewy billed at 2%, where the
    periodised path charges 2%. "This was broken" is a checkable claim rather
    than something read off a diff.

  * A7 ABSENT A WINDOW THE RETURN IS BYTE-IDENTICAL to v11.03. The change is
    opt-in, and that is the only way to make "no caller changes behaviour by
    accident" checkable across eight call sites.

  * A4 UNCOVERED WEEKS ARE NOT FOLDED IN AT 0%. Rebate invoices only go back to
    2026-03-02, so a year-long window is ~40% dark. Averaging those weeks in at
    zero would read as a suspiciously CHEAP allowance rather than as missing
    data - a wrong number that looks like good news.

  * A6 THE PRICING SCENARIOS WORKING COPY STILL WINS. Someone modelling a promo
    over there must keep seeing their own rate, windowed or not.

  * B4 NO CALLER READS THE FLAT RATE. An unwindowed call is v11.03 behaviour.
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


# ===========================================================================
# A. BEHAVIOUR - the real sliced functions driven in node
# ===========================================================================
print('\n== A. the real resolver, driven ==')

# Jason's actual shape, trimmed to what the maths needs: Damages alone, then
# Damages + AutoShip, then the full five-line stack from P5-26. Two agreements
# overlap on purpose so the dedupe is exercised.
FIXTURE = """
const chewyPnlData = [
  // 100-17384 ALLOWANCES
  { agreement_period_start:'2026-04-06', agreement_period_end:'2026-05-03',
    rebate_name:'Damages', category:'damages', rebate_pct_rate:2 },
  { agreement_period_start:'2026-05-04', agreement_period_end:'2026-05-31',
    rebate_name:'Damages', category:'damages', rebate_pct_rate:2 },
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'Damages', category:'damages', rebate_pct_rate:2 },
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'Freight', category:'freight', rebate_pct_rate:1.5 },
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'MDF/Coop', category:'coop_marketing', rebate_pct_rate:16 },
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'Satisfaction', category:'satisfaction_guarantee', rebate_pct_rate:2 },
  // the SAME period invoiced twice - must not charge its own rate twice
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'MDF/Coop', category:'coop_marketing', rebate_pct_rate:16 },
  // 100-17477 AUTOSHIP, running in PARALLEL over an overlapping range
  { agreement_period_start:'2026-05-04', agreement_period_end:'2026-05-31',
    rebate_name:'Auto Ship', category:'autoship', rebate_pct_rate:5 },
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'Auto Ship', category:'autoship', rebate_pct_rate:5 },
  // a PROMO line - must never reach the standing floor
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-06-30',
    rebate_name:'HG Toys Buy 3 Get 1', category:'promo_bxgx', rebate_pct_rate:9 },
  // rate-less (the FTAS shape: rate lives in the NAME) - contributes nothing
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-06-30',
    rebate_name:'Treats 35% FTAS', category:'trade_allowance', rebate_pct_rate:null },
];
const chewyPnlSalesData = [
  { week_start:'2026-02-01', merch_sales:1000 },   // BEFORE any invoice: dark
  { week_start:'2026-04-12', merch_sales:1000 },   // Damages only      -> 2.0
  { week_start:'2026-05-10', merch_sales:1000 },   // + Auto Ship       -> 7.0
  { week_start:'2026-06-14', merch_sales:2000 },   // full stack        -> 26.5
];
let _chewyPricingAllow = null;
let _chewyPricingDerived = null;
let _chewyPricingSrcNote = '';
"""

HARNESS = "\n".join([
    FIXTURE,
    lift_const('CHEWY_STANDING_CATS'),
    lift_const('CHEWY_PROMO_CATS'),
    fn('chewyPricingDeriveAllowances'),
    fn('chewyAllowancePeriods'),
    fn('chewyStandingRateOn'),
    fn('chewyAllowanceBlend'),
    fn('chewyAllowanceStack'),
    """
const out = {};
const P = chewyAllowancePeriods();
out.periodCount = P.length;
out.rateApr = chewyStandingRateOn(P, '2026-04-12');
out.rateMay = chewyStandingRateOn(P, '2026-05-10');
out.rateJun = chewyStandingRateOn(P, '2026-06-14');
out.rateDark = chewyStandingRateOn(P, '2026-02-01');
out.rateEdgeFirst = chewyStandingRateOn(P, '2026-06-01');
out.rateEdgeLast  = chewyStandingRateOn(P, '2026-07-05');
out.rateDayAfter  = chewyStandingRateOn(P, '2026-07-06');

out.blendAll  = chewyAllowanceBlend(P, '2026-01-01', '2026-12-31');
out.blendJun  = chewyAllowanceBlend(P, '2026-06-01', '2026-06-30');
out.blendDark = chewyAllowanceBlend(P, '2026-01-01', '2026-02-28');

// THE REGRESSION GUARD: what v11.03 did. Latest rate per name, flat.
const flat = chewyAllowanceStack();
out.flatPct = flat.standingPct;
out.flatBlended = flat.blended;
out.flatKeys = Object.keys(flat).sort();

const win = chewyAllowanceStack({ from:'2026-04-06', to:'2026-05-31' });
out.winPct = win.standingPct;
out.winBlended = win.blended;
out.winUncoveredPct = win.uncoveredPct;
out.winObserved = win.observedRate;
out.winSource = win.source;
out.winKeys = Object.keys(win).sort();

// the Pricing Scenarios working copy must still win, windowed or not
// 9 + 3 = 12, deliberately distinct from BOTH the 4.5 blend and the 26.5
// flat rate, so "the edit won" cannot be confused with either.
_chewyPricingAllow = { damages: 9, coop_marketing: 3 };
_chewyPricingDerived = { damages: 2, coop_marketing: 1 };
const edited = chewyAllowanceStack({ from:'2026-04-06', to:'2026-05-31' });
out.editedPct = edited.standingPct;
out.editedSource = edited.source;
out.editedBlended = !!edited.blended;
_chewyPricingAllow = null; _chewyPricingDerived = null;

// degenerate shapes must not throw or leak NaN
out.emptyWindow = chewyAllowanceBlend(P, '2030-01-01', '2030-12-31');
out.noPeriods   = chewyAllowanceBlend([], '2026-01-01', '2026-12-31');
console.log(JSON.stringify(out));
""",
])

hpath = os.path.join(SP, 'test_v1104.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
r = subprocess.run(['node', hpath], capture_output=True, text=True)
if r.returncode != 0:
    print('HARNESS FAILED:\n' + (r.stderr or '')[:2500]); sys.exit(1)
res = json.loads(r.stdout)

# --- A1  periods are built and deduped -------------------------------------
eq('A1  the duplicate (period, name) invoice line is deduped', res['periodCount'], 9)

# --- A2  the rate in force on a day ----------------------------------------
eq('A2a Damages alone in April', res['rateApr'], 2)
eq('A2b Damages + Auto Ship in May, two agreements summed', res['rateMay'], 7)
eq('A2c the full five-line stack in June', res['rateJun'], 26.5)
ok(res['rateJun'] == 26.5,
   'A2d  the PROMO line is excluded from the standing floor (26.5, not 35.5)')
eq('A2e a day before any invoice is 0, not the latest rate', res['rateDark'], 0)

# --- A3  period edges are INCLUSIVE ----------------------------------------
eq('A3a the first day of a period is inside it', res['rateEdgeFirst'], 26.5)
eq('A3b the last day of a period is inside it', res['rateEdgeLast'], 26.5)
eq('A3c the day after falls out', res['rateDayAfter'], 0)

# --- A4  uncovered revenue is REPORTED, never folded in at 0% --------------
b = res['blendAll']
# covered weeks: 1000@2 + 1000@7 + 2000@26.5 = 2000+7000+53000 = 62000 / 4000
eq('A4a the OBSERVED rate is revenue-weighted over covered weeks',
   round(b['observedRate'], 2), 15.5)
ok('rate' not in b,
   'A4a2 and it is NOT called `rate`, so it cannot be charged by mistake')
eq('A4b the dark week is reported as uncovered, not averaged in at 0%',
   b['revUncovered'], 1000)
eq('A4c and its share is stated', round(b['uncoveredPct'], 1), 20.0)
ok(res['blendDark']['observedRate'] is None,
   'A4d a window with NO invoices at all returns null, not 0%')
eq('A4e and reports 100% uncovered', round(res['blendDark']['uncoveredPct'], 1), 100.0)
eq('A4f a single fully-covered month observes its own rate',
   round(res['blendJun']['observedRate'], 2), 26.5)

# --- A5  THE REGRESSION GUARD ----------------------------------------------
print('\n-- A5 THE GUARD: a window must not move the rate (the v11.04 bug) --')
eq('A5a the flat path charges the rate from the invoices', res['flatPct'], 26.5)
eq('A5b  !! a WINDOWED call charges the IDENTICAL rate',
   res['winPct'], res['flatPct'])
# v11.04 shipped 4.5% here, blended out of periods that are simply not
# uploaded. A cheaper allowance overstates contribution and reads break-even
# LOWER than reality, so a SKU that cannot pay looks like it can. This is the
# assertion that stops that coming back.
ok(res['winPct'] != 4.5,
   'A5c  and is NOT the v11.04 blend, which read missing invoices as cheap months',
   res['winPct'])
ok(res['winObserved'] is not None and round(res['winObserved'], 2) == 4.5,
   'A5d  the observed figure is still reported, just never charged',
   res['winObserved'])
ok(res['winObserved'] < res['winPct'],
   'A5e  and it sits BELOW the charged rate, which is why it had to stop being the rate')

# --- A6  the working copy still wins ---------------------------------------
eq('A6a an EDITED Pricing Scenarios stack still wins over the blend',
   res['editedPct'], 12)
eq('A6b and still reports itself as edited', res['editedSource'], 'edited')
ok(res['editedBlended'] is False,
   'A6c  and is not mislabelled as a period blend')

# --- A7  absent a window, byte-identical to v11.03 -------------------------
ok(res['flatBlended'] is False, 'A7a an unwindowed call is not blended')
eq('A7b and carries the v11.03 key set plus the blended flag',
   res['flatKeys'],
   sorted(['standingPct', 'promoPct', 'unclassifiedPct', 'byCat', 'source',
           'note', 'blended']))
eq('A7c  a windowed call keeps the SAME provenance - the rate did not change',
   res['winSource'], 'invoices')
eq('A7d  a window ADDS coverage keys and nothing else',
   [k for k in res['winKeys'] if k not in res['flatKeys']],
   sorted(['windowFrom', 'windowTo', 'revCovered', 'revUncovered',
           'uncoveredPct', 'observedRate']))
ok(isinstance(res['winUncoveredPct'], (int, float)),
   'A7e  the uncovered share is stated for the reader')
eq('A7f  and it is 0 on a window that IS fully covered',
   round(res['winUncoveredPct'], 1), 0.0)
eq('A7g  while a window spanning the dark week reports a real share',
   round(res['blendAll']['uncoveredPct'], 1), 20.0)

# --- A8  degenerate shapes --------------------------------------------------
ok(res['emptyWindow']['observedRate'] is None and res['emptyWindow']['uncoveredPct'] == 0,
   'A8a an empty window yields null and 0%, not NaN')
ok(res['noPeriods']['observedRate'] is None,
   'A8b no periods at all yields null rather than throwing')
_blob = json.dumps(res)
ok('NaN' not in _blob and 'Infinity' not in _blob and 'null,null' not in _blob,
   'A8c  nothing leaked NaN or Infinity')


# ===========================================================================
# B. STATIC - every consumer converted in the same commit (hard rule #5)
# ===========================================================================
print('\n== B. every Chewy surface resolves the stack over its own window ==')

for name in ('chewyAllowancePeriods', 'chewyStandingRateOn', 'chewyAllowanceBlend'):
    ok(js.count('function %s(' % name) == 1, 'B1  %s defined exactly once' % name)

CALLERS = {
    'openChewyBeAudit':         'getChewyBreakevenDateRange()',
    'renderChewyPnlSales':      'getChewyPnlSalesDateRange()',
    'renderChewyPnlCost':       'getChewyPnlCostDateRange()',
    'updateChewyPnlChart':      'getChewyPnlSalesDateRange()',
    'chewyProgramContribBySku': 'getChewyProgramDateRange()',
    'renderChewyBreakeven':     'getChewyBreakevenDateRange()',
    '_writeChewyBreakevenCSV':  'getChewyBreakevenDateRange()',
    '_writeChewyPnlCostCSV':    'getChewyPnlCostDateRange()',
}
for caller, resolver in CALLERS.items():
    kw = 'async function' if caller == 'updateChewyPnlChart' else 'function'
    body = fn(caller, kw=kw)
    ok('chewyAllowanceStack(%s)' % resolver in body,
       'B2  %s resolves the stack over %s' % (caller, resolver))

ok(js.count('chewyAllowanceStack()') == 0,
   'B3  NO caller reads the unwindowed flat rate (that IS v11.03 behaviour)')
ok(js.count('chewyAllowanceStack(') == len(CALLERS) + 1,
   'B4  exactly the eight surfaces plus the definition touch the resolver',
   js.count('chewyAllowanceStack('))

# The dedupe and the uncovered rule are the two places this can silently go
# wrong, so the reasoning has to survive in the source.
blend_body = fn('chewyAllowanceBlend')
ok('uncovered' in blend_body and 'revUncovered' in blend_body,
   'B5  the blend reports uncovered revenue rather than swallowing it')
stack_body = fn('chewyAllowanceStack')
ok('standingPct:  b.' not in stack_body and 'standingPct: b.' not in stack_body,
   'B5a !! the window NEVER assigns standingPct (the v11.04 bug)')
ok('observedRate' in blend_body and 'rate:' not in blend_body,
   'B5b  and the coverage read does not even expose a field called `rate`')
ok('covered > 0' in blend_body,
   'B6  and divides by COVERED revenue, not the window total')
per_body = fn('chewyAllowancePeriods')
ok('seen.has(k)' in per_body and "'|'" in per_body,
   'B7  periods dedupe on (period, name), so a re-invoiced period cannot double')
rate_body = fn('chewyStandingRateOn')
ok('CHEWY_STANDING_CATS.includes' in rate_body,
   'B8  only STANDING categories reach the floor')
ok('seen.has(p.name)' in rate_body,
   'B9  each rebate NAME counts once across overlapping agreements')


print('\n' + '-' * 58)
print('v11.04: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
