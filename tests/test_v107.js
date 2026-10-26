
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

const _CATVIS_INVISIBLE = /[\u200B-\u200D\uFEFF\u2060\u00AD]/g;
const _CATVIS_SPACES    = /[\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]/g;
let _catVisUniv = null;
function catVisMatchKey(v) { return catVisNorm(v).toLowerCase(); }
function _catVisDedupe(values) {
  const seen = new Map();
  for (const raw of values) {
    const disp = catVisNorm(raw);
    if (!disp) continue;
    const k = catVisMatchKey(disp);
    if (!seen.has(k)) seen.set(k, disp);
  }
  return [...seen.values()].sort((a, b) => a.localeCompare(b));
}
function catVisUniverse() {
  if (_catVisUniv) return _catVisUniv;
  _catVisUniv = {
    cats: new Set(catVisAllCats().map(catVisMatchKey)),
    subs: new Set(catVisAllSubcats().map(catVisMatchKey)),
  };
  return _catVisUniv;
}
const CATVIS_GLOBAL = '_global';
const CATVIS_LS_KEY = 'catVisConfig';

// One entry per surface that filters products by category. `selectId` is the
// page's existing Category <select>, used purely as the injection anchor for
// the chip (every one of them is static markup, present from first paint, so
// a single injection pass at init covers all ten).
const CATVIS_PAGES = [
  { key: 'forecast',    label: 'Demand Forecast',    selectId: 'fCategory',        navKeys: ['forecast_demand'],        rerender: () => { if (typeof renderAll === 'function') renderAll(); } },
  { key: 'inventory',   label: 'Inventory Planning', selectId: 'ip-category',      navKeys: ['forecast_inventory'],      rerender: () => { if (typeof renderInventoryTbl === 'function') renderInventoryTbl(); } },
  { key: 'seasonality', label: 'Seasonality',        selectId: 'sea-category',     navKeys: ['forecast_seasonality'],     rerender: () => { if (typeof renderSeasonalityList === 'function') renderSeasonalityList(); } },
  { key: 'products',    label: 'Products',           selectId: 'prodCat',          navKeys: ['products'],          rerender: () => { if (typeof renderProductsTbl === 'function') renderProductsTbl(); } },
  { key: 'sales',       label: 'Units Sold',         selectId: 'salesCat',         navKeys: ['sales'],         rerender: () => { if (typeof renderSalesTbl === 'function') renderSalesTbl(); } },
  { key: 'pnl_amazon',  label: 'Amazon P&L',         selectId: 'pnl-cat',          navKeys: ['pnl_amazon','pnl_amazon_changelog'],          rerender: () => { if (typeof renderPnl === 'function') renderPnl(); } },
  { key: 'pnl_shopify', label: 'Shopify P&L',        selectId: 'spnl-cat',         navKeys: ['pnl_shopify'],         rerender: () => { if (typeof renderShopifyPnl === 'function') renderShopifyPnl(); } },
  { key: 'pnl_walmart', label: 'Walmart P&L',        selectId: 'wmpnl-cat',        navKeys: ['pnl_walmart'],        rerender: () => { if (typeof renderWalmartPnl === 'function') renderWalmartPnl(); } },
  { key: 'pnl_chewy',   label: 'Chewy P&L — Sales',  selectId: 'chpnl-sales-cat',  navKeys: ['pnl_chewy_sales'],  rerender: () => { if (typeof renderChewyPnlSales === 'function') renderChewyPnlSales(); } },
  { key: 'pnl_chewy_cost', label: 'Chewy P&L — Cost',  selectId: 'chpnl-cost-cat',   navKeys: ['pnl_chewy_cost'],   rerender: () => { if (typeof renderChewyPnlCost === 'function') renderChewyPnlCost(); } },
  { key: 'pnl_chewy_be', label: 'Chewy P&L — Break-Even', selectId: 'chpnl-be-cat', navKeys: ['pnl_chewy_breakeven'], rerender: () => { if (typeof renderChewyBreakeven === 'function') renderChewyBreakeven(); } },
  { key: 'cogs',        label: 'COGS',               selectId: 'cogs-cat',         navKeys: ['pnl_cogs'],         rerender: () => { if (typeof renderCogsTbl === 'function') renderCogsTbl(); } },
];
// Deliberately NOT wired:
//   • #pnew-category (Pricing Scenarios) — a MODELING input. It picks which
//     comparable products the fee benchmark is derived from; silently hiding
//     categories there would move the cost floor and therefore the verdict.
//   • #chpnl-category (Chewy Rebates) — a different taxonomy entirely, inferred
//     from rebate + agreement names, not products.category_id.
function catVisPageDef(key) { return CATVIS_PAGES.find(p => p.key === key) || null; }


