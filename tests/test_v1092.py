# -*- coding: utf-8 -*-
r"""v10.92 - the rail read a ROW window and called it a session list.

Jason: "i know i uploaded more months than this" - the SQP Brand-view rail
showed ONE upload covering 2026-01 while the freshness line on the SAME
card correctly read 2026-08.

Root cause: dzLoadRecentUploads asked for .limit(4000), but PostgREST caps
a response at db-max-rows (1000 by default). A Brand-view CSV is ~1000
rows, so the rail received exactly ONE session's worth of rows and
faithfully reported what it could see. The "1,000 rows" on screen WAS the
cap, printed as data.

That is Architecture Rule #4 ("Supabase default row limit = 1000 - all
large queries must use .range() pagination"), which the v10.85 rail broke.
It affected EVERY rail on a high-row table, not just this one.

Two guarantees this suite pins:
  1. the loader pages by SESSION, so a single >=1000-row upload reports its
     real row count and older sessions are not invisible
  2. a session that may be cut by the page cap is DROPPED, not printed -
     a short list is honest, a wrong range is not
"""
import io, os, re, sys, json, subprocess

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8', newline='').read()
JS  = max(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', s, re.S), key=len)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond:
        P += 1; print('  ok  ' + label)
    else:
        F += 1; fails.append(label)
        print('  FAIL ' + label + (('  -> ' + str(got)) if got is not None else ''))

def fn(name):
    """Slice a function by brace balance. Includes the `async ` when the real
    declaration has one - the v10.85 trap: an anchor on `function X(` matches
    INSIDE `async function X(` and splits it."""
    m = re.search(r'(?:async\s+)?function\s+' + name + r'\s*\(', JS)
    if not m: return ''
    k = JS.index('(', m.end() - 1); d = 0
    while True:
        if JS[k] == '(': d += 1
        elif JS[k] == ')':
            d -= 1
            if d == 0: break
        k += 1
    j = JS.index('{', k); d = 0; k = j
    while True:
        if JS[k] == '{': d += 1
        elif JS[k] == '}':
            d -= 1
            if d == 0: return JS[m.start():k + 1]
        k += 1


LOADER = fn('dzLoadRecentUploads')

def strip_comments(src):
    """Drop // line comments and /* */ blocks.

    The v10.92 fix DOCUMENTS the old `.limit(4000)` in a comment explaining
    why it was wrong. A naive grep for it therefore matches forever and the
    guard can never go green - the v10.90 prose-in-source class. Assert on
    live code only.
    """
    src = re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', src)

LOADER_CODE = strip_comments(LOADER)


# -- A. The cap is gone and pagination is real -----------------------------
print('\nA. the loader pages instead of sampling rows')

ok(bool(LOADER), 'dzLoadRecentUploads located')
ok(re.search(r'async\s+function\s+dzLoadRecentUploads', JS) is not None,
   'still async (its awaits depend on it)')

# The regression guard: the bare row-sample cannot come back.
ok('.limit(4000)' not in LOADER_CODE, 'the .limit(4000) row sample is gone from live code')
ok(not re.search(r'\.limit\(\s*\d+\s*\)', LOADER_CODE),
   'no bare .limit(N) row sample survives anywhere in the loader',
   re.findall(r'\.limit\([^)]*\)', LOADER_CODE))
# ...but the comment explaining WHY must stay, so the next person does not
# "optimise" the pagination back into a single capped request.
ok('.limit(4000)' in LOADER,
   'the comment naming the old bug is still there as a warning')
# Guard the stripper, or it could pass vacuously against a blanked body.
ok('.range(' in LOADER_CODE and 'const PAGE' in LOADER_CODE,
   'strip_comments kept the real code (not a vacuous pass)')
ok('.range(' in LOADER, 'pages with .range()')

# Constants, with sane bounds - a PAGE above 1000 would be silently capped
# by PostgREST again, which is the whole bug.
m = re.search(r'const PAGE = (\d+), MAX_PAGES = (\d+), WANT_SESSIONS = (\d+)', LOADER)
ok(bool(m), 'PAGE / MAX_PAGES / WANT_SESSIONS declared')
if m:
    page, maxp, want = int(m.group(1)), int(m.group(2)), int(m.group(3))
    ok(page <= 1000, 'PAGE <= 1000 - above the PostgREST cap it would truncate again', page)
    ok(maxp >= 2, 'MAX_PAGES allows more than one page', maxp)
    ok(want >= 1, 'WANT_SESSIONS is positive', want)
    ok(maxp > want, 'MAX_PAGES exceeds WANT_SESSIONS so the cap can be reached', (maxp, want))

# The query builder must be REBUILT each page. A Supabase builder is
# single-use; hoisting it out of the loop and re-ranging it is the subtle
# way to make pagination look right and return the same page twice.
loop = LOADER[LOADER.index('for (let pageNo'):] if 'for (let pageNo' in LOADER else ''
ok('sb.from(table)' in loop, 'the query is rebuilt INSIDE the paging loop')
ok('.eq(col, val)' in loop, 'the view_type filter is re-applied on every page')
ok(loop.count('.range(') == 1, 'exactly one .range() call, inside the loop',
   loop.count('.range('))


# -- B. A possibly-truncated session is dropped, not printed ---------------
print('\nB. the page cap cannot print a wrong range')

ok('exhausted' in LOADER, 'tracks whether the rows ran out or the cap hit')
ok(re.search(r'if \(!exhausted && byTs\.size > 1\)', LOADER) is not None,
   'drops the oldest session only when the cap stopped us')
ok('byTs.delete(' in LOADER, 'the suspect session is removed from the group map')
# Guard the guard: dropping when we DID exhaust would lose a real session.
ok('if (page.length < PAGE) { exhausted = true' in LOADER,
   'a short page means the data ran out')
ok('if (!page || !page.length) { exhausted = true' in LOADER,
   'an empty page means the data ran out')


# -- C. The v10.90 sort and labelling survived the rewrite -----------------
print('\nC. v10.90 behaviour is intact')

ok('periods: new Set()' in LOADER, 'sessions still carry a periods Set (v10.90)')
ok('localeCompare' in LOADER, 'still sorted by the DATA PERIOD, not upload time')
ok(not re.search(r'sort\(\(a, b\) =>\s*String\(b\.ts\)', LOADER),
   'no upload-time-only sort came back')
ok('_dzRecentCache[ckey] = out' in LOADER, 'result still cached per source key')


# -- D. Drive the REAL loader against a stubbed Supabase -------------------
print('\nD. behaviour, against a paging stub')

harness = r'''
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

// -- stubs ---------------------------------------------------------------
const UH_SOURCES = {
  big:   { dateField: 'reporting_month', label: 'Big' },
  meta:  { dateField: 'reporting_month', label: 'Meta', rowCountField: 'row_count' },
};
function dzSourceKey(src) {
  return src.table + (src.filter ? '|' + Object.entries(src.filter).map(([k, v]) => k + '=' + v).join(',') : '');
}
let _dzRecentCache = {};

// Rows are served newest-upload-first, exactly as the real query orders them.
let ROWS = [], EQ_CALLS = [], RANGES = [], ERROR_ON_PAGE = -1, PAGE_HITS = 0;
// db-max-rows: PostgREST silently truncates ANY response past this. The whole
// bug was asking for 4000 and getting 1000 with no error.
const DB_MAX_ROWS = 1000;

function builder(table) {
  const b = { _eq: [] };
  b.select = () => b;
  b.eq = (col, val) => { b._eq.push([col, val]); return b; };
  b.order = () => b;
  b.limit = (n) => { b._limit = n; return b; };
  b.range = async (from, to) => {
    const page = PAGE_HITS++;
    RANGES.push([from, to]);
    EQ_CALLS.push(b._eq.slice());
    if (page === ERROR_ON_PAGE) return { data: null, error: { message: 'boom' } };
    let rows = ROWS;
    for (const [c, v] of b._eq) rows = rows.filter(r => r[c] === v);
    const want = to - from + 1;
    return { data: rows.slice(from, from + Math.min(want, DB_MAX_ROWS)), error: null };
  };
  // The pre-v10.92 path: one shot, capped by the server.
  b.run_limit = async () => {
    EQ_CALLS.push(b._eq.slice());
    let rows = ROWS;
    for (const [c, v] of b._eq) rows = rows.filter(r => r[c] === v);
    return { data: rows.slice(0, DB_MAX_ROWS), error: null };
  };
  return b;
}
async function getSB() { return { from: (t) => builder(t) }; }

function reset() { EQ_CALLS = []; RANGES = []; ERROR_ON_PAGE = -1; PAGE_HITS = 0; _dzRecentCache = {}; }

// N sessions, each `per` rows, NEWEST FIRST (i = 0 is newest) - the order the
// real query returns. Timestamps strictly descend and months roll across the
// year boundary, so `oldest by ts` and `newest by period` are unambiguous even
// at 16 sessions.
function tsStr(i)  { return '2026-09-01T' + String(23 - i).padStart(2, '0') + ':00:00'; }
function monStr(i) {                 // i = 0 -> 2027-04, then back one month
  const t = 2027 * 12 + 3 - i;
  return String(Math.floor(t / 12)) + '-' + String((t % 12) + 1).padStart(2, '0');
}
function build(sessions, per, extra) {
  const rows = [];
  for (let i = 0; i < sessions; i++) {
    const ts = tsStr(i), mon = monStr(i);
    for (let k = 0; k < per; k++) rows.push(Object.assign({ uploaded_at: ts, reporting_month: mon }, extra || {}));
  }
  return rows;
}

__LOADER__

(async () => {

// -- 1. Jason's case: three 1000-row monthly uploads ---------------------
reset();
ROWS = build(3, 1000);
let r = await dzLoadRecentUploads('big');
t('D1  three 1000-row uploads surface as THREE sessions', r.length, 3);
t('D2  each reports its real row count', r.map(x => x.rows), [1000, 1000, 1000]);
t('D3  sorted newest data period first', r.map(x => x.max), [monStr(0), monStr(1), monStr(2)]);
t('D3b the fixture itself is sane - strictly descending valid timestamps',
  [tsStr(0), tsStr(15), monStr(0), monStr(15)],
  ['2026-09-01T23:00:00', '2026-09-01T08:00:00', '2027-04', '2026-01']);

// -- 2. The regression guard: reproduce the pre-v10.92 behaviour ---------
reset();
ROWS = build(3, 1000);
const sbOld = await getSB();
const oldRes = await sbOld.from('big').select('x').order().limit(4000).run_limit();
const oldTs = new Set(oldRes.data.map(x => String(x.uploaded_at).slice(0, 19)));
t('D4  the OLD single-.limit path really did see one session', oldTs.size, 1);
t('D5  ...and really did report exactly the cap as its row count', oldRes.data.length, 1000);

// -- 3. One big upload mid-page: the row count is now whole --------------
reset();
ROWS = build(1, 2500);
r = await dzLoadRecentUploads('big');
t('D6  a single 2,500-row upload reports 2,500 rows, not the 1,000 cap',
  [r.length, r[0].rows], [1, 2500]);
t('D7  a run that exhausted the rows keeps its only session', r.length, 1);

// -- 4. The page cap drops the session it may have cut ------------------
reset();
ROWS = build(16, 1000);          // 16,000 rows - more than MAX_PAGES can read
r = await dzLoadRecentUploads('big');
t('D8  the cap stops the walk without printing a cut session', r.length, 14);
const months = r.map(x => x.max);
t('D9  it is the OLDEST session that was dropped - the newest survives',
  [months[0], months.includes(monStr(15)), months.length], [monStr(0), false, 14]);
t('D10 every surviving session is whole', r.every(x => x.rows === 1000), true);

// -- 5. The filter is re-applied on every page --------------------------
reset();
ROWS = build(3, 1000, { view_type: 'brand' })
  .concat(build(2, 1000, { view_type: 'asin' }));
r = await dzLoadRecentUploads({ table: 'big', filter: { view_type: 'brand' } });
t('D11 a filtered source still pages', r.length >= 3, true);
t('D12 the filter rode along on EVERY page',
  EQ_CALLS.length > 1 && EQ_CALLS.every(c => c.length === 1 && c[0][0] === 'view_type' && c[0][1] === 'brand'),
  true);
t('D13 pages advance - no page served twice',
  RANGES.length > 1 && RANGES[1][0] > RANGES[0][0], true);

// -- 6. Errors ----------------------------------------------------------
reset();
ROWS = build(3, 1000); ERROR_ON_PAGE = 0;
r = await dzLoadRecentUploads('big');
t('D14 an error on the FIRST page returns nothing rather than guessing', r.length, 0);

reset();
ROWS = build(3, 1000); ERROR_ON_PAGE = 2;
r = await dzLoadRecentUploads('big');
t('D15 an error on a LATER page keeps the sessions already in hand', r.length >= 1, true);
t('D16 ...and drops the one it could not finish reading', r.every(x => x.rows === 1000), true);

// -- 7. rowCountField still wins over counting rows ---------------------
reset();
ROWS = build(2, 1, { row_count: 4321 });
r = await dzLoadRecentUploads('meta');
t('D17 a metadata table reports its stored count, not "1 rows"',
  r.map(x => x.rows), [4321, 4321]);

// -- 8. Cache -----------------------------------------------------------
reset();
ROWS = build(2, 1000);
await dzLoadRecentUploads('big');
const hitsAfterFirst = PAGE_HITS;
await dzLoadRecentUploads('big');
t('D18 a second call is served from cache, not re-queried', PAGE_HITS, hitsAfterFirst);

// -- 9. An unknown table degrades quietly -------------------------------
reset();
r = await dzLoadRecentUploads('not_in_uh_sources');
t('D19 a table missing from UH_SOURCES returns [] without throwing', r.length, 0);

console.log(JSON.stringify(out));
})();
'''

harness = harness.replace('__LOADER__', LOADER)
hp = os.path.join(SP, 'test_v1092_rail.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', hp], capture_output=True, text=True)
if r.returncode != 0:
    print('  FAIL  rail harness did not run:\n' + (r.stderr or '')[:2500]); F += 1; fails.append('harness')
