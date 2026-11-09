#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.78 - the GA4 pull as a REQUEST row on the Uploads page.

Jason: "add it to the report upload section as a request."

  * A  static: the three consolidations are real, and the row is deliberately
       NOT a .dz (a drop target with no file input is the v10.19 dead control,
       and initUploadDropTargets() sweeps every .dz in the document).
  * B  the real ga4SettledThrough, sliced: the ~48h restatement window,
       derived from the pull's own timestamp and never typed.
  * C  the real refreshUploadDataRanges, driven against a stubbed Supabase on
       a pinned clock: the two lines the row writes and the behind chip.
  * D  the regression guard: the pre-v11.78 inline arithmetic run beside the
       shared helper on the same inputs, so "consolidated" means the existing
       consumer's answer did not move.

Nothing here is stubbed that ships: every function under test is sliced out of
index.html, so a moved default fails the suite.
"""
import io, os, re, sys, json, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

passed = failed = 0


def ok(cond, label, extra=None):
    global passed, failed
    if cond:
        passed += 1; print("  ok    %s" % label)
    else:
        failed += 1
        print("  FAIL  %s%s" % (label, ("  got: %s" % ascii(extra)) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


def nocomment(t):
    return re.sub(r"(?m)^\s*//.*$", "", t)


def _bal(i):
    k, n = i, len(js)
    depth, started, prev = 0, False, ""
    while k < n:
        c = js[k]
        if c == "/" and k + 1 < n and js[k + 1] == "/":
            while k < n and js[k] != "\n":
                k += 1
            continue
        if c == "/" and k + 1 < n and js[k + 1] == "*":
            k = js.index("*/", k) + 2
            continue
        if c in "\"'`":
            q = c; k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = "x"
            continue
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise SystemExit("unbalanced at %d" % i)


def fn(name, kw="function"):
    return _bal(js.index(kw + " " + name + "("))


def const_line(name):
    m = re.search(r"(?m)^const " + name + r"\s*=.*$", js)
    if not m:
        raise SystemExit("no const " + name)
    return m.group(0)


NC    = nocomment(js)
SET   = fn("ga4SettledThrough")
COV   = fn("seoTrCoverage")
RUDR  = fn("refreshUploadDataRanges", "async function")
UPL   = s[s.index('<div id="data-view-uploads"'):s.index('<div id="data-view-history"')]
# v11.81 - was sliced to the comment that FOLLOWED this group, and the
# reorganisation moved that comment. A group ends at its own boundary:
# the next up-grp, or the close of its section list.
def grp_block(gid):
    a = s.index(chr(60) + 'div class="up-grp" id="%s"' % gid)
    nxt = s.find(chr(60) + 'div class="up-grp" id="', a + 10)
    end = s.find(chr(60) + '/div' + chr(62) + chr(10) + '      ' + chr(60) + '/div' + chr(62), a)
    b = min(x for x in (nxt, end) if x > a)
    return s[a:b]
GRP   = grp_block("grp-ga4")
BLOCK = RUDR[RUDR.index("ga4_by_date"):RUDR.index("Chewy ")]

# ---------------------------------------------------------------------------
print("A. static - the consolidations, and the row that is not a dropzone")
# ---------------------------------------------------------------------------
eq("A1  ga4SettledThrough declared exactly once",
   NC.count("function ga4SettledThrough("), 1)
eq("A2  GA4_SETTLE_DAYS declared exactly once",
   NC.count("const GA4_SETTLE_DAYS"), 1)
ok("setUTCDate" not in nocomment(COV),
   "A3  /!\\ the OLD inline arithmetic is GONE from seoTrCoverage, not shadowing it")
ok("ga4SettledThrough(" in COV,
   "A4  seoTrCoverage reads the shared rule")
ok("ga4SettledThrough(" in BLOCK,
   "A5  /!\\ ...and so does the Uploads row - two consumers, one definition")
eq("A6  ga4SettledThrough is CALLED exactly twice",
   NC.count("ga4SettledThrough(") - 1, 2)

eq("A7  appendWarnChip declared exactly once",
   NC.count("const appendWarnChip"), 1)
ok("appendWarnChip(groupId," in nocomment(RUDR),
   "A8  appendGapChip delegates to it rather than drawing its own pill")
eq("A9  /!\\ exactly ONE copy of the chip style - one glyph, one pill",
   NC.count("margin-left:8px;padding:2px 7px;background:rgba(232,96,26,.14)"), 1)
# This is the assertion that keeps it converged: a fourth hand-rolled chip in
# this function fails here. The EU gap chip WAS one of those, 68 lines from
# appendGapChip, found by this very assertion on its first run.
eq("A9b /!\\ no chip builds its own style inside the rollup any more",
   nocomment(RUDR).count("chip.style.cssText"), 1)
ok("appendWarnChip('last-ga4-grp'" in NC,
   "A10 the GA4 row is the second consumer of the chip")
ok("appendWarnChip('last-sales-skuecon-eu'" in NC,
   "A10b /!\\ ...and the EU gap chip is the third, converted in this commit")
ok("'gap-chip-eu'" in NC and "el.querySelector('.' + cls)" in NC,
   "A10c the EU copy's idempotence guard came along rather than being dropped")
ok("by country" in NC and "Re-upload EU reports" in NC,
   "A10d ...and its WORDING stayed its own - the pill was shared, not the text")

eq("A11 .up-badge defined exactly once", s.count(".up-badge {"), 1)
eq("A12 ...and used twice - Warehouse converted in the same commit",
   s.count('class="up-badge"'), 2)
ok("font-size:9px;background:rgba(232,96,26,.18)" not in UPL,
   "A13 /!\\ the old inline badge style is gone from the Uploads view, not left "
   "beside the class")
# One copy of that look survives and it was SEEN, not missed: the BUNDLE pill
# in the products table. .up-badge is declared inside the Uploads view's own
# <style>, so it is not in scope there, and that pill carries margin-left:4px
# against this one's 6px - a shared class would move one of them. Promoting it
# to the global sheet is a products-table change, not a GA4 one, and it is on
# the open list rather than done silently.
eq("A13b ...and exactly one copy survives, the one named in CLAUDE.md",
   s.count("font-size:9px;background:rgba(232,96,26,.18)"), 1)
ok("BUNDLE</span>" in s[s.index("font-size:9px;background:rgba(232,96,26,.18)"):][:400],
   "A13c /!\\ the survivor is the BUNDLE pill, not another upload badge")

# The row itself.
eq("A14 grp-ga4 exists exactly once", s.count('id="grp-ga4"'), 1)
eq("A15 ...inside the Uploads view", UPL.count('id="grp-ga4"'), 1)
ok('class="dz"' not in GRP and "dz-ico" not in GRP and "dz-title" not in GRP,
   "A16 /!\\ NO .dz ON THIS ROW - initUploadDropTargets sweeps every .dz and "
   "would wire a drop that cannot land (v10.19)")
ok("input" not in GRP,
   "A17 /!\\ ...and no file input either, so there is nothing to look live")
eq("A18 the freshness element exists once", s.count('id="last-ga4"'), 1)
eq("A19 the rollup element exists once", s.count('id="last-ga4-grp"'), 1)
# v11.82 - the two copy-a-command rows were this release's answer while the
# pull could only run on Jason's machine. They are a button now, and a census
# that asserts the status quo goes red on the release that changes it (the
# v11.63 lesson). What v11.78 was actually FOR survives below: the row has no
# dropzone, no dead input, and no interactive element buried in a title=.
ok("ga4RunPull(this)" in GRP,
   "A20 the row's one action is the Run button (v11.82 replaced the commands)")
eq("A21 ...and no copy-a-command affordance survives beside it",
   GRP.count("copyTextToClipboard("), 0)
ok("<a " not in GRP,
   "A22 rule 1a: nothing INTERACTIVE was collapsed into a title= here")
ok("toggleUploadGroup('grp-ga4')" in GRP,
   "A23 it expands through the same toggle as every other group")
# v11.82 - the badge said RUN BY HAND while it was. It is ONE CLICK now; what
# this assertion is for is that the row carries a badge at all, because in the
# collapsed list every other row means "drop a file here" and this one does not.
ok("up-badge" in GRP,
   "A24 the row still carries a badge - in the collapsed list every other row "
   "means drop a file here, and this one does not")

# Scope: the title names no property, so the query must not pick one.
ok("property" not in BLOCK.split("ga4_snapshots")[0].replace("ga4_by_date", ""),
   "A25 /!\\ the newest-day probe is NOT filtered to one property - the label "
   "names none")

# The chip is appended AFTER the rollup writes textContent (the v10.95 trap:
# textContent assignment drops children, so the reverse order loses the chip).
ok(BLOCK.index("setLast('last-ga4-grp'") < BLOCK.index("appendWarnChip('last-ga4-grp'"),
   "A26 /!\\ the chip is appended AFTER the rollup writes textContent")

ok("GA4_SETTLE_DAYS}" in BLOCK or "${GA4_SETTLE_DAYS}" in BLOCK,
   "A27 the chip's tooltip states the horizon from the constant, not a typed 2")
ok(not re.search(r"\b202[0-9]-[0-9]{2}-[0-9]{2}\b", nocomment(SET)),
   "A28 /!\\ no cutoff DATE is typed into the settle rule")

m = re.search(r">v(\d+\.\d+) · [\d-]+<", s)
cl = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
cm = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cl)
eq("A29 /!\\ the version chip AGREES with CLAUDE.md",
   m.group(1) if m else None, cm.group(1) if cm else None)

# ---------------------------------------------------------------------------
print("\nB. the real ga4SettledThrough, sliced")
# ---------------------------------------------------------------------------
B = r"""
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}
__CONST__
__SET__

