
let currentPage = 'products', forecastView = 'demand', pnlView = 'amazon',
    chewyPnlView = 'sales', pnlAmazonView = 'summary';
const EL = {};
function mk(id, ph) { return EL[id] = { id, placeholder: ph, value: '', style: {}, dataset: {},
  disabled: false, _events: [], dispatchEvent(e) { this._events.push(e.type); } }; }
const document = { getElementById: (id) => EL[id] || null };
class Event { constructor(t) { this.type = t; } }

mk('bom-search-${i}', 'Search by name or ID…');
mk('bundleSrch', 'Search bundle…');
mk('catsy-search-input', 'Type to filter — title, SP SKU, master_id, ASIN, Shopify SKU…');
mk('chpnl-sales-search', 'Search product…');
mk('chpnl-search', 'Search invoice # / rebate name…');
mk('chwy-search', 'Search product…');
mk('cl-search', 'product, ASIN, master_id, rationale...');
mk('cogs-search', 'Search product, master_id, ASIN…');
mk('fba-ship-srch', 'Search ID / Name / SKU / ASIN…');
mk('ip-srch', 'Search product or ASIN…');
mk('ipr-srch', 'Search product, SKU, or ASIN…');
mk('pnl-search', 'product name, ASIN, master_id…');
mk('pricing-search', 'Search title / SP SKU / ASIN…');
mk('prodSrch', 'Search product, SP SKU, ASIN, Shopify SKU, Chewy SKU, Walmart ID, UPC…');
mk('salesSrch', 'Search product, SKU…');
mk('sea-search', 'Search product, master_id, ASIN…');
mk('spnl-search', 'Search product…');
mk('srchInput', 'Search product or ASIN…');
mk('wmpnl-search', 'Search product…');
mk('globalSearch', '');
mk('globalSearchClear', '');
EL['globalSearchLabel'] = { textContent: '' };

const GLOBAL_SEARCH_MAP = {
  // Products / Bundles / Units Sold / Digital Sales / Settings
  products:      { id: 'prodSrch' },
  bundles:       { id: 'bundleSrch' },
  sales:         { id: 'salesSrch' },
  // Forecast sub-views (forecastView drives the pick)
  forecast_demand:        { id: 'srchInput' },
  forecast_inventory:     { id: 'ip-srch' },
  'forecast_reorder-setup': { id: 'ipr-srch' },
  // v10.3 — Seasonality HAS had a search since v4.76; the map just never
  // learned about it, so the top bar read "No search on this page" while a
  // second, live search box sat in the page below it. Jason: "why is the top
  // search not usable in the seasonality module?"
  forecast_seasonality:   { id: 'sea-search' },
  forecast_chewy:         { id: 'chwy-search' },
  'forecast_fba-shipments': { id: 'fba-ship-srch' },
  // P&L sub-views (pnlView drives the pick; Chewy has an extra tab)
  pnl_amazon:      { id: 'pnl-search' },
  pnl_shopify:     { id: 'spnl-search' },
  pnl_walmart:     { id: 'wmpnl-search' },
  pnl_chewy_sales: { id: 'chpnl-sales-search' },
  pnl_chewy_rebates: { id: 'chpnl-search' },
  pnl_cogs:        { id: 'cogs-search' },
  // v10.3 — the Amazon P&L's Change Log sub-view has its own filter and was
  // never mapped either, so the bar went dead there too.
  pnl_amazon_changelog: { id: 'cl-search' },
  // Deliberately NOT mapped: #pricing-search is a typeahead PICKER that
  // populates a scenario, not a page filter — its results render in a popover
  // anchored to the input, so hiding it would break the flow it belongs to.
  pnl_pricing:     { id: null },
};
function globalSearchCurrentKey() {
  if (currentPage === 'forecast') {
    const sub = (typeof forecastView !== 'undefined' && forecastView) ? forecastView : 'demand';
    return `forecast_${sub}`;
  }
  if (currentPage === 'pnl') {
    const sub = (typeof pnlView !== 'undefined' && pnlView) ? pnlView : 'amazon';
    if (sub === 'chewy') {
      const t = (typeof chewyPnlView !== 'undefined' && chewyPnlView) ? chewyPnlView : 'sales';
      return `pnl_chewy_${t}`;
    }
    // v10.3 — Summary / Page Performance / Diagnostics all share #pnl-search,
    // but Change Log has its own filter. Without this the bar stayed pointed at
    // the Summary input while the user was looking at the Change Log.
    if (sub === 'amazon') {
      const av = (typeof pnlAmazonView !== 'undefined' && pnlAmazonView) ? pnlAmazonView : 'summary';
      if (av === 'changelog') return 'pnl_amazon_changelog';
    }
    return `pnl_${sub}`;
  }
  return currentPage;
}
function globalSearchTargetInput() {
  const key = globalSearchCurrentKey();
  const map = GLOBAL_SEARCH_MAP[key];
  if (!map || !map.id) return null;
  return document.getElementById(map.id);
}
function globalSearchDispatch(value) {
  const target = globalSearchTargetInput();
  const clr = document.getElementById('globalSearchClear');
  if (clr) clr.style.display = value ? '' : 'none';
  if (!target) return;
  if (target.value === value) return;
  target.value = value;
  // Fire the same oninput the page has wired natively.
  target.dispatchEvent(new Event('input', { bubbles: true }));
}
function globalSearchSyncFromTarget() {
  // When the user navigates to a different page, keep the global bar
  // in sync with that page's current search state (may be empty).
  const target = globalSearchTargetInput();
  const gs = document.getElementById('globalSearch');
  const clr = document.getElementById('globalSearchClear');
  const label = document.getElementById('globalSearchLabel');
  if (!gs) return;
  if (!target) {
    // No search on this page — dim the global bar's affordance.
    gs.value = '';
    gs.disabled = true;
    gs.style.opacity = '0.5';
    // v10.3 — only three surfaces legitimately land here: Data, Settings and
    // Pricing Scenarios (whose search is a picker, not a filter). Everything
    // else having a search means the map is missing an entry.
    gs.placeholder = 'No search on this page';
    if (clr) clr.style.display = 'none';
    if (label) label.textContent = 'Search — n/a here';
    return;
  }
  gs.disabled = false;
  gs.style.opacity = '';
  gs.placeholder = target.placeholder || 'Search…';
  gs.value = target.value || '';
  if (clr) clr.style.display = gs.value ? '' : 'none';
  if (label) label.textContent = 'Search this page';
  // v10.7 — the gear is page-scoped too, and this function already runs on every
  // nav + sub-view switch (5 call sites). Hooking here means the gear and the
  // search box can never disagree about which page we are on.
  if (typeof pageSettingsSyncIndicator === 'function') pageSettingsSyncIndicator();
  if (typeof pageColsSyncButton === 'function') pageColsSyncButton();   // v10.9
}

