#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.93 - the target points at the lines, and the shelf gets a verdict.

Jason, on the Fees tab:
  "changing the reduction target does not highlight where the savings
   targeted could come from"
  "the units held in storage does not have any kind of analysis of sell
   through during that period to indicate storage savings"

  * A  static: the plan, the idle figure and the new column are declared once.
  * B  the real amzFeeTargetPlan: avoidable only, ranked, capped, and a
       SHORTFALL REPORTED rather than filled.
  * C  the real amzFeeStamp / amzFeeSumRows: Units/Held, and the basis - a
       total divides the units that HAVE a held figure by the held they have.
  * D  the real amzFeeIdle: the shelf that sold nothing in this window.
  * E  /!\ THE DEFECT REPRODUCED. amzUnitsHeld takes no window, so the
       previous period's aggregation returns the IDENTICAL held figure and
       v11.91's chip could only ever read `-> 0.0% vs prev`.
  * F  the renderer and the export follow the declarations.
"""
import io, os, re, sys, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")

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
    """Brace matcher. /!\\ It handles a regex literal and a plain template
    literal; it CANNOT walk nested template literals (v11.91's lesson), which
    is why renderAmazonFees is sliced by its closing brace instead."""
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


def fn(name):
    i = js.index("function " + name + "(")
    while i > 0 and js[i - 1] != "\n":
        i -= 1
    b = js.index("{", js.index("function " + name + "("))
    return js[i:b] + _bal(b)


def fn_flat(name):
    i = js.index("function " + name + "(")
    return js[i:js.index("\n}", i) + 2]


def const_arr(name):
    i = js.index("const %s = [" % name)
    j, d = js.index("[", i), 0
    k = j
    while k < len(js):
        if js[k] == "[":
            d += 1
        elif js[k] == "]":
            d -= 1
            if d == 0:
                return "const %s = %s;" % (name, js[j:k + 1])
        k += 1
    raise SystemExit("unbalanced %s" % name)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v11.93  where the saving comes from, and whether the shelf turns")
print("=" * 68)

REND = nocomment(fn_flat("renderAmazonFees"))
NC   = nocomment(js)

# ===========================================================================
print("\nA. declared once")
# ===========================================================================
ok("function amzFeeTargetPlan(" in js, "A1  the plan has a function")
ok("function amzFeeIdle(" in js, "A2  so does the idle shelf")
ok("function amzFeeTopFor(" in js, "A3  and the per-line product ranking")
ok("function amzFeeFocusLine(" in js, "A4  and the composition row's click")

# /!\ ONE TARGET-DOLLARS DEFINITION. v11.91 left `const target = t.fees *
# tgtPct / 100` beside loadGap - the same number by a second route, read by
# nothing. The plan takes the card's own figure.
ok(re.search(r"(?m)^\s*const target = t\.fees \* tgtPct / 100;", js) is None,
   "A5  /!\\ the dead second target computation is gone")
ok("amzFeeTargetPlan(t, loadGap || 0)" in REND,
   "A6  ...and the plan reads the CARD's dollars, so they cannot disagree")

# The lever vocabulary decides what can contribute - not a new rule here.
PLANFN = nocomment(fn("amzFeeTargetPlan"))
ok("l.lever === 'avoidable'" in PLANFN,
   "A7  /!\\ the plan is built from the registry's own `avoidable`")
ok("'rate'" not in PLANFN and "'fixed'" not in PLANFN,
   "A8  ...and claims nothing from a rate or fixed line")
ok("shortfall" in PLANFN, "A9  a shortfall is a result, not an error")
# A rate literal here would be v11.72's refusal reversed.
ok(not re.search(r"\*\s*0\.\d", PLANFN), "A10 no invented haircut percentage")

# The suppression, and WHY it is not the same thing as the direction map.
# /!\ THE SET GREW IN v11.98 (the three pack columns are states too). What
# this assertion is for is that v11.93's three are IN it, not that they are
# the only ones - a census of a list that is meant to grow.
for _k in ('held', 'cuft', 'sellThru'):
    ok(re.search(r"const AMZ_FEE_DELTA_NONE = new Set\(\[[^\]]*'%s'" % _k, js) is not None,
       "A11 /!\\ %s's delta cannot move, and is declared" % _k)
ok("const AMZ_FEE_DELTA_GOOD = { units: true, netSales: true, held: null, cuft: null };" in js,
   "A12 ...and the direction map is untouched (two questions, not one)")

# The declared pair (rule 3a): the picker and the table.
fixed = re.search(r"const AMZ_FEE_FIXED_COLS = \[([\s\S]*?)\n\];", js).group(1)
pick = [(m.group(1), m.group(2)) for m in
        re.finditer(r"\{\s*k:\s*'([A-Za-z0-9_]+)',\s*h:\s*'([^']*)'\s*\}", fixed)]
allc = REND[REND.index("const ALLCOLS = ["):]
tbl = [(m.group(1), m.group(2)) for m in
       re.finditer(r"\{\s*k:\s*'([A-Za-z0-9_]+)',\s*h:\s*'([^']*)'", allc)]
tbl_fixed = [x for x in tbl if x[0] in dict(pick)]
eq("A13 /!\\ the picker's keys still match the table's",
   [k for k, _ in pick], [k for k, _ in tbl_fixed])
eq("A14 ...and the headers",
   [h for _, h in pick], [h for _, h in tbl_fixed])
ok(("sellThru", "Units/Held") in pick, "A15 Units/Held is in the declared pair")

# /!\ RULE 3a: NOT A THIRD SPELLING OF COVER. `Cover days` (Inventory
# Planning) and `Stock Cover Months` (Break-Even) already exist and compute
# different things; this column is a SHARE, and its header names its own two
# operands rather than borrowing either vocabulary.
ok("Cover days" not in REND and "Cover Months" not in REND,
   "A16 /!\\ no rival cover spelling on this tab")

# ===========================================================================
print("\nB. the real amzFeeTargetPlan, driven")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1193_b.js"),
    const_arr("AMZ_FEE_LINES") + "\n" + fn("amzFeeTargetPlan") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const r2 = v => Math.round(v * 100) / 100;
// Avoidable: placement 150, aged 600, low inv 200, removal 60, surcharge 15
// = 1,025. Plus two lines the plan may never touch.
const T = {
  inbound_placement_fee_total: 150, aged_inventory_fee_total: 600,
  low_inventory_fee_total: 200, removal_fee_total: 60, storage_util_surcharge: 15,
  fba_fulfillment_fee_total: 9000, referral_fee_total: 4000,
  fba_storage_fee_total: 800, fees: 14825,
};
const P1 = amzFeeTargetPlan(T, 500);
t('B1  the biggest avoidable line is ranked first', P1.rows[0].k, 'aged_inventory_fee_total');
t('B2  /!\\ and it alone covers a 500 target', P1.rows.filter(r => r.inPlan).length, 1);
t('B3  ...capped at what is left, not at its own size', r2(P1.rows[0].applied), 500);
t('B4  /!\\ the column sums to the target exactly', r2(P1.applied), 500);
t('B5  covered', P1.covered, true);
t('B6  nothing is short', r2(P1.shortfall), 0);

// A target needing three lines: 600 + 200 + 150 = 950, so the third is capped.
const P2 = amzFeeTargetPlan(T, 900);
t('B7  three lines are drawn on', P2.rows.filter(r => r.inPlan).length, 3);
t('B8  the first two go in whole', r2(P2.rows[0].applied + P2.rows[1].applied), 800);
t('B9  /!\\ the last one is capped at the remainder', r2(P2.rows[2].applied), 100);
t('B10 ...so the total is the target, not the pool', r2(P2.applied), 900);
t('B11 and the lines after it put in nothing',
  P2.rows.slice(3).every(r => r.applied === 0 && !r.inPlan), true);

// /!\ A TARGET BEYOND THE AVOIDABLE POOL IS REPORTED SHORT, NEVER FILLED.
const P3 = amzFeeTargetPlan(T, 2000);
t('B12 /!\\ the pool is what it is', r2(P3.pool), 1025);
t('B13 /!\\ the shortfall is stated', r2(P3.shortfall), 975);
t('B14 ...and the column stops at the pool', r2(P3.applied), 1025);
t('B15 not covered', P3.covered, false);
// /!\ MY EXPECTATION WAS WRONG HERE, not the code: 1025/2000 is not a dyadic
// rational, so the product lands on 51.24999999999999 and one decimal place
// rounds it DOWN to 51.2. Read to two places, where the value is stable.
t('B16 the coverage reads as a share of the target', Math.round(P3.coverPct * 100) / 100, 51.25);

// /!\ A RATE OR FIXED LINE NEVER APPEARS, however large. FBA Fulfilment is
// 9,000 here - by size it would be first on every plan.
t('B17 /!\\ no rate line is in the plan',
  P3.rows.some(r => r.k === 'fba_fulfillment_fee_total' || r.k === 'fba_storage_fee_total'), false);
t('B18 /!\\ no fixed line either',
  P3.rows.some(r => r.k === 'referral_fee_total'), false);

// Zero and absent lines are not rows.
const P4 = amzFeeTargetPlan({ aged_inventory_fee_total: 0, removal_fee_total: 40 }, 100);
t('B19 a line charged nothing is not in the plan', P4.rows.map(r => r.k).join(','),
  'removal_fee_total');
t('B20 ...and the shortfall counts only what exists', r2(P4.shortfall), 60);

// No target typed: no plan, and no division by zero.
const P5 = amzFeeTargetPlan(T, 0);
t('B21 a zero target draws on nothing', P5.rows.filter(r => r.inPlan).length, 0);
t('B22 ...and reports no coverage rather than NaN', P5.coverPct, null);
t('B23 ...and is not "covered"', P5.covered, false);
const P6 = amzFeeTargetPlan(null, 500);
t('B24 /!\\ a missing total does not throw', P6.rows.length, 0);
console.log(JSON.stringify(out));
""")
for c in B:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nC. the real amzFeeStamp / amzFeeSumRows: Units/Held and its basis")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1193_c.js"),
    const_arr("AMZ_FEE_LINES") + "\n" + const_arr("AMZ_FEE_OUTSIDE") + "\n"
    + fn("amzFeeStamp") + "\n" + fn("amzFeeSumRows") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const r1 = v => (v == null ? null : Math.round(v * 10) / 10);
