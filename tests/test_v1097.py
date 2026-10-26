# -*- coding: utf-8 -*-
r"""v10.97 - per-page SUB-TAB visibility, set org-wide.

Jason: "make a per page tab visibility setting, set globally, like the other
settings. i want to hide this by default" (pointing at Ad Activity).

"like the other settings" has a specific meaning, recorded at v10.28:

    "i do NOT want the global settings on the setting pages - it is supposed
     to be a global settings per page for all users default - we already have
     the module"

The module is PAGE_SETTINGS_PANELS, the gear beside the global search bar.
So this is a panel there, stored on app_settings exactly like view_defaults
(v10.26) and default_visible_tabs (v9.85). No migration.

The whole feature hangs off subtabApply, which v10.17 made the single place
every sub-tab strip's state runs through - six strips, one chokepoint, so
hiding works everywhere without touching six switch functions.

Three guarantees worth pinning:
  1. a strip can never be left with ZERO visible tabs - that is a page with
     no way back into itself, and nothing on screen would explain it
  2. hiding the tab you are ON moves you to the first visible one rather
     than stranding you on a panel with no lit tab
  3. only HIDDEN tabs are stored, so a sub-tab added in a later version is
     visible by default instead of inheriting someone's old hide-list
"""
import io, os, re, sys, json, subprocess

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
RAW = io.open(SRC, encoding='utf-8', newline='').read()
JS  = max(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', RAW, re.S), key=len)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond:
        P += 1; print('  ok  ' + label)
    else:
        F += 1; fails.append(label)
        print('  FAIL ' + label + (('  -> ' + str(got)) if got is not None else ''))

def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', src)

def fn(name):
    m = re.search(r'(?:async\s+)?function\s+' + name + r'\s*\(', JS)
    if not m: return ''
    k = JS.index('(', m.end() - 1); d = 0
    while True:
        if JS[k] == '(': d += 1
        elif JS[k] == ')':
            d -= 1
            if d == 0: break
        k += 1
    j = JS.index('{', k); d = 0; k = j
    while True:
        if JS[k] == '{': d += 1
        elif JS[k] == '}':
            d -= 1
            if d == 0: return JS[m.start():k + 1]
        k += 1

APPLY = fn('subtabApply')
KEYFN = fn('subtabStripKey')


# -- A. It lives in the gear, not on the Settings page --------------------
print('\nA. the setting lives where Jason said it should')

ok("id: 'subtabvis'" in JS, 'registered as a PAGE_SETTINGS_PANELS entry')
# v10.28: he explicitly rejected the Settings page for org-wide per-page
# defaults. Guard that it did not drift back there.
panel = JS[JS.index("id: 'subtabvis'"): JS.index("id: 'subtabvis'") + 1200]
for k in ['pageKeyFor', 'isSet', 'summary', 'render']:
    ok(k in panel, 'the panel implements %s (the registry contract)' % k)
ok('subtabVisStripFor' in panel, 'it resolves the strip from the current nav key')
ok('Admin-only' in panel, 'the hint says it is admin-only')

# Stored org-wide on app_settings, same as every other global default.
LOAD = strip_comments(fn('loadGlobalSubtabVis'))
WRITE = strip_comments(fn('writeGlobalSubtabVis'))
ok("'subtab_visibility'" in LOAD and "from('app_settings')" in LOAD,
   'read from app_settings, like view_defaults')
ok("from('app_settings')" in WRITE and "onConflict: 'key'" in WRITE,
   'written back to app_settings by key')
ok('_globalSubtabVis = null' in LOAD,
   'FAILS OPEN - an unreadable setting must never remove a tab from a screen')
# Point at the real init call, not the first mention of the name anywhere.
_init = re.search(r'await Promise\.all\(\[loadMyProfile\(\)[^\]]*\]\)', JS)
ok(bool(_init) and 'loadGlobalSubtabVis()' in _init.group(0),
   'loaded at init beside the other org-wide settings',
   _init.group(0) if _init else 'init Promise.all not found')


# -- B. Strip identity, against the REAL strips ---------------------------
print('\nB. strip identity derives from the real button ids')

# Pull every actual subtabApply call site out of the source. Testing the
# derivation against invented fixtures would prove nothing about this app.
# ⚠ The pairs are a multi-line array OF arrays, so a non-greedy `\[(.*?)\]`
# stops at the first inner `]` and finds nothing. Balance the brackets.
calls = []
for m in re.finditer(r'subtabApply\(\s*\[', JS):
    k = JS.index('[', m.end() - 1); d = 0; i = k
    while True:
        if JS[i] == '[': d += 1
        elif JS[i] == ']':
            d -= 1
            if d == 0: break
        i += 1
    ids = re.findall(r"\[\s*'([^']+)'\s*,\s*'([^']+)'\s*\]", JS[k:i + 1])
    if ids: calls.append(ids)
# The registry-driven Chewy strip builds its pairs with .map(), so add it.
chewy = re.findall(r"btn:\s*'([^']+)'", JS)
ok(len(calls) >= 5, 'found the literal subtabApply call sites', len(calls))
ok(len(chewy) >= 4, 'found the Chewy strip built via .map()', len(chewy))

ok(bool(KEYFN), 'subtabStripKey located')
ok('replace(/-+$/' in KEYFN, 'it trims a trailing dash off the shared prefix')


# -- C. Behaviour, driven in node -----------------------------------------
print('\nC. behaviour')

real_strips = json.dumps([[list(p) for p in c] for c in calls])

harness = r'''
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

// -- DOM stub ------------------------------------------------------------
let NODES = {};
let CLICKS = [];
function mkBtn(id, label) {
  return { id, className: 'subtab', style: {}, textContent: label || id,
           click() { CLICKS.push(this.id); } };
}
const document = { getElementById: (id) => NODES[id] || null };
function pageSettingsCurrentNavKey() { return NAVKEY; }
let NAVKEY = 'pnl_amazon';
let _globalSubtabVis = null;
// Module-scope state subtabApply owns, lifted so the real function runs intact.
const _subtabRegistry = {};
let _subtabHealing = false;

__KEYFN__
__ISHIDDEN__
__APPLY__

function build(pairs) {
  NODES = {}; CLICKS = [];
  for (const [id, key] of pairs) NODES[id] = mkBtn(id, 'Label ' + key);
}
const shown = (pairs) => pairs.filter(([id]) => NODES[id].style.display !== 'none').map(([, k]) => k);

// -- 1. Strip keys, against the app's REAL strips ------------------------
const REAL = __REAL__;
const keys = REAL.map(p => subtabStripKey(p));
t('C1 every real strip yields a non-empty key', keys.every(k => !!k), true);
t('C2 strip keys are unique - no two strips collide',
  new Set(keys).size, keys.length);
t('C3 no key keeps a trailing dash', keys.every(k => !/-$/.test(k)), true);
t('C4 the Amazon P&L strip resolves to its shared prefix',
  subtabStripKey([['pnl-amzn-tab-summary','summary'],['pnl-amzn-tab-perf','performance']]),
  'pnl-amzn-tab');
t('C5 a single-button strip still yields a key',
  subtabStripKey([['ipv-planning','planning']]), 'ipv-planning');
t('C6 empty input does not throw', subtabStripKey([]), '');

// -- 2. Hiding ------------------------------------------------------------
const AMZ = [['pnl-amzn-tab-summary','summary'],['pnl-amzn-tab-perf','performance'],
             ['pnl-amzn-tab-adactivity','adactivity']];
build(AMZ);
_globalSubtabVis = { 'pnl-amzn-tab': { adactivity: false } };
subtabApply(AMZ, 'summary');
t('C7 a hidden sub-tab is removed from the strip', shown(AMZ), ['summary','performance']);
t('C8 the active tab is still marked on', NODES['pnl-amzn-tab-summary'].className, 'subtab on');
t('C9 hiding does not click anything', CLICKS, []);

// Visible again the moment it is ticked back on - nothing is deleted.
build(AMZ);
_globalSubtabVis = {};
subtabApply(AMZ, 'summary');
t('C10 absent from the hide-list means visible', shown(AMZ), ['summary','performance','adactivity']);

// A sub-tab nobody has an opinion about is visible, so a NEW one added in a
// later version does not inherit an old hide-list.
build(AMZ);
_globalSubtabVis = { 'pnl-amzn-tab': { somethingRemoved: false } };
subtabApply(AMZ, 'summary');
t('C11 a stale key for a tab that no longer exists hides nothing',
  shown(AMZ), ['summary','performance','adactivity']);

// -- 3. Never leave a strip with zero tabs -------------------------------
build(AMZ);
_globalSubtabVis = { 'pnl-amzn-tab': { summary: false, performance: false, adactivity: false } };
subtabApply(AMZ, 'summary');
t('C12 an all-hidden strip is ignored - every tab stays visible',
  shown(AMZ), ['summary','performance','adactivity']);
t('C13 ...and it does not try to heal into nothing', CLICKS, []);

// -- 4. Self-heal when the ACTIVE tab is hidden --------------------------
build(AMZ);
_globalSubtabVis = { 'pnl-amzn-tab': { adactivity: false } };
subtabApply(AMZ, 'adactivity');
t('C14 being on a hidden tab moves you to the first visible one',
  CLICKS, ['pnl-amzn-tab-summary']);

// The heal must not loop: the re-entrant call during the click is suppressed.
build(AMZ);
NODES['pnl-amzn-tab-summary'].click = function () {
  CLICKS.push(this.id);
  subtabApply(AMZ, 'adactivity');   // what the real switch fn would do
};
_globalSubtabVis = { 'pnl-amzn-tab': { adactivity: false } };
subtabApply(AMZ, 'adactivity');
t('C15 the heal cannot loop', CLICKS.length, 1);

// Healing to the first VISIBLE tab, not merely the first tab.
const S2 = [['x-a','a'],['x-b','b'],['x-c','c']];
build(S2);
_globalSubtabVis = { 'x': { a: false, c: false } };
subtabApply(S2, 'c');
t('C16 it heals to the first VISIBLE tab, skipping hidden ones', CLICKS, ['x-b']);

// -- 5. The registry the settings panel reads ----------------------------
build(AMZ);
_globalSubtabVis = null;
NAVKEY = 'pnl_amazon_changelog';
subtabApply(AMZ, 'summary');
t('C17 the strip registers itself with the nav key it rendered under',
  [_subtabRegistry['pnl-amzn-tab'].stripKey, _subtabRegistry['pnl-amzn-tab'].navKey],
  ['pnl-amzn-tab', 'pnl_amazon_changelog']);
t('C18 ...and captures the rendered labels for the panel',
  _subtabRegistry['pnl-amzn-tab'].labels.adactivity, 'Label adactivity');

console.log(JSON.stringify(out));
'''
harness = (harness
    .replace('__KEYFN__', KEYFN)
    .replace('__ISHIDDEN__', fn('subtabIsHidden'))
    .replace('__APPLY__', APPLY)
    .replace('__REAL__', real_strips))
hp = os.path.join(SP, 'test_v1097_subtab.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', hp], capture_output=True, text=True)
if r.returncode != 0:
    print('  FAIL  subtab harness did not run:\n' + (r.stderr or '')[:2200]); F += 1; fails.append('harness')
