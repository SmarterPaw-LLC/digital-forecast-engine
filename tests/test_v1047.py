# -*- coding: utf-8 -*-
r"""v10.47 — Net Units is a scorecard on the Amazon P&L, not a sub-line.

Jason: "i can't see total number of units sold here."

Static only. The scorecard strip is built from a plain array literal inside
renderPnl (3,000+ lines, DOM- and Supabase-bound), so slicing it would mean
stubbing most of the P&L. What matters here is cheap to pin: the card exists,
it reads the same field the table sums, its delta compares like for like, and
the number now lives in exactly ONE place.
"""
import io, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

P = F = 0
def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))

print('A. the card exists and reads the right field')

ok("label:'Net Units'" in js, 'the Amazon P&L has a Net Units scorecard')
ok('val: Math.round(view.units).toLocaleString()' in js,
   '  and its value is the same view.units the product table sums')
ok('pnlDeltaChip(view.units, prevView.units, true, false, prevLabel)' in js,
   '  with a vs-prev delta built from the prior period of the SAME comparison set')
ok('units:0' in js.replace(' ', '').replace('\n', ''),
   '  and pnlTotalsForRange carries units, so the delta is not comparing against 0')

# goodWhenUp must be true: more units is favourable. A copy-paste from a cost
# card would make growth render red.
m = re.search(r"pnlDeltaChip\(view\.units, prevView\.units, (\w+),", js)
ok(bool(m) and m.group(1) == 'true', '  and a rise reads green, not red (goodWhenUp)')

print('\nB. the number lives in exactly one place')

ok('${Math.round(view.units).toLocaleString()} net units' not in js,
   'Gross Sales no longer carries the unit count in its sub-line')
ok("sub: `before returns`" in js and "sub: `after returns`" in js,
   '  Gross / Net Sales now say what distinguishes them instead')
ok(js.count('val: Math.round(view.units).toLocaleString()') == 1,
   'the unit total is rendered from one site')

print('\nC. ASP uses the existing vocabulary, not a coined one')

ok('const aspNow' in js and 'view.net_sales     / view.units' in js,
   'the sub-line is net sales / net units')
ok('`${$(aspNow)} ASP`' in js, '  labelled ASP, the name the Growth Model already uses')
ok('aspPrev' not in js, '  and no dead prev-period ASP left behind')

print('\nD. nine cards fit the grid')

ok('id="pnl-scorecards" style="display:grid;grid-template-columns:repeat(5,1fr)' in RAW,
   'the grid is 5 columns, so 9 cards land 5 + 4')
ok('id="pnl-scorecards" style="display:grid;grid-template-columns:repeat(4,1fr)' not in RAW,
   '  the old 4-column grid is gone (it would strand one card on its own row)')

# The banner rows span the full width; a column-count change must not break them.
ok(js.count('grid-column:1/-1') >= 2,
   '  the drill + COGS banners still span the full row')

print('\n' + ('=' * 60))
if F:
    print('FAILED: %d of %d' % (F, P + F)); sys.exit(1)
print('v10.47 — all green (%d assertions)' % P)
