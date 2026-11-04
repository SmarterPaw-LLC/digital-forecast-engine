#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.55 - the trend charts get headroom, so a peak is not drawn clipped.

Jason: "also the top of the graph is cut off."
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1155_")
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
    while i > 0 and js[i - 1] not in "\n":
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


print("\n" + "=" * 62)
print("  v11.55  headroom above the data, so a peak is not clipped")
print("=" * 62)

# The SHIPPED declaration, lifted rather than retyped, so this suite cannot
# pass against a value the app does not use.
GRACE_DECL = re.search(r"const PNL_SCALE_GRACE = '[^']+';", js).group(0)
# v11.63 - pnlTrendRender now asks pnlScaleCeiling for a suggestedMax, so the
# harness slices it too. The dependency is real and the harness follows it
# (the v10.43 / v10.45 / v10.97 pattern).
HEAD_DECL = re.search(r"const PNL_SCALE_HEADROOM = [0-9.]+;", js).group(0)
CEILING = HEAD_DECL + "\n" + fn("pnlScaleCeiling")

# ---------------------------------------------------------------------------
# A. The real pnlTrendRender driven, Chart stubbed to capture the config.
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, "a.js"), r"""
'use strict';
let SEEN = null;
class Chart {
  constructor(ctx, cfg) { SEEN = cfg; this.canvas = ctx.__canvas; }
  destroy() {}
  static getChart() { return null; }
}
const getChart = async () => Chart;
const pnlBucketGrain = () => 'day';
const pnlPickBucket = () => {};
const CHART_HTML_LEGEND = { id: 'htmlLegend' };
const CANVAS = { title: '', style: {}, getContext() { return { __canvas: CANVAS }; } };
global.document = { getElementById: () => CANVAS };

""" + GRACE_DECL + "\n" + CEILING + "\n" + fn("pnlTrendRender") + r"""

const B = ['2026-10-01', '2026-10-02', '2026-10-03'];
(async () => {
  const out = { grace: PNL_SCALE_GRACE };

  // Single-y: every caller that declares no axes.
  await pnlTrendRender({ canvasId: 'c', buckets: B, mode: 'line', isPct: false, unit: '$',
    datasets: [{ label: 'Spend', data: [1, 2, 3] }] });
  out.y = { grace: SEEN.options.scales.y.grace,
            beginAtZero: SEEN.options.scales.y.beginAtZero,
            stacked: SEEN.options.scales.y.stacked,
            keys: Object.keys(SEEN.options.scales.y).sort() };
  // /!\ A category axis must NOT get headroom - there is no room between
  // buckets to give, and a padded x axis would invent space beside real data.
  out.xHasGrace = 'grace' in SEEN.options.scales.x;
  out.scaleKeys = Object.keys(SEEN.options.scales).sort();

  // A PERCENTAGE chart is not pinned to zero, so grace moves both ends.
  await pnlTrendRender({ canvasId: 'c', buckets: B, mode: 'line', isPct: true, unit: '%',
    datasets: [{ label: 'Margin', data: [1, 2, 3] }] });
  out.pct = { grace: SEEN.options.scales.y.grace, beginAtZero: SEEN.options.scales.y.beginAtZero };

  // Stacked, which is the mode Jason was looking at.
  await pnlTrendRender({ canvasId: 'c', buckets: B, mode: 'stacked', isPct: false, unit: '',
    datasets: [{ label: 'A', data: [1, 2, 3] }, { label: 'B', data: [1, 2, 3] }] });
  out.stacked = { grace: SEEN.options.scales.y.grace, y: SEEN.options.scales.y.stacked };

  // Multi-axis (v11.33): the same smoothed lines, so the same headroom.
  await pnlTrendRender({ canvasId: 'c', buckets: B, mode: 'line', unit: '$',
    datasets: [{ label: 'Spend', data: [1, 2, 3], yAxisID: 'y_spend' },
               { label: 'ROAS',  data: [1, 2, 3], yAxisID: 'y_roas' }],
    axes: [{ id: 'y_spend', unit: '$', isPct: false },
           { id: 'y_roas',  unit: 'x', isPct: false },
           { id: 'y_acos',  unit: '%', isPct: true }] });
  out.axes = Object.entries(SEEN.options.scales)
    .filter(([k]) => k !== 'x')
    .map(([k, v]) => [k, v.grace === undefined ? null : v.grace]);
  out.axesXHasGrace = 'grace' in SEEN.options.scales.x;
  console.log(JSON.stringify(out));
})();
""")

GRACE = A["grace"]
ok(isinstance(GRACE, str) and GRACE.endswith("%"),
   "A0 the headroom is a PERCENTAGE of the range, not an absolute amount",
   GRACE)
