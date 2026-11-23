#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.51 - the app's own brand cell, and a drill-in that lands on the set.

- **Jason**, twice on the v12.50 missing-detail list:
  *"it doesn't tell me which brand it's for"*
  *"also the info doesn't match"*

(1) Seven dashes, because the block printed `r.brand` straight off
    `fba_shipment_summaries`. The FBA Shipments tab never printed that
    column - it resolves through `shipGroupBrand` and renders a clickable
    `+ Set` when nothing can be derived. Both were **locals** inside
    `renderFbaShipmentsTbl`, which is why a second surface could not reach
    them.

(2) That tab, filter `Missing detail`, read **0 shipments** against this
    block's 7. The filter is fine. Its WINDOW is `Last 365 days` and every
    one of the seven was created in 2023. This suite drives the real window
    filter and reproduces that zero.
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
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.51  one brand cell, and a link that lands on the rows")
print("=" * 70)

# ===========================================================================
print("\nA. the two locals are now one pair of module-scope helpers")
# ===========================================================================
eq("A1  shipGroupBrand declared once, at module scope",
   js.count("\nfunction shipGroupBrand(g) {"), 1)
eq("A2  shipBrandCell declared once, at module scope",
   js.count("\nfunction shipBrandCell(g) {"), 1)
ok("const shipGroupBrand = (g) =>" not in js,
   "A3  /!\\ the LOCAL is gone, not left standing beside the lifted copy "
   "(hard rule #1 - a consolidation that leaves copies behind is not one)")
ok("const brandCell = (g) =>" not in js,
   "A4  ...and so is the local brand cell")
eq("A5  the + Set BUTTON exists exactly once in the file",
   js.count(">+ Set</button>"), 1)
ok("Summary-only rows don't have items to auto-derive from" in js,
   "A6  the v5.56 tooltip came across verbatim, not re-typed")
# every reader of the resolver
for n in ["shipBrandCell(g)", "shipGroupBrand(g) || 'zzz_'", "!shipGroupBrand(g)"]:
    ok(n in js, "A7  the tab still reads the resolver: %s" % n)

# ===========================================================================
print("\nB. the gap block renders THAT cell")
# ===========================================================================
H = fn_flat("fbaDetailGapHtml")
ok("shipBrandCell({ shipment_id: r.shipment_id" in H,
   "B1  /!\\ THE ASK: the block calls the app's brand cell")
ok("esc2(r.brand" not in H,
   "B2  ...and no longer prints the raw column")
ok("summary: { brand: r.brand }, items: []" in H,
   "B3  shaped as a group with NO items, which is what a summary-only row is")

HARNESS = (fn_flat("fbaDetailGapHtml") + "\n" + fn_flat("fbaDetailGapTip") + "\n"
           + fn_flat("shipGroupBrand") + "\n" + fn_flat("shipBrandCell") + r"""
function esc2(x) { return String(x == null ? '' : x)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
const allProducts = [{ master_id: 'SP-0034', brand: 'Meowijuana' }];
const _fbaDetailGap = {};
const _fbaDetailGapOpen = { dz: true };
const document = { getElementById: () => null };

const NO_BRAND = { shipment_id:'FBA179Z6SM14', shipment_name:'x', region:'CA',
  brand:null, status:'Closed', units_expected:149, units_located:149,
  sku_count:4, created_on:'2023-07-31' };
const TAGGED = Object.assign({}, NO_BRAND, { shipment_id:'FBA1786R71JD', brand:'Kitty Ka-Zoom' });
const MEOWI  = Object.assign({}, NO_BRAND, { shipment_id:'FBA173082ZD8', brand:'Meowijuana' });

console.log(JSON.stringify({
  untagged: fbaDetailGapHtml({ rows: [NO_BRAND], err: null }, 'dz'),
  tagged:   fbaDetailGapHtml({ rows: [TAGGED],   err: null }, 'dz'),
  meowi:    fbaDetailGapHtml({ rows: [MEOWI],    err: null }, 'dz'),
  // the resolver itself, on the three shapes a summary-only row can take
  rNone:  shipGroupBrand({ summary: { brand: null }, items: [] }),
  rTag:   shipGroupBrand({ summary: { brand: 'Doggijuana' }, items: [] }),
  rItems: shipGroupBrand({ summary: { brand: null }, items: [{ master_id: 'SP-0034' }] }),
}));
""")
B = run_node(os.path.join(SP, "_v1251_b.js"), HARNESS)

ok(">+ Set</button>" in B["untagged"],
   "B4  /!\\ a row with no brand renders the CLICKABLE + Set, not a dash")
ok("setShipmentBrand('FBA179Z6SM14')" in B["untagged"],
   "B5  ...wired to the shipment it is on")
ok("—</td>" not in B["untagged"].split("units with no item detail")[0]
   or B["untagged"].count(">+ Set</button>") == 1,
   "B6  the dash is gone from the brand column")
ok("KKZ" in B["tagged"] and "+ Set" not in B["tagged"],
   "B7  a tagged row renders its chip, abbreviated the way the tab does")
ok("c-meow" in B["meowi"],
   "B8  ...with the brand's own chip colour")
eq("B9  the resolver: no tag and no items is ''", B["rNone"], "")
eq("B10 a manual tag wins", B["rTag"], "Doggijuana")
eq("B11 items resolve when there ARE items", B["rItems"], "Meowijuana")

