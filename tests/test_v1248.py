#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.48 - the SEO chart draws the PREVIOUS PERIOD too.

- **Jason**, twice: *"the previous period data points never show in the hover
  window"* ... *"i still am not seeing the comparison period datapoint in the
  hover over window"*

v12.42 dated the PRIOR-YEAR line and his screenshot shows that working
(`Sessions (prior year) - 4/28/25: 4,366`). The line he has been asking for
is the other one: **vs prev period**, the block immediately before this
window, which this chart had never fetched and whose control was greyed out.

Two comparisons, two sets of rows, two lines - never one control carrying
both meanings.
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
print("  v12.48  two comparisons, two lines")
print("=" * 70)

# ===========================================================================
print("\nA. /!\\ A CHART CAN CARRY TWO OVERLAYS NOW")
# ===========================================================================
A = run_node(os.path.join(SP, "_v1248_a.js"),
             fn_flat("chartLegendIsOverlay") + "\n" + fn_flat("chartLegendVisibleBands") + r"""
const mk = (ds, vis) => ({ data: { datasets: ds }, isDatasetVisible: (j) => !vis || vis(j) });
const band = (l) => ({ label: l });
const year = { stack: '_prev',  label: 'Sessions (prior year)' };
const perd = { stack: '_prevp', label: 'Previous period (2026-03-01 -> 2026-04-26)' };
console.log(JSON.stringify({
  none: chartLegendVisibleBands(mk([band('a'), band('b')])),
  one:  chartLegendVisibleBands(mk([band('a'), band('b'), year])),
  two:  chartLegendVisibleBands(mk([band('a'), band('b'), year, perd])),
  // One band hidden, with BOTH overlays present: narrowed must fire on the
  // bands alone.
  twoNarrow: chartLegendVisibleBands(mk([band('a'), band('b'), year, perd], (j) => j !== 1)),
  // ...and a chart where only the overlays are visible is NOT narrowed.
  onlyOverlays: chartLegendVisibleBands(mk([band('a'), band('b'), year, perd], (j) => j >= 2)),
}));
""")
eq("A1  with ONE overlay the answer is byte-identical to v12.47 - index 2, "
   "two bands, not narrowed",
   [A["one"]["overlayIndex"], A["one"]["bands"], A["one"]["narrowed"]], [2, 2, False])
eq("A2  /!\\ with TWO, the second is NOT counted as a band",
   [A["two"]["overlayIndex"], A["two"]["bands"]], [2, 2])
eq("A3  ...and it is excluded from the drawable indices",
   A["two"]["idx"], [0, 1])
eq("A4  /!\\ overlayIndex stays the FIRST overlay, which is the one each sync "
   "rewrites - the prior-year line is pushed before the period one",
   A["two"]["overlayIndex"], 2)
eq("A5  both are reported, so a future sync can address either",
   A["two"]["overlays"], [2, 3])
eq("A6  /!\\ narrowing fires on the BANDS, not on the overlay count",
   [A["twoNarrow"]["narrowed"], A["twoNarrow"]["labels"]], [True, ["a"]])
eq("A7  ...and hiding every band is not 'narrowed to nothing'",
   A["onlyOverlays"]["narrowed"], False)
eq("A8  no overlay at all still reports -1", A["none"]["overlayIndex"], -1)

# ===========================================================================
print("\nB. which rows the previous-period line describes")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1248_b.js"), r"""
let PICK = { chan: '', dev: '' };
const document = { getElementById: (id) =>
  id === 'seo-tr-chan' ? { value: PICK.chan }
  : id === 'seo-tr-dev' ? { value: PICK.dev } : null };
let seoTrSel = { dim: '', keys: new Set(), pages: new Set() };
const D = (day, x) => Object.assign({ day, sessions: 0 }, x);
let seoTr = {
  pp:     [D('2026-03-02', { sessions: 900 })],
  ppChan: [D('2026-03-02', { channel: 'Organic Search', sessions: 300 }),
           D('2026-03-02', { channel: null,             sessions: 600 })],
  ppDev:  [D('2026-03-02', { device: 'mobile', sessions: 400 })],
  pages:  [D('2026-03-02', { landing_page: '/a', channel: 'Direct', sessions: 11 })],
};
""" + fn_flat("seoTrScopeSel") + "\n" + fn_flat("seoTrPrevPeriodRows") + r"""
const sum = (rs) => rs.reduce((a, r) => a + (r.sessions || 0), 0);
const clear = () => { seoTrSel = { dim: '', keys: new Set(), pages: new Set() };
                      PICK = { chan: '', dev: '' }; };
