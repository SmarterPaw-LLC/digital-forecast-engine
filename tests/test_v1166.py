#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.66 - the prior-year line is the prior year OF THE BANDS THAT ARE DRAWN.

Jason: "when i filter to a channel it is still showing the prior period TOTAL
FOR ALL CHANNELS, not the prior period for the filtered channel."

v11.61 scoped that line to the dropdown pick and to the ticked rows. The
LEGEND was never on that list. `only` and a plain toggle change dataset
VISIBILITY, and the `_prev` dataset's DATA is whatever the last full render
computed - sitewide, when nothing is picked. So isolating Organic Search in
the legend drew 546 against a prior year of 6,559, which is the whole site.

v11.56 made the reference survive an isolation. It never asked "the reference
OF WHAT", and that is this release.

  * A  THE DEFECT REPRODUCED. The pre-v11.66 chartLegendOnly is run beside the
       shipped one on the same chart, so "it was showing the site's" is a
       measurement rather than a reading.
  * B  the REAL seoTrOverlaySync over ten states, with the numbers checked
       against channel-filtered sums - including Other as a COMPLEMENT, a band
       with no prior-year rows at all, and both round trips.
  * C  the REAL chartLegendOnly / chartLegendToggle: they sync, they sync
       BEFORE the repaint, a chart that did not opt in is byte-identical, and
       a throwing resolver cannot stop the update.
  * D  the REAL seoTrRenderChart: which views publish a resolver, which
       publish null, and the end-to-end measurement through a real isolation.
  * E  static: one definition each, one publisher, the retired rollup gone,
       the reasoning survives, node --check.
"""
import io, os, re, sys, json, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(ROOT, "index.html")
s    = io.open(SRC, encoding="utf-8", newline="").read()
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
    # /!\ LINE comments only - stripping block comments from this file eats
    # 824,674 characters (v11.63).
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
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v11.66  the prior year follows the bands that are drawn")
print("=" * 68)

NC = nocomment(js)

# v11.69 - seoTrOverlaySync asks the SHARED "which bands are still drawn"
# read now, because the P&L charts grew the same question and a second
# copy of the narrowing rule is how the two would drift apart. The
# harness slices it; what this suite owns is unchanged.

# A stub chart with the four methods the legend uses, and an ops log, so the
# ORDER of sync-then-repaint is read off the log rather than off the source.
CHART = r"""
const OPS = [];
function mkChart(datasets) {
  const hidden = new Set();
  return {
    data: { datasets }, options: {}, updates: 0,
    isDatasetVisible: j => !hidden.has(j),
    setDatasetVisibility: (j, v) => { if (v) hidden.delete(j); else hidden.add(j); },
    update() { this.updates++; OPS.push('update'); },
    show(labels) {
      hidden.clear();
      datasets.forEach((d, j) => { if (labels.indexOf(String(d.label)) < 0) hidden.add(j); });
    },
  };
}
globalThis.console = Object.assign({}, console, { warn: (...a) => OPS.push('warn') });
"""

# Last year's channel feed. +364 days puts 2025-10-02 on 2026-10-01 and
# 2025-10-03 on 2026-10-02, which is v11.41's 52-whole-weeks shift.
FEED = r"""
const pc = (d, c, n) => ({ day: d, channel: c, sessions: n });
const P1 = '2025-10-02', P2 = '2025-10-03';
const PREV_CHAN = [
  pc(P1, 'Organic Search', 500), pc(P2, 'Organic Search', 520),
  pc(P1, 'Direct', 300),         pc(P2, 'Direct', 310),
  pc(P1, 'Email', 100),          pc(P2, 'Email', 110),
  pc(P1, 'SMS', 50),             pc(P2, 'SMS', 60),
];
const BUCKETS = ['2026-10-01', '2026-10-02'];
const shift = (k) => { const x = new Date(k + 'T00:00:00'); x.setDate(x.getDate() + 364);
  return `${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`; };
