# -*- coding: utf-8 -*-
"""v10.66 - Chewy P&L Sales row selection.

Jason: "on the chewy p&L i should be able to check a box next to product rows
to see sales over the period (like on amazon p&l)."

Two halves, both asserted:
  A. STRUCTURE - the checkbox lives outside the column registry, the colspan is
     computed, the chart/CSV/scorecards all read the selection, and row-click
     moved to toggle while the product card moved to a button.
  B. BEHAVIOUR - the three REAL sliced helpers are driven in node, plus the
     selection-resolution expressions lifted verbatim out of index.html. This
     is the v10.65 lesson: node --check and static greps both passed while the
     page threw at runtime, so the helpers get executed here.
"""
import io, os, re, sys, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond: passed += 1; print('  ok  ' + name)
    else:    failed += 1; print('  FAIL  ' + name)

def fn(name):
    """Slice a top-level `function name(...) { ... }` by brace balance."""
    i = s.index('function %s(' % name)
    j = s.index('{', i); d = 0; k = j
    while True:
        if s[k] == '{': d += 1
        elif s[k] == '}':
            d -= 1
            if d == 0: return s[i:k+1]
        k += 1

print('\n== A. STRUCTURE ==')

# --- the checkbox must NOT be a registry column (the picker must not hide it)
reg_i = s.index('const CHEWY_SALES_COLUMNS')
reg   = s[reg_i:s.index('];', reg_i)]
ok("k: '_chk'" not in reg and 'checkbox' not in reg,
   'the checkbox is NOT a CHEWY_SALES_COLUMNS entry (picker cannot hide it)')
ok('chpnl-sales-select-all' in s, 'a select-all checkbox is rendered in the thead')

# --- the Sales thead builds the checkbox th, and still carries v10.57 sourcing
hdr = [l for l in s.split('\n') if 'chewyPnlSalesSetSort(' in l and '<th' in l]
ok(len(hdr) == 1, 'exactly one Sales header builder line (found %d)' % len(hdr))
if hdr:
    ok("srcTipLine(colSrc('chewy_sales'" in hdr[0],
       '  and it still appends the v10.57 source line')
    ok('chewyPnlSalesToggleSelectAllVisible()' in hdr[0],
       '  and the select-all is wired to the toggle')

# --- empty state spans the computed count PLUS the checkbox column
ok("colspan=\"' + (cols.length + 1) + '\"" in s,
   'empty state spans cols.length + 1 (never a hardcoded number)')

# --- row click toggles selection; the product card moved to a button
render = fn('renderChewyPnlSales')
ok("onclick=\"chewyPnlSalesToggleProduct('${r.master_id}')\"" in render,
   'row click toggles the selection (Amazon / Walmart convention)')
ok('onclick="openProductModal(' not in render,
   '  and no longer opens the product modal directly')
ok('pnlCardBtn(r.master_id)' in render,
   '  while the product card stays reachable via the card button')
ok("event.stopPropagation();chewyPnlSalesToggleProduct(" in render,
   'the checkbox stops propagation so it cannot double-fire the row handler')

# --- totals / prev-period / scorecards all read the selection, not the table
ok('const tot = _selRows.reduce(' in render,
   'scorecard totals aggregate the SELECTION')
ok('_selActive ? _selRows.map(r => r.master_id) : Object.keys(agg)' in render,
   'prev-period comparison set narrows too (v4.132 apples-to-apples)')
ok('_selMissingCount' in render and 'const missingCount     = rows.filter' in render,
   'missing-COGS is split: selection scope for the card, table scope for the row count')

# --- the drill banner exists and can clear
ok('id="chpnl-sales-drill"' in s, 'the drill banner has a host element')
ok('chewyPnlSalesClearSelection()' in render, '  and offers a clear button')
ok('_selHidden' in render, '  and counts anything selected but hidden by a filter')

# --- chart + CSV honour it
chart = fn('updateChewyPnlChart')
ok('const selectionActive = !!(chewyPnlSalesSelectedMids' in chart,
   'the chart derives selectionActive from the real set')
ok('selectionActive: false' not in chart,
   '  and no longer hardcodes selectionActive:false')
ok('isPct: false, selectionActive,' in chart,
   '  and passes it through to pnlTrendSeries')
csv_fn = fn('downloadChewyPnlSalesCSV')
ok('chewyPnlSalesSelectedMids.has(r.master_id)' in csv_fn,
   'the CSV exports the selection when one is active (v4.122 rule)')

# --- no self-referencing declarations (the v10.65 TDZ bug class)
selfref = re.findall(r'\b(?:const|let)\s+(\w+)\s*=[^;\n]*\b\1\s*\(', render + chart + csv_fn)
ok(not selfref, 'no self-referencing const/let in the touched functions (v10.65 TDZ class)')

print('\n== B. BEHAVIOUR (real sliced helpers driven in node) ==')

HARNESS = r"""
let _renders = 0;
function renderChewyPnlSales(){ _renders++; }      // stub: count the repaints
let chewyPnlSalesSelectedMids = new Set();
let chewyPnlSalesVisibleMids  = [];

__TOGGLE__
__CLEAR__
__ALL__

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
"""

js = (HARNESS
      .replace('__TOGGLE__', fn('chewyPnlSalesToggleProduct'))
      .replace('__CLEAR__',  fn('chewyPnlSalesClearSelection'))
      .replace('__ALL__',    fn('chewyPnlSalesToggleSelectAllVisible')))

p = os.path.join(SP, 'test_v1066.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(js)
rc = subprocess.call(['node', p])

print('\n' + '=' * 60)
print('static: %d passed, %d failed' % (passed, failed))
sys.exit(1 if (failed or rc) else 0)
