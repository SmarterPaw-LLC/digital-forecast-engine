#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.85 - the Y axis follows what is drawn, and a Lock for when it must not.

- Jason: "when i drill in, the chart doesn't update granularity to adjust for
  the smaller totals" ... "i would like options to lock it vs not too"

v11.63 replaced Chart.js's grace lottery with suggestedMax computed ONCE at
render from the full dataset array. A suggestedMax is a FLOOR the axis is
raised to - which is why it fixed the clipping - so hiding bands could never
lower it again.

  * A  static: the rescale runs from both legend gestures, AFTER the overlay
       sync, and honours the lock.
  * B  the real pnlScaleCeiling with a visibility test.
  * C  the real chartRescaleY on a chart double: fit, lock, multi-axis, and
       the axes v11.63 deliberately left alone.
  * D  the regression guard: the pre-v11.85 ceiling run beside the shipped one
       on an isolated band.
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
    return _bal(js.index(kw + " " + name + "("))


NC = nocomment(js)

# ---------------------------------------------------------------------------
print("A. static")
# ---------------------------------------------------------------------------
eq("A1  chartRescaleY declared exactly once", NC.count("function chartRescaleY("), 1)
eq("A2  pnlChartScaleLock declared once", NC.count("function pnlChartScaleLock("), 1)
eq("A3  the control is declared once", NC.count("function pnlScaleToggleHtml("), 1)
# Scoped to the injector itself: `host.innerHTML` appears all over the file,
# and splitting on the LAST one lands somewhere else entirely.
inj = nocomment(fn("pnlInjectChartModeToggle"))
ok("pnlScaleToggleHtml(rerenderName)" in inj,
   "A4  ...and rendered in the one shared control row (hard rule #1)")
ok("mode === 'stacked' ? pnlScaleToggleHtml" not in inj,
   "A4b /!\ ...in BOTH modes, unlike FILL - hiding a LINE pins the axis too")

tog = nocomment(fn("chartLegendToggle"))
only = nocomment(fn("chartLegendOnly"))
for nm, body in (("toggle", tog), ("only", only)):
    ok("chartRescaleY(chart)" in body, "A5  the legend %s rescales" % nm)
    ok(body.index("chartLegendSyncOverlay") < body.index("chartRescaleY"),
       "A6  /!\\ ...AFTER the overlay sync, which rewrites the line's own data")
    ok(body.index("chartRescaleY") < body.index("chart.update()"),
       "A7  ...and BEFORE the repaint, so one update paints the new axis")

resc = nocomment(fn("chartRescaleY"))
ok("if (pnlChartScaleLock()) return;" in resc,
   "A8  /!\\ locked, it does nothing at all - the render-time ceiling IS the lock")
ok("sc.suggestedMax == null" in resc,
   "A9  /!\\ an axis v11.63 left alone stays left alone (empty / all-negative)")
ok("next.suggestedMax != null" in resc,
   "A10 /!\\ nothing visible keeps the old ceiling rather than dropping it")
ok("chart.isDatasetVisible(i)" in resc,
   "A11 visibility comes from the CHART, not from a copy of it")
ok("id === 'x'" in resc, "A12 the x axis is never given a ceiling")

ceil = fn("pnlScaleCeiling")
ok("visible" in ceil.split("{")[0],
   "A13 pnlScaleCeiling takes the visibility test as an argument")
ok("typeof visible !== 'function'" in ceil,
   "A14 /!\\ ...and no argument means EVERY dataset - the render-time behaviour")

# Rule #2: the GROUP stepper already has an Auto.
ctl = fn("pnlScaleToggleHtml")
ok("'Fit'" in ctl and "'Auto'" not in ctl,
   "A15 /!\\ the button says Fit, not Auto - GROUP already has an Auto in the "
   "same strip")
