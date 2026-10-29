# -*- coding: utf-8 -*-
"""
v10.17 — one sub-tab look for every page that has sub-pages.

Jason: "can you make all the pages that have multiple subpages use this tab
layout?" — pointing at the Chewy P&L browser-tab strip.

Six strips, four looks (green pills on Data + Amazon P&L, a segmented box on
Pricing Scenarios + Bundles, an underline on Inventory Planning, browser tabs
on Chewy P&L), each re-implementing active/inactive as inline styles inside
its own switcher. Now one CSS class and one applier.

The assertions that earn their keep are the two round-trip ones at the bottom:
every id handed to subtabApply must exist in the markup, and every .subtab in
the markup must be handed to subtabApply. Either gap leaves a tab that can
never light up, which looks like a dead button rather than a bug.
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


def fn(name):
    m = re.search(r'\nfunction %s\s*\(' % re.escape(name), js)
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


# The six strips that were unified, and the sub-view each tab maps to.
STRIPS = {
    # v10.36 added the Break-Even sub-tab (Chewy ad spend vs contribution
    # per unit). This count going red is the test doing its job.
    # v11.01 added the Program sub-tab (account-level efficiency). This count
    # going red is the test doing its job, same as v10.36's 20 -> 21.
    # v11.16 added the Ads sub-tab (campaign level) to BOTH P&Ls. Census
    # 25 -> 27; this going red is the test doing its job.
    'Chewy P&L':          ['chpnl-tab-sales', 'chpnl-tab-cost', 'chpnl-tab-breakeven',
                           'chpnl-tab-program', 'chpnl-tab-ads', 'chpnl-tab-rebates'],
    'Data':               ['dst-uploads', 'dst-history', 'dst-query'],
    'Amazon P&L':         ['pnl-amzn-tab-summary', 'pnl-amzn-tab-perf', 'pnl-amzn-tab-diag',
                           'pnl-amzn-tab-changelog',
                           'pnl-amzn-tab-opps', 'pnl-amzn-tab-ads',
                           'pnl-amzn-tab-breakeven'],
    # v11.21 - Growth Model LEFT the Amazon strip for the Ads one, which also
    # grew an Uploads area. Census 28 -> 29.
    # v11.17 - Jason: "ads activity tab on amazon p&L should be a sub area
    # of the ads tab." Ad Activity LEFT the Amazon P&L strip and the Ads tab
    # grew a nested one. Census 27 -> 28; this going red is the test working.
    # v11.22 - Keywords joins the Ads strip. Census 29 -> 30.
    'Amazon Ads':         ['pnl-amzn-ads-tab-campaigns', 'pnl-amzn-ads-tab-keywords',
                           'pnl-amzn-ads-tab-growth',
                           'pnl-amzn-ads-tab-activity', 'pnl-amzn-ads-tab-uploads'],
    'Inventory Planning': ['ipv-planning', 'ipv-reorder'],
    'Pricing Scenarios':  ['pricing-mode-new', 'pricing-mode-existing', 'pricing-mode-chewy'],
    'Digital Sales':      ['ds-view-grid', 'ds-view-reports'],
    # v11.08 - Walmart P&L grew a strip (Sales + Cost to Walmart). Census
    # 23 -> 25; this going red is the test doing its job, same as v10.36's
    # 20 -> 21 and v11.01's 22 -> 23.
    'Walmart P&L':        ['wmpnl-tab-sales', 'wmpnl-tab-cost'],
}
DEFAULT_ON = {'chpnl-tab-sales', 'dst-uploads', 'pnl-amzn-tab-summary',
              'ipv-planning', 'pricing-mode-new', 'ds-view-grid',
              'wmpnl-tab-sales', 'pnl-amzn-ads-tab-campaigns'}


def tag_of(btn_id):
    m = re.search(r'<button[^>]*id="%s"[^>]*>' % re.escape(btn_id), src)
    return m.group(0) if m else None


# ═════════ A. the shared look exists once ═════════
print('\nA. static — one definition of the look')

ok(len(re.findall(r'^\.subtab-strip\s*\{', src, re.M)) == 1, '.subtab-strip defined exactly once')
ok(len(re.findall(r'^\.subtab\s*\{', src, re.M)) == 1, '.subtab defined exactly once')
ok(len(re.findall(r'^\.subtab\.on\s*\{', src, re.M)) == 1, '.subtab.on defined exactly once')
ok(len(re.findall(r'\nfunction subtabApply\s*\(', js)) == 1, 'subtabApply defined exactly once')

# The active tab is lifted 1px over the strip's bottom border — that is the
# whole "joined to the panel" effect. Lose either half and it reads as a pill.
ok(re.search(r'\.subtab-strip\s*\{[^}]*border-bottom:\s*1px', src) is not None,
   'the strip keeps its bottom border')
ok(re.search(r'\.subtab\.on\s*\{[^}]*top:\s*1px', src, re.S) is not None,
   'the active tab sits 1px over that border')
ok(re.search(r'\.subtab\.on\s*\{[^}]*border-bottom:\s*none', src, re.S) is not None,
   'the active tab has no bottom border of its own')


# ═════════ B. every strip converted ═════════
print('\nB. static — every strip and every button converted')

for page, btns in STRIPS.items():
    first = btns[0]
    m = re.search(r'<div[^>]*class="subtab-strip"[^>]*>\s*(?:<!--.*?-->\s*)?<button[^>]*id="%s"'
                  % re.escape(first), src, re.S)
    ok(m is not None, '%s: container uses .subtab-strip' % page)
    for b in btns:
        tag = tag_of(b)
        ok(tag is not None and 'class="subtab' in tag, '%s: %s has class="subtab"' % (page, b))
        ok(tag is not None and ' style=' not in tag,
           '%s: %s carries no inline style to override the class' % (page, b))
    on = [b for b in btns if (tag_of(b) or '').find('class="subtab on"') >= 0]
    ok(len(on) == 1, '%s: exactly one tab starts active (got %d)' % (page, len(on)))
    ok(not on or on[0] in DEFAULT_ON, '%s: the right tab starts active (%s)' % (page, on))

ok(len(re.findall(r'class="subtab(?: on)?"', src)) == sum(len(v) for v in STRIPS.values()),
   'no stray .subtab buttons beyond the %d accounted for' % sum(len(v) for v in STRIPS.values()))


# ═════════ C. no switcher still hand-styles a tab ═════════
print('\nC. static — the old per-switcher styling is gone')

for dead, why in [
    ("const styleTab = (btnId, active)", 'Amazon P&L styleTab'),
    ("gbtn.style.cssText", 'Digital Sales cssText'),
    ("tabP.style.borderBottomColor", 'Inventory underline styling'),
    ("sub.style.background = view === v", 'Data strip inline styling'),
]:
    ok(dead not in js, 'removed: %s' % why)

# Every converted switcher routes through the one applier.
for f, label in [('switchChewyPnlView', 'Chewy P&L'), ('switchDataView', 'Data'),
                 ('switchPnlAmazonView', 'Amazon P&L'), ('setIpView', 'Inventory Planning'),
                 ('pricingSetMode', 'Pricing Scenarios'), ('setDigitalSalesView', 'Digital Sales')]:
    ok('subtabApply(' in fn(f), '%s switcher calls subtabApply' % label)


# ═════════ D. the round trip: ids in code ↔ buttons in markup ═════════
print('\nD. static — every wired id exists, every button is wired')

wired = set(re.findall(r"\['([\w-]+)',\s*'[\w-]+'\]", js))
# Chewy's strip is registry-driven (TABS.map(t => [t.btn, t.key])) rather than
# a literal pair list, so pull its ids out of the registry itself.
wired |= set(re.findall(r"btn:\s*'([\w-]+)'", js))

for b in sorted(wired):
    if b.startswith(('chpnl-tab-', 'dst-', 'pnl-amzn-tab-', 'ipv-', 'pricing-mode-', 'ds-view-')):
        ok(('id="%s"' % b) in src, 'wired id %s exists in the markup' % b)

declared = {b for v in STRIPS.values() for b in v}
ok(declared <= wired,
   'every .subtab button is handed to subtabApply (missing: %s)' % sorted(declared - wired))


# ═════════ E. subtabApply behaviour ═════════
print('\nE. behaviour — subtabApply (the real function)')

h = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};
const EL = {};
// v10.97 — subtabApply now also sets style.display and reads textContent for
// the sub-tab visibility panel, so the stub element grew to match. The
// assertions below are unchanged: they are about className.
const mk = id => (EL[id] = { id, className: 'whatever', style: {}, textContent: id, click() {} });
const document = { getElementById: id => EL[id] || null };
function pageSettingsCurrentNavKey() { return 'test'; }

// v10.97 — module-scope state subtabApply depends on. Lifted so the REAL
// function runs intact rather than being reimplemented here (the v10.43 /
// v10.45 / v10.46 pattern: fn() captures function bodies only).
let _globalSubtabVis = null;
const _subtabRegistry = {};
let _subtabHealing = false;
DEPS

HANDLER

['a','b','c'].forEach(mk);
const PAIRS = [['a','one'],['b','two'],['c','three']];

subtabApply(PAIRS, 'two');
t('exactly the matching tab is on', ['a','b','c'].map(i => EL[i].className),
  ['subtab', 'subtab on', 'subtab']);

// Switching clears the previous one — two tabs lit at once is the bug this
// replaces (every old switcher re-styled all of its buttons by hand).
subtabApply(PAIRS, 'three');
t('switching moves the highlight', ['a','b','c'].map(i => EL[i].className),
  ['subtab', 'subtab', 'subtab on']);

// An unknown key lights nothing rather than everything.
subtabApply(PAIRS, 'nope');
t('unknown key -> all inactive', ['a','b','c'].map(i => EL[i].className),
  ['subtab', 'subtab', 'subtab']);

// Whatever was on the element before is replaced, not appended — otherwise
// 'on' accumulates and the highlight never clears.
EL.a.className = 'subtab on stale junk';
subtabApply(PAIRS, 'two');
t('stale classes are replaced, not appended', EL.a.className, 'subtab');

// A strip whose page is not in the DOM yet must not throw.
let threw = false;
try { subtabApply([['missing-id','x'],['a','x']], 'x'); } catch (e) { threw = true; }
t('missing elements do not throw', threw, false);
t('present siblings still update', EL.a.className, 'subtab on');

// Degenerate inputs.
threw = false;
try { subtabApply([], 'x'); } catch (e) { threw = true; }
t('empty pair list does not throw', threw, false);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
h = h.replace('DEPS', fn('subtabStripKey') + chr(10) + fn('subtabIsHidden'))
h = h.replace('HANDLER', fn('subtabApply'))
tmp = os.path.join(tempfile.gettempdir(), 'test_v1017_subtab.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(h)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip())
    fails.append('subtabApply behaviour')


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.17 — all green')