ok(0 < float(GRACE[:-1]) <= 10,
   "A0b and a small one - this is headroom, not a rescale", GRACE)

eq("A1 the single-y scale carries it", A["y"]["grace"], GRACE)
eq("A1b and still begins at zero", A["y"]["beginAtZero"], True)
eq("A1c the scale set is unchanged", A["scaleKeys"], ["x", "y"])
ok(not A["xHasGrace"],
   "A2 /!\\ the CATEGORY axis does not - there is no room between buckets to give")

eq("A3 a percentage chart gets it too", A["pct"]["grace"], GRACE)
eq("A3b and is NOT pinned to zero, so the floor moves with the ceiling",
   A["pct"]["beginAtZero"], False)

eq("A4 stacked - the mode the clipping was reported on", A["stacked"]["grace"], GRACE)
eq("A4b still stacked", A["stacked"]["y"], True)

eq("A5 every declared axis carries it (v11.33 draws the same curves)",
   sorted(A["axes"]), sorted([["y_spend", GRACE], ["y_roas", GRACE], ["y_acos", GRACE]]))
ok(not A["axesXHasGrace"], "A5b and the x axis still does not")

# ---------------------------------------------------------------------------
# B. ONE number, named once.
# ---------------------------------------------------------------------------
code = nocomment(js)
eq("B1 declared exactly once", code.count("const PNL_SCALE_GRACE"), 1)
eq("B2 and read in exactly two places - both scale paths",
   code.count("grace: PNL_SCALE_GRACE"), 2)
ok(re.search(r"grace:\s*['\"0-9]", code) is None,
   "B3 never written as a literal beside the shared one")
ok(code.index("const PNL_SCALE_GRACE") < code.index("async function pnlTrendRender("),
   "B4 declared before its only reader - a const in TDZ would throw on every chart")

# ---------------------------------------------------------------------------
# C. The reasoning, and the measurement that produced the number.
# ---------------------------------------------------------------------------
# /!\ v11.60 REWORDED one of these because it was WRONG. "A percentage of the
# RANGE" is not what Chart.js does - it is a percentage of HALF the range - and
# sizing the constant against that belief is why Jason reported the chart still
# cut off. The phrase this pinned is gone on purpose; what it was really
# protecting (most charts do not move) is pinned as a MEASUREMENT below.
for phrase in ("A peak drawn with a flat top is not a peak",
               "GRACE IS A PERCENTAGE OF HALF THE RANGE",
               "FLOOR down (62.4% max kept its 65 tick"):
    ok(phrase in js, "C1 the reasoning survives: %s" % phrase[:42])

ok("FIVE OF SIX ARE BYTE-IDENTICAL" in js,
   "C1b and the no-change claim is a measurement, not an assertion")
ok("it costs nothing on a chart that already has room" not in js,
   "C1c the WRONG claim is gone rather than left beside the right one")

# ---------------------------------------------------------------------------
# v11.60 - THE VALUE HAS A MEASURED FLOOR, and it is not a matter of taste.
#
# /!\ Chart.js computes grace as toDimension(grace, (max - min) / 2), so the
# declared percentage buys HALF that much headroom. v11.55 declared '5%'
# believing it was a percentage of the range; it bought 2.5%, and at the worst
# case - a peak just under a tick boundary - that is 2.44%, about 6px, which
# is what Jason was still looking at one release later.
#
# Measured on the REAL seoTrRenderChart with a stacked peak of 4,878:
#     '5%'  -> scale max 5,000, 6.1px of headroom
#     '10%' -> scale max 6,000, 29.4px
# and five of six other chart shapes are byte-identical between the two.
#
# /!\ v11.63: THAT MEASUREMENT WAS TRUE AND IT DID NOT GENERALISE. Grace is
# applied BEFORE the nice-tick rounding, so how much of it survives depends on
# where the graced max falls against the next tick. 4,878 is the LUCKIEST peak
# in the range - measured over twelve peaks on Chart.js 4.6.1, grace '10%'
# alone delivers between 6.0% and 18.7%, and Jason's own chart (peak 4,660)
# got 6.8% and still read as cut off. So grace is KEPT - it is what moves the
# FLOOR on a non-zero axis, which A3b pins - but it is no longer the thing
# that guarantees the top. Section D is.
_pct = int(re.search(r"const PNL_SCALE_GRACE = '(\d+)%';", js).group(1))
ok(_pct >= 10, "C3 grace is at least the measured 10%% (halved by Chart.js to 5%%)", _pct)
ok("A LOTTERY" in js or "lottery" in js,
   "C3b the source says why grace ALONE is not a guarantee")
ok("4,660" in js, "C3c and cites the peak that disproved the v11.60 claim")

eq("C2 version chip", len(re.findall(r">v11\.\d+ · [\d-]+<", s)), 1)

