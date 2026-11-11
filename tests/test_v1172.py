#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.72 - fee LOAD as the target, and a ranking by what we are storing.

Jason, twice: "this page tells me literally nothing."  Asked what the cost
actually is: "the costs are likely unit storage costs primarily."  On the 5%
goal: measure it as fee % of net sales.

  * A  the cubic-feet load: newest snapshot wins, a non-inch row is SKIPPED
       rather than converted on a guess, a failure yields {} so it cannot
       retry forever, and a SKU with no Fee Preview row is NULL not zero.
  * B  units held come from `records`, which is already in memory - no fetch
       for something the app holds (the v11.71 lesson applied forward).
  * C  /!\ the target is a RATIO. 88% of fees are fixed, so a dollar target
       can only be met by selling less.
  * D  /!\ a column with no charge in this window is NOT a column. 93 rows x
       6 columns of dashes is what Jason was looking at.
  * E  static: no Amazon rate card entered the app, and `Cover days` was not
       given a rival spelling.
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
    pat = kw + " " + name + "("
    i = js.index(pat)
    head = js.index("{", i)
    j = i
    while j > 0 and js[j - 1] != "\n":
        j -= 1
    return js[j:head] + _bal(head)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("v11.72 - fee load, and a ranking by what we are storing")
print("=" * 68)

NC = nocomment(js)

# ---------------------------------------------------------------------------
print("\nA. the real amzLoadCuFt")
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, "_v1172_a.js"), """
let amzCuFtByMid = null, _amzCuFtLoading = false;
let pnlAmazonView = 'summary';
const renderAmazonFees = () => {};
let ROWS = [], FAIL = null;
const getSB = async () => ({
  from: () => ({ select: () => ({ order: () => FAIL
      ? { data: null, error: { message: FAIL } }
      : { data: ROWS, error: null } }) }),
});
""" + fn("amzLoadCuFt", "async function") + """
(async () => {
  const out = {};
  // 12 x 12 x 12 inches = exactly 1 cu ft. Newest snapshot wins.
  ROWS = [
    { master_id: 'M1', region: 'US', snapshot_date: '2026-11-02',
      longest_side: 12, median_side: 12, shortest_side: 12, unit_of_dimension: 'inches' },
    { master_id: 'M1', region: 'US', snapshot_date: '2025-01-01',
      longest_side: 24, median_side: 12, shortest_side: 12, unit_of_dimension: 'inches' },
    { master_id: 'M2', region: 'CA', snapshot_date: '2026-11-02',
      longest_side: 6, median_side: 6, shortest_side: 6, unit_of_dimension: 'inches' },
    // centimetres - SKIPPED rather than converted on a guess
    { master_id: 'M3', region: 'US', snapshot_date: '2026-11-02',
      longest_side: 30, median_side: 30, shortest_side: 30, unit_of_dimension: 'centimeters' },
    // a missing dimension is not a zero-volume product
    { master_id: 'M4', region: 'US', snapshot_date: '2026-11-02',
      longest_side: 12, median_side: null, shortest_side: 12, unit_of_dimension: 'inches' },
    { master_id: null, region: 'US', snapshot_date: '2026-11-02',
      longest_side: 12, median_side: 12, shortest_side: 12, unit_of_dimension: 'inches' },
  ];
  await amzLoadCuFt();
  out.map = amzCuFtByMid;
  out.m1 = amzCuFtByMid['M1|US'];
  out.m2 = Math.round(amzCuFtByMid['M2|CA'] * 10000) / 10000;
  out.m3 = amzCuFtByMid['M3|US'];
  out.m4 = amzCuFtByMid['M4|US'];
  out.keys = Object.keys(amzCuFtByMid).sort();
  // second call is a no-op
  ROWS = [{ master_id: 'ZZ', region: 'US', snapshot_date: '2026-11-03',
            longest_side: 12, median_side: 12, shortest_side: 12, unit_of_dimension: 'inches' }];
  await amzLoadCuFt();
  out.afterSecond = Object.keys(amzCuFtByMid).sort();
  // a failure yields {} - not null, or it retries on every render for ever
  amzCuFtByMid = null; FAIL = 'boom';
  const _w = console.warn; console.warn = () => {};
  await amzLoadCuFt();
  console.warn = _w;
  out.onFail = amzCuFtByMid;
  console.log(JSON.stringify(out));
})();
""")