const toData = (rs) => {
  const m = new Map();
  for (const r of rs) { const k = shift(r.day); m.set(k, (m.get(k) || 0) + Number(r.sessions || 0)); }
  return BUCKETS.map(b => m.has(b) ? m.get(b) : null);
};
const KEEP = ['Organic Search', 'Direct', 'Paid Shopping'];
const FNS = new Map(KEEP.map(g => [g, r => (r.channel || '(not set)') === g]));
FNS.set('Other', r => !KEEP.includes(r.channel || '(not set)'));
const BASE_LABEL = 'Sessions (prior year)';
const CTX = { src: PREV_CHAN, fns: FNS, noun: 'channel', baseRows: PREV_CHAN,
              baseLabel: BASE_LABEL, toData };
const bands = () => [
  { label: 'Organic Search' }, { label: 'Direct' },
  { label: 'Paid Shopping' },  { label: 'Other' },
  { label: BASE_LABEL, stack: '_prev', data: toData(PREV_CHAN) },
];
"""


# ===========================================================================
print("\nA. /!\\ THE DEFECT, REPRODUCED - the legend never reached the line")
# ===========================================================================
A = run_node(os.path.join(SP, "_v1166_a.js"), CHART + FEED
   + fn("chartLegendIsOverlay") + "\n" + fn("chartLegendSoloed") + "\n"
   + fn("chartLegendSyncOverlay") + "\n" + fn("chartLegendOnly") + "\n"
   + fn("seoTrSelNoun") + "\n" + fn("chartLegendVisibleBands") + chr(10) + fn("seoTrOverlaySync") + r"""
// The pre-v11.66 chartLegendOnly, character for character minus the one line
// this release adds. Visibility only - which is the defect.
function chartLegendOnlyOLD(chart, i) {
  const ds = chart.data.datasets || [];
  const soloed = chartLegendSoloed(chart, i);
  const mine = chartLegendIsOverlay(ds[i]);
  for (let j = 0; j < ds.length; j++) {
    if (soloed) { chart.setDatasetVisibility(j, true); continue; }
    if (!mine && j !== i && chartLegendIsOverlay(ds[j])) continue;
    chart.setDatasetVisibility(j, j === i);
  }
  chart.update();
}
const out = {};
// Jason's own gesture: `only` on Organic Search.
const oldC = mkChart(bands());
oldC.$overlaySync = (c) => seoTrOverlaySync(c, CTX);
chartLegendOnlyOLD(oldC, 0);
out.oldVisible = oldC.data.datasets.map((d, j) => oldC.isDatasetVisible(j));
out.oldPrev    = oldC.data.datasets[4].data;
out.oldLabel   = oldC.data.datasets[4].label;

const newC = mkChart(bands());
newC.$overlaySync = (c) => seoTrOverlaySync(c, CTX);
chartLegendOnly(newC, 0);
out.newVisible = newC.data.datasets.map((d, j) => newC.isDatasetVisible(j));
out.newPrev    = newC.data.datasets[4].data;
out.newLabel   = newC.data.datasets[4].label;
out.siteTotal  = toData(PREV_CHAN);
console.log(JSON.stringify(out));
""")

eq("A1  both isolate the same band and keep the reference line visible",
   [A["oldVisible"], A["newVisible"]],
   [[True, False, False, False, True]] * 2)
# /!\ THE DEFECT. 950/1000 is every channel last year; 500/520 is Organic
# Search's own. The old code drew the first beside a band that is the second.
eq("A2  /!\\ pre-v11.66 the line stayed SITEWIDE", A["oldPrev"], A["siteTotal"])
eq("A2b and said so only in the most general terms", A["oldLabel"], "Sessions (prior year)")
eq("A3  /!\\ v11.66 draws that channel's own prior year", A["newPrev"], [500, 520])
eq("A3b and the line names the population it is comparing against",
   A["newLabel"], "Organic Search (prior year)")
ok(A["oldPrev"] != A["newPrev"], "A4  so the two are measurably different", A["oldPrev"])


# ===========================================================================
print("\nB. the real seoTrOverlaySync, over every shape the legend can reach")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1166_b.js"), CHART + FEED
   + fn("chartLegendIsOverlay") + "\n" + fn("seoTrSelNoun") + "\n"
   + fn("chartLegendVisibleBands") + chr(10) + fn("seoTrOverlaySync") + r"""
