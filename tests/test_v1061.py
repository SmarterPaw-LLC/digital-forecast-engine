# -*- coding: utf-8 -*-
r"""v10.61 - the markup must BALANCE. A stray </div> silently relocates pages.

Jason: "something got broken here - the 'select a product...' text only belongs
on the seasonal index page" + "also the p&L pages no longer load"

Both were ONE bug, and it was mine: v10.59's prose sweep collapsed four
multi-line info boxes into single tooltip divs but left their original </div>
closes behind. Five orphaned closes total.

The cascade is why this deserves a permanent guard:
  - the first orphan closed #page-seasonality early, so #sea-chart-msg,
    #sea-canvas-box and #sea-table-wrap became children of #page-forecast,
    and the "Select a product..." line rendered on EVERY forecast sub-view
  - the second then closed #page-forecast itself, so #page-inventory,
    #page-chewy-forecast and #page-fba-shipments became SIBLINGS of it at
    body level. Those are driven only by inline display, and nothing resets
    that when you leave the Forecast tab - so Inventory Planning stayed
    painted over the P&L page, which read as "P&L no longer loads"

Nothing caught it. `node --check` only sees JavaScript. All 44 suites passed.
The browser silently auto-corrects stray closes, so it looked plausible.

This is the v4.43 lesson ("the closing </div> for each page-X is unmarked -
verify nesting depth, don't trust comments") finally made runnable.
"""
import io, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)


def _blank(m):
    """Replace a match with spaces, PRESERVING newlines so line numbers stay
    usable in failure messages."""
    return re.sub(r'[^\n]', ' ', m.group(0))


def markup_only(html):
    """Strip HTML comments and <script> bodies. Both legitimately contain
    div markup (JS builds HTML in template literals) and would otherwise
    poison the count - this is why a naive grep-based check never worked."""
    out = re.sub(r'<!--.*?-->', _blank, html, flags=re.S)
    out = re.sub(r'(<script\b[^>]*>)(.*?)(</script>)',
                 lambda m: m.group(1) + _blank(re.match(r'(?s).*', m.group(2))) + m.group(3),
                 out, flags=re.S)
    return out


CLEAN = markup_only(RAW)
LINES = CLEAN.split('\n')
ORIG = RAW.split('\n')


def depth_trace():
    """Yield (line_no, depth_before, depth_after) for every line."""
    d = 0
    for i, line in enumerate(LINES):
        o = len(re.findall(r'<div\b', line, re.I))
        c = len(re.findall(r'</div>', line, re.I))
        d0 = d
        d += o - c
        yield i + 1, d0, d


# ============ A. the whole document balances ============
print('A. structural - <div> balance across the document')

trace = list(depth_trace())
final = trace[-1][2] if trace else None
ok(final == 0,
   'every <div> in the markup is closed exactly once (final depth 0)', final)

negatives = [(ln, d0, d1, ORIG[ln - 1].strip()[:70]) for ln, d0, d1 in trace if d1 < 0]
ok(not negatives,
   'depth never goes negative (no orphaned </div>)',
   negatives[:3] or None)

# guard the guard: a planted stray close must be detected
planted = markup_only('<div><div>x</div></div></div>')
pd = 0
for line in planted.split('\n'):
    pd += len(re.findall(r'<div\b', line, re.I)) - len(re.findall(r'</div>', line, re.I))
ok(pd == -1, '  and the detector catches a planted stray </div>', pd)

planted2 = markup_only('<div><div>x</div>')
pd2 = 0
for line in planted2.split('\n'):
    pd2 += len(re.findall(r'<div\b', line, re.I)) - len(re.findall(r'</div>', line, re.I))
ok(pd2 == 1, '  and catches a planted unclosed <div>', pd2)

# comments / scripts must really be excluded, else the count is noise
ok('<div' not in markup_only('<!-- <div><div> -->'),
   '  HTML comments are excluded from the count')
ok('<div' not in markup_only('<script>var x = `<div></div><div>`;</script>'),
   '  <script> bodies are excluded from the count')