const row = (units, held, cuft) => {
  const o = { netSales: 100, units, fees: 10, held, cuft,
              heldUnits: (held == null ? null : units) };
  for (const l of AMZ_FEE_LINES) o[l.k] = 0;
  return amzFeeStamp(o);
};
const A = row(10, 100, 5);
const B2 = row(90, 300, 9);
t('C1  units over units held', r1(A.sellThru), 10);
t('C2  ...per product', r1(B2.sellThru), 30);

// /!\ RE-DERIVED FROM THE SUMS, NEVER AVERAGED. 10% and 30% average to 20%;
// 100 units over 400 held is 25%. This is v10.12's rule, applied to a ratio
// that reads as a verdict on the shelf.
const tot = amzFeeSumRows([A, B2]);
t('C3  /!\\ the footer re-derives it from the sums', r1(tot.sellThru), 25);
t('C4  ...which is NOT the average of the rows', r1(tot.sellThru) === 20, false);

// /!\ AND THE BASIS. A null held is 'not measured' (v11.91), so it is left
// out of the denominator - and its UNITS have to be left out of the
// numerator too, or the ratio is units-over-part-of-the-held.
const noHeld = row(500, null, null);
const mixed = amzFeeSumRows([A, B2, noHeld]);
t('C5  /!\\ held still sums only the measured rows', mixed.held, 400);
t('C6  /!\\ and the units follow the same rows', mixed.heldUnits, 100);
t('C7  /!\\ so the ratio does not jump on an unmeasured product',
  r1(mixed.sellThru), 25);