const out = {};
const run = (labels, ctx) => {
  const c = mkChart(bands());
  c.show(labels);
  seoTrOverlaySync(c, ctx || CTX);
  const o = c.data.datasets[4];
  return { data: o.data, label: o.label };
};
out.all        = run(['Organic Search', 'Direct', 'Paid Shopping', 'Other', BASE_LABEL]);
out.soloOrganic= run(['Organic Search', BASE_LABEL]);
out.soloDirect = run(['Direct', BASE_LABEL]);
out.twoBands   = run(['Organic Search', 'Direct', BASE_LABEL]);
out.soloOther  = run(['Other', BASE_LABEL]);
out.soloEmpty  = run(['Paid Shopping', BASE_LABEL]);
out.noBands    = run([BASE_LABEL]);
// /!\ The unplaceable band has to be a real dataset, or `show` simply never
// makes it visible and the fallback is never exercised.
const uk = mkChart(bands().concat([{ label: 'Made Up Band' }]));
uk.show(['Organic Search', 'Made Up Band', BASE_LABEL]);
seoTrOverlaySync(uk, CTX);
out.unknown = { data: uk.data.datasets[4].data, label: uk.data.datasets[4].label };
// The round trip has to restore BYTE for byte, or "all" is not all.
const rt = mkChart(bands());
const before = JSON.stringify(rt.data.datasets[4]);
rt.show(['Organic Search', BASE_LABEL]);  seoTrOverlaySync(rt, CTX);
const mid = JSON.stringify(rt.data.datasets[4]);
rt.show(['Organic Search', 'Direct', 'Paid Shopping', 'Other', BASE_LABEL]);
seoTrOverlaySync(rt, CTX);
out.roundTrip = [before === mid, before === JSON.stringify(rt.data.datasets[4])];

// A DEVICE selection borrows the same resolver with its own noun.
const DFNS = new Map([['mobile', r => r.device === 'mobile'],
                      ['desktop', r => r.device === 'desktop']]);
const DROWS = [{ day: P1, device: 'mobile', sessions: 700 },
               { day: P1, device: 'desktop', sessions: 200 }];
const dC = mkChart([{ label: 'mobile' }, { label: 'desktop' }, { label: 'tablet' },
                    { label: BASE_LABEL, stack: '_prev', data: [0, 0] }]);
dC.show(['mobile', 'desktop', BASE_LABEL]);
seoTrOverlaySync(dC, { src: DROWS, fns: DFNS, noun: 'device', baseRows: DROWS,
                       baseLabel: BASE_LABEL, toData });
out.deviceLabel = dC.data.datasets[3].label;

