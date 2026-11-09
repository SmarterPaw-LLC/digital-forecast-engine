#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.79 - the Amazon Monthly Inventory Storage Fees uploader.

Jason: "3. Amazon storage fee uploader."

  * A  static: the consolidations are real, the feed is registered everywhere
       a feed has to be registered, and the standing merge audit was done.
  * B  the real parser, sliced: both delimiters, both header spellings, the
       blank-fee-is-null rule, a multi-month file, an unknown column, and the
       wrong-file guard.
  * C  the real write path against a stubbed Supabase: the scoped delete, the
       master_id resolve, and what the status line reports.
  * D  the regression guard: pNum() - the function every other parser here
       uses - really does turn a blank fee into $0.00, which is the v11.72
       defect this table exists to fix.
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
        # A REGEX LITERAL, skipped whole. storageMonth holds /^(\d{4})-(\d{2})/
        # and without this branch those {4} / {2} are counted as braces, so the
        # slice never closes and swallows the next 400 lines of the file.
        if c == "/" and prev in "(,=:[!&|?{};+-*%~^<>":
            k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == "[":
                    while k < n and js[k] != "]":
                        k += 2 if js[k] == "\\" else 1
                if js[k] == "/":
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = "x"
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


def const_obj(name):
    i = js.index("const " + name + " = {")
    return "const " + name + " = " + _bal(js.index("{", i)) + ";"


def const_line(name):
    """A whole `const NAME = ...;` statement, however many lines it spans.

    A line-regex truncated STORAGE_FEE_NUMERIC mid-Set and produced a harness
    that would not parse - a slicer that silently takes half a definition is
    worse than one that throws.
    """
    i = js.index("const " + name)
    k, depth, n = i, 0, len(js)
    while k < n:
        c = js[k]
        if c in "\"'`":
            q = c; k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == ";" and depth == 0:
            return js[i:k + 1]
        elif c == "\n" and depth == 0 and js[i:k].count("=") >= 1:
            return js[i:k]
        k += 1
    raise SystemExit("unterminated const " + name)


NC   = nocomment(js)
PARSE = fn("parseAmazonStorageFees")
WRITE = fn("writeAmazonStorageFees", "async function")
RUDR  = fn("refreshUploadDataRanges", "async function")
MERGE = fn("runMerge", "async function")
# v11.81 - was sliced to the comment that FOLLOWED this group, and the
# reorganisation moved that comment. A group ends at its own boundary:
# the next up-grp, or the close of its section list.
def grp_block(gid):
    a = s.index(chr(60) + 'div class="up-grp" id="%s"' % gid)
    nxt = s.find(chr(60) + 'div class="up-grp" id="', a + 10)
    end = s.find(chr(60) + '/div' + chr(62) + chr(10) + '      ' + chr(60) + '/div' + chr(62), a)
    b = min(x for x in (nxt, end) if x > a)
    return s[a:b]
GRP   = grp_block("grp-amz-storage")

# ---------------------------------------------------------------------------
print("A. static - consolidated, registered, and audited")
# ---------------------------------------------------------------------------
eq("A1  parseDelimited declared exactly once", NC.count("function parseDelimited("), 1)
ok("return parseDelimited(line, ',');" in NC,
   "A2  parseCSV keeps its signature and delegates - ~100 call sites untouched")
eq("A3  sniffDelimiter declared exactly once", NC.count("function sniffDelimiter("), 1)
eq("A4  hdrNorm declared exactly once", NC.count("const hdrNorm"), 1)
ok("_chewyCatNorm" not in NC,
   "A5  /!\\ the old Chewy-named normaliser is GONE, not left beside the new one")
ok("sniffDelimiter(lines[i])" in NC,
   "A6  /!\\ parseChewyCatalog converted in the same commit (rule #5)")
eq("A7  ...and it has no inline tabs-vs-commas left",
   nocomment(fn("parseChewyCatalog", "async function")).count("match(/,/g)"), 0)

# The feed has to be registered everywhere a feed is registered, or it is
# invisible on the rail, the grid and Upload History (the v10.86 defect).
ok("amazon_storage_fees:" in const_obj("UH_SOURCES"),
   "A8  /!\\ registered in UH_SOURCES - rail, coverage grid AND Upload History")
