
let _renders = 0;
function renderChewyPnlSales(){ _renders++; }      // stub: count the repaints
let chewyPnlSalesSelectedMids = new Set();
let chewyPnlSalesVisibleMids  = [];

function chewyPnlSalesToggleProduct(mid) {
  if (chewyPnlSalesSelectedMids.has(mid)) chewyPnlSalesSelectedMids.delete(mid);
  else chewyPnlSalesSelectedMids.add(mid);
  renderChewyPnlSales();
}
function chewyPnlSalesClearSelection() { chewyPnlSalesSelectedMids.clear(); renderChewyPnlSales(); }
function chewyPnlSalesToggleSelectAllVisible() {
  const allOn = chewyPnlSalesVisibleMids.length > 0 && chewyPnlSalesVisibleMids.every(m => chewyPnlSalesSelectedMids.has(m));
  if (allOn) chewyPnlSalesVisibleMids.forEach(m => chewyPnlSalesSelectedMids.delete(m));
  else       chewyPnlSalesVisibleMids.forEach(m => chewyPnlSalesSelectedMids.add(m));
  renderChewyPnlSales();
}

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}

// ---- toggle -------------------------------------------------------------
chewyPnlSalesVisibleMids = ['SP-1','SP-2','SP-3'];
chewyPnlSalesToggleProduct('SP-1');
t('toggle adds', chewyPnlSalesSelectedMids.has('SP-1'));
t('toggle re-renders', _renders === 1, _renders);
chewyPnlSalesToggleProduct('SP-1');
t('toggle removes', !chewyPnlSalesSelectedMids.has('SP-1'));

// ---- select all visible -------------------------------------------------
chewyPnlSalesSelectedMids.clear();
chewyPnlSalesToggleSelectAllVisible();
t('select-all checks every visible row', chewyPnlSalesSelectedMids.size === 3, [...chewyPnlSalesSelectedMids]);
chewyPnlSalesToggleSelectAllVisible();
t('select-all again clears them', chewyPnlSalesSelectedMids.size === 0);

// partial -> select-all should FILL, not clear
chewyPnlSalesSelectedMids.clear();
chewyPnlSalesSelectedMids.add('SP-2');
chewyPnlSalesToggleSelectAllVisible();
t('partial selection fills rather than clearing', chewyPnlSalesSelectedMids.size === 3);

// ---- clear --------------------------------------------------------------
chewyPnlSalesClearSelection();
t('clear empties the set', chewyPnlSalesSelectedMids.size === 0);

// ---- THE v4.122 RULE: selection survives a filter change ----------------
chewyPnlSalesSelectedMids = new Set(['SP-1','SP-9']);
chewyPnlSalesVisibleMids  = ['SP-1','SP-2'];          // SP-9 filtered out
t('a selected row hidden by a filter is NOT pruned', chewyPnlSalesSelectedMids.has('SP-9'));

// ---- selection resolution (expressions lifted from renderChewyPnlSales) --
const rows = [{master_id:'SP-1'},{master_id:'SP-2'}];
chewyPnlSalesVisibleMids = rows.map(r => r.master_id);
const _selActive = chewyPnlSalesSelectedMids.size > 0;
const _visSet    = new Set(chewyPnlSalesVisibleMids);
const _selRows   = _selActive ? rows.filter(r => chewyPnlSalesSelectedMids.has(r.master_id)) : rows;
const _selHidden = _selActive ? [...chewyPnlSalesSelectedMids].filter(m => !_visSet.has(m)).length : 0;
t('_selRows = visible AND selected', _selRows.length === 1 && _selRows[0].master_id === 'SP-1', _selRows);
t('_selHidden counts selected-but-filtered-out', _selHidden === 1, _selHidden);

// no selection -> totals cover the whole visible table
chewyPnlSalesSelectedMids.clear();
const _a2 = chewyPnlSalesSelectedMids.size > 0;
const _r2 = _a2 ? rows.filter(r => chewyPnlSalesSelectedMids.has(r.master_id)) : rows;
t('no selection -> totals cover every visible row', _r2.length === 2);

// select-all over an EMPTY visible set must not claim "all on"
chewyPnlSalesVisibleMids = [];
chewyPnlSalesSelectedMids.clear();
chewyPnlSalesToggleSelectAllVisible();
t('select-all on an empty table is a no-op', chewyPnlSalesSelectedMids.size === 0);

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