// No overlay at all: nothing to sync, and nothing may be touched.
const noOv = mkChart([{ label: 'a', data: [1] }, { label: 'b', data: [2] }]);
const snap = JSON.stringify(noOv.data.datasets);
seoTrOverlaySync(noOv, CTX);
out.noOverlay = snap === JSON.stringify(noOv.data.datasets);
console.log(JSON.stringify(out));
""")

# 950 = 500+300+100+50, 1000 = 520+310+110+60.
eq("B1  everything visible is the base population",
   [B["all"]["data"], B["all"]["label"]], [[950, 1000], "Sessions (prior year)"])
eq("B2  one band isolated draws that band's own prior year",
   [B["soloOrganic"]["data"], B["soloOrganic"]["label"]],
   [[500, 520], "Organic Search (prior year)"])
eq("B2b and a different band, a different line",
   [B["soloDirect"]["data"], B["soloDirect"]["label"]],
   [[300, 310], "Direct (prior year)"])
eq("B3  two bands sum, and the label counts them in the page's own noun",
   [B["twoBands"]["data"], B["twoBands"]["label"]],
   [[800, 830], "2 channel groups (prior year)"])
# /!\ Other is the COMPLEMENT of the ranked set, not a list: 150 = 100+50.
eq("B4  /!\\ Other resolves as the complement of the ranked channels",
   [B["soloOther"]["data"], B["soloOther"]["label"]],
   [[150, 170], "Other (prior year)"])
# v11.61's rule, unchanged: a missing breakdown draws NOTHING, not the site's.
eq("B5  /!\\ a band with no prior-year rows draws NOTHING, not the site's",
   B["soloEmpty"]["data"], [None, None])
eq("B5b and still says which population it found none for",
   B["soloEmpty"]["label"], "Paid Shopping (prior year)")
# Soloing the reference itself hides every band. It must not then describe
# no one - "everything" and "nothing" both mean the base.
eq("B6  /!\\ with no band visible the line is the base again",
   [B["noBands"]["data"], B["noBands"]["label"]], [[950, 1000], "Sessions (prior year)"])
eq("B7  /!\\ a band this chart cannot place falls back to the base rather "
   "than reporting a partial sum",
   [B["unknown"]["data"], B["unknown"]["label"]], [[950, 1000], "Sessions (prior year)"])
eq("B8  the round trip restores the dataset byte for byte",
   B["roundTrip"], [False, True])
eq("B9  a device selection carries its own noun", B["deviceLabel"], "2 devices (prior year)")
eq("B10 a chart with no overlay is left entirely alone", B["noOverlay"], True)


# ===========================================================================
print("\nC. the real legend handlers, and what they must NOT change")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1166_c.js"), CHART + FEED
   + fn("chartLegendIsOverlay") + "\n" + fn("chartLegendSoloed") + "\n"
   + fn("chartLegendSyncOverlay") + "\n" + fn("chartLegendToggle") + "\n"
   + fn("chartLegendOnly") + "\n" + fn("seoTrSelNoun") + "\n"
   + fn("chartLegendVisibleBands") + chr(10) + fn("seoTrOverlaySync") + r"""
const out = {};
// C1 `only` syncs, and it syncs BEFORE the repaint - one update, not two.
const c1 = mkChart(bands());
c1.$overlaySync = (c) => { OPS.push('sync'); seoTrOverlaySync(c, CTX); };
OPS.length = 0;
chartLegendOnly(c1, 1);
out.onlyOps  = OPS.slice();
out.onlyPrev = c1.data.datasets[4].data;

// C2 a plain toggle narrows it too - hiding bands one at a time is the same
// statement as isolating one, made in more clicks.
const c2 = mkChart(bands());
c2.$overlaySync = (c) => seoTrOverlaySync(c, CTX);
chartLegendToggle(c2, 2);   // hide Paid Shopping
chartLegendToggle(c2, 3);   // hide Other
out.togglePrev  = c2.data.datasets[4].data;
out.toggleLabel = c2.data.datasets[4].label;
chartLegendToggle(c2, 2); chartLegendToggle(c2, 3);
out.toggleBack  = c2.data.datasets[4].data;

// C3 /!\ A CHART THAT DID NOT OPT IN IS BYTE-IDENTICAL. The Units Sold goal
// line is an overlay too, and a goal is not a population.
const c3 = mkChart([{ label: 'Units' }, { label: 'Goal', stack: '_goal', data: [9, 9] }]);
const before3 = JSON.stringify(c3.data.datasets);
chartLegendOnly(c3, 0);
chartLegendToggle(c3, 0);
out.noOptIn = [before3 === JSON.stringify(c3.data.datasets), c3.updates];