ok("month_of_charge" in const_obj("UH_SOURCES").split("amazon_storage_fees:")[1][:400],
   "A9  ...with its real date field, so the grid measures the right column")
ok("setLast('last-amz-storage-grp'" in NC,
   "A10 the group rollup is written")
eq("A11 ...with its date / Never pair",
   nocomment(RUDR).count("setLast('last-amz-storage-grp'"), 3)

# The standing merge audit.
ok("reassignMasterId('amazon_storage_fees')" in NC,
   "A12 /!\\ MERGE AUDIT: a product merge reassigns the storage rows")
ok("amazon_storage_fees" in nocomment(MERGE).split("This cannot be undone")[0],
   "A13 /!\\ ...and the confirm dialog says so, rather than under-stating it")

# The card.
eq("A14 the group exists exactly once", s.count('id="grp-amz-storage"'), 1)
ok('class="dz"' in GRP and 'type="file"' in GRP,
   "A15 this one IS a dropzone - unlike the v11.78 GA4 row, it takes a file")
ok("multiple" in GRP, "A16 ...and accepts several, so 13 months backfill in one drop")
ok("handleAmazonStorageFeeUpload(this)" in GRP, "A17 wired to its handler")
eq("A18 the status element exists once", s.count('id="st-amz-storage"'), 1)
eq("A19 the freshness element exists once", s.count('id="last-amz-storage"'), 1)
ok("<a " in GRP and "reportcentral" in GRP,
   "A20 rule 1a: the report link is an affordance, not a label inside a title=")

# The whole point: a blank fee must not become zero.
ok("pNum(" not in nocomment(PARSE),
   "A21 /!\\ the parser does NOT use pNum - it returns 0 for a blank (D1)")
ok("storageNum(" in nocomment(PARSE), "A22 ...it uses storageNum")
# v11.87 - the real export writes `--` for a blank too, so the guard covers
# both. Pinned on BEHAVIOUR rather than on the literal, which is what went
# stale here.
_num = nocomment(fn("storageNum"))
ok("return null" in _num and "t === ''" in _num,
   "A23 /!\\ and storageNum returns NULL for an empty cell")
ok("'--'" in _num,
   "A23b /!\\ ...and for `--`, which is how THIS report writes a blank")

# The six columns a real September 2026 export (2,357 rows, US + CA) settled.
_cols = const_obj("STORAGE_FEE_COLS")
for _f in ("total_incentive_fee_amount", "breakdown_incentive_fee_amount",
           "est_base_msf", "est_sus", "avg_qty_for_sus", "est_vol_for_sus"):
    ok(_f + ":" in _cols, "A23c the real column %s is mapped" % _f)
ok("total_incremental_fee:" not in _cols
   and "breakdown_incentive_fee_discount:" not in _cols,
   "A23d /!\\ ...and my two GUESSED names are gone, not left beside them")
_numset = js[js.index("const STORAGE_FEE_NUMERIC"):]
_numset = _numset[:_numset.index("]);") + 3]
ok("breakdown_incentive_fee_amount" not in _numset,
   "A23e /!\\ breakdown_incentive_fee_amount is NOT numeric - it reads "
   "`COVID-19:0.0057`, and as a number it would be null on every row that has one")
for _f in ("est_base_msf", "est_sus"):
    ok(_f in _numset, "A23f %s IS numeric" % _f)
ok("storageText(" in nocomment(fn("parseAmazonStorageFees")),
   "A23g text cells go through storageText - the `--` and the Excel apostrophe")

ok("estimated_monthly_storage_fee" in const_obj("STORAGE_FEE_COLS"),
   "A24 the fee column is in the map")
ok("fba_storage_fee_total" in js,
   "A25 the OLD weekly column still exists - this release adds, it does not cut")

m = re.search(r">v(\d+\.\d+) · [\d-]+<", s)
cl = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
cm = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cl)
eq("A26 /!\\ the version chip AGREES with CLAUDE.md",
   m.group(1) if m else None, cm.group(1) if cm else None)