ok("'Lock'" in ctl, "A16 ...and Lock")
ok("Fit is the default" in js or "=== '1'" in nocomment(fn("pnlChartScaleLock")),
   "A17 Fit is the default - the pre-v11.63 behaviour, and what he expected")

m = re.search(r">v(\d+\.\d+) · [\d-]+<", s)
cl = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
cm = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cl)
eq("A18 /!\\ the version chip AGREES with CLAUDE.md",
   m.group(1) if m else None, cm.group(1) if cm else None)

# ---------------------------------------------------------------------------
print("\nB + C. the real helpers, driven")
# ---------------------------------------------------------------------------
B = r"""
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}
const PNL_SCALE_HEADROOM = __HEADROOM__;
let LOCK = false;
function pnlChartScaleLock() { return LOCK; }
__CEIL__
__RESC__

const big   = { label: 'big',   data: [60000, 62000], stack: 's' };
const mid   = { label: 'mid',   data: [ 4000,  4200], stack: 's' };
const small = { label: 'small', data: [ 1200,  1300], stack: 's' };
const prev  = { label: 'prev',  data: [50000, 51000], stack: '_prev' };
const DS = [big, mid, small];

const r2 = x => Math.round(x * 100) / 100;

// -- B. the ceiling itself ------------------------------------------------
t('B1  stacked, everything: the column total plus headroom',
  r2(pnlScaleCeiling(DS, true).suggestedMax), r2(67500 * (1 + PNL_SCALE_HEADROOM)));
t('B2  /!\\ only the small band visible: the ceiling FOLLOWS it',
  r2(pnlScaleCeiling(DS, true, null, (d) => d.label === 'small').suggestedMax),
  r2(1300 * (1 + PNL_SCALE_HEADROOM)));
t('B3  two bands visible: their column, not the whole one',
  r2(pnlScaleCeiling(DS, true, null, (d) => d.label !== 'big').suggestedMax),
  r2(5500 * (1 + PNL_SCALE_HEADROOM)));
t('B4  no visibility test means every dataset - the render-time answer',
  pnlScaleCeiling(DS, true).suggestedMax, pnlScaleCeiling(DS, true, null, null).suggestedMax);
t('B5  nothing visible has no ceiling to give', pnlScaleCeiling(DS, true, null, () => false), {});
t('B6  /!\\ an OVERLAY is its own column, never summed into the bands',
  r2(pnlScaleCeiling([...DS, prev], true).suggestedMax),
  r2(67500 * (1 + PNL_SCALE_HEADROOM)));
t('B7  ...and when the bands are hidden the overlay still sets the floor',
  r2(pnlScaleCeiling([...DS, prev], true, null, (d) => d.stack === '_prev').suggestedMax),
  r2(51000 * (1 + PNL_SCALE_HEADROOM)));
t('B8  unstacked reads the tallest POINT, not a sum',
  r2(pnlScaleCeiling(DS, false).suggestedMax), r2(62000 * (1 + PNL_SCALE_HEADROOM)));
t('B9  an all-negative series gets no ceiling',
  pnlScaleCeiling([{ data: [-5, -9] }], false), {});
t('B10 an empty one neither', pnlScaleCeiling([], false), {});

// -- C. chartRescaleY on a chart double -----------------------------------
function mkChart(datasets, scales, hidden) {
  const h = new Set(hidden || []);
  return {
    data: { datasets },
    options: { scales },
    isDatasetVisible: (i) => !h.has(i),
    _hide: (i) => h.add(i),
  };
}
const FULL = r2(67500 * (1 + PNL_SCALE_HEADROOM));
const SMALL = r2(1300 * (1 + PNL_SCALE_HEADROOM));

LOCK = false;
let c = mkChart(DS, { x: {}, y: { stacked: true, suggestedMax: FULL } }, [0, 1]);
chartRescaleY(c);
t('C1  /!\\ hiding the big bands lowers the axis - the whole complaint',
  r2(c.options.scales.y.suggestedMax), SMALL);

c = mkChart(DS, { x: {}, y: { stacked: true, suggestedMax: FULL } }, []);
chartRescaleY(c);
t('C2  everything visible round-trips to the full ceiling',
  r2(c.options.scales.y.suggestedMax), FULL);

LOCK = true;
c = mkChart(DS, { x: {}, y: { stacked: true, suggestedMax: FULL } }, [0, 1]);
chartRescaleY(c);
t('C3  /!\\ LOCKED, the axis does not move', r2(c.options.scales.y.suggestedMax), FULL);
LOCK = false;

// An axis v11.63 gave no ceiling must not gain one here.
c = mkChart(DS, { x: {}, y: { stacked: true } }, [0, 1]);
chartRescaleY(c);
t('C4  /!\\ an axis with no ceiling stays without one',
  c.options.scales.y.suggestedMax === undefined, true);

// Nothing visible: keep what is there rather than letting it clip.
c = mkChart(DS, { x: {}, y: { stacked: true, suggestedMax: FULL } }, [0, 1, 2]);
chartRescaleY(c);
t('C5  /!\\ nothing visible keeps the old ceiling', r2(c.options.scales.y.suggestedMax), FULL);

// Multi-axis: each one measured over the datasets that sit on IT.
const a1 = { label: 'a', data: [100, 120], yAxisID: 'y',  stack: 'A' };
const a2 = { label: 'b', data: [  3,   4], yAxisID: 'y2', stack: 'B' };
c = mkChart([a1, a2], { x: {}, y: { suggestedMax: 999 }, y2: { suggestedMax: 999 } }, []);
chartRescaleY(c);
t('C6  /!\\ a second axis is measured over ITS OWN datasets',
  [r2(c.options.scales.y.suggestedMax), r2(c.options.scales.y2.suggestedMax)],
  [r2(120 * (1 + PNL_SCALE_HEADROOM)), r2(4 * (1 + PNL_SCALE_HEADROOM))]);

c = mkChart([a1, a2], { x: {}, y: { suggestedMax: 999 }, y2: { suggestedMax: 999 } }, [0]);
chartRescaleY(c);
t('C7  ...and hiding one axis’s series leaves the other alone',
  r2(c.options.scales.y2.suggestedMax), r2(4 * (1 + PNL_SCALE_HEADROOM)));

t('C8  a chart with no scales at all is a no-op, not a throw',
  (() => { try { chartRescaleY({}); chartRescaleY(null); return 'ok'; } catch (e) { return String(e); } })(), 'ok');

// -- D. the regression guard ----------------------------------------------
// The pre-v11.85 ceiling took no visibility test, so isolating a band left
// the axis exactly where the full population put it.
function v1163Ceiling(datasets, stacked) { return pnlScaleCeiling(datasets, stacked); }
t('D1  /!\\ the OLD rule really does hold the axis at the full ceiling',
  r2(v1163Ceiling(DS, true).suggestedMax), FULL);
t('D2  ...where the new one follows the isolated band',
  r2(pnlScaleCeiling(DS, true, null, (d) => d.label === 'small').suggestedMax), SMALL);
t('D3  /!\\ and they AGREE when nothing is hidden - no chart moved by default',
  r2(v1163Ceiling(DS, true).suggestedMax),
  r2(pnlScaleCeiling(DS, true, null, () => true).suggestedMax));

console.log(JSON.stringify(out));
"""
head = re.search(r"(?m)^const PNL_SCALE_HEADROOM\s*=\s*([0-9.]+)", js)
B = (B.replace("__HEADROOM__", head.group(1) if head else "0.15")
      .replace("__CEIL__", fn("pnlScaleCeiling"))
      .replace("__RESC__", fn("chartRescaleY")))
p = os.path.join(SP, "_v1185_b.js")
io.open(p, "w", encoding="utf-8", newline="").write(B)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-3000:]); print(r.stderr[-3000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
