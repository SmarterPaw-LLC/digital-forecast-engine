# -*- coding: utf-8 -*-
"""
v10.29 — the gear panel gets REAL CONTROLS (supersedes test_v1028).

Jason: "I CANNOT SET IT HERE" — the v10.28 panel was a read-out plus a "save
this page's current view" button, so setting a default meant leaving the panel,
configuring the page, then coming back. Every other panel in this gear writes
on change; this one does now too.

Also still guards v10.28's two placement/copy rules, which are unchanged:

Jason, twice:
  "i do NOT want the global settings on the setting pages — it is supposed to
   be a global settings per page for all users default — we already have the
   module"
  "also jfc, what did i say about extra unnecssary copy"

So this supersedes test_v1026 (whose functions no longer exist) and guards two
things:

  * the setting lives in PAGE_SETTINGS_PANELS and NOT on the Settings page
  * no panel prints its hint as a paragraph — the gear renders it as a tooltip

That second one is the structural fix. The gear USED to print `panel.hint` as a
visible block on every panel, so each new panel shipped another paragraph. One
change at the render site fixes it for all of them and stops the next one
re-introducing it.
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


def vd_helpers():
    """The four _vd* DOM helpers, lifted from source.

    They are module-level consts, so neither fn() nor const_arr() captures
    them and the harness throws ReferenceError without this. Lifted rather
    than restated so a changed helper breaks the test instead of silently
    passing against a stale copy."""
    out = []
    for name in ['_vdChk', '_vdSetChk', '_vdSetSel', '_vdCols']:
        m = re.search(r'\nconst %s\s*=' % re.escape(name), js)
        if not m:
            raise SystemExit('FAIL: cannot find const %s' % name)
        # Depth-aware: stop at the first ';' outside any bracket. A plain
        # non-greedy regex truncates the multi-line ones at their own first
        # statement and leaves an unbalanced brace.
        i, depth, j = m.start() + 1, 0, m.end()
        while j < len(js):
            ch = js[j]
            if ch in '([{':
                depth += 1
            elif ch in ')]}':
                depth -= 1
            elif ch == ';' and depth == 0:
                break
            j += 1
        out.append(js[i:j + 1])
    return '\n'.join(out)


def const_arr(name):
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


# ═════════ A. it lives in the gear, not on Settings ═════════
print('\nA. placement — the module Jason pointed at, not a second one')

registry = const_arr('PAGE_SETTINGS_PANELS')
ok("id: 'viewdefault'" in registry, 'registered as a page-settings panel')
ok('viewDefaultPageFor(navKey)' in registry, 'resolves its page from the nav key like every other panel')
for hook in ['pageKeyFor', 'isSet', 'summary', 'render']:
    ok(hook + ':' in registry.split("id: 'viewdefault'")[1], 'honours the panel contract: %s' % hook)

# ⚠ The v10.26 Settings slab must be GONE, not merely hidden.
for dead in ['users-global-view', 'renderGlobalViewDefaults', 'onGlobalViewSortChange', 'VIEW_SORT_PAGES']:
    ok(dead not in src, 'no leftover from the Settings-page version: %s' % dead)

# Still the same table v9.85 created — no migration invented.
ok("eq('key', 'view_defaults')" in js, 'second key on app_settings, not a new table')
ok('supabase_v10_2' not in src, 'no new migration file referenced')


# ═════════ B. the copy rule, fixed at the root ═════════
print('\nB. copy — hints are tooltips, not printed paragraphs')

# ⚠ This is the structural half. If the gear prints panel.hint again, EVERY
# panel grows a paragraph back, so the assertion is on the render site.
menu = fn('renderPageSettingsMenu') if re.search(r'\nfunction renderPageSettingsMenu\s*\(', js) else js
ok('${panel.hint}</div>' not in js, 'the gear no longer PRINTS panel.hint as a block')
ok('title="${String(panel.hint' in js, 'it renders the hint as a tooltip on the label instead')

# The v9.82 banner is gone from the DOM but its warning survives on hover —
# it is load-bearing, so losing it entirely would be the wrong fix.
ok('users-access-note' not in src, 'the standing UI-scoping banner is gone')
ok('Tab visibility is UI scoping, not data security' in js,
   '  but the warning itself survives')
ok('status.title =' in fn('renderUsersList'),
   '  carried on the status line it qualifies')

# My own panel body must be state + controls, not prose.
body = fn('viewDefaultRenderControls')
prose = re.findall(r"'([A-Z][a-z][^']{60,})'", body)
ok(not prose, 'the panel body ships no long prose string' + ('' if not prose else ' — found: ' + prose[0][:70]))
# v10.29 — the save-the-current-view button is gone, so what matters now is
# that the panel actually lets you SET things rather than only report them.
ok('setViewDefaultField(' in body, 'the panel sets fields directly')
ok('onViewDefaultSortChange(' in body, '  and offers a sort picker')
ok('saveCurrentViewAsDefault' not in src, 'the save-the-page-view gesture is gone')


# ═════════ C. behaviour — per-page apply ═════════
print('\nC. behaviour — the real applyGlobalViewDefaults, now per page')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

const EL = {};
const mkChk = (id, c) => EL[id] = { id, checked: c };
const mkSel = (id, v, opts) => EL[id] = { id, value: v, options: opts.map(x => ({ value: x })) };
function resetDom() {
  mkChk('fHideInactive', true);  mkChk('ip-hide-inactive', true);
  mkChk('fHideBundles', false);  mkChk('ip-hide-bundles', true);
  mkChk('salesHideBundles', false);
  mkSel('cogs-status-filter', 'active', ['active', 'inactive', 'all']);
  mkSel('prodFilter', '', ['', 'bundle', 'active', 'needs_review']);
}
const document = { getElementById: id => EL[id] || null };

let prodSortKey = 'title', prodSortDir = 1;
let ipSortKey = 'need30', ipSortDir = -1;
let pnlSortKey = 'net_sales', pnlSortDir = -1;
let sortChain = [{ key: 'adj_daily', dir: -1 }];
let _lsProdSort = null;
const localStorage = { getItem: k => (k === 'prodSortKey' ? _lsProdSort : null), setItem: () => {} };

const PROD_COLUMNS = [{ key: 'msrp', label: 'MSRP', sortVal: () => 0 }];
const IP_COLUMNS   = [{ key: 'need30', label: '30d Need', sortVal: () => 0 }];
const FC_COLUMNS   = [{ key: 'adj_daily', label: 'Vel/day', get: () => 0 }];
const PNL_COLUMNS  = [{ key: 'net_sales', label: 'Net Sales' }];

let _globalViewDefaults = null;

PAGES
APPLY

// ═════ per-page scoping ═════
resetDom();
_globalViewDefaults = { forecast: { activeOnly: false } };
applyGlobalViewDefaults();
t('a default set on Forecast does NOT leak onto Inventory',
  [EL['fHideInactive'].checked, EL['ip-hide-inactive'].checked], [false, true]);

resetDom();
_globalViewDefaults = { forecast: { hideBundles: true }, inventory: { hideBundles: false } };
applyGlobalViewDefaults();
t('each page gets its own answer',
  [EL['fHideBundles'].checked, EL['ip-hide-bundles'].checked], [true, false]);

// ═════ the third state ═════
resetDom(); _globalViewDefaults = null; applyGlobalViewDefaults();
t('nothing set -> nothing touched',
  [EL['fHideInactive'].checked, EL['ip-hide-bundles'].checked], [true, true]);

resetDom(); _globalViewDefaults = { forecast: { hideBundles: true } }; applyGlobalViewDefaults();
t('an absent field is NOT read as false', EL['fHideInactive'].checked, true);
t('  while the field that IS set applies', EL['fHideBundles'].checked, true);

resetDom(); _globalViewDefaults = { forecast: { activeOnly: 'yes' } }; applyGlobalViewDefaults();
t('a non-boolean is ignored, not coerced', EL['fHideInactive'].checked, true);

// ═════ the Products filter guard ═════
resetDom(); EL['prodFilter'].value = 'needs_review';
_globalViewDefaults = { products: { activeOnly: true } }; applyGlobalViewDefaults();
t('a filter the user is using is left alone', EL['prodFilter'].value, 'needs_review');

resetDom(); _globalViewDefaults = { products: { activeOnly: true } }; applyGlobalViewDefaults();
t('an idle filter is steered', EL['prodFilter'].value, 'active');

// ═════ sort ═════
resetDom(); _lsProdSort = null;
_globalViewDefaults = { products: { sort: { key: 'msrp', dir: 1 } }, pnl: { sort: { key: 'net_sales', dir: 1 } } };
applyGlobalViewDefaults();
t('sort applies per page', [prodSortKey, prodSortDir, pnlSortDir], ['msrp', 1, 1]);

prodSortKey = 'title'; prodSortDir = 1; _lsProdSort = 'brand';
_globalViewDefaults = { products: { sort: { key: 'msrp', dir: -1 } } };
applyGlobalViewDefaults();
t('a personal sort outranks the org default', [prodSortKey, prodSortDir], ['title', 1]);

_lsProdSort = null;
_globalViewDefaults = { forecast: { sort: { key: 'adj_daily', dir: 1 } } };
applyGlobalViewDefaults();
t('Forecast writes the whole chain', sortChain, [{ key: 'adj_daily', dir: 1 }]);

_globalViewDefaults = { pnl: { sort: { key: 'net_sales', dir: 'up' } } };
applyGlobalViewDefaults();
t('a junk direction normalises to desc', pnlSortDir, -1);

// ═════ degenerate shapes ═════
for (const bad of [undefined, null, {}, { forecast: null }, { nosuchpage: { activeOnly: true } }]) {
  let th = false; resetDom();
  try { _globalViewDefaults = bad; applyGlobalViewDefaults(); } catch (e) { th = true; }
  t('no throw on ' + JSON.stringify(bad === undefined ? 'undefined' : bad), th, false);
}

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
harness = (harness.replace('PAGES', vd_helpers() + '\n' + const_arr('VIEW_DEFAULT_PAGES'))
                  .replace('APPLY', fn('applyGlobalViewDefaults')))
tmp = os.path.join(tempfile.gettempdir(), 'test_v1028_apply.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip())
    fails.append('per-page apply behaviour')


# ═════════ D. the setters — writing from the panel ═════════
print('\nD. setters — set it in the panel, writes on change')

h2 = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};
let _globalViewDefaults = null;
let written, applied = 0, repainted = [];
// Mirrors the real function's normalisation: an empty object is stored as
// null, so "every page cleared" and "never set" are the same state.
async function writeGlobalViewDefaults(n) {
  written = (n && Object.keys(n).length) ? n : null;
  _globalViewDefaults = written;
}
async function logAudit() {}
function viewDefaultError(e) { throw e; }
function applyGlobalViewDefaults() { applied++; }
function pageSettingsRefresh() {}
const window = {};
const VIEW_DEFAULT_PAGES = [{ key: 'inventory', rerender: 'renderInventoryTbl' },
                            { key: 'products',  rerender: 'renderProductsTbl' }];
const document = { getElementById: id => ({ 'vds-inventory': { value: 'need30' },
                                            'vdd-inventory': { value: '1' } })[id] || null };

FIELD
SORT
AFTER
ONCHANGE

(async () => {
  _globalViewDefaults = null;
  await setViewDefaultField('inventory', 'activeOnly', true);
  t('setting a field from empty', written, { inventory: { activeOnly: true } });
  t('  applies to the live page immediately', applied > 0, true);

  await setViewDefaultField('inventory', 'hideBundles', false);
  t('a second field joins without disturbing the first',
    written.inventory, { activeOnly: true, hideBundles: false });

  // ⚠ "not set" must DELETE the field. Storing false would turn "no opinion"
  // into "show everything", which is a different instruction.
  await setViewDefaultField('inventory', 'activeOnly', null);
  t('"not set" deletes the field rather than storing false',
    written.inventory, { hideBundles: false });

  // Clearing the LAST field drops the page entirely rather than leaving {}.
  await setViewDefaultField('inventory', 'hideBundles', null);
  t('clearing the last field drops the page entry', written, null);

  // Pages stay independent.
  _globalViewDefaults = null;
  await setViewDefaultField('inventory', 'activeOnly', true);
  await setViewDefaultField('products', 'activeOnly', false);
  t('pages are independent',
    written, { inventory: { activeOnly: true }, products: { activeOnly: false } });

  await setViewDefaultSort('inventory', 'need30', 1);
  t('sort nests inside its page',
    written.inventory, { activeOnly: true, sort: { key: 'need30', dir: 1 } });

  await setViewDefaultSort('inventory', 'need30', 'junk');
  t('a junk direction normalises to desc', written.inventory.sort.dir, -1);

  await setViewDefaultSort('inventory', '', -1);
  t('clearing sort leaves the other fields', written.inventory, { activeOnly: true });

  // The dropdown handler reads both selects and routes to the setter.
  await onViewDefaultSortChange('inventory');
  t('the sort dropdown handler reads column + direction',
    written.inventory.sort, { key: 'need30', dir: 1 });

  console.log('\n  ' + P + ' passed, ' + F + ' failed');
  if (F) process.exit(1);
})();
"""
h2 = (h2.replace('FIELD', fn('setViewDefaultField'))
        .replace('SORT', fn('setViewDefaultSort'))
        .replace('AFTER', fn('afterViewDefaultChange'))
        .replace('ONCHANGE', fn('onViewDefaultSortChange')))
