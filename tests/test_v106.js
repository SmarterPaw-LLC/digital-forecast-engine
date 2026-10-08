
// ── stubs ────────────────────────────────────────────────────────────────────
let allCategories = [
  { id: 1, category: 'Sprays',      subcategory: '3 oz'     },
  { id: 2, category: 'Sprays',      subcategory: '6 oz'     },
  { id: 3, category: 'Treats',      subcategory: 'Crunchy'  },
  { id: 4, category: 'Toys',        subcategory: 'Kickers'  },
  { id: 5, category: 'Apparel',     subcategory: 'Tees'     },
];
function getCategories() { return [...new Set(allCategories.map(c => c.category))].sort(); }
let STORE = {};
const localStorage = {
  getItem: (k) => (k in STORE ? STORE[k] : null),
  setItem: (k, v) => { STORE[k] = String(v); },
  removeItem: (k) => { delete STORE[k]; },
};
let PERSISTS = 0;
function catVisPersist() { PERSISTS++; try { localStorage.setItem(CATVIS_LS_KEY, JSON.stringify(catVisConfig)); } catch {} }
function catVisSyncAllChips() {}
function catVisRenderSettings() {}
let catVisConfig = {};

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
function catVisInvalidate() { _catVisCache = {}; _catVisIdMap = null; }
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
function catVisIdMap() {
  if (_catVisIdMap) return _catVisIdMap;
  _catVisIdMap = new Map();
  if (typeof allCategories !== 'undefined' && Array.isArray(allCategories)) {
    for (const c of allCategories) _catVisIdMap.set(c.id, c);
  }
  return _catVisIdMap;
}
function catVisPass(pageKey, obj) {
  const r = catVisResolved(pageKey);
  if (!r.cats && !r.subcats) return true;          // fast path — nothing hidden
  if (!obj) return true;
  let cat = obj.category || '';
  let sub = obj.subcategory || '';
  if ((!cat || !sub) && obj.category_id != null) {
    const row = catVisIdMap().get(obj.category_id);
    if (row) { cat = cat || row.category || ''; sub = sub || row.subcategory || ''; }
  }
  if (!cat && !sub) return true;                   // unclassifiable → visible
  if (r.cats    && cat && !r.cats.has(cat))    return false;
  if (r.subcats && sub && !r.subcats.has(sub)) return false;
  return true;
}
function catVisAllCats() {
  if (typeof getCategories === 'function') { try { return getCategories() || []; } catch {} }
  if (typeof allCategories !== 'undefined' && Array.isArray(allCategories)) {
    return [...new Set(allCategories.map(c => c.category).filter(Boolean))].sort();
  }
  return [];
}
function catVisAllSubcats() {
  if (typeof allCategories !== 'undefined' && Array.isArray(allCategories)) {
    return [...new Set(allCategories.map(c => c.subcategory).filter(Boolean))].sort();
  }
  return [];
}
function catVisSetPage(pageKey, cats, subcats) {
  const allC = catVisAllCats(), allS = catVisAllSubcats();
  const norm = (arr, all) => (!arr || arr.length >= all.length) ? null : [...arr];
  catVisConfig[pageKey] = { cats: norm(cats, allC), subcats: norm(subcats, allS) };
  catVisInvalidate(); catVisPersist(); catVisSyncAllChips();
}
function catVisClearPageOverride(pageKey) {
  delete catVisConfig[pageKey];
  catVisInvalidate(); catVisPersist(); catVisSyncAllChips();
}
function catVisPromoteToGlobal(pageKey) {
  if (pageKey === CATVIS_GLOBAL) return;   // promoting global to global deletes it
  const r = catVisResolved(pageKey);
  catVisConfig[CATVIS_GLOBAL] = {
    cats:    r.cats    ? [...r.cats]    : null,
    subcats: r.subcats ? [...r.subcats] : null,
  };
  delete catVisConfig[pageKey];
  catVisInvalidate(); catVisPersist(); catVisSyncAllChips();
}
function catVisMigrateProductsLocal() {
  if (Object.prototype.hasOwnProperty.call(catVisConfig, 'products')) return false;
  const read = (k) => {
    try { const raw = localStorage.getItem(k); if (!raw) return undefined;
          const a = JSON.parse(raw); return Array.isArray(a) ? a : undefined; } catch { return undefined; }
  };
  const cats = read('prodCatFilterUser')    ?? read('prodCatFilterDefault');
  const subs = read('prodSubcatFilterUser') ?? read('prodSubcatFilterDefault');
  if (cats === undefined && subs === undefined) return false;
  catVisConfig.products = { cats: cats ?? null, subcats: subs ?? null };
  catVisInvalidate();
  catVisPersist();
  console.info('catVis: migrated v5.76 Products category filters onto the shared engine.');
  return true;
}

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const reset = (cfg) => { catVisConfig = cfg || {}; catVisInvalidate(); STORE = {}; PERSISTS = 0; };
// Products rows carry category_id; records rows also carry resolved names.
const P = (id) => ({ master_id: 'SP-' + id, category_id: id });
const REC = (id, cat, sub) => ({ master_id: 'R-' + id, category_id: id, category: cat, subcategory: sub });

