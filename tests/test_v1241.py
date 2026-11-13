#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.41 - All time was SAMPLING for its earliest row.

- **Jason:** "the 'our revenue' amount here is not adding correctly..." ...
  "or it is all time" ... "maybe it is fine"

Reconciled against the live database, channel by channel:

    Year to date   SQL $1,931,632   screen $1,931,747   -0.006%
    All time       SQL $4,047,391   screen $4,044,983   +0.060%

So both are right to within a rounding band - but the all-time gap was not
rounding. `_salesAllTimeRows` (mine, v12.37) took each product's FIRST and
LAST array element as its date bracket, and `salesData[mid]` is in FETCH
order: sales_weekly's unordered pages, then Shopify, then Walmart, then
Chewy. The floor could land AFTER rows that exist before it, and a window
called "All time" then dropped them.
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


ATR = fn_flat("_salesAllTimeRows")

print("\n" + "=" * 70)
print("  v12.41  All time means all of it")
print("=" * 70)

A = run_node(os.path.join(SP, "_v1241_a.js"),
             fn_flat("pnlAllTimeFrom") + "\n" + ATR + r"""
// /!\ THE DEFECT REPRODUCED: the pre-v12.41 sampler, verbatim, beside the
// shipped one, over the same rows.
function sampled() {
  const out = [];
  for (const mid of Object.keys(salesData || {})) {
    const rows = salesData[mid];
    if (rows && rows.length) out.push(rows[0], rows[rows.length - 1]);
  }
  return out;
}
// Fetch order, which is what salesData actually holds: sales_weekly's
// unordered pages first, then Shopify, then Walmart, then Chewy. The
// earliest row sits in the MIDDLE of this product's array.
let salesData = {
  A: [
    { week_start: '2026-03-02', channel: 'amazon_us' },
    { week_start: '2024-06-10', channel: 'amazon_us' },   // the real floor
    { week_start: '2026-11-09', channel: 'shopify' },
  ],
  B: [ { week_start: '2025-01-06', channel: 'chewy' } ],
};
const out = {
  shipped: pnlAllTimeFrom(_salesAllTimeRows(), 'week_start'),
  old:     pnlAllTimeFrom(sampled(), 'week_start'),
  rowsReturned: _salesAllTimeRows().length,
};
salesData = {};
out.empty = pnlAllTimeFrom(_salesAllTimeRows(), 'week_start');
salesData = { C: [ { channel: 'shopify' }, { week_start: null } ] };
out.noDates = pnlAllTimeFrom(_salesAllTimeRows(), 'week_start');
salesData = { D: [] };
out.emptyArr = _salesAllTimeRows().length;
console.log(JSON.stringify(out));
""")

# ===========================================================================
print("\nA. /!\\ THE DEFECT: the floor landed after rows that exist")
# ===========================================================================
eq("A1  /!\\ the OLD sampler missed the earliest row entirely - it was neither "
   "first nor last in a FETCH-ordered array", A["old"], "2025-01-06")
eq("A2  /!\\ ...and the shipped one finds it", A["shipped"], "2024-06-10")
ok(A["old"] > A["shipped"],
   "A3  which means All time started LATE, and everything before it vanished "
   "from a total that says All time")

# ===========================================================================
print("\nB. the guards")
# ===========================================================================
eq("B1  no data at all falls back to pnlAllTimeFrom's own floor",
   A["empty"], "1970-01-01")
eq("B2  ...and so does data with no usable date on it", A["noDates"], "1970-01-01")
eq("B3  an empty row array contributes nothing rather than throwing",
   A["emptyArr"], 0)
eq("B4  /!\\ it returns ONE row, not a copy of the feed - this is a floor, "
   "not a dataset", A["rowsReturned"], 1)

# ===========================================================================
print("\nC. no sampling left")
# ===========================================================================
ok("rows[rows.length - 1]" not in ATR,
   "C1  /!\\ the sampler is GONE, not left standing beside the fix")
ok("min === null || v < min" in ATR,
   "C2  the minimum is computed, with the same string compare pnlAllTimeFrom "
   "applies to an ISO date")
ok("allRows: _salesAllTimeRows()" in js,
   "C3  and it is still what the Units Sold window is floored on")
ok(js.count("function _salesAllTimeRows") == 1, "C4  one of it")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