t('C8  ...while Units still reports every product', mixed.units, 600);

// Nothing held at all: no ratio, rather than a division by zero.
const none = amzFeeSumRows([noHeld]);
t('C9  nothing measured answers null', none.sellThru, null);
t('C10 ...and so does an empty table', amzFeeSumRows([]).sellThru, null);
t('C11 a product holding zero units answers null, not Infinity',
  row(5, 0, 0).sellThru, null);

// A product that sold nothing while holding stock is the 0% case, which is
// the one the table colours red.
t('C12 /!\\ held with no sales reads 0%, not a dash', row(0, 250, 7).sellThru, 0);
console.log(JSON.stringify(out));
""")
for c in C:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nD. the real amzFeeIdle")
# ===========================================================================
D = run_node(os.path.join(SP, "_v1193_d.js"), fn("amzFeeIdle") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const P = [
  { mid: 'A', units: 100, held: 400, cuft: 20 },   // turning
  { mid: 'B', units: 0,   held: 250, cuft: 7 },    // idle, measured
  { mid: 'C', units: 0,   held: 60,  cuft: null }, // idle, NOT measured
  { mid: 'D', units: 0,   held: 0,   cuft: 0 },    // nothing held
  { mid: 'E', units: 0,   held: null, cuft: null },// no inventory figure
  { mid: 'F', units: 3,   held: 10,  cuft: 1 },    // turning, barely
];
const I = amzFeeIdle(P);
t('D1  /!\\ only a product holding stock and selling none', I.n, 2);
t('D2  ...counted against the products that hold anything', I.total, 4);
t('D3  /!\\ a null cu ft is left OUT of the volume', I.cuft, 7);
t('D4  ...and counted, so the figure can say what it is missing', I.cuftMissing, 1);
t('D5  the units are summed over the idle ones', I.held, 310);
const E = amzFeeIdle([{ units: 5, held: 10, cuft: 1 }]);
t('D6  everything turning reads zero idle', E.n, 0);
t('D7  ...and no volume at all, rather than 0 cu ft', E.cuft, null);
const Z = amzFeeIdle([]);
t('D8  an empty window reports nothing held', Z.total, 0);
t('D9  ...without throwing', amzFeeIdle(null).n, 0);
console.log(JSON.stringify(out));
""")
for c in D:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nE. /!\\ THE DEFECT REPRODUCED: a chip that could only read flat")
# ===========================================================================
# amzUnitsHeld is SLICED, not stubbed: the claim is about what the shipped
# function does with a window, so a hand-written stand-in would prove nothing.
E = run_node(os.path.join(SP, "_v1193_e.js"),
    const_arr("AMZ_FEE_LINES") + "\n" + const_arr("AMZ_FEE_OUTSIDE") + "\n"
    + re.search(r"(?m)^const AMZ_FEE_DELTA_NONE\s*=.*$", js).group(0) + "\n"
    + r"""
let pnlCurrencyMode = 'usd', pnlFxRate = 1.35, pnlFxGbp = 1.25, pnlFxEur = 1.1;
let amzCuFtByMid = { 'M1|US': 0.5 }, _amzCuFtLoading = false;
// v11.98 - amzFeeAgg stamps the Fee Preview pack onto every product,
// so the index and the gap rule have to be in scope. Sliced below.
let amzPackByMid = {};

const pnlRegion = 'US';
let _pnlSuppressDeltas = false;
const records = [{ master_id: 'M1', region: 'US', fba_available: 900, fba_inbound: 100 }];
const allProducts = [{ master_id: 'M1', short_name: 'Pawty Mix' }];
let pnlVisibleMids = ['M1'];
const mk = (wk, o) => Object.assign({ master_id: 'M1', week_start: wk, region: 'US',
  currency: 'USD', net_sales: 0, net_units_sold: 0 }, o);
const ROWS = [
  mk('2026-10-05', { net_sales: 4000, net_units_sold: 400, fba_fulfillment_fee_total: 1200,
      aged_inventory_fee_total: 300 }),
  mk('2026-09-07', { net_sales: 1000, net_units_sold: 100, fba_fulfillment_fee_total: 300,
      aged_inventory_fee_total: 90 }),
];
let WIN = { from: '2026-10-01', to: '2026-10-31' };
const getPnlDateRange = () => WIN;
const getPnlSource = () => ({ rows: ROWS, regionMatches: r => r === 'US' });
"""
    + fn("pnlRowFx") + "\n" + fn("amzUnitsHeld") + "\n" + fn("amzFeeStamp") + "\n"
    + re.search(r"(?m)^const AMZ_SMALL_STD = .*$", js).group(0) + "\n" + fn("amzSmallStdGap") + "\n" + fn("amzFeeAgg") + "\n" + fn("pnlDeltaChip") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const cur = amzFeeAgg({ from: '2026-10-01', to: '2026-10-31' });
const prv = amzFeeAgg({ from: '2026-09-01', to: '2026-09-30' });
const c = cur.prods[0], p = prv.prods[0];
// The two windows are genuinely different periods, measured rather than
// assumed: the units and the fees move.
t('E1  the two windows hold different sales', [c.units, p.units].join('/'), '400/100');
t('E2  ...and different fees', [Math.round(c.fees), Math.round(p.fees)].join('/'), '1500/390');
// /!\ AND THE SAME HELD, because amzUnitsHeld takes no window at all.
t('E3  /!\\ held is IDENTICAL in both', c.held === p.held, true);
t('E4  ...at today\u2019s snapshot', c.held, 1000);
t('E5  /!\\ and so is Cu Ft, which is derived from it', c.cuft === p.cuft, true);

// v11.91's chip, fed those two numbers: the only sentence it can produce.
const chip = pnlDeltaChip(c.held, p.held, null, false, 'prev');
t('E6  /!\\ v11.91 rendered a chip there', chip.length > 0, true);
t('E7  /!\\ ...and it could only ever say 0.0%', /0\.0% vs prev/.test(chip), true);
t('E8  ...with a flat arrow, on every row holding stock',
  chip.indexOf('\u2192') >= 0, true);

// v11.93: no chip at all on those three columns.
t('E9  held is suppressed', AMZ_FEE_DELTA_NONE.has('held'), true);
t('E10 so is cu ft', AMZ_FEE_DELTA_NONE.has('cuft'), true);
t('E11 /!\\ and Units/Held, whose denominator is that same snapshot',
  AMZ_FEE_DELTA_NONE.has('sellThru'), true);

// /!\ AND NO OTHER COLUMN LOST ITS CHIP. Units moved 100 -> 400.
t('E12 /!\\ Units still carries one', /\+300\.0% vs prev/.test(
    pnlDeltaChip(c.units, p.units, true, false, 'prev')), true);
t('E13 ...and the fee columns do too', /vs prev/.test(
    pnlDeltaChip(c.fees, p.fees, false, false, 'prev')), true);
t('E14 Units/Held is computed, even though it carries no chip',
  Math.round(c.sellThru * 10) / 10, 40);
console.log(JSON.stringify(out));
""")
for c in E:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nF. the renderer and the export follow the declarations")
# ===========================================================================
ok("(c.k === 'name' || AMZ_FEE_DELTA_NONE.has(c.k)) ? ''" in REND,
   "F1  /!\\ the row cells read the suppression")
ok("AMZ_FEE_DELTA_NONE.has(c.k) ? ''" in REND.split("tfoot")[-1]
   or REND.count("AMZ_FEE_DELTA_NONE.has(c.k)") >= 2,
   "F2  /!\\ ...and so does the footer, which has its own chip call")
eq("F3  both cell builders, no third", REND.count("AMZ_FEE_DELTA_NONE.has(c.k)"), 2)

# The plan on the table Jason named.
ok("'To Target'" in REND, "F4  the composition table carries a To Target column")
ok("PLAN.byKey[l.k]" in REND, "F5  ...fed per line from the one plan")
ok("amzFeeFocusLine('${l.k}')" in REND,
   "F6  /!\\ a line with a per-SKU column opens it on the products")
ok("const canOpen = !!l.sku;" in REND,
   "F7  /!\\ ...and a line without one gets no handler (v10.19)")
ok("amzFeeTopFor(A.prods, l.k, 3)" in REND,
   "F8  the products carrying the line are named under it")
ok("amzFeeTopFor(A.prods, l.k, 12)" in REND,
   "F9  ...with the fuller list on its tooltip rather than wrapped")
# /!\ MEASURED IN A BROWSER AT 1600px: as a plain block, the nowrap names set
# the first column's min-content to 302px and pushed the 585px table 70px OUT
# of its 515px panel, which `.ds-body` does not clip. An absolutely positioned
# child contributes no intrinsic width.
ok(re.search(r"position:relative;height:12px;margin-top:3px\"><div style=\"position:absolute", REND) is not None,
   "F9b /!\\ the names line cannot widen the column it sits in")
ok("PLAN.shortfall" in REND, "F10 the shortfall is reported on the panel")
ok("'Idle Shelf'" in REND, "F11 the idle shelf is a card")
ok("amzFeeIdle(A.prods)" in REND, "F12 ...over the window's own products")

# The focus must not grow a second column writer.
FOCUS = nocomment(fn("amzFeeFocusLine"))
ok("amzFeeSetCol(k, true, true)" in FOCUS,
   "F13 /!\\ the column is switched on through the ONE setter")
ok("localStorage" not in FOCUS,
   "F14 ...never by writing the store itself")
ok("if (!defer) renderAmazonFees();" in nocomment(fn("amzFeeSetCol")),
   "F15 ...and the setter's render is deferrable, so there is one repaint")

# Every data-bearing column is exportable (the standing rule).
CSV = nocomment(fn("downloadAmazonFeesCSV"))
for h in ("Units Held", "Cu Ft Held", "Units/Held %"):
    ok("'%s'" % h in CSV, "F16 the CSV carries %s" % h)
eq("F17 ...on the rows and on the TOTAL", CSV.count("n2(p.held)") + CSV.count("n2(t.held)"), 2)

# Five columns need the room, or the panel clips its own numbers.
ok("minmax(360px,1fr) minmax(420px,2fr)" in s,
   "F18 the composition panel was widened for the fifth column")

# The version chip and CLAUDE.md must agree (the v11.63 rule).
chip = re.search(r'margin-left:4px">v(\d+\.\d+)', s).group(1)
cmd = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", errors="replace").read()
doc = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cmd).group(1)
# /!\ RE-POINTED IN v11.94. This pinned the chip at the literal 11.93, so it
# went red on the next release for doing its job correctly - a census that
# asserts the status quo (v11.63's lesson). The guarantee worth keeping is
# that the chip and CLAUDE.md AGREE, and that this release's own entry is
# still in the file.
ok(re.match(r"^11\.\d+$", chip) is not None, "F19 the chip carries a v11.x version", chip)
eq("F20 /!\\ ...and CLAUDE.md agrees with it", doc, chip)
ok("## v11.93 - the target points at the lines" in cmd,
   "F21 /!\\ ...and v11.93's own entry is still on record")

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
