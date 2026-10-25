# -*- coding: utf-8 -*-
"""v10.77 - three controls that lied about what they were doing.

All three are the same shape: the MATH was right, the affordance was not, so
the operator read the screen and concluded the feature was broken.

  * A  CHEWY CSV SCOPE. Jason, three times: "would you look at the columns
    builder/view vs what exports on the csv?" -> "if the columns are in the
    data, they should be pickable" -> "the csv export still exports
    EVERYTHING, not the selected columns. this is why the dialog box should be
    there. why do i have to keep asking for tihs?"
    v10.77 put a LABEL on the mismatch, on audit-trail grounds that were MY
    framing rather than his ask. v10.79 added the dialog but it chose ROWS
    only. v10.80 made all 39 columns selectable and still exported all 39.
    v10.81 is the actual answer: the export defaults to the columns on screen
    and the dialog carries an all-columns opt-in, sharing the fieldset
    Inventory Planning has had since v4.200. Section A asserted the note
    EXISTED; it now asserts the note is GONE and the scope reaches the writer.
    N8/N9 are the ones that earn their keep - they drive the real dialog and
    prove the chosen scope lands in onPick.

  * C  PERCENTAGE METRIC. Jason: "if i change the metric to contribution %,
    the stacked chart doesn't render." It renders - as a LINE, because
    pnlTrendSeries forces line mode for a percentage (percentages do not sum)
    and the subtitle says so. But the toggle kept painting Stacked GREEN and
    kept rendering the BANDS stepper under it: two live-looking controls doing
    nothing, which is the v10.19 lesson the BANDS comment itself records.
    C5 is the REGRESSION GUARD - it runs the pre-v10.77 toggle and proves it
    really did paint Stacked active on a percentage metric.

  * D  TABLE FIT BELOW THE FOLD. A table measured while it sits below the fold
    has no meaningful "space left": innerHeight - top goes NEGATIVE, Math.max
    pins it at the 280px floor (~5 rows), and nothing re-fits on scroll, so it
    STAYS there. Amazon P&L puts 9 scorecards plus a 123-week chart above its
    table, so 272 products rendered as 5 rows with dead space underneath.
    D6 is the one that matters most: where v10.56 was already correct (the
    element IS in view) the new formula must be BYTE-IDENTICAL, so this fix
    cannot have moved any table that was fine.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name, got=None):
    global passed, failed
    if cond: passed += 1; print('  ok    ' + name)
    else:    failed += 1; print('  FAIL  %s%s' % (name, '' if got is None else '  got: %r' % (got,)))

def fn(name, kw='function'):
    """Slice a function by brace balance so the test cannot drift from ship."""
    i = js.index('%s %s(' % (kw, name))
    j = js.index('{', i); d = 0; k = j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k+1]
        k += 1

def fn_param(name, kw='function'):
    """Slice a function whose FIRST param is a destructuring pattern.

    ⚠ pnlExportScopeDialog takes `({ title, filtered, ... })`, so the first
    `{` after the name is the PATTERN, not the body - a naive slice truncates
    the function and the harness will not parse. Balance the parameter list
    first. Exactly the trap recorded at v10.12 and hit again at v10.79.
    """
    i = js.index('%s %s(' % (kw, name))
    p = js.index('(', i); d = 0; k = p
    while True:
        if js[k] == '(': d += 1
        elif js[k] == ')':
            d -= 1
            if d == 0: break
        k += 1
    j = js.index('{', k); d = 0; k2 = j
    while True:
        if js[k2] == '{': d += 1
        elif js[k2] == '}':
            d -= 1
            if d == 0: return js[i:k2+1]
        k2 += 1


def const_line(name):
    # Whole line, not `...;` - these consts carry a trailing // comment.
    m = re.search(r'^const\s+%s\s*=.*$' % re.escape(name), js, re.M)
    assert m, 'const %s not found as a single line' % name
    return m.group(0)

def arr_body(name):
    """Text between `const NAME = [` and the closing `\\n];`."""
    m = re.search(r'const %s = \[\n(.*?)\n\];' % re.escape(name), js, re.S)
    assert m, 'array %s not found' % name
    return m.group(1)

def hdr_keys(func_src):
    """The hardcoded `const hdr = [...]` column names inside a CSV writer."""
    i = func_src.index('const hdr = [')
    j = func_src.index('];', i)
    return re.findall(r"'([a-z0-9_]+)'", func_src[i:j])


# ===========================================================================
# A. The export dialog picks COLUMNS, not just rows (v10.81)
# ===========================================================================
print('\nA. the export dialog picks COLUMNS, not just rows')

# v10.81 - Jason, for the third time: "the csv export still exports
# EVERYTHING, not the selected columns. this is why the dialog box should be
# there. why do i have to keep asking for tihs?"
#
# v10.77 put a LABEL on the mismatch (my call, on audit-trail grounds, which
# he accepted as my framing rather than asked for). v10.79 added the dialog
# but it chose ROWS only. v10.80 made all 39 columns selectable and still
# exported all 39. So the note that said "CSV = every column" described a
# default nobody wanted, and A1 now asserts it is GONE.
ok('CHEWY_CSV_SCOPE_NOTE' not in js,
   'A1  the "CSV = every column" note is gone - the export matches the screen now')

# Inventory Planning has had this control since v4.200. The fix is to SHARE
# that fieldset, not write a second one - a pattern living in two places with
# different markup IS the bug (hard rule #1).
ok(js.count('function colScopeFieldsetHtml(') == 1,
   'A2  exactly one Columns fieldset renderer, shared by every export dialog',
   js.count('function colScopeFieldsetHtml('))
ok(js.count('function readColScope(') == 1,
   'A3  exactly one reader for the chosen column scope',
   js.count('function readColScope('))

# Both dialogs must RENDER the shared one and READ through the shared helper.
# An inline copy in either is how the P&L dialog shipped without it twice.
_sed = fn('showExportDialog')
_pes = fn_param('pnlExportScopeDialog')
ok('colScopeFieldsetHtml(' in _sed,
   'A4  showExportDialog renders the shared fieldset')
ok('colScopeFieldsetHtml(' in _pes,
   'A5  pnlExportScopeDialog renders the shared fieldset')
ok('readColScope(' in _sed and 'readColScope(' in _pes,
   'A6  both dialogs read the scope through the shared helper')
ok('name="exp-cols"' not in _sed and 'name="exp-cols"' not in _pes,
   'A7  neither dialog hand-rolls the radios (no second copy of the markup)')

# The Cost line was textContent, which cannot carry a tooltip span (v10.77).
ok('rc.innerHTML = `${rows.length} Chewy SKUs`' in js,
   'A8  Cost row-count is still innerHTML')
ok('rc.textContent = `${rows.length} Chewy SKUs`' not in js,
   'A9  no textContent assignment survives on the Cost row-count line')

# v10.77 also fixed two tooltips that templated a page name into the middle
# of a sentence ("Break-Even of these columns are hidden").
ok('of these columns are hidden' not in js,
   'A10 the mis-templated "<page> of these columns are hidden" tooltip is gone')
ok(js.count('These columns are hidden on screen.') == 2,
   'A11 both hidden-column tooltips read as English',
   js.count('These columns are hidden on screen.'))

# v10.78 - THE NO-PROSE RULE, MADE RUNNABLE. A rule nobody can run is a rule
# that drifts, so it is a hard character cap rather than a habit. The CSV-note
# half of this check retired with the note itself; the disabled-Stacked
# tooltip is still live and still capped.
off_tip = re.search(r"const offTip = '(.*?)';", js, re.S).group(1)
ok(len(off_tip) <= 20,
   'A12 the disabled-Stacked tooltip is a state, not an explanation (<=20 chars)',
   (len(off_tip), off_tip))
BANNED = ['would draw', 'Pick a', 'so that', 'because', 'in order to', 'which means']
leak = [b for b in BANNED if b.lower() in off_tip.lower()]
ok(not leak, 'A13 it does not editorialise (descriptions only)', leak)

# THE BEHAVIOUR. Default is the columns ON SCREEN; 'all' is the opt-in.
_wr = fn('_writeChewyBreakevenCSV')
ok('colScope' in re.findall(r'function _writeChewyBreakevenCSV\(([^)]*)\)', _wr)[0],
   'A14 the writer takes a column scope')
ok("colScope === 'all'" in _wr,
   'A15 all-columns is the OPT-IN branch, so the default is the visible set')
ok("chewyVisibleCols('breakeven')" in _wr,
   'A16 the default set comes from the picker, not a second list')

# REGRESSION GUARD - run the pre-v10.81 line and prove it really did ignore
# the picker. Without this, "we fixed the export" is a memory, not a check.
_old = "CHEWY_BE_COLUMNS.filter(c => c.csv).slice().sort((a, b) => a.csv.order - b.csv.order)"
ok(_old not in _wr,
   'A17 regression guard: the unconditional all-columns map is gone')


# ---------------------------------------------------------------------------
# A-node. Drive the REAL dialog so the column scope is a checked claim.
# ---------------------------------------------------------------------------
hA = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

// STATE.pick simulates which radio the operator left selected. null exercises
// the `|| 'visible'` fallback (no radios rendered at all).
const STATE = { pick: null, html: '', removed: 0 };

function mkOv() {
  return {
    id: '', style: {}, dataset: {},
    set innerHTML(v) { STATE.html = v; },
    get innerHTML() { return STATE.html; },
    addEventListener(_, h) { this._h = h; },
    remove() { STATE.removed++; },
    querySelector(sel) {
      if (sel.includes('exp-cols') && STATE.pick) return { value: STATE.pick };
      return null;
    },
  };
}
let LAST = null;
const document = {
  getElementById: () => null,
  body: { appendChild(){} },
  createElement: () => (LAST = mkOv()),
};

__FIELDSET__
__READER__
__DIALOG__

const three = [1,2,3];
const call = (opts) => {
  STATE.html = ''; STATE.removed = 0; LAST = null;
  let got = null;
  pnlExportScopeDialog(Object.assign({
    title: 'x', filtered: three, everything: three, everythingLabel: 'All',
    onPick: (rows, scope) => { got = { n: rows.length, scope }; },
  }, opts));
  return got;
};

// N1 - neither axis has a choice, so it must not ask. This is the only path
// that can legitimately skip the dialog.
t('N1  no column choice + same rows -> exports immediately as visible',
  call({ cols: { visible: 39, all: 39 } }), { n: 3, scope: 'visible' });

// N2 - the rows are identical but the COLUMNS are not. Pre-v10.81 this
// skipped the dialog and exported all 39. It must ask now.
let got = call({ cols: { visible: 8, all: 39 } });
t('N2  column choice + same rows -> asks instead of guessing', [got, STATE.html.length > 0], [null, true]);
t('N3  the Columns fieldset is rendered', STATE.html.includes('exp-cols'), true);
t('N4  visible is pre-checked, so the default honours the screen',
  /value="visible" checked/.test(STATE.html), true);
t('N5  both counts are shown so the choice is legible',
  [STATE.html.includes('8'), STATE.html.includes('39')], [true, true]);

// N6 - identical row sets must not render a 2-option Rows section.
t('N6  same rows -> one row button, no Rows header',
  [(STATE.html.match(/data-pick="/g) || []).length, STATE.html.includes('>Rows<')],
  [2, false]);   // filtered + cancel

// N7 - differing rows DO get the labelled two-option Rows section.
call({ filtered: [1], cols: { visible: 8, all: 39 } });
t('N7  differing rows -> two row buttons + a Rows header',
  [(STATE.html.match(/data-pick="/g) || []).length, STATE.html.includes('>Rows<')],
  [3, true]);   // filtered + everything + cancel

// N8/N9 - the chosen scope must actually reach onPick. This is the assertion
// the whole version exists for.
const click = (pick) => {
  const h = LAST._h;
  h({ target: { closest: () => ({ dataset: { pick } }) } });
};
STATE.pick = 'visible';
let seen = null;
STATE.html = ''; LAST = null;
pnlExportScopeDialog({ title:'x', filtered:[1], everything:three, everythingLabel:'All',
  cols: { visible: 8, all: 39 }, onPick: (r, sc) => { seen = { n: r.length, scope: sc }; } });
click('filtered');
t('N8  picking the visible radio returns scope=visible', seen, { n: 1, scope: 'visible' });

STATE.pick = 'all';
seen = null; STATE.html = ''; LAST = null;
pnlExportScopeDialog({ title:'x', filtered:[1], everything:three, everythingLabel:'All',
  cols: { visible: 8, all: 39 }, onPick: (r, sc) => { seen = { n: r.length, scope: sc }; } });
click('everything');
t('N9  picking all columns + all rows returns both choices',
  seen, { n: 3, scope: 'all' });

// N10 - the scope is read BEFORE ov.remove(), or it would always fall back.
STATE.pick = 'all';
seen = null; STATE.html = ''; LAST = null;
pnlExportScopeDialog({ title:'x', filtered:[1], everything:three, everythingLabel:'All',
  cols: { visible: 8, all: 39 }, onPick: (r, sc) => { seen = { n: r.length, scope: sc }; } });
click('filtered');
t('N10 scope survives the node teardown (read before remove)',
  seen && seen.scope, 'all');

console.log(JSON.stringify(out));
'''
hA = (hA.replace('__FIELDSET__', fn('colScopeFieldsetHtml'))
        .replace('__READER__',   fn('readColScope'))
        .replace('__DIALOG__',   fn_param('pnlExportScopeDialog')))
hAp = os.path.join(SP, 'test_v1077_colscope.js')
io.open(hAp, 'w', encoding='utf-8', newline='').write(hA)
rA = subprocess.run(['node', hAp], capture_output=True, text=True)
if rA.returncode != 0:
    print('  FAIL  colscope harness did not run:\n' + (rA.stderr or '')[:2500]); failed += 1
else:
    try: rowsA = json.loads(rA.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  colscope harness unparseable: %s' % e); failed += 1; rowsA = []
    for row in rowsA:
        ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))

# ===========================================================================
# B. The claim the note makes is TRUE: CSV is a hardcoded superset
# ===========================================================================
print('\nB. the CSV really is every column')

# v10.80 - this section used to assert the CSV was a strict SUPERSET of the
# picker. Jason: "the csv export has columns that DO NOT EXIST on the view ...
# they should be selectable columns." So Break-Even is now 1:1 - the CSV header
# is DERIVED from CHEWY_BE_COLUMNS - and the assertion flips to equality.
_be_body = arr_body('CHEWY_BE_COLUMNS')
be_cols  = len(re.findall(r"^  \{ key: '", _be_body, re.M))
be_csv   = re.findall(r"csv: \{ name: '([^']+)'", _be_body)

ok(be_cols == 39, 'B1  Break-Even picker holds all 39 columns', be_cols)
ok(len(be_csv) == 39, 'B2  and every one of them carries a csv descriptor', len(be_csv))
ok(be_cols == len(be_csv),
   'B3  1:1 - no column can reach the CSV without being selectable on screen',
   (be_cols, len(be_csv)))

# The impressions / clicks Jason named, plus the audit columns that drove the
# v10.77 decision to keep exporting everything. All selectable now.
MUST = ['impressions', 'clicks', 'catalog_cost', 'purchase_uom', 'case_qty',
        'wholesale_per_each', 'standing_allowance_pct', 'net_per_unit',
        'cogs_per_unit', 'autoship_actualized_sales', 'autoship_first_order_sales']
absent = [c for c in MUST if c not in be_csv]
ok(not absent, 'B4  every former CSV-only column is now a registry column', absent)

# The exporter must not grow a second list again.
ok('const hdr = [' not in fn('_writeChewyBreakevenCSV'),
   'B5  the exporter has no hardcoded header of its own')
ok('CHEWY_BE_COLUMNS' in fn('_writeChewyBreakevenCSV'),
   'B6  it maps the registry instead')

# KNOWN OUTSTANDING: Sales and Cost were NOT consolidated. Same shape of gap,
# so record the exact counts rather than let them pass as if they were fine.
# v10.82 - Cost to Chewy is consolidated now: 25 registry columns, 25 csv
# descriptors, and the body is keyed so the header and the cells cannot
# disagree. Its hardcoded `hdr` array is gone, so B7 asserts the 1:1 rather
# than reading a list that no longer exists.
_cost_body = arr_body('CHEWY_COST_COLUMNS')
cost_cols  = len(re.findall(r"\{ k: '", _cost_body))
cost_csv   = re.findall(r"csv: \{ name: '([^']+)'", _cost_body)
ok(cost_cols == 25, 'B7  Cost picker holds all 25 columns', cost_cols)
ok(len(cost_csv) == 25, 'B8  and every one of them carries a csv descriptor', len(cost_csv))
ok('const hdr = [' not in fn('_writeChewyPnlCostCSV'),
   'B9  the Cost exporter has no hardcoded header of its own')
ok('CHEWY_COST_COLUMNS' in fn('_writeChewyPnlCostCSV'),
   'B10 it maps the registry instead')
# The 13 that were reachable only through the file.
for c in ['purchase_uom', 'standing_allowance_pct', 'net_per_unit', 'break_even_price',
          'chewy_msrp', 'chewy_map', 'pct_of_msrp', 'chewy_avg_retail', 'moq', 'data_gap']:
    ok(c in cost_csv, 'B11 former CSV-only Cost column is now pickable: %s' % c)

# v10.82 - Chewy Sales was the last of the three with the gap. All three are
# consolidated now, so this stops recording an outstanding count and asserts
# the 1:1 instead. hdr_keys() is no longer used on any Chewy exporter.
_sales_body = arr_body('CHEWY_SALES_COLUMNS')
sales_cols  = len(re.findall(r"\{ k: '", _sales_body))
sales_csv   = re.findall(r"csv: \{ name: '([^']+)'", _sales_body)
ok(sales_cols == 18, 'B12 Sales picker holds all 18 columns', sales_cols)
ok(len(sales_csv) == 18, 'B13 and every one of them carries a csv descriptor', len(sales_csv))
ok('const hdr = [' not in fn('_writeChewyPnlSalesCSV'),
   'B14 the Sales exporter has no hardcoded header of its own')
ok('CHEWY_SALES_COLUMNS' in fn('_writeChewyPnlSalesCSV'),
   'B15 it maps the registry instead')
for c in ['master_id', 'brand', 'autoship_units', 'cogs_per_unit',
          'vendor_price_per_each', 'vendor_allowances', 'vendor_contribution_pct']:
    ok(c in sales_csv, 'B16 former CSV-only Sales column is now pickable: %s' % c)

# THE GUARANTEE THAT REPLACES THE OUTSTANDING NOTE. All three Chewy tabs are
# now one registry each, and every export defaults to the picker's set. If a
# future tab grows a hardcoded header again, this goes red.
for _w in ['_writeChewyBreakevenCSV', '_writeChewyPnlCostCSV', '_writeChewyPnlSalesCSV']:
    _src = fn(_w)
    ok("colScope === 'all'" in _src,
       'B17 %s defaults to the visible set (all-columns is the opt-in)' % _w)
    ok('chewyVisibleCols(' in _src,
       'B18 %s reads the picker, not a second list' % _w)


# ===========================================================================
# C. Percentage metric - the toggle shows the EFFECTIVE mode
# ===========================================================================
print('\nC. percentage metric: no live-looking dead controls')

harness = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

let _store = {};
const localStorage = {
  getItem: k => (k in _store ? _store[k] : null),
  setItem: (k, v) => { _store[k] = String(v); },
};
const hosts = {};
const document = { getElementById: id => hosts[id] || null };

__CHARTMODE__

// Marker stub so the test can assert the BANDS stepper's presence/absence.
function pnlBandsStepperHtml(rerenderName) { return '<!--BANDS-->'; }

__TOGGLE__

// Faithful copy of the PRE-v10.77 body, for the regression guard.
function oldInjectToggle(hostId, rerenderName) {
  const host = document.getElementById(hostId);
  if (!host) return;
  const mode = pnlChartMode();
  const btn = (m, label, tip) => {
    const on = mode === m;
    return `<button type="button" onclick="pnlSetChartMode('${m}','${rerenderName}')" title="${tip}"
      style="background:${on ? 'var(--sp-green)' : 'transparent'}">${label}</button>`;
  };
  host.innerHTML = btn('line', 'Line', '') + btn('stacked', 'Stacked', '')
    + (mode === 'stacked' ? pnlBandsStepperHtml(rerenderName) : '');
}

// --- helpers -------------------------------------------------------------
function render(isPct, stored, inject) {
  _store = { pnlChartMode: stored };
  hosts.h = { innerHTML: '' };
  (inject || pnlInjectChartModeToggle)('h', 'rerender', isPct);
  return hosts.h.innerHTML;
}
// The buttons render in order: Line then Stacked.
const parts  = html => html.split('<button').slice(1);
const green  = p => p.indexOf('var(--sp-green)') !== -1;
const bands  = html => html.indexOf('<!--BANDS-->') !== -1;

// C1 - a DOLLAR metric is untouched: stacked stays stacked, BANDS renders.
let h = render(false, 'stacked');
t('C1  $ metric + stored stacked -> Stacked active, BANDS rendered',
  [green(parts(h)[0]), green(parts(h)[1]), bands(h)], [false, true, true]);

// C2 - a PERCENTAGE metric shows LINE active, because that is what draws.
h = render(true, 'stacked');
t('C2  % metric + stored stacked -> Line active, Stacked NOT active',
  [green(parts(h)[0]), green(parts(h)[1])], [true, false]);

// C3 - and the Stacked button is visibly, and functionally, unavailable.
const st = parts(h)[1];
t('C3  % metric -> Stacked is dimmed, not-allowed, and has NO onclick',
  [st.indexOf('opacity:.4') !== -1, st.indexOf('not-allowed') !== -1, st.indexOf('onclick') !== -1],
  [true, true, false]);

// C4 - the BANDS stepper is a stacked-only control; it must disappear too.
t('C4  % metric -> BANDS stepper is not rendered', bands(h), false);

// C5 - THE REGRESSION GUARD. The pre-v10.77 toggle painted Stacked green and
// rendered BANDS on a percentage metric, with the chart drawing a line.
const oldHtml = render(true, 'stacked', oldInjectToggle);
t('C5  REGRESSION GUARD: pre-v10.77 painted Stacked active + BANDS on a % metric',
  [green(parts(oldHtml)[1]), bands(oldHtml)], [true, true]);

// C6 - the STORED preference must survive, so switching back to a $ metric
// restores stacked rather than silently demoting the user to line.
render(true, 'stacked');
t('C6  stored preference untouched by a % metric render', _store.pnlChartMode, 'stacked');

// C7 - stored=line on a % metric is just line; nothing weird.
h = render(true, 'line');
t('C7  % metric + stored line -> Line active, Stacked dimmed, no BANDS',
  [green(parts(h)[0]), green(parts(h)[1]), bands(h)], [true, false, false]);

// C8 - isPct omitted entirely (old 2-arg call shape) degrades to the $ path.
_store = { pnlChartMode: 'stacked' };
hosts.h = { innerHTML: '' };
pnlInjectChartModeToggle('h', 'rerender');
t('C8  isPct omitted -> behaves exactly as before (no accidental blocking)',
  [green(parts(hosts.h.innerHTML)[1]), bands(hosts.h.innerHTML)], [true, true]);

console.log(JSON.stringify(out));
'''
harness = (harness
    .replace('__CHARTMODE__', fn('pnlChartMode'))
    .replace('__TOGGLE__',    fn('pnlInjectChartModeToggle')))

hp = os.path.join(SP, 'test_v1077_toggle.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', hp], capture_output=True, text=True)
if r.returncode != 0:
    print('  FAIL  toggle harness did not run:\n' + (r.stderr or '')[:3000]); failed += 1
else:
    try:
        rows = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  toggle harness output unparseable: %s\n%s' % (e, r.stdout[:2000])); failed += 1; rows = []
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


# ===========================================================================
# D. Table fit - below the fold, and the equivalence proof
# ===========================================================================
print('\nD. data-fit tables measured below the fold')

h2 = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

__GUTTER__
__MIN__
__STICKY__

let VH = 900;
const window = { innerHeight: VH };
let ELS = [];
const document = { querySelectorAll: () => ELS };

__FIT__

// The PRE-v10.77 body, for the equivalence proof and the regression guard.
function oldFit() {
  ELS.forEach(el => {
    if (!el.offsetParent) return;
    const top = el.getBoundingClientRect().top;
    const h = Math.max(TBL_FIT_MIN, Math.round(window.innerHeight - top - TBL_FIT_GUTTER));
    const want = h + 'px';
    if (el.style.maxHeight !== want) el.style.maxHeight = want;
  });
}

function mk(top, visible) {
  return { offsetParent: visible === false ? null : {}, style: { maxHeight: '' },
           getBoundingClientRect: () => ({ top }) };
}
function run(vh, top, visible, fit) {
  VH = vh; window.innerHeight = vh;
  const el = mk(top, visible); ELS = [el];
  (fit || fitTableWrapsToViewport)();
  return el.style.maxHeight;
}

// D1 - in view: unchanged. 900 - 300 - 24 = 576.
t('D1  table in view -> sized from its own position (576px)', run(900, 300, true), '576px');

// D2 - BELOW THE FOLD. Jason's Amazon P&L: 9 scorecards + a 123-week chart.
t('D2  table below the fold -> viewport minus sticky chrome (776px)', run(900, 1400, true), '776px');

// D3 - REGRESSION GUARD: the old formula pinned that same table at the floor.
t('D3  REGRESSION GUARD: pre-v10.77 pinned the below-fold table at the 280px floor',
  run(900, 1400, true, oldFit), '280px');

// D4 - partially below the fold still cannot be measured usefully.
t('D4  table partly below the fold also falls back (not the 280px floor)',
  [run(900, 800, true), run(900, 800, true, oldFit)], ['776px', '280px']);

// D5 - the floor still holds on a genuinely short viewport.
t('D5  short viewport still clamps to the 280px floor', run(350, 1000, true), '280px');

// D6 - THE EQUIVALENCE PROOF. Wherever v10.56 was already right (the element
// is in view and clears the floor), the new formula must be IDENTICAL - this
// fix must not have moved a single table that was fine.
const drift = [];
for (const vh of [700, 900, 1100, 1440]) {
  for (let top = 0; top <= vh; top += 25) {
    const a = run(vh, top, true);
    const b = run(vh, top, true, oldFit);
    if (parseInt(b, 10) > TBL_FIT_MIN && a !== b) drift.push([vh, top, a, b]);
  }
}
t('D6  EQUIVALENCE: identical to v10.56 wherever v10.56 cleared the floor', drift, []);

// D7 - hidden tab: rect is 0, so it must be skipped entirely.
t('D7  hidden tab is skipped (rect would be 0)', run(900, 0, false), '');

// D8 - the fallback never undercuts the floor by construction.
const under = [];
for (const vh of [300, 400, 600, 900, 1440]) {
  const v = parseInt(run(vh, vh + 500, true), 10);
  if (v < TBL_FIT_MIN) under.push([vh, v]);
}
t('D8  the below-fold fallback never returns less than the floor', under, []);

console.log(JSON.stringify(out));
'''
h2 = (h2
      .replace('__GUTTER__', const_line('TBL_FIT_GUTTER'))
      .replace('__MIN__',    const_line('TBL_FIT_MIN'))
      .replace('__STICKY__', const_line('TBL_FIT_STICKY'))
      .replace('__FIT__',    fn('fitTableWrapsToViewport')))

h2p = os.path.join(SP, 'test_v1077_fit.js')
io.open(h2p, 'w', encoding='utf-8', newline='').write(h2)
r2 = subprocess.run(['node', h2p], capture_output=True, text=True)
if r2.returncode != 0:
    print('  FAIL  fit harness did not run:\n' + (r2.stderr or '')[:3000]); failed += 1
else:
    try:
        rows2 = json.loads(r2.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  fit harness output unparseable: %s\n%s' % (e, r2.stdout[:2000])); failed += 1; rows2 = []
    for row in rows2:
        ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


# ===========================================================================
# E. Static - every caller passes isPct, from ONE source of truth
# ===========================================================================
print('\nE. call-site wiring')

calls = [c for c in re.findall(r'pnlInjectChartModeToggle\([^)]*\)', js)
         if 'hostId' not in c]
ok(len(calls) == 4, 'E1  four P&L pages inject the toggle', len(calls))

missing = [c for c in calls if c.count(',') < 2]
ok(not missing, 'E2  every call site passes isPct', missing)

# The Amazon page has TWO percentage metrics and already declares isPct per
# metric in metricLabels. The call must read from there, not re-derive it.
ok("pnlInjectChartModeToggle('pnl-chart-mode-host', 'updatePnlChart', m.isPct)" in js,
   'E3  Amazon reads isPct from metricLabels (one source, no second copy)')

# And the injection must happen AFTER the metric resolves, or isPct is stale.
amz = fn('updatePnlChart', 'async function')
ok(amz.index('const m = metricLabels[metricKey]') < amz.index("pnlInjectChartModeToggle('pnl-chart-mode-host'"),
   'E4  Amazon injects AFTER the metric resolves')

for name, host in (('updateShopifyPnlChart', 'spnl-chart-mode-host'),
                   ('updateWalmartPnlChart', 'wmpnl-chart-mode-host')):
    body = fn(name, 'async function')
    ok(body.index("const isPct = metric === 'margin_pct';") < body.index("pnlInjectChartModeToggle('%s'" % host),
       'E5  %s injects AFTER isPct is computed' % name)

# pnlTrendSeries is still the thing that actually forces the mode - the toggle
# only REPORTS it. If these ever disagree the subtitle and the buttons split.
ok("if (isPct && mode === 'stacked') {" in js,
   'E6  pnlTrendSeries still owns the forced fallback (toggle only reports it)')

# Chewy P&L has no percentage metric today; the explicit false keeps the
# signature uniform and makes a future % metric a one-word edit.
ok("'updateChewyPnlChart', false)" in js,
   'E7  Chewy passes false explicitly rather than relying on undefined')


print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
