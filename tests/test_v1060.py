# -*- coding: utf-8 -*-
r"""v10.60 - ONE scorecard renderer, so a chip reaches every page.

Jason: "i asked for chips on EVERY page. please follow my isntructions"

He is right, and the reason is worth writing down: I was not forgetting a
strip. FIVE bespoke copies of the card markup existed, so annotating pnlCard
only ever reached the strips that CALL pnlCard. v10.49 consolidated seven P&L
strips and left these standing:

  renderPnlPerformance        tile(label,value,sub,valColor)   <- his screenshot
  renderPnlDiagnostics        tile(label,val,sub,color)        + left accent
  renderChewyRevisionTracker  tile(label,val,sub,color)        + left accent
  pnlGrowthRenderResult       sc(label,value,sub,tip,valColor)
  renderDigitalSales          inline tileBg/cardLabel/cardVal consts

So this suite does NOT assert "page X has a chip". It asserts the STRUCTURE
that makes a missing chip impossible: exactly one card renderer, every
scorecard builder declaring a source, and every wrapper forwarding it.

That last one is the v10.57 bug class - three mappers built pnlCard's
arguments field by field and silently dropped `src`, so 25 annotated
scorecards rendered nothing while every suite passed.
"""
import io, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()
JS  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)


def fnbody(name, hay=None):
    """Slice a function body by brace balance."""
    hay = JS if hay is None else hay
    m = re.search(r'\n\s*(?:async )?function %s\s*\(' % re.escape(name), hay)
    if not m: return None
    i = hay.index('{', m.start()); d = 0
    while True:
        c = hay[i]
        if c == '{': d += 1
        elif c == '}':
            d -= 1
            if d == 0: return hay[m.start():i + 1]
        i += 1


# ============ A. exactly ONE card renderer ============
print('A. static - one renderer decides what a scorecard looks like')

ok(JS.count('function pnlCard(') == 1,
   'pnlCard is declared exactly once', JS.count('function pnlCard('))
ok(JS.count('function srcChip(') == 1,
   'srcChip is declared exactly once', JS.count('function srcChip('))

# The five shapes the bespoke copies took. Each is a template literal assigned
# to a local named tile/sc, or a bare style-string const - i.e. a card being
# built WITHOUT going through pnlCard.
BESPOKE = [
    (r"const tile = \([^)]*\) => `",   'inline tile template'),
    (r"const sc = \([^)]*\) => `",     'inline sc template'),
    (r"const cardVal = 'font-family",  'cardVal style const'),
    (r"const tileBg = 'background",    'tileBg style const'),
    (r"const cardLabel = 'font-family",'cardLabel style const'),
]
for pat, label in BESPOKE:
    n = len(re.findall(pat, JS))
    ok(n == 0, 'no %s remains (was a second card renderer)' % label, n)

# guard the guard: the detector must fire on a planted bespoke renderer
PLANTED = "const tile = (label, val) => `<div style=\"padding:12px\">${label}</div>`;"
ok(len(re.findall(r"const tile = \([^)]*\) => `", PLANTED)) == 1,
   '  and the detector really does catch a planted bespoke renderer')


# ============ B. every wrapper forwards src (the v10.57 bug class) ============
print('\nB. static - no wrapper may drop src on the floor')

wrappers = re.findall(
    r'const (?:tile|sc|card) = \(([^)]*)\) =>\s*\n?\s*pnlCard\(\{([^}]*)\}\)', JS)
ok(len(wrappers) >= 5,
   'the bespoke helpers survive as thin pnlCard wrappers', len(wrappers))

dropped = [(p.strip(), b.strip()) for p, b in wrappers
           if 'src' in p and 'src' not in b]
ok(not dropped,
   'every wrapper that ACCEPTS src also passes it through', dropped or None)

missing_param = [(p.strip(), b.strip()) for p, b in wrappers if 'src' not in p]
ok(not missing_param,
   '  and every wrapper accepts src in the first place', missing_param or None)

# the { l: ... } mappers from v10.59 must still forward it
ok(JS.count('src: c.src') >= 3,
   'the { l: ... } mappers still forward src (v10.59 regression guard)',
   JS.count('src: c.src'))

ok("${c.src ? srcChip(c.src) : ''}" in JS,
   'pnlCard renders the chip when a source is declared')


# ============ C. every scorecard builder declares a source ============
print('\nC. sweep - no scorecard surface renders without a source')

# Every function that paints a scorecard strip. If a new one is added without
# a source, this list is what fails - so the next strip cannot ship bare.
BUILDERS = [
    'buildInventoryStatusScorecardsHTML',
    'buildInventoryTopScorecardsHTML',
    'buildInventoryModeScorecardsHTML',
    'renderPnl',
    'renderPnlPerformance',
    'renderPnlDiagnostics',
    'renderShopifyPnl',
    'renderWalmartPnl',
    'renderChewyPnl',
    'renderChewyPnlSales',
    'renderChewyPnlCost',
    'renderChewyBreakeven',
    'renderChewyForecast',
    'renderChewyRevisionTracker',
    'renderDigitalSales',
    'pnlGrowthRenderResult',
]
SRC_REF = re.compile(
    r"srcChip\(|\bsrc\s*:|,\s*\[?'(?:sku_economics|sku_economics_eu|chewy_[a-z_]+|amazon_[a-z_]+"
    r"|products|product_cogs|digital_sales_tracker|shopify_sales_daily|walmart_sales_weekly"
    r"|sales_weekly|inventory|velocity_calculated|fba_[a-z_]+)'")