eq("A1  12x12x12 inches is exactly one cubic foot", A["m1"], 1)
eq("A2  the NEWEST snapshot wins (24in would be 2.0)", A["m1"], 1)
eq("A3  6x6x6 is 0.125 cu ft", A["m2"], 0.125)
ok("M3|US" not in A["keys"],
   "A4  a centimetre row is SKIPPED, never converted on a guess", A["keys"])
ok("M4|US" not in A["keys"], "A5  a missing dimension yields no entry, not zero")
eq("A6  a row with no master_id is dropped", A["keys"], ["M1|US", "M2|CA"])
eq("A7  region is part of the key", A["keys"], ["M1|US", "M2|CA"])
eq("A8  a second call does not refetch", A["afterSecond"], ["M1|US", "M2|CA"])
eq("A9  /!\\ a FAILURE yields {} so it cannot retry for ever", A["onFail"], {})

# ---------------------------------------------------------------------------
print("\nB. units held come from memory, not a fetch")
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, "_v1172_b.js"), """
let records = [
  { master_id: 'M1', region: 'US', fba_available: 100, fba_inbound: 25, warehouse: 999 },
  { master_id: 'M1', region: 'CA', fba_available: 7,   fba_inbound: 0 },
  { master_id: 'M2', region: 'US', fba_available: 0,   fba_inbound: 0 },
];
""" + fn("amzUnitsHeld") + """
const out = {
  us: amzUnitsHeld('M1', 'US'),
  ca: amzUnitsHeld('M1', 'CA'),
  zero: amzUnitsHeld('M2', 'US'),
  missing: amzUnitsHeld('NOPE', 'US'),
  noRegion: amzUnitsHeld('M1', null),
};
records = undefined;
out.noRecords = (() => { try { return amzUnitsHeld('M1', 'US'); } catch (e) { return 'THREW'; } })();
console.log(JSON.stringify(out));
""")
eq("B1  fulfillable + inbound, for that region", B["us"], 125)
ok("warehouse" not in nocomment(fn("amzUnitsHeld")),
   "B2  our OWN warehouse is not Amazon storage, so it is excluded")
eq("B3  a different region is its own number", B["ca"], 7)
eq("B4  a real zero is zero, not null", B["zero"], 0)
eq("B5  a product with no inventory row is NULL, never zero", B["missing"], None)
eq("B6  no region means every region", B["noRegion"], 132)
eq("B7  no records loaded yet is null, not a throw", B["noRecords"], None)
ok("from('fba_inventory_snapshots')" not in fn("amzLoadCuFt", "async function"),
   "B8  no fetch was added for data already in memory")

# ---------------------------------------------------------------------------
print("\nC. /!\\ the target is a RATIO")
# ---------------------------------------------------------------------------
rf = fn("renderAmazonFees")
ok("const loadNow = t.netSales > 0 ? (t.fees / t.netSales * 100) : null;" in rf,
   "C1  fee load is fees over net sales")
ok("const loadTgt = loadNow == null ? null : loadNow * (1 - tgtPct / 100);" in rf,
   "C2  the target reduces the LOAD by the typed percentage")
ok("'Fee % Target'" in rf, "C3  and the card says so")
ok("to remove from this window" not in rf,
   "C4  the retired dollar-target card is GONE, not left beside it")
ok("label: 'Avoidable Now'" not in rf,
   "C5  and so is Avoidable Now - storage is ~2/3 missing, so it understated")
C = run_node(os.path.join(SP, "_v1172_c.js"), """
function compute(fees, netSales, tgtPct) {
  const loadNow = netSales > 0 ? (fees / netSales * 100) : null;
  const loadTgt = loadNow == null ? null : loadNow * (1 - tgtPct / 100);
  const loadGap = loadNow == null ? null : (loadNow - loadTgt) / 100 * netSales;
  return [loadNow, loadTgt, loadGap];
}
const r = x => x == null ? null : Math.round(x * 100) / 100;
console.log(JSON.stringify({
  normal: compute(14184, 28200, 5).map(r),
  zeroSales: compute(100, 0, 5).map(r),
  zeroTarget: compute(14184, 28200, 0).map(r),
  hundred: compute(14184, 28200, 100).map(r),
}));
""")
eq("C6  50.3% load, 5% off it, is 47.8%", C["normal"][:2], [50.3, 47.78])
eq("C7  ...and that is worth 5% of the fees", C["normal"][2], 709.2)
eq("C8  no sales yields nulls, never NaN", C["zeroSales"], [None, None, None])
eq("C9  a zero target is worth nothing, not everything", C["zeroTarget"][2], 0)
eq("C10 a 100% target is the whole fee bill", C["hundred"][2], 14184)