tmp2 = os.path.join(tempfile.gettempdir(), 'test_v1029_set.js')
io.open(tmp2, 'w', encoding='utf-8', newline='').write(h2)
r2 = subprocess.run(['node', tmp2], capture_output=True, text=True, encoding='utf-8')
print(r2.stdout.rstrip())
if r2.returncode != 0:
    print(r2.stderr.rstrip())
    fails.append('panel setters')


# ═════════ E. wiring ═════════
print('\nE. wiring')
# v10.97 re-pointed: this pinned the EXACT contents of the init Promise.all,
# so adding a fourth org-wide setting (sub-tab visibility) broke it. The
# guarantee this assertion exists for is that the view defaults load in
# PARALLEL with the profile at init, not that the list never grows.
_init = re.search(r'await Promise\.all\(\[loadMyProfile\(\)[^\]]*\]\)', js)
ok(bool(_init), 'the init Promise.all is still there')
ok(bool(_init) and 'loadGlobalViewDefaults()' in _init.group(0),
   'loaded alongside the profile + tab defaults')
ok(bool(_init) and 'loadGlobalTabDefaults()' in _init.group(0),
   'tab defaults still load there too')
# v10.97 re-pointed: this anchored on 'loadGlobalViewDefaults()]' — the ']'
# assumed it was the LAST entry in the init Promise.all. A fourth org-wide
# setting moved it. Anchor on the end of the Promise.all instead; the
# guarantee (defaults applied before init paints) is unchanged.
after = re.sub(r'//[^\n]*', '', js[_init.end():])
ok(after.index('applyGlobalViewDefaults()') < after.index('init()'),
   'applied BEFORE init() paints')
loader = fn('loadGlobalViewDefaults')
ok('_globalViewDefaults = null' in loader and 'catch' in loader, 'fails open on a broken read')

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.29 — all green')
