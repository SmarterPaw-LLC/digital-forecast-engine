#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.38 - the chart's own numbers, as a table, exportable.

Jason: "i would also like a table below the graph that filters the way the
page filters, that i can export"

/!\ THE PRODUCT TABLE ALREADY DID THAT, which is the clue to what he meant.
It filters the way the page filters and it exports, and he had just hidden
it. What is missing is a table of what the CHART draws - the bands he
picked, over the buckets he picked, in the measure he picked - and it
filters the way the page filters BY CONSTRUCTION, because it is built from
the chart's own datasets rather than from a second pass over the rows.
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
        print("  FAIL  %s%s" % (label, ("  got: %s" % extra) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


def fn_flat(name):
    i = js.index("function " + name + "(")
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.38  the chart as a table")
print("=" * 70)

# ===========================================================================
print("\nA. /!\\ A GOAL IS NOT AN ACTUAL")
# ===========================================================================
# Both the goal line and the previous-period overlay ride in `datasets` so
# the chart can draw them. Neither is something that sold, and summing them
# into a total is the trap `stack:'_goal'` was added for in v10.76.
A = run_node(os.path.join(SP, "_v1238_a.js"), fn_flat("salesGridSeries") + r"""
const ds = [
  { label: 'Toys', data: [1, 2] },
  { label: 'Blends', data: [3, 4] },
  { label: 'Goal', data: [9, 9], _isGoal: true, stack: '_goal' },
  { label: 'Previous period', data: [5, 5], stack: '_prev' },
];
console.log(JSON.stringify({
  kept: salesGridSeries(ds).map(d => d.label),
  none: salesGridSeries(null).length,
  empty: salesGridSeries([]).length,
  nullish: salesGridSeries([null, undefined, { label: 'x', data: [] }]).map(d => d.label),
}));
""")
eq("A1  /!\\ the goal and the previous period are left out", A["kept"], ["Toys", "Blends"])
eq("A2  a missing dataset list is not a crash", A["none"], 0)
eq("A3  nor an empty one", A["empty"], 0)
eq("A4  nor a null inside one", A["nullish"], ["x"])

# ===========================================================================
print("\nB. it is built FROM the chart, not beside it")
# ===========================================================================
TOT = fn_flat("updateSalesChart")
CHAN = fn_flat("updateChannelChart")
ok("renderSalesChartGrid(weeks, datasets, measure," in TOT,
   "B1  /!\\ the Total chart hands it the very datasets it just drew")
ok("renderSalesChartGrid(weeks, datasets, measure, 'Channel')" in CHAN,
   "B2  ...and By Channel hands it its own")
ok(js.count("function renderSalesChartGrid") == 1,
   "B3  /!\\ ONE grid renderer - two would be two answers to 'what is on the "
   "chart'")
ok(TOT.index("renderSalesChartGrid") > TOT.index("new Chart(ctx"),
   "B4  /!\\ drawn AFTER the chart, so a throw in Chart.js cannot leave the "
   "table describing something that was never rendered")
GRID = fn_flat("renderSalesChartGrid")
ok("salesData" not in GRID and "inRange" not in GRID,
   "B5  /!\\ it never touches the rows - re-deriving the filters here is how "
   "a table and the chart above it come to disagree (hard rule #1)")
ok("salesFmtVal(" in GRID and "salesBucketLabel(" in GRID,
   "B6  and it formats through the page's own helpers")

# ===========================================================================
print("\nC. the grid itself")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1238_c.js"),
             fn_flat("salesGridSeries") + "\n" + fn_flat("salesFmtVal") + "\n"
             + fn_flat("salesMeasureUnit") + "\n" + fn_flat("salesBucketLabel") + r"""
let _salesGrid = null, salesGridOn = true;
const SEEN = {};
function salesChartGrain() { return 'month'; }
function salesPeriodLabel() { return 'Last 12 months'; }
function salesGridApply() {}
globalThis.document = { getElementById: (id) => (SEEN[id] = SEEN[id] || {
  style: {}, set innerHTML(v) { this._html = v; }, get innerHTML() { return this._html; },
  set textContent(v) { this._t = v; }, get textContent() { return this._t; },
}) };
""" + fn_flat("renderSalesChartGrid") + r"""
const buckets = ['2026-09', '2026-10', '2026-11'];
renderSalesChartGrid(buckets, [
  { label: 'Blends', data: [1, 0, 3], borderColor: '#111' },   // a zero bucket
  { label: 'Toys',   data: [40, 50, 60], borderColor: '#222' },
  { label: 'Goal',   data: [99, 99, 99], _isGoal: true },
], 'revenue', 'Category');
const g = _salesGrid;
const out = {
  order: g.rows.map(r => r.label),
  totals: g.rows.map(r => r.total),
  colTotals: g.colTotals,
  grand: g.grand,
  title: SEEN['salesGridTitle'].textContent,
  sub: SEEN['salesGridSub'].textContent,
  shown: SEEN['salesGridPanel'].style.display,
  hasDollar: SEEN['salesGridBody'].innerHTML.includes('$150'),
  dashForZero: SEEN['salesGridBody'].innerHTML.includes('—'),
};
// an empty window hides the panel rather than drawing an empty table
renderSalesChartGrid([], [{ label: 'x', data: [] }], 'units', 'Product');
out.emptyHides = SEEN['salesGridPanel'].style.display;
out.emptyGrid = _salesGrid;
console.log(JSON.stringify(out));
""")
eq("C1  /!\\ biggest band first, which is the order the stacked chart draws "
   "them in - reading the table against the chart should not need a search",
   C["order"], ["Toys", "Blends"])
eq("C2  each band's own total", C["totals"], [150, 4])
eq("C3  and each bucket's", C["colTotals"], [41, 50, 63])
eq("C4  the grand total is the sum of both ways round", C["grand"], 154)
ok("$154" in C["sub"], "C5  the sub-line carries the measure's format", C["sub"])
ok("our revenue" in C["sub"], "C6  ...and names the basis", C["sub"])
ok("Category" in C["title"] and "2 " in C["title"] and "3 months" in C["title"],
   "C7  the title says what the bands are and how many buckets", C["title"])
ok(C["hasDollar"], "C8  a dollar measure renders as dollars")
ok(C["dashForZero"], "C9  /!\\ a zero bucket renders as a dash, not a 0 - the "
   "band drew nothing there")
eq("C10 /!\\ an empty window HIDES the panel rather than drawing an empty "
   "table (the v10.19 rule)", C["emptyHides"], "none")
eq("C11 ...and clears the grid, so a stale CSV cannot be exported from it",
   C["emptyGrid"], None)

# ===========================================================================
print("\nD. the export is what is on screen")
# ===========================================================================
CSV = fn_flat("downloadSalesGridCSV")
ok("const g = _salesGrid;" in CSV,
   "D1  /!\\ written from the grid that was LAST RENDERED, not re-derived - "
   "there is no window in which the file and the table can disagree")
ok("if (!g) { alert(" in CSV,
   "D2  ...and refuses rather than downloading an empty file")
ok("Our_Revenue_USD" in CSV and "'Units'" in CSV,
   "D3  the header names the measure, as v12.35's export does")
ok("promptCsvName(" in CSV,
   "D4  through the app's own filename prompt, not a second one")
ok("salesBucketLabel(b)" in CSV,
   "D5  and the column headers are the chart's own bucket labels")
ok('onclick="downloadSalesGridCSV()"' in s and s.count("downloadSalesGridCSV") == 2,
   "D6  one button, one function")

# ===========================================================================
print("\nE. the panel")
# ===========================================================================
ok(s.index('id="salesGridPanel"') > s.index('id="salesDrillPanel"'),
   "E1  below the graph, which is where he asked for it")
ok('class="ds"' in s[s.index('id="salesGridPanel"'):s.index('id="salesGridPanel"') + 400],
   "E2  /!\\ built from the app's own panel pattern, not a tenth look "
   "(hard rule #1 - v12.28 shipped an invented class and rendered as bare "
   "text)")
CLOSE = fn_flat("closeSalesDrill")
ok("salesGridPanel" in CLOSE and "_salesGrid = null" in CLOSE,
   "E3  it closes with the chart, because it IS the chart's numbers")
TOG = fn_flat("toggleSalesGrid")
ok("localStorage.setItem('salesGridOn'" in TOG,
   "E4  hiding it persists, like every other display preference here")
ok("localStorage.getItem('salesGridOn') !== '0'" in js,
   "E5  /!\\ ...and it defaults ON, because it is what he asked for")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
