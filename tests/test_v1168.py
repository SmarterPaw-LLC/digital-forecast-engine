#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.68 - a previous-period comparison you can toggle, on the shared renderer.

Jason: "allow me to toggle comparison over previous period on all graphs."

The scorecards above these charts have read "+34.3% vs prev" since v10.13. The
chart underneath them never drew it.

  * A  the control: OFF by default, one state for every chart, and a chart
       that cannot compare renders it DISABLED with the reason (v10.19).
  * B  /!\ the overlay aligns by POSITION, not by date - the prior window is a
       different stretch of calendar and not one of its bucket keys matches.
  * C  the real pnlPrevVals: summed across products THEN measured, so a
       percentage metric is not averaged across products.
  * D  the wiring: every chart resolves its previous period through the ONE
       resolver the scorecards use, and pushes the overlay LAST.
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


def fn(name):
    i = js.index("function " + name + "(")
    while i > 0 and js[i - 1] != "\n":
        i -= 1
    d, started, k = 0, False, js.index("{", js.index("function " + name + "("))
    while k < len(js):
        if js[k] == "{":
            d += 1; started = True
        elif js[k] == "}":
            d -= 1
            if started and d == 0:
                return js[i:k + 1]
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
print("  v11.68  the previous-period comparison, on every chart")
print("=" * 68)

NC = nocomment(js)


# ===========================================================================
print("\nA. the control: one state, off by default, refused with a reason")
# ===========================================================================
A = run_node(os.path.join(SP, "_v1168_a.js"),
    "const STORE = {};\nglobalThis.localStorage = { getItem: k => (k in STORE ? STORE[k] : null),"
    " setItem: (k, v) => { STORE[k] = String(v); } };\n"
    + fn("esc2") + "\n" + fn("pnlChartCompare") + "\n" + fn("pnlSetChartCompare") + "\n"
    + fn("pnlCompareToggleHtml") + r"""
const out = {};
let RERENDERS = 0;
globalThis.window = { reRender: () => { RERENDERS++; } };
out.defaultOff = pnlChartCompare();
// A chart that passes nothing gets NO control - not a dead one.
out.noCmp = pnlCompareToggleHtml('reRender', undefined);
// Available, and off.
out.offHtml = pnlCompareToggleHtml('reRender', { ok: true });
pnlSetChartCompare(true, 'reRender');
out.afterSet = pnlChartCompare();
out.rerenders = RERENDERS;
out.onHtml = pnlCompareToggleHtml('reRender', { ok: true });
// /!\ Refused: the stored preference is irrelevant, the control must be dead.
out.deadHtml = pnlCompareToggleHtml('reRender', { ok: false, why: 'An "All time" window has no previous period.' });
// The state is ONE value, not one per chart.
out.sharedAcrossCharts = pnlCompareToggleHtml('aaa', { ok: true }).includes('var(--sp-green)')
                      && pnlCompareToggleHtml('bbb', { ok: true }).includes('var(--sp-green)');
pnlSetChartCompare(false, 'reRender');
out.backOff = pnlChartCompare();
// A storage that throws must not take the page with it.
globalThis.localStorage = { getItem() { throw new Error('blocked'); },
                            setItem() { throw new Error('blocked'); } };
out.throwsSafe = (function () { try { pnlSetChartCompare(true, 'reRender'); return pnlChartCompare() === false; }
                                catch (e) { return 'THREW'; } })();
console.log(JSON.stringify(out));
""")

eq("A1  /!\\ OFF by default - eight charts do not grow a line unasked",
   A["defaultOff"], False)
eq("A2  /!\\ a chart that passes no cmp gets NO control at all", A["noCmp"], "")
ok("vs prev period" in A["offHtml"], "A3  an available control is drawn", A["offHtml"])
ok("pnlSetChartCompare(true," in A["offHtml"], "A3b and offers to turn it ON")
eq("A4  setting it stores and re-renders once", [A["afterSet"], A["rerenders"]], [True, 1])
ok("pnlSetChartCompare(false," in A["onHtml"], "A4b once on, the same control offers to turn it OFF")
ok("var(--sp-green)" in A["onHtml"], "A4c and reads as active")
# /!\ BOTH HALVES. A disabled control that still carries its handler is
# bypassable from the console (v10.19 / v11.57).
ok("onclick" not in A["deadHtml"], "A5  /!\\ a refused control carries NO handler", A["deadHtml"])
ok("not-allowed" in A["deadHtml"], "A5b and says so with its cursor")
ok("All time" in A["deadHtml"], "A5c and names the reason on its tooltip")
eq("A6  one state, read the same by every chart", A["sharedAcrossCharts"], True)
eq("A6b and it turns back off", A["backOff"], False)
eq("A7  a storage that throws leaves it OFF rather than throwing",
   A["throwsSafe"], True)