# ===========================================================================
print("\nC. THE MISMATCH, reproduced")
# ===========================================================================
# The real window+detail filter, lifted out of renderFbaShipmentsTbl.
R = fn_flat("renderFbaShipmentsTbl")
i = R.index("  let arr = [...groups.values()].filter(g => {")
PRED = R[i:R.index("\n  });\n", i) + len("\n  });\n")]
ok("detailFilter === 'missing'" in PRED and "cutoff && g.created_date" in PRED,
   "C0  the predicate lifted holds both the detail filter and the window")

C = run_node(os.path.join(SP, "_v1251_c.js"), r"""
// The seven stub groups the merge builds for summary-only shipments, with the
// created dates read off the live database on 2026-11-23.
const DATES = ['2023-07-31','2023-06-21','2023-04-26','2023-04-05','2023-03-29',
               '2023-02-20','2023-02-14'];
const groups = new Map(DATES.map((d, n) => [String(n), {
  shipment_id: 'S' + n, created_date: d, region: 'CA', items: [],
  has_detail: false, summary: { status: 'Closed' } }]));
// ...and one 2026 shipment that DOES have detail, so the filter has something
// to exclude for the other reason.
groups.set('x', { shipment_id: 'Sx', created_date: '2026-11-01', region: 'CA',
  items: [{}], has_detail: true, summary: { status: 'Closed' } });

function run(winDays, detailFilter) {
  const region = '';
  const cutoff = winDays ? (() => { const d = new Date('2026-11-23T12:00:00');
    d.setDate(d.getDate() - winDays); return d.toISOString().slice(0,10); })() : null;
""" + PRED.replace("  let arr =", "  const arr =") + r"""
  return arr.length;
}
console.log(JSON.stringify({
  w365_missing: run(365, 'missing'),
  all_missing:  run(0,   'missing'),
  w365_all:     run(365, ''),
  all_all:      run(0,   ''),
}));
""")
eq("C1  /!\\ HIS SCREEN: Missing detail + Last 365 days -> ZERO, and the filter "
   "was right - every one of the seven is from 2023", C["w365_missing"], 0)
eq("C2  Missing detail + All time -> the 7 the block names",
   C["all_missing"], 7)
eq("C3  the window alone still hides them", C["w365_all"], 1)
eq("C4  and all-time with no detail filter sees everything", C["all_all"], 8)

# ===========================================================================
print("\nD. so the block links instead of instructing")
# ===========================================================================
D = fn_flat("fbaDetailGapDrill")
ok("'fba-ship-detail', 'missing'" in D, "D1  the drill-in sets Missing detail")
ok("'fba-ship-window', '0'" in D,
   "D2  ...and All time, which is '0' in this picker's own vocabulary (v12.37)")
for ctl in ["'fba-ship-region', ''", "'fba-ship-brand', ''", "'fba-ship-srch', ''"]:
    ok(ctl in D,
       "D3  /!\\ and clears %s - landing on a tab still narrowed by an old "
       "filter is the same mismatch one click later" % ctl.split(",")[0])
ok("switchForecastView('fba-shipments')" in D,
   "D4  then opens the tab through the app's own navigator")
# v12.53 - the page search is the sticky globalSearch bar, which dispatches
# INTO fba-ship-srch. Clearing only the target left the visible box showing
# text for a filter that no longer applied.
ok("globalSearchSyncFromTarget" in D,
   "D4a /!\\ and syncs the search bar the operator can SEE, not just the "
   "input it dispatches into")
ok(D.index("switchForecastView") < D.index("globalSearchSyncFromTarget"),
   "D4b ...after the page is shown, or the sync resolves the wrong page")
ok("fbaDetailGapDrill()" in fn_flat("fbaDetailGapHtml"),
   "D5  the link is in the block's footer, beside the CSV one")
ok("open in FBA Shipments" in js,
   "D6  ...and says where it goes")
ok("set it to All time to see every one" not in js,
   "D7  /!\\ the tooltip that told him to do it BY HAND is gone - v12.50 "
   "shipped exactly that and he still had to find it")

# ===========================================================================
print("\nE. a tag set from the block shows up in the block")
# ===========================================================================
S = fn_flat("setShipmentBrand")
ok("fbaDetailGapSetBrand(shipmentId, newBrand)" in S,
   "E1  the setter patches the gap rows it does not own")
ok(S.index("renderFbaShipmentsTbl()") < S.index("fbaDetailGapSetBrand"),
   "E2  after the tab's own repaint, so neither waits on the other")
G = fn_flat("fbaDetailGapSetBrand")
ok("if (!hit) return;" in G,
   "E3  a shipment that is not in the list repaints nothing")
ok('[id^="fdg-"]' in G,
   "E4  every open host, because the setter cannot know which card asked")
ok("rows.splice" not in G and "filter(" not in G,
   "E5  /!\\ THE ROW STAYS. It is listed for having no DETAIL; tagging a brand "
   "does not close that gap, and dropping it would read as work that was done")

# ===========================================================================
print("\nF. the release names itself")
# ===========================================================================
C_ = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r"(v\d+\.\d+)\s*·\s*(\d{4}-\d{2}-\d{2})", s)
decl = re.search(r"current version \*\*(v\d+\.\d+)\*\*", C_)
ok(chip is not None and decl is not None and chip.group(1) == decl.group(1),
   "F1  the version chip and CLAUDE.md name the SAME release",
   "%s vs %s" % (chip.group(1) if chip else None, decl.group(1) if decl else None))
ok(chip is not None and "\\u" not in chip.group(0),
   "F2  /!\\ REAL characters in markup (v12.42 shipped the escape form)",
   chip.group(0) if chip else None)
ok("v12.51" in C_, "F3  CLAUDE.md carries the entry")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