bare, notfound = [], []
for fn in BUILDERS:
    b = fnbody(fn)
    if b is None:
        notfound.append(fn); continue
    if not SRC_REF.search(b):
        bare.append(fn)

ok(not notfound, 'every named scorecard builder still exists', notfound or None)
ok(not bare, 'every scorecard builder declares at least one source', bare or None)

# guard the guard: a builder with no source must be detected
ok(not SRC_REF.search("function fake(){ return `<div>${v}</div>`; }"),
   '  and the sweep correctly flags a source-less builder')
ok(bool(SRC_REF.search("pnlCard({ label:'x', val:1, src:'products' })")),
   '  while a sourced one passes')


# ============ D. the registry covers every key that is referenced ============
print('\nD. static - no chip can render a raw table name')

reg = RAW[RAW.index('const DATA_SOURCES'):]
reg = reg[:reg.index('\n};') + 3]
declared = set(re.findall(r'^\s{2}([a-z_][a-z0-9_]*):\s*\{', reg, re.M))

ok(len(declared) >= 28,
   'DATA_SOURCES declares every upload / derived source', len(declared))

for k in ['amazon_query_performance_asin', 'amazon_sp_search_term',
          'amazon_sp_campaign_snapshot', 'amazon_ads_bulk_snapshot',
          'pnl_action_items']:
    ok(k in declared, '  %s is declared (v10.60 added it)' % k)

# Every string handed as a source must be declared, else srcChip falls back to
# printing the bare table name. Sources arrive in TWO forms, and an extractor
# that knows only one passes vacuously:
#   1. object form   pnlCard({ ..., src: 'products' })
#   2. trailing arg  tile('Label', v, sub, color, ['products', 'f ...'])
# Form 2 is how v10.60 feeds the five converted strips, so missing it would
# make this check blind to exactly the surfaces Jason flagged.
def _last_arg_literals(hay, fname):
    """Balance-aware: string literals from the LAST argument of every
    fname(...) call. Regex alone cannot do this - the args contain nested
    parens, arrays, and commas inside template literals."""
    out = set()
    for m in re.finditer(r'\b%s\(' % re.escape(fname), hay):
        i = m.end(); depth = 1; start = i
        while i < len(hay) and depth:
            c = hay[i]
            if c in '([{': depth += 1
            elif c in ')]}': depth -= 1
            i += 1
        if depth: continue
        args = hay[start:i - 1]
        parts, d, cur = [], 0, ''
        for ch in args:
            if ch in '([{': d += 1
            elif ch in ')]}': d -= 1
            if ch == ',' and d == 0: parts.append(cur); cur = ''
            else: cur += ch
        parts.append(cur)
        if parts:
            out |= set(re.findall(r"'([^']*)'", parts[-1]))
    return out

used = set()
for m in re.finditer(r"src:\s*(\[(?:[^\]]|\n)*?\]|'[^']*')", JS):
    used |= set(re.findall(r"'([^']*)'", m.group(1)))
for _fname in ('tile', 'sc'):
    used |= _last_arg_literals(JS, _fname)

# Legal source = a derived marker, or a declared table key.
used = {u for u in used
        if u and not u.startswith('\u0192') and re.fullmatch(r'[a-z_][a-z0-9_]*', u)}

# 11 today. Deliberately lower than the 28 declared keys: Digital Sales builds
# its sources into `dsActualSrc` / `dsFcSrc` variables and spreads them, which
# a literal extractor cannot see - and should not pretend to. The assertion
# exists only to stop the undeclared-key check below from passing vacuously.
ok(len(used) >= 10, '  the extractor finds src keys in BOTH forms', len(used))
undeclared = sorted(used - declared)
ok(not undeclared,
   'every table-shaped src key resolves to a DATA_SOURCES entry',
   undeclared or None)


# ============ E. the two deliberate variations are parameters, not copies ============
print('\nE. static - accent + labelHint are params on the one renderer')

body = fnbody('pnlCard')
ok(body is not None, 'pnlCard body is sliceable')
ok('c.accent' in body,
   'accent (left-edge status colour) is a pnlCard param')
ok('c.labelHint' in body,
   'labelHint (the hover affordance) is a pnlCard param')
ok(JS.count('accent: color') >= 2,
   'the two accent strips (Diagnostics + Revision Tracker) use it',
   JS.count('accent: color'))


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d): %s' % (F, ', '.join(fails[:8])))
    sys.exit(1)
print('v10.60 - all green (%d static assertions)' % P)
