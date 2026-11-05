#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" v11.56 - "only" no longer crosses out the comparison line.

Jason: "when i click to view a stacked option, the comparison period line
should appear for all charts on all views."
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1156_")
s = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

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
    # /!\ Keep the `async` keyword. Dropping it is what test_v1133 had to fix:
    # the slice then parses as a plain function and dies on its own `await`.
    if js[i - 6:i] == "async ":
        i -= 6
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


print("\n" + "=" * 62)
print("  v11.56  a reference line is not a band, and only must not hide it")
print("=" * 62)

# v11.66 — the handlers re-scope the chart's overlay before repainting now.
# A chart that does not publish a resolver (every chart in this suite) is
# byte-identical, which test_v1166 C3 asserts directly.
CORE = (fn("chartLegendIsOverlay") + "\n" + fn("chartLegendSyncOverlay") + "\n"
        + fn("chartLegendSoloed") + "\n"
        + fn("chartLegendOnly") + "\n" + fn("chartLegendToggle") + "\n")

A = run_node(os.path.join(SP, "a.js"), CORE + r"""
function mkChart(datasets) {
  const vis = datasets.map(() => true);
  const c = { data: { datasets }, updates: 0,
    isDatasetVisible: (j) => vis[j],
    setDatasetVisibility: (j, v) => { vis[j] = !!v; },
    update() { c.updates++; },
    vis: () => vis.slice() };
  return c;
}
// SEO Traffic's own shape: three stacked bands plus the prior-year reference.
const SEO = () => mkChart([
  { label: 'Organic Search' },
  { label: 'Direct' },
  { label: 'Paid Social' },
  { label: 'Sessions (prior year)', stack: '_prev' },
]);
// Units Sold's shape: two product lines plus the goal overlay.
const SALES = () => mkChart([
  { label: 'Catnip Spray' }, { label: 'Bubbles' }, { label: 'Goal', stack: '_goal' },
]);
// A chart with NO reference at all - every P&L / Ads surface.
const PLAIN = () => mkChart([{ label: 'A' }, { label: 'B' }, { label: 'C' }]);

const out = {};
out.overlayTest = {
  band: chartLegendIsOverlay({ label: 'Direct' }),
  prev: chartLegendIsOverlay({ label: 'x', stack: '_prev' }),
  goal: chartLegendIsOverlay({ label: 'x', stack: '_goal' }),
  namedStack: chartLegendIsOverlay({ label: 'x', stack: 'sales' }),
  missing: chartLegendIsOverlay(undefined),
};

// 1. THE REPORT: only on a band keeps the comparison line.
let c = SEO();
chartLegendOnly(c, 0);
out.onlyBand = c.vis();
out.onlyBandSoloed = chartLegendSoloed(c, 0);
out.onlyBandUpdates = c.updates;

// 2. and clicking it again puts everything back, reference included.
chartLegendOnly(c, 0);
out.roundTrip = c.vis();

// 3. A reference hidden BY HAND stays hidden - only must not force it back.
c = SEO();
chartLegendToggle(c, 3);
out.afterManualHide = c.vis();
chartLegendOnly(c, 1);
out.onlyWithRefHidden = c.vis();
out.soloedWithRefHidden = chartLegendSoloed(c, 1);
// ...and "all" brings everything back, reference included.
chartLegendOnly(c, 1);
out.allRestoresRef = c.vis();

// 4. only on the REFERENCE itself isolates it, and round-trips.
c = SEO();
out.onlyRefSoloedBefore = chartLegendSoloed(c, 3);
chartLegendOnly(c, 3);
out.onlyRef = c.vis();
out.onlyRefSoloed = chartLegendSoloed(c, 3);
chartLegendOnly(c, 3);
out.onlyRefBack = c.vis();

// 5. The goal overlay on Units Sold behaves identically - "all charts".
c = SALES();
chartLegendOnly(c, 0);
out.salesOnlyBand = c.vis();
out.salesSoloed = chartLegendSoloed(c, 0);

// 6. REGRESSION: a chart with no reference is exactly what v11.55 did.
c = PLAIN();
chartLegendOnly(c, 1);
out.plainOnly = c.vis();
out.plainSoloed = chartLegendSoloed(c, 1);
chartLegendOnly(c, 1);
out.plainBack = c.vis();

// 7. A band hidden by hand is still just hidden - the plain toggle is untouched.
c = SEO();
chartLegendToggle(c, 1);
out.toggleBand = c.vis();
chartLegendToggle(c, 1);
out.toggleBandBack = c.vis();

// 8. The chip's own question, on every state of an isolated band.
c = SEO();
chartLegendOnly(c, 0);
out.chipStates = c.data.datasets.map((_, j) => chartLegendSoloed(c, j));

console.log(JSON.stringify(out));
""")