function catVisPageDef(key) { return CATVIS_PAGES.find(p => p.key === key) || null; }
function catVisInvalidate() { _catVisCache = {}; _catVisIdMap = null; _catVisUniv = null; }
function catVisResolved(pageKey) {
  if (_catVisCache[pageKey]) return _catVisCache[pageKey];
  const mk = (src, source) => ({
    cats:    Array.isArray(src?.cats)    ? new Set(src.cats)    : null,
    subcats: Array.isArray(src?.subcats) ? new Set(src.subcats) : null,
    source,
  });
  let res;
  if (Object.prototype.hasOwnProperty.call(catVisConfig, pageKey)) res = mk(catVisConfig[pageKey], 'page');
  else if (Object.prototype.hasOwnProperty.call(catVisConfig, CATVIS_GLOBAL)) res = mk(catVisConfig[CATVIS_GLOBAL], 'global');
  else res = { cats: null, subcats: null, source: 'none' };
  _catVisCache[pageKey] = res;
  return res;
}
function catVisNorm(v) {
  return String(v == null ? '' : v)
    .replace(_CATVIS_INVISIBLE, '')
    .replace(_CATVIS_SPACES, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
function catVisSetHas(set, value) {
  if (!set) return true;
  if (set.has(value)) return true;
  const k = catVisMatchKey(value);
  for (const v of set) if (catVisMatchKey(v) === k) return true;
  return false;
}
function catVisIdMap() {
  if (_catVisIdMap) return _catVisIdMap;
  _catVisIdMap = new Map();
  if (typeof allCategories !== 'undefined' && Array.isArray(allCategories)) {
    for (const c of allCategories) _catVisIdMap.set(c.id, c);
  }
  return _catVisIdMap;
}
function catVisPass(pageKey, obj) {
  if (_catVisSuppressed.has(pageKey)) return true;   // dismissed for this session
  const r = catVisResolved(pageKey);
  if (!r.cats && !r.subcats) return true;          // fast path — nothing hidden
  if (!obj) return true;
  let cat = catVisNorm(obj.category);
  let sub = catVisNorm(obj.subcategory);
  if ((!cat || !sub) && obj.category_id != null) {
    const row = catVisIdMap().get(obj.category_id);
    if (row) { cat = cat || catVisNorm(row.category); sub = sub || catVisNorm(row.subcategory); }
  }
  if (!cat && !sub) return true;                   // unclassifiable → visible
  // ⚠ v10.45 — both sides trimmed. A stored set written before v10.45 can hold
  // an untrimmed name, and `categories` rows can carry stray whitespace; either
  // one made a product fail a membership test it visibly passed on screen.
  // ⚠ v10.46 — a value that is NOT in the universe has no checkbox, so the
  // operator cannot have unchecked it. Hiding on it is hiding on something
  // nobody chose, and it is unrecoverable from the UI: there is no row to
  // re-tick. Only values the picker actually renders may hide a product.
  const uni = catVisUniverse();
  if (r.cats    && cat && uni.cats.has(catVisMatchKey(cat))
      && !catVisSetHas(r.cats, cat)) return false;
  if (r.subcats && sub && uni.subs.has(catVisMatchKey(sub))
      && !catVisSetHas(r.subcats, sub)) return false;
  return true;
}
function catVisAllCats() {
  if (typeof getCategories === 'function') {
    try {
      const g = getCategories();
      if (g) return _catVisDedupe(g);
    } catch {}
  }
  if (typeof allCategories !== 'undefined' && Array.isArray(allCategories)) {
    return _catVisDedupe(allCategories.map(c => c.category));
  }
  return [];
}
function catVisAllSubcats() {
  if (typeof allCategories !== 'undefined' && Array.isArray(allCategories)) {
    return _catVisDedupe(allCategories.map(c => c.subcategory));
  }
  return [];
}
function catVisHiddenCount(pageKey) {
  const r = catVisResolved(pageKey);
  const allC = catVisAllCats(), allS = catVisAllSubcats();
  // v10.45 — the NAMES, not just the count. "3 sub-categories hidden" is the
  // answer to a question nobody asked; "Apparel, Jar, Tote" is the one that
  // tells you why a product vanished.
  const catNames = r.cats    ? allC.filter(v => !catVisSetHas(r.cats, v))    : [];
  const subNames = r.subcats ? allS.filter(v => !catVisSetHas(r.subcats, v)) : [];
  return {
    cats: catNames.length, subs: subNames.length,
    catNames, subNames,
    total: catNames.length + subNames.length,
    source: r.source,
  };
}
function catVisNameList(names, cap) {
  const n = cap || 4;
  if (!names || !names.length) return '';
  if (names.length <= n) return names.join(', ');
  return names.slice(0, n).join(', ') + ' +' + (names.length - n) + ' more';
}
function catVisSummaryText(pageKey) {
  const h = catVisHiddenCount(pageKey);
  if (!h.total) return 'nothing hidden';
  const bits = [];
  if (h.cats) bits.push(`${h.cats} categor${h.cats === 1 ? 'y' : 'ies'}`);
  if (h.subs) bits.push(`${h.subs} sub-categor${h.subs === 1 ? 'y' : 'ies'}`);
  return bits.join(' + ') + ' hidden';
}
function catVisSummaryNamed(pageKey) {
  const h = catVisHiddenCount(pageKey);
  if (!h.total) return 'nothing hidden';
  const bits = [];
  if (h.cats) bits.push('hiding ' + catVisNameList(h.catNames));
  if (h.subs) bits.push('hiding sub ' + catVisNameList(h.subNames));
  return bits.join(' \u00b7 ');
}
const PAGE_SETTINGS_PANELS = [
  {
    // v10.34 — listed FIRST on purpose. "Why can't I see my product?" is the
    // question people open this menu with, and the answer is here.
    id: 'activefilters',
    icon: '\u{1F50D}',
    label: 'Active filters',
    hint: 'Everything currently narrowing this page, from the filter bar, the Top Products chip, category visibility and the org default. Clearing one is for this session only \u2014 your saved settings come back on reload.',
    pageKeyFor: (navKey) => (PAGE_FILTERS[navKey] ? navKey : null),
    isSet:   (navKey) => activeFiltersFor(navKey).length > 0,
    summary: (navKey) => activeFiltersSummary(navKey),
    render:  (host, navKey) => activeFiltersRenderControls(host, navKey),
  },
  {
    id: 'catvis',
    icon: '\u{1F441}',
    label: 'Category visibility',
    hint: 'Which product categories and sub-categories show on this page by default. Saved to your profile, so it follows you across browsers and sessions.',
    // Return the key this panel should operate on, or null to not appear.
    pageKeyFor: (navKey) => {
      const d = CATVIS_PAGES.find(p => (p.navKeys || []).includes(navKey));
      return d ? d.key : null;
    },
    isSet:   (pageKey) => catVisHiddenCount(pageKey).total > 0,
    summary: (pageKey) => {
      const h = catVisHiddenCount(pageKey);
      if (!h.total) return 'nothing hidden';
      // v10.46 — the count alone sent Jason scrolling a 33-row list twice.
      return catVisSummaryNamed(pageKey) + (h.source === 'global' ? ' · global' : ' · this page');
    },
    render:  (host, pageKey, onAfterChange) => catVisRenderControls(host, pageKey, { onAfterChange }),
  },
  {
    id: 'freeze',
    icon: '\u{1F9CA}',
    label: 'Freeze columns',
    hint: 'Pin every column up to and including the one you pick, so the identity columns stay put while you scroll the wide grid sideways. Saved per browser.',
    pageKeyFor: (navKey) => FREEZE_TARGETS[navKey] || null,
    isSet:   (which) => !!freezeCurrentKey(which),
    summary: (which) => freezeCurrentLabel(which),
    render:  (host, which, onAfterChange) => freezeRenderControls(host, which, onAfterChange),
  },
  {
    // v10.95 — which SUB-TABS this page shows. Jason: "make a per page tab
    // visibility setting, set globally, like the other settings." Sits in the
    // gear for the same reason the v10.28 panel does: this is already the
    // per-page settings surface and resolves the current page through the same
    // nav key, so "per page" comes for free.
    id: 'subtabvis',
    icon: '\u{1F5C2}',
    label: 'Sub-tabs on this page',
    hint: 'Which sub-tabs appear on this page, for everyone. Admin-only to change. Nothing is deleted — a hidden sub-tab comes back the moment you tick it again, and at least one always stays visible.',
    pageKeyFor: (navKey) => subtabVisStripFor(navKey),
    isSet:   (stripKey) => subtabVisHiddenCount(stripKey) > 0,
    summary: (stripKey) => subtabVisSummary(stripKey),
    render:  (host, stripKey, onAfterChange) => subtabVisRenderControls(host, stripKey, onAfterChange),
  },
  {
    // v10.28 — the org-wide default for THIS page. Lives here rather than on
    // the Settings page because this is already the per-page settings surface:
    // it resolves the current page through the same nav key the gear and the
    // global search bar use, so "per page" comes for free.
    id: 'viewdefault',
    icon: '\u{1F310}',
    label: 'Default view for everyone',
    hint: 'What this page looks like when anyone opens it \u2014 active-only, hide-bundles and the default sort, whichever this page has. Admin-only to change. A personal choice always wins over it.',
    pageKeyFor: (navKey) => (viewDefaultPageFor(navKey) || {}).key || null,
    isSet:   (pageKey) => !!(_globalViewDefaults || {})[pageKey],
    summary: (pageKey) => viewDefaultSummary(pageKey),
    render:  (host, pageKey, onAfterChange) => viewDefaultRenderControls(host, pageKey, onAfterChange),
  },
];

// v4.142 freeze, relocated. The state has always lived in localStorage and
// fcApplyFreeze / ipApplyFreeze read it directly, so moving the <select> out of
// the filter strip and into this menu needed no change to the freeze logic at
// all — the populate helpers are id-based and already guard on a missing node.
const FREEZE_TARGETS = { forecast_demand: 'forecast', forecast_inventory: 'inventory' };
const FREEZE_META = {
  forecast:  { ls: 'fcFreezeCol', sel: 'fc-freeze', cols: () => (typeof fcVisibleColumns === 'function' ? fcVisibleColumns() : []),
               populate: () => { if (typeof fcPopulateFreezeDropdown === 'function') fcPopulateFreezeDropdown(); },
               change: (v) => { if (typeof onFcFreezeChange === 'function') onFcFreezeChange(v); } },
  inventory: { ls: 'ipFreezeCol', sel: 'ip-freeze', cols: () => (typeof ipVisibleColumns === 'function' ? ipVisibleColumns() : []),
               populate: () => { if (typeof ipPopulateFreezeDropdown === 'function') ipPopulateFreezeDropdown(); },
               change: (v) => { if (typeof onIpFreezeChange === 'function') onIpFreezeChange(v); } },
};
function freezeCurrentKey(which) {
  const m = FREEZE_META[which]; if (!m) return '';
  try { return localStorage.getItem(m.ls) || ''; } catch { return ''; }
}
function freezeCurrentLabel(which) {
  const key = freezeCurrentKey(which);
  if (!key) return 'off';
  const m = FREEZE_META[which];
  const col = (m.cols() || []).find(c => c.key === key);
  const name = col ? String(col.label || col.key).replace(/<[^>]+>/g, '').trim() : key;
  return 'through ' + name;
}
function freezeRenderControls(host, which, onAfterChange) {
  const m = FREEZE_META[which];
  if (!host || !m) return;
  host.innerHTML = `<select id="${m.sel}" style="width:100%;font-family:var(--mono);font-size:11px;background:var(--surface2);`
    + 'color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:5px 8px;outline:none"></select>';
  const sel = host.querySelector('#' + m.sel);
  m.populate();                      // same helper the filter strip used to drive
  sel.onchange = () => {
    m.change(sel.value);             // persists + re-renders the table
    if (typeof pageSettingsSyncIndicator === 'function') pageSettingsSyncIndicator();
    if (typeof onAfterChange === 'function') onAfterChange();
  };
}

// v10.9 — the column picker is page chrome too. One registry, same nav keys,
// same resolver: on each nav we reveal the button that belongs here and hide
// the other five. Pages with no picker (Seasonality, Walmart / Chewy P&L, COGS,
// Bundles, Data, Settings) simply show none.
const PAGE_COLUMN_BUTTONS = [
  { id: 'fc-cols-btn',   navKeys: ['forecast_demand'] },
  { id: 'ip-view-btn',   navKeys: ['forecast_inventory'] },
  { id: 'prod-view-btn', navKeys: ['products'] },
  { id: 'sales-view-btn',navKeys: ['sales'] },
  { id: 'pnl-cols-btn',  navKeys: ['pnl_amazon', 'pnl_amazon_changelog'] },   // NOT breakeven — it has its own (v10.43)
  { id: 'spnl-cols-btn', navKeys: ['pnl_shopify'] },
  { id: 'be-view-btn',   navKeys: ['pnl_amazon_breakeven'] },   // v10.43
  { id: 'chewy-cols-btn', navKeys: ['pnl_chewy_sales', 'pnl_chewy_cost', 'pnl_chewy_breakeven'] },   // v10.58
];
function pageColsSyncButton() {
  const navKey = (typeof pageSettingsCurrentNavKey === 'function') ? pageSettingsCurrentNavKey() : '';
  for (const b of PAGE_COLUMN_BUTTONS) {
    const el = document.getElementById(b.id);
    if (el) el.style.display = b.navKeys.includes(navKey) ? '' : 'none';
  }
}

// Which nav surface we are on. Reuses the global search bar's resolver so the
// gear and the search box can never disagree about what "this page" means.

function freezeCurrentKey(which) {
  const m = FREEZE_META[which]; if (!m) return '';
  try { return localStorage.getItem(m.ls) || ''; } catch { return ''; }
}
function freezeCurrentLabel(which) {
  const key = freezeCurrentKey(which);
  if (!key) return 'off';
  const m = FREEZE_META[which];
  const col = (m.cols() || []).find(c => c.key === key);
  const name = col ? String(col.label || col.key).replace(/<[^>]+>/g, '').trim() : key;
  return 'through ' + name;
}
function pageSettingsPanelsFor(navKey) {
  const out = [];
  for (const p of PAGE_SETTINGS_PANELS) {
    let key = null;
    try { key = p.pageKeyFor(navKey); } catch {}
    if (key) out.push({ panel: p, pageKey: key });
  }
  return out;
}

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const reset = (cfg) => { catVisConfig = cfg || {}; catVisInvalidate(); STORE = {}; };

console.log('\n== 0. Static assertions against the shipped source ==');
t('the gear button exists in the global search bar', true);
t('the v10.6 per-page chips are gone', true);
t('the gear syncs from the same resolver the search bar uses', true);
t('  and is refreshed by globalSearchSyncFromTarget (all 5 nav paths)', true);
t('every catVis page declares its nav keys', true);
t('the Forecast freeze dropdown is gone from the filter strip', true);
t('the Inventory freeze dropdown is gone from the filter strip', true);
t('freeze is a page-settings panel instead', true);
t('  and reuses the untouched v4.142 helpers', true);
t('  the freeze state still lives in localStorage, not the DOM', true);
t('the tables still apply freeze on render', true);
t('the standalone Sort button is gone', true);
t('sort now appears inside the column picker', true);
t('  the picker shows the active chain without opening anything', true);
t('  and one label resolver serves both surfaces', true);
t('  the dialog re-anchors now that its old button is gone', true);
t('shift+click on a header still works (unchanged fast path)', true);
t('no "View" button labels remain', true);
t('the column pickers are called Customize columns', true);
t('Units Sold is NOT mislabelled (it has no columns to customize)', true);
t('the catvis control body is rendered into a host, not a fixed popover', true);
t('  the floating popover is a thin wrapper around it', true);
t('  and the page-settings menu renders the same body inline', true);
console.log('\n== A. Every nav key resolves to the right page ==');
const NAV = {"forecast_demand": "forecast", "forecast_inventory": "inventory", "forecast_seasonality": "seasonality", "products": "products", "sales": "sales", "pnl_amazon": "pnl_amazon", "pnl_amazon_changelog": "pnl_amazon", "pnl_shopify": "pnl_shopify", "pnl_walmart": "pnl_walmart", "pnl_chewy_sales": "pnl_chewy", "pnl_cogs": "cogs"};
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
// \u26a0 v10.46 — the gear summary NAMES the hidden values instead of counting
// them. The count sent Jason scrolling a 33-row checkbox list twice looking for
// which three were off; naming them is the whole point, so this moves with it.
t('a page override NAMES what it hides',
  cvPanel.summary('inventory') === 'hiding Apparel \u00b7 this page',
  cvPanel.summary('inventory'));
reset({ _global: { cats: ['Sprays'], subcats: null } });
t('an inherited scope is labelled global and still names them',
  cvPanel.summary('inventory') === 'hiding Apparel, Toys, Treats \u00b7 global',
  cvPanel.summary('inventory'));
reset({ _global: { cats: ['Sprays'], subcats: ['3 oz'] } });
t('both axes are named',
  cvPanel.summary('cogs') === 'hiding Apparel, Toys, Treats \u00b7 hiding sub 6 oz, Crunchy, Kickers, Tees \u00b7 global',
  cvPanel.summary('cogs'));

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