t('B1  no pull row: the newest day stands, unqualified',
  ga4SettledThrough(null, '2026-11-06'), '2026-11-06');
t('B2  pulled the same day: two days back',
  ga4SettledThrough('2026-11-06', '2026-11-06'), '2026-11-04');
t('B3  pulled one day later: one day back',
  ga4SettledThrough('2026-11-07', '2026-11-06'), '2026-11-05');
t('B4  pulled two days later: the newest day is settled',
  ga4SettledThrough('2026-11-08', '2026-11-06'), '2026-11-06');
t('B5  pulled long after: never later than the data itself',
  ga4SettledThrough('2026-12-25', '2026-11-06'), '2026-11-06');
t('B6  a timestamptz, not a date, is accepted',
  ga4SettledThrough('2026-11-06T18:20:41.882+00:00', '2026-11-06'), '2026-11-04');
t('B7  /!\\ a month boundary goes back a month, not to day -1',
  ga4SettledThrough('2026-03-01', '2026-03-01'), '2026-02-27');
t('B8  /!\\ a leap day is real arithmetic, not 30-day maths',
  ga4SettledThrough('2024-03-01', '2024-03-01'), '2024-02-28');
t('B9  /!\\ junk in pulled_at does not poison the answer',
  ga4SettledThrough('not-a-date', '2026-11-06'), '2026-11-06');
