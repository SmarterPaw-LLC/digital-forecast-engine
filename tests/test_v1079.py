# -*- coding: utf-8 -*-
"""v10.79 - Chewy Break-Even: custom date range, and an export that says what it is.

Jason: "on chewy breakeven i can't set a custom time. the csv export is not
giving me the option to export like on other pages - it doesn't ask to export
using the filters."

Two separate gaps, both divergences rather than new features:

  * CUSTOM RANGE. Chewy SALES has had one since v10.13. Break-Even and Cost
    never got it, so the same control family behaved three different ways one
    click apart. Same markup, same handler shape, same resolver branch.

  * EXPORT SCOPE. Forecast / Inventory / Products / Bundles / Units Sold all
    open showExportDialog and ask. Every P&L page writes the visible rows
    straight to disk. The Chewy Break-Even file genuinely DID honour the
    filters - there was just no way to know, and no way to ask for anything
    else.

The assertions that earn their keep:

  * D1 THE PARTITION PROPERTY. windowRows must be a SUPERSET of rows, and the
    push must happen BEFORE the filter branches. Push it one line later and the
    "All SKUs in this window" option silently becomes a second copy of the
    filtered set - an export that lies while looking completely normal.

  * D2 catVisPass STAYS A HARD SKIP. It is a saved preference ("never show me
    this category"), not a transient filter, so "everything" must not resurrect
    a category the operator switched off. One flipped line would do it.

  * C1 THE DIALOG SKIPS ITSELF when nothing is narrowing the view. Without that
    every export on a clean page becomes a pointless two-click chore, which is
    how a helpful dialog turns into the thing people ask you to remove.
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
    """Slice a function by brace balance.

    ⚠ Skips the PARAMETER LIST first. pnlExportScopeDialog takes a
    destructured arg, so the first `{` after the name is the destructuring
    pattern, not the body - balancing from there truncates the function and the
    harness will not parse. Exactly the trap recorded at v10.12.
    """
    i = js.index('%s %s(' % (kw, name))
    # Balance the parameter list, so `{` inside it cannot be mistaken for the body.
    k = js.index('(', i); d = 0
    while True:
        if js[k] == '(': d += 1
        elif js[k] == ')':
            d -= 1
            if d == 0: break
        k += 1
    j = js.index('{', k); d = 0; k = j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k+1]
        k += 1


# ===========================================================================
# A. Custom range - the same control on all three Chewy tabs
# ===========================================================================
print('\nA. custom range parity across the Chewy tabs')

for tab, pre in (('Sales', 'chpnl-sales'), ('Cost', 'chpnl-cost'), ('Break-Even', 'chpnl-be')):
    ok('id="%s-custom-wrap"' % pre in s, 'A1  %s has the custom-range wrap' % tab)
    ok('id="%s-from"' % pre in s and 'id="%s-to"' % pre in s,
       'A2  %s has both date inputs' % tab)

# One shape, not three. Each period select routes through its own handler so
# the wrap can be toggled; none may still call the renderer directly.
for tab, sel, handler in (('Sales', 'chpnl-sales-period', 'onChewyPnlSalesPeriodChange'),
                          ('Cost',  'chpnl-cost-period',  'onChewyPnlCostPeriodChange'),
                          ('Break-Even', 'chpnl-be-period', 'onChewyBreakevenPeriodChange')):
    m = re.search(r'<select id="%s" onchange="([^"]+)"' % sel, s)
    ok(m and m.group(1).startswith(handler),
       'A3  %s period select routes through %s()' % (tab, handler),
       m.group(1) if m else None)
    ok(('function %s(' % handler) in js, 'A4  %s is defined' % handler)

# The handler must NOT re-render while the user is mid-way through picking two
# dates - the from/to inputs fire the render themselves.
for handler in ('onChewyPnlSalesPeriodChange', 'onChewyPnlCostPeriodChange', 'onChewyBreakevenPeriodChange'):
    ok("if (v !== 'custom')" in fn(handler),
       'A5  %s does not render on the custom pick itself' % handler)


# ===========================================================================
# B. The resolvers actually honour it
# ===========================================================================
print('\nB. date-range resolution')

harness = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

let VALS = {};
const document = { getElementById: id => (id in VALS ? { value: VALS[id] } : null) };
const chewyAdSpendData = [{ date: '2025-01-15' }, { date: '2026-03-01' }];
const chewyPnlSalesData = [{ week_start: '2025-02-03' }];
function pnlAllTimeFrom(rows, field) {
  return rows.map(r => r[field]).sort()[0];
}
let _pnlSuppressDeltas = false;

__BE__
__COST__

// B1 - custom range is read straight off the two inputs.
VALS = { 'chpnl-be-period': 'custom', 'chpnl-be-from': '2026-02-01', 'chpnl-be-to': '2026-02-28' };
t('B1  Break-Even custom range uses the from/to inputs',
  getChewyBreakevenDateRange(), { from: '2026-02-01', to: '2026-02-28' });

VALS = { 'chpnl-cost-period': 'custom', 'chpnl-cost-from': '2026-04-01', 'chpnl-cost-to': '2026-04-30' };
t('B2  Cost custom range uses the from/to inputs',
  getChewyPnlCostDateRange(), { from: '2026-04-01', to: '2026-04-30' });

// B3 - a blank "to" falls forward to today rather than emptying the window.
const today = new Date().toISOString().split('T')[0];
VALS = { 'chpnl-be-period': 'custom', 'chpnl-be-from': '2026-02-01', 'chpnl-be-to': '' };
t('B3  a blank end date falls forward to today', getChewyBreakevenDateRange().to, today);

// B4 - every other option is untouched by the new branch.
VALS = { 'chpnl-be-period': 'all' };
t('B4  all-time still reads the earliest ad day', getChewyBreakevenDateRange().from, '2025-01-15');
VALS = { 'chpnl-be-period': 'ytd' };
t('B5  ytd still starts on Jan 1', getChewyBreakevenDateRange().from,
  new Date().getFullYear() + '-01-01');
VALS = { 'chpnl-be-period': '90' };
const d90 = new Date(); d90.setDate(d90.getDate() - 90);
t('B6  a trailing window still counts back from today',
  getChewyBreakevenDateRange().from, d90.toISOString().split('T')[0]);

console.log(JSON.stringify(out));
'''
harness = (harness
    .replace('__BE__',   fn('getChewyBreakevenDateRange'))
    .replace('__COST__', fn('getChewyPnlCostDateRange')))

hp = os.path.join(SP, 'test_v1079_dates.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', hp], capture_output=True, text=True)
if r.returncode != 0:
    print('  FAIL  date harness did not run:\n' + (r.stderr or '')[:2500]); failed += 1
else:
    try: rows = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  date harness unparseable: %s' % e); failed += 1; rows = []
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


def lift_const(name):
    """Lift a top-level `const NAME = ...;` by brace/bracket balance.

    ⚠ A naive `^const NAME = .*?;$` stops at the first line ending in `;`,
    which inside an object literal is one of its own entries - the v10.28
    depth-aware-slice lesson. Scan forward and stop at the first `;` at
    depth 0.
    """
    i = js.index('const %s =' % name)
    d = 0; q = None; k = i
    QUOTES = chr(39) + chr(34) + chr(96)
    while k < len(js):
        c = js[k]
        if q:
            # inside a string/template: only its own unescaped quote ends it
            if c == chr(92): k += 2; continue
            if c == q: q = None
        elif c in QUOTES: q = c
        elif c in '([{': d += 1
        elif c in ')]}': d -= 1
        elif c == ';' and d == 0: return js[i:k + 1]
        k += 1
    raise AssertionError('unterminated const %s' % name)


def export_dlg_shell():
    """Everything pnlExportScopeDialog now closes over, in dependency order.

    ⚠ exportDlgActionHtml and exportDlgShellHtml take DESTRUCTURED params, so
    they need the param-aware slicer or the body is truncated at the pattern's
    closing brace (the v10.12 trap). Use fn_param where this file has one.
    """
    _fnp = fn_param if 'fn_param' in globals() else fn
    return chr(10).join([
        lift_const('EXPORT_DLG_OVERLAY_CSS'),
        lift_const('EXPORT_DLG_TONES'),
        _fnp('exportDlgActionHtml'),
        fn('exportDlgSectionHtml'),
        _fnp('exportDlgShellHtml'),
    ])


# ===========================================================================
# C. The export-scope chooser
# ===========================================================================
print('\nC. export scope chooser')

h2 = r'''
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

// The skip path never touches the DOM, which is exactly why it is the one
// worth driving in node.
const document = { getElementById: () => null, body: { appendChild(){} },
                   createElement: () => ({ style:{}, set innerHTML(v){}, addEventListener(){} }) };

__SHELL__
__FIELDSET__
__DIALOG__

// C1 - nothing is narrowing the view, so there is no question to ask.
let picked = null, opened = 0;
const origCreate = document.createElement;
document.createElement = (...a) => { opened++; return origCreate(...a); };
const three = [1,2,3];
pnlExportScopeDialog({ title:'x', filtered: three, everything: three,
                       everythingLabel:'All', onPick: r => { picked = r; } });
t('C1  equal counts -> exports immediately, no dialog', [picked, opened], [three, 0]);

// C2 - counts differ, so it must ask rather than guess.
picked = null; opened = 0;
pnlExportScopeDialog({ title:'x', filtered: [1], everything: three,
                       everythingLabel:'All', onPick: r => { picked = r; } });
t('C2  differing counts -> asks, exports nothing yet', [picked, opened > 0], [null, true]);

console.log(JSON.stringify(out));
'''
h2 = (h2.replace('__SHELL__', export_dlg_shell())
        .replace('__FIELDSET__', fn('colScopeFieldsetHtml') + chr(10) + fn('readColScope'))
        .replace('__DIALOG__', fn('pnlExportScopeDialog')))
h2p = os.path.join(SP, 'test_v1079_scope.js')
io.open(h2p, 'w', encoding='utf-8', newline='').write(h2)
r2 = subprocess.run(['node', h2p], capture_output=True, text=True)
if r2.returncode != 0:
    print('  FAIL  scope harness did not run:\n' + (r2.stderr or '')[:2500]); failed += 1
else:
    try: rows2 = json.loads(r2.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  scope harness unparseable: %s' % e); failed += 1; rows2 = []
    for row in rows2:
        ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))

# Built as a SHARED helper, not a Chewy-only dialog - the other four P&L
# exports are one call each whenever they want it.
ok(js.count('function pnlExportScopeDialog(') == 1,
   'C3  one scope dialog, named for the family not the tab')
ok('showExportDialog' not in fn('downloadChewyBreakevenCSV'),
   'C4  it does NOT reuse showExportDialog (which re-implements filter chains)')
ok('_writeChewyBreakevenCSV' in fn('downloadChewyBreakevenCSV'),
   'C5  the entry point hands the chosen rows to the writer')

# v10.78 rule, made runnable here too. The first cut of this dialog carried a
# three-line note under the buttons - prose in a UI, flagged two hours earlier.
# The disambiguation belongs ON the option it describes.
dlg = fn('pnlExportScopeDialog')
ok('note' not in re.findall(r'function pnlExportScopeDialog\(\{([^}]*)\}', dlg)[0],
   'C6  no free-text `note` block under the buttons')
sub = re.search(r"everythingSub: '([^']*)'", js)
ok(sub and len(sub.group(1)) <= 48,
   'C7  the second option is disambiguated in one short line, not a paragraph',
   (len(sub.group(1)), sub.group(1)) if sub else None)


# ===========================================================================
# D. The partition property, and what "everything" is allowed to mean
# ===========================================================================
print('\nD. what the second scope actually contains')

be = fn('renderChewyBreakeven', 'async function') if 'async function renderChewyBreakeven(' in js else fn('renderChewyBreakeven')

i_win   = be.index('windowRows.push(row)')
i_pass  = be.index('if (!passesFilters) continue;')
i_all   = be.index('allRows.push(row)')
i_quick = be.index("if (quick === 'gaps')")
i_rows  = be.index('rows.push(row)')

# THE invariant. Push windowRows after any filter and the "All SKUs in this
# window" export quietly becomes a second copy of the filtered set.
ok(i_win < i_pass < i_all < i_quick < i_rows,
   'D1  PARTITION: windowRows pushed BEFORE every filter, then allRows, then rows',
   (i_win, i_pass, i_all, i_quick, i_rows))

# catVisPass is a saved preference, not a transient filter, so it must stay a
# hard skip - "everything" must not resurrect a category switched off on purpose.
ok("if (mid && !catVisPass('pnl_chewy_be', p)) continue;" in be,
   'D2  category VISIBILITY stays a hard skip, above the passesFilters flag')
ok(be.index("catVisPass('pnl_chewy_be'") < be.index('let passesFilters'),
   'D3  and it is evaluated before the flag, so it cannot be flipped on by it')

# The transient controls are the ones the flag governs.
for ctrl in ('brand', 'cat', 'search'):
    ok(('passesFilters = false' in be) and (be.count('passesFilters = false') >= 3),
       'D4  brand / category / search all route through the flag (%s)' % ctrl)
    break

ok('let chewyBreakevenWindowRows' in js, 'D5  the window set is snapshotted for the export')
ok('chewyBreakevenWindowRows = windowRows' in be,
   'D6  and assigned from the render, not rebuilt by the exporter')


# ===========================================================================
# E. The file says what it was scoped to
# ===========================================================================
print('\nE. CSV context line')

w = fn('_writeChewyBreakevenCSV')
for token in ('chpnl-be-brand', 'chpnl-be-cat', 'chpnl-be-search', 'chpnl-be-filter', 'chpnl-be-minunits'):
    ok(token in w, 'E1  the context line reads %s' % token)
ok('rows exported' in w, 'E2  and states the exported row count')
ok('window ${from} -> ${to}' in w, 'E3  the window is still named')


print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