# ===========================================================================
print("\nB. /!\\ the overlay aligns by POSITION, never by date")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1168_b.js"), fn("pnlPrevOverlay") + r"""
const out = {};
// The prior window is a DIFFERENT stretch of calendar: not one of these keys
// appears in the current window's, which is why a date join draws nothing.
const CUR  = ['2026-10-05', '2026-10-12', '2026-10-19', '2026-10-26'];
const PREV = ['2026-09-07', '2026-09-14', '2026-09-21', '2026-09-28'];
out.paired = pnlPrevOverlay([10, 20, 30, 40], CUR, PREV);
// A live window usually has MORE buckets than its predecessor (this week so
// far). The tail has no partner and must be null, not zero.
out.shortPrev = pnlPrevOverlay([10, 20], CUR, PREV.slice(0, 2));
// /!\ AND FEWER, which is the case a browser run caught MISLABELLED: the
// current window is truncated by where the data stops while its predecessor
// is complete, so only its first buckets are drawn - and the label has to
// say which, or the chart misreports its own axis.
const LONG = PREV.concat(['2026-10-05p', '2026-10-12p']);
out.longPrev = pnlPrevOverlay([10, 20, 30, 40, 50, 60], CUR.slice(0, 3), LONG);
out.stack = out.paired.stack;
out.dashed = out.paired.borderDash;
out.notFilled = out.paired.fill;
// Nothing to draw is NOTHING, not an empty line on the legend.
out.emptyVals = pnlPrevOverlay([], CUR, PREV);
out.allNull = pnlPrevOverlay([null, null, null, null], CUR, PREV);
out.noBuckets = pnlPrevOverlay([1, 2], [], PREV);
out.missing = pnlPrevOverlay(null, CUR, PREV);
// No prior keys at all: it still draws, under a generic name.
out.noKeys = pnlPrevOverlay([10, 20, 30, 40], CUR, null).label;
// A hole INSIDE the prior period stays a hole - spanGaps false.
out.holey = pnlPrevOverlay([10, null, 30, 40], CUR, PREV).data;
out.spanGaps = pnlPrevOverlay([10, null, 30, 40], CUR, PREV).spanGaps;
console.log(JSON.stringify(out));
""")

eq("B1  bucket 1 meets bucket 1", B["paired"]["data"], [10, 20, 30, 40])
# /!\ THE LABEL NAMES WHAT WAS DRAWN, and it is derived inside the helper so
# it cannot drift from the data beside it.
eq("B1b under a label naming the prior buckets it paired",
   B["paired"]["label"], "Previous period (2026-09-07 → 2026-09-28)")
# /!\ v11.42 / v11.56: without its own stack group Chart.js folds the
# reference into the stack and the chart reads as this period PLUS last.
eq("B2  /!\\ it sits in its OWN stack group", B["stack"], "_prev")
eq("B2b drawn as a dashed line", B["dashed"], [5, 4])
eq("B2c and never filled", B["notFilled"], False)
eq("B3  /!\\ a tail with no partner is NULL, not zero",
   B["shortPrev"]["data"], [10, 20, None, None])
eq("B3b and the label names only the buckets that WERE paired",
   B["shortPrev"]["label"], "Previous period (2026-09-07 → 2026-09-14)")
eq("B4  /!\\ surplus prior buckets are dropped, never shifted",
   B["longPrev"]["data"], [10, 20, 30])
# The defect a browser run caught: three current buckets drawn against a
# six-bucket predecessor, labelled with the whole prior range.
eq("B4b and the label names the THREE it drew, not the six it was given",
   B["longPrev"]["label"], "Previous period (2026-09-07 → 2026-09-21)")
eq("B5  a hole inside the prior period stays a hole", B["holey"], [10, None, 30, 40])
eq("B5b so the line breaks rather than bridging it", B["spanGaps"], False)
eq("B6  with no prior keys it still draws, under a generic name",
   B["noKeys"], "Previous period")
for k, why in [("emptyVals", "no prior values"), ("allNull", "every prior value null"),
               ("noBuckets", "no current buckets"), ("missing", "no prior array at all")]:
    eq("B7  %s draws NOTHING, not an empty legend entry" % why, B[k], None)


# ===========================================================================
print("\nC. the real pnlPrevVals: summed THEN measured")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1168_b2.js"), fn("pnlSlotAdd") + "\n" + fn("pnlPrevVals") + r"""
const out = {};
const perProd = {
  A: { w1: { netSales: 100, cogs: 40 }, w2: { netSales: 200, cogs: 50 } },
  B: { w1: { netSales: 300, cogs: 60 }, w2: { netSales: 100, cogs: 90 } },
};
const BUCKETS = ['w1', 'w2'];
const money = (s) => s.netSales || 0;
// A PERCENTAGE: the trap. Per product w1 is 60% and 80%; the honest answer
// for the pair is (400-100)/400 = 75%, not the 70% an average would give.
const pct = (s) => (s.netSales > 0 ? ((s.netSales - (s.cogs || 0)) / s.netSales * 100) : null);
out.money = pnlPrevVals(perProd, BUCKETS, ['A', 'B'], money);
out.pct = pnlPrevVals(perProd, BUCKETS, ['A', 'B'], pct);
out.avgWouldBe = [(60 + 80) / 2, ((200 - 50) / 200 * 100 + (100 - 90) / 100 * 100) / 2];
// A selection of one measures only that one.
out.oneOnly = pnlPrevVals(perProd, BUCKETS, ['A'], money);
// A product with no slot in a bucket contributes nothing and does not throw.
out.missingSlot = pnlPrevVals(perProd, ['w1', 'w3'], ['A', 'B'], money);
// A product that is not in the map at all.
out.unknownMid = pnlPrevVals(perProd, BUCKETS, ['A', 'ZZZ'], money);
// No mids: every bucket measures an empty slot, which a % reports as null.
out.noMids = pnlPrevVals(perProd, BUCKETS, [], pct);
console.log(JSON.stringify(out));
""")

eq("C1  dollars sum across the products in scope", C["money"], [400, 300])
# /!\ THE TRAP: a percentage cannot be averaged across products (the v10.12
# rule the bands already follow). 75% is the pair's real margin.
eq("C2  /!\\ a percentage is derived from the SUM, never averaged",
   [round(C["pct"][0], 2), round(C["pct"][1], 2)], [75.0, 53.33])
ok(C["pct"][0] != C["avgWouldBe"][0],
   "C2b and that is a different number from the average", C["avgWouldBe"])
eq("C3  a selection measures only what is selected", C["oneOnly"], [100, 200])
eq("C4  a bucket a product never reached contributes nothing", C["missingSlot"], [400, 0])
eq("C5  a product that is not in the map does not throw", C["unknownMid"], [100, 200])
eq("C6  and an empty scope reports null on a percentage, not zero",
   C["noMids"], [None, None])


# ===========================================================================
print("\nD. the wiring: one resolver, pushed LAST, on every chart")
# ===========================================================================
# /!\ The chart and the chip above it must describe the SAME previous period,
# so every chart resolves it through the resolver the scorecards already use.
CHARTS = [("updatePnlChart", "_pnlPrevR", "_pnlCmpOn", "pnlBucketize"),
          ("updateShopifyPnlChart", "_spnlPrevR", "_spnlCmpOn", "spnlBucketize"),
          ("updateWalmartPnlChart", "_wmpnlPrevR", "_wmpnlCmpOn", "wmpnlBucketize"),
          ("updateChewyPnlChart", "_chpnlPrevR", "_chpnlCmpOn", "chpnlBucketize")]
for name, prevR, cmpOn, bucketize in CHARTS:
    body = fn(name)
    ok("getPnlPrevDateRange({ from, to })" in body,
       "D1  %s resolves the prior window through the SHARED resolver" % name)
    ok("pnlPrevOverlay(" in body, "D1b and builds the overlay through the shared helper")
    ok(body.count("%s(" % bucketize) == 2,
       "D1c and runs ONE accumulation over TWO windows, not two spellings of it",
       body.count("%s(" % bucketize))
    # Pushed LAST: the stacked fill chain is index-relative (v11.42).
    ok(body.index("built.datasets.push(") > body.index("pnlTrendSeries({"),
       "D1d and pushes the overlay AFTER the bands are built")

# The ads chart reads the prev rollup the delta chips already read.
adsb = fn("adsUpdateChart")
ok("const { ch, channel, view, COLS, res, win, list, sel, grain, totals, prev } = ctx;" in adsb,
   "D2  the ads chart receives the prior rollup rather than recomputing one")
ok("prev.series" in adsb and "prev.buckets" in adsb,
   "D2b and reads its SERIES, which is why the prev call gained a bucket grain")
ok("bucket: grain" in js, "D2c the prev rollup is bucketed")

# Every surface passes a cmp, so none of them shows a stale or missing control.
calls = re.findall(r"pnlInjectChartModeToggle\(((?:[^()]|\([^()]*\))*)\)", NC)
calls = [c for c in calls if "hostId" not in c]
eq("D3  seven chart surfaces inject the toggle", len(calls), 7)
withcmp = [c for c in calls if "ok:" in c]
eq("D3b and every one of them declares whether it can compare", len(withcmp), 7)

# /!\ The one chart that already compares says what it compares against.
seo = [c for c in calls if "seo-tr-mode" in c]
ok(seo and "PRIOR YEAR" in seo[0],
   "D4  /!\\ the SEO chart refuses with the comparison it DOES draw", seo)
# An All-time window has no previous period, which is already why the chips
# suppress themselves there (v10.13).
ok(NC.count("!_pnlSuppressDeltas") >= 4,
   "D5  the All-time case is read from the flag the chips already use",
   NC.count("!_pnlSuppressDeltas"))

for f in ("pnlChartCompare", "pnlSetChartCompare", "pnlCompareToggleHtml",
          "pnlPrevOverlay", "pnlPrevVals"):
    eq("D6  %s defined once" % f, NC.count("function %s(" % f), 1)
eq("D6b and the overlay dataset has ONE spelling", NC.count("stack: '_prev'"), 2)
ok("ALIGNS BY POSITION, NOT BY DATE" in js,
   "D7  the alignment rule is written where the overlay is built")

r = subprocess.run(["node", "--check", os.path.join(SP, "_v1168_a.js")],
                   capture_output=True, text=True)
ok(r.returncode == 0, "D8  the sliced source parses", r.stderr[-300:])

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