# ---------------------------------------------------------------------------
# D. v11.63 - THE REAL pnlScaleCeiling, driven.
#
# A suggestedMax is a FLOOR the data max is raised to before the ticks are
# built, so the snapped tick is always >= it: snapping can then only ADD
# headroom, never remove it.
# ---------------------------------------------------------------------------
D = run_node(os.path.join(SP, "d.js"), CEILING + r"""
const bands = [{ label:'a', data:[1865, 900] },
               { label:'b', data:[840, 400] },
               { label:'c', data:[1955, 700] }];
const withPrev = bands.concat([{ label:'prev', stack:'_prev', data:[3635, 1800] }]);
const out = {
  stacked:        pnlScaleCeiling(bands, true),
  stackedOverlay: pnlScaleCeiling(withPrev, true),
  unstacked:      pnlScaleCeiling(withPrev, false),
  empty:          pnlScaleCeiling([], true),
  noDatasets:     pnlScaleCeiling(null, true),
  allNull:        pnlScaleCeiling([{ data:[null, undefined] }], true),
  allNegative:    pnlScaleCeiling([{ data:[-5, -9] }], false),
  zeroes:         pnlScaleCeiling([{ data:[0, 0] }], true),
  objectPoints:   pnlScaleCeiling([{ data:[{x:1,y:200},{x:2,y:400}] }], false),
  missingData:    pnlScaleCeiling([{ label:'no data' }, { data:[50] }], false),
  perAxis:        pnlScaleCeiling(
      [{ data:[10,20], yAxisID:'ySpend' }, { data:[9000,9500], yAxisID:'ySales' }],
      false, 'ySpend'),
  raggedRows:     pnlScaleCeiling([{ data:[1,2,3] }, { data:[10] }], true),
};
console.log(JSON.stringify(out));
""")

PEAK = 1865 + 840 + 1955          # 4,660 - Jason's own peak
eq("D1 a stacked chart is sized to the SUM of its bands",
   D["stacked"]["suggestedMax"], PEAK * 1.15)
# /!\ The v11.56 defect, one level down: an overlay is a REFERENCE, not a
# band. Summing the prior-year line into the stack would size the axis to this
# year PLUS last year.
eq("D2 /!\\ an overlay is NOT summed into the bands",
   D["stackedOverlay"]["suggestedMax"], PEAK * 1.15)
eq("D3 unstacked takes the largest single value",
   D["unstacked"]["suggestedMax"], 3635 * 1.15)
eq("D4 a declared axis reads only ITS OWN datasets",
   D["perAxis"]["suggestedMax"], 20 * 1.15)
eq("D5 {x,y} points are read too", D["objectPoints"]["suggestedMax"], 400 * 1.15)
# Ragged rows: the loop runs to the LONGEST series in the group, so the short
# one stacks where it has a value (1 + 10 at index 0) and the long one's later
# buckets are still considered rather than being cut off with it.
eq("D6 ragged rows iterate to the LONGEST series",
   D["raggedRows"]["suggestedMax"], (1 + 10) * 1.15)
eq("D7 a dataset with no data array is skipped, not thrown on",
   D["missingData"]["suggestedMax"], 50 * 1.15)

# /!\ NO CEILING IS AN ANSWER. An empty, all-null, all-zero or all-negative
# series has no top edge to clip against, and raising its max would stretch
# the axis away from the data - a chart emptier than the one it replaced
# (v10.19). Each must return {} so Chart.js keeps its own sizing.
for key, why in [("empty", "no datasets"), ("noDatasets", "a null datasets list"),
                 ("allNull", "every value null"), ("allNegative", "an all-negative series"),
                 ("zeroes", "an all-zero series")]:
    eq("D8 no suggestedMax for %s" % why, D[key], {})

# One definition, both scale paths - and never a literal beside it.
eq("D9 declared exactly once", code.count("function pnlScaleCeiling("), 1)
eq("D9b read by BOTH scale paths", code.count("...pnlScaleCeiling("), 2)
eq("D9c the headroom constant is named once",
   code.count("const PNL_SCALE_HEADROOM"), 1)
ok(re.search(r"suggestedMax:\s*[0-9]", code) is None,
   "D10 no hardcoded suggestedMax anywhere")
eq("D10b suggestedMax is spelled in exactly one place", code.count("suggestedMax"), 1)
ok(code.index("function pnlScaleCeiling(") < code.index("async function pnlTrendRender("),
   "D11 declared before its readers")
_head = float(re.search(r"const PNL_SCALE_HEADROOM = ([0-9.]+);", js).group(1))
ok(0.10 <= _head <= 0.30,
   "D12 the headroom is a sane fraction, not a rescale", _head)

print("\n" + "=" * 62)
print("  v11.55  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