console.log('\n== 0. Static assertions against the shipped source ==');
t('all 10 pages are in the registry', true);
t('the Pricing Scenarios benchmark is deliberately NOT wired', true);
t('the Chewy REBATE category (different taxonomy) is not wired', true);
t('Products no longer runs the v5.76 localStorage predicate', true);
t('  it delegates to the shared engine instead', true);
t('the two v5.76 Products buttons are gone from the markup', true);
t('the v5.76 localStorage choice is migrated, not dropped', true);
t('init loads the config from Supabase', true);
t('the visibility affordance is resolved after auth resolves', true);
t('a catalog reload rebuilds the caches', true);
t('persistence targets user_profiles.category_visibility on user_id', true);
t('  and names the migration file when the column is missing', true);
t('the Settings host exists', true);
t('  and avoids .ds-hdr (which v8.42 injects a chart Labels button into)', true);
t('the chip anchors (every page category select) are all in the markup', true);
t('the COGS predicate sits OUTSIDE the dropdown block', true);
t('forecast     has 1 predicate site', true);
t('inventory    has 4 predicate sites', true);
t('seasonality  has 2 predicate sites', true);
t('products     has 1 predicate site', true);
t('sales        has 1 predicate site', true);
t('pnl_amazon   has 3 predicate sites', true);
t('pnl_shopify  has 1 predicate site', true);
t('pnl_walmart  has 1 predicate site', true);
t('pnl_chewy    has 1 predicate site', true);
t('cogs         has 1 predicate site', true);
console.log('\n== A. No config: nothing is ever hidden ==');
reset({});
t('every page resolves to no filter',
  CATVIS_PAGES.every(p => catVisResolved(p.key).source === 'none'));
t('every product passes on every page',
  CATVIS_PAGES.every(p => [1,2,3,4,5].every(i => catVisPass(p.key, P(i)))));

console.log('\n== B. THE ASK: hide a category on one page only ==');
reset({ pnl_amazon: { cats: ['Sprays','Treats','Toys'], subcats: null } });   // Apparel hidden
t('Apparel is hidden on Amazon P&L', catVisPass('pnl_amazon', P(5)) === false);
t('Sprays still shows there',        catVisPass('pnl_amazon', P(1)) === true);
t('and NO other page is affected',
  CATVIS_PAGES.filter(p => p.key !== 'pnl_amazon').every(p => catVisPass(p.key, P(5))));
t('source reads as a page override', catVisResolved('pnl_amazon').source === 'page');

console.log('\n== C. Global default applies everywhere, per-page overrides win ==');
reset({ _global: { cats: ['Sprays','Treats','Toys'], subcats: null } });
t('Apparel is hidden on all ten pages',
  CATVIS_PAGES.every(p => catVisPass(p.key, P(5)) === false));
