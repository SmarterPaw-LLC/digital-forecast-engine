# -*- coding: utf-8 -*-
r"""v10.95 - the Uploads freshness probes read ROW windows and called them
date windows / region lists.

refreshUploadDataRanges carried FOUR newest-N-rows samples, each of which
then derived a per-region or per-week answer from whatever rows happened to
fit. v10.92 triaged three of them and deliberately left them alone (a
different symptom from the rail bug it was fixing). This is that change.

  1. findWeeklyGaps  .limit(500)  - sku_economics holds ~500 ASINs per week,
     so 500 newest rows cover ONE week and the advertised "last 26 weeks"
     gap audit silently inspected a one-week window. Under-reports gaps.
  2. sku_economics / _eu  .limit(200)  "latest week per region" - 200 newest
     rows can all belong to one week, so a region that skipped the newest
     week read as having NO DATA AT ALL.
  3. fba_inventory_snapshots  .limit(10)  "latest per region" - the most
     fragile; ten rows on a one-row-per-ASIN-per-snapshot table.
  4. walmart_sales_weekly  .order(ASC).limit(500)  - the FOURTH, which hid
     from the v10.92 section-F guard because that guard asserted the SET of
     limit values, so this 500 and findWeeklyGaps' 500 collapsed into one
     entry. ASCENDING, so it read the OLDEST rows in the window and a
     missing RECENT week could never be flagged.

And the one that made all of this moot: findWeeklyGaps referenced `sb`,
which was declared `const sb = await getSB()` INSIDE the try block - a
nested block scope the helper could not see. Every call threw
ReferenceError into its own catch, so the v8.72 gap audit has reported "no
gaps" for every table since the day it shipped. The v10.8
called-but-undefined class: valid JavaScript, clean `node --check`, dead at
runtime.

Second dead path, same audit: the Amazon US/CA gap chip was appended to
`last-amz-sales-grp` BEFORE the Amazon group rollup set that element's
textContent, which wipes its children. Even a working audit could not have
shown on that card.

Guarantees pinned here:
  1. no multi-row row window survives anywhere in refreshUploadDataRanges
  2. a region that skipped the newest week reports ITS OWN latest, and the
     pre-v10.95 path really did drop it
  3. the 26-week gap audit really reads 26 weeks, and really did not
  4. the region SET comes from the data, so a new region needs no code change
  5. the printed format per card is unchanged
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
    declaration has one - the v10.85 trap."""
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

def strip_comments(src):
    """Drop // line comments and /* */ blocks.

    Every one of the four fixes NAMES its old probe in a comment explaining
    why it was wrong, so a naive grep matches forever and the guard can never
    go green - the v10.90 prose-in-source class. Assert on live code only.
    """
    src = re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', src)

RUDR = fn('refreshUploadDataRanges')
CODE = strip_comments(RUDR)


# -- A. Every row window is gone -------------------------------------------
print('\nA. no newest-N-rows sample survives')

ok(bool(RUDR), 'refreshUploadDataRanges located')
ok(re.search(r'async\s+function\s+refreshUploadDataRanges', JS) is not None,
   'still async (every probe in it is awaited)')

