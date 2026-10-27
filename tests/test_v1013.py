# -*- coding: utf-8 -*-
"""
v10.13 — "All time" on every date picker, and a default trend on Units Sold.

Two asks: an All-time option everywhere a date window is chosen, and the
v10.12 default-trend behaviour extended to the Units Sold page.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(os.path.dirname(HERE), 'index.html')
src = io.open(INDEX, encoding='utf-8', newline='').read()
js = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', src, re.S), key=len)


def fn(name):
    for pat in (r'\nfunction %s\s*\(' % re.escape(name),
                r'\nasync function %s\s*\(' % re.escape(name)):
        m = re.search(pat, js)
        if m:
            break
    else:
        raise SystemExit('FAIL: cannot find %s' % name)
    k = m.end() - 1
    pdepth = 0
    while k < len(js):                       # balance the parameter list first
        if js[k] == '(':
            pdepth += 1
        elif js[k] == ')':
            pdepth -= 1
            if pdepth == 0:
                break
        k += 1
    i = js.index('{', k)
    depth, j = 0, i
    while j < len(js):
        if js[j] == '{':
            depth += 1
        elif js[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return js[m.start() + 1:j + 1]


SLICES = ['let _pnlSuppressDeltas = false;', fn('pnlAllTimeFrom'), fn('pnlDeltaChip')]

HARNESS = r'''
__SLICES__

let pass = 0, fail = 0; const failures = [];
function ok(c, label, extra) { if (c) pass++; else { fail++; failures.push(label + (extra ? ' :: ' + extra : '')); } }

// ═════════ A. pnlAllTimeFrom ═════════
const rows = [
  { week_start: '2025-06-02' },
  { week_start: '2024-03-04' },     // earliest
  { week_start: '2026-09-07' },
];
ok(pnlAllTimeFrom(rows, 'week_start') === '2024-03-04', 'A1 returns the earliest date',
   pnlAllTimeFrom(rows, 'week_start'));

// A2 — ISO dates compare correctly as strings, including across a year edge
// and a single-digit month that a numeric sort would get wrong.
ok(pnlAllTimeFrom([{d:'2026-01-05'},{d:'2025-12-31'}], 'd') === '2025-12-31', 'A2 year boundary');
ok(pnlAllTimeFrom([{d:'2026-10-01'},{d:'2026-09-30'}], 'd') === '2026-09-30', 'A2 month boundary');
ok(pnlAllTimeFrom([{d:'2026-02-10'},{d:'2026-02-02'}], 'd') === '2026-02-02', 'A2 day within a month');

// A3 — degenerate inputs fall back to an epoch rather than throwing or
// producing undefined, which would silently filter every row out.
ok(pnlAllTimeFrom([], 'week_start') === '1970-01-01', 'A3 empty data -> epoch');
ok(pnlAllTimeFrom(null, 'week_start') === '1970-01-01', 'A3 null data -> epoch');
ok(pnlAllTimeFrom(undefined, 'x') === '1970-01-01', 'A3 undefined data -> epoch');
ok(pnlAllTimeFrom([{}, {}], 'week_start') === '1970-01-01', 'A3 rows without the field -> epoch');
ok(pnlAllTimeFrom([null, { d: '2026-01-01' }], 'd') === '2026-01-01', 'A3 a null row is skipped');
ok(pnlAllTimeFrom([{ d: '' }, { d: '2026-01-01' }], 'd') === '2026-01-01', 'A3 a blank value is skipped');

// A4 — the field name is honoured, not assumed.
ok(pnlAllTimeFrom([{ day: '2024-01-01', week_start: '2026-01-01' }], 'day') === '2024-01-01',
   'A4 reads the requested field');

// ═════════ B. delta suppression under All time ═════════
// A delta needs a prior period. "All time" has none by construction, so every
// scorecard would read "new - no prior data": true, and uniformly useless.
_pnlSuppressDeltas = false;
const normal = pnlDeltaChip(120, 100, true, false, '2026-01-01 -> 2026-03-01');
ok(normal.indexOf('20.0%') >= 0, 'B1 a normal period still renders its delta', normal);
ok(normal.indexOf('vs prev') >= 0, 'B1 and labels it vs prev');

_pnlSuppressDeltas = true;
ok(pnlDeltaChip(120, 100, true, false, 'x') === '', 'B2 suppressed under all time');
ok(pnlDeltaChip(120, 0, true, false, 'x') === '', 'B2 the "new - no prior data" variant too');
ok(pnlDeltaChip(12, 10, true, true, 'x') === '', 'B2 and the percentage-points variant');
ok(pnlDeltaChip(0, 0, true, false, 'x') === '', 'B2 and the both-zero variant');

// B3 — the flag is a toggle, not a one-way door: switching back off restores.
_pnlSuppressDeltas = false;
ok(pnlDeltaChip(120, 100, true, false, 'x') !== '', 'B3 restored when the flag clears');

// B4 — direction and colour are unaffected by the change.
_pnlSuppressDeltas = false;
const down = pnlDeltaChip(80, 100, true, false, 'x');
ok(down.indexOf('-20.0%') >= 0 && down.indexOf('▼') >= 0, 'B4 a fall renders as a down arrow', down);
const costUp = pnlDeltaChip(120, 100, false, false, 'x');
ok(costUp.indexOf('sp-red') >= 0, 'B4 a rising COST still reads red (goodWhenUp=false)');

console.log('\n  v10.13: ' + pass + ' passed, ' + fail + ' failed');
if (fail) { failures.forEach(f => console.log('    FAIL ' + f)); process.exit(1); }
'''

harness = HARNESS.replace('__SLICES__', '\n\n'.join(SLICES))
tmpdir = tempfile.mkdtemp(prefix='v1013_')
jsp = os.path.join(tmpdir, 'test_v1013.js')
io.open(jsp, 'w', encoding='utf-8', newline='').write(harness)

print('=== v10.13 behaviour tests ===')
r = subprocess.run([os.environ.get('NODE', 'node'), jsp], capture_output=True, text=True)
sys.stdout.write(r.stdout)
sys.stderr.write(r.stderr)
if r.returncode != 0:
    sys.exit(r.returncode)

print('\n=== v10.13 static assertions ===')
sfail = []


def sok(cond, label):
    print(('  ok: ' if cond else '  FAIL: ') + label)
    if not cond:
        sfail.append(label)


def options_of(select_id):
    """Pull the <option> values out of one <select> by id."""
    m = re.search(r'<select[^>]*id="%s"' % re.escape(select_id), src)
    if not m:
        return None
    end = src.index('</select>', m.start())
    return re.findall(r'<option value="([^"]*)"', src[m.start():end])


# THE ask: every date-window picker offers an all-time choice.
# v11.02 re-point: the Chewy P&L had FOUR period pickers and now has ONE
# (chpnl-period). The guarantee this block asserts is unchanged - every
# date-window picker in the app offers all-time - so it simply follows the
# control. RETIRED_PICKERS below is the regression guard that keeps the
# consolidation from drifting back into per-tab copies.
PICKERS = {
    'pnl-period': 'all', 'spnl-period': 'all', 'wmpnl-period': 'all',
    'chpnl-period': 'all',          # v11.02: the ONE Chewy picker
    'fPeriod': '0', 'salesPeriod': '0', 'fba-ship-window': '0',   # pre-existing
}
RETIRED_PICKERS = ('chpnl-sales-period', 'chpnl-cost-period', 'chpnl-be-period')
for sid, val in PICKERS.items():
    opts = options_of(sid)
    sok(opts is not None, 'picker %s exists' % sid)
    sok(opts is not None and val in opts, '%s offers an all-time option (%r)' % (sid, val))

# All-time must be LAST among the window choices on the five new ones, i.e.
# after the rolling / named windows, so it does not interrupt the common path.
# v11.02 - chpnl-period JOINS this check. Before the consolidation the
# Rebates picker had no custom-range option at all, so it could not be held
# to the ordering rule; the shared control carries the full option list, so
# the re-point TIGHTENS rather than loosens.
for sid in ('pnl-period', 'spnl-period', 'wmpnl-period', 'chpnl-period'):
    opts = options_of(sid)
    sok(opts is not None and opts.index('all') == len(opts) - 2 and opts[-1] == 'custom',
        '%s puts All time just before Custom range' % sid)

# Regression guard: the three retired per-tab pickers must stay gone, or the
# page is back to four controls that can drift apart (it already had done -
# Sales carried this-month/last-month that Cost and Break-Even lacked).
for sid in RETIRED_PICKERS:
    sok(options_of(sid) is None,
        'retired per-tab picker %s is gone (one shared control)' % sid)
sok(len(re.findall(r'<select[^>]*id="chpnl-period"', src)) == 1,
    'exactly one Chewy period <select> in the markup')

# Each resolver has an all-time branch that reads the real earliest date.
for fname, data in (('getPnlDateRange', 'src.rows'),
                    ('getShopifyPnlDateRange', 'shopifyPnlData'),
                    ('getWalmartPnlDateRange', 'walmartPnlData')):
    body = fn(fname)
    sok('pnlAllTimeFrom(' in body, '%s derives all-time from real data' % fname)
    sok(data in body, '%s reads %s' % (fname, data))
    sok('allTime: true' in body, '%s flags the range as all-time' % fname)

# v11.02 re-point - the Chewy resolvers are thin wrappers now, so the check
# FOLLOWS THE CALL rather than being dropped. Same guarantee in three hops:
# wrapper -> getChewyPnlDateRange -> computePnlDateRange's allRows branch.
for fname, key in (('getChewyPnlSalesDateRange', 'sales'),
                   ('getChewyPnlCostDateRange', 'cost'),
                   ('getChewyBreakevenDateRange', 'breakeven'),
                   ('getChewyProgramDateRange', 'program'),
                   ('getChewyRebatesDateRange', 'rebates')):
    body = fn(fname)
    sok("getChewyPnlDateRange('%s')" % key in body,
        '%s delegates to the shared resolver as %r' % (fname, key))
_shared = fn('getChewyPnlDateRange')
sok('CHEWY_PERIOD_SOURCES[sourceKey]' in _shared,
    'getChewyPnlDateRange picks the all-time feed from the registry')
sok('allRows:' in _shared and 'allField:' in _shared,
    'getChewyPnlDateRange hands computePnlDateRange its own all-time source')
_cpdr = fn('computePnlDateRange')
sok('Array.isArray(opts.allRows)' in _cpdr and 'pnlAllTimeFrom(opts.allRows' in _cpdr,
    'computePnlDateRange derives all-time from the caller-supplied rows')
sok('allTime: true' in _cpdr, 'computePnlDateRange flags the range as all-time')

# The registry must name the REAL caches, or 'All time' silently floors at
# 1970 - and Break-Even must keep reading the AD feed rather than the
# sell-through one, which starts on a different day.
_reg = js[js.index('const CHEWY_PERIOD_SOURCES'):]
_reg = _reg[:_reg.index('};') + 2]
for key, cache in (('sales', 'chewyPnlSalesData'), ('cost', 'chewyPnlSalesData'),
                   ('breakeven', 'chewyAdSpendData'), ('program', 'chewyPnlSalesData'),
                   ('rebates', 'chewyPnlData')):
    line = [l for l in _reg.split(chr(10)) if l.strip().startswith(key + ':')]
    sok(len(line) == 1 and cache in line[0],
        'CHEWY_PERIOD_SOURCES.%s measures all-time over %s' % (key, cache))

# The pure PDF resolver must NOT set the global flag (it loops arbitrary keys).
# Look for an ASSIGNMENT, not a mention — the function's comment names the
# flag precisely to explain why it does not touch it.
sok(not re.search(r'_pnlSuppressDeltas\s*=', fn('computePnlDateRange')),
    'computePnlDateRange stays pure (no suppression side effect)')
sok("if (v === 'all')" in fn('computePnlDateRange'), 'computePnlDateRange still handles all-time')

# Suppression wired in exactly one place.
sok(js.count('if (_pnlSuppressDeltas) return \'\';') == 1, 'suppression guard lives in pnlDeltaChip only')
sok(js.count('let _pnlSuppressDeltas = false;') == 1, 'one suppression flag')

# Period label maps know the new key, or the UI prints a raw "all".
sok(js.count("'all': 'All time'") + js.count("'all':'All time'") == 2,
    'both Amazon period-label maps know the all-time key')

# ── Units Sold default trend.
sales = fn('updateSalesChart')
sok('salesSelectionActive' in sales, 'Units Sold tracks whether a selection is active')
sok('salesVisibleRows' in sales, 'Units Sold falls back to the visible rows')
sok('if (salesSelected.size === 0) { closeSalesDrill(); return; }' not in sales,
    'Units Sold no longer closes the panel when nothing is selected')
sok(sales.count('chartMids.forEach(mid => {') == 4,
    'all four per-product loops walk chartMids')
sok(sales.count('salesSelected.forEach(mid => {') == 0,
    'no loop still walks the raw selection')
sok('Total \\u00b7 ${chartMids.length} product' in sales or 'Total · ${chartMids.length} product' in sales,
    'Units Sold builds a Total series')
sok("Other \\u00b7 ${tail.length} SKUs" in sales or 'Other · ${tail.length} SKUs' in sales,
    'Units Sold rolls the tail into Other when stacked')
sok("d.fill = i === 0 ? 'origin' : '-1'" in sales,
    'Units Sold re-chains the area fills after reordering (the v4.135 bug)')
sok("_salesPanel.style.display = 'block'" in sales, 'the render opens the panel itself')

# Every call site must fire in the default state too.
sok('if(salesSelected.size>0)updateSalesChart()' not in src,
    'markup pickers no longer gate the redraw on a selection')
sok('if (hasSel) updateSalesChart();' not in js,
    'renderSalesTbl no longer gates the redraw on a selection')
sok('else if (salesSelected.size > 0) updateSalesChart();' not in js,
    'chart-type change no longer gates the redraw on a selection')
sok(js.count('if (salesSelected.size > 0) updateSalesChart();\n  else closeSalesDrill();') == 0,
    'deselecting to empty falls back to the total instead of closing')

# Provenance, not the chip (see README).
sok(src.count('v10.13 —') >= 1, "v10.13's own provenance markers survive")
for marker in ('v10.12 —', 'v10.11 —', 'v4.135 '):
    sok(marker in src, 'earlier provenance marker preserved: %s' % marker.split(' ')[0])

print('\n  static: %d failed' % len(sfail))
if sfail:
    sys.exit(1)
print('\n  v10.13 ALL GREEN')