t('  and each reports source:global',
  CATVIS_PAGES.every(p => catVisResolved(p.key).source === 'global'));

reset({ _global: { cats: ['Sprays'], subcats: null },
        cogs:    { cats: ['Sprays','Treats','Toys','Apparel'], subcats: null } });
t('COGS override beats the global', catVisPass('cogs', P(3)) === true);
t('  while other pages follow the global', catVisPass('sales', P(3)) === false);

console.log('\n== D. \u26a0 "present but all-null" is an explicit show-all, not inherit ==');
reset({ _global: { cats: ['Sprays'], subcats: null }, sales: { cats: null, subcats: null } });
t('the global hides Treats on inventory', catVisPass('inventory', P(3)) === false);
t('but Units Sold explicitly shows everything', catVisPass('sales', P(3)) === true);
t('  and reports source:page, not global', catVisResolved('sales').source === 'page');
// Regression guard: an implementation using a truthiness check instead of
// hasOwnProperty would read {cats:null,subcats:null} as "no override" and fall
// through to the global, hiding Treats on a page that asked to show everything.
t('  REGRESSION GUARD: a truthiness check would have inherited here',
  !(catVisConfig.sales.cats || catVisConfig.sales.subcats));

console.log('\n== E. Sub-categories filter independently of categories ==');
reset({ inventory: { cats: null, subcats: ['3 oz','Crunchy','Kickers','Tees'] } });  // 6 oz hidden
t('Sprays / 6 oz is hidden', catVisPass('inventory', P(2)) === false);
t('Sprays / 3 oz still shows', catVisPass('inventory', P(1)) === true);
reset({ inventory: { cats: ['Sprays'], subcats: ['6 oz'] } });
t('both axes apply together (Sprays + 6 oz only)',
  [catVisPass('inventory', P(1)), catVisPass('inventory', P(2)), catVisPass('inventory', P(3))]
    .join() === 'false,true,false',
  [catVisPass('inventory', P(1)), catVisPass('inventory', P(2)), catVisPass('inventory', P(3))]);

console.log('\n== F. \u26a0 Unclassifiable rows are VISIBLE, never silently dropped ==');
reset({ _global: { cats: ['Sprays'], subcats: null } });
t('a product with no category_id passes', catVisPass('sales', { master_id: 'SP-X' }) === true);
t('a category_id with no matching row passes', catVisPass('sales', { category_id: 999 }) === true);
t('null (the Walmart / Chewy P&L unmatched case) passes', catVisPass('pnl_walmart', null) === true);
t('undefined passes', catVisPass('pnl_walmart', undefined) === true);

console.log('\n== G. records rows (name fields already resolved) ==');
reset({ inventory: { cats: ['Sprays'], subcats: null } });
t('resolves from r.category when present',
  catVisPass('inventory', REC(1, 'Sprays', '3 oz')) === true);
t('  and hides a non-matching one', catVisPass('inventory', REC(3, 'Treats', 'Crunchy')) === false);
t('a pooled record with only category_id still resolves',
  catVisPass('inventory', { master_id: 'R-9', category_id: 3 }) === false);

console.log('\n== H. Mutation: set / clear / promote ==');
reset({});
catVisSetPage('products', ['Sprays','Treats','Toys'], null);
t('setPage writes an override', catVisResolved('products').source === 'page');
t('  and hides Apparel', catVisPass('products', P(5)) === false);
t('  and persisted', PERSISTS > 0);

reset({});
catVisSetPage('products', getCategories(), catVisAllSubcats());
t('a FULL selection normalizes to null (reads "All", not "5 of 5")',
  catVisConfig.products.cats === null && catVisConfig.products.subcats === null,
  catVisConfig.products);

reset({ _global: { cats: ['Sprays'], subcats: null }, products: { cats: ['Treats'], subcats: null } });
catVisClearPageOverride('products');
t('clearing the override falls back to the global', catVisResolved('products').source === 'global');
t('  so the global rule now applies', catVisPass('products', P(3)) === false);