t('B10 no newest day: nothing to settle',
  ga4SettledThrough('2026-11-06', null), null);
t('B11 both missing', ga4SettledThrough(null, null), null);
t('B12 /!\\ the horizon comes from the constant',
  GA4_SETTLE_DAYS, 2);

console.log(JSON.stringify(out));
"""
B = B.replace("__CONST__", const_line("GA4_SETTLE_DAYS")).replace("__SET__", SET)
p = os.path.join(SP, "_v1178_b.js")
io.open(p, "w", encoding="utf-8", newline="").write(B)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-2000:]); print(r.stderr[-2000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ---------------------------------------------------------------------------
print("\nC. the real refreshUploadDataRanges, clock pinned to 2026-11-09")
# ---------------------------------------------------------------------------
C = r"""
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

// The row reports against TODAY, so the clock is pinned or this suite is a
// countdown (the v11.75 lesson: test_v1147's D2c detonated 11 days in).
const _RealDate = Date;
const PINNED = new _RealDate('2026-11-09T12:00:00').getTime();
class PinnedDate extends _RealDate {
  constructor(...a) { super(...(a.length ? a : [PINNED])); }
  static now() { return PINNED; }
}
globalThis.Date = PinnedDate;

function mkEl(id) {
  return {
    id, _text: '', children: [], style: {}, className: '', title: '',
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); this.children = []; },
    appendChild(c) { this.children.push(c); return c; },
    querySelector(sel) {
      const cls = String(sel).replace('.', '');
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
function chips(id) { return ((ELS[id] || {}).children || []).map(c => c._text); }
function chipTitle(id) { const c = ((ELS[id] || {}).children || [])[0]; return c ? c.title : null; }
function reset() { for (const k of Object.keys(ELS)) delete ELS[k]; }

const AMAZON_BR_REGIONS = [{ code: 'US' }, { code: 'CA' }];
const FBA_REGION_OPTIONS = [{ code: 'US' }, { code: 'CA' }];
const EU_REGIONS = new Set(['GB', 'DE', 'FR', 'IT', 'ES', 'NL']);
function walmartWeekToDate(c) { const y = Math.floor(c / 100), w = c % 100; const d = new Date(y, 0, 3); d.setDate(d.getDate() + (w - 1) * 7); return d; }
function updateShopifyReportLink() {}
function dzRecentInvalidate() {}
function renderAllDzRecentUploads() {}
// v11.81 - the rollup ends by calling the attention strip. Not under
// test here, and no-op'd exactly like the two rail helpers above.
async function renderUploadAttention() {}
__UHS__
__GRAIN__
__OFFSET__
__PEND__
__THRU__

let WARNED = [];
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
let SB_DEAD = false;
async function getSB() {
  if (SB_DEAD) throw new Error('no connection');
  return { from: (t) => builder(t) };
}

function setGa4(days, snaps) {
  TABLES = {
    sku_economics: [], sku_economics_eu: [], walmart_sales_weekly: [],
    fba_inventory_snapshots: [], shopify_sales_daily: [], chewy_forecasts: [],
    ga4_by_date: days, ga4_snapshots: snaps,
  };
}

__RUDR__

(async () => {

// 1. The shape of Jason's own feed on the day he asked: pulled 2026-11-06,
//    data through 2026-11-06, read on 2026-11-09.
reset(); WARNED = [];
setGa4([{ day: '2026-11-04' }, { day: '2026-11-06' }, { day: '2026-10-01' }],
       [{ snapshot_date: '2026-11-06', pulled_at: '2026-11-06T18:20:41Z', loaded_at: '2026-11-06T18:40:00Z' },
        { snapshot_date: '2026-11-02', pulled_at: '2026-11-02T18:20:00Z', loaded_at: '2026-11-02T18:30:00Z' }]);
await refreshUploadDataRanges();
t('C1  the card line carries data thru, settled thru and the pull',
  txt('last-ga4'),
  '\u{1F4C5} Data thru 2026-11-06 · settled thru 2026-11-04 · pulled 2d ago');
// 3d vs 2d is not a bug and not a rounding slip: relDays measures a DAY from
// local midnight, ago measures a TIMESTAMP that landed at 18:20 that evening.
// Two different measures of two different things, side by side on purpose.
t('C2  the rollup is the newest day, its age, and the pull',
  txt('last-ga4-grp'), '2026-11-06 (3d ago) · pulled 2d ago');
t('C3  /!\\ and the chip says it is behind - the whole point of the row',
  chips('last-ga4-grp'), ['⚠ 3 days behind']);
t('C4  the chip derives the horizon rather than restating the label',
  /GA4 settles a day within ~48h/.test(chipTitle('last-ga4-grp') || ''), true);
t('C5  /!\\ the NEWEST snapshot row wins: the 11-02 pull would read 1w ago',
  [/pulled 2d ago/.test(txt('last-ga4-grp')), /1w ago/.test(txt('last-ga4-grp'))],
  [true, false]);
t('C6  nothing reached the outer catch',
  WARNED.filter(w => w.startsWith('refreshUploadDataRanges:')), []);

// 2. Current: pulled today, data through today.
reset();
setGa4([{ day: '2026-11-09' }],
       [{ snapshot_date: '2026-11-09', pulled_at: '2026-11-09T09:00:00Z', loaded_at: '2026-11-09T09:10:00Z' }]);
await refreshUploadDataRanges();
t('C7  /!\\ no chip inside the settle horizon', chips('last-ga4-grp'), []);
t('C8  the settled day is still named, because it DIFFERS',
  txt('last-ga4'),
  '\u{1F4C5} Data thru 2026-11-09 · settled thru 2026-11-07 · pulled 9h ago');
t('C9  the rollup reads today', txt('last-ga4-grp').startsWith('2026-11-09 (today)'), true);

// 3. A pull old enough that the newest day is fully settled: the clause goes
//    away rather than repeating the same date twice (the v11.75 lesson).
reset();
setGa4([{ day: '2026-10-20' }],
       [{ snapshot_date: '2026-10-25', pulled_at: '2026-10-25T10:00:00Z', loaded_at: '2026-10-25T10:00:00Z' }]);
await refreshUploadDataRanges();
t('C10 /!\\ settled == newest prints ONE date, not a second opinion',
  txt('last-ga4'), '\u{1F4C5} Data thru 2026-10-20 · pulled 2w ago');
t('C11 ...and 20 days behind is reported', chips('last-ga4-grp'), ['⚠ 20 days behind']);

// 4. A pull row with no pulled_at falls back to loaded_at rather than printing
//    a dash where a real answer exists.
reset();
setGa4([{ day: '2026-11-08' }],
       [{ snapshot_date: '2026-11-08', pulled_at: null, loaded_at: '2026-11-08T12:00:00Z' }]);
await refreshUploadDataRanges();
t('C12 loaded_at stands in for a missing pulled_at',
  /pulled 1d ago/.test(txt('last-ga4')), true);

// 5. Data but no snapshot row at all: the settle rule cannot run, so the
//    newest day stands unqualified (B1's contract, end to end).
reset();
setGa4([{ day: '2026-11-08' }], []);
await refreshUploadDataRanges();
t('C13 /!\\ no pull row: no settled clause and no invented one',
  txt('last-ga4'), '\u{1F4C5} Data thru 2026-11-08 · pulled —');

// 6. Nothing loaded.
reset();
setGa4([], []);
await refreshUploadDataRanges();
t('C14 empty feed reads Never, not a blank', txt('last-ga4-grp'), '— Never');
t('C15 ...and the card says so too', txt('last-ga4'), '\u{1F4C5} No GA4 data loaded yet');

// 7. The EU gap chip, now drawn by the shared helper. What has to hold is its
//    idempotence guard: it used to check for its own class before appending,
//    and a refresh runs more than once per session.
reset();
setGa4([], []);
TABLES.sku_economics_eu = [
  { region: 'GB', week_start: '2026-09-21', uploaded_at: '2026-09-22T00:00:00Z' },
  { region: 'GB', week_start: '2026-09-28', uploaded_at: '2026-09-29T00:00:00Z' },
  { region: 'GB', week_start: '2026-10-12', uploaded_at: '2026-10-13T00:00:00Z' },
];
await refreshUploadDataRanges();
const euFirst = chips('last-sales-skuecon-eu').length;
// Pinned, so a fixture that stops producing a gap cannot make C17/C18 pass
// vacuously - the v11.63 lesson about a shape-only check.
t('C16b the fixture really does produce one EU gap chip', euFirst, 1);
await refreshUploadDataRanges();
t('C17 /!\\ a second refresh does not double the EU chip - the guard survived',
  chips('last-sales-skuecon-eu').length, euFirst);
t('C18 ...and the chip it draws is the shared pill',
  (ELS['last-sales-skuecon-eu'].children[0] || {}).className || null,
  euFirst ? 'gap-chip-eu' : null);

// 8. The tables are missing entirely (pre-migration database).
reset();
TABLES = { sku_economics: [], sku_economics_eu: [], walmart_sales_weekly: [],
           fba_inventory_snapshots: [], shopify_sales_daily: [], chewy_forecasts: [] };
await refreshUploadDataRanges();
t('C16 a missing ga4_by_date degrades to Never rather than throwing',
  txt('last-ga4-grp'), '— Never');

console.log(JSON.stringify(out));
})();
"""
UH = js[js.index("const UH_SOURCES = {"):]
UH = UH[:UH.index("\n};") + 3]
C = (C.replace("__UHS__", UH)
      .replace("__GRAIN__", fn("uploadGrain"))
      .replace("__OFFSET__", fn("uploadWeekEndOffset"))
      .replace("__PEND__", fn("uploadPeriodEnd"))
      .replace("__THRU__", fn("uploadDataThru"))
      .replace("__RUDR__", const_line("GA4_SETTLE_DAYS") + "\n" + SET + "\n" + RUDR))
p = os.path.join(SP, "_v1178_c.js")
io.open(p, "w", encoding="utf-8", newline="").write(C)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-3000:]); print(r.stderr[-3000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ---------------------------------------------------------------------------
print("\nD. the regression guard - consolidating did not move the old answer")
# ---------------------------------------------------------------------------
D = r"""
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}
__CONST__
__SET__

