#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.91 - the Fees By-product table: the view's columns, a delta, a total.

Jason, on the Fees tab:
  1. "the columns appear/disappear based on the period chosen - the columns
     should be based on the view that is set ... if there is no data for a
     period, i need to know that"
  2. "i want the delta to appear based on the previous period"
  4. "the should be totals for the by product columns"

(1) is v11.72, and I shipped it: that release gated every fee column on the
window's own total, so the table changed shape whenever the period moved.

  * A  static: the window no longer picks the columns, the view does.
  * B  the real amzFeeStamp / amzFeeSumRows: ratios re-derived, nulls not
       counted as zero, and the footer equal to the window when nothing is
       filtered.
  * C  the delta direction registry.
  * D  the picker and the table agree on what exists and what it is called.
  * E  the regression guard: v11.72's gate run beside the shipped one.
"""
import io, os, re, sys, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="",
               errors="replace").read()
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
            prev = "x"; continue
        if c in "\"'`":
            q = c; k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1; prev = "x"; continue
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


def fn(name):
    return _bal(js.index("function " + name + "("))


NC = nocomment(js)
REND = nocomment(fn("renderAmazonFees"))

# ---------------------------------------------------------------------------
print("A. the view picks the columns, not the window")
# ---------------------------------------------------------------------------
# /!\ v11.72's gate, gone. `Math.abs(t[l.k]...) > 0.005` inside the SKU_LINES
# filter is the exact expression that made the column set a function of the
# period.
ok("AMZ_FEE_LINES.filter(l => l.sku)" in REND,
   "A1  /!\\ SKU_LINES takes every line that declares a column")
ok("l.sku && Math.abs(t[l.k] || 0) > 0.005" not in REND,
   "A2  /!\\ ...and the window no longer gates it (the v11.72 defect)")
ok("const VIS = amzFeeVisibleCols();" in REND, "A3  the view's set is read")
ok("ALLCOLS.filter(c => VIS.has(c.k))" in REND, "A4  ...and the table filters to it")

# "if there is no data for a period, i need to know that"
ok("const NOCHARGE = new Set(AMZ_FEE_LINES" in REND,
   "A5  a line charging nothing in this window is identified")
ok("No charge in this window." in REND, "A6  ...said on the column header")
ok("opacity:.45" in REND, "A7  ...which is dimmed")
ok("no charge in this window: ${nzCols.join(', ')}" in REND,
   "A8  ...and named once on the sub-line, not per row")
ok("amzFeeCadenceNote(A, c.k)" in REND,
   "A9  ...with the billing cadence, so a dash is not read as 'nobody pays this'")

# The total row.
ok("<tfoot>" in REND, "A10 the table has a footer")
ok("amzFeeSumRows(list)" in REND,
   "A11 /!\\ the total is over the rows SHOWN, not the window's A.tot")
ok("list.length ? `<tfoot>" in REND,
   "A12 ...and no footer at all when there are no rows")

# Product cannot be hidden: a table of numbers with no name is not a table.
vis = nocomment(fn("amzFeeVisibleCols"))
setc = nocomment(fn("amzFeeSetCol"))
ok("sset.add('name')" in vis and "sset.add('name')" in setc,
   "A13 /!\\ Product is forced on in BOTH the reader and the setter")
ok("catch (e) {}" in vis, "A14 a throwing localStorage yields the default")

# ---------------------------------------------------------------------------
print("\nB. the real amzFeeStamp / amzFeeSumRows")
# ---------------------------------------------------------------------------
B = r"""
const AMZ_FEE_LINES = __LINES__;
const AMZ_FEE_OUTSIDE = __OUTSIDE__;
__STAMP__
__SUM__
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const r2 = v => v == null ? null : Math.round(v * 100) / 100;

const row = (ns, u, fba, aged, held, cuft) => ({
  netSales: ns, units: u, fees: fba + aged,
  fba_fulfillment_fee_total: fba, aged_inventory_fee_total: aged,
  held, cuft,
});
const A = row(100, 10, 30, 5, 100, 2);
const B2 = row(300, 20, 60, 0, null, null);

const tot = amzFeeSumRows([A, B2]);
t('B1  dollars sum', r2(tot.fees), 95);
t('B2  units sum', tot.units, 30);
// /!\ RE-DERIVED, NEVER SUMMED. 35% and 20% do not add to 55%.
t('B3  /!\\ Fee % is re-derived off the summed dollars', r2(tot.feePct), 23.75);
t('B4  /!\\ ...not the sum of the rows\' own percentages',
  r2(tot.feePct) === r2(A.netSales ? 35 + 20 : 0), false);