# ---------------------------------------------------------------------------
# A. What counts as a reference.
# ---------------------------------------------------------------------------
eq("A1 a band is not an overlay", A["overlayTest"]["band"], False)
eq("A1b the prior-year line is", A["overlayTest"]["prev"], True)
eq("A1c so is the sales goal", A["overlayTest"]["goal"], True)
eq("A1d a NAMED stack group is an ordinary stack, not a reference",
   A["overlayTest"]["namedStack"], False)
eq("A1e a missing dataset is not an overlay", A["overlayTest"]["missing"], False)

# ---------------------------------------------------------------------------
# B. THE REPORT, reproduced: only on a band keeps the comparison line.
# ---------------------------------------------------------------------------
eq("B1 only on Organic Search keeps the prior-year line visible",
   A["onlyBand"], [True, False, False, True])
eq("B1b and the chip says 'all', so the way back is still offered",
   A["onlyBandSoloed"], True)
eq("B1c one repaint, not one per series", A["onlyBandUpdates"], 1)
eq("B2 clicking it again restores every band AND the reference",
   A["roundTrip"], [True, True, True, True])

eq("B3 a reference hidden by hand is hidden", A["afterManualHide"],
   [True, True, True, False])
eq("B3b and only does NOT force it back on", A["onlyWithRefHidden"],
   [False, True, False, False])
eq("B3c the chip still reads 'all' there", A["soloedWithRefHidden"], True)
eq("B3d and 'all' means all - the reference comes back with the bands",
   A["allRestoresRef"], [True, True, True, True])

eq("B4 only on the REFERENCE isolates it", A["onlyRef"], [False, False, False, True])
eq("B4b which is soloed, so it round-trips the same way", A["onlyRefSoloed"], True)
eq("B4c and it does", A["onlyRefBack"], [True, True, True, True])

eq("B5 the Units Sold goal behaves identically - 'all charts'",
   A["salesOnlyBand"], [True, False, True])
eq("B5b and reads as soloed", A["salesSoloed"], True)

# ---------------------------------------------------------------------------
# C. A chart with no reference is byte-identical to v11.55.
# ---------------------------------------------------------------------------
eq("C1 a chart with no reference isolates exactly as before",
   A["plainOnly"], [False, True, False])
eq("C1b soloed", A["plainSoloed"], True)
eq("C1c and round-trips", A["plainBack"], [True, True, True])
eq("C2 the plain toggle is untouched - a band hides", A["toggleBand"],
   [True, False, True, True])
eq("C2b and comes back", A["toggleBandBack"], [True, True, True, True])

eq("C3 only the isolated band reads as soloed, not the reference beside it",
   A["chipStates"], [True, False, False, False])
# /!\ The reference's own chip therefore reads "only", not "all" - clicking it
# isolates it. A chart carries one reference, so a mutually-exclusive peer
# rule would have left it with no peers, permanently soloed, and its chip
# saying "all" while doing nothing.
eq("C3b and the reference's chip offers 'only', which does something",
   A["onlyRefSoloedBefore"], False)

# ---------------------------------------------------------------------------
# D. ONE definition, and the overlays it relies on are the real ones.
# ---------------------------------------------------------------------------
code = nocomment(js)
for f in ("chartLegendIsOverlay", "chartLegendSoloed", "chartLegendOnly", "chartLegendToggle"):
    eq("D1 %s defined once" % f, code.count("function %s(" % f), 1)
eq("D2 'soloed' has ONE definition and TWO readers - the action and the chip",
   code.count("chartLegendSoloed("), 3)
ok("chartLegendSoloed(chart, j)" in code,
   "D2b the legend chip asks it rather than counting visible datasets")
ok("live === 1" not in code and "live = vis.reduce" not in code,
   "D3 the retired visible-count rule is gone, not merely unused")