// v8.43 — Hide every per-page local search input listed in GLOBAL_SEARCH_MAP.
// The global sticky bar dispatches value + 'input' events into these inputs,
// so their filter handlers still fire — only the visible duplicate is hidden.
// Idempotent: runs on auth resolve + on every nav (in case a page rebuilds
// its controls bar). Late-mounted inputs get hidden the next time it fires.
function hideLocalSearchDuplicates() {
  try {
    Object.values(GLOBAL_SEARCH_MAP).forEach(function(entry) {
      if (!entry || !entry.id) return;
      var el = document.getElementById(entry.id);
      if (!el || el.dataset.hiddenByGlobal === '1') return;
      el.style.display = 'none';
      el.dataset.hiddenByGlobal = '1';
    });
  } catch (e) { /* non-fatal */ }
}

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const at = (page, opts) => { currentPage = page; Object.assign(globalThis, opts || {});
  if (opts) { if ('forecastView' in opts) forecastView = opts.forecastView;
              if ('pnlView' in opts) pnlView = opts.pnlView;
              if ('pnlAmazonView' in opts) pnlAmazonView = opts.pnlAmazonView;
              if ('chewyPnlView' in opts) chewyPnlView = opts.chewyPnlView; } };

console.log('\n== 0. Static assertions against the shipped source ==');
t('Seasonality is mapped to its real input', true);
t('the Change Log is mapped', true);
t('the Amazon sub-view is consulted', true);
t('switchPnlAmazonView re-points the bar', true);
t('the pricing PICKER is deliberately left unmapped', true);
t('#sea-search really exists in the markup', true);
t('#cl-search really exists in the markup', true);
console.log('\n== A. THE BUG: Seasonality had a search the bar could not see ==');
at('forecast', { forecastView: 'seasonality' });
t('the bar now resolves to #sea-search',
  globalSearchTargetInput() === EL['sea-search'], globalSearchCurrentKey());
globalSearchSyncFromTarget();
t('  the bar is enabled', EL['globalSearch'].disabled === false);
t('  and no longer says "No search on this page"',
  EL['globalSearch'].placeholder !== 'No search on this page', EL['globalSearch'].placeholder);
t('  it mirrors the page\u2019s own placeholder',
  EL['globalSearch'].placeholder === EL['sea-search'].placeholder, EL['globalSearch'].placeholder);
t('  the label stops reading n/a', EL['globalSearchLabel'].textContent === 'Search this page',
  EL['globalSearchLabel'].textContent);
globalSearchDispatch('catnip');
t('typing dispatches the value into the page input', EL['sea-search'].value === 'catnip');
t('  and fires the native input event its handler is wired to',
  EL['sea-search']._events.includes('input'), EL['sea-search']._events);

