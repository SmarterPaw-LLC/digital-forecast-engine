# -*- coding: utf-8 -*-
r"""
v10.20 — literal \uXXXX escapes rendering as text, and what Autoship % means.

Jason: "you have some escaped characters here" — the Chewy chart's metric
dropdown read "Merch Sales \u2014 Chewy retail ($)". And: "what is this
autoship % based on?"

The escape sweep below is the part worth keeping. Inside <script> a \u2014 is
turned into an em dash by the JS parser, so the ~490 of them in this file are
only a style wart. In MARKUP nothing interprets them and they render as the
literal six characters. CLAUDE.md records this escape-mangling class biting
repeatedly (v9.99, v10.11, and three times in the session that produced this
fix), always from a patch script rather than from anyone typing it. A sweep
catches the next one for free.
"""
import io
import os
import re
import sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(os.path.dirname(HERE), 'index.html')
src = io.open(INDEX, encoding='utf-8', newline='').read()
js = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', src, re.S), key=len)

fails = []
def ok(cond, label):
    if cond:
        print('  ok  ' + label)
    else:
        print('  FAIL ' + label)
        fails.append(label)


# ═════════ A. no escape sequence is left rendering as text ═════════
print('\nA. sweep — no \\uXXXX escapes survive in raw markup')

# Mask every <script> and <style> BODY (group 2 — group 1 is the tag name,
# and getting that wrong makes the sweep pass vacuously).
spans = [(m.start(2), m.end(2)) for m in
         re.finditer(r'<(script|style)\b[^>]*>(.*?)</\1>', src, re.S | re.I)]
masked = list(src)
for a, b in spans:
    for i in range(a, b):
        masked[i] = ' '
masked = ''.join(masked)

# Guard the guard: if the masking ever breaks, the sweep would silently pass
# on an empty string. Markup is a small slice of this file, but not nothing.
ok(len(spans) >= 1, 'found the script/style blocks to mask')
# Length proves nothing here (masking writes spaces, so the total is
# unchanged). Prove it properly: a known JS-only escape must be GONE from the
# masked text, and a known markup string must still be there. Without both,
# a broken mask makes the whole sweep pass vacuously.
ok('Accelerating' not in masked,
   'script bodies really were masked (a JS-only string is absent)')
ok('<option value="vendor_rev">' in masked,
   'markup really was kept (a markup-only string is present)')
ok('<option value="merch_sales">' in masked,
   'the markup the sweep reads includes the dropdown that had the bug')

raw = []
for m in re.finditer(r'\\u\{?[0-9a-fA-F]{4,6}\}?', masked):
    line = src.count('\n', 0, m.start()) + 1
    start = src.rfind('\n', 0, m.start()) + 1
    raw.append('line %d: %s' % (line, src[start:src.find('\n', m.start())].strip()[:120]))
ok(not raw, 'no raw-markup unicode escapes (%d found)%s'
   % (len(raw), ('\n        ' + '\n        '.join(raw[:6])) if raw else ''))

# The two that were broken, now as real characters.
ok('<option value="merch_sales">Merch Sales \u2014 Chewy retail ($)</option>' in src,
   'merch_sales option renders a real em dash')
ok('<option value="vendor_rev">Our Revenue \u2014 what Chewy pays us ($)</option>' in src,
   'vendor_rev option renders a real em dash')
ok('\\u2014 Chewy retail' not in src, 'the literal escape is gone from the source')

# Same class, different shape: an HTML entity typed into a JS string renders
# literally too. Cheap to check while we are here.
ok('&amp;mdash;' not in src, 'no double-escaped entities in the markup')


# ═════════ B. Autoship % explains itself ═════════
print('\nB. Autoship % says what it is based on')

ok('autoship_units \u00f7 units_sold' in js,
   'the tooltip states the formula')
ok('not share of revenue' in js,
   'and says explicitly that it is units, not revenue')
ok("'AS units sold'" in js,
   'and names the source column in Chewy\u2019s file')

# It has to be reachable from both places the number appears.
ok(len(re.findall(r'autoship_units \u00f7 units_sold', js)) == 2,
   'both the column header and the scorecard carry it (found %d)'
   % len(re.findall(r'autoship_units \u00f7 units_sold', js)))

# The header had no title attribute at all, so a column `t:` went nowhere.
ok('chpnl-sales-thead-row' in js, 'the Chewy Sales header is still built here')
m = re.search(r"if \(thr\) thr\.innerHTML = cols\.map\(c => `<th[^\n]*", js)
ok(m is not None and 'title="${String(c.t || c.label)' in m.group(0),
   'the Chewy Sales header renders a title attribute')
ok(m is not None and "cursor:help" in m.group(0),
   'and a help cursor when a column carries a tooltip')

# The ratio itself is unchanged — this release is labelling, not math.
ok('const autoshipPct = a.units > 0 ? (a.autoship / a.units) * 100 : 0;' in js,
   'the per-row ratio is untouched')
ok('const totAutoshipPct = tot.units > 0 ? (tot.autoship / tot.units) * 100 : 0;' in js,
   'the total ratio is untouched')


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.20 — all green')
