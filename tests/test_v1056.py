# -*- coding: utf-8 -*-
r"""v10.56 - one rule for how tall a main data table may be.

Jason: "the window doesn't display at the bottom despite the vertical height
being taller enough." The Chewy Break-Even table was capped at a hardcoded
520px, so on a tall monitor it cut off mid-row with dead space underneath.

The hardcoded cap was not the bug on its own - the bug is that there were ~20
hardcoded max-heights across the file and exactly ONE viewport-relative value
(Inventory Planning, v4.158). That divergence is the same shape as the four
scorecard markups v10.49 consolidated: a pattern existing in several places with
different values, so every new table picks a fresh magic number.

This suite pins the consolidation, not the pixel values.
"""
import io, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()
JS  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)
MARKUP = RAW.replace(JS, ' ' * len(JS))

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)


# ============ A. one helper, declared once ============
print('A. static - one helper decides the height')

ok(JS.count('function fitTableWrapsToViewport()') == 1,
   'fitTableWrapsToViewport is declared exactly once',
   JS.count('function fitTableWrapsToViewport()'))
ok(JS.count('function fitTableWrapsSoon()') == 1,
   'the deferred variant is declared exactly once')
ok('const TBL_FIT_GUTTER' in JS and 'const TBL_FIT_MIN' in JS,
   'the gutter and the floor are named constants, not inline magic numbers')
ok("window.addEventListener('resize'" in JS and 'fitTableWrapsToViewport' in
   JS[JS.index("window.addEventListener('resize'"):JS.index("window.addEventListener('resize'") + 200],
   'it re-fits on window resize')
ok('if (!el.offsetParent) return;' in JS,
   'a hidden tab is skipped (its rect would be 0 and the cap would collapse)')
ok('TBL_FIT_MIN' in JS and 'Math.max(TBL_FIT_MIN' in JS,
   'a floor guard stops a short window collapsing the table to a sliver')


# ============ B. every MAIN table opts in ============
print('\nB. static - every main data table is marked, and only those')

marked = re.findall(r'class="tbl-wrap" data-fit="viewport"', MARKUP)
ok(len(marked) >= 9, 'the main data tables are marked data-fit="viewport"', len(marked))

# each marked wrap must be the one wrapping a known main tbody
MAIN_TBODIES = ['pnl-tbody', 'spnl-tbody', 'wmpnl-tbody', 'chpnl-sales-tbody',
                'chpnl-cost-tbody', 'chpnl-be-tbody', 'chpnl-tbody', 'cogs-tbody']
missing = []
for tb in MAIN_TBODIES:
    i = MARKUP.find('id="%s"' % tb)
    if i < 0: missing.append(tb + ' (no such tbody)'); continue
    # walk back to the nearest preceding tbl-wrap
    j = MARKUP.rfind('class="tbl-wrap"', 0, i)
    if j < 0 or 'data-fit="viewport"' not in MARKUP[j:j + 60]:
        missing.append(tb)
ok(not missing, 'every main P&L / COGS table sits in a marked wrap', missing or None)

# the small nested wraps (modals, side panels) keep their deliberate short scroll
short = re.findall(r'class="tbl-wrap"(?! data-fit)[^>]*max-height:(\d+)px', MARKUP)
ok(len(short) >= 5,
   'small nested wraps are deliberately NOT marked (short scroll is intended)',
   len(short))


# ============ C. the hardcoded caps on main tables are gone ============
print('\nC. static - no main table still carries a hardcoded cap')

stuck = []
for m in re.finditer(r'class="tbl-wrap" data-fit="viewport"[^>]*', MARKUP):
    tag = m.group(0)
    mm = re.search(r'max-height:\s*(\d+)px', tag)
    if mm: stuck.append(mm.group(1) + 'px')
ok(not stuck,
   'no marked wrap keeps a hardcoded pixel cap in its style attribute',
   stuck or None)

# Inventory Planning's calc() was the ONE viewport-relative value in the app.
# It is folded into the same mechanism rather than left as a second rule.
inv = re.search(r'class="tbl-wrap" data-fit="viewport"[^>]*calc\(100vh', MARKUP)
ok(inv is not None,
   "Inventory Planning's v4.158 calc() is folded into the same mechanism")


# ============ D. it is actually called ============
print('\nD. static - the helper is wired at every surface that paints a table')

for fn in ['switchChewyPnlView', 'switchPnlView', 'switchForecastView']:
    i = JS.find('function %s(' % fn)
    ok(i > 0 and 'fitTableWrapsSoon()' in JS[i:i + 400],
       '%s re-fits when a tab becomes visible' % fn)

RENDERS = ['renderChewyPnlSales', 'renderChewyPnlCost', 'renderChewyBreakeven',
           'renderChewyPnl', 'renderPnl', 'renderShopifyPnl', 'renderWalmartPnl',
           'renderCogsTbl', 'renderInventoryTbl']
calls = JS.count('fitTableWrapsSoon()')
ok(calls >= len(RENDERS) + 3,
   'every render that paints a marked table re-fits at its tail (%d call sites)' % calls,
   calls)

# Call sites sit textually ABOVE the declaration (switchPnlView and friends are
# defined earlier in the file). That is safe because this is a function
# DECLARATION, which hoists - but only as long as it stays one. An arrow
# assigned to a const would be in the temporal dead zone and every one of those
# earlier call sites would throw.
ok(re.search(r'\nfunction fitTableWrapsToViewport\(\)', JS) is not None,
   'the helper is a hoisted function declaration, not a const arrow')
ok(re.search(r'\nfunction fitTableWrapsSoon\(\)', JS) is not None,
   '  and so is the deferred variant')
# The two consts are NOT hoisted, so they may only be read from inside the
# function body (which runs long after parse), never at module scope.
_decl = JS.index('const TBL_FIT_GUTTER')
_body = JS.index('function fitTableWrapsToViewport()')
ok(_decl < _body,
   '  and the constants initialise before the body that reads them')


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d): %s' % (F, ', '.join(fails[:8])))
    sys.exit(1)
print('v10.56 - all green (%d static assertions)' % P)
