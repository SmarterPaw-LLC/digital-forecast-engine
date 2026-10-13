# -*- coding: utf-8 -*-
r"""v10.49 — ONE scorecard renderer for every P&L surface.

Jason: "these scorecard should be formatted like the amazon P&L scorecards.
please, please be consistent with design patterns."

Four markups across seven strips, and one of them referenced three CSS classes
that do not exist, so it rendered as unstyled plain text. The guarantee worth
pinning is not "the card looks like X" (that will change) but "there is exactly
ONE place that decides what a card looks like, and every strip goes through it".
"""
import io, os, re, subprocess, sys, tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

# Comments quote the old class names on purpose; strip them before sweeping.
code = re.sub(r'^\s*//.*$', '', js, flags=re.M)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)

def fn(name):
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), js)
    if not m: raise SystemExit('FAIL: cannot slice %s' % name)
    a = m.start() + 1
    i = js.index('{', a); depth = 0
    while True:
        c = js[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return js[a:i + 1]
        i += 1


# ══════════════ A. one renderer, every strip ══════════════
print('A. static — one renderer, and every P&L strip goes through it')

ok(js.count('function pnlCard(') == 1, 'pnlCard is declared exactly once')
ok(js.count('function pnlCardStrip(') == 1, 'pnlCardStrip is declared exactly once')

# Seven strips: Amazon, Shopify, Walmart, Chewy Sales, Chewy Cost,
# Chewy Break-Even, Chewy Rebates.
ok(code.count('pnlCardStrip(') - 1 == 3, 'three strips render a whole array through pnlCardStrip',
   code.count('pnlCardStrip(') - 1)
direct = len(re.findall(r'(?<!function )\bpnlCard\(', code)) - 0
ok(direct >= 4, 'four more map their own rows through pnlCard', direct)

for el in ['pnl-scorecards', 'spnl-scorecards', 'wmpnl-scorecards',
           'chpnl-sales-scorecards', 'chpnl-cost-scorecards',
           'chpnl-be-scorecards', 'chpnl-scorecards']:
    ok(("id=\"%s\"" % el) in RAW, '  %s exists in the markup' % el)


# ══════════════ B. the variants are gone ══════════════
print('\nB. static — no second card markup survives')

# The --surface / 8px / 12-14 padding variant (Walmart, Chewy Sales, Chewy Cost)
ok('border-radius:8px;padding:12px 14px"><div style="font-family:var(--mono)' not in code,
   'the --surface / 8px / 12-14px variant is gone')
# The hand-written Rebates block. NOT a padding sweep: 'border-radius:10px;
# padding:12px 16px' also matches two PANEL wrappers on that page
# (Month-over-Month, Breakdown by Category), which are not scorecards.
ok('>Total Rebates</div>' not in code, 'the hand-written Rebates cards are gone')
ok('scEl.innerHTML = pnlCardStrip(' in code, '  and that strip renders through the helper')

# The undefined classes. \b matters: '.sc-l' is a SUBSTRING of '.sc-lbl', and
# .sc-v / .sc-s of .sc-val / .sc-sub, so a plain `in` check matches the classes
# that DO exist.
CSS = RAW[:RAW.index('</style>')]
for cls in ['sc-l', 'sc-v', 'sc-s']:
    ok(('class="%s"' % cls) not in code, 'class="%s" is no longer used' % cls)
    ok(not re.search(r'\.%s\s*[,{]' % re.escape(cls), CSS),
       '  (and %s was never defined in the stylesheet, which was the bug)' % cls)
# The real ones are still there and still used by the Inventory Planning strip.
for cls in ['sc-lbl', 'sc-val', 'sc-sub']:
    ok(bool(re.search(r'\.%s\s*[,{]' % re.escape(cls), CSS)),
       '  .%s is defined (the banded Inventory strip still uses it)' % cls)


# ══════════════ C. the card contract ══════════════
print('\nC. static — the Amazon card shape is what the helper emits')

card = fn('pnlCard')
for frag in ['background:var(--surface2)', 'border-radius:10px', 'padding:14px 16px',
             'font-size:10px', 'text-transform:uppercase', 'letter-spacing:.5px',
             'font-family:var(--display)', 'font-size:22px', 'font-weight:800',
             'line-height:1.1']:
    ok(frag in card, '  emits %s' % frag)

ok('c.badge' in card, 'badge renders inline after the value (the v7.44 brand-pool warning)')
ok('c.delta' in card, 'delta renders beneath the sub-line')
ok("c.color || 'var(--text)'" in card,
   'colour falls back to --text, so a card that passes none is not invisible')
ok(".replace(/\"/g, '&quot;')" in card,
   'the tooltip is attribute-escaped (a quote in a tip would break the div)')
ok("cursor:help" in card, 'a card with a tip gets the help cursor')


# ══════════════ D. behaviour — drive the real helper ══════════════
print('\nD. behaviour — the real sliced pnlCard')

harness = r"""
let P = 0, F = 0;
const t = (label, cond, got) => {
  if (cond) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + (got === undefined ? '' : '  got ' + JSON.stringify(got))); }
};

//<<CARD>>
//<<STRIP>>

const full = pnlCard({ label: 'Net Units', val: '89,532', sub: '$11.74 ASP',
                       color: 'var(--sp-green)', tip: 'He said "flat rate"',
                       badge: '<span>!</span>', delta: '<div>d</div>' });
t('renders the label', full.includes('Net Units'));
t('renders the value', full.includes('89,532'));
t('renders the sub', full.includes('$11.74 ASP'));
t('applies the colour', full.includes('color:var(--sp-green)'));
t('renders the badge inline after the value', full.indexOf('<span>!</span>') > full.indexOf('89,532'));
t('renders the delta', full.includes('<div>d</div>'));
t('escapes a double quote in the tip', full.includes('He said &quot;flat rate&quot;'));
t('  and does not leak a raw quote out of the attribute',
  !/title="[^"]*"[^>]*flat rate/.test(full) || full.includes('&quot;'));

const bare = pnlCard({ label: 'Coverage', val: '\u2014' });
t('a card with no colour still has a colour', bare.includes("color:var(--text)"));
t('a card with no sub renders an empty sub line, not "undefined"',
  !bare.includes('undefined'), bare.includes('undefined'));
t('a card with no tip has no title attribute', !bare.includes('title='));
t('  and no help cursor', !bare.includes('cursor:help'));
t('a card with no badge/delta leaks nothing',
  !bare.includes('null') && !bare.includes('false'));

const strip = pnlCardStrip([{ label: 'A', val: '1' }, { label: 'B', val: '2' }]);
t('the strip concatenates with no separator', strip === pnlCard({label:'A',val:'1'}) + pnlCard({label:'B',val:'2'}));
t('  and renders one div per card', (strip.match(/<div style="background/g) || []).length === 2);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
harness = harness.replace('//<<CARD>>', fn('pnlCard'), 1)
harness = harness.replace('//<<STRIP>>', fn('pnlCardStrip'), 1)

tmp = os.path.join(tempfile.gettempdir(), 'test_v1049_card.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1500])
    fails.append('pnlCard behaviour')


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d static, %d sections): %s' % (F, len(fails), ', '.join(fails[:6])))
    sys.exit(1)
print('v10.49 — all green (%d static assertions + 1 behaviour section)' % P)