else:
    try: rows = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  rail harness unparseable: %s\n%s' % (e, r.stdout[:800])); F += 1; fails.append('harness parse'); rows = []
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else ('got ' + row['got'] + ' want ' + row['want']))


# -- E. Sweep: no OTHER rail loader still samples rows --------------------
print('\nE. the same mistake is not hiding in the rail loaders')

for name in ['dzLoadRecentForDz', 'dzLoadRecentUploads']:
    body = fn(name)
    if not body:
        ok(False, '%s located' % name); continue
    bare = [x for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', strip_comments(body)) if int(x) > 1]
    ok(not bare, '%s has no multi-row .limit() sample' % name, bare)

# Guard the sweep: it must be able to SEE a limit when one is there, or it
# passes vacuously (the v10.20 masking class).
ok(re.findall(r'\.limit\(\s*(\d+)\s*\)', 'x.limit(4000)') == ['4000'],
   'the sweep can detect a planted .limit(4000)')
# A .limit(1) is a deliberate newest-row probe, not a sample - keep it legal.
ok([x for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', 'x.limit(1)') if int(x) > 1] == [],
   'the sweep allows a .limit(1) newest-row probe')
# And that it does not pass just because the stripper blanked everything.
ok('.range(' in strip_comments(fn('dzLoadRecentUploads')),
   'the sweep ran against real code, not a blanked body')


# -- F. The probes v10.92 triaged, FIXED in v10.95 ------------------------
# refreshUploadDataRanges carried the same truncation shape in several more
# places. All were real, all were a DIFFERENT symptom from what Jason
# reported (a narrower audit window / a possibly-missed region, not a wrong
# number on the rail), so v10.92 deliberately did not touch them and instead
# asserted the KNOWN SET of limit values here, "so a fourth cannot blend in".
#
# ⚠ It already had. The Walmart gap audit ALSO used .limit(500), so the set
# collapsed it into findWeeklyGaps' entry and this guard reported THREE
# probes when there were four - and the fourth ordered ASCENDING, so it read
# the OLDEST rows in its window and a missing recent week could never be
# flagged. v10.95 removed all four.
#
# The lesson is pinned below rather than written down: count OCCURRENCES,
# never distinct values. A de-duplicating sweep can hide a whole site.
print('\nF. the truncating freshness probes are gone (fixed in v10.95)')

RUDR = strip_comments(fn('refreshUploadDataRanges'))
rudr_limits = [int(x) for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', RUDR) if int(x) > 1]
ok(rudr_limits == [],
   'no multi-row row window survives in refreshUploadDataRanges (was 10, 200, 500, 500)',
   rudr_limits)
ok(not re.findall(r'\.limit\(\s*([A-Za-z_][^)]*)\)', RUDR),
   'and none with a computed size either',
   re.findall(r'\.limit\(\s*([A-Za-z_][^)]*)\)', RUDR))
for _ident in ['seRows', 'euRows', 'fiRows', 'allWm']:
    ok(_ident not in RUDR,
       'the old row-sample variable %s is gone, so a renamed probe cannot hide' % _ident)

# The replacement shape is the one v10.89 already used per SQP view: one
# .eq() + .limit(1) probe per region, so the SERVER picks the max and there
# is no row window to truncate.
ok(".eq('region', region)" in RUDR, 'the per-region probe filters with .eq(region)')
_probe = RUDR[RUDR.index('latestDateForRegion = async'):] if 'latestDateForRegion = async' in RUDR else ''
_probe = _probe[:_probe.index('latestUploadedAt')] if 'latestUploadedAt' in _probe else _probe
ok('.limit(1)' in _probe, '...and takes exactly ONE row per region')
ok('{ ascending: false }' in _probe, '...newest-first, so that one row IS the max')
ok('.range(' in RUDR, 'the 26-week gap audit pages with .range() (Architecture Rule #4)')
ok('distinctColumnValues' in RUDR,
   'the region list is read from the data, not hardcoded')

# Vacuity guards. A sweep that cannot SEE a limit passes for the wrong
# reason (the v10.20 masking class), and one run against a blanked body
# passes for no reason at all.
ok([int(x) for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', 'x.limit(500)') if int(x) > 1] == [500],
   'the sweep can still detect a planted .limit(500)')
ok(len([x for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', 'a.limit(500) b.limit(500)') if int(x) > 1]) == 2,
   'and detects BOTH probes when two share one limit value - the blind spot above')
ok([x for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', 'x.limit(1)') if int(x) > 1] == [],
   'the sweep allows a .limit(1) newest-row probe (deliberate, not a sample)')
ok('.limit(1)' in RUDR and 'latestByRegion' in RUDR and len(RUDR) > 10000,
   'the sweep ran against real code, not a blanked body', len(RUDR))

print('\n' + '=' * 62)
print('  v10.92  PASS %d   FAIL %d' % (P, F))
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