eq("D4 the overlay test is spelled once", code.count("charAt(0) === '_'"), 1)

eq("D5 the app's only reference overlays are the two this relies on",
   sorted(set(re.findall(r"stack:\s*'(_[a-z]+)'", code))), ["_goal", "_prev"])

tg = code[code.index("function chartLegendToggle("):]
tg = tg[:tg.index("\n}") + 2]
ok("chartLegendIsOverlay" not in tg,
   "D6 the plain toggle knows nothing about overlays - hiding one by hand still works")

# ---------------------------------------------------------------------------
# E. The STACKED TOTAL stops counting the reference line.
#    Found by reading a driven tooltip, not by an assertion: Jason's own
#    screenshot showed Total 4,918 against 3,406 of channels + 1,512 prior year.
# ---------------------------------------------------------------------------
E = run_node(os.path.join(SP, "e.js"), r"""
'use strict';
let SEEN = null;
class Chart {
  constructor(ctx, cfg) { SEEN = cfg; this.canvas = ctx.__canvas; }
  destroy() {}
  static getChart() { return null; }
}
const getChart = async () => Chart;
const pnlBucketGrain = () => 'week';
const pnlPickBucket = () => {};
const CHART_HTML_LEGEND = { id: 'htmlLegend' };
const CANVAS = { title: '', style: {}, getContext() { return { __canvas: CANVAS }; } };
global.document = { getElementById: () => CANVAS };
""" + re.search(r"const PNL_SCALE_GRACE = '[^']+';", js).group(0) + "\n"
      + re.search(r"const PNL_SCALE_HEADROOM = [0-9.]+;", js).group(0) + "\n"
      + fn("pnlScaleCeiling") + "\n"
      + fn("chartLegendIsOverlay") + "\n" + fn("pnlTrendRender") + r"""

// Jason's own screenshot, verbatim.
const CHANNELS = [['Other',11],['Referral',30],['Organic Social',139],['Unassigned',26],
                  ['Paid Search',2],['Paid Social',397],['Cross-network',396],
                  ['Direct',435],['Organic Search',1970]];
const ITEMS = CHANNELS.map(([label, y]) => ({ dataset: { label }, parsed: { y } }));
const PREV = { dataset: { label: 'Sessions (prior year)', stack: '_prev' }, parsed: { y: 1512 } };

(async () => {
  const out = {};
  await pnlTrendRender({ canvasId: 'c', buckets: ['2024-06-17'], mode: 'stacked', unit: '',
    datasets: [{ label: 'a', data: [1] }, { label: 'b', data: [2] }] });
  const foot = SEEN.options.plugins.tooltip.callbacks.footer;
  out.withReference = foot(ITEMS.concat([PREV]));
  out.channelsOnly  = foot(ITEMS);
  // The PRE-v11.56 rule, reproduced, so "this was wrong" is a measurement.
  const old = (items) => 'Total: ' + items.reduce((a, i) => a + (Number(i.parsed.y) || 0), 0).toLocaleString();
  out.oldWithReference = old(ITEMS.concat([PREV]));
  // A LINE chart has no total at all, unchanged.
  await pnlTrendRender({ canvasId: 'c', buckets: ['2024-06-17'], mode: 'line', unit: '',
    datasets: [{ label: 'a', data: [1] }] });
  out.lineFooter = SEEN.options.plugins.tooltip.callbacks.footer === undefined ? 'undefined' : 'present';
  console.log(JSON.stringify(out));
})();
""")

eq("E1 /!\\ THE DEFECT, reproduced: the old rule added last year to this year",
   E["oldWithReference"], "Total: 4,918")
eq("E2 the total is now the STACK, and only the stack",
   E["withReference"], "Total: 3,406")
eq("E2b which is exactly what the channels alone come to",
   E["channelsOnly"], E["withReference"])
eq("E3 a line chart still has no total footer", E["lineFooter"], "undefined")

eq("D7 version chip", len(re.findall(r">v11\.\d+ · [\d-]+<", s)), 1)
for phrase in ('does not mean "and hide what I am',
               '"all" means all - references included'):
    ok(phrase in js, "D8 the reasoning survives: %s" % phrase[:40])

print("\n" + "=" * 62)
print("  v11.56  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
