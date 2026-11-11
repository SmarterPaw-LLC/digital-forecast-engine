#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.02 - TACoS gets its + toggle and a line on the chart.

Jason: "i can't click to add the tacos% to the graph"

v12.00 shipped the card with no `plot`, because the chart's metric list is
derived from the TABLE's columns and TACoS is not a column - it cannot be,
since sales do not belong to a campaign. It needed a series of its own.

/!\ THE TWO WEEK CONVENTIONS ARE ONE DAY APART:
    ads bucket    = SUNDAY  (adsBucketFn: dt.setDate(dt.getDate()-dt.getDay()))
    sku_economics = MONDAY  (Amazon's Sun-Sat week, mapped forward)
Joining them by string would have paired every week's sales with the PREVIOUS
week's spend. Section D drives the real helpers to prove the span approach
catches the right week.

/!\ AND THIS SUITE ASSERTS THE CALLERS, not just the helpers - v12.01 shipped
a crash because test_v1200 proved a helper in isolation and never ran the four
lines that called it.
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


print("\n" + "=" * 68)
print("  v12.02  TACoS is plottable")
print("=" * 68)

SPEC   = const_obj("ADS_METRIC_SPEC")
METFN  = fn_flat("adsChartMetrics")
DIV    = fn_flat("adsDiv")
BRANGE = fn_flat("pnlBucketRange")
BFN    = fn_flat("adsBucketFn")

# ===========================================================================
print("\nA. the metric exists and declares what it needs")
# ===========================================================================
ok("tacos:" in SPEC, "A1  tacos is in the metric registry")
ok("needsNetSales: true" in SPEC,
   "A2  /!\\ ...and DECLARES that its denominator is not in the ads feed")
ok("isPct: true" in SPEC.split("tacos:")[1], "A3  it is a percentage")
ok("noStack: true" in SPEC.split("tacos:")[1],
   "A4  and cannot be stacked (a ratio never stacks)")

# ===========================================================================
print("\nB. the real helpers, driven")
# ===========================================================================
DRIVER = r"""
'use strict';
__DIV__
__SPEC__
__MET__
__BRANGE__
const out = {};
const T = ADS_METRIC_SPEC.tacos;

// --- B the ratio ---------------------------------------------------------
out.normal  = T.sum({ spend: 20312, netSales: 118023 });
out.zeroSp  = T.sum({ spend: 0, netSales: 118023 });
// /!\ A bucket with no sales is a GAP, never 0% - 0.0% would mean "sold
// plenty, spent nothing", a different fact from having no sales figure.
out.zeroNs  = T.sum({ spend: 20312, netSales: 0 });
out.missing = T.sum({ spend: 20312 });

// --- C the metric list ---------------------------------------------------
const COLS = [{ k: 'spend', label: 'Spend' }, { k: 'acos', label: 'ACOS %' },
              { k: 'campaign', label: 'Campaign' }];
out.amazon  = adsChartMetrics(COLS, 'amazon').map(m => m.k);
out.chewy   = adsChartMetrics(COLS, 'chewy').map(m => m.k);
out.walmart = adsChartMetrics(COLS, 'walmart').map(m => m.k);
out.noChan  = adsChartMetrics(COLS).map(m => m.k);
out.amazonLabel = (adsChartMetrics(COLS, 'amazon').find(m => m.k === 'tacos') || {}).label;

// --- D /!\ THE SUNDAY/MONDAY TRAP ----------------------------------------
// The ads bucket for the week of Sun 2026-11-01; sku_economics files that
// same week under Mon 2026-11-02.
out.span = pnlBucketRange('2026-11-01', 'week');
out.mondayInside = (out.span.from <= '2026-11-02' && '2026-11-02' <= out.span.to);
// ...and the PREVIOUS week's Monday must NOT fall inside it.
out.prevMondayOutside = !(out.span.from <= '2026-10-26' && '2026-10-26' <= out.span.to);
// A month bucket spans its whole month.
out.monthSpan = pnlBucketRange('2026-11', 'month');

console.log(JSON.stringify(out));
"""
R = run_node(os.path.join(SP, "_v1202_a.js"),
             DRIVER.replace("__DIV__", DIV).replace("__SPEC__", SPEC)
                   .replace("__MET__", METFN).replace("__BRANGE__", BRANGE))

eq("B1  20,312 over 118,023 is 17.21%", round(R["normal"], 2), 17.21)
eq("B2  zero spend is 0.0%, a real reading", R["zeroSp"], 0)
eq("B3  /!\\ zero net sales is a GAP, not 0%", R["zeroNs"], None)
eq("B4  /!\\ a missing net sales figure is also a gap", R["missing"], None)

print("\nC. offered on Amazon only")
ok("tacos" in R["amazon"], "C1  Amazon offers tacos", R["amazon"])
ok("tacos" not in R["chewy"], "C2  Chewy does not", R["chewy"])
ok("tacos" not in R["walmart"], "C3  Walmart does not", R["walmart"])
ok("tacos" not in R["noChan"], "C4  and neither does a call with no channel")
eq("C5  it is labelled TACoS %", R["amazonLabel"], "TACoS %")
eq("C6  /!\\ the column-derived metrics are unchanged",
   [k for k in R["chewy"]], ["spend", "acos"])

print("\nD. the Sunday/Monday trap")
eq("D1  a Sunday bucket spans Sun to Sat",
   R["span"], {"from": "2026-11-01", "to": "2026-11-07"})
ok(R["mondayInside"],
   "D2  /!\\ the week's sku_economics Monday (11-02) falls INSIDE that span")
ok(R["prevMondayOutside"],
   "D3  /!\\ ...and the PREVIOUS week's Monday (10-26) does not")
eq("D4  a month bucket spans its month",
   R["monthSpan"], {"from": "2026-11-01", "to": "2026-11-30"})

# The convention this depends on, pinned so a change to either side fails here.
ok("dt.setDate(dt.getDate() - dt.getDay());" in BFN,
   "D5  /!\\ the ads bucket really is keyed on the SUNDAY")

# ===========================================================================
print("\nE. the callers - v12.01's lesson")
# ===========================================================================
eq("E1  /!\\ every adsChartMetrics call passes the channel",
   len(re.findall(r"adsChartMetrics\(COLS\)", js)), 0)
# /!\ FOUR matches, not three: the function's own DECLARATION reads the same.
# Counted without it, so adding a fourth caller fails here rather than being
# absorbed into a number that already looked wrong.
eq("E2  ...all three call sites, plus the declaration",
   len(re.findall(r"adsChartMetrics\(COLS, channel\)", js)), 4)
eq("E2b three of those are CALLS",
   len(re.findall(r"(?<!function )adsChartMetrics\(COLS, channel\)", js)), 3)
ok("adsChartMetrics(COLS, channel).map(m =>" in js, "E3  including the metric picker")

# The denominator is attached by SPAN, through the shared helpers.
ok("pnlBucketRange(b, grain)" in js, "E4  the bucket's span comes from pnlBucketRange")
ok("const a = amzFeeAgg(r);" in js,
   "E5  /!\\ and the sales from amzFeeAgg - the SAME aggregator the card uses")
ok("plot.some(x => x.needsNetSales)" in js,
   "E6  /!\\ the scan runs ONLY when a metric that needs it is plotted")
ok("perB[i].netSales = a.tot.netSales || 0;" in js, "E7  ...onto the bucket accumulator")

# /!\ The accumulator must NOT seed netSales, or a bucket the scan skipped
# would read 0 (a real-looking 0% TACoS) instead of absent (a gap).
ACC = js[js.index("const acc = { impressions: 0"):]
ACC = ACC[:ACC.index("};") + 2]
ok("netSales" not in ACC,
   "E8  /!\\ netSales is NOT seeded in the accumulator, so a skipped bucket is a gap")

# ===========================================================================
print("\nF. the toggle, and where it refuses")
# ===========================================================================
ok("plot: plotOf('tacos')," in js, "F1  the card carries the toggle")
PLOTOF = js[js.index("  const plotOf = (k) => {"):]
PLOTOF = PLOTOF[:PLOTOF.index("\n  };") + 4]
ok("if (k === 'tacos') {" in PLOTOF, "F2  tacos has its own refusals")
ok("grain === 'day'" in PLOTOF,
   "F3  /!\\ refused at DAY grain - there is no daily sales figure")
ok("sel && sel.size" in PLOTOF,
   "F4  /!\\ refused while campaigns are selected")
eq("F5  both refusals strip the onclick", PLOTOF.count("onclick: '',"), 2)
ok(PLOTOF.count("disabled: true") >= 2,
   "F6  ...and render disabled rather than vanishing")

# ===========================================================================
print("\nG. the chip agrees with CLAUDE.md")
# ===========================================================================
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "G1  both declare a version")
eq("G2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
