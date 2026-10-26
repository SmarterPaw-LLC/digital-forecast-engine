# -*- coding: utf-8 -*-
r"""v10.87 - a prose sweep must not swallow a clickable affordance.

Jason: "the link to these reports was removed" (both FBA Shipments cards).

v4.202 put a Seller Central deep link on every upload card. v10.59 swept the
page's prose paragraphs into tooltips and collapsed each card's info-box
<div> - and the <a> INSIDE that box went with it. Its label survived only as
TEXT inside the resulting title attribute:

    title="... click Download shipment contents ... ^ Open Manage FBA Shipments queue"

which nobody can click. Every other card kept its link purely because that
link happened to sit outside the collapsed block.

This is the second casualty of the v10.59 sweep. v10.61 caught the first
(five orphaned </div> closes) and made div balance runnable; nothing checked
that the sweep had not deleted FUNCTIONALITY along with the prose. That is
what this suite adds.

The rule it encodes: prose may be collapsed into a tooltip, but an
interactive element may never be. A tooltip is not an affordance.
"""
import io, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()

ARROW = chr(0x2197)   # the up-right arrow every deep link uses

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond:
        P += 1; print('  ok  ' + label)
    else:
        F += 1; fails.append(label)
        print('  FAIL ' + label + (('  -> ' + str(got)) if got is not None else ''))


def markup_only(html):
    """Blank <script> and <style> bodies - they contain link-shaped strings."""
    def blank(m):
        return m.group(0)[:m.start(2) - m.start(0)] + ' ' * (m.end(2) - m.start(2)) + \
               m.group(0)[m.end(2) - m.start(0):]
    return re.sub(r'(<(script|style)\b[^>]*>)(.*?)(</\2>)',
                  lambda m: m.group(1) + ' ' * len(m.group(3)) + m.group(4),
                  html, flags=re.S | re.I)


MARKUP = markup_only(RAW)


# ── A. No link text stranded inside a tooltip ──────────────────────────────
print('\nA. no clickable affordance has been flattened into a tooltip')

def flattened(html):
    """Link LABEL living inside a title= attribute instead of inside an <a>."""
    out = []
    for m in re.finditer(r'title="([^"]*)"', html):
        t = m.group(1)
        if ARROW + ' Open' in t or ARROW + ' Download' in t:
            out.append(t[:70])
    return out

flat = flattened(MARKUP)
ok(not flat, 'no title= attribute carries link text', flat)

# teeth - the detector must fire on a planted flattened link
planted = '<div title="some prose ' + ARROW + ' Open Report Somewhere">x</div>'
ok(len(flattened(planted)) == 1, 'GUARD detector fires on a planted flattened link')
ok(len(flattened('<div title="ordinary tooltip, no link">x</div>')) == 0,
   'GUARD detector ignores an ordinary tooltip')


# ── B. The two links v10.59 ate are back and real ──────────────────────────
print('\nB. both FBA Shipments links are clickable again')

QUEUE = 'shipping-queue.html'
anchors = re.findall(r'<a\b[^>]*href="([^"]*' + QUEUE + r'[^"]*)"[^>]*>(.*?)</a>', MARKUP, re.S)
ok(len(anchors) == 2, 'two real <a> elements point at the FBA shipments queue', len(anchors))

for href, label in anchors:
    ok(href.startswith('https://sellercentral.amazon.com/'),
       'link targets Seller Central', href[:60])
    ok(ARROW in label, 'link carries the standard arrow label', label[:40])

full = re.findall(r'<a\b[^>]*' + QUEUE + r'[^>]*>', MARKUP)
for a in full:
    ok('target="_blank"' in a, 'opens in a new tab (does not lose the dashboard)')
    ok('rel="noopener"' in a, 'rel=noopener set')
    # Every .dz card has an invisible full-card <input type=file> overlaying it
    # (the v4.152 / v7.97 lesson). A link must out-rank it and must not let the
    # click bubble into the dropzone and open a file picker.
    ok('onclick="event.stopPropagation()"' in a, 'click does not open the file picker')
    ok('z-index:2' in a and 'position:relative' in a, 'sits above the hidden file input')


# ── C. The prose stayed collapsed ──────────────────────────────────────────
print('\nC. restoring the link did not restore the paragraph')

# v10.59's whole point: no card prints a paragraph. Re-adding the link must
# not drag the old info-box back (the v10.78 / v10.59 standing rule).
for grp in ['last-fba-ship-grp', 'last-fba-ship-sum-grp']:
    i = MARKUP.index('id="' + grp + '"')
    body = MARKUP[i:i + 3000]
    j = body.index('<div class="dg">') if '<div class="dg">' in body else len(body)
    head = body[:j]
    # strip tags, measure what is actually PRINTED on screen
    visible = re.sub(r'<[^>]+>', '', head)
    visible = re.sub(r'\s+', ' ', visible).strip()
    ok(len(visible) <= 120, grp + ' prints a one-liner, not a paragraph', repr(visible[:130]))
    ok('rgba(96,200,250,.08)' not in head,
       grp + ' did not get the old info-box background back')


# ── D. Every documented report keeps a way to reach it ─────────────────────
print('\nD. deep links survive across the uploads page')

links = re.findall(r'href="(https://(?:sellercentral|advertising)\.amazon\.[^"]*)"', MARKUP)
ok(len(links) >= 12, 'the uploads page still carries its deep links', len(links))

# the specific reports that must remain one click away
for frag, name in [
    ('sereport', 'SKU Economics'),
    ('FBA_MYI_UNSUPPRESSED_INVENTORY', 'FBA Inventory'),
    ('ESTIMATED_FBA_FEES', 'FBA Fee Preview'),
    ('DetailSalesTrafficByChildItem', 'Sales & Traffic'),
    ('query-performance', 'SQP'),
    ('shipping-queue.html', 'FBA Shipments queue'),
    ('bulk-operations', 'Amazon Ads bulk sheet'),
]:
    ok(any(frag in l for l in links), name + ' is reachable by link')


print('\n' + '=' * 62)
print(f'  v10.87  PASS {P}   FAIL {F}')
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
