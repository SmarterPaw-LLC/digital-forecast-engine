#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.15 - TACoS plots on Chewy and Walmart too.

Jason: "i can't add tacos to the line chart for chewy" - with the card right
beside it reading 16.2% of $111,226 our revenue, so the number existed and
only the + was missing.

Two things kept it off, both v12.02's and both Amazon-shaped:

  1. adsChartMetrics appended `tacos` only when channel === 'amazon'.
  2. the chart's per-bucket denominator came from amzFeeAgg, which is
     Amazon's own aggregate and knows nothing about the 1P sell-through feeds.

/!\ AND THE FIX IS NOT A QUERY PER BUCKET. These feeds are weekly, so one
query returns the weeks and every bucket is summed from them in the browser -
the same shape v12.02 used for Amazon, where amzFeeAgg reads a cache rather
than the network. A round trip per point on a line is not a chart.
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


def fn_flat(name):
    i = js.index("function " + name + "(")
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def line_of(pat):
    for ln in js.split("\n"):
        if pat in ln:
            return ln
    raise SystemExit("not found: " + pat)


def const_obj(name):
    i = js.index("const " + name + " = {")
    return js[i:js.index("\n};", i) + 3]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.15  TACoS is plottable on the 1P channels")
print("=" * 70)

DRIVER = r"""
'use strict';
__SPEC__
__DIV__
__TACOSSRC__
__METRICS__
__OURREVKEY__
const _adsOurRev = {};
__OURREVFOR__
__BUCKET__
__BRANGE__

const out = {};
const COLS = [{ k: 'spend', label: 'Spend' }, { k: 'acos', label: 'ACOS %' }];

// --- A offered wherever it can be computed -------------------------------
for (const ch of ['amazon', 'walmart', 'chewy', 'shopify']) {
  out['has_' + ch] = adsChartMetrics(COLS, ch).some(m => m.k === 'tacos');
}
out.label = (adsChartMetrics(COLS, 'chewy').find(m => m.k === 'tacos') || {}).label;

// --- B the bucket denominator, from the cached weeks ---------------------
// Four weeks, keyed on the MONDAY the way chewy_sales_weekly is.
const W = { from: '2026-10-05', to: '2026-11-01' };
_adsOurRev['chewy|2026-10-05|2026-11-01'] = {
  rev: 400, retail: 900, weeks: [
    { w: '2026-10-05', rev: 100, retail: 220 },
    { w: '2026-10-12', rev: 110, retail: 230 },
    { w: '2026-10-19', rev: 90,  retail: 210 },
    { w: '2026-10-26', rev: 100, retail: 240 },
  ], why: null };

// /!\ THE SUNDAY/MONDAY TRAP, which is why this is matched by SPAN not key.
// An ads bucket for the week of Sun 2026-10-04 contains the Monday 10-05.
const sun = pnlBucketRange('2026-10-04', 'week');
out.sunSpan = sun;
out.sunBucket = adsOurRevBucket('chewy', W, sun.from, sun.to);
// ...and the NEXT Sunday bucket must pick up the NEXT Monday, not the same one.
const sun2 = pnlBucketRange('2026-10-11', 'week');
out.sun2Bucket = adsOurRevBucket('chewy', W, sun2.from, sun2.to);

// A month bucket gathers every week starting inside it.
const oct = pnlBucketRange('2026-10', 'month');
out.monthSpan = oct;
out.monthBucket = adsOurRevBucket('chewy', W, oct.from, oct.to);

// /!\ A BUCKET WITH NO WEEK IN IT IS A GAP, NOT 0.
out.emptyBucket = adsOurRevBucket('chewy', W, '2026-12-01', '2026-12-07');
// ...and so is a window that was never fetched, or one still in flight.
out.noFetch = adsOurRevBucket('chewy', { from: '1999-01-01', to: '1999-01-07' }, '1999-01-01', '1999-01-07');
_adsOurRev['chewy|1999-02-01|1999-02-07'] = { pending: true };
out.pending = adsOurRevBucket('chewy', { from: '1999-02-01', to: '1999-02-07' }, '1999-02-01', '1999-02-07');

// --- C the metric itself -------------------------------------------------
const T = ADS_METRIC_SPEC.tacos;
out.ratio  = T.sum({ spend: 110, netSales: 100 });
out.gapNs  = T.sum({ spend: 110, netSales: 0 });
out.absent = T.sum({ spend: 110 });
console.log(JSON.stringify(out));
"""

A = run_node(os.path.join(SP, "_v1215_a.js"),
             DRIVER.replace("__SPEC__", const_obj("ADS_METRIC_SPEC"))
                   .replace("__DIV__", fn_flat("adsDiv"))
                   .replace("__TACOSSRC__", const_obj("TACOS_SRC"))
                   .replace("__METRICS__", fn_flat("adsChartMetrics"))
                   .replace("__OURREVKEY__", fn_flat("_adsOurRevKey"))
                   .replace("__OURREVFOR__", fn_flat("adsOurRevFor"))
                   .replace("__BUCKET__", fn_flat("adsOurRevBucket"))
                   .replace("__BRANGE__", fn_flat("pnlBucketRange")))