bare = sorted({int(x) for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', CODE) if int(x) > 1})
ok(bare == [],
   'no multi-row .limit(N) survives in live code (was 10, 200, 500, 500)', bare)
ok(not re.findall(r'\.limit\(\s*([A-Za-z_][^)]*)\)', CODE),
   'no .limit() with a computed size either',
   re.findall(r'\.limit\(\s*([A-Za-z_][^)]*)\)', CODE))
# The four identifiers the old samples bound their rows to must all be gone,
# so a resurrected probe cannot hide behind a renamed limit.
for ident in ['seRows', 'euRows', 'fiRows', 'allWm']:
    ok(ident not in CODE, 'the old row-sample variable %s is gone' % ident)

# Vacuity guards. A sweep that cannot SEE a limit passes for the wrong
# reason - the v10.20 masking class - and one run against a blanked body
# passes for no reason at all.
ok([int(x) for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', 'x.limit(500)') if int(x) > 1] == [500],
   'the sweep can still detect a planted .limit(500)')
ok([int(x) for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', 'x.limit(10)') if int(x) > 1] == [10],
   'the sweep can still detect a planted .limit(10)')
ok([x for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', 'x.limit(1)') if int(x) > 1] == [],
   'the sweep allows a .limit(1) newest-row probe (deliberate, not a sample)')
ok('.range(' in CODE and 'latestByRegion' in CODE and len(CODE) > 10000,
   'strip_comments kept the real code - not a vacuous pass', len(CODE))

# ...and the comments naming the old bugs must SURVIVE, or the next person
# "optimises" the walks back into one capped request (the v10.92 lesson).
for needle in ['.limit(500)', '.limit(200)', '.limit(10)', 'ASCENDING']:
    ok(needle in RUDR, 'the comment naming the old `%s` probe is still there' % needle)


# -- B. `sb` is reachable from the helpers ---------------------------------
print('\nB. the gap audit can actually run')

ok('let sb = null;' in CODE, '`sb` is declared at FUNCTION scope')
ok('const sb = await getSB()' not in CODE,
   'no block-scoped `const sb` re-declaration came back')
ok(len(re.findall(r'(?<!\w)sb = await getSB\(\)', CODE)) == 1,
   'exactly one assignment to the hoisted sb',
   re.findall(r'(?<!\w)sb = await getSB\(\)', CODE))
# The declaration must come BEFORE findWeeklyGaps, or the helper closes over
# a TDZ binding and throws the same ReferenceError by a different route.
ok(CODE.index('let sb = null;') < CODE.index('findWeeklyGaps'),
   '`sb` is declared above findWeeklyGaps')


# -- C. The probe shapes --------------------------------------------------
print('\nC. probes ask the SERVER for the max, and the region set for the data')

dcv = CODE[CODE.index('distinctColumnValues = async'):] if 'distinctColumnValues = async' in CODE else ''
dcv = dcv[:dcv.index('regionDisplayOrder')] if 'regionDisplayOrder' in dcv else dcv
ok('.gt(col, last)' in dcv, 'distinctColumnValues keyset-walks with .gt()')
ok('.limit(1)' in dcv, '...one row per round trip, so it cannot truncate')
ok("{ ascending: true }" in dcv, '...ascending, so it starts at the smallest value')

ldr = CODE[CODE.index('latestDateForRegion = async'):] if 'latestDateForRegion = async' in CODE else ''
ldr = ldr[:ldr.index('latestUploadedAt')] if 'latestUploadedAt' in ldr else ldr
ok(".eq('region', region)" in ldr, 'latestDateForRegion filters with .eq(region) (the v10.89 shape)')
ok('.limit(1)' in ldr, '...and takes exactly one row')
ok('{ ascending: false }' in ldr, '...ordered newest-first, so the one row IS the max')

dvw = CODE[CODE.index('distinctValuesInWindow = async'):] if 'distinctValuesInWindow = async' in CODE else ''
dvw = dvw[:dvw.index('distinctColumnValues')] if 'distinctColumnValues' in dvw else dvw
ok('.range(' in dvw, 'distinctValuesInWindow pages with .range() (Architecture Rule #4)')
ok('.gte(col, cutoff)' in dvw, '...bounded by the cutoff')
ok('.lt(col, cursor)' in dvw, '...and keyset-advanced by DATE, not by row offset')
m = re.search(r'const PAGE = (\d+), MAX_PAGES = (\d+)', dvw)
ok(bool(m), 'PAGE / MAX_PAGES declared')
if m:
    ok(int(m.group(1)) <= 1000,
       'PAGE <= 1000 - above the PostgREST cap it would truncate again', int(m.group(1)))
    ok(int(m.group(2)) >= 26, 'MAX_PAGES can cover a 26-week window', int(m.group(2)))
# A Supabase builder is single-use: hoisting it out of the loop would make
# the paging look right and serve the same page twice (the v10.92 trap).
ok('sb.from(table).select(col)' in dvw, 'the query is rebuilt INSIDE the paging loop')
ok(dvw.count('.range(') == 1, 'exactly one .range() call, inside the loop', dvw.count('.range('))
ok('complete' in dvw and 'console.warn' in dvw,
   'a walk that stopped early says so instead of passing for a full window')

# The region list must come from the data, never from a literal.
ok('distinctColumnValues(table, \'region\')' in CODE,
   'the region set is read from the data')
ok(not re.search(r"\[\s*'US'\s*,\s*'CA'", CODE), 'no hardcoded US/CA region array')
ok('AMAZON_BR_REGIONS' in CODE and 'FBA_REGION_OPTIONS' in CODE,
   'display ORDER reuses the app\'s own marketplace ladders (hard rule #1)')
ok(CODE.count('await latestByRegion(') == 3,
   'all three per-region cards route through the ONE walk',
   CODE.count('await latestByRegion('))


# -- D. The chip is appended after the rollup, not before -----------------
print('\nD. the Amazon gap chip is not wiped by the rollup')

roll = CODE.index("setLast('last-amz-sales-grp', `thru Sat")
chip = CODE.index("appendGapChip('last-amz-sales-grp'")
ok(chip > roll, 'appendGapChip runs AFTER the rollup writes textContent', (roll, chip))
ok(CODE.count("appendGapChip('last-amz-sales-grp'") == 1,
   'exactly one chip append for that element',
   CODE.count("appendGapChip('last-amz-sales-grp'"))


# -- E. Drive the REAL function against a stubbed Supabase ----------------
print('\nE. behaviour, against a stub built to Jason\'s shape')

harness = r'''
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

// ── DOM stub. textContent MUST clear children, like the real thing - that
//    is the whole mechanism behind the wiped gap chip.
function mkEl(id) {
  const el = {
    id, _text: '', children: [], style: {}, className: '', title: '',
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); this.children = []; },
    appendChild(c) { this.children.push(c); return c; },
    querySelector(sel) {
      const cls = sel.replace('.', '');
      return this.children.find(c => (c.className || '') === cls) || null;
    },
  };
  return el;
}
const ELS = {};
const document = {
  getElementById: (id) => (ELS[id] || (ELS[id] = mkEl(id))),
  createElement: () => mkEl('new'),
};
function txt(id) { return (ELS[id] || {})._text || ''; }
function chipOn(id) { return ((ELS[id] || {}).children || [])[0] || null; }

// ── the app globals the function reaches for
const AMAZON_BR_REGIONS = [
  { code: 'US' }, { code: 'CA' }, { code: 'MX' }, { code: 'GB' }, { code: 'DE' },
  { code: 'FR' }, { code: 'IT' }, { code: 'ES' }, { code: 'NL' }, { code: 'AU' }, { code: 'JP' },
];
const FBA_REGION_OPTIONS = [{ code: 'US' }, { code: 'CA' }, { code: 'MX' }, { code: 'EU/UK' }];
// yyyyww -> the Saturday of that week. Consecutive codes are exactly 7 days
// apart, which is all the gap arithmetic needs.
function walmartWeekToDate(code) {
  const y = Math.floor(code / 100), w = code % 100;
  const d = new Date(y, 0, 3);
  d.setDate(d.getDate() + (w - 1) * 7);
  return d;
}
function updateShopifyReportLink() {}
function dzRecentInvalidate() {}
function renderAllDzRecentUploads() {}

let WARNED = [];
const _consoleWarn = console.warn;
console.warn = (...a) => { WARNED.push(a.map(String).join(' ')); };

// ── Supabase stub. db-max-rows caps EVERY response at 1000 and does not
//    error - the v10.92 bug - so the stub caps too.
const DB_MAX_ROWS = 1000;
let TABLES = {}, QUERIES = [];

function builder(table) {
  const b = { table, _f: [], _order: null, _asc: true, _from: 0, _to: null };
  b.select = (cols) => { b._cols = cols; return b; };
  b.eq  = (c, v) => { b._f.push(['eq', c, v]);  return b; };
  b.gt  = (c, v) => { b._f.push(['gt', c, v]);  return b; };
  b.lt  = (c, v) => { b._f.push(['lt', c, v]);  return b; };
  b.gte = (c, v) => { b._f.push(['gte', c, v]); return b; };
  b.order = (c, o) => { b._order = c; b._asc = !!(o && o.ascending); return b; };
  b.limit = (n) => { b._from = 0; b._to = n - 1; return b; };
  b.range = (a, z) => { b._from = a; b._to = z; return b; };
  b._exec = async () => {
    QUERIES.push({ table, f: b._f.slice(), order: b._order, asc: b._asc, from: b._from, to: b._to });
    let rows = (TABLES[table] || null);
    if (rows === null) return { data: null, error: { message: 'relation does not exist' } };
    rows = rows.slice();
    for (const [op, c, v] of b._f) {
      if (op === 'eq')  rows = rows.filter(r => r[c] === v);
      if (op === 'gt')  rows = rows.filter(r => r[c] >  v);
      if (op === 'lt')  rows = rows.filter(r => r[c] <  v);
      if (op === 'gte') rows = rows.filter(r => r[c] >= v);
    }
    if (b._order) {
      const c = b._order, sgn = b._asc ? 1 : -1;
      rows.sort((x, y) => (x[c] < y[c] ? -1 : x[c] > y[c] ? 1 : 0) * sgn);
    }
    const to = (b._to == null) ? rows.length - 1 : b._to;
    const want = to - b._from + 1;
    return { data: rows.slice(b._from, b._from + Math.min(want, DB_MAX_ROWS)), error: null };
  };
  b.then = (res, rej) => b._exec().then(res, rej);
  return b;
}
async function getSB() { return { from: (t) => builder(t) }; }

// ── fixture helpers. Weeks are real Mondays relative to TODAY, so the
//    26-week cutoff the code computes at run time always contains them.
function mondaysBack(n) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));   // this week's Monday
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
    d.setDate(d.getDate() - 7);
  }
  return out;                                        // newest first
}
function skuRows(weeks, region, perWeek, uploadedAt) {
  const rows = [];
  for (const w of weeks) for (let i = 0; i < perWeek; i++)
    rows.push({ week_start: w, region, uploaded_at: uploadedAt, asin: 'A' + i });
  return rows;
}

__FN__

(async () => {

// =====================================================================
// 1. Jason's shape: 26 weeks x ~500 ASINs, and CA skipped the newest week
//    AND US is missing one week in the middle.
// =====================================================================
const W = mondaysBack(26);                 // W[0] newest
const GAP = W[8];                          // a genuinely missing US week
const usWeeks = W.filter(w => w !== GAP);
const caWeeks = W.slice(1);                // CA never got the newest week

ELS.__reset = undefined;
for (const k of Object.keys(ELS)) delete ELS[k];
WARNED = []; QUERIES = [];
TABLES = {
  sku_economics: skuRows(usWeeks, 'US', 500, '2026-10-26T12:00:00Z')
           .concat(skuRows(caWeeks, 'CA', 500, '2026-10-25T12:00:00Z')),
  sku_economics_eu: [],
  fba_inventory_snapshots: [],
  walmart_sales_weekly: [],
};
await refreshUploadDataRanges();

const sat = (monday, off) => {
  const d = new Date(monday + 'T00:00:00');
  d.setDate(d.getDate() + off);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

t('E1  BOTH regions report, each with ITS OWN latest week',
  txt('last-sales-skuecon').replace(/ \u00b7 uploaded.*$/, ''),
  `\u{1F4C5} Data US: thru Sat ${sat(W[0], 5)} \u00b7 CA: thru Sat ${sat(W[1], 5)}`);
t('E2  the format is unchanged - emoji, "thru Sat", " \u00b7 " separator',
  /^\u{1F4C5} Data US: thru Sat \d{4}-\d\d-\d\d \u00b7 CA: thru Sat \d{4}-\d\d-\d\d \u00b7 uploaded /u.test(txt('last-sales-skuecon')),
  true);
t('E3  US prints before CA (the marketplace ladder, not the alphabet)',
  txt('last-sales-skuecon').indexOf('US:') < txt('last-sales-skuecon').indexOf('CA:'), true);
t('E4  the function ran to completion - nothing threw into the outer catch',
  WARNED.filter(w => w.startsWith('refreshUploadDataRanges:')), []);

// The gap audit, which has never once run before this release.
const amzChip = chipOn('last-amz-sales-grp');
t('E5  the gap chip EXISTS on the Amazon group card', !!amzChip, true);
t('E6  ...and it survived the rollup writing that element\'s textContent',
  (txt('last-amz-sales-grp').indexOf('thru Sat') === 0), true);
t('E7  it found the planted US gap, and ONLY that one',
  amzChip ? amzChip.title.split('\n').filter(l => /^US: \d{4}/.test(l)) : null, [`US: ${GAP}`]);
// CA is a week behind, and that is NOT a gap: the audit reports missing
// weeks BETWEEN a region's own first and latest week (the v8.72 semantic),
// so a region whose data simply ENDS earlier must not be accused of a hole.
// "CA is behind" is the card LINE's job (E1), not the chip's.
t('E8  a region whose data ends early is NOT reported as a gap',
  amzChip ? amzChip.title.includes(`CA: ${W[0]}`) : null, false);
t('E9  so the chip counts the one real interior gap, and no edge artefacts',
  amzChip ? amzChip.textContent : null, '\u26a0 1 gap');
t('E10 no truncation warning - the full 26-week window was read',
  WARNED.filter(w => w.includes('stopped before the')), []);

// =====================================================================
// 2. The regression guard: the pre-v10.95 path, same fixture.
// =====================================================================
{
  const sb = await getSB();
  const { data: seRows } = await sb.from('sku_economics')
    .select('week_start, region, uploaded_at').order('week_start', { ascending: false }).limit(200);
  const byRegion = {};
  for (const r of seRows) if (!byRegion[r.region]) byRegion[r.region] = r.week_start;
  t('E11 the OLD .limit(200) walk really did see only ONE region',
    Object.keys(byRegion), ['US']);
  t('E12 ...so CA read as having NO DATA AT ALL on that card',
    'CA' in byRegion, false);

  // ...and the old gap audit, from the same rows.
  const cutoff = new Date(); cutoff.setDate(cutoff.getDate() - 26 * 7);
  const cutoffStr = `${cutoff.getFullYear()}-${String(cutoff.getMonth() + 1).padStart(2, '0')}-${String(cutoff.getDate()).padStart(2, '0')}`;
  const { data: old } = await sb.from('sku_economics').select('week_start')
    .gte('week_start', cutoffStr).eq('region', 'US')
    .order('week_start', { ascending: false }).limit(500);
  const oldWeeks = [...new Set(old.map(r => r.week_start))];
  t('E13 the OLD .limit(500) audit saw ONE week of the 26 it advertised',
    oldWeeks.length, 1);
  t('E14 ...so weeks.length < 2 and it returned NO gaps - the planted gap was missed',
    oldWeeks.length < 2, true);
}

// =====================================================================
// 3. The dead-closure guard: the pre-v10.95 scoping really did throw.
// =====================================================================
{
  // Byte-for-byte the old shape: `sb` const-declared inside the try block,
  // referenced from a helper defined at function scope.
  let threw = null, result = null;
  const old = async () => {
    const helper = async () => {
      try { return { got: sb.from('x') }; }
      catch (e) { threw = e.constructor.name; return { missing: [] }; }
    };
    try {
      const sb = await getSB();     // eslint-disable-line no-unused-vars
      result = await helper();
    } catch (_) {}
  };
  await old();
  t('E15 the old block-scoped `sb` threw ReferenceError from the helper', threw, 'ReferenceError');
  t('E16 ...straight into the helper\'s own catch, which returned no gaps',
    result, { missing: [] });
}

// =====================================================================
// 4. A brand-new region appears with no code change.
// =====================================================================
for (const k of Object.keys(ELS)) delete ELS[k];
WARNED = []; QUERIES = [];
TABLES = {
  sku_economics: skuRows([W[0]], 'US', 500, '2026-10-26T12:00:00Z')
           .concat(skuRows([W[0]], 'CA', 500, '2026-10-26T12:00:00Z'))
           .concat(skuRows([W[1]], 'ZZ', 500, '2026-10-26T12:00:00Z')),
  sku_economics_eu: [], fba_inventory_snapshots: [], walmart_sales_weekly: [],
};
await refreshUploadDataRanges();
t('E17 an unrecognised region still appears on the card',
  txt('last-sales-skuecon').includes('ZZ: thru Sat'), true);
t('E18 ...sorted AFTER the known marketplaces, not dropped',
  txt('last-sales-skuecon').indexOf('ZZ:') > txt('last-sales-skuecon').indexOf('CA:'), true);

// =====================================================================
// 5. FBA snapshots - ten rows could never have covered two regions.
// =====================================================================
for (const k of Object.keys(ELS)) delete ELS[k];
WARNED = []; QUERIES = [];
const fba = [];
for (let i = 0; i < 600; i++) fba.push({ snapshot_date: '2026-05-16', region: 'US', asin: 'U' + i });
for (let i = 0; i < 400; i++) fba.push({ snapshot_date: '2026-05-09', region: 'CA', asin: 'C' + i });
TABLES = { sku_economics: [], sku_economics_eu: [], walmart_sales_weekly: [], fba_inventory_snapshots: fba };
await refreshUploadDataRanges();
t('E19 both regions report their own snapshot date',
  txt('last-fba-inv'), '\u{1F4C5} US: 2026-05-16 \u00b7 CA: 2026-05-09');
t('E20 the group label shows the NEWEST across regions',
  txt('last-fba-inv-grp').startsWith('2026-05-16 ('), true);
{
  const sb = await getSB();
  const { data } = await sb.from('fba_inventory_snapshots')
    .select('snapshot_date, region').order('snapshot_date', { ascending: false }).limit(10);
  const byR = {};
  for (const r of data) if (!byR[r.region]) byR[r.region] = r.snapshot_date;
  t('E21 the OLD .limit(10) walk saw ONE region out of two', Object.keys(byR), ['US']);
}
// The exact line from the brief, with both regions on the same date.
for (const k of Object.keys(ELS)) delete ELS[k];
TABLES.fba_inventory_snapshots = fba.map(r => ({ ...r, snapshot_date: '2026-05-16' }));
await refreshUploadDataRanges();
t('E22 the documented line renders byte-for-byte',
  txt('last-fba-inv'), '\u{1F4C5} US: 2026-05-16 \u00b7 CA: 2026-05-16');

// =====================================================================
// 6. EU - six countries sharing one table.
// =====================================================================
for (const k of Object.keys(ELS)) delete ELS[k];
WARNED = []; QUERIES = [];
let eu = [];
for (const [reg, wk] of [['GB', W[0]], ['DE', W[0]], ['FR', W[1]], ['IT', W[2]], ['ES', W[3]], ['NL', W[4]]])
  eu = eu.concat(skuRows([wk], reg, 200, '2026-10-26T12:00:00Z'));
TABLES = { sku_economics: [], fba_inventory_snapshots: [], walmart_sales_weekly: [], sku_economics_eu: eu };
await refreshUploadDataRanges();
t('E23 all six countries are found, four shown + "+2 more" (unchanged shape)',
  /^\u{1F4C5} GB: thru Sat \S+ \u00b7 DE: thru Sat \S+ \u00b7 FR: thru Sat \S+ \u00b7 IT: thru Sat \S+ \+2 more \u00b7 uploaded /u.test(txt('last-sales-skuecon-eu')),
  true);
t('E24 the four shown are the big marketplaces, in ladder order',
  txt('last-sales-skuecon-eu').startsWith('\u{1F4C5} GB:'), true);
{
  const sb = await getSB();
  const { data } = await sb.from('sku_economics_eu')
    .select('week_start, region, uploaded_at').order('week_start', { ascending: false }).limit(200);
  const byEu = {};
  for (const r of data) if (!byEu[r.region]) byEu[r.region] = r.week_start;
  // 200 rows per country, so the 200-row window is filled by the FIRST
  // country at the newest week and the other five are invisible.
  t('E25 the OLD .limit(200) walk saw 1 of the 6 countries', Object.keys(byEu).length, 1);
}

// =====================================================================
// 7. Walmart - the fourth window, and the one that read the OLDEST rows.
// =====================================================================
for (const k of Object.keys(ELS)) delete ELS[k];
WARNED = []; QUERIES = [];
// 26 consecutive week codes ending at the current week, 500 rows each, with
// one RECENT week missing - exactly what an ascending window cannot see.
const cutoffCode = (() => {
  const d = new Date(); d.setDate(d.getDate() - 26 * 7);
  const y = d.getFullYear();
  const w = Math.max(1, Math.ceil((d - new Date(y, 0, 1)) / (7 * 864e5)));
  return y * 100 + w;
})();
const codes = [];
for (let i = 0; i < 26; i++) codes.push(cutoffCode + i);
const WM_GAP = codes[23];                       // near the NEWEST end
const wm = [];
for (const c of codes) {
  if (c === WM_GAP) continue;
  for (let i = 0; i < 500; i++) wm.push({ walmart_calendar_week: c, uploaded_at: '2026-10-26T12:00:00Z', sku: 'S' + i });
}
TABLES = { sku_economics: [], sku_economics_eu: [], fba_inventory_snapshots: [], walmart_sales_weekly: wm };
await refreshUploadDataRanges();
const wmChip = chipOn('last-walmart-sales-grp');
t('E26 the Walmart audit finds the missing RECENT week', !!wmChip, true);
t('E27 ...exactly one gap, not a window artefact',
  wmChip ? wmChip.textContent : null, '\u26a0 1 gap');
t('E28 the group label still reads thru the newest Saturday',
  txt('last-walmart-sales-grp').startsWith('thru Sat '), true);
{
  const sb = await getSB();
  const { data } = await sb.from('walmart_sales_weekly').select('walmart_calendar_week')
    .gte('walmart_calendar_week', cutoffCode)
    .order('walmart_calendar_week', { ascending: true }).limit(500);
  const seen = [...new Set(data.map(r => r.walmart_calendar_week))];
  t('E29 the OLD ASCENDING .limit(500) read only the OLDEST week in the window',
    seen.length, 1);
  t('E30 ...so a missing RECENT week could never be flagged', seen.includes(WM_GAP), false);
}

// =====================================================================
// 8. Paging mechanics, read off the recorded queries.
// =====================================================================
for (const k of Object.keys(ELS)) delete ELS[k];
WARNED = []; QUERIES = [];
TABLES = {
  sku_economics: skuRows(W, 'US', 500, '2026-10-26T12:00:00Z'),
  sku_economics_eu: [], fba_inventory_snapshots: [], walmart_sales_weekly: [],
};
await refreshUploadDataRanges();
const walk = QUERIES.filter(q => q.table === 'sku_economics' && q.to === 999);
t('E31 the 26-week window took MORE than one round trip', walk.length > 1, true);
t('E32 every page is a fresh query with the cutoff re-applied',
  walk.every(q => q.f.some(f => f[0] === 'gte')), true);
t('E33 the region filter rode along on every page of the per-region scan',
  walk.every(q => q.f.some(f => f[0] === 'eq' && f[1] === 'region')), true);
t('E34 the cursor advances - each page asks for strictly older dates',
  walk.slice(1).every((q, i) => {
    const prev = walk[i].f.find(f => f[0] === 'lt');
    const cur  = q.f.find(f => f[0] === 'lt');
    return !!cur && (!prev || cur[2] < prev[2]);
  }), true);
t('E35 no page ever asks for more than 1000 rows',
  walk.every(q => q.to - q.from + 1 <= 1000), true);
t('E36 the whole window was read - every week is accounted for',
  WARNED.filter(w => w.includes('stopped before the')), []);
const probes = QUERIES.filter(q => q.table === 'sku_economics' && q.to === 0 && q.f.some(f => f[0] === 'eq'));
t('E37 the per-region latest probe asks for exactly one row', probes.length >= 1, true);

// =====================================================================
// 9. Degradation: a missing table, and an empty one.
// =====================================================================
for (const k of Object.keys(ELS)) delete ELS[k];
WARNED = [];
TABLES = { sku_economics: [] };          // every other table errors
await refreshUploadDataRanges();
t('E38 an empty sku_economics reports the empty state, not a crash',
  txt('last-sales-skuecon'), '\u{1F4C5} No SKU Economics data loaded yet');
t('E39 a missing table degrades quietly - nothing reached the outer catch',
  WARNED.filter(w => w.startsWith('refreshUploadDataRanges:')), []);
t('E40 ...and the group rollup says Never rather than a bogus date',
  txt('last-amz-sales-grp'), '\u2014 Never');

console.warn = _consoleWarn;
console.log(JSON.stringify(out));
})();
'''

harness = harness.replace('__FN__', RUDR)
hp = os.path.join(SP, 'test_v1095_probes.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', hp], capture_output=True, text=True, encoding='utf-8')
if r.returncode != 0:
    print('  FAIL  probe harness did not run:\n' + (r.stderr or '')[:3000]); F += 1; fails.append('harness')
else:
    try: rows = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  probe harness unparseable: %s\n%s' % (e, r.stdout[:1200])); F += 1; fails.append('harness parse'); rows = []
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else ('got ' + row['got'] + ' want ' + row['want']))


# -- F. The sweep that let the fourth probe hide --------------------------
print('\nF. a de-duplicating sweep can hide a whole site')

# v10.92 section F asserted `sorted(set(limits)) == [10, 200, 500]`. The
# Walmart probe ALSO used 500, so the set collapsed it and the guard
# reported three probes when there were four. Pin the lesson: count the
# OCCURRENCES, never the distinct values.
sample = "a.limit(500) b.limit(500) c.limit(10)"
ok(sorted({int(x) for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', sample)}) == [10, 500],
   'a SET-based sweep sees 2 probes in a 3-probe sample (the v10.92 blind spot)')
ok(len([x for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', sample) if int(x) > 1]) == 3,
   'an OCCURRENCE-based sweep sees all 3')

# And the real assertion: zero occurrences, not zero distinct values.
occ = [int(x) for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', CODE) if int(x) > 1]
ok(occ == [], 'refreshUploadDataRanges has ZERO multi-row probe occurrences', occ)

print('\n' + '=' * 62)
print('  v10.95  PASS %d   FAIL %d' % (P, F))
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