ok(os.path.exists(os.path.join(ROOT, "supabase_v11_79_storage_fees.sql")),
   "A27 the migration Jason has to run is in the repo")
ok("supabase_v11_79_storage_fees.sql" in js,
   "A28 /!\\ ...and the uploader NAMES it when the table is missing")

# ---------------------------------------------------------------------------
print("\nB. the real parser, sliced")
# ---------------------------------------------------------------------------
HDR_U = ("month_of_charge\tasin\tfnsku\tsku\tproduct_name\tcountry_code\tfulfillment_center\t"
         "average_quantity_on_hand\titem_volume\tvolume_units\tbase_rate\tcurrency\t"
         "estimated_monthly_storage_fee")
ROW_U = "2026-10\tB08W24837G\tX00ABC\tMEOW-1\tMeowi Waui\tUS\tLAS1\t120.5\t0.08\tcubic feet\t2.40\tUSD\t231.55"
ROW_U2 = "2026-10\tB0HBR9JB81\tX00DEF\tMEOW-2\tCatnip Cigar\tUS\tPHX7\t40\t0.05\tcubic feet\t2.40\tUSD\t"
ROW_U3 = "2026-09\tB08W24837G\tX00ABC\tMEOW-1\tMeowi Waui\tCA\tYYZ1\t10\t0.08\tcubic feet\t2.40\tCAD\t9.10"

HDR_H = ('"month-of-charge","asin","fnsku","sku","product-name","country-code",'
         '"fulfillment-center","average-quantity-on-hand","estimated-monthly-storage-fee",'
         '"some-new-column"')
ROW_H = '"September 2026","B08W24837G","X00ABC","MEOW-1","Meowi Waui","US","LAS1","99","12.34","surprise"'

B = r"""
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}
function clean(s){ return s?s.replace(/^"|"$/g,'').trim():''; }
__DELIM__
__SNIFF__
__NORM__
__COLS__
__NUMSET__
__NUM__
__MNAMES__
__MONTH__
__MEND__
__PARSE__

const TSV = __TSV__;
const CSV = __CSV__;

const a = parseAmazonStorageFees(TSV);
t('B1  a TAB-delimited file parses', a.rows.length, 3);
t('B2  the fee lands as a number', a.rows[0].estimated_monthly_storage_fee, 231.55);
t('B3  /!\\ a BLANK fee is null, not 0 - the v11.72 defect at the parser',
  a.rows[1].estimated_monthly_storage_fee, null);
t('B4  the month comes from the file', a.rows[0].month_of_charge, '2026-10');
t('B5  charge_date is the DERIVED last day of that month', a.rows[0].charge_date, '2026-10-31');
t('B6  country_code lands under the app\'s own word', a.rows[0].region, 'US');
t('B7  the fulfilment centre is kept - it is part of the unique key',
  a.rows[0].fulfillment_center, 'LAS1');
t('B8  /!\\ a multi-month, multi-market file reports every pair it covers',
  a.months.sort(), ['CA|2026-09', 'US|2026-10']);
t('B9  nothing unknown in a file we fully recognise', a.unknown, []);
t('B10 text columns are not coerced to numbers', a.rows[0].volume_units, 'cubic feet');
t('B11 a missing optional column is null, not undefined',
  a.rows[0].dangerous_goods_storage_type, null);

const b = parseAmazonStorageFees(CSV);
t('B12 /!\\ a COMMA file with HYPHENATED headers parses the same', b.rows.length, 1);
t('B13 ...and "September 2026" resolves to a month key', b.rows[0].month_of_charge, '2026-09');
t('B14 ...and its month end is derived too', b.rows[0].charge_date, '2026-09-30');
t('B15 /!\\ an unrecognised column is NAMED, not swallowed', b.unknown, ['some-new-column']);
t('B16 ...and its value is kept in extra', b.rows[0].extra, { somenewcolumn: 'surprise' });

// The wrong-file guard, before anything is written.
let err = null;
try { parseAmazonStorageFees('asin,units\nB08W24837G,5'); } catch (e) { err = e.message; }
t('B17 /!\\ a file with no fee column is REFUSED, not half-loaded',
  /Wrong file/.test(err || ''), true);
t('B18 ...and the message names where to get the right one',
  /Monthly Inventory Storage Fees/.test(err || ''), true);

err = null;
try { parseAmazonStorageFees(''); } catch (e) { err = e.message; }
t('B19 an empty file is refused', /empty/i.test(err || ''), true);

// Month parsing on its own.
t('B20 YYYY-MM-DD collapses to its month', storageMonth('2026-10-01'), '2026-10');
t('B21 "Oct 2026" works', storageMonth('Oct 2026'), '2026-10');
t('B22 "10/2026" works', storageMonth('10/2026'), '2026-10');
t('B23 junk is null, not a guess', storageMonth('whenever'), null);
t('B24 /!\\ a month end is real calendar maths',
  [storageMonthEnd('2026-02'), storageMonthEnd('2024-02')], ['2026-02-28', '2024-02-29']);

// The delimiter sniff.
t('B25 tabs win when there are more of them', sniffDelimiter('a\tb\tc'), '\t');
t('B26 commas win otherwise', sniffDelimiter('a,b,c'), ',');
t('B27 /!\\ a comma INSIDE a quoted tab field does not flip the sniff',
  sniffDelimiter('a\t"b,c"\td'), '\t');

// The header normaliser.
t('B28 three spellings are one key',
  [hdrNorm('Month of Charge'), hdrNorm('month-of-charge'), hdrNorm('month_of_charge')],
  ['monthofcharge', 'monthofcharge', 'monthofcharge']);

console.log(JSON.stringify(out));
"""
B = (B.replace("__DELIM__", fn("parseDelimited"))
      .replace("__SNIFF__", fn("sniffDelimiter"))
      .replace("__NORM__", const_line("hdrNorm"))
      .replace("__COLS__", const_obj("STORAGE_FEE_COLS"))
      .replace("__NUMSET__", const_line("STORAGE_FEE_NUMERIC"))
      .replace("__NUM__", fn("storageText") + chr(10) + fn("storageNum"))
      .replace("__MNAMES__", const_line("STORAGE_MONTH_NAMES"))
      .replace("__MONTH__", fn("storageMonth"))
      .replace("__MEND__", fn("storageMonthEnd"))
      .replace("__PARSE__", PARSE)
      .replace("__TSV__", json.dumps("\n".join([HDR_U, ROW_U, ROW_U2, ROW_U3])))
      .replace("__CSV__", json.dumps("\n".join([HDR_H, ROW_H]))))
