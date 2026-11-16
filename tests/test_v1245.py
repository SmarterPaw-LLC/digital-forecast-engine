#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.45 - Our Revenue read $0 after a reload.

- **Jason:** *"on the units sold page, the 'our revenue' doesn't render"*

/!\ `ourRevUsd` is written onto the ROW OBJECTS inside `salesData`, and
`loadSalesAnalytics` does `salesData = {}` and refills it with NEW objects on
every reload. v12.35 cached the whole pass behind `_salesRev.ok`, so the
re-attach the loader already asks for returned the cached marker and did
nothing. Every row then read `null`, and `salesRowVal` turns null into 0.

The fix splits the pass by COST: the 41k-row fetch is cached, the one pass
over rows already in memory is not.
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


def strip_comments(t):
    t = re.sub(r"/\*[\s\S]*?\*/", "", t)
    return re.sub(r"^\s*//.*$", "", t, flags=re.M)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.45  the attach follows the data")
print("=" * 70)

ATTACH = fn_flat("salesRevAttach")
ENSURE = fn_flat("salesEnsureRevenue")
COUNT  = fn_flat("salesRowsLoaded")

HARNESS = r"""
let salesData = {};
let _salesRev = null, _salesRevSrc = null, _salesRevFor = null, _salesRevRows = -1;
let allProducts = [];
let fetches = 0;
// The fetched maps, shaped exactly as salesRevFetch returns them. One Amazon
// US week and one Chewy price, which is enough to prove an attach happened.
async function salesRevFetch() {
  fetches++;
  return {
    seByKey: new Map([['SP-1\u0000US\u00002026-11-02', 1234.5]]),
    wmCost:  new Map([['SP-2', 2]]),
    cyPx:    new Map([['SP-3', 3]]),
    wmErr: null, cyErr: null,
  };
}
""" + COUNT + "\n" + ATTACH + "\n" + ENSURE + r"""
const mkData = () => ({
  'SP-1': [{ channel: 'amazon_us', region: 'US', week_start: '2026-11-02', units_ordered: 10 }],
  'SP-2': [{ channel: 'walmart',               week_start: '2026-11-02', units_ordered: 5 }],
  'SP-3': [{ channel: 'chewy',                 week_start: '2026-11-02', units_ordered: 7 }],
  'SP-4': [{ channel: 'shopify',               week_start: '2026-11-02', units_ordered: 1, revenue: 9 }],
  'SP-9': [{ channel: 'chewy',                 week_start: '2026-11-02', units_ordered: 4 }],
});
const read = () => Object.keys(salesData).map(k => salesData[k][0].ourRevUsd);
"""

A = run_node(os.path.join(SP, "_v1245_a.js"), HARNESS + r"""
(async () => {
  const out = {};
  salesData = mkData();
  await salesEnsureRevenue();
  out.first = read(); out.fetchesAfterFirst = fetches;
  out.gapChewyFirst = _salesRev.gap.chewyMids.size;

  // /!\ THE DEFECT: a RELOAD. loadSalesAnalytics does exactly this - a new
  // object, refilled with NEW row objects that carry no ourRevUsd.
  salesData = mkData();
  out.beforeReattach = read();
  await salesEnsureRevenue();
  out.afterReload = read(); out.fetchesAfterReload = fetches;

  // ...and a second ask with nothing changed must do no work at all.
  const before = JSON.stringify(read());
  await salesEnsureRevenue();
  out.idempotent = JSON.stringify(read()) === before;
  out.fetchesAfterIdle = fetches;

  // /!\ THE OTHER HALF: the loader EMPTIES the object and fills it
  // asynchronously, so an attach against zero rows must not cache itself.
  salesData = {};
  await salesEnsureRevenue();
  out.emptyAttach = read();
  salesData['SP-1'] = mkData()['SP-1'];
  await salesEnsureRevenue();
  out.afterLateRows = read();

  // The gap counters describe the CURRENT rows, so they are recomputed.
  out.gapChewy = _salesRev.gap.chewyMids.size;
  out.ok = !!_salesRev.ok;
  console.log(JSON.stringify(out));
})();
""")

