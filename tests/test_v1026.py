# -*- coding: utf-8 -*-
"""
v10.26 — org-wide view defaults (active-only · hide-bundles · default sort).

Jason: "on the global defaults settings, i want to be able to set more global
defaults, like only showing active products, choosing default sort, etc."
Confirmed scope: org-wide, admin-only, those three settings.

The assertion that earns its keep is the THIRD STATE. "not set" has to be
distinct from "set to false" — an admin who has never expressed an opinion
must not silently force every hide-inactive checkbox off for the whole team.
A truthiness check would collapse those two cases; there is a named guard that
reproduces the truthy version and shows it gets the answer wrong.

Second one worth having: the Products filter is multi-purpose (bundles /
needs-review / missing-ASIN / …). Steering it to "active" is only safe while
it is still sitting on its own default — otherwise a global setting silently
clobbers the filter someone is actively using.
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
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, 'index.html')
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
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), js)
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


def const_block(name):
    """Slice `const NAME = [ … ];` by bracket balance."""
    m = re.search(r'\nconst %s = \[' % re.escape(name), js)
    if not m:
        raise SystemExit('FAIL: cannot find const %s' % name)
    i = js.index('[', m.end() - 1)
    depth, j = 0, i
    while j < len(js):
        if js[j] == '[':
            depth += 1
        elif js[j] == ']':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return js[m.start() + 1:j + 1] + ';'


# ═════════ A. wiring ═════════
print('\nA. wiring — loaded, applied and mounted in the right order')

ok('loadGlobalViewDefaults()' in js, 'loader exists')
ok(re.search(r'Promise\.all\(\[loadMyProfile\(\), loadGlobalTabDefaults\(\), loadGlobalViewDefaults\(\)\]\)', js) is not None,
   'loaded in parallel with the profile + tab defaults')
# ⚠ Must land BEFORE init() paints, or the first render shows the built-in
# default and then visibly flips.
# Comments are stripped first -- the explanatory comment at that call site
# literally contains the words "before init() paints", and matching that
# instead of the real call is how this assertion first went red.
after = re.sub(r'//[^\n]*', '', js[js.index('loadGlobalViewDefaults()]'):])
ok(after.index('applyGlobalViewDefaults()') < after.index('init()'),
   'applied BEFORE init() paints, not after')
ok("document.getElementById('users-global-view')" in js, 'panel mounted in Settings')
# Scoped to the mount function. renderGlobalViewDefaults() is ALSO called
# from setGlobalViewDefaults(), which lives earlier in the file, so a
# first-occurrence-in-file comparison answers a different question.
_mount = fn('renderUsersList')
ok('renderGlobalViewDefaults();' in _mount
   and _mount.index('renderGlobalTabDefaults();') < _mount.index('renderGlobalViewDefaults();'),
   'sits below the tab-access panel')

# No migration: this rides on the table v9.85 already created.
ok("eq('key', 'view_defaults')" in js, "stored under its own app_settings key")
ok('supabase_v10_26' not in src, 'no new migration invented — app_settings already exists')

# Fail-open, same as v9.82 / v9.85.
loader = fn('loadGlobalViewDefaults')
ok('_globalViewDefaults = null' in loader and 'catch' in loader,
   'a broken read falls open to no defaults')


# ═════════ B. behaviour — the real applyGlobalViewDefaults ═════════
print('\nB. behaviour — the real sliced functions')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

// ── DOM stub: just the controls the applier touches ──
const EL = {};
function mkChk(id, checked) { EL[id] = { id, checked, tagName: 'INPUT' }; }
function mkSel(id, value, opts) {
  EL[id] = { id, value, options: opts.map(v => ({ value: v })), tagName: 'SELECT' };
}
function resetDom() {
  mkChk('fHideInactive', true);  mkChk('ip-hide-inactive', true);
  mkChk('fHideBundles', false);  mkChk('ip-hide-bundles', true);
  mkChk('salesHideBundles', false);
  mkSel('cogs-status-filter', 'active', ['active', 'inactive', 'all']);
  mkSel('prodFilter', '', ['', 'bundle', 'single', 'active', 'inactive', 'needs_review']);
}
const document = { getElementById: id => EL[id] || null };

// ── sort state the page descriptors write to ──
let prodSortKey = 'title', prodSortDir = 1;
let ipSortKey = 'need30', ipSortDir = -1;
let pnlSortKey = 'net_sales', pnlSortDir = -1;
let sortChain = [{ key: 'adj_daily', dir: -1 }];
let _lsProdSort = null;
const localStorage = {
  getItem: k => (k === 'prodSortKey' ? _lsProdSort : null),
  setItem: () => {},
};

// Minimal registries so cols() resolves.
const PROD_COLUMNS = [
  { key: '_chk', label: '', locked: true, sortVal: () => 0 },
  { key: 'title', label: 'Product', sortVal: () => 0 },
  { key: 'msrp', label: 'MSRP', sortVal: () => 0 },
];
const IP_COLUMNS = [{ key: 'need30', label: '30d Need', sortVal: () => 0 }];
const FC_COLUMNS = [{ key: 'adj_daily', label: 'Vel/day', get: () => 0 }];
const PNL_COLUMNS = [{ key: 'net_sales', label: 'Net Sales' }];

let _globalViewDefaults = null;

PAGES
APPLY

// ═════ the third state ═════
resetDom(); _globalViewDefaults = null; applyGlobalViewDefaults();
t('no defaults at all -> every control untouched',
  [EL['fHideInactive'].checked, EL['ip-hide-bundles'].checked, EL['prodFilter'].value],
  [true, true, '']);

// ⚠ THE named guard. An admin who has set hideBundles but never touched
// activeOnly must not have activeOnly silently forced off.
resetDom(); _globalViewDefaults = { hideBundles: true }; applyGlobalViewDefaults();
t('a key that is absent is NOT treated as false',
  [EL['fHideInactive'].checked, EL['ip-hide-inactive'].checked], [true, true]);
t('  while the key that IS set applies',
  [EL['fHideBundles'].checked, EL['salesHideBundles'].checked], [true, true]);

// Reproduce the truthiness version and show it gets the absent case wrong.
resetDom();
const d_truthy = { hideBundles: true };
if (d_truthy.activeOnly) { EL['fHideInactive'].checked = true; }
else { EL['fHideInactive'].checked = false; }   // what a naive if/else does
t('regression guard — truthiness really would have forced it off',
  EL['fHideInactive'].checked, false);

// ═════ explicit false IS a setting ═════
resetDom(); _globalViewDefaults = { activeOnly: false }; applyGlobalViewDefaults();
t('activeOnly:false unchecks hide-inactive (a real choice)',
  [EL['fHideInactive'].checked, EL['ip-hide-inactive'].checked], [false, false]);
t('  and opens COGS on All rather than Active only',
  EL['cogs-status-filter'].value, 'all');

resetDom(); _globalViewDefaults = { activeOnly: true }; applyGlobalViewDefaults();
t('activeOnly:true checks both hide-inactive boxes',
  [EL['fHideInactive'].checked, EL['ip-hide-inactive'].checked], [true, true]);
t('  sets COGS to Active only', EL['cogs-status-filter'].value, 'active');
t('  and steers the Products filter', EL['prodFilter'].value, 'active');

// ═════ the Products filter is multi-purpose — do not clobber it ═════
resetDom(); EL['prodFilter'].value = 'needs_review';
_globalViewDefaults = { activeOnly: true }; applyGlobalViewDefaults();
t('a filter the user is actively using is left alone',
  EL['prodFilter'].value, 'needs_review');

resetDom(); EL['prodFilter'].value = 'active';
_globalViewDefaults = { activeOnly: false }; applyGlobalViewDefaults();
t('but the one WE set is still ours to release',
  EL['prodFilter'].value, '');

// An unknown select value is never written (would blank the control).
resetDom(); EL['cogs-status-filter'].options = [{ value: 'active' }];
_globalViewDefaults = { activeOnly: false }; applyGlobalViewDefaults();
t('a value the select does not offer is not written',
  EL['cogs-status-filter'].value, 'active');

// ═════ hideBundles ═════
resetDom(); _globalViewDefaults = { hideBundles: false }; applyGlobalViewDefaults();
t('hideBundles:false clears all three',
  [EL['fHideBundles'].checked, EL['ip-hide-bundles'].checked, EL['salesHideBundles'].checked],
  [false, false, false]);

// ═════ sort ═════
resetDom(); _lsProdSort = null;
_globalViewDefaults = { sort: { products: { key: 'msrp', dir: 1 }, inventory: { key: 'need30', dir: -1 } } };
applyGlobalViewDefaults();
t('sort applies when the user has no personal choice', [prodSortKey, prodSortDir], ['msrp', 1]);

// ⚠ A sort the user has clicked themselves outranks the org default.
prodSortKey = 'title'; prodSortDir = 1; _lsProdSort = 'brand';
_globalViewDefaults = { sort: { products: { key: 'msrp', dir: -1 } } };
applyGlobalViewDefaults();
t('a personal sort wins over the org default', [prodSortKey, prodSortDir], ['title', 1]);

_lsProdSort = null;
_globalViewDefaults = { sort: { forecast: { key: 'adj_daily', dir: 1 } } };
applyGlobalViewDefaults();
t('Forecast writes the whole sort chain, not a stray key', sortChain, [{ key: 'adj_daily', dir: 1 }]);

_globalViewDefaults = { sort: { pnl: { key: 'net_sales', dir: 1 } } };
applyGlobalViewDefaults();
t('P&L sort applies', [pnlSortKey, pnlSortDir], ['net_sales', 1]);

// A junk direction normalises rather than leaking through.
_globalViewDefaults = { sort: { pnl: { key: 'net_sales', dir: 'up' } } };
applyGlobalViewDefaults();
t('a junk direction normalises to desc', pnlSortDir, -1);

// A page naming a column that no longer exists must not throw.
let threw = false;
try {
  _globalViewDefaults = { sort: { inventory: { key: 'gone_column', dir: -1 } } };
  applyGlobalViewDefaults();
} catch (e) { threw = true; }
t('an unknown column does not throw', threw, false);

// ═════ degenerate shapes ═════
for (const bad of [undefined, null, {}, { sort: null }, { sort: {} }, { activeOnly: 'yes' }]) {
  let th = false;
  resetDom();
  try { _globalViewDefaults = bad; applyGlobalViewDefaults(); } catch (e) { th = true; }
  t('no throw on ' + JSON.stringify(bad === undefined ? 'undefined' : bad), th, false);
}
// A non-boolean must be ignored, not coerced.
resetDom(); _globalViewDefaults = { activeOnly: 'yes' }; applyGlobalViewDefaults();
t('a non-boolean activeOnly is ignored, not coerced', EL['fHideInactive'].checked, true);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""

harness = harness.replace('PAGES', const_block('VIEW_SORT_PAGES'))
harness = harness.replace('APPLY', fn('applyGlobalViewDefaults'))
tmp = os.path.join(tempfile.gettempdir(), 'test_v1026_apply.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip())
    fails.append('applyGlobalViewDefaults behaviour')


# ═════════ C. the payload setters shape the record correctly ═════════
print('\nC. setters — clearing removes the key rather than storing false')

h2 = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};
let _globalViewDefaults = null;
let sent;
async function setGlobalViewDefaults(next) { sent = next; _globalViewDefaults = next; }

FIELD
SORTSET

(async () => {
  _globalViewDefaults = null;
  await setGlobalViewDefault('activeOnly', true);
  t('setting a field from empty', sent, { activeOnly: true });

  await setGlobalViewDefault('hideBundles', false);
  t('a second field does not disturb the first', sent, { activeOnly: true, hideBundles: false });

  // ⚠ "not set" must DELETE the key. Writing false would turn "no opinion"
  // into "show everything", which is a different instruction.
  await setGlobalViewDefault('activeOnly', null);
  t('clearing deletes the key rather than storing false', sent, { hideBundles: false });

  _globalViewDefaults = { activeOnly: true };
  await setGlobalViewSort('products', 'msrp', 1);
  t('sort nests under its page id', sent, { activeOnly: true, sort: { products: { key: 'msrp', dir: 1 } } });

  await setGlobalViewSort('inventory', 'need30', -1);
  t('a second page joins it', sent.sort, { products: { key: 'msrp', dir: 1 }, inventory: { key: 'need30', dir: -1 } });

  await setGlobalViewSort('products', '', -1);
  t('clearing one page leaves the others', sent.sort, { inventory: { key: 'need30', dir: -1 } });

  await setGlobalViewSort('inventory', '', -1);
  t('clearing the last page drops the whole sort object', sent, { activeOnly: true });

  await setGlobalViewSort('products', 'msrp', 'junk');
  t('a junk direction normalises on write', sent.sort.products.dir, -1);

  console.log('\n  ' + P + ' passed, ' + F + ' failed');
  if (F) process.exit(1);
})();
"""
h2 = h2.replace('FIELD', fn('setGlobalViewDefault')).replace('SORTSET', fn('setGlobalViewSort'))
tmp2 = os.path.join(tempfile.gettempdir(), 'test_v1026_set.js')
io.open(tmp2, 'w', encoding='utf-8', newline='').write(h2)
r2 = subprocess.run(['node', tmp2], capture_output=True, text=True, encoding='utf-8')
print(r2.stdout.rstrip())
if r2.returncode != 0:
    print(r2.stderr.rstrip())
    fails.append('setter payload shaping')


