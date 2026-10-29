# -*- coding: utf-8 -*-
r"""v10.50 — one concept, one glyph. And the sweep that keeps it that way.

Jason: "the icon for break even is different for chewy vs amazon. please LOG IN
YOUR INSTRUCTIONS TO STAY CONSISTENT."

The instruction is logged in CLAUDE.md, but a rule nobody can run is a rule
that drifts. This suite IS the enforcement: it walks every sub-tab button in
the app and fails when one label carries two glyphs, when one strip uses the
same glyph twice, or when a tab ships with no glyph at all.

So the next tab added with a borrowed icon breaks the build instead of
reaching Jason.
"""
import io, os, re, sys, collections

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()

MONEYBAG = '\U0001F4B0'
TARGET   = '\U0001F3AF'
ROCKET   = '\U0001F680'

P = F = 0
def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))


# ── collect every sub-tab button, attribute order agnostic ────────────────
# The ACTIVE tab carries class="subtab on", so the class match must not be
# anchored to a closing quote.
pairs = re.findall(r'<button[^>]*class="subtab[^"]*"[^>]*id="([^"]*)"[^>]*>([^<]*)</button>', RAW)
pairs += [(i, t) for t, i in
          re.findall(r'<button[^>]*id="([^"]*)"[^>]*class="subtab[^"]*"[^>]*>([^<]*)</button>', RAW)]
tabs = {}
for bid, txt in pairs:
    tabs[bid] = txt.strip()

print('A. the sweep found the strips')
ok(len(tabs) >= 20, 'every sub-tab button is reachable by the sweep', len(tabs))

# Strip = the id minus its last segment. Every strip in the app follows that
# shape (pnl-amzn-tab-*, chpnl-tab-*, dst-*, ipv-*, ds-view-*, pricing-mode-*),
# so a new strip is grouped correctly without touching this test.
strips = collections.defaultdict(dict)
glyph_of = {}
label_of = {}
for bid, txt in tabs.items():
    m = re.match(r'^(\S+)\s+(.+)$', txt)
    ok(bool(m), 'every tab ships with a glyph: %s' % bid, txt)
    if not m: continue
    glyph, label = m.group(1), m.group(2).strip()
    strips[bid.rsplit('-', 1)[0]][bid] = (glyph, label)
    glyph_of.setdefault(label, set()).add(glyph)
    label_of.setdefault(glyph, set()).add(label)

ok(len(strips) >= 5, '  grouped into the app\'s strips', sorted(strips))


# ── the rule Jason flagged ────────────────────────────────────────────────
print('\nB. one concept, one glyph')

offenders = {lab: sorted(gs) for lab, gs in glyph_of.items() if len(gs) > 1}
ok(not offenders,
   'no tab label carries two different glyphs across the app', offenders)

for strip, members in sorted(strips.items()):
    seen = collections.defaultdict(list)
    for bid, (g, lab) in members.items():
        seen[g].append(lab)
    dupes = {g: labs for g, labs in seen.items() if len(labs) > 1}
    ok(not dupes, '  %-16s uses each glyph once' % strip, dupes)


# ── the specific resolution ───────────────────────────────────────────────
print('\nC. the resolution')

be = {bid: v for bid, v in tabs.items() if 'breakeven' in bid}
ok(len(be) == 2, 'there are two Break-Even tabs (Amazon + Chewy)', sorted(be))
ok(all(v.startswith(TARGET) for v in be.values()),
   '  and both use the target glyph', be)
ok(MONEYBAG + ' Break-Even' not in RAW, '  the money-bag Break-Even is gone')

# v11.21 - was pinned to the button id `pnl-amzn-tab-growth`. The Growth
# Model moved into the Ads tab and the id changed, so the check went red on a
# rule that still held. Find it BY LABEL instead: that follows the tab
# wherever it lives, which is the guarantee this line was always about.
_growth = {bid: v for bid, v in tabs.items() if v.endswith('Growth Model')}
ok(len(_growth) == 1, 'there is exactly one Growth Model tab', sorted(_growth))
ok(all(v.startswith(ROCKET) for v in _growth.values()),
   'Growth Model vacated the target for the rocket', _growth)
ok(RAW.count(ROCKET + ' Growth Model') == 2,
   '  including its empty state, so the tab and the panel agree',
   RAW.count(ROCKET + ' Growth Model'))
# The rocket already meant scale / invest / launch in this app, which is why it
# is the right vacancy to fill rather than a fresh glyph.
for existing in ['Scale candidates', 'Launch ads', 'UNDER-INVESTED WINNER']:
    ok(ROCKET in RAW[max(0, RAW.index(existing) - 120): RAW.index(existing) + 40],
       '  rocket already meant "%s"' % existing)


# ── the instruction is written down, not just applied ─────────────────────
print('\nD. the rule is logged where the next change will read it')

MD = io.open(r'C:\Users\Jason\digital-forecast-engine\CLAUDE.md',
             encoding='utf-8', newline='').read()
ok('## Design-pattern consistency' in MD,
   'CLAUDE.md carries a standing design-consistency rule')
head = MD[:MD.index('## v10.50')] if '## v10.50' in MD else MD[:8000]
ok('## Design-pattern consistency' in head,
   '  above the changelog, where it will actually be read')
for phrase in ['one concept, one glyph', 'reuse the existing', 'test_v1050']:
    ok(phrase.lower() in MD.lower(), '  names: %s' % phrase)


print('\n' + ('=' * 60))
if F:
    print('FAILED: %d of %d' % (F, P + F)); sys.exit(1)
print('v10.50 — all green (%d assertions)' % P)
