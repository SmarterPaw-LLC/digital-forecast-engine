# -*- coding: utf-8 -*-
"""v10.77 - three controls that lied about what they were doing.

All three are the same shape: the MATH was right, the affordance was not, so
the operator read the screen and concluded the feature was broken.

  * A/B  CHEWY CSV SCOPE. Jason, with 8 columns on screen and 39 in the file:
    "would you look at the columns builder/view vs what exports on the csv?"
    The export deliberately ignores the picker (it carries the cost stack and
    the autoship split, which are the AUDIT TRAIL for BE ROAS - a picker-scoped
    export would strip exactly the inputs that let someone re-derive the
    number). Amazon Break-Even says so on its button; these three tabs said
    nothing. The assertion that earns its keep is B3: the CSV header really IS
    a hardcoded superset of the picker. Wire the CSV to the picker later and
    the note becomes a lie - this test goes red instead.

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
# A. Static - the Chewy CSV scope note is wired on ALL THREE tabs
# ===========================================================================
print('\nA. Chewy CSV scope note - wiring')

ok(js.count('function chewyCsvScopeNote(') == 1,
   'A1  exactly one definition (one note, one helper - hard rule #1)',
   js.count('function chewyCsvScopeNote('))

for page in ('sales', 'cost', 'breakeven'):
    ok(("chewyCsvScopeNote('%s')" % page) in js,
       "A2  the %s row-count line carries the note" % page)

# The Cost line was textContent, which cannot carry a tooltip span.
ok('rc.innerHTML = `${rows.length} Chewy SKUs`' in js,
   'A3  Cost row-count switched to innerHTML so the note can be a tooltip')
ok('rc.textContent = `${rows.length} Chewy SKUs`' not in js,
   'A4  no textContent assignment survives on the Cost row-count line')

# The two tooltips read "Sales of these columns are hidden" / "Break-Even of
# these columns are hidden" - a page name templated into the middle of a
# sentence. Not a behaviour bug, but it is the text sitting next to the fix.
ok('of these columns are hidden' not in js,
   'A5  the mis-templated "<page> of these columns are hidden" tooltip is gone')
ok(js.count('These columns are hidden on screen.') == 2,
   'A6  both hidden-column tooltips read as English',
   js.count('These columns are hidden on screen.'))

# The note must COUNT from the registry, not from a hardcoded number, or it
# drifts the moment a column is added to the picker.
note = fn('chewyCsvScopeNote')
ok('cfg.cols().length' in note,
   'A7  the printed column count is derived from the registry, never hardcoded')


# ===========================================================================
# B. The claim the note makes is TRUE: CSV is a hardcoded superset
# ===========================================================================
print('\nB. the CSV really is every column')

be_csv    = hdr_keys(fn('downloadChewyBreakevenCSV'))
sales_csv = hdr_keys(fn('downloadChewyPnlSalesCSV'))
cost_csv  = hdr_keys(fn('downloadChewyPnlCostCSV'))

be_cols    = len(re.findall(r"\{ key: '", arr_body('CHEWY_BE_COLUMNS')))
sales_cols = len(re.findall(r"\{ k: '",   arr_body('CHEWY_SALES_COLUMNS')))
cost_cols  = len(re.findall(r"\{ k: '",   arr_body('CHEWY_COST_COLUMNS')))

ok(be_cols == 18, 'B1  Break-Even picker holds 18 columns', be_cols)
ok(len(be_csv) == 39, 'B2  Break-Even CSV holds 39 columns', len(be_csv))

# THE assertion. If anyone ever wires a Chewy CSV to chewyVisibleCols(), the
# note on screen starts lying and this goes red.
for tag, csv_n, pick_n in (('Break-Even', len(be_csv), be_cols),
                           ('Sales',      len(sales_csv), sales_cols),
                           ('Cost',       len(cost_csv),  cost_cols)):
    ok(csv_n > pick_n,
       'B3  %s CSV is a strict SUPERSET of the picker (%d > %d)' % (tag, csv_n, pick_n),
       None if csv_n > pick_n else (csv_n, pick_n))

# The audit columns the note names by hand must actually be in the BE file.
AUDIT = ['catalog_cost', 'purchase_uom', 'case_qty', 'wholesale_per_each',
         'standing_allowance_pct', 'net_per_unit', 'cogs_per_unit',
         'autoship_recurring_sales', 'autoship_first_order_sales']
absent = [c for c in AUDIT if c not in be_csv]
ok(not absent, 'B4  every audit column the tooltip promises is in the BE CSV', absent)

# None of the three writers may read the picker - that IS the behaviour.
for name in ('downloadChewyBreakevenCSV', 'downloadChewyPnlSalesCSV', 'downloadChewyPnlCostCSV'):
    ok('chewyVisibleCols' not in fn(name),
       'B5  %s builds its own header, independent of the picker' % name)


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