// C4 a resolver that throws is caught: the repaint still happens, so the
// visibility the operator just asked for is not left undrawn.
const c4 = mkChart(bands());
c4.$overlaySync = () => { throw new Error('boom'); };
OPS.length = 0;
chartLegendOnly(c4, 0);
out.throwOps = OPS.slice();
out.throwVisible = c4.data.datasets.map((d, j) => c4.isDatasetVisible(j));
console.log(JSON.stringify(out));
""")

eq("C1  /!\\ the sync runs BEFORE the repaint, so there is one repaint",
   C["onlyOps"], ["sync", "update"])
eq("C1b and `only` on Direct moves the line to Direct", C["onlyPrev"], [300, 310])
eq("C2  hiding bands one at a time narrows it the same way",
   [C["togglePrev"], C["toggleLabel"]], [[800, 830], "2 channel groups (prior year)"])
eq("C2b and showing them again restores the site", C["toggleBack"], [950, 1000])
eq("C3  /!\\ a chart that did not opt in is byte-identical, goal line included",
   C["noOptIn"], [True, 2])
eq("C4  a throwing resolver is caught and the repaint still happens",
   C["throwOps"], ["warn", "update"])
eq("C4b so the isolation the operator asked for is still drawn",
   C["throwVisible"], [True, False, False, False, True])


# ===========================================================================
print("\nD. the real seoTrRenderChart: who publishes a resolver, and who does not")
# ===========================================================================
D = run_node(os.path.join(SP, "_v1166_d.js"), CHART + r"""
const chan = (d, c, n) => ({ day: d, channel: c, sessions: n });
const D1 = '2026-10-01', D2 = '2026-10-02';
const P1 = '2025-10-02', P2 = '2025-10-03';
const seoTr = {
  days: [{ day: D1, sessions: 1000 }, { day: D2, sessions: 1100 }],
  chan: [chan(D1, 'Organic Search', 600), chan(D1, 'Direct', 400), chan(D1, 'Email', 90),
         chan(D2, 'Organic Search', 700), chan(D2, 'Direct', 400), chan(D2, 'Email', 80)],
  dev:  [{ day: D1, device: 'mobile', sessions: 900 }],
  pages: [{ day: D1, landing_page: '/', channel: 'Organic Search', sessions: 300 }],
  prev: [{ day: P1, sessions: 900 }, { day: P2, sessions: 950 }],
  prevChan: [chan(P1, 'Organic Search', 500), chan(P2, 'Organic Search', 520),
             chan(P1, 'Direct', 300),         chan(P2, 'Direct', 310),
             chan(P1, 'Email', 100),          chan(P2, 'Email', 110)],
  prevDev: [{ day: P1, device: 'mobile', sessions: 800 }],
};
let MODE = 'line', CHAN = '', DEV = '', BANDS = 8;
const EL = {};
globalThis.document = { getElementById: (id) =>
  id === 'seo-tr-chan' ? { get value() { return CHAN; } }
  : id === 'seo-tr-dev' ? { get value() { return DEV; } }
  : (EL[id] || (EL[id] = { id, textContent: '', innerHTML: '' })) };
const pnlChartMode = () => MODE;
const pnlChartBands = () => BANDS;
const pnlInjectChartModeToggle = () => {};
let CFG = null, seoTrChart = null;
// /!\ REUSES `instance`, which is what the real pnlTrendRender does - and is
// the only way a stale resolver could survive a render to be inherited.
const pnlTrendRender = async (cfg) => { CFG = cfg;
  return cfg.instance || { destroy() {} }; };
