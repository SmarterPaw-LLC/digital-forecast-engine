# -*- coding: utf-8 -*-
"""
v10.34 — "Active filters": see everything narrowing this page, clear any of it.

Jason: "i cannot find buds jar when is search for it, and i do not konw what
filters are applied that could be causing this."

The Products page can be narrowed from FOUR surfaces — the filter bar, the Top
Products chip above the table, category visibility inside the gear, and the
v10.26 org default which is visible nowhere at all. A product disappears and
nothing tells you which one did it.

⚠ The assertion that earns its keep is the ID SWEEP. Every control the registry
names must exist in the markup. Writing this registry I guessed three IDs wrong
(`fStatus`, `srch`, `ip-search`) and a missing element fails SILENTLY here —
_afVal returns '' so the filter simply never appears in the panel, which is the
exact failure the panel exists to prevent. Same class as v10.30's invented
function names; this time it is caught by a test rather than by Jason.
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


REG = re.search(r'const PAGE_FILTERS = \{(.*?)\n\};', js, re.S)
if not REG:
    raise SystemExit('FAIL: cannot find PAGE_FILTERS')
REG = REG.group(1)


# ═════════ A. the ID sweep ═════════
print('\nA. every control the registry names exists in the markup')

ids = re.findall(r"af(?:Select|Search|Hide)\('([^']+)'", REG)
missing = [i for i in ids if ('id="%s"' % i) not in src]
ok(not missing,
   '%d referenced control ids all exist' % len(ids)
   + ('' if not missing else ' — MISSING: ' + ', '.join(missing)))
ok(len(ids) >= 30, 'the registry covers a meaningful number of filters (%d)' % len(ids))

# ⚠ Has teeth? A deliberately bogus id must be reported.
probe = ids + ['definitely-not-a-real-control']
probe_missing = [i for i in probe if ('id="%s"' % i) not in src]
ok(probe_missing == ['definitely-not-a-real-control'],
   'regression guard — the sweep DOES flag an id that is not in the markup')

# Every page in the registry must declare a re-render, or clearing a filter
# updates the stored value and leaves the table showing the old rows.
pages = re.findall(r'^  ([a-z_]+): \(\) =>', REG, re.M)
rr = re.search(r'const PAGE_FILTER_RERENDER = \{(.*?)\n\};', js, re.S).group(1)
rr_pages = set(re.findall(r"^\s*([a-z_]+):", rr, re.M))
ok(set(pages) <= rr_pages,
   'every page with filters declares a re-render'
   + ('' if set(pages) <= rr_pages else ' — missing: ' + ', '.join(sorted(set(pages) - rr_pages))))
for fname in set(re.findall(r"'([a-zA-Z]+)'", rr)):
    ok(re.search(r'\bfunction %s\s*\(' % re.escape(fname), js) is not None,
       '  re-render %s() is a real function' % fname)


# ═════════ B. session-only dismissal ═════════
print('\nB. dismissing is session-only — saved settings come back on reload')

ok('const _catVisSuppressed = new Set()' in js,
   'category visibility uses a session Set, not a write')
cvp = fn('catVisPass')
ok('_catVisSuppressed.has(pageKey)' in cvp,
   '  and catVisPass consults it')
# ⚠ It must NOT persist. catVisSetPage / catVisPersist would survive a reload,
# which is the opposite of what Jason asked for.
cv_desc = re.search(r'const afCatVis = \(catVisKey\) => \(\{(.*?)\n\}\);', js, re.S).group(1)
ok('catVisSetPage' not in cv_desc and 'catVisPersist' not in cv_desc,
   '  and clearing it never writes the saved setting')
ok('sessionOnly: true' in cv_desc, '  flagged sessionOnly so the UI can say so')

# The DOM-backed filters are not persisted anywhere, so they are session-only
# by construction — assert the clear path only touches the element.
ok('const _afSetVal' in js and 'e.value = v' in js, 'select/search clears write to the element only')


# ═════════ C. behaviour ═════════
print('\nC. behaviour — the real activeFiltersFor / clear paths')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

const EL = {};
const mkSel = (id, v, opts) => EL[id] = { id, value: v,
  options: opts.map(x => ({ value: x, textContent: x || 'All' })),
  get selectedIndex() { return this.options.findIndex(o => o.value === this.value); } };
const mkTxt = (id, v) => EL[id] = { id, value: v };
const mkChk = (id, c) => EL[id] = { id, checked: c };
const document = { getElementById: id => EL[id] || null };
const Event = function () {};

let topProductFilterId = null;
let allProducts = [{ master_id: 'SP-1', short_name: 'Buds Jar', title: 'Buds Jar' }];
function setTopProductFilter(v) { topProductFilterId = v; }
const _catVisSuppressed = new Set();
let _hidden = { cats: 2, subs: 0, total: 2, source: 'global' };
function catVisHiddenCount() { return _hidden; }
function catVisSummaryText() { return '2 hidden'; }
// v10.45 — the Active filters row names the hidden VALUES now, which is
// the whole point of the change: "3 sub-categories hidden" never told
// anyone WHICH three.
function catVisSummaryNamed() { return 'hiding sub Apparel, Jar'; }
function catVisInvalidate() {}
function pageSettingsRefresh() {}
function pageSettingsSyncIndicator() {}
const window = {};
const _afHosts = {};

HELPERS
REGISTRY
RERENDER
FORFN
CLEARONE
CLEARALL
AFTER
SUMMARY

function resetDom() {
  mkSel('prodBrand', '', ['', 'Meowijuana']);
  mkSel('prodFilter', '', ['', 'active', 'bundle']);
  mkSel('prodCat', '', ['', 'Toys']);
  mkTxt('prodSrch', '');
  topProductFilterId = null;
  _catVisSuppressed.clear();
  _hidden = { cats: 0, subs: 0, total: 0, source: 'page' };
}

// ═════ nothing on ═════
resetDom();
t('clean page reports no filters', activeFiltersFor('products').map(f => f.key), []);
t('  summary says none', activeFiltersSummary('products'), 'none');

// ═════ Jason's actual situation: searching and finding nothing ═════
resetDom();
mkTxt('prodSrch', 'buds jar');
EL['prodFilter'].value = 'active';
_hidden = { cats: 3, subs: 0, total: 3, source: 'global' };
topProductFilterId = 'SP-1';
const on = activeFiltersFor('products');
t('every surface narrowing the page is listed',
  on.map(f => f.key), ['topproduct', 'prodFilter', 'catvis', 'prodSrch']);
t('  including the chip, named by product', on.find(f => f.key === 'topproduct').display, 'Buds Jar');
// v10.45 — NAMES the hidden values, not just a count.
t('  the gear-hidden category visibility NAMES what is hidden', on.find(f => f.key === 'catvis').display, 'hiding sub Apparel, Jar · global');
t('  and the search text', on.find(f => f.key === 'prodSrch').display, '"buds jar"');
t('  summary counts them', activeFiltersSummary('products'), '4 filters on');

// ═════ clearing one at a time ═════
clearActiveFilter('products', 'topproduct');
t('clearing the chip drops it', topProductFilterId, null);
t('  and leaves the others alone', activeFiltersFor('products').map(f => f.key),
  ['prodFilter', 'catvis', 'prodSrch']);

clearActiveFilter('products', 'catvis');
t('clearing category visibility suppresses it for the session',
  _catVisSuppressed.has('products'), true);
t('  without touching the saved setting', _hidden.total, 3);
t('  so it stops being listed', activeFiltersFor('products').some(f => f.key === 'catvis'), false);

clearActiveFilter('products', 'prodSrch');
t('clearing search empties the input', EL['prodSrch'].value, '');

// ═════ clear all ═════
resetDom();
mkTxt('prodSrch', 'x'); EL['prodBrand'].value = 'Meowijuana'; topProductFilterId = 'SP-1';
clearAllActiveFilters('products');
t('clear all empties everything', activeFiltersFor('products').map(f => f.key), []);

// ═════ a select whose value is empty is NOT a filter ═════
resetDom();
EL['prodBrand'].value = '';
t('an unset dropdown is not reported', activeFiltersFor('products').length, 0);

// ═════ a missing control must not break the panel ═════
resetDom();
delete EL['prodCat'];
let threw = false;
try { activeFiltersFor('products'); } catch (e) { threw = true; }
t('a control that is not on screen does not throw', threw, false);

// ═════ an unknown page is empty, not an error ═════
t('a page with no filter registry returns nothing', activeFiltersFor('nosuchpage'), []);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""

def const_block(name, opener, closer):
    m = re.search(r'\nconst %s = \%s' % (re.escape(name), opener), js)
    i = js.index(opener, m.end() - 1)
    depth, j = 0, i
    while j < len(js):
        if js[j] == opener:
            depth += 1
        elif js[j] == closer:
            depth -= 1
            if depth == 0:
                break
        j += 1
    return js[m.start() + 1:j + 1] + ';'

helpers = '\n'.join(
    re.search(r'^const %s = .*?;$' % h, js, re.M | re.S).group(0)
    for h in ['_afVal']) + '\n'
# The multi-line helpers need balanced slicing.
for h in ['_afSetVal', '_afSetChk', '_afSelLabel', 'afSelect', 'afSearch', 'afHide', 'afCatVis', 'afTopProduct']:
    m = re.search(r'\nconst %s = ' % h, js)
    i, depth, j = m.start() + 1, 0, m.end()
    while j < len(js):
        c = js[j]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c == ';' and depth == 0:
            break
        j += 1
    helpers += js[i:j + 1] + '\n'

harness = (harness
           .replace('HELPERS', helpers)
           .replace('REGISTRY', const_block('PAGE_FILTERS', '{', '}'))
           .replace('RERENDER', const_block('PAGE_FILTER_RERENDER', '{', '}'))
           .replace('FORFN', fn('activeFiltersFor'))
           .replace('CLEARONE', fn('clearActiveFilter'))
           .replace('CLEARALL', fn('clearAllActiveFilters'))
           .replace('AFTER', fn('afterFilterCleared'))
           .replace('SUMMARY', fn('activeFiltersSummary')))

tmp = os.path.join(tempfile.gettempdir(), 'test_v1034_filters.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1600])
    fails.append('active-filters behaviour')


# ═════════ D. placement ═════════
print('\nD. placement')
registry = js[js.index('const PAGE_SETTINGS_PANELS = ['):]
registry = registry[:registry.index('\n];')]
ok("id: 'activefilters'" in registry, 'registered as a gear panel')
ok(registry.index("id: 'activefilters'") < registry.index("id: 'catvis'"),
   "listed FIRST — it is the question people open the menu with")
ok("id: 'viewdefault'" in registry, '  the other panels are still there')

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.34 — all green')
