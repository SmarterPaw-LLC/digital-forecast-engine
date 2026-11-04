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

""" + GRACE_DECL + "\n" + fn("pnlTrendRender") + r"""

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
_pct = int(re.search(r"const PNL_SCALE_GRACE = '(\d+)%';", js).group(1))
ok(_pct >= 10, "C3 grace is at least the measured 10%% (halved by Chart.js to 5%%)", _pct)

eq("C2 version chip", len(re.findall(r">v11\.\d+ · [\d-]+<", s)), 1)

print("\n" + "=" * 62)
print("  v11.55  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