// The arithmetic exactly as it stood INSIDE seoTrCoverage before v11.78.
function v1173Settled(pulled, newest) {
  let settled = newest;
  if (pulled) {
    const cut = new Date(Date.parse(pulled + 'T00:00:00Z'));
    cut.setUTCDate(cut.getUTCDate() - 2);
    const lastFinal = cut.toISOString().slice(0, 10);
    if (lastFinal < settled) settled = lastFinal;
  }
  return settled;
}

// Pulled dates are DATE-sliced by seoTrCoverage before they reach the rule,
// which is what the old copy assumed, so the comparison is on that shape.
const CASES = [
  [null, '2026-11-06'], ['2026-11-06', '2026-11-06'], ['2026-11-07', '2026-11-06'],
  ['2026-11-08', '2026-11-06'], ['2026-12-25', '2026-11-06'], ['2026-03-01', '2026-03-01'],
  ['2024-03-01', '2024-03-01'], ['2026-01-01', '2026-01-01'], ['2026-11-02', '2026-11-02'],
];
let same = 0, diffs = [];
for (const [p, n] of CASES) {
  const a = v1173Settled(p, n), b = ga4SettledThrough(p, n);
  if (a === b) same++; else diffs.push([p, n, a, b]);
}
t('D1  /!\\ every pre-v11.78 answer is reproduced exactly', diffs, []);
t('D2  ...across the whole battery', same, CASES.length);

// And the guard in the other direction: the OLD copy could not answer the
// question the Uploads row asks, because it had no notion of a missing
// newest day - it returned undefined where the shared rule returns null.
t('D3  the old copy really was narrower than the shared rule',
  [v1173Settled('2026-11-06', null), ga4SettledThrough('2026-11-06', null)],
  [null, null]);

console.log(JSON.stringify(out));
"""
D = D.replace("__CONST__", const_line("GA4_SETTLE_DAYS")).replace("__SET__", SET)
p = os.path.join(SP, "_v1178_d.js")
io.open(p, "w", encoding="utf-8", newline="").write(D)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-2000:]); print(r.stderr[-2000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ---------------------------------------------------------------------------
print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