else:
    try: rows = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  subtab harness unparseable: %s\n%s' % (e, r.stdout[:600])); F += 1; fails.append('harness parse'); rows = []
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else ('got ' + row['got'] + ' want ' + row['want']))


# -- D. Storage shape + admin gating --------------------------------------
print('\nD. storage shape and who may change it')

SET = strip_comments(fn('setSubtabVisible'))
ok('delete strip[viewKey]' in SET,
   'showing a tab DELETES the entry - visible is the absence of an opinion')
ok('strip[viewKey] = false' in SET, 'hiding records an explicit false')
ok('delete next[stripKey]' in SET, 'an empty strip entry is dropped, not left as {}')
ok('stillVisible' in SET and 'alert(' in SET,
   'refuses to hide the last visible tab, and says why')
ok('app_settings table missing' in SET,
   'names the migration if app_settings is not there')

REN = strip_comments(fn('subtabVisRenderControls'))
ok('isAppAdmin' in REN, 'the panel checks admin')
ok('disabled' in REN, 'non-admins get a read-only view')
ok('visibleCount <= 1' in REN,
   'the last visible tab cannot be unticked from the UI either')
ok('line-through' in REN, 'hidden tabs read as hidden in the list')

# Belt and braces: the render guard and the write guard are independent, so
# neither alone can strand a page.
ok('const enforce = visible.length > 0' in strip_comments(APPLY),
   'the render guard is independent of the write guard')


print('\n' + '=' * 62)
print('  v10.97  PASS %d   FAIL %d' % (P, F))
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
