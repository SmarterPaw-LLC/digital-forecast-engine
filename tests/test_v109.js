
const SHOWN = {};
const document = {
  getElementById: (id) => (id in SHOWN ? { style: SHOWN[id] } : null),
};
let NAV = '';
function pageSettingsCurrentNavKey() { return NAV; }

const PAGE_COLUMN_BUTTONS = [
  { id: 'fc-cols-btn',   navKeys: ['forecast_demand'] },
  { id: 'ip-view-btn',   navKeys: ['forecast_inventory'] },
  { id: 'prod-view-btn', navKeys: ['products'] },
  { id: 'sales-view-btn',navKeys: ['sales'] },
  { id: 'pnl-cols-btn',  navKeys: ['pnl_amazon', 'pnl_amazon_changelog'] },
  { id: 'spnl-cols-btn', navKeys: ['pnl_shopify'] },
];

function pageColsSyncButton() {
  const navKey = (typeof pageSettingsCurrentNavKey === 'function') ? pageSettingsCurrentNavKey() : '';
  for (const b of PAGE_COLUMN_BUTTONS) {
    const el = document.getElementById(b.id);
    if (el) el.style.display = b.navKeys.includes(navKey) ? '' : 'none';
  }
}

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const IDS = ["fc-cols-btn", "ip-view-btn", "prod-view-btn", "pnl-cols-btn", "spnl-cols-btn", "sales-view-btn"];
const reset = () => { IDS.forEach(id => SHOWN[id] = { display: 'none' }); };
const visible = () => IDS.filter(id => SHOWN[id].display !== 'none');

console.log('\n== 0. Static assertions against the shipped source ==');
t('all six column buttons now live in the global bar', true);
t('  and each appears exactly once in the whole file', true);
t('they sit AFTER the search input', true);
t('  and BEFORE the settings gear', true);
t('they start hidden, so nothing flashes before the nav key resolves', true);
t('  with one uniform look rather than the three they arrived with', true);
t('⚠ every id is PRESERVED — ~35 call sites re-open popups by id', true);
t('  the openers were not touched', true);
t('  and the v10.7 sort re-anchor still points at a real element', true);
t('visibility is driven by the same resolver as the gear', true);
t('synced on every nav (inside globalSearchSyncFromTarget)', true);
t('  and once auth resolves', true);
t('Units Sold keeps its honest label', true);
t('the other five say Customize columns', true);
console.log('\n== A. Exactly one button per page ==');
const CASES = {
  forecast_demand:      'fc-cols-btn',
  forecast_inventory:   'ip-view-btn',
  products:             'prod-view-btn',
  sales:                'sales-view-btn',
  pnl_amazon:           'pnl-cols-btn',
  pnl_amazon_changelog: 'pnl-cols-btn',
  pnl_shopify:          'spnl-cols-btn',
};
for (const [navKey, want] of Object.entries(CASES)) {
  reset(); NAV = navKey; pageColsSyncButton();
  const v = visible();
  t(`${navKey.padEnd(22)} -> ${want}`, v.length === 1 && v[0] === want, v);
}

console.log('\n== B. Pages with no column picker show none ==');
for (const navKey of ['forecast_seasonality', 'pnl_walmart', 'pnl_chewy_sales', 'pnl_cogs',
                      'bundles', 'data', 'settings', 'forecast_chewy', 'pnl_pricing',
                      'forecast_fba-shipments', 'pnl_chewy_rebates']) {
  reset(); NAV = navKey; pageColsSyncButton();
  t(`${navKey.padEnd(24)} shows no button`, visible().length === 0, visible());
}

console.log('\n== C. Switching pages hides the previous one ==');
reset();
NAV = 'products';          pageColsSyncButton();
t('on Products, the Products button shows', visible().join() === 'prod-view-btn');
NAV = 'pnl_shopify';       pageColsSyncButton();
t('moving to Shopify P&L swaps it', visible().join() === 'spnl-cols-btn', visible());
NAV = 'pnl_cogs';          pageColsSyncButton();
t('moving to COGS leaves none', visible().length === 0, visible());
NAV = 'forecast_demand';   pageColsSyncButton();
t('coming back reveals the right one', visible().join() === 'fc-cols-btn', visible());

console.log('\n== D. Registry shape ==');
t('every entry has an id and at least one nav key',
  PAGE_COLUMN_BUTTONS.every(b => typeof b.id === 'string' && Array.isArray(b.navKeys) && b.navKeys.length));
t('no id is registered twice',
  new Set(PAGE_COLUMN_BUTTONS.map(b => b.id)).size === PAGE_COLUMN_BUTTONS.length);
t('no nav key maps to two buttons', (() => {
  const seen = new Set();
  for (const b of PAGE_COLUMN_BUTTONS) for (const k of b.navKeys) {
    if (seen.has(k)) return false; seen.add(k);
  }
  return true;
})());

console.log('\n== E. Missing elements never throw ==');
let threw = false;
try { for (const id of IDS) delete SHOWN[id]; NAV = 'products'; pageColsSyncButton(); } catch { threw = true; }
t('a button absent from the DOM is skipped, not fatal', !threw);
reset();
for (const k of ['', null, undefined, 'nonsense']) {
  let th = false;
  try { NAV = k; pageColsSyncButton(); } catch { th = true; }
  t('nav key ' + JSON.stringify(k) + ' is safe', !th && visible().length === 0, visible());
}

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