t('B5  FBA $/u is total fba over total units', r2(tot.fbaPerU), 3);
t('B6  the avoidable bucket sums its own lines', r2(tot.avoidable), 5);

// /!\ A NULL IS "NOT MEASURED", NEVER ZERO.
t('B7  /!\\ a null Held is left out of the sum', tot.held, 100);
t('B8  ...and counted, so the footer can say it is short', tot.heldMissing, 1);
t('B9  the same for Cu Ft', tot.cuft, 2);
t('B10 ...and its own count', tot.cuftMissing, 1);

// Every product unmeasured: the total is NULL, not 0 - so the cell is a dash
// and the "short" mark must not render beside it.
const none = amzFeeSumRows([B2]);
t('B11 /!\\ nothing measured at all answers null, not zero', none.held, null);

// No rows at all must not throw or produce NaN.
const empty = amzFeeSumRows([]);
t('B12 an empty list totals zero', empty.fees, 0);
t('B13 ...with a null ratio rather than NaN', empty.feePct, null);
t('B14 ...and does not throw', true, true);
console.log(JSON.stringify(out));
"""


def const_blk(name):
    i = js.index("const " + name + " = [")
    j = js.index("\n];", i)
    return js[i + len("const " + name + " = "):j + 2]


B = (B.replace("__LINES__", const_blk("AMZ_FEE_LINES"))
      .replace("__OUTSIDE__", const_blk("AMZ_FEE_OUTSIDE"))
      .replace("__STAMP__", fn("amzFeeStamp"))
      .replace("__SUM__", fn("amzFeeSumRows")))
p = os.path.join(SP, "_v1191_b.js")
io.open(p, "w", encoding="utf-8", newline="").write(B)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-2500:]); print(r.stderr[-2500:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ---------------------------------------------------------------------------
print("\nC. which way is good")
# ---------------------------------------------------------------------------
C = r"""
__GOOD__
__PTS__
__DIR__
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
// Fees are COSTS: the default is that a rise is bad.
t('C1  fees: up is bad', amzFeeDeltaDir('fees'), false);
t('C2  a fee line: up is bad', amzFeeDeltaDir('aged_inventory_fee_total'), false);
t('C3  avoidable: up is bad', amzFeeDeltaDir('avoidable'), false);
t('C4  units: up is good', amzFeeDeltaDir('units'), true);
t('C5  net sales: up is good', amzFeeDeltaDir('netSales'), true);
// /!\ v11.03's NO VERDICT. Holding more stock is neither good nor bad, and a
// red chip there would read as "cut it".
t('C6  /!\\ held: no verdict', amzFeeDeltaDir('held'), null);
t('C7  /!\\ cu ft: no verdict', amzFeeDeltaDir('cuft'), null);
t('C8  an unknown key falls back to cost-like', amzFeeDeltaDir('nope'), false);
// /!\ POINTS for a column that IS a percentage.
t('C9  /!\\ Fee % is points', AMZ_FEE_DELTA_PTS.has('feePct'), true);
t('C10 /!\\ FBA % is points', AMZ_FEE_DELTA_PTS.has('fbaPct'), true);
t('C11 a dollar column is not', AMZ_FEE_DELTA_PTS.has('fees'), false);
console.log(JSON.stringify(out));
"""
C = (C.replace("__GOOD__", re.search(r"(?m)^const AMZ_FEE_DELTA_GOOD\s*=.*$", js).group(0))
      .replace("__PTS__", re.search(r"(?m)^const AMZ_FEE_DELTA_PTS\s*=.*$", js).group(0))
      .replace("__DIR__", fn("amzFeeDeltaDir")))
p = os.path.join(SP, "_v1191_c.js")
io.open(p, "w", encoding="utf-8", newline="").write(C)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-2500:]); print(r.stderr[-2500:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ---------------------------------------------------------------------------
print("\nD. the picker and the table cannot disagree")
# ---------------------------------------------------------------------------
# /!\ THE DECLARED PAIR (rule 3a). The picker lists columns and the table
# renders them; two lists means a column can appear in one and not the other.
fixed = re.search(r"const AMZ_FEE_FIXED_COLS = \[([\s\S]*?)\n\];", js).group(1)
pick = [(m.group(1), m.group(2)) for m in
        re.finditer(r"\{\s*k:\s*'([a-z0-9_]+)',\s*h:\s*'([^']*)'\s*\}", fixed)]
# The table's own ALLCOLS, as it declares the same nine.
allc = REND[REND.index("const ALLCOLS = ["):]
tbl = [(m.group(1), m.group(2)) for m in
       re.finditer(r"\{\s*k:\s*'([a-z0-9_]+)',\s*h:\s*'([^']*)'", allc)]
tbl_fixed = [x for x in tbl if x[0] in dict(pick)]
eq("D1  /!\\ the picker's keys match the table's", [k for k, _ in pick], [k for k, _ in tbl_fixed])
eq("D2  /!\\ ...and so do the headers", [h for _, h in pick], [h for _, h in tbl_fixed])

# The fee columns are NOT listed twice: they come from the registry's `sku`.
ok("AMZ_FEE_LINES.filter(l => l.sku).map(l => ({ k: l.k, h: l.sku }))" in js,
   "D3  /!\\ the fee columns are derived from the registry, not re-listed")
ok("function amzFeeAllCols() { return amzFeePickerCols().map(c => c.k); }" in js,
   "D4  ...and the default set is the picker's list, not a third copy")

# The popup this page already has, not an eighth one.
#
# /!\ SLICED BY ITS CLOSING BRACE, not by brace balance. This function is
# almost entirely NESTED TEMPLATE LITERALS, and a matcher that treats a
# backtick as a plain string skips to the wrong one and ends the slice early
# - which is why every assertion in this section failed on its first run
# against code that was present.
# /!\ AND IT IS pnlRenderColsPopup, NOT pnlToggleColsPopup. The latter is a
# 456-character open/close toggle that delegates; all the markup lives in the
# renderer, which is the function the Fees section was added to.
_pi = js.index("function pnlRenderColsPopup(")
pop = nocomment(js[_pi:js.index("\n}", _pi) + 2])
ok("activeSubview !== 'fees' ? ''" in pop,
   "D5  /!\\ the picker lives in the page's EXISTING popup (hard rule #1)")
ok("amzFeePickerCols()" in pop, "D6  ...and reads the one column list")
ok("amzFeeSetCol(" in pop, "D7  ...and writes through the one setter")
# The label also appears inside popup HEADINGS, so count the BUTTONS.
eq("D8  no eighth Customize columns button was added",
   s.count('\U0001f4cb Customize columns</button>'), 7)
# Product's checkbox is disabled, and the reason is on the label.
ok("c.k === 'name' ? 'disabled' : ''" in pop,
   "D9  Product cannot be unticked")
for k in ("opportunities", "breakeven", "fees", "ads"):
    ok("%s: '" % k in pop, "D10 the popup titles the %s sub-view" % k)
# The note must stop claiming Fees has fixed columns.
ok("activeSubview === 'fees' ? 'Fees has its own column set" in pop,
   "D11 /!\\ ...and the note no longer says Fees uses fixed columns")

# ---------------------------------------------------------------------------
print("\nE. the regression guard - v11.72's gate beside the shipped rule")
# ---------------------------------------------------------------------------
E = r"""
const AMZ_FEE_LINES = __LINES__;
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
// A weekly window that charged no monthly line - Jason's actual case.
const tot = { inbound_placement_fee_total: 120, low_inventory_fee_total: 40,
              fba_storage_fee_total: 0, aged_inventory_fee_total: 0,
              removal_fee_total: 0, storage_util_surcharge: 0 };
