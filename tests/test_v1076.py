# -*- coding: utf-8 -*-
"""v10.76 - unit-sales goals by channel: monthly entry, weekly prorated line.

Jason: "on the units sold page, allow me to set goals by channel for unit sales.
i should be able to set these on a monthly basis and have the goal trend appear
as a weekly line. i should be able to toggle this on and off."

Monthly numbers have to become a WEEKLY series, and the interesting part is
every way that conversion can lie:

  * THE REGRESSION GUARD (section B4). A week straddling the end of the goal
    range covers only part of a month that has a goal. Summing "whatever is
    covered" gives ~3/7 of a full week, which draws as a goal CRASH at the
    boundary rather than as "the goals stop here". The guard runs that naive
    version and proves it really does report 600 where the shipped code
    reports null. Without it, "the line ends cleanly" is a memory, not a
    checkable claim.

  * PER-DAY, NOT PER-MONTH (B2). 3,100 in a 31-day January and 2,800 in a
    28-day February are the SAME daily rate, so the weekly line must be flat
    at 700 across the boundary. A month/4.33 shortcut would step by 10%.

  * STRICT vs LOOSE COVERAGE (B5/B6). A single-channel line must NOT draw 0
    for a month that channel has no goal for - 0 is a target of zero, and
    blank means no target. The business total must still draw when only one
    channel has goals, or setting one channel would render nothing.

  * stack: '_goal' (C3). Without it a stacked bar / stacked area chart folds
    the TARGET into the stack and the top of the chart reads actual + goal.
    Visually plausible, completely wrong.

  * THE TARGET IS NOT UNITS (D1/D2/D5). The goal dataset must be pushed only
    AFTER the chart's unit total is summed, and salesCovFooter's "Combined:"
    line must skip it. Both are off-by-one-dataset bugs that inflate a
    headline number while every individual series still reads correctly.
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

def const_obj(name):
    """Slice `const NAME = { ... };` by balancing braces."""
    i = js.index('const %s = {' % name)
    j = js.index('{', i); d = 0; k = j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k+1] + ';'
        k += 1

def const_line(name):
    """Slice a one-line `const NAME ... ;` arrow helper."""
    m = re.search(r'^const\s+%s\s*=.*?;\s*$' % re.escape(name), js, re.M)
    assert m, 'const %s not found as a single line' % name
    return m.group(0)


# ===========================================================================
# A. Static - the wiring, the storage key, the markup
# ===========================================================================
print('\nA. static source assertions')

ok(js.count("'sales_unit_goals'") >= 2,
   "A1  goals live on app_settings key 'sales_unit_goals' (read + write)",
   js.count("'sales_unit_goals'"))

ok("upsert({ key: 'sales_unit_goals', value: payload }, { onConflict: 'key' })" in js,
   "A2  write upserts on the app_settings primary key")

# No migration: app_settings came from v9.85 and already carries a second key.
ok('supabase_v9_85_global_tab_defaults.sql' in js,
   "A3  the missing-table message names the EXISTING migration (no new SQL)")

# v10.8 class - every handler named in the editor markup must be defined.
HANDLERS = ['toggleSalesGoals', 'openSalesGoalsEditor', 'salesGoalsEditorYear',
            'salesGoalsDraftSet', 'salesGoalsFillYear', 'salesGoalsClearYear',
            'salesGoalsSave', 'renderSalesGoalsEditor', 'salesGoalsEditorRefreshTotals',
            'syncSalesGoalsToggle', 'refreshSalesChart', 'salesGoalWeeklyFor',
            'salesGoalDatasets', 'salesGoalChannels', 'salesGoalScopeNote',
            'salesGoalSubNote', 'loadSalesGoals', 'writeSalesGoals']
missing_def = [h for h in HANDLERS if ('function %s(' % h) not in js]
ok(not missing_def, 'A4  every new function is defined (called-but-undefined sweep)', missing_def)

called = set(re.findall(r'\b(salesGoals\w+|toggleSalesGoals|openSalesGoalsEditor|refreshSalesChart|syncSalesGoalsToggle|loadSalesGoals|writeSalesGoals)\s*\(', js))
undef = sorted(c for c in called if ('function %s(' % c) not in js)
ok(not undef, 'A5  no goal-namespace call site resolves to nothing', undef)

# v10.20 class - a \uXXXX escape in RAW markup renders as six literal chars.
hdr = s[s.index('<button id="salesGoalsToggle"'): s.index('<!-- v7.54')]
ok('\\u' not in hdr and '\\U' not in hdr,
   'A6  the toggle markup uses real glyphs, not \\uXXXX (raw markup does not decode)')
ok('\U0001F3AF' in hdr, 'A7  the toggle carries the target glyph')

# Saved reports carry the toggle, not the numbers.
ok('goalsOn: salesGoalsOn,' in js, 'A8  salesSnapshotState captures the on/off state')
ok('if (v.chart && v.chart.goalsOn !== undefined) {' in js,
   'A9  apply guards on !== undefined so a pre-v10.76 report does not force it off')
ok('goalsOn' in js and 'salesGoals:' not in js.split('chart: {')[1][:600],
   'A10 the goal NUMBERS are not snapshotted into a report (shared, not frozen)')

ok('loadSalesGoals().then(() => { try { syncSalesGoalsToggle(); } catch {} });' in js,
   'A11 init loads goals in the background and syncs the toggle label')


# ===========================================================================
# B. Behaviour - drive the REAL sliced salesGoalWeeklyFor
# ===========================================================================
print('\nB. weekly proration (real sliced salesGoalWeeklyFor)')

harness = r'''
// ---- real code, sliced out of index.html ----
__PARSE_LOCAL__
__MONTHKEY__
__DAYSIN__
__CHANNELS__
__WEEKLYFOR__
__GOALCHANS__
__DATASETS__
__SUBNOTE__
__SCOPENOTE__

// ---- stubs ----
let salesGoals = {};
let salesGoalsOn = true;
let salesSelected = new Set();
let topProductFilterId = null;
let _dom = {};
const document = { getElementById: (id) => (_dom[id] || null) };

const out = [];
const T = (name, got, want) => out.push({ name, got, want, pass: JSON.stringify(got) === JSON.stringify(want) });

// 3100 over a 31-day January = exactly 100 units/day.
// 2800 over a 28-day February = exactly 100 units/day too.
// Same daily rate, different monthly number: the weekly line must be FLAT.
const JAN_FEB = { amazon_us: { '2026-01': 3100, '2026-02': 2800 } };
const JAN_ONLY = { amazon_us: { '2026-01': 3100 } };
const JAN_FEB_FAST = { amazon_us: { '2026-01': 3100, '2026-02': 5600 } };   // Feb = 200/day

// Mondays: 2026-01-05 is fully inside January.
// 2026-01-26 covers Jan 26-31 (6 days) + Feb 1 (1 day).
// 2026-02-02 is fully inside February.
const W_JAN  = '2026-01-05';
const W_EDGE = '2026-01-26';
const W_FEB  = '2026-02-02';

salesGoals = JAN_ONLY;
T('B1 full week inside a month = 7 x daily rate',
  salesGoalWeeklyFor([W_JAN], ['amazon_us'], true), [700]);

salesGoals = JAN_FEB;
T('B2 same daily rate across a 31d and a 28d month = FLAT weekly line',
  salesGoalWeeklyFor([W_JAN, W_EDGE, W_FEB], ['amazon_us'], true), [700, 700, 700]);

salesGoals = JAN_FEB_FAST;
T('B3 straddling week blends per DAY (6 x 100 + 1 x 200)',
  salesGoalWeeklyFor([W_EDGE], ['amazon_us'], true), [800]);

// --- THE REGRESSION GUARD ---------------------------------------------------
// Pre-fix behaviour: sum whatever days happen to be covered, with no
// all-days-covered gate. The straddling week then reports 6/7 of a full week,
// which draws as a goal CRASH at the end of the goal range.
function naiveWeekly(weeks, chans) {
  return weeks.map(w => {
    const mon = parseLocalDate(w);
    let total = 0;
    for (let i = 0; i < 7; i++) {
      const d = new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + i);
      const mk = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      const dim = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
      chans.forEach(ch => {
        const g = (salesGoals[ch] || {})[mk];
        if (g != null) total += Number(g) / dim;
      });
    }
    return Math.round(total * 10) / 10;
  });
}
salesGoals = JAN_ONLY;   // February has NO goal at all
T('B4a GUARD: the naive version really does report a partial week (600)',
  naiveWeekly([W_EDGE], ['amazon_us']), [600]);
T('B4b shipped code refuses to draw that week at all (no series)',
  salesGoalWeeklyFor([W_EDGE], ['amazon_us'], true), null);
T('B4c and the fully-covered week before it is unaffected',
  salesGoalWeeklyFor([W_JAN, W_EDGE], ['amazon_us'], true), [700, null]);

// --- strict vs loose coverage ----------------------------------------------
// Shopify has January only. Amazon has January AND February.
salesGoals = { amazon_us: { '2026-01': 3100, '2026-02': 2800 },
               shopify:   { '2026-01':  620 } };
T('B5 single-channel line does NOT draw 0 for a month it has no goal for',
  salesGoalWeeklyFor([W_FEB], ['shopify'], true), null);
T('B5b and in a mixed window that month is a gap beside a real week',
  salesGoalWeeklyFor([W_JAN, W_FEB], ['shopify'], true), [140, null]);
T('B6 business total still draws in February off the channel that HAS a goal',
  salesGoalWeeklyFor([W_FEB], ['amazon_us', 'shopify'], false), [700]);
T('B7 business total sums both channels in a month both cover (700 + 140)',
  salesGoalWeeklyFor([W_JAN], ['amazon_us', 'shopify'], false), [840]);

// --- degenerate shapes -----------------------------------------------------
salesGoals = {};
T('B8 no goals at all returns null (no series), not an array of zeros',
  salesGoalWeeklyFor([W_JAN], ['amazon_us'], true), null);
salesGoals = { amazon_us: { '2026-01': 3100 } };
T('B9 a channel with no goal data is dropped from the request',
  salesGoalWeeklyFor([W_JAN], ['walmart'], true), null);
T('B10 an all-null window returns null rather than a line of gaps',
  salesGoalWeeklyFor([W_FEB], ['amazon_us'], true), null);
T('B11 a malformed week key is a gap beside a good week, not a throw',
  salesGoalWeeklyFor([W_JAN, 'not-a-date'], ['amazon_us'], true), [700, null]);

// ---------------------------------------------------------------------------
// C. dataset shape
// ---------------------------------------------------------------------------
salesGoals = { amazon_us: { '2026-01': 3100 }, shopify: { '2026-01': 620 } };

salesGoalsOn = false;
T('C1 toggle OFF produces no dataset at all',
  salesGoalDatasets([W_JAN], null, 'total'), []);
salesGoalsOn = true;

const tot = salesGoalDatasets([W_JAN], null, 'total');
T('C2 total mode = exactly ONE line', tot.length, 1);
T('C3 stack is isolated so a stacked chart cannot add the target into the stack',
  tot[0].stack, '_goal');
T('C4 flagged _isGoal so unit totals can exclude it', tot[0].isGoal_flag = tot[0]._isGoal, true);
T('C5 drawn as a dashed, unfilled line even inside a bar/area chart',
  [tot[0].type, tot[0].fill, Array.isArray(tot[0].borderDash)], ['line', false, true]);
T('C6 total line value = sum across both channels (700 + 140)', tot[0].data, [840]);
T('C7 gaps are NOT spanned, so the line ends where the goals do',
  tot[0].spanGaps, false);

const perCh = salesGoalDatasets([W_JAN], ['amazon_us', 'shopify', 'walmart'], 'channel');
T('C8 channel mode emits one line per channel WITH goals (walmart dropped)',
  perCh.length, 2);
T('C9 each channel line carries its own channel colour',
  perCh.map(d => d.borderColor), [SALES_CHANNELS.amazon_us.color, SALES_CHANNELS.shopify.color]);
T('C10 per-channel values are that channel alone', perCh.map(d => d.data), [[700], [140]]);
T('C11 no weeks = no dataset (cannot divide an empty window)',
  salesGoalDatasets([], null, 'total'), []);

// ---------------------------------------------------------------------------
// D. subtitle note + scope warning
// ---------------------------------------------------------------------------
T('D1 % of goal is actual/goal, and the goal is NOT added to actual',
  salesGoalSubNote(tot, 420).indexOf('50% of goal') > -1, true);
T('D2 no goal series = no note', salesGoalSubNote([], 420), '');

salesSelected = new Set();
_dom = {};
T('D3 a clean, unfiltered view carries no scope warning', salesGoalScopeNote(), '');
salesSelected = new Set(['SP-0001', 'SP-0002']);
const note = salesGoalScopeNote();
T('D4 a product selection warns that the goal is business-wide',
  [note.indexOf('business-wide') > -1, note.indexOf('2 products selected') > -1], [true, true]);
salesSelected = new Set();
_dom = { salesBrand: { value: 'Meowijuana' }, salesSrch: { value: 'spray' } };
const note2 = salesGoalScopeNote();
T('D5 every narrowing filter is named, not just the first',
  [note2.indexOf('brand filter') > -1, note2.indexOf('search') > -1], [true, true]);
salesGoalsOn = false;
T('D6 no warning when the overlay is off', salesGoalScopeNote(), '');
salesGoalsOn = true;

console.log(JSON.stringify(out));
'''

harness = (harness
    .replace('__PARSE_LOCAL__', fn('parseLocalDate'))
    .replace('__MONTHKEY__',    const_line('_salesMonthKey'))
    .replace('__DAYSIN__',      const_line('_salesDaysInMonth'))
    .replace('__CHANNELS__',    const_obj('SALES_CHANNELS'))
    .replace('__WEEKLYFOR__',   fn('salesGoalWeeklyFor'))
    .replace('__GOALCHANS__',   fn('salesGoalChannels'))
    .replace('__DATASETS__',    fn('salesGoalDatasets'))
    .replace('__SUBNOTE__',     fn('salesGoalSubNote'))
    .replace('__SCOPENOTE__',   fn('salesGoalScopeNote')))

hp = os.path.join(SP, 'test_v1076.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run([ 'node', hp ], capture_output=True, text=True)
if r.returncode != 0:
    print('  FAIL  harness did not run:\n' + (r.stderr or '')[:3000]); failed += 1
else:
    try:
        rows = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  harness output unparseable: %s\n%s' % (e, r.stdout[:2000])); failed += 1; rows = []
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


# ===========================================================================
# D. Static - the target must never be counted as units sold
# ===========================================================================
print('\nD. the target is not units sold')

tot_fn = fn('updateSalesChart', 'async function')
i_total = tot_fn.index('const periodTotal = datasets.map(')
i_goal  = tot_fn.index("salesGoalDatasets(weeks, null, 'total')")
ok(i_total < i_goal,
   'D1  Total tab: the goal joins `datasets` only AFTER periodTotal is summed')
ok('_salesGoalNote' in tot_fn and '${_freshLine}${_salesGoalNote}' in tot_fn,
   'D2  Total tab: the goal figure lands in the subtitle')
ok('_salesGoalDs.length > 0' in tot_fn,
   'D3  Total tab: the legend appears for the goal line even with 0-1 products selected')

ch_fn = fn('updateChannelChart', 'async function')
i_ctot  = ch_fn.index('const chanTotal = datasets.reduce(')
i_cgoal = ch_fn.index("salesGoalDatasets(weeks, activeChannels.map(")
ok(i_ctot < i_cgoal,
   'D4  By Channel: the goal joins `datasets` only AFTER chanTotal is summed')
ok("'channel')" in ch_fn[i_cgoal:i_cgoal + 200],
   'D5  By Channel asks for per-channel lines, not the business total')

footer = fn('salesCovFooter')
ok('_isGoal' in footer and 'Combined:' in footer,
   "D6  salesCovFooter's stacked 'Combined:' line skips the goal dataset")

# Both chart paths push LAST, so the stacked-area fill chain (index-relative
# `fill: '-1'`) is untouched.
ok(tot_fn.count('_salesGoalDs.forEach(d => datasets.push(d));') == 1 and
   ch_fn.count('_chGoalDs.forEach(d => datasets.push(d));') == 1,
   'D7  each chart appends the goal exactly once, at the end of `datasets`')

# Blank means "no goal", not zero - the whole gap rule depends on it.
draft = fn('salesGoalsDraftSet')
ok('delete _salesGoalsDraft[ch][mk]' in draft,
   'D8  a blank / 0 / junk entry DELETES the month (no goal != a goal of zero)')
wr = fn('writeSalesGoals', 'async function')
ok('num > 0' in wr and 'Object.keys(m).length' in wr,
   'D9  the write prunes non-positive months and empty channels')


# ===========================================================================
# E. storage round trip against a stubbed Supabase
# ===========================================================================
print('\nE. storage (real sliced loadSalesGoals / writeSalesGoals)')

h2 = r'''
__LOAD__
__WRITE__

let salesGoals = {};
let _salesGoalsLoaded = false;
let _sent = null, _mode = 'ok', _stored = null;

const getSB = async () => ({
  from: () => ({
    select: () => ({ eq: () => ({ maybeSingle: async () =>
      _mode === 'err'   ? { data: null, error: { message: 'relation "app_settings" does not exist' } }
    : _mode === 'array' ? { data: { value: [1, 2, 3] }, error: null }
    : _mode === 'null'  ? { data: null, error: null }
    :                     { data: { value: _stored }, error: null }
    }) }),
    upsert: async (row) => { _sent = row; return { error: null }; },
  }),
});

const out = [];
const T = (name, got, want) => out.push({ name, got, want, pass: JSON.stringify(got) === JSON.stringify(want) });

(async () => {
  // write prunes
  await writeSalesGoals({
    amazon_us: { '2026-01': 3100, '2026-02': 0, '2026-03': '', '2026-04': -5, '2026-05': '4200' },
    shopify:   { '2026-01': null },
    chewy:     {},
  });
  T('E1 blanks / zero / negatives are dropped; strings coerce; empty channels vanish',
    _sent.value, { amazon_us: { '2026-01': 3100, '2026-05': 4200 } });
  T('E2 upsert targets the app_settings key', _sent.key, 'sales_unit_goals');
  T('E3 the in-memory copy matches what was stored',
    salesGoals, { amazon_us: { '2026-01': 3100, '2026-05': 4200 } });

  await writeSalesGoals({ amazon_us: { '2026-01': 0 } });
  T('E4 an all-blank grid stores null, not an empty object', _sent.value, null);

  // load
  _mode = 'ok'; _stored = { shopify: { '2026-06': 900 } };
  salesGoals = { stale: {} };
  await loadSalesGoals();
  T('E5 load replaces the local copy with the shared one', salesGoals, { shopify: { '2026-06': 900 } });
  T('E6 load marks itself done so the toggle stops re-fetching', _salesGoalsLoaded, true);

  _mode = 'err'; salesGoals = { shopify: { '2026-06': 900 } };
  await loadSalesGoals();
  T('E7 a failed read FAILS OPEN to no goals (never a broken page)', salesGoals, {});

  _mode = 'array';
  await loadSalesGoals();
  T('E8 a non-object stored value is rejected rather than indexed into', salesGoals, {});

  _mode = 'null';
  await loadSalesGoals();
  T('E9 an empty app_settings row reads as no goals', salesGoals, {});

  console.log(JSON.stringify(out));
})();
'''
h2 = h2.replace('__LOAD__', fn('loadSalesGoals', 'async function')) \
       .replace('__WRITE__', fn('writeSalesGoals', 'async function'))
h2p = os.path.join(SP, 'test_v1076_store.js')
io.open(h2p, 'w', encoding='utf-8', newline='').write(h2)
r2 = subprocess.run([ 'node', h2p ], capture_output=True, text=True)
if r2.returncode != 0:
    print('  FAIL  storage harness did not run:\n' + (r2.stderr or '')[:3000]); failed += 1
else:
    try:
        rows2 = json.loads(r2.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  storage output unparseable: %s\n%s' % (e, r2.stdout[:2000])); failed += 1; rows2 = []
    for row in rows2:
        ok(row['pass'], row['name'], None if row['pass'] else (row['got'], 'want', row['want']))


print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