const seoTrWindow = () => ({ from: '2026-10-01', to: '2026-10-02', label: 'x' });
""" + fn("chartLegendIsOverlay") + "\n" + fn("seoTrSelNew") + "\n"
   + fn("seoTrPageKey") + "\n" + fn("seoTrSelNoun") + "\n"
   + fn("seoTrPrevRows") + "\n" + fn("chartLegendVisibleBands") + chr(10) + fn("seoTrOverlaySync") + "\n"
   + fn("seoTrRenderChart") + r"""
let seoTrSel = seoTrSelNew();
const out = {};
// Draw, then ISOLATE in the way the legend does and read the line back.
const drawThenSolo = async (rows, scoped, solo) => {
  await seoTrRenderChart(rows, scoped);
  const has = typeof seoTrChart.$overlaySync === 'function';
  if (!has || !solo) return { has, labels: CFG.datasets.map(d => d.label) };
  const c = mkChart(CFG.datasets.map(d => Object.assign({}, d)));
  c.$overlaySync = seoTrChart.$overlaySync;
  c.show(solo);
  c.$overlaySync(c);
  const oi = c.data.datasets.findIndex(d => chartLegendIsOverlay(d));
  return { has, labels: CFG.datasets.map(d => d.label),
           prev: c.data.datasets[oi].data, prevLabel: c.data.datasets[oi].label };
};
MODE = 'stacked';
out.stacked = await drawThenSolo(seoTr.days, '',
  ['Organic Search', 'Sessions (prior year)']);
// Two bands kept, so Other is real - and Other is Email here.
BANDS = 2;
out.other = await drawThenSolo(seoTr.days, '', ['Other', 'Sessions (prior year)']);
BANDS = 8;
// A ticked channel selection: the bands ARE the selection, and the legend may
// still narrow inside it.
MODE = 'line';
seoTrSel = seoTrSelNew({ dim: 'channel', keys: new Set(['Organic Search', 'Direct']) });
out.selection = await drawThenSolo(seoTr.days, '',
  ['Direct', '2 channel groups (prior year)']);
// A landing-page selection has no prior year at all, so nothing to publish.
seoTrSel = seoTrSelNew({ pages: new Set(['/']) });
out.pages = await drawThenSolo(seoTr.days, '', null);
// One series and no bands: there is nothing a legend could narrow.
seoTrSel = seoTrSelNew();
out.line = await drawThenSolo(seoTr.days, '', null);
// A dropdown pick is already scoped by the resolver, and draws one series.
CHAN = 'Organic Search';
out.chanPick = await drawThenSolo(
  seoTr.chan.filter(r => r.channel === 'Organic Search'), 'Organic Search', null);