const go = (set) => { clear(); set(); return sum(seoTrPrevPeriodRows()); };
console.log(JSON.stringify({
  site:   go(() => {}),
  tick:   go(() => { seoTrSel = { dim: 'channel', keys: new Set(['Organic Search']), pages: new Set() }; }),
  tickNull: go(() => { seoTrSel = { dim: 'channel', keys: new Set(['(not set)']), pages: new Set() }; }),
  dev:    go(() => { seoTrSel = { dim: 'device', keys: new Set(['mobile']), pages: new Set() }; }),
  pick:   go(() => { PICK.chan = 'Organic Search'; }),
  both:   go(() => { PICK.chan = 'Organic Search'; PICK.dev = 'mobile'; }),
  pages:  go(() => { seoTrSel = { dim: '', keys: new Set(), pages: new Set(['/a']) }; }),
}));
""")
eq("B1  nothing selected is the site's own previous period", B["site"], 900)
eq("B2  a ticked channel narrows to it", B["tick"], 300)
eq("B3  /!\\ through the same '(not set)' fallback the rollups use - GA4 "
   "writes nulls, and a key mismatch draws a blank line that reads as 'no "
   "traffic last period'", B["tickNull"], 600)
eq("B4  a ticked device narrows to it", B["dev"], 400)
eq("B5  a dropdown pick narrows the same way", B["pick"], 300)
eq("B6  a dropdown pair has nothing to draw", B["both"], 0)
eq("B7  /!\\ and a PAGE selection has no previous period either - that feed "
   "is not fetched for any comparison window (v11.65)", B["pages"], 0)
ok("seoTrScopeSel()" in fn_flat("seoTrPrevPeriodRows"),
   "B8  /!\\ it reads the SAME decision this year and last year read, so "
   "three lines cannot describe three populations")

# ===========================================================================
print("\nC. the fetch is paid for only when it is wanted")
# ===========================================================================
LOAD = fn_flat("loadSeoTraffic")
ok("pnlChartCompare()" in LOAD and "getPnlPrevDateRange({ from: w.from, to: w.to })" in LOAD,
   "C1  the previous window comes from the shared resolver, not a fourth "
   "copy of the arithmetic")
ok("? seoFetchAll(table" in LOAD and "Promise.resolve([])" in LOAD,
   "C2  /!\\ and with Compare off the three extra reads do not happen - this "
   "page's heaviest feeds, on a page whose refresh time is a standing "
   "complaint")
ok("!w.allTime" in LOAD,
   "C3  all time has nothing before it, so nothing is fetched for it")
eq("C4  three extra feeds, no more", LOAD.count("ppFetch("), 3)
ok("ppFetch('ga4_by_date_landing_page'" not in LOAD,
   "C5  /!\\ and NOT the landing-page feed, which is the heaviest and whose "
   "selection draws no line anyway")

# ===========================================================================
print("\nD. /!\\ ALL TIME IS A FLAG, NOT A LABEL")
# ===========================================================================
WIN = fn_flat("seoTrWindow")
ok("allTime: _allTime" in WIN,
   "D1  the window reports it")
ok("label = 'All time'; _allTime = true;" in WIN,
   "D2  ...set where all-time is decided")
ok("w.label === 'All time'" not in js,
   "D3  /!\\ and nothing keys the comparison on the DISPLAY STRING, which a "
   "rename would silently break")

# ===========================================================================
print("\nE. the line, and the control that asks for it")
# ===========================================================================
RC = fn_flat("seoTrRenderChart")
ok("const _seoCmp = (w.from && w.to && !w.allTime)" in RC,
   "E1  the control is OFFERED now, and refused only where there is nothing "
   "before the window")
ok("pnlInjectChartModeToggle('seo-tr-mode', 'renderSeoTraffic', !canStack, 'channel groups',\n    _seoCmp," in RC,
   "E2  ...through the shared toggle, not a second control shape")
ok("The previous period is not fetched for GA4" not in js,
   "E3  /!\\ and the old refusal is GONE, not left on the tooltip of a "
   "control that now works")
ok("stack: '_prevp'" in RC,
   "E4  /!\\ the new line gets its OWN stack group - two datasets in one "
   "group stack on each other, and the chart would read as last year PLUS "
   "the period before")
ok("stack: '_prev'" in js,
   "E5  ...and the prior-year line keeps the group it had")
ok("pnlPrevOverlay(ppb.map(k => ppm.get(k)), buckets, ppb)" in RC,
   "E6  /!\\ built by the SHARED overlay helper, so it aligns by POSITION "
   "the way every other previous-period line does - and it inherits the "
   "$pairKeys v12.42 added, which is what puts the date in the tooltip")
ok(RC.index("datasets.push({ label: prevLabel") < RC.index("stack: '_prevp'"),
   "E7  the prior-year line is pushed FIRST, which is what makes "
   "overlayIndex the one its own sync owns")
ok("seoTrPpLoading" in RC and "loadSeoTraffic(true);" in RC,
   "E8  /!\\ switching Compare on against a cache fetched without it RELOADS "
   "rather than drawing nothing and saying nothing (v10.19)")
ok("!seoTr.ppWin && seoTrLoaded && !seoTrPpLoading" in RC,
   "E9  ...guarded, so the render that asks cannot ask again before it lands")
ok("seoTrPpLoading = false;" in LOAD,
   "E10 and the loader clears the flag, so a failed load does not wedge it")

# ===========================================================================
print("\nF. and the page says which comparisons are on it")
# ===========================================================================
ok("' \\u00b7 vs prev period'" in RC,
   "F1  the sub-line names the second comparison when it is drawn")
ok("prior year " in RC,
   "F2  ...beside the one that is always on")
NO_C = strip_comments(js)
eq("F3  one previous-period resolver on this page",
   NO_C.count("function seoTrPrevPeriodRows"), 1)
eq("F4  one prior-year resolver", NO_C.count("function seoTrPrevRows"), 1)

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