# ===========================================================================
print("\nA. /!\\ THE DEFECT: every cell read $0 after a refresh")
# ===========================================================================
eq("A1  the first pass attaches - Amazon US off sku_economics, Walmart "
   "units x cost, Chewy units x per-each, Shopify its own revenue",
   A["first"], [1234.5, 10, 21, 9, None])
eq("A2  /!\\ a reload replaces the row objects, so NOTHING is attached - "
   "this is the state Jason's screenshot shows, and salesRowVal turns every "
   "one of these nulls into 0",
   A["beforeReattach"], [None, None, None, None, None])
eq("A3  /!\\ and the shipped helper RE-ATTACHES rather than returning its "
   "cached marker", A["afterReload"], [1234.5, 10, 21, 9, None])

# ===========================================================================
print("\nB. /!\\ BUT THE EXPENSIVE HALF IS STILL FETCHED ONCE")
# ===========================================================================
eq("B1  the first pass fetches", A["fetchesAfterFirst"], 1)
eq("B2  /!\\ a reload re-attaches WITHOUT re-fetching 41k rows - the whole "
   "reason v12.35 cached this at all", A["fetchesAfterReload"], 1)
eq("B3  ...and an idle re-ask fetches nothing either", A["fetchesAfterIdle"], 1)
ok(A["idempotent"],
   "B4  an ask with nothing changed leaves the values exactly as they were")

# ===========================================================================
print("\nC. /!\\ IDENTITY ALONE WOULD NOT HAVE BEEN ENOUGH")
# ===========================================================================
eq("C1  an attach against an EMPTY salesData attaches nothing", A["emptyAttach"], [])
eq("C2  /!\\ and rows arriving afterwards are still attached - the loader "
   "empties the object FIRST and fills it asynchronously, so a cache keyed "
   "on object identity alone would have called that empty pass done",
   A["afterLateRows"], [1234.5])
ok("_salesRevFor === salesData && _salesRevRows === rows" in ENSURE,
   "C3  which is why the guard tests the object AND the row count")

# ===========================================================================
print("\nD. the gap is recomputed, not remembered")
# ===========================================================================
eq("D1  SP-9 sells on Chewy with no price, so the first pass names one "
   "unpriced SKU", A["gapChewyFirst"], 1)
eq("D2  /!\\ and after a reload that left only SP-1 loaded it names NONE - "
   "the gap describes the rows ON SCREEN, not the pass that first ran. A "
   "remembered count would keep naming a SKU the page is no longer showing",
   A["gapChewy"], 0)
ok(A["ok"], "D3  and the result still reports ok")

# ===========================================================================
print("\nE. one writer, one asker")
# ===========================================================================
NO_C = strip_comments(js)
eq("E1  one fetch", NO_C.count("async function salesRevFetch"), 1)
eq("E2  one attach", NO_C.count("function salesRevAttach"), 1)
eq("E3  one ensure", NO_C.count("async function salesEnsureRevenue"), 1)
ok("_salesRev = salesRevAttach(src);" in ENSURE,
   "E4  /!\\ the attach RETURNS its result rather than assigning it, so "
   "there is exactly one writer of _salesRev")
ok("_salesRev =" not in strip_comments(ATTACH),
   "E5  ...and the attach never writes it")
ok("if (measure === 'revenue') {" in js,
   "E6  /!\\ the chart ALWAYS asks when the measure is revenue - a caller "
   "that decides for the helper is how the reload left every cell at $0")
ok("!(_salesRev && _salesRev.ok)" not in NO_C,
   "E7  /!\\ and the guard that made a correct call a no-op is GONE, not "
   "left standing beside the fix")
eq("E8  the three callers all still ask",
   NO_C.count("await salesEnsureRevenue()"), 3)

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
