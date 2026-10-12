# -*- coding: utf-8 -*-
"""
v10.21 — contribution totals, sortable columns, and the window stated in dates.

Jason: "does this show contribution/unit and contribution total product? ...
i should be able to sort by any column" and "also what is the date range?"

Contribution per unit was already there under the name Non-Ad Profit. What was
missing: the totals, and anything POST-ad — which is the number a financial
control on ad spend actually turns on ("did this SKU make money after what we
spent on it", not "what could it have carried").

The sort tests matter more than they look. PostgREST hands back numeric()
columns as STRINGS, so a naive comparator sorts "9.99" above "100.00" and the
whole table quietly lies while looking sorted.
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


# ═════════ A. the contribution columns ═════════
print('\nA. contribution — per unit AND total, pre-ad AND post-ad')

cols = outcols(sqlfile)
for c in ['Non-Ad Profit', 'Contribution Total pre-ad',
          'Contribution per Unit post-ad', 'Contribution Total post-ad']:
    ok(c in cols, 'column present: %s' % c)

# Appended, not inserted — Blake's sheet consumes this CSV and I cannot see
# whether it reads by header or by position. Appending cannot break a
# positional reader; inserting mid-list would shift everything after it.
oldTail = ['Net Units window', 'Net Sales window']
for c in oldTail:
    ok(cols.index(c) < cols.index('Contribution Total pre-ad'),
       'the new columns come AFTER the pre-existing "%s"' % c)
ok(cols.index('Break Even ROAS') < cols.index('Contribution Total pre-ad'),
   'and after the whole original profit block')

# The pre-ad / post-ad distinction has to be visible, not implied — every
# other "Contribution" in this app (Amazon P&L) is already post-ad.
ok('pre-ad' in ' '.join(cols) and 'post-ad' in ' '.join(cols),
   'the names say which side of ad spend they sit on')
ok('before</em> ad spend' in src or 'before ad spend' in src,
   'the page explains that Non-Ad Profit is the pre-ad one')

# The maths, read out of the SQL rather than restated.
sqlNoC = re.sub(r'--[^\n]*', '', sqlfile)
ok(re.search(r'round\(\(price - total_cost\) \* net_units, 2\)\s*as "Contribution Total pre-ad"', sqlNoC) is not None,
   'pre-ad total = (price - total_cost) x net_units')
ok(re.search(r'total_ad_spend / nullif\(net_units,0\)', sqlNoC) is not None,
   'post-ad per unit subtracts ad spend per unit (nullif-guarded)')
ok(re.search(r'\* net_units - total_ad_spend, 2\)\s*as "Contribution Total post-ad"', sqlNoC) is not None,
   'post-ad total subtracts the whole window ad spend')

# Drift guard still holds after the edit.
m = re.search(r'const BREAKEVEN_SQL_BODY = `(.*?)`;\n', js, re.S)
ok(m is not None and outcols(m.group(1)) == cols,
   'the embedded SQL still matches the .sql file column for column')


# ═════════ B. the window, in dates ═════════
print('\nB. the window is stated in dates, not just days')

ok('breakevenWindow' in js, 'the resolved window is kept')
run = fn('runBreakeven')
ok('setDate(back.getDate() -' in run, 'it is derived from the win_days param on run')
rend = fn('renderBreakeven')
ok('weeks starting' in rend, 'the row-count line names the start date')
ok('breakevenWindow.from' in rend and 'breakevenWindow.to' in rend,
   'both ends are shown')

csv = fn('downloadBreakevenCSV')
ok('# Amazon break-even' in csv, 'the CSV carries a context line')
ok('trailing ${breakevenWindow.days}d' in csv, 'naming the window')
ok('finance rate' in csv and 'SOH target' in csv,
   'and the assumptions behind the numbers')
ok('Non-Ad Profit' in csv, 'and flags which contribution column is pre-ad')

# A hardcoded count in the button label drifts the moment a column is added,
# which is exactly what just happened.
ok(not re.search(r'CSV \(all \d+ columns\)', src),
   'the CSV button does not hardcode a column count')


# ═════════ C. sorting ═════════
print('\nC. behaviour — sort every column, on data PostgREST returns as strings')

h = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

// numeric() columns arrive as STRINGS over PostgREST. This is the whole point.
let breakevenRows = [
  { SKU:'A', Brand:'Meowijuana',   Price:'9.99',   Pct:'35.8', Flag:'',     Neg:'1644'  },
  { SKU:'B', Brand:'Doggijuana',   Price:'100.00', Pct:'51.0', Flag:'',     Neg:'-96'   },
  { SKU:'C', Brand:'Kitty Ka-Zoom',Price:'12.49',  Pct:null,   Flag:'LOW',  Neg:'-510'  },
  { SKU:'D', Brand:'Meowijuana',   Price:'7.99',   Pct:'',     Flag:'',     Neg:'25.1'  },
];
let breakevenSortKey = null, breakevenSortDir = -1;
function renderBreakeven() {}

HELPERS

const order = () => breakevenSortRows(breakevenRows).map(r => r.SKU);

// ── the bug a naive comparator has: lexical order puts "100.00" below "9.99".
breakevenSetSort('Price');
t('numeric desc on string data', order(), ['B','C','A','D']);
t('"100.00" really did beat "9.99"', order()[0], 'B');
breakevenSetSort('Price');
t('numeric asc', order(), ['D','A','C','B']);

// Negatives sort as numbers, not as text beginning with "-".
breakevenSortKey = null; breakevenSetSort('Neg');
t('negatives desc', order(), ['A','D','B','C']);
breakevenSetSort('Neg');
t('negatives asc', order(), ['C','B','D','A']);

// Text columns compare as text.
breakevenSortKey = null; breakevenSetSort('Brand');
t('text desc', order(), ['A','D','C','B']);
breakevenSetSort('Brand');
t('text asc', order(), ['B','C','A','D']);

// ── blanks sink BOTH ways. A column of dashes floating to the top is never
// what you asked for, whichever arrow you clicked.
breakevenSortKey = null; breakevenSetSort('Pct');
t('null + empty sink on desc', order().slice(2).sort(), ['C','D']);
breakevenSetSort('Pct');
t('null + empty sink on asc too', order().slice(2).sort(), ['C','D']);
t('and the real values still order correctly asc', order().slice(0,2), ['A','B']);

// A column that is numeric-looking but has one text value is treated as text,
// or the text row would silently sort as NaN.
t('a mixed column is text', breakevenIsNumericCol('Flag'), false);
t('a clean numeric column is numeric', breakevenIsNumericCol('Price'), true);
t('an all-blank column is not numeric', breakevenIsNumericCol('Nope'), false);

// Clicking the same column twice flips; a different column resets to desc.
breakevenSortKey = null;
breakevenSetSort('Price'); const d1 = breakevenSortDir;
breakevenSetSort('Price'); const d2 = breakevenSortDir;
breakevenSetSort('Brand'); const d3 = breakevenSortDir;
t('same column toggles direction', [d1, d2], [-1, 1]);
t('a new column resets to descending', d3, -1);

// No sort key = the SQL's own ORDER BY is preserved.
breakevenSortKey = null;
t('unsorted keeps the query order', order(), ['A','B','C','D']);

// Sorting must not mutate the source array.
breakevenSortKey = 'Price'; breakevenSortDir = -1; breakevenSortRows(breakevenRows);
t('the source rows are not reordered in place', breakevenRows.map(r => r.SKU), ['A','B','C','D']);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
h = h.replace('HELPERS', '\n'.join(
    fn(n) for n in ['breakevenSetSort', 'breakevenIsNumericCol', 'breakevenSortRows']))
tmp = os.path.join(tempfile.gettempdir(), 'test_v1021_sort.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(h)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip())
    fails.append('sort behaviour')

# Every header is a sort target, including ones only visible with audit on.
ok("onclick=\"breakevenSetSort(" in rend, 'every header carries a sort handler')
ok('cursor:pointer' in rend and 'user-select:none' in rend,
   'headers look and behave clickable')
ok('breakevenSortRows(rows)' in rend, 'the rendered rows go through the sorter')


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.21 — all green')