p = os.path.join(SP, "_v1179_b.js")
io.open(p, "w", encoding="utf-8", newline="").write(B)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-3000:]); print(r.stderr[-3000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ---------------------------------------------------------------------------
print("\nC. the real write path, against a stubbed Supabase")
# ---------------------------------------------------------------------------
C = r"""
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}
function clean(s){ return s?s.replace(/^"|"$/g,'').trim():''; }
__DELIM__
__SNIFF__
__NORM__
__COLS__
__NUMSET__
__NUM__
__MNAMES__
__MONTH__
__MEND__
__PARSE__

let DELETES = [], INSERTED = [], TABLE_MISSING = false;
function builder(table) {
  const b = { table, _f: [] };
  b.select = () => b;
  b.eq = (c, v) => { b._f.push([c, v]); return b; };
  b.delete = () => {
    const d = { _f: [] };
    d.eq = (c, v) => { d._f.push([c, v]); return d; };
    d.then = (res) => {
      DELETES.push({ table, filters: d._f.slice() });
      return Promise.resolve(res(TABLE_MISSING
        ? { error: { message: 'relation "public.amazon_storage_fees" does not exist' } }
        : { error: null }));
    };
    return d;
  };
  b.insert = (rows) => ({ then: (res) => { INSERTED.push(...rows); return Promise.resolve(res({ error: null })); } });
  return b;
}
async function getSB() { return { from: (t) => builder(t) }; }
let allProducts = [
  { asin: 'B08W24837G', master_id: 'SP-0001' },
  { asin: 'b0hbr9jb81', master_id: 'SP-0002' },
];

__WRITE__

const TSV = __TSV__;

(async () => {
  const res = await writeAmazonStorageFees(parseAmazonStorageFees(TSV));
  t('C1  every row is inserted', res.rows, 3);
  t('C2  /!\\ the delete is SCOPED to the (region, month) pairs in the file',
    DELETES.map(d => d.filters).sort(),
    [[['region','CA'],['month_of_charge','2026-09']],
     [['region','US'],['month_of_charge','2026-10']]].sort());
  t('C3  ...so no other month or market is touched', DELETES.length, 2);
  t('C4  master_id resolves off the catalog', INSERTED[0].master_id, 'SP-0001');
  t('C5  /!\\ the ASIN match is case-insensitive, as the catalog is not clean',
    INSERTED[1].master_id, 'SP-0002');
  t('C6  an unknown ASIN is null, not dropped and not invented',
    res.matched, 3);

  // A missing table names the migration rather than failing opaquely.
  DELETES = []; INSERTED = []; TABLE_MISSING = true;
  let err = null;
  try { await writeAmazonStorageFees(parseAmazonStorageFees(TSV)); } catch (e) { err = e.message; }
  t('C7  /!\\ a missing table names the migration file',
    /supabase_v11_79_storage_fees\.sql/.test(err || ''), true);
  t('C8  ...and nothing was inserted', INSERTED.length, 0);

  console.log(JSON.stringify(out));
})();
"""
C = (C.replace("__DELIM__", fn("parseDelimited"))
      .replace("__SNIFF__", fn("sniffDelimiter"))
      .replace("__NORM__", const_line("hdrNorm"))
      .replace("__COLS__", const_obj("STORAGE_FEE_COLS"))
      .replace("__NUMSET__", const_line("STORAGE_FEE_NUMERIC"))
      .replace("__NUM__", fn("storageText") + chr(10) + fn("storageNum"))
      .replace("__MNAMES__", const_line("STORAGE_MONTH_NAMES"))
      .replace("__MONTH__", fn("storageMonth"))
      .replace("__MEND__", fn("storageMonthEnd"))
      .replace("__PARSE__", PARSE)
      .replace("__WRITE__", WRITE)
      .replace("__TSV__", json.dumps("\n".join([HDR_U, ROW_U, ROW_U2, ROW_U3]))))
p = os.path.join(SP, "_v1179_c.js")
io.open(p, "w", encoding="utf-8", newline="").write(C)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-3000:]); print(r.stderr[-3000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ---------------------------------------------------------------------------
print("\nD. the regression guard - pNum really would have reported $0.00")
# ---------------------------------------------------------------------------
D = r"""
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}
__PNUM__
__NUM__

// Every other parser in this file reads numbers with pNum. On a fee column
// that is the v11.72 defect: a month Amazon did not report reads as a month
// Amazon did not charge for.
t('D1  /!\\ pNum turns a blank fee into 0.00 - the defect, reproduced',
  [pNum(''), pNum('   '), pNum(null)], [0, 0, 0]);
t('D2  ...and storageNum does not', [storageNum(''), storageNum('   '), storageNum(null)],
  [null, null, null]);
t('D3  both still read a real figure the same way',
  [pNum('231.55'), storageNum('231.55')], [231.55, 231.55]);
// pNum strips quotes, commas and whitespace but NOT a currency symbol, so
// parseFloat('$1410.88') is NaN and it returns 0. A second way the same
// column could have read as "charged nothing". storageNum strips '$' for
// exactly this reason.
t('D4  /!\\ pNum returns 0 for a $-formatted figure; storageNum reads it',
  [pNum('$1,410.88'), storageNum('$1,410.88')], [0, 1410.88]);
t('D5  /!\\ a real zero is still a zero, not a null',
  storageNum('0'), 0);
t('D6  junk is null rather than a silent 0', storageNum('n/a'), null);

console.log(JSON.stringify(out));
"""
PNUM = re.search(r"(?m)^function pNum\(s\)\{.*$", js).group(0)
D = D.replace("__PNUM__", PNUM).replace("__NUM__", fn("storageText") + chr(10) + fn("storageNum"))
p = os.path.join(SP, "_v1179_d.js")
io.open(p, "w", encoding="utf-8", newline="").write(D)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-2000:]); print(r.stderr[-2000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