# ═════════ D. the panel renders, and is read-only for non-admins ═════════
print('\nD. panel render')

h3 = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};
let host = { innerHTML: '' };
const document = { getElementById: id => (id === 'users-global-view' ? host : null) };
let _admin = true;
function isAppAdmin() { return _admin; }
let _globalViewDefaults = null;
const PROD_COLUMNS = [{ key: 'title', label: 'Product', sortVal: () => 0 },
                      { key: 'msrp', label: 'MSRP', sortVal: () => 0 }];
const IP_COLUMNS = [{ key: 'need30', label: '30d Need', sortVal: () => 0 }];
const FC_COLUMNS = [{ key: 'adj_daily', label: 'Vel/day', get: () => 0 }];
const PNL_COLUMNS = [{ key: 'net_sales', label: 'Net Sales' }];

PAGES
RENDER

_admin = true; _globalViewDefaults = null; renderGlobalViewDefaults();
t('empty state says nothing is set', /Nothing set/.test(host.innerHTML), true);
t('admin gets the controls', /setGlobalViewDefault\('activeOnly'/.test(host.innerHTML), true);
t('and a column picker per page',
  ['gvs-products', 'gvs-inventory', 'gvs-forecast', 'gvs-pnl'].every(id => host.innerHTML.includes(id)), true);
t('no leaked undefined/NaN', /undefined|NaN|\[object/.test(host.innerHTML), false);

_globalViewDefaults = { activeOnly: true, hideBundles: false, sort: { products: { key: 'msrp', dir: 1 } } };
renderGlobalViewDefaults();
t('counts everything that is set', /3 set/.test(host.innerHTML), true);
t('the chosen sort column is selected',
  /value="msrp" selected/.test(host.innerHTML), true);
t('still no leaked undefined/NaN', /undefined|NaN|\[object/.test(host.innerHTML), false);

// ⚠ Non-admins must see the state but get no write controls — the setting is
// org-wide, so a non-admin editing it would change it for everyone.
_admin = false; renderGlobalViewDefaults();
t('non-admin sees it read-only', /setGlobalViewDefault\(/.test(host.innerHTML), false);
t('  and no column pickers either', /<select/.test(host.innerHTML), false);
t('  but can still read what is set', /active only/.test(host.innerHTML), true);

// A registry that has not loaded yet must degrade, not crash.
_admin = true; _globalViewDefaults = null;
const _savedProd = PROD_COLUMNS.splice(0, PROD_COLUMNS.length);
let threw = false;
try { renderGlobalViewDefaults(); } catch (e) { threw = true; }
t('an unloaded column registry does not throw', threw, false);
t('  and says so instead of rendering an empty picker',
  /open that page once/.test(host.innerHTML), true);
_savedProd.forEach(c => PROD_COLUMNS.push(c));

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
h3 = h3.replace('PAGES', const_block('VIEW_SORT_PAGES')).replace('RENDER', fn('renderGlobalViewDefaults'))
tmp3 = os.path.join(tempfile.gettempdir(), 'test_v1026_render.js')
io.open(tmp3, 'w', encoding='utf-8', newline='').write(h3)
r3 = subprocess.run(['node', tmp3], capture_output=True, text=True, encoding='utf-8')
print(r3.stdout.rstrip())
if r3.returncode != 0:
    print(r3.stderr.rstrip())
    fails.append('panel render')


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.26 — all green')
