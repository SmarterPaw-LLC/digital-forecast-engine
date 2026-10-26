# -*- coding: utf-8 -*-
r"""v10.96 - the FBA EU card was never refreshed, only written on upload.

The FBA Inventory group has had TWO dropzones since v5.14 - the NA/APAC
gateway (US/CA/MX/AU/JP) and the EU/UK one - and two `dz-last` cards to
match. refreshUploadDataRanges wrote only the first. `last-fba-inv-eu` was
set by handleFbaInventoryUpload alone, so it showed its line until the next
page load and then went blank: the one card in the group that could not
answer "is this stale?", which is the entire job of that strip.

Worse after v10.95, not better: that release made `last-fba-inv` list EVERY
region found in the table, so an EU/UK snapshot was reported on the NA card
while the EU card beside it sat empty.

Both cards now render from the SAME walk through the SAME formatter and
differ only in which regions each claims. The group rollup stays
whole-table, because "when did ANY FBA snapshot land?" is a question
neither card alone can answer.

Pinned here:
  1. refreshUploadDataRanges writes BOTH cards, and the pre-v10.96 path
     really did write neither EU line
  2. the split is by region, with EU_REGIONS reused rather than re-listed
  3. an unrecognised region is never dropped - it stays on the card whose
     dropzone has the region picker
  4. one formatter, so the two cards cannot drift apart
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
    src = re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', src)

RUDR = fn('refreshUploadDataRanges')
CODE = strip_comments(RUDR)


# -- A. Both cards are written, by one formatter --------------------------
print('\nA. the refresh writes both FBA cards')

ok(bool(RUDR), 'refreshUploadDataRanges located')
ok("setLast('last-fba-inv-eu'" in CODE,
   'the EU card is written by the refresh, not only by the upload handler')
ok(CODE.count("setLast('last-fba-inv-eu'") == 1, 'exactly once',
   CODE.count("setLast('last-fba-inv-eu'"))
ok(CODE.count("setLast('last-fba-inv',") == 1, 'and the NA card exactly once',
   CODE.count("setLast('last-fba-inv',"))

# Hard rule #1: one renderer. Two hand-written `${reg}: ${d}` joins would be
# a second copy of the pattern and would drift the moment one is touched.
ok('const fiLine' in CODE, 'a single line formatter exists')
ok(CODE.count('${reg}: ${d}') == 1,
   'the per-region markup is written ONCE, not once per card',
   CODE.count('${reg}: ${d}'))
ok(CODE.count('fiLine(') == 2, 'both cards call it', CODE.count('fiLine('))

# Reuse the app's EU set rather than writing a second one (hard rule #1).
ok('EU_REGIONS' in CODE, 'the EU split reuses EU_REGIONS')
ok(not re.search(r"\[\s*'GB'\s*,\s*'DE'", CODE),
   'no second hand-written EU country list')
ok("reg === 'EU/UK'" in CODE,
   "the EU dropzone's own bucket code is matched explicitly")

# The rollup must stay whole-table: it is the only thing that answers
# "when did ANY FBA snapshot land?".
ok(CODE.count("setLast('last-fba-inv-grp'") == 2,
   'the group rollup still has exactly its date / Never pair',
   CODE.count("setLast('last-fba-inv-grp'"))
ok('fiPairs.map(([, d]) => d).sort().reverse()[0]' in CODE,
   'the rollup reads the newest across BOTH cards, not one of them')

# The markup really does have two cards, or none of this matters.
ok(s.count('id="last-fba-inv-eu"') == 1, 'the EU card element exists in the page')
ok(s.count('id="dz-fba-inv-eu"') == 1, 'and so does the EU dropzone it belongs to')


# -- B. Drive the real function ------------------------------------------
print('\nB. behaviour, against a stubbed Supabase')

harness = r'''
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

function mkEl(id) {
  return {
    id, _text: '', children: [], style: {}, className: '', title: '',
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); this.children = []; },
    appendChild(c) { this.children.push(c); return c; },
    querySelector(sel) {
      const cls = sel.replace('.', '');
      return this.children.find(c => (c.className || '') === cls) || null;
    },
  };
}
const ELS = {};
const document = {
  getElementById: (id) => (ELS[id] || (ELS[id] = mkEl(id))),
  createElement: () => mkEl('new'),
};
function txt(id) { return (ELS[id] || {})._text || ''; }
function reset() { for (const k of Object.keys(ELS)) delete ELS[k]; }

const AMAZON_BR_REGIONS = [
  { code: 'US' }, { code: 'CA' }, { code: 'MX' }, { code: 'GB' }, { code: 'DE' },
  { code: 'FR' }, { code: 'IT' }, { code: 'ES' }, { code: 'NL' }, { code: 'AU' }, { code: 'JP' },
];
const FBA_REGION_OPTIONS = [{ code: 'US' }, { code: 'CA' }, { code: 'MX' }, { code: 'EU/UK' }, { code: 'AU' }, { code: 'JP' }];
const EU_REGIONS = new Set(['GB', 'DE', 'FR', 'IT', 'ES', 'NL']);
function walmartWeekToDate(c) { const y = Math.floor(c / 100), w = c % 100; const d = new Date(y, 0, 3); d.setDate(d.getDate() + (w - 1) * 7); return d; }
function updateShopifyReportLink() {}
function dzRecentInvalidate() {}
function renderAllDzRecentUploads() {}

let WARNED = [];
const _warn = console.warn;
console.warn = (...a) => { WARNED.push(a.map(String).join(' ')); };

const DB_MAX_ROWS = 1000;
let TABLES = {};
function builder(table) {
  const b = { table, _f: [], _order: null, _asc: true, _from: 0, _to: null };
  b.select = () => b;
  b.eq  = (c, v) => { b._f.push(['eq', c, v]);  return b; };
  b.gt  = (c, v) => { b._f.push(['gt', c, v]);  return b; };
  b.lt  = (c, v) => { b._f.push(['lt', c, v]);  return b; };
  b.gte = (c, v) => { b._f.push(['gte', c, v]); return b; };
  b.order = (c, o) => { b._order = c; b._asc = !!(o && o.ascending); return b; };
  b.limit = (n) => { b._from = 0; b._to = n - 1; return b; };
  b.range = (a, z) => { b._from = a; b._to = z; return b; };
  b._exec = async () => {
    let rows = TABLES[table] || null;
    if (rows === null) return { data: null, error: { message: 'missing' } };
    rows = rows.slice();
    for (const [op, c, v] of b._f) {
      if (op === 'eq')  rows = rows.filter(r => r[c] === v);
      if (op === 'gt')  rows = rows.filter(r => r[c] >  v);
      if (op === 'lt')  rows = rows.filter(r => r[c] <  v);
      if (op === 'gte') rows = rows.filter(r => r[c] >= v);
    }
    if (b._order) { const c = b._order, sg = b._asc ? 1 : -1; rows.sort((x, y) => (x[c] < y[c] ? -1 : x[c] > y[c] ? 1 : 0) * sg); }
    const to = (b._to == null) ? rows.length - 1 : b._to;
    const want = to - b._from + 1;
    return { data: rows.slice(b._from, b._from + Math.min(want, DB_MAX_ROWS)), error: null };
  };
  b.then = (res, rej) => b._exec().then(res, rej);
  return b;
}
async function getSB() { return { from: (t) => builder(t) }; }

// One row per ASIN per snapshot - the shape that made .limit(10) hopeless.
function snaps(spec) {
  const rows = [];
  for (const [region, date, n] of spec)
    for (let i = 0; i < (n || 400); i++) rows.push({ snapshot_date: date, region, asin: region + i });
  return rows;
}
function setTables(fba) {
  TABLES = { sku_economics: [], sku_economics_eu: [], walmart_sales_weekly: [], fba_inventory_snapshots: fba };
}

__FN__

(async () => {

// -- 1. Both gateways loaded ------------------------------------------
reset(); WARNED = [];
setTables(snaps([['US', '2026-05-16'], ['CA', '2026-05-16'], ['EU/UK', '2026-05-09']]));
await refreshUploadDataRanges();
t('B1  the NA card lists only the NA/APAC gateway regions',
  txt('last-fba-inv'), '\u{1F4C5} US: 2026-05-16 \u00b7 CA: 2026-05-16');
t('B2  the EU card is populated by the REFRESH - the whole fix',
  txt('last-fba-inv-eu'), '\u{1F4C5} EU/UK: 2026-05-09');
t('B3  the two cards use the same format',
  /^\u{1F4C5} [^:]+: \d{4}-\d\d-\d\d/u.test(txt('last-fba-inv-eu')), true);
t('B4  the group rollup is the newest across BOTH cards',
  txt('last-fba-inv-grp').startsWith('2026-05-16 ('), true);
t('B5  nothing reached the outer catch',
  WARNED.filter(w => w.startsWith('refreshUploadDataRanges:')), []);

// -- 2. The regression guard: v10.95 put EU/UK on the NA card ----------
{
  const pairs = [['US', '2026-05-16'], ['CA', '2026-05-16'], ['EU/UK', '2026-05-09']];
  const v1095Line = '\u{1F4C5} ' + pairs.map(([r, d]) => `${r}: ${d}`).join(' \u00b7 ');
  t('B6  the pre-v10.96 NA card really did swallow the EU snapshot',
    v1095Line.includes('EU/UK'), true);
  t('B7  ...and the EU card really was left blank by the refresh',
    v1095Line === txt('last-fba-inv'), false);
}

// -- 3. EU only: the NA card must say so, not go stale -----------------
reset(); WARNED = [];
setTables(snaps([['EU/UK', '2026-05-09']]));
await refreshUploadDataRanges();
t('B8  EU-only data leaves the NA card on its empty state',
  txt('last-fba-inv'), '\u{1F4C5} No FBA snapshot loaded yet');
t('B9  ...and the EU card reports the snapshot',
  txt('last-fba-inv-eu'), '\u{1F4C5} EU/UK: 2026-05-09');
t('B10 ...and the rollup is the EU date', txt('last-fba-inv-grp').startsWith('2026-05-09 ('), true);

// -- 4. NA only: the EU card gets its OWN empty state ------------------
reset();
setTables(snaps([['US', '2026-05-16']]));
await refreshUploadDataRanges();
t('B11 the EU card says it is empty rather than staying blank',
  txt('last-fba-inv-eu'), '\u{1F4C5} No EU FBA snapshot loaded yet');
t('B12 ...which is distinguishable from the NA empty state',
  txt('last-fba-inv-eu') !== '\u{1F4C5} No FBA snapshot loaded yet', true);

// -- 5. Per-country EU codes land on the EU card -----------------------
reset();
setTables(snaps([['US', '2026-05-16'], ['GB', '2026-05-09'], ['DE', '2026-05-02']]));
await refreshUploadDataRanges();
t('B13 GB and DE are EU, not NA', txt('last-fba-inv'), '\u{1F4C5} US: 2026-05-16');
t('B14 ...and print on the EU card in marketplace order',
  txt('last-fba-inv-eu'), '\u{1F4C5} GB: 2026-05-09 \u00b7 DE: 2026-05-02');

// -- 6. An unrecognised region is never dropped ------------------------
reset();
setTables(snaps([['US', '2026-05-16'], ['ZZ', '2026-05-09'], ['EU/UK', '2026-05-02']]));
await refreshUploadDataRanges();
t('B15 an unknown region stays on the card whose dropzone has the picker',
  txt('last-fba-inv').includes('ZZ: 2026-05-09'), true);
t('B16 ...and does not leak onto the EU card',
  txt('last-fba-inv-eu'), '\u{1F4C5} EU/UK: 2026-05-02');
t('B17 every region in the table is printed SOMEWHERE - none vanishes',
  ['US', 'ZZ', 'EU/UK'].every(r => (txt('last-fba-inv') + txt('last-fba-inv-eu')).includes(r + ':')), true);

// -- 7. Empty + missing table ------------------------------------------
reset(); WARNED = [];
setTables([]);
await refreshUploadDataRanges();
t('B18 an empty table puts BOTH cards on their empty states',
  [txt('last-fba-inv'), txt('last-fba-inv-eu')],
  ['\u{1F4C5} No FBA snapshot loaded yet', '\u{1F4C5} No EU FBA snapshot loaded yet']);
t('B19 ...and the rollup says Never', txt('last-fba-inv-grp'), '\u2014 Never');

reset(); WARNED = [];
TABLES = { sku_economics: [] };          // fba table errors outright
await refreshUploadDataRanges();
t('B20 a missing table degrades quietly', WARNED.filter(w => w.startsWith('refreshUploadDataRanges:')), []);

console.warn = _warn;
console.log(JSON.stringify(out));
})();
'''

harness = harness.replace('__FN__', RUDR)
hp = os.path.join(SP, 'test_v1096_fbaeu.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', hp], capture_output=True, text=True, encoding='utf-8')
if r.returncode != 0:
    print('  FAIL  harness did not run:\n' + (r.stderr or '')[:3000]); F += 1; fails.append('harness')
else:
    try: rows = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  harness unparseable: %s\n%s' % (e, r.stdout[:1200])); F += 1; fails.append('harness parse'); rows = []
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else ('got ' + row['got'] + ' want ' + row['want']))


# -- C. v10.95 did not regress -------------------------------------------
print('\nC. the v10.95 guarantees still hold')

occ = [int(x) for x in re.findall(r'\.limit\(\s*(\d+)\s*\)', CODE) if int(x) > 1]
ok(occ == [], 'still no multi-row row window in refreshUploadDataRanges', occ)
ok(CODE.count('await latestByRegion(') == 3,
   'still three per-region cards through the one walk', CODE.count('await latestByRegion('))
ok('let sb = null;' in CODE, '`sb` is still at function scope')

print('\n' + '=' * 62)
print('  v10.96  PASS %d   FAIL %d' % (P, F))
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