# ---------------------------------------------------------------------------
print("\nD. /!\\ a column with no charge in this window is NOT a column")
# ---------------------------------------------------------------------------
# /!\ RE-POINTED IN v11.91, AND IT WAS RIGHT TO GO RED.
#
# D1/D2 pinned v11.72's rule: a fee line charging nothing in this window got
# no column. Jason reversed it - "the columns should be based on the view that
# is set ... if there is no data for a period, i need to know that" - because
# the gate made the column SET a function of the period, so the table changed
# shape every time he moved the window.
#
# This is the v11.63 / v11.77 lesson again: a census that asserts the status
# quo goes red on the release that fixes what it was hiding. The guarantee
# worth keeping is not "the column disappears", it is "a window that charged
# nothing never reads as 'nobody pays this'" - which is what is measured now.
ok("AMZ_FEE_LINES.filter(l => l.sku && Math.abs(t[l.k] || 0) > 0.005)" not in js,
   "D1  /!\\ v11.72's window gate on the columns is GONE (v11.91)")
ok("const NOCHARGE = new Set(AMZ_FEE_LINES" in js,
   "D2  ...replaced by marking the column instead of dropping it")
ok("No charge in this window." in js and "opacity:.45" in js,
   "D2b ...on the header, dimmed, with the cadence on its tooltip")
# The composition table still NAMES them, which is where the fact belongs.
ok("const unseen = AMZ_FEE_LINES" in js and "not in window" in js,
   "D3  ...because the composition row above already says it once")
ok("k: 'cuft'" in rf and "k: 'held'" in rf,
   "D4  Held and Cu Ft are columns")
ok("let amzFeeSort = { k: 'cuft', dir: -1 };" in js,
   "D5  and the table DEFAULTS to what we are storing")
ok("p.cuftU != null && p.held != null" in js,
   "D6  cubic feet needs BOTH a dimension and a holding, else null")

# ---------------------------------------------------------------------------
print("\nE. static: no rate card, no rival vocabulary")
# ---------------------------------------------------------------------------
# Jason's call: rank cu ft and cover, no dollars. A storage rate in the file
# would be stale the day Amazon moves it - v9.73's reason for the Fee Preview.
for rate in ["0.78", "2.40", "0.87", "2.4 "]:
    ok(rate not in rf, "E1  no storage rate card in the renderer (%s)" % rate)
ok("cu ft" not in rf.lower() or "$" not in rf[rf.lower().index("cu ft"):rf.lower().index("cu ft") + 40],
   "E2  cubic feet are never dollarised on the card")
# rule 3a - Inventory Planning owns `Cover days`; this must not coin a rival.
# against COMMENT-STRIPPED source: the comment explaining why it was not
# duplicated obviously names it (v11.18 / v11.63's rule, which this very
# assertion broke on its first run).
_rfc = nocomment(rf)
eq("E3  `Cover days` keeps ONE spelling, and no rival renders on this tab",
   _rfc.count("Cover days") + _rfc.count("Cover mo") + _rfc.count("cover_days"), 0)
ok("Cover days" in js, "E4  ...while the app's own spelling still exists elsewhere")
# ...and the comment must SURVIVE, so grepping the concept still lands on
# the reasoning. Matched on a fragment that does not wrap.
ok("rival spelling of it" in js and "Cover days" in rf,
   "E5  and the source says why it was not duplicated")

cm = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) . 20\d\d-\d\d-\d\d<", s).group(1)
doc  = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cm).group(1)
eq("E6  the chip and CLAUDE.md agree", chip, doc)
ok("fba_fee_preview" in js and "amzLoadCuFt" in js,
   "E7  the dimensions feed is wired")
eq("E8  the loader is kicked exactly once, from the renderer",
   NC.count("amzLoadCuFt();"), 1)

print("\n" + "-" * 68)
print("  passed %d   failed %d" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
