# -*- coding: utf-8 -*-
"""v10.7 — one page-settings gear; sort inside Customize columns."""
import io, os, re, sys, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
RAW = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)


def fn(name):
    a = js.index('function %s(' % name)
    i = js.index('{', a); depth = 0
    while True:
        c = js[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return js[a:i + 1]
        i += 1


def slab(start, end):
    a = js.index(start); b = js.index(end, a)
    return js[a:b]


REAL = '\n'.join([
    slab("const CATVIS_GLOBAL = '_global';", 'let catVisConfig = {};'),
    fn('catVisPageDef'), fn('catVisInvalidate'), fn('catVisResolved'),
    fn('catVisIdMap'), fn('catVisPass'), fn('catVisAllCats'), fn('catVisAllSubcats'),
    fn('catVisHiddenCount'), fn('catVisSummaryText'),
    slab('const PAGE_SETTINGS_PANELS = [', 'function pageSettingsCurrentNavKey'),
    fn('freezeCurrentKey'), fn('freezeCurrentLabel'),
    fn('pageSettingsPanelsFor'),
])

NAV_TO_PAGE = {
    'forecast_demand': 'forecast', 'forecast_inventory': 'inventory',
    'forecast_seasonality': 'seasonality', 'products': 'products', 'sales': 'sales',
    'pnl_amazon': 'pnl_amazon', 'pnl_amazon_changelog': 'pnl_amazon',
    'pnl_shopify': 'pnl_shopify', 'pnl_walmart': 'pnl_walmart',
    'pnl_chewy_sales': 'pnl_chewy', 'pnl_cogs': 'cogs',
}

static = [
    # ── the gear replaces ten chips ──
    ('the gear button exists in the global search bar',
     'id="pageSettingsBtn"' in RAW
     and RAW.index('id="pageSettingsBtn"') > RAW.index('id="globalSearchBar"')
     and RAW.index('id="pageSettingsBtn"') < RAW.index('<!-- SHEETS BAR')),
    ('the v10.6 per-page chips are gone',
     'catVisInjectChips' not in RAW and 'catvis-chip-' not in RAW),
    ('the gear syncs from the same resolver the search bar uses',
     'function pageSettingsCurrentNavKey' in js and 'globalSearchCurrentKey()' in js),
    ('  and is refreshed by globalSearchSyncFromTarget (all 5 nav paths)',
     "if (typeof pageSettingsSyncIndicator === 'function') pageSettingsSyncIndicator();\n}" in js),
    # v10.9 re-point: PAGE_COLUMN_BUTTONS also uses navKeys, so a file-wide count
    # overshoots. Scope it to the CATVIS_PAGES slab, which is what it was ever about.
    ('every catVis page declares its nav keys',
     slab('const CATVIS_PAGES = [', '];').count('navKeys: [') == 10),

    # ── freeze moved ──
    ('the Forecast freeze dropdown is gone from the filter strip',
     'id="fc-freeze" onchange' not in RAW),
    ('the Inventory freeze dropdown is gone from the filter strip',
     'id="ip-freeze" onchange' not in RAW),
    ('freeze is a page-settings panel instead',
     "id: 'freeze'" in js and 'FREEZE_TARGETS' in js),
    ('  and reuses the untouched v4.142 helpers',
     'fcPopulateFreezeDropdown' in js and 'ipPopulateFreezeDropdown' in js
     and 'onFcFreezeChange' in js and 'onIpFreezeChange' in js),
    ('  the freeze state still lives in localStorage, not the DOM',
     "localStorage.getItem('fcFreezeCol')" in js and "localStorage.getItem('ipFreezeCol')" in js),
    ('the tables still apply freeze on render',
     'fcApplyFreeze' in js and 'ipApplyFreeze' in js),

    # ── sort moved ──
    ('the standalone Sort button is gone', 'id="fc-sort-btn"' not in RAW),
    ('sort now appears inside the column picker',
     'Sort order</div>' in js and 'Edit sort order' in js),
    ('  the picker shows the active chain without opening anything',
     'const sortSummary = sortChain.length' in js),
    ('  and one label resolver serves both surfaces',
     'function fcSortLabelOf' in js and 'const labelOf = fcSortLabelOf;' in js),
    ('  the dialog re-anchors now that its old button is gone',
     "document.getElementById('fc-sort-btn') || document.getElementById('fc-cols-btn')" in js),
    ('shift+click on a header still works (unchanged fast path)',
     'shift+click' in js.lower() or 'shiftKey' in js),

    # ── rename ──
    ('no "View" button labels remain', '\U0001F4CB View' not in RAW),
    ('the column pickers are called Customize columns',
     RAW.count('\U0001F4CB Customize columns') >= 10),
    ('Units Sold is NOT mislabelled (it has no columns to customize)',
     '\U0001F4CB Saved reports</button>' in RAW
     and 'openSalesViewPopup' in RAW),

    # ── one control body, two containers ──
    ('the catvis control body is rendered into a host, not a fixed popover',
     'function catVisRenderControls(host, pageKey, opts)' in js),
    ('  the floating popover is a thin wrapper around it',
     "catVisRenderControls(pop.querySelector('#catVisPopBody'), pageKey)" in js),
    ('  and the page-settings menu renders the same body inline',
     'panel.render(sec.querySelector(\'.psHost\'), pageKey, refreshSummary)' in js),
]

HARNESS = r"""
let allCategories = [
  { id: 1, category: 'Sprays',  subcategory: '3 oz'    },
  { id: 2, category: 'Sprays',  subcategory: '6 oz'    },
  { id: 3, category: 'Treats',  subcategory: 'Crunchy' },
  { id: 4, category: 'Toys',    subcategory: 'Kickers' },
  { id: 5, category: 'Apparel', subcategory: 'Tees'    },
];
function getCategories() { return [...new Set(allCategories.map(c => c.category))].sort(); }
let STORE = {};
const localStorage = {
  getItem: (k) => (k in STORE ? STORE[k] : null),
  setItem: (k, v) => { STORE[k] = String(v); },
  removeItem: (k) => { delete STORE[k]; },
};
let catVisConfig = {};
function catVisPersist() {}
function catVisSyncAllChips() {}
function catVisSetPage() {}
function catVisClearPageOverride() {}
function catVisPromoteToGlobal() {}
function catVisRenderControls() {}
function freezeRenderControls() {}
function fcVisibleColumns() { return [{ key: 'brand', label: 'Brand' }, { key: 'title', label: 'Product' }, { key: 'adj_daily', label: 'Vel/day' }]; }
function ipVisibleColumns() { return [{ key: 'brand', label: 'Brand' }, { key: 'title', label: 'Product' }]; }
function fcPopulateFreezeDropdown() {}
function ipPopulateFreezeDropdown() {}
function onFcFreezeChange() {}
function onIpFreezeChange() {}

__REAL__

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const reset = (cfg) => { catVisConfig = cfg || {}; catVisInvalidate(); STORE = {}; };

console.log('\n== A. Every nav key resolves to the right page ==');
const NAV = __NAV__;
for (const [navKey, want] of Object.entries(NAV)) {
  const panels = pageSettingsPanelsFor(navKey);
  const cv = panels.find(p => p.panel.id === 'catvis');
  t(`${navKey.padEnd(22)} -> ${want}`, cv && cv.pageKey === want, cv && cv.pageKey);
}

console.log('\n== B. The gear hides itself where there is nothing to set ==');
for (const navKey of ['data', 'settings', 'pnl_pricing', 'bundles', 'forecast_chewy', 'pnl_chewy_rebates']) {
  t(`${navKey.padEnd(20)} has no panels`, pageSettingsPanelsFor(navKey).length === 0,
    pageSettingsPanelsFor(navKey).map(p => p.panel.id));
}

console.log('\n== C. Freeze appears on exactly the two grids that have it ==');
const freezeOn = Object.keys(NAV).filter(k => pageSettingsPanelsFor(k).some(p => p.panel.id === 'freeze'));
t('only Demand Forecast + Inventory Planning',
  JSON.stringify(freezeOn.sort()) === JSON.stringify(['forecast_demand', 'forecast_inventory']), freezeOn);
t('  Demand Forecast maps to the fc freeze state',
  pageSettingsPanelsFor('forecast_demand').find(p => p.panel.id === 'freeze').pageKey === 'forecast');
t('  Inventory maps to the ip freeze state',
  pageSettingsPanelsFor('forecast_inventory').find(p => p.panel.id === 'freeze').pageKey === 'inventory');
t('a page with catvis but no freeze shows one panel',
  pageSettingsPanelsFor('pnl_amazon').length === 1);
t('a page with both shows two, catvis first',
  pageSettingsPanelsFor('forecast_demand').map(p => p.panel.id).join() === 'catvis,freeze');

console.log('\n== D. Freeze summary + "is set" read from localStorage ==');
reset({});
t('nothing frozen reads "off"', freezeCurrentLabel('forecast') === 'off');
const freezePanel = PAGE_SETTINGS_PANELS.find(p => p.id === 'freeze');
t('  and isSet is false', freezePanel.isSet('forecast') === false);
STORE['fcFreezeCol'] = 'title';
t('a frozen column names itself', freezeCurrentLabel('forecast') === 'through Product',
  freezeCurrentLabel('forecast'));
t('  and isSet flips true', freezePanel.isSet('forecast') === true);
STORE['fcFreezeCol'] = 'gone_column';
t('a stale key degrades to the raw key rather than throwing',
  freezeCurrentLabel('forecast') === 'through gone_column', freezeCurrentLabel('forecast'));
STORE['ipFreezeCol'] = 'brand';
t('the two grids keep separate state',
  freezeCurrentLabel('inventory') === 'through Brand' && freezeCurrentLabel('forecast') === 'through gone_column');

console.log('\n== E. Category-visibility panel summary ==');
const cvPanel = PAGE_SETTINGS_PANELS.find(p => p.id === 'catvis');
reset({});
t('unset reads "nothing hidden"', cvPanel.summary('inventory') === 'nothing hidden');
t('  and isSet is false', cvPanel.isSet('inventory') === false);
reset({ inventory: { cats: ['Sprays', 'Treats', 'Toys'], subcats: null } });
t('a page override says so', cvPanel.summary('inventory') === '1 category hidden \u00b7 this page',
  cvPanel.summary('inventory'));
reset({ _global: { cats: ['Sprays'], subcats: null } });
t('an inherited scope is labelled global',
  cvPanel.summary('inventory') === '3 categories hidden \u00b7 global', cvPanel.summary('inventory'));
reset({ _global: { cats: ['Sprays'], subcats: ['3 oz'] } });
t('both axes are counted',
  cvPanel.summary('cogs') === '3 categories + 4 sub-categories hidden \u00b7 global', cvPanel.summary('cogs'));

console.log('\n== F. Registry shape \u2014 adding a panel must stay cheap ==');
for (const p of PAGE_SETTINGS_PANELS) {
  t(`panel "${p.id}" has the full contract`,
    typeof p.pageKeyFor === 'function' && typeof p.isSet === 'function'
    && typeof p.summary === 'function' && typeof p.render === 'function'
    && typeof p.label === 'string' && typeof p.icon === 'string' && typeof p.hint === 'string');
}
t('panel ids are unique',
  new Set(PAGE_SETTINGS_PANELS.map(p => p.id)).size === PAGE_SETTINGS_PANELS.length);

console.log('\n== G. Nothing throws on an unknown or malformed page ==');
for (const k of ['', 'nope', null, undefined]) {
  let threw = false, out;
  try { out = pageSettingsPanelsFor(k); } catch { threw = true; }
  t('pageSettingsPanelsFor(' + JSON.stringify(k) + ') is safe', !threw && Array.isArray(out), out);
}
let threwFz = false;
try { freezeCurrentLabel('nope'); freezeCurrentKey('nope'); } catch { threwFz = true; }
t('freeze helpers survive an unknown grid', !threwFz);
t('  and report off', freezeCurrentKey('nope') === '');

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
"""

import json
static_js = '\n'.join("t(%r, %s);" % (n, 'true' if v else 'false') for n, v in static)
out = (HARNESS.replace('__REAL__', REAL)
              .replace('__NAV__', json.dumps(NAV_TO_PAGE))
              .replace("console.log('\\n== A.",
                       "console.log('\\n== 0. Static assertions against the shipped source ==');\n"
                       + static_js + "\nconsole.log('\\n== A."))
p = os.path.join(SP, 'test_v107.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(out)
print('harness %d chars' % len(out))
sys.exit(subprocess.call(['node', p]))