# ===========================================================================
print("\nA. the + is offered wherever TACoS can be computed")
# ===========================================================================
ok(A["has_amazon"], "A1  Amazon, as before")
ok(A["has_chewy"], "A2  /!\\ Chewy - the one Jason could not plot")
ok(A["has_walmart"], "A3  /!\\ and Walmart")
ok(not A["has_shopify"], "A4  /!\\ but not a channel with no sales feed")
eq("A5  labelled TACoS %", A["label"], "TACoS %")
# /!\ ONE REGISTRY. The card and the chart metric are gated on the SAME
# TACOS_SRC, so a channel can never have the card without the + again.
MET = fn_flat("adsChartMetrics")
ok("TACOS_SRC[channel]" in MET,
   "A6  /!\\ gated on the same registry the CARD uses, so the two cannot "
   "disagree about where TACoS belongs")
# /!\ The string survives in the COMMENT that explains what it used to be,
# which is the point of the comment - so the CODE is what is checked.
MET_NC = "\n".join(ln for ln in MET.split("\n") if not ln.strip().startswith("//"))
ok("channel === 'amazon'" not in MET_NC,
   "A7  ...and the Amazon-only test is gone from the CODE")

# ===========================================================================
print("\nB. the bucket denominator - by SPAN, not by key")
# ===========================================================================
eq("B1  a Sunday bucket spans Sun to Sat", A["sunSpan"],
   {"from": "2026-10-04", "to": "2026-10-10"})
# /!\ ads buckets are keyed on the SUNDAY and these sales weeks on the MONDAY.
# Matching by string would pair every week with the wrong one.
eq("B2  /!\\ and picks up the Monday inside it", A["sunBucket"], 100)
eq("B3  /!\\ the next Sunday picks up the NEXT Monday, not the same one",
   A["sun2Bucket"], 110)
eq("B4  a month bucket gathers every week starting inside it",
   A["monthBucket"], 400)
eq("B5  ...over its own span", A["monthSpan"], {"from": "2026-10-01", "to": "2026-10-31"})
# /!\ v11.16: a bucket with no denominator is a GAP. Zero would draw a point
# at 0% TACoS, which reads as "spent nothing".
eq("B6  /!\\ a bucket with no week in it is a GAP, never 0", A["emptyBucket"], None)
eq("B7  ...so is a window nothing fetched", A["noFetch"], None)
eq("B8  ...and one still in flight", A["pending"], None)

print("\nC. the metric")
# Floating point: 110/100*100 is 110.00000000000001.
eq("C1  110 over 100 is 110%", round(A["ratio"], 6), 110)
eq("C2  /!\\ zero sales is a gap, not 0%", A["gapNs"], None)
eq("C3  ...and an absent figure too", A["absent"], None)

# ===========================================================================
print("\nD. the chart reads the CHANNEL'S feed, not Amazon's")
# ===========================================================================
ok("if (channel === 'amazon') {\n            if (typeof amzFeeAgg !== 'function') return;" in js,
   "D1  Amazon keeps amzFeeAgg")
ok("const v = adsOurRevBucket(channel, { from: win.from, to: win.to }, r.from, r.to);" in js,
   "D2  /!\\ and the 1P channels read their own weeks")
ok("if (plot.some(x => x.needsNetSales)) {" in js,
   "D3  the scan still runs only when TACoS is actually plotted")
ok("if (v != null) perB[i].netSales = v;" in js,
   "D4  /!\\ a null bucket is left ABSENT, so the line draws a gap not a zero")

# ===========================================================================
print("\nE. one query for the window, not one per bucket")
# ===========================================================================
LOAD = fn_flat("adsLoadOurRev")
ok("group by 1 order by 1" in LOAD, "E1  Walmart groups by week")
ok("group by 1, 2 order by 1" in LOAD, "E2  Chewy groups by week and sku")
ok("weeks: wk," in LOAD, "E3  the weeks are cached on the window's entry")
# /!\ THE TOTAL IS THE SUM OF THE WEEKS. Two ways to total the same rows is
# two numbers that can disagree - and the card and the chart would be the two
# surfaces showing them.
ok("rev: wk.reduce((t, x) => t + x.rev, 0)" in LOAD,
   "E4  /!\\ and the TOTAL is the sum of those weeks, not a second aggregate")
# /!\ An unpriced SKU is counted once, not once per week it sold in.
ok("unpricedSet.add(row.master_id)" in LOAD,
   "E5  /!\\ an unpriced SKU is counted ONCE, not once per week it sold in")
ok("pricedSet.size" in LOAD, "E6  ...and so is a priced one")

print("\nF. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "F1  both declare a version")
eq("F2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
