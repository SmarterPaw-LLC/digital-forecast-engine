# -*- coding: utf-8 -*-
r"""v10.59 - no prose paragraphs on any page, and a chip on every scorecard.

Jason: "is there some reason you are making me point out every instance of text
bloat? please clean up all pages. i want the text captured in a tooltip."

He is right that the problem was my method, not the individual banners: v10.57
removed the four he had pointed at instead of sweeping for the shape. This suite
IS the sweep, so the next paragraph fails the build instead of reaching him.

It also pins the thing that made v10.57's chips invisible: three mappers built
pnlCard's arguments field by field and silently dropped `src`.
"""
import io, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()
JS  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)
JS_A = RAW.index(JS)
MARKUP = RAW[:JS_A] + RAW[JS_A + len(JS):]

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)


# ============ A. the sweep - no always-visible prose paragraph anywhere ============
print('A. sweep - no page prints a paragraph')

def prose_blocks(hay, limit=160):
    """Always-visible divs whose own text is long and which carry no tooltip.
    A <details> is opt-in, and a div holding a control is a toolbar, so both
    are excluded - the target is text the operator cannot dismiss."""
    out = []
    for m in re.finditer(r'<div([^>]*)>(.*?)</div>\s*(?=<)', hay, re.S):
        attrs, inner = m.group(1), m.group(2)
        if re.search(r'<(input|select|button|textarea|table|div|details)\b', inner): continue
        if 'title="' in attrs: continue
        txt = re.sub(r'<[^>]+>', ' ', inner)
        txt = re.sub(r'\s+', ' ', txt).strip()
        if len(txt) < limit: continue
        before = hay[max(0, m.start() - 4000):m.start()]
        if before.count('<details') > before.count('</details>'): continue
        out.append((hay[:m.start()].count('\n') + 1, len(txt), txt[:70]))
    return out

markup_prose = prose_blocks(RAW[:JS_A])
ok(not markup_prose,
   'no always-visible prose block left in the markup',
   markup_prose[:4] or None)

# guard the guard: the detector must actually fire on a paragraph
FAKE = ('<div style="border:1px solid red">' + ('word ' * 60) + '</div><span>')
ok(len(prose_blocks(FAKE)) == 1,
   '  and the detector really does catch one when present')
ok(len(prose_blocks('<div title="x" style="border:1px solid red">' + ('word ' * 60) + '</div><span>')) == 0,
   '  while a tooltipped block is correctly left alone')

ok(RAW.count('data-prose="1"') >= 45,
   'the collapsed blocks kept their full text on a tooltip',
   RAW.count('data-prose="1"'))


# ============ B. the four banners Jason named are gone ============
print('\nB. static - the specific banners, and they stay gone')

for gone, why in [
    ('Two different revenue lines on this page', 'Chewy Sales'),
    ('Rebate-only tracking',                     'Chewy Rebates'),
    ('Vendor economics</strong>',                'Cost to Chewy'),
]:
    ok(gone not in RAW, '%s prose banner is gone' % why)

ok('Partial P&L' in RAW and 'Partial data</strong>' not in RAW,
   'Shopify / Walmart partial-data warning survives as ONE line, not a paragraph')


# ============ C. the bug that made v10.57's chips invisible ============
print('\nC. static - src reaches pnlCard from every mapper')

ok('src: c.src' in JS, 'the { l: ... } mappers forward src')
ok(JS.count('src: c.src') >= 3,
   '  all three of them, not just the one that was noticed',
   JS.count('src: c.src'))
ok('const card = (label, val, sub, color, tip, src)' in JS,
   "Break-Even's card() helper takes a source too")
ok('${c.src ? srcChip(c.src) : \'\'}' in JS,
   'pnlCard renders the chip when a source is declared')

# a card declaring a source whose arg never reaches pnlCard is the v10.57 bug
mappers = re.findall(r'map\(c => pnlCard\(\{([^}]*)\}\)\)', JS)
bad = [m for m in mappers if 'src' not in m]
ok(not bad, 'no pnlCard mapper drops src on the floor', bad or None)


# ============ D. chips on every scorecard surface ============
print('\nD. static - every scorecard surface declares sources')

ok('function srcChip(' in JS and JS.count('function srcChip(') == 1,
   'srcChip is declared exactly once')
ok('function srcTipLine(' in JS and JS.count('function srcTipLine(') == 1,
   'srcTipLine is declared exactly once')
ok('const DATA_SOURCES' in JS and 'const COLUMN_SOURCES' in JS,
   'both registries exist')

ok(JS.count('srcChip(') >= 20,
   'the banded strips (Inventory, Units Sold, Chewy Forecasts) carry chips too',
   JS.count('srcChip('))
ok(JS.count('src:') >= 25,
   'the pnlCard strips declare a source per card',
   JS.count('src:'))
ok(JS.count('srcTipLine(colSrc(') >= 9,
   'nine column registries append their source to every header tooltip',
   JS.count('srcTipLine(colSrc('))


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d): %s' % (F, ', '.join(fails[:8])))
    sys.exit(1)
print('v10.59 - all green (%d static assertions)' % P)