# ============ B. every top-level .page sits at body level ============
print('\nB. structural - page containers are where the nav expects them')

page_opens = []
for ln, d0, d1 in trace:
    line = LINES[ln - 1]
    if re.search(r'class="page(?: active)?"\s+id="page-[a-z-]+"', line) or \
       re.search(r'class="page(?: active)?" id="page-[a-z-]+"', line):
        m = re.search(r'id="(page-[a-z-]+)"', line)
        page_opens.append((m.group(1) if m else '?', ln, d0, d1))

ok(len(page_opens) >= 8,
   'found the top-level .page containers', len(page_opens))

misplaced = [(pid, ln, d0) for pid, ln, d0, d1 in page_opens if d0 != 0]
ok(not misplaced,
   'every .page opens at depth 0 (a direct child of <body>)',
   misplaced or None)


# ============ C. forecast sub-pages live INSIDE page-forecast ============
print('\nC. structural - forecast sub-views nest inside #page-forecast')

# These are NOT class="page" - they are plain divs toggled by inline display.
# If one escapes #page-forecast it becomes a body-level element that nothing
# hides when you switch tabs, which is exactly how Inventory Planning ended
# up painted over the P&L page.
SUBVIEWS = ['demand-view', 'page-seasonality', 'page-chewy-forecast',
            'page-inventory', 'page-fba-shipments']
found, bad = {}, []
for ln, d0, d1 in trace:
    m = re.search(r'<div[^>]*\bid="(%s)"' % '|'.join(SUBVIEWS), LINES[ln - 1])
    if m:
        found[m.group(1)] = (ln, d0, d1)
        if d0 != 1:
            bad.append((m.group(1), ln, d0))

missing = [s for s in SUBVIEWS if s not in found]
ok(not missing, 'every forecast sub-view container exists', missing or None)
ok(not bad,
   'every forecast sub-view opens at depth 1 (inside #page-forecast)',
   bad or None)


# ============ D. the seasonality chart elements stay in their own page ============
print('\nD. structural - seasonality chart parts are inside #page-seasonality')

# The literal regression Jason reported. These three were ejected to
# #page-forecast, so they rendered on Demand / Inventory / Chewy / FBA too.
sea_open = found.get('page-seasonality', (None,))[0]
ok(sea_open is not None, 'page-seasonality open line located')

# find its matching close by brace balance
sea_close = None
if sea_open:
    d = 0
    for ln in range(sea_open, len(LINES) + 1):
        line = LINES[ln - 1]
        d += len(re.findall(r'<div\b', line, re.I)) - len(re.findall(r'</div>', line, re.I))
        if d == 0:
            sea_close = ln
            break

ok(sea_close is not None, '  and its matching </div> is resolvable', sea_close)

for eid in ['sea-chart-wrap', 'sea-chart-legend-guide', 'sea-chart-msg',
            'sea-canvas-box', 'sea-table-wrap']:
    at = next((i + 1 for i, l in enumerate(LINES) if ('id="%s"' % eid) in l), None)
    inside = at is not None and sea_open is not None and sea_close is not None \
             and sea_open < at < sea_close
    ok(inside, '  #%s is inside #page-seasonality' % eid,
       None if inside else {'elementLine': at, 'pageRange': (sea_open, sea_close)})

# the legend guide is show/hidden by JS - it must still exist, because two
# call sites had been no-oping against a deleted element since v10.59
ok(RAW.count("getElementById('sea-chart-legend-guide')") == 2,
   '  the two JS show/hide call sites still have an element to find',
   RAW.count("getElementById('sea-chart-legend-guide')"))
ok(re.search(r'id="sea-chart-legend-guide"[^>]*style="display:none', RAW) is not None,
   '  and it starts hidden (shown only when a product is active)')


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d): %s' % (F, ', '.join(fails[:8])))
    sys.exit(1)
print('v10.61 - all green (%d structural assertions)' % P)