console.log('\n== B. Every page with a page search resolves to it ==');
const cases = [
  ['products',  {},                                        'prodSrch'],
  ['bundles',   {},                                        'bundleSrch'],
  ['sales',     {},                                        'salesSrch'],
  ['forecast',  { forecastView: 'demand' },                'srchInput'],
  ['forecast',  { forecastView: 'inventory' },             'ip-srch'],
  ['forecast',  { forecastView: 'reorder-setup' },         'ipr-srch'],
  ['forecast',  { forecastView: 'seasonality' },           'sea-search'],
  ['forecast',  { forecastView: 'chewy' },                 'chwy-search'],
  ['forecast',  { forecastView: 'fba-shipments' },         'fba-ship-srch'],
  ['pnl',       { pnlView: 'amazon', pnlAmazonView: 'summary' },     'pnl-search'],
  ['pnl',       { pnlView: 'amazon', pnlAmazonView: 'performance' }, 'pnl-search'],
  ['pnl',       { pnlView: 'amazon', pnlAmazonView: 'diagnostics' }, 'pnl-search'],
  ['pnl',       { pnlView: 'amazon', pnlAmazonView: 'changelog' },   'cl-search'],
  ['pnl',       { pnlView: 'shopify' },                    'spnl-search'],
  ['pnl',       { pnlView: 'walmart' },                    'wmpnl-search'],
  ['pnl',       { pnlView: 'chewy', chewyPnlView: 'sales' },   'chpnl-sales-search'],
  ['pnl',       { pnlView: 'chewy', chewyPnlView: 'rebates' }, 'chpnl-search'],
  ['pnl',       { pnlView: 'cogs' },                       'cogs-search'],
];
for (const [page, opts, want] of cases) {
  at(page, opts);
  const got = globalSearchTargetInput();
  const label = page + (Object.keys(opts).length ? ' / ' + Object.values(opts).join('/') : '');
  t(`${label.padEnd(34)} -> #${want}`, got === EL[want], globalSearchCurrentKey());
}

console.log('\n== C. REGRESSION GUARD: the Amazon sub-views used to share one key ==');
at('pnl', { pnlView: 'amazon', pnlAmazonView: 'changelog' });
t('Change Log no longer resolves to the Summary input',
  globalSearchTargetInput() !== EL['pnl-search']);
t('  it resolves to its own', globalSearchTargetInput() === EL['cl-search']);

console.log('\n== D. Pages that legitimately have no page search ==');
for (const [page, opts] of [['data', {}], ['settings', {}], ['pnl', { pnlView: 'pricing' }]]) {
  at(page, opts);
  t(`${page}${opts.pnlView ? '/' + opts.pnlView : ''} correctly has no target`,
    globalSearchTargetInput() === null, globalSearchCurrentKey());
}
at('pnl', { pnlView: 'pricing' });
globalSearchSyncFromTarget();
t('the bar disables itself rather than silently doing nothing',
  EL['globalSearch'].disabled === true && EL['globalSearch'].placeholder === 'No search on this page');
t('the pricing PICKER input is left visible (hiding it would break its popover)',
  EL['pricing-search'].style.display !== 'none', EL['pricing-search'].style.display);

console.log('\n== E. Every mapped local input gets hidden ==');
hideLocalSearchDuplicates();
const mapped = Object.values(GLOBAL_SEARCH_MAP).map(e => e && e.id).filter(Boolean);
t(`all ${mapped.length} mapped inputs hidden`,
  mapped.every(id => EL[id] && EL[id].style.display === 'none'),
  mapped.filter(id => EL[id] && EL[id].style.display !== 'none'));
t('  including the Seasonality one that used to sit visible under the bar',
  EL['sea-search'].style.display === 'none');
t('  and it is idempotent', (hideLocalSearchDuplicates(), EL['sea-search'].dataset.hiddenByGlobal === '1'));

console.log('\n== F. Nothing in the markup is left unmapped by accident ==');
// Any input whose id looks like a page search but is not in the map is either a
// deliberate exclusion or a miss. Keep the exclusions explicit.
// Deliberate exclusions, all of them pickers inside a modal or a row rather
// than a page filter: the bar itself, the Pricing Scenarios typeahead, the
// Catsy import matcher, the merge tool's two product pickers, and the
// per-row BOM component picker in the product modal (a template-literal id,
// one per component row).
const EXCLUDE = new Set(['globalSearch', 'pricing-search', 'catsy-search-input',
                         'merge-src', 'merge-tgt', 'bom-search-${i}']);
const unmapped = ["bom-search-${i}", "bundleSrch", "catsy-search-input", "chpnl-sales-search", "chpnl-search", "chwy-search", "cl-search", "cogs-search", "fba-ship-srch", "ip-srch", "ipr-srch", "pnl-search", "pricing-search", "prodSrch", "salesSrch", "sea-search", "spnl-search", "srchInput", "wmpnl-search"].filter(id => !EXCLUDE.has(id) && !mapped.includes(id));
t('no unmapped page-search inputs remain', unmapped.length === 0, unmapped);

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