CHAN = '';
// /!\ And the publisher is REASSIGNED, so a stacked view's resolver cannot
// outlive it onto a view whose bands are not keyed to a breakdown.
MODE = 'stacked';
await seoTrRenderChart(seoTr.days, '');
const carried = seoTrChart;
MODE = 'line';
await seoTrRenderChart(seoTr.days, '');
out.notInherited = [carried === seoTrChart, typeof seoTrChart.$overlaySync];
console.log(JSON.stringify(out));
""")

eq("D1  a stacked ranked view publishes a resolver", D["stacked"]["has"], True)
# THE END-TO-END MEASUREMENT: 500/520 is Organic Search's own prior year;
# 900/950 is the site's, which is what used to be drawn here.
eq("D1b /!\\ and isolating Organic Search draws THAT channel's prior year",
   D["stacked"]["prev"], [500, 520])
eq("D1c under a label that names it", D["stacked"]["prevLabel"], "Organic Search (prior year)")
eq("D2  Other resolves to the channels outside the ranked set",
   [D["other"]["prev"], D["other"]["prevLabel"]], [[100, 110], "Other (prior year)"])
eq("D3  a ticked channel selection publishes one too, and narrows inside it",
   [D["selection"]["has"], D["selection"]["prev"], D["selection"]["prevLabel"]],
   [True, [300, 310], "Direct (prior year)"])
# v11.65: that feed is not fetched for last year, so there is no line to scope.
eq("D4  a landing-page selection publishes nothing", D["pages"]["has"], False)
eq("D5  one 'Sessions' series has no bands to narrow by", D["line"]["has"], False)
eq("D6  a dropdown pick is already scoped, and draws one series",
   [D["chanPick"]["has"], D["chanPick"]["labels"]],
   [False, ["Sessions", "Organic Search (prior year)"]])
# The SAME chart instance carries from a stacked render into a line one, so
# a resolver that was merely left alone would still be answering here - with
# the previous view's bands, against this view's single series.
eq("D7  /!\\ the resolver is REASSIGNED on every render, never inherited",
   D["notInherited"], [True, "object"])


# ===========================================================================
print("\nE. one definition each, one publisher, and the reasoning survives")
# ===========================================================================
for f in ("chartLegendSyncOverlay", "seoTrOverlaySync"):
    eq("E1  %s defined once" % f, NC.count("function %s(" % f), 1)
# Both legend gestures sync: fixing `only` alone would leave a seven-click
# route to the same wrong line.
eq("E2  /!\\ BOTH legend gestures sync",
   NC.count("chartLegendSyncOverlay(chart);"), 2)
ok(re.search(r"function chartLegendToggle[\s\S]{0,260}chartLegendSyncOverlay", NC),
   "E2b the plain toggle included")
# v11.69 - SIX charts publish one now: v11.68 shipped this overlay onto four
# more charts and the Ads one WITHOUT wiring them to this mechanism, so
# isolating a band left the line describing everything. The guarantee this
# assertion was protecting is not "only one chart", it is "every chart that
# draws an overlay can re-scope it" - which is what the count measures now.
eq("E3  every chart that draws an overlay publishes a resolver",
   NC.count("$overlaySync ="), 6)
eq("E3b and exactly one reader runs it", NC.count("chart.$overlaySync"), 1)
# /!\ And the narrowing rule has ONE spelling, shared by both syncs.
eq("E3c one definition of which bands are still drawn",
   NC.count("function chartLegendVisibleBands("), 1)
ok("chartLegendVisibleBands(chart)" in NC[NC.index("function seoTrOverlaySync("):],
   "E3d which the SEO sync reads rather than spelling its own")
# /!\ ONE rollup, read by the initial draw AND by the sync, so a narrowed line
# cannot be built by different arithmetic from the one it replaces.
eq("E4  /!\\ the 364-day shift is spelled once", NC.count("x.getDate() + 364"), 1)
eq("E4b and the prior-year rollup once", NC.count("shifted.set("), 1)
eq("E4c with the initial draw reading it", NC.count("data: prevData(prevRows)"), 1)
# The rebuild guard moved from the labels to the count, because the overlay's
# label changes on a click now. The retired form must be GONE, not shadowed.
eq("E5  the legend rebuild is keyed on the series COUNT", NC.count("String(ds.length)"), 1)
eq("E5b and the retired label-keyed signature is gone",
   NC.count("ds.map(d => String(d.label)"), 0)
ok("refreshed in place below" in js,
   "E5c /!\\ but the reasoning survives, so a grep for the old key still lands on it")
ok("A REFERENCE HAS TO BE THE REFERENCE OF WHAT IS DRAWN" in js,
   "E6  and the defect this release fixes is written where it was made")
# v11.56's guarantee is untouched: the reference still survives an isolation.
ok(re.search(r"if \(!mine && j !== i && chartLegendIsOverlay\(ds\[j\]\)\) continue;", NC),
   "E7  v11.56's rule is untouched - a reference still survives an isolation")

r = subprocess.run(["node", "--check", os.path.join(SP, "_v1166_a.js")],
                   capture_output=True, text=True)
ok(r.returncode == 0, "E8  the sliced source parses", r.stderr[-300:])

ok(len(re.findall(r">v11\.\d+ · [\d-]+<", s)) == 1, "E9  the version chip is well-formed")

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