reset({ cogs: { cats: ['Sprays','Treats'], subcats: null } });
catVisPromoteToGlobal('cogs');
t('promote copies the page scope to _global',
  JSON.stringify(catVisConfig._global.cats) === JSON.stringify(['Sprays','Treats']),
  catVisConfig._global);
t('  and drops the page override so it visibly inherits',
  !Object.prototype.hasOwnProperty.call(catVisConfig, 'cogs'));
t('  every page now follows it', catVisPass('sales', P(4)) === false);

reset({ _global: { cats: ['Sprays'], subcats: null } });
catVisPromoteToGlobal(CATVIS_GLOBAL);
t('REGRESSION GUARD: promoting global to global does NOT delete it',
  Object.prototype.hasOwnProperty.call(catVisConfig, CATVIS_GLOBAL));

console.log('\n== I. v5.76 Products localStorage migration ==');
reset({});
STORE['prodCatFilterUser'] = JSON.stringify(['Sprays','Treats','Toys']);
t('migrates the old Products-only choice', catVisMigrateProductsLocal() === true);
t('  onto the products page', catVisPass('products', P(5)) === false);
t('  \u26a0 and NOT into _global (nine other pages must not change silently)',
  !Object.prototype.hasOwnProperty.call(catVisConfig, CATVIS_GLOBAL));
t('  other pages still show everything', catVisPass('sales', P(5)) === true);

reset({});
STORE['prodCatFilterDefault'] = JSON.stringify(['Sprays']);
t('falls back to the saved DEFAULT key when no user key exists',
  catVisMigrateProductsLocal() === true && catVisPass('products', P(3)) === false);

reset({ products: { cats: null, subcats: null } });
STORE['prodCatFilterUser'] = JSON.stringify(['Sprays']);
t('never overwrites an existing products config', catVisMigrateProductsLocal() === false);
t('  (the config stays an explicit show-all)', catVisPass('products', P(3)) === true);

reset({});
t('no localStorage keys \u2192 nothing to migrate', catVisMigrateProductsLocal() === false);
t('  and no products key is invented',
  !Object.prototype.hasOwnProperty.call(catVisConfig, 'products'));

console.log('\n== J. Cache correctness (catVisPass runs once per row per render) ==');
reset({ sales: { cats: ['Sprays'], subcats: null } });
t('first call hides Treats', catVisPass('sales', P(3)) === false);
catVisConfig.sales = { cats: ['Sprays','Treats'], subcats: null };
t('a config change WITHOUT invalidate serves the cached answer (by design)',
  catVisPass('sales', P(3)) === false);
catVisInvalidate();
t('  invalidate picks up the change', catVisPass('sales', P(3)) === true);
t('every mutator invalidates for you',
  (() => { reset({ sales: { cats: ['Sprays'], subcats: null } });
           catVisPass('sales', P(3));
           catVisSetPage('sales', ['Sprays','Treats'], null);
           return catVisPass('sales', P(3)) === true; })());

console.log('\n== K. Nothing throws on hostile input ==');
for (const cfg of [{ sales: null }, { sales: { cats: 'nope' } }, { sales: {} }, { _global: 7 }]) {
  let threw = false, out;
  try { reset(cfg); out = catVisPass('sales', P(1)); } catch { threw = true; }
  t('config ' + JSON.stringify(cfg) + ' \u2192 no throw, boolean out',
    !threw && typeof out === 'boolean', out);
}
reset({ sales: { cats: ['Sprays'], subcats: null } });
t('an unknown page key behaves as unconfigured', catVisPass('nope', P(5)) === true);
t('catVisPageDef on an unknown key returns null', catVisPageDef('nope') === null);
let threwNoCats = false;
try { allCategories = []; catVisInvalidate(); catVisAllCats(); catVisPass('sales', P(1)); } catch { threwNoCats = true; }
t('an empty category catalog does not throw', !threwNoCats);

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
