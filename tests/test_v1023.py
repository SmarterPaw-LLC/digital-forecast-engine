# -*- coding: utf-8 -*-
"""
v10.23 — Stock Forward Cover Months, and a coverage check against Blake's ask.

Blake Anderssen's original request (25 Sep 2026) is an explicit 18-column list.
Until now I had the query that was built from it but not the list itself, so
"does this answer his questions" was unanswerable. It is answerable now, and
section A is that check: every column he named, asserted by name.

Seventeen were already produced. The one that was not:

    Stock Forward Cover Months (SOH / next 6 months average FORECAST sales)

which is a different question from "Stock Cover Months" (SOH / last 3 months
ACTUAL sales) — backward-looking cover existed, forward-looking did not.

It is computed in JS rather than SQL on purpose. The forward number is
forwardSeaDemand(), which walks each product's own seasonal curve day by day,
and that curve is resolved in JS with a category-default fallback. A SQL port
would be a second implementation of the forecast the whole app runs on — the
same mistake v10.22 had just finished cleaning up.
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
QFILE = os.path.join(ROOT, 'query_amazon_breakeven_acos.sql')
src = io.open(INDEX, encoding='utf-8', newline='').read()
js = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', src, re.S), key=len)
sqlfile = io.open(QFILE, encoding='utf-8', newline='').read()

fails = []
def ok(cond, label):
    if cond:
        print('  ok  ' + label)
    else:
        print('  FAIL ' + label)
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


def outcols(text):
    return re.findall(r'as "([^"]*)"', re.sub(r'--[^\n]*', '', text))


# ═════════ A. Blake's list, column by column ═════════
print("\nA. coverage — Blake's 25 Sep 2026 request, item by item")

cols = outcols(sqlfile)
jsCols = cols + ['Stock Forward Cover Months']   # the one the page adds

# His list verbatim, mapped to the column that answers it.
BLAKE = [
    ('SKU',                              'SKU'),
    ('Product Title',                    'Product Title'),
    ('Price',                            'Price'),
    ('Refunds%',                         'Refunds pct'),
    ('Refund Cost',                      'Refund Cost'),
    ('AMZN FBA Fee',                     'AMZN FBA Fee'),
    ('Should be FBA Fee',                'Should be FBA Fee'),
    ('Referral Fees',                    'Referral Fees'),
    ('COGS+Shipping+Storage',            'COGS+Shipping+Storage'),
    ('Finance cost Adjustment',          'Finance cost Adjustment'),
    ('Total Cost',                       'Total Cost'),
    ('Non-Ad Profit (max ad spend)',     'Non-Ad Profit'),
    ('Break Even ACOS',                  'Break Even ACOS pct'),
    ('Break Even ROAS',                  'Break Even ROAS'),
    ('Stock Cover Months (3mo actual)',  'Stock Cover Months'),
    ('Stock Forward Cover Months (6mo forecast)', 'Stock Forward Cover Months'),
    ('SOH Target Assumption',            'SOH Target Assumption Months'),
    ('Excess Stock',                     'Excess Stock'),
]
for asked, col in BLAKE:
    ok(col in jsCols, 'Blake asked for "%s" -> column "%s"' % (asked, col))

# Named in the body of his email rather than the list.
ok('Daily Sales Velocity' in cols,
   'body: "daily sales velocity per SKU" for the supply-chain tool')
for c in ['Size Tier', 'Pkg Weight', 'Longest Side', 'Median Side', 'Shortest Side', 'Dim Unit']:
    ok(c in cols, 'body: "product dims and the tiers" -> %s' % c)

# ⚠ His parenthetical on Non-Ad Profit is "MAX WE CAN SPEND ON ADS FOR PROFIT".
# That confirms it is deliberately BEFORE ad spend — it is an ad budget ceiling,
# not a profit figure. v10.21 briefly reframed it as a contribution variant;
# v10.22 put it back. It must stay pre-ad.
sqlNoC = re.sub(r'--[^\n]*', '', sqlfile)
ok(re.search(r'round\(price - total_cost, 4\)\s*as "Non-Ad Profit"', sqlNoC) is not None,
   'Non-Ad Profit is price - total_cost (ad spend excluded, as he intends)')
ok('total_ad_spend' not in re.search(
      r'round\(coalesce\(c\.refund_cost_pu.*?as total_cost', sqlNoC, re.S).group(0),
   'and total_cost itself carries no ad spend')


# ═════════ B. the forward-cover column ═════════
print('\nB. Stock Forward Cover Months')

ok("BREAKEVEN_FWD_COL = 'Stock Forward Cover Months'" in js, 'the column is named')
ok('BREAKEVEN_FWD_MONTHS = 6' in js, 'the horizon is 6 months, as he asked')
ok('Stock Forward Cover Months' not in cols,
   'it is NOT in the SQL (the forecast lives in JS)')

enrich = fn('breakevenAttachForwardCover')
# ⚠ Amazon velocity, not blended. SOH is the FBA pool.
ok('invAmazonVel(rec)' in enrich,
   'uses AMAZON velocity, not blended — SOH is the FBA pool')
ok('blended_daily: amzVel' in enrich,
   'and feeds it through the seasonal curve as the daily rate')
ok('forwardSeaDemand(' in enrich,
   'forward demand comes from the same function the rest of the app uses')
ok('/ BREAKEVEN_FWD_MONTHS' in enrich, 'divided to a monthly average')

run = fn('runBreakeven')
ok('breakevenAttachForwardCover()' in run, 'runs after every query')

# It must reach the CSV, or Blake still has to build the column himself.
csv = fn('downloadBreakevenCSV')
ok('breakevenCols' in csv and 'breakevenCols.push' in enrich,
   'the column is appended to breakevenCols, so the CSV carries it')


# ═════════ C. behaviour ═════════
print('\nC. behaviour — the real enrichment function')

h = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

let breakevenRows = [], breakevenCols = [], breakevenFwdStats = null;
let records = [];
// Flat curve => forwardSeaDemand is just rate x days, so the arithmetic is
// hand-checkable. The seasonal path is exercised by its own suites.
let VEL = {};
function invAmazonVel(r) { return VEL[r.asin] ?? 0; }
function forwardSeaDemand(r, days) { return (r.blended_daily || 0) * days; }

ENRICH

const setup = (rows, recs, vel) => {
  breakevenRows = rows; breakevenCols = ['ASIN', 'SOH total'];
  records = recs; VEL = vel; breakevenFwdStats = null;
  breakevenAttachForwardCover();
};

// 1,800 units on hand, 10/day Amazon => 1,800 / (10*180/6) = 6.00 months.
setup([{ ASIN: 'B1', 'SOH total': '1800' }], [{ asin: 'B1', region: 'US' }], { B1: 10 });
t('cover = SOH / (6mo forecast / 6)', breakevenRows[0]['Stock Forward Cover Months'], 6);
t('the column is registered once', breakevenCols.filter(c => c === 'Stock Forward Cover Months').length, 1);
t('and it reaches breakevenCols so the CSV gets it',
  breakevenCols.includes('Stock Forward Cover Months'), true);

// Half the demand = double the cover. Sanity that it is a ratio, not a constant.
setup([{ ASIN: 'B1', 'SOH total': '1800' }], [{ asin: 'B1', region: 'US' }], { B1: 5 });
t('halving demand doubles the cover', breakevenRows[0]['Stock Forward Cover Months'], 12);

// ── the two blank causes are distinguished, because they need different fixes.
setup([{ ASIN: 'B9', 'SOH total': '500' }], [{ asin: 'B1', region: 'US' }], { B1: 10 });
t('no catalog record -> blank', breakevenRows[0]['Stock Forward Cover Months'], null);
t('and counted as noRec', breakevenFwdStats.noRec, 1);

setup([{ ASIN: 'B1', 'SOH total': '500' }], [{ asin: 'B1', region: 'US' }], { B1: 0 });
t('no Amazon demand -> blank, not Infinity', breakevenRows[0]['Stock Forward Cover Months'], null);
t('and counted separately as noDemand', breakevenFwdStats.noDemand, 1);

// Zero stock is a real answer (0 months), not a gap.
setup([{ ASIN: 'B1', 'SOH total': '0' }], [{ asin: 'B1', region: 'US' }], { B1: 10 });
t('zero stock reads 0 months, not blank', breakevenRows[0]['Stock Forward Cover Months'], 0);
t('and is not counted as a gap', [breakevenFwdStats.noRec, breakevenFwdStats.noDemand], [0, 0]);

// ⚠ This view is US only. A CA record must not be used to cover a US SOH.
setup([{ ASIN: 'B1', 'SOH total': '1800' }], [{ asin: 'B1', region: 'CA' }], { B1: 10 });
t('a CA-only record does not satisfy a US row', breakevenRows[0]['Stock Forward Cover Months'], null);
setup([{ ASIN: 'B1', 'SOH total': '1800' }], [{ asin: 'B1', region: 'US+CA' }], { B1: 10 });
t('a pooled US+CA record does count', breakevenRows[0]['Stock Forward Cover Months'], 6);

// First US record wins rather than the last, so the result is stable.
setup([{ ASIN: 'B1', 'SOH total': '1800' }],
      [{ asin: 'B1', region: 'US' }, { asin: 'B1', region: 'US' }], { B1: 10 });
t('duplicate records do not double-count', breakevenRows[0]['Stock Forward Cover Months'], 6);

// A throwing forecast must not take the whole run down.
setup([{ ASIN: 'B1', 'SOH total': '1800' }], [{ asin: 'B1', region: 'US' }], { B1: 10 });
const realFwd = forwardSeaDemand;
forwardSeaDemand = () => { throw new Error('bad curve'); };
let threw = false;
try { breakevenAttachForwardCover(); } catch (e) { threw = true; }
forwardSeaDemand = realFwd;
t('a throwing forecast is caught', threw, false);
t('and that row reads blank', breakevenRows[0]['Stock Forward Cover Months'], null);

// Empty result set is a no-op.
setup([], [], {});
t('no rows -> no column invented', breakevenCols.includes('Stock Forward Cover Months'), false);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
# The two consts are module-level, so fn() does not capture them. Lift them out
# of the source rather than restating their values here — a changed horizon
# must break this test, not silently pass against a stale copy.
consts = '\n'.join(
    re.search(r'^const %s = [^\n]*$' % k, js, re.M).group(0) for k in
    ['BREAKEVEN_FWD_COL', 'BREAKEVEN_FWD_MONTHS'])
h = h.replace('ENRICH', consts + '\n' + enrich)
tmp = os.path.join(tempfile.gettempdir(), 'test_v1023_fwd.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(h)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip())
    fails.append('forward-cover behaviour')


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.23 — all green')