const v1172 = AMZ_FEE_LINES.filter(l => l.sku && Math.abs(tot[l.k] || 0) > 0.005);
const v1191 = AMZ_FEE_LINES.filter(l => l.sku);
t('E1  /!\\ v11.72 showed 2 fee columns on this window', v1172.length, 2);
t('E2  /!\\ v11.91 shows all 6, whatever the window charged', v1191.length, 6);
// And the window moving changed the SHAPE of the table, which was the bug.
const wide = { inbound_placement_fee_total: 120, low_inventory_fee_total: 40,
               fba_storage_fee_total: 475, aged_inventory_fee_total: 12,
               removal_fee_total: 3, storage_util_surcharge: 1 };
const v1172wide = AMZ_FEE_LINES.filter(l => l.sku && Math.abs(wide[l.k] || 0) > 0.005);
t('E3  /!\\ ...and a wider window gave v11.72 a DIFFERENT column count',
  v1172wide.length !== v1172.length, true);
t('E4  /!\\ the shipped rule gives the same count on both',
  AMZ_FEE_LINES.filter(l => l.sku).length, v1191.length);
// The four with nothing charged are the ones now marked rather than dropped.
const nocharge = AMZ_FEE_LINES.filter(l => l.sku && Math.abs(tot[l.k] || 0) <= 0.005)
  .map(l => l.sku);
t('E5  and they are named', nocharge.join(','), 'Storage,Aged,Removal,Surcharge');
console.log(JSON.stringify(out));
"""
E = E.replace("__LINES__", const_blk("AMZ_FEE_LINES"))
p = os.path.join(SP, "_v1191_e.js")
io.open(p, "w", encoding="utf-8", newline="").write(E)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-2500:]); print(r.stderr[-2500:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
