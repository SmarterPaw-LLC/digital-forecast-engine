#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.71 - the Fees tab joins the render pipeline, and ranks by the fee you pick.

Jason: "this page does nothing... what is the point? i wanted a way to view
high fee items and look for savings from storage costs and other fees."

  * A  /!\ THE DEFECT REPRODUCED. The pre-v11.71 tail is run beside the
       shipped one over the same four views: the old one fires three and
       leaves `fees` untouched, which is why changing the period did nothing.
  * B  ONE registry, read by renderPnl's tail AND by switchPnlAmazonView, so
       a view cannot be wired into one and missed by the other. The four
       retired spellings are GONE, not left standing beside it.
  * C  the real pnlRenderAmazonView: each view, an unknown view, and a
       throwing renderer that must not break the Summary render.
  * D  ONE comparator. tableSortCmp is byte-identical to the Ads inline sort
       it replaces, which is the only form in which "no Ads table moved" is
       checkable rather than read off a diff.
  * E  the real by-product table: a Storage column at last, every avoidable
       line beside it, the Avoidable column tying out against them, and the
       sort driven through the real amzFeeSortBy.
  * F  static: the registry's `sku` short forms are declared beside their
       long forms, and the empty-state branch refreshes the sub-view too.
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
    # LINE comments only. Block-stripping index.html eats 824,674 chars
    # because a /* inside a string or regex pairs with a distant */ (v11.63).
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


def fn(name):
    i = js.index("function " + name + "(")
    head = js.index("{", i)
    j = i
    while j > 0 and js[j - 1] != "\n":
        j -= 1
    return js[j:head] + _bal(head)


def const_arr(name):
    i = js.index("const %s = [" % name)
    j, d, k = js.index("[", i), 0, js.index("[", i)
    while k < len(js):
        if js[k] == "[":
            d += 1
        elif js[k] == "]":
            d -= 1
            if d == 0:
                return "const %s = %s;" % (name, js[j:k + 1])
        k += 1
    raise SystemExit("unbalanced %s" % name)


def const_obj(name):
    i = js.index("const %s = {" % name)
    return "const %s = %s;" % (name, _bal(js.index("{", i)))


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("v11.71 - the Fees tab joins the render pipeline")
print("=" * 68)

NC = nocomment(js)

# ---------------------------------------------------------------------------
print("\nA. /!\\ THE DEFECT REPRODUCED - the old tail never reached the Fees tab")
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, "_v1171_a.js"), """
%s
// The tail EXACTLY as it stood in v11.70: two bare ifs and a try/catch,
// three spellings of one rule, and nothing at all for 'fees'.
function oldTail(view, log) {
  if (view === 'diagnostics') log.push('diagnostics');
  if (view === 'performance') log.push('performance');
  try {
    if (view === 'opportunities') log.push('opportunities');
  } catch (e) {}
}
const VIEWS = ['diagnostics', 'performance', 'opportunities', 'fees'];
const out = { old: {}, now: {} };
for (const v of VIEWS) { const l = []; oldTail(v, l); out.old[v] = l; }
let log = [];
const renderPnlDiagnostics   = () => log.push('diagnostics');
const renderPnlPerformance   = () => log.push('performance');
const renderPnlOpportunities = () => log.push('opportunities');
const renderAmazonFees       = () => log.push('fees');
%s
%s
for (const v of VIEWS) { log = []; pnlRenderAmazonView(v); out.now[v] = log; }
console.log(JSON.stringify(out));
""" % ("", const_obj("PNL_AMZN_LIVE_VIEWS"), fn("pnlRenderAmazonView")))

eq("A1  old tail, view=fees           -> NOTHING rendered", A["old"]["fees"], [])
eq("A2  old tail, view=diagnostics    -> rendered", A["old"]["diagnostics"], ["diagnostics"])
eq("A3  old tail, view=performance    -> rendered", A["old"]["performance"], ["performance"])
eq("A4  old tail, view=opportunities  -> rendered", A["old"]["opportunities"], ["opportunities"])
eq("A5  v11.71, view=fees             -> RENDERED", A["now"]["fees"], ["fees"])
eq("A6  v11.71, view=diagnostics      -> unchanged", A["now"]["diagnostics"], ["diagnostics"])
eq("A7  v11.71, view=performance      -> unchanged", A["now"]["performance"], ["performance"])
eq("A8  v11.71, view=opportunities    -> unchanged", A["now"]["opportunities"], ["opportunities"])
eq("A9  the old tail covered 3 of 4 views",
   sum(1 for v in A["old"].values() if v), 3)
eq("A10 v11.71 covers 4 of 4",
   sum(1 for v in A["now"].values() if v), 4)

# ---------------------------------------------------------------------------
print("\nB. ONE registry, and the retired spellings are GONE")
# ---------------------------------------------------------------------------
reg = const_obj("PNL_AMZN_LIVE_VIEWS")
eq("B1  the registry holds exactly four views",
   sorted(re.findall(r"(?m)^\s{2}(\w+):\s*\{ render:", reg)),
   ["diagnostics", "fees", "opportunities", "performance"])
eq("B1b ONE of them survives an empty source, and it is Fees",
   re.findall(r"(?m)^\s{2}(\w+):\s*\{ render:[^}]*onEmpty: true", reg), ["fees"])
ok("fees:" in reg.replace(" ", ""), "B2  'fees' IS in the registry - the whole release")
for name in ["renderPnlDiagnostics", "renderPnlPerformance",
             "renderPnlOpportunities", "renderAmazonFees"]:
    ok(("function %s(" % name) in js or ("async function %s(" % name) in js,
       "B3  %s is a real top-level function" % name)

ok("if (pnlAmazonView === 'diagnostics') renderPnlDiagnostics();" not in NC,
   "B4  the retired tail `if (pnlAmazonView === 'diagnostics')` is gone")
ok("if (pnlAmazonView === 'performance') renderPnlPerformance();" not in NC,
   "B5  the retired tail `if (pnlAmazonView === 'performance')` is gone")
ok("pnlAmazonView === 'opportunities'" not in NC,
   "B6  the retired Opportunities try/catch is gone")
ok("if (view === 'fees') renderAmazonFees();" not in NC,
   "B7  switchPnlAmazonView's own `if (view === 'fees')` is gone")
ok("if (view === 'opportunities') { renderPnlOpportunities(); }" not in NC,
   "B8  switchPnlAmazonView's own Opportunities call is gone")
eq("B9  exactly ONE spelling of the registry",
   NC.count("const PNL_AMZN_LIVE_VIEWS"), 1)

sw = fn("switchPnlAmazonView")
ok("pnlRenderAmazonView(view)" in sw,
   "B10 switchPnlAmazonView reads the SAME registry")
tail = js[js.index("function renderPnl("):]
tail = tail[:tail.index("fitTableWrapsSoon();   // v10.56") + 40]
ok("pnlRenderAmazonView(pnlAmazonView)" in tail,
   "B11 renderPnl's tail reads the SAME registry")
eq("B12 renderPnl's tail calls it unqualified", NC.count("pnlRenderAmazonView(pnlAmazonView);"), 1)
eq("B12b and the empty branch calls it with { empty: true }",
   NC.count("pnlRenderAmazonView(pnlAmazonView, { empty: true })"), 1)

# Entry-only actions must NOT have been folded into the live registry: they
# are round trips and uploader wiring, not a repaint on a filter change.
ok("if (view === 'breakeven')   { renderBreakeven(); }" in js,
   "B13 Break-Even stays ENTRY-only - it runs its own SQL")
ok("if (view === 'changelog')" in js,
   "B14 Change Log stays entry-only")
for k in ["breakeven", "changelog", "summary", "ads"]:
    ok(("%s:" % k) not in reg.replace(" ", ""),
       "B15 '%s' is NOT a filter-driven view" % k)

# ---------------------------------------------------------------------------
print("\nC. the real pnlRenderAmazonView")
# ---------------------------------------------------------------------------
C = run_node(os.path.join(SP, "_v1171_c.js"), """
let log = [];
const renderPnlDiagnostics   = () => log.push('diagnostics');
const renderPnlPerformance   = () => log.push('performance');
const renderPnlOpportunities = () => log.push('opportunities');
const renderAmazonFees       = () => { log.push('fees'); throw new Error('boom'); };
%s
%s
const out = {};
log = []; out.unknown = [pnlRenderAmazonView('summary'), log.slice()];
log = []; out.emptyOpps = [pnlRenderAmazonView('opportunities', { empty: true }), log.slice()];
log = []; out.emptyDiag = [pnlRenderAmazonView('diagnostics', { empty: true }), log.slice()];
log = []; out.undef   = [pnlRenderAmazonView(undefined), log.slice()];
log = []; out.diag    = [pnlRenderAmazonView('diagnostics'), log.slice()];
log = []; out.emptyFees = [pnlRenderAmazonView('fees', { empty: true }), log.slice()];
log = []; const warns = [];
const _w = console.warn; console.warn = (...a) => warns.push(a.join(' '));
out.threw = [pnlRenderAmazonView('fees'), log.slice()];
console.warn = _w;
out.warned = warns.length;
out.after = (() => { log = []; return [pnlRenderAmazonView('performance'), log.slice()]; })();
console.log(JSON.stringify(out));
""" % (const_obj("PNL_AMZN_LIVE_VIEWS"), fn("pnlRenderAmazonView")))

eq("C1  an unregistered view renders nothing and reports false",
   C["unknown"], [False, []])
eq("C2  undefined is a no-op, not a throw", C["undef"], [False, []])
eq("C3  a registered view renders exactly once", C["diag"], [True, ["diagnostics"]])
eq("C4  a THROWING renderer is caught and reports false",
   C["threw"], [False, ["fees"]])
eq("C5  ...and it is warned about rather than swallowed", C["warned"], 1)
eq("C6  the next render is unaffected by the throw",
   C["after"], [True, ["performance"]])
# /!\ The v11.17 guarantee test_v1117 A1c was written to protect.
eq("C7  an EMPTY source refuses Opportunities - its aggregates do not exist",
   C["emptyOpps"], [False, []])
eq("C8  ...and Diagnostics with it", C["emptyDiag"], [False, []])
# Reached, not refused. (This fixture's renderer throws on purpose - C4
# owns that half - so the guarantee here is that `empty` did not gate it.)
eq("C9  while FEES is NOT refused on an empty source - it reads the rows itself",
   C["emptyFees"][1], ["fees"])

# ---------------------------------------------------------------------------
print("\nD. ONE comparator, and the Ads tables did not move")
# ---------------------------------------------------------------------------
D = run_node(os.path.join(SP, "_v1171_d.js"), """
%s
%s
// The Ads sort EXACTLY as it stood before v11.71.
function oldSort(list, k, dir) {
  return list.slice().sort((a, b) => {
    const av = a[k], bv = b[k];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'string' || typeof bv === 'string') {
      return String(av).localeCompare(String(bv)) * dir;
    }
    return (av - bv) * dir;
  });
}
const rows = [
  { id: 'a', spend: 10,   name: 'Zebra' },
  { id: 'b', spend: null, name: 'apple' },
  { id: 'c', spend: 3,    name: 'Mango' },
  { id: 'd', spend: 10,   name: null },
  { id: 'e', spend: -2,   name: 'Blue' },
];
const ids = l => l.map(r => r.id);
const out = {};
for (const k of ['spend', 'name']) for (const dir of [-1, 1]) {
  out[k + dir] = {
    old: ids(oldSort(rows, k, dir)),
    now: ids(rows.slice().sort(tableSortCmp(k, dir))),
  };
}
out.arrow = [tableSortArrow(true, -1), tableSortArrow(true, 1), tableSortArrow(false, -1)];
out.dirZero = ids(rows.slice().sort(tableSortCmp('spend', 0)));
out.holey = ids([null, { id: 'x', spend: 1 }, undefined].sort(tableSortCmp('spend', -1))
                 .map(r => r || { id: '-' }));
console.log(JSON.stringify(out));
""" % (fn("tableSortCmp"), fn("tableSortArrow")))

for k in ["spend-1", "spend1", "name-1", "name1"]:
    eq("D1  %-8s byte-identical to the retired Ads sort" % k,
       D[k]["now"], D[k]["old"])
eq("D2  nulls sort LAST descending", D["spend-1"]["now"][-1], "b")
eq("D3  nulls sort LAST ascending too", D["spend1"]["now"][-1], "b")
eq("D4  descending by spend ranks the biggest first",
   D["spend-1"]["now"][:2], ["a", "d"])
eq("D5  a string column uses localeCompare", D["name1"]["now"][:3], ["apple", "Blue", "Mango"]
   and ["b", "e", "c"])
eq("D6  the arrows are one glyph each way", D["arrow"], [" " + chr(0x25BC), " " + chr(0x25B2), ""])
eq("D7  dir 0 is treated as ascending, never as a collapse",
   D["dirZero"], D["spend1"]["now"])
ok(isinstance(D["holey"], list), "D8  a holey list does not throw")
eq("D9  exactly ONE spelling of the null rule",
   NC.count("if (av == null && bv == null) return 0;"), 1)
eq("D10 the Ads table calls the shared comparator",
   NC.count("tableSortCmp(st.sortK, st.sortDir)"), 1)
eq("D11 and the shared arrow", NC.count("tableSortArrow(st.sortK === c.k, st.sortDir)"), 1)

# ---------------------------------------------------------------------------
print("\nE. the real by-product table")
# ---------------------------------------------------------------------------
LINES = const_arr("AMZ_FEE_LINES")
AVOID = re.findall(r"\{ k: '(\w+)',[^}]*?lever: 'avoidable'", LINES, re.S)
SKUC  = re.findall(r"\{ k: '(\w+)',[^}]*?sku: '([^']+)'", LINES, re.S)

E = run_node(os.path.join(SP, "_v1171_e.js"), """
%s
%s
%s
const esc2 = v => String(v == null ? '' : v)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const pnlCard = c => '<card>' + c.label + '</card>';
const pnlRegion = 'US';
let amzCuFtByMid = {}, _amzCuFtLoading = false;
const amzLoadCuFt = () => {};
const DOM = {};
const mk = id => (DOM[id] = { id, innerHTML: '', textContent: '', value: '' });
['amzfee-cards','amzfee-note','amzfee-composition','amzfee-comp-sub',
 'amzfee-skus','amzfee-sku-sub','amzfee-target','amzfee-search'].forEach(mk);
DOM['amzfee-target'].value = '5';
const document = { getElementById: id => DOM[id] || null };
const AMZ_FEE_LEVER = %s;
const AMZ_FEE_OUTSIDE = %s;
const P = (mid, name, o) => Object.assign({ mid, name, netSales: 0, units: 0, fees: 0,
  avoidable: 0, feePct: null, fbaPct: null, fbaPerU: null }, o);
let AGG = null;
function amzFeeAgg() { return AGG; }
// v11.91 - the renderer grew a previous period, a per-cell delta and a column
// set. Sliced, never stubbed.
//
// /!\ DELTAS ARE SUPPRESSED HERE ON PURPOSE. This suite owns the COLUMNS and
// the SORT; what the delta says is test_v1191's. _pnlSuppressDeltas is the
// app's own All-time flag, so amzFeePrevAgg returns null exactly as it does
// on that period and no delta markup lands inside the cells being asserted.
let _pnlSuppressDeltas = true;
const localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
%s
%s
%s
%s
%s

function build(prods, scanned) {
  const tot = P('TOT', 'TOT', { netSales: 1000, units: 100, fees: 400, avoidable: 40 });
  for (const l of AMZ_FEE_LINES) tot[l.k] = 0;
  for (const o of AMZ_FEE_OUTSIDE) tot[o.k] = 0;
  tot.fba_fulfillment_fee_total = 200; tot.referral_fee_total = 150;
  // v11.72 - a window that CHARGED these, so their columns render. Storage
  // and Surcharge are deliberately left at zero: a line this window did not
  // charge must NOT take a column (E2b).
  tot.aged_inventory_fee_total = 984; tot.removal_fee_total = 426;
  tot.inbound_placement_fee_total = 228; tot.low_inventory_fee_total = 12;
  // Storage billed once in thirteen weeks and NOT in this window - the live
  // shape, measured: 1 of 13 US weeks.
  const cadence = {};
  for (const l of AMZ_FEE_LINES) cadence[l.k] = { weeks: 13, last: '2026-10-26' };
  cadence.fba_storage_fee_total   = { weeks: 1, last: '2026-08-31' };
  cadence.refund_admin_fee_total  = { weeks: 0, last: '' };
  AGG = { tot, prods, from: '2026-10-25', to: '2026-10-31',
          scanned: scanned === undefined ? 10 : scanned, inWindow: prods.length,
          keys: AMZ_FEE_LINES.map(l => l.k), cadence, weeksLoaded: 13 };
}

const mkp = (mid, name, o) => {
  const p = P(mid, name, o);
  for (const l of AMZ_FEE_LINES) if (p[l.k] === undefined) p[l.k] = 0;
  for (const o2 of AMZ_FEE_OUTSIDE) if (p[o2.k] === undefined) p[o2.k] = 0;
  Object.assign(p, o);
  p.avoidable = AMZ_FEE_LINES.filter(l => l.lever === 'avoidable')
                             .reduce((a, l) => a + (p[l.k] || 0), 0);
  return p;
};

const rows = [
  mkp('m1', 'Avocado Toast', { netSales: 1841, units: 300, fees: 900, feePct: 48.9,
      fbaPct: 20, fbaPerU: 1.5, fba_fulfillment_fee_total: 450,
      aged_inventory_fee_total: 884, fba_storage_fee_total: 12 }),
  mkp('m2', 'Pupcorn', { netSales: 402, units: 40, fees: 600, feePct: 149,
      fbaPct: 40, fbaPerU: 2.5, fba_fulfillment_fee_total: 100,
      aged_inventory_fee_total: 100, removal_fee_total: 426, fba_storage_fee_total: 90 }),
  mkp('m3', 'Zoom Sticks', { netSales: 5000, units: 900, fees: 1200, feePct: 24,
      fbaPct: 18, fbaPerU: 1.0, fba_fulfillment_fee_total: 900,
      fba_storage_fee_total: 3 }),
];

const out = {};
const head = () => (DOM['amzfee-skus'].innerHTML.match(/<th[\\s\\S]*?<\\/th>/g) || []);
const hdrText = () => head().map(h => h.replace(/<[^>]*>/g, '').trim());
// v11.91 - /!\\ STOP AT </tbody>. The table grew a <tfoot> TOTAL row, and
// taking everything after <tbody> swept it into the row list, so every
// ordering assertion read a trailing 'TOTAL'.
const bodyRows = () => ((DOM['amzfee-skus'].innerHTML.split('<tbody>')[1] || '')
  .split('</tbody>')[0] || '')
  .split('<tr').slice(1).map(r => (r.match(/<td[\\s\\S]*?<\\/td>/g) || [])
    .map(c => c.replace(/<[^>]*>/g, '').trim()));

build(rows); renderAmazonFees();
out.headers = hdrText();
out.sub = DOM['amzfee-sku-sub'].textContent;
out.order = bodyRows().map(r => r[0]);
out.thHasSort = head().filter(h => h.indexOf('amzFeeSortBy(') > -1).length;
out.row1 = bodyRows()[0];
out.comp = DOM['amzfee-composition'].innerHTML;
out.storageTip = (out.comp.match(/title="(FBA Storage[^"]*)"/) || [])[1] || '';
out.skuStorageTip = (DOM['amzfee-skus'].innerHTML.match(/title="(FBA Storage[^"]*)"/) || [])[1] || '';

// the real sort control
amzFeeSortBy('aged_inventory_fee_total');
out.aged = { order: bodyRows().map(r => r[0]), sub: DOM['amzfee-sku-sub'].textContent,
             state: JSON.parse(JSON.stringify(amzFeeSort)) };
amzFeeSortBy('aged_inventory_fee_total');
out.agedAsc = { order: bodyRows().map(r => r[0]), dir: amzFeeSort.dir };
amzFeeSortBy('name');
out.byName = { order: bodyRows().map(r => r[0]), dir: amzFeeSort.dir };
amzFeeSortBy('fees');
out.backToFees = bodyRows().map(r => r[0]);

// the two empty states
build([], 0); renderAmazonFees();
out.noData = (DOM['amzfee-skus'].innerHTML.match(/>([^<>]*window[^<>]*|[^<>]*loaded[^<>]*)</) || [])[1];
build([], 25); renderAmazonFees();
out.noFees = (DOM['amzfee-skus'].innerHTML.match(/>([^<>]*window[^<>]*|[^<>]*loaded[^<>]*)</) || [])[1];

console.log(JSON.stringify(out));
""" % (fn("tableSortCmp"), fn("tableSortArrow"), LINES,
       const_obj("AMZ_FEE_LEVER").split("=", 1)[1].rstrip(";").strip(),
       const_arr("AMZ_FEE_OUTSIDE").split("=", 1)[1].rstrip(";").strip(),
       # v11.91 - everything renderAmazonFees newly reaches for, in dependency
       # order. Sliced out of the shipped file so a change to any of them
       # fails this suite rather than being papered over by a stub.
       "\n".join([
           re.search(r"(?m)^const AMZ_FEE_DELTA_GOOD\s*=.*$", js).group(0),
           re.search(r"(?m)^const AMZ_FEE_DELTA_PTS\s*=.*$", js).group(0),
           fn("amzFeeDeltaDir"),
           re.search(r"(?m)^const AMZ_FEE_COL_KEY\s*=.*$", js).group(0),
           js[js.index("const AMZ_FEE_FIXED_COLS = ["):js.index("\n];", js.index("const AMZ_FEE_FIXED_COLS = [")) + 3],
           fn("amzFeePickerCols"),
           "function amzFeeAllCols() { return amzFeePickerCols().map(c => c.k); }",
           fn("amzFeeVisibleCols"),
           fn("amzFeeStamp"),
           fn("amzFeeSumRows"),
           fn("amzFeePrevAgg"),
           fn("amzFeeDeltaCell"),
           # v11.93 - the target plan, the idle shelf and the per-line product
           # ranking. Sliced for the same reason as everything above it: this
           # suite drives the REAL renderAmazonFees, so a stub here would hide
           # a change to the numbers it now prints.
           re.search(r"(?m)^const AMZ_FEE_DELTA_NONE\s*=.*$", js).group(0),
           fn("amzFeeTargetPlan"),
           fn("amzFeeTopFor"),
           fn("amzFeeIdle"),
           # v11.96 - the open-row set and the breakdown it renders. The row
           # markup reads both, so this harness needs them to drive the real
           # renderAmazonFees at all.
           re.search(r"(?m)^let amzFeeOpenRows\s*=.*$", js).group(0),
           fn("amzFeeRowBreakdown"),
           re.search(r"(?m)^const AMZ_FEE_OPP_TYPES\s*=.*$", js).group(0),
           fn("amzFeeActions"),
       ]),
       # the REAL default sort state, sliced rather than restated
       js[js.index("let amzFeeSort = "):].split(";", 1)[0] + ";",
       fn("amzFeeCadenceNote"), fn("amzFeeSortBy"), fn("renderAmazonFees")))

SHORTS = [sh for _, sh in SKUC]
CHARGED = ['Aged', 'Removal', 'Placement', 'Low Inv']
for sh in CHARGED:
    ok(sh in E["headers"], "E2  '%s' was charged, so it has a column" % sh)
# /!\ RE-POINTED IN v11.91. This pinned v11.72's rule - a line this window
# did not charge took no column - and Jason reversed it: "the columns should
# be based on the view that is set ... if there is no data for a period, I
# need to know that". The gate made the column SET a function of the period.
#
# The guarantee that survives is the one v11.72 actually cared about: a column
# of dashes must never read as "nobody pays this". It is now said ON the
# column and ONCE on the sub-line, instead of by deleting the column.
for sh in ['Storage', 'Surcharge']:
    ok(sh in [h.split(" ▼")[0].split(" ▲")[0] for h in E["headers"]],
       "E2b '%s' keeps its column even though this window charged it nothing" % sh,
       E["headers"])
# /!\ RE-POINTED IN v11.95, which gave the remaining five lines a column too,
# so this fixture now has five unpaid columns rather than two. The guarantee
# is that they are NAMED ONCE on the sub-line, not which ones they happen to
# be - a literal list is a census of the registry, and the registry grew.
ok("no charge in this window: " in E["sub"]
   and "Storage" in E["sub"] and "Surcharge" in E["sub"],
   "E2c ...and the sub-line names them, once", E["sub"])
ok(E["sub"].count("no charge in this window") == 1,
   "E2d ...once, not once per column", E["sub"])
# the active column carries the sort arrow, so match on the stem
_bare = [h.split(" ▼")[0].split(" ▲")[0] for h in E["headers"]]
ok("Held" in _bare and "Cu Ft" in _bare,
   "E1  WHAT WE ARE HOLDING is on the table", E["headers"])
for k in AVOID:
    ok(k in [kk for kk, _ in SKUC], "E3  avoidable line %s can have a column" % k)
eq("E4  every header is sortable", E["thHasSort"], len(E["headers"]))
# v11.72 - the default ranks what we are STORING. Sorted by Fees the table
# ranked by product shape and sales volume, which is a list of the biggest
# sellers - "this page tells me literally nothing".
ok("sorted by Cu Ft" in E["sub"],
   "E5  the default ranks cubic feet held", E["sub"])
ok("sorted by Cu Ft" in E["sub"], "E6  the sub-line names the sorted column", E["sub"])
eq("E7  sorting by Aged ranks the aged-inventory payers",
   E["aged"]["order"], ["Avocado Toast", "Pupcorn", "Zoom Sticks"])
ok("sorted by Aged" in E["aged"]["sub"],
   "E8  ...and the sub-line says so", E["aged"]["sub"])
eq("E9  a second click reverses it", E["agedAsc"]["dir"], 1)
eq("E10 ...and nulls/zeroes do not float to the top",
   E["agedAsc"]["order"][0], "Zoom Sticks")
eq("E11 a NAME column defaults to ascending", E["byName"]["dir"], 1)
eq("E12 ...alphabetically", E["byName"]["order"],
   ["Avocado Toast", "Pupcorn", "Zoom Sticks"])
eq("E13 and Fees still sorts, biggest first",
   E["backToFees"], ["Zoom Sticks", "Avocado Toast", "Pupcorn"])
eq("E14 no data loaded says so", E["noData"], "No SKU Economics data loaded.")
eq("E15 rows scanned but none in the window says something ELSE",
   E["noFees"], "No fees in this window.")

# The Avoidable column must equal the avoidable columns beside it, or the
# table contradicts itself on its own face.
hdr = E["headers"]
r1  = E["row1"]
cell = dict(zip(hdr, r1))
money = lambda v: 0.0 if v in ("", chr(0x2014)) else float(v.replace("$", "").replace(",", ""))
avoid_cols = [sh for k, sh in SKUC if k in AVOID and sh in hdr]
ok("not in window" in E["comp"],
   "E17 a monthly line this window cannot see is LISTED, not dropped")
ok("Last charged 2026-08-31" in E["storageTip"] and "1 of 13 weeks" in E["storageTip"],
   "E18 ...with the cadence and the last billing week on its tooltip", E["storageTip"])
# /!\ RE-POINTED IN v11.91. Under v11.72 Storage took no column in this
# window, so there was no header to carry the note and this asserted silence.
# The column now stays, which means the header IS the place the fact belongs -
# said once there rather than on all 93 rows.
ok("No charge in this window." in E["skuStorageTip"],
   "E19 ...and the Storage header says this window charged it nothing",
   E["skuStorageTip"])
ok("1 of 13 weeks" in E["skuStorageTip"],
   "E19b ...with the billing cadence, so it is not read as 'nobody pays this'",
   E["skuStorageTip"])
ok("Refund Admin" not in E["comp"],
   "E20 a line never charged at all is still never surfaced")

eq("E16 Avoidable == the avoidable columns beside it",
   round(money(cell["Avoidable"]), 2),
   round(sum(money(cell[c]) for c in avoid_cols), 2))

# ---------------------------------------------------------------------------
print("\nF. static")
# ---------------------------------------------------------------------------
eq("F1  every `sku` short form is declared beside a full label",
   len(SKUC), len(re.findall(r"sku: '", LINES)))
ok(all(sh and sh.strip() for _, sh in SKUC),
   "F2  ...and none of them is blank")
# /!\ RE-POINTED IN v11.95. This pinned v11.71's choice - FBA Storage plus
# every avoidable line - and Jason reversed it: "the biggest bucket is 'fees'
# column, which isn't broken out further." Those six were 3.2% of fees over
# 30 days. The guarantee worth keeping is that NONE OF THE SIX WAS LOST.
for _k in sorted(AVOID + ["fba_storage_fee_total"]):
    ok(_k in [k for k, _ in SKUC], "F3  %s still has its column" % _k)
eq("F3b /!\\ ...and now every line does",
   len(SKUC), len(re.findall(r"\{ k: '", LINES)))
# v11.91 - still derived from the registry's `sku` field, no longer gated on
# the window (that gate is what Jason reversed).
ok("const SKU_LINES = AMZ_FEE_LINES.filter(l => l.sku);" in js,
   "F4  the columns are DERIVED from the registry, not listed by hand")
eq("F5  the short form is never spelled a second time",
   sum(NC.count("h: '%s'" % sh) for _, sh in SKUC), 0)

empty_branch = js[js.index("const sourceData = isEu ? euPnlData : pnlData;"):]
empty_branch = empty_branch[:empty_branch.index("const { from, to } = getPnlDateRange();")]
ok("pnlRenderAmazonView(pnlAmazonView, { empty: true })" in empty_branch,
   "F6  the empty-state branch RETURNS, so it refreshes the sub-view itself")
ok("pnlVisibleMids = [];" in empty_branch,
   "F7  ...and it still clears the visible mids")

ok(re.search(r">v11\.\d+ . 20\d\d-\d\d-\d\d<", s) is not None,
   "F8  the version chip is present")
cm = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(11\.\d+) . 20\d\d-\d\d-\d\d<", s).group(1)
doc  = re.search(r"current version \*\*v(11\.\d+)\*\*", cm).group(1)
eq("F9  the chip and CLAUDE.md agree (v11.63's rule)", chip, doc)

eq("F10 the CSV follows the sort that is on screen",
   NC.count("tableSortCmp(amzFeeSort.k, amzFeeSort.dir)"), 2)
ok("b.fees - a.fees" not in NC,
   "F11 the retired hard-coded fee sort is gone from the Fees tab")


# ---------------------------------------------------------------------------
print("\nG. /!\\ a fee that bills MONTHLY is not a fee of zero")
# ---------------------------------------------------------------------------
# Measured on the live table: FBA Storage is charged in 1 of the last 13 US
# weeks. The composition drops zero lines, so on a weekly window the line
# Jason came to analyse was simply absent - which reads as "we pay no storage".
G = run_node(os.path.join(SP, "_v1171_g.js"),
    const_arr("AMZ_FEE_LINES") + "\n" + const_arr("AMZ_FEE_OUTSIDE") + "\n" + r"""
let pnlCurrencyMode = 'usd', pnlFxRate = 1.35, pnlFxGbp = 1.25, pnlFxEur = 1.1;
let amzCuFtByMid = {}, _amzCuFtLoading = false;
const pnlRegion = 'US';
const records = [];
const amzLoadCuFt = () => {};
function amzUnitsHeld(mid, region) {
  let held = null;
  for (const r of records) {
    if (r.master_id !== mid) continue;
    if (region && r.region !== region) continue;
    held = (held || 0) + (r.fba_available || 0) + (r.fba_inbound || 0);
  }
  return held;
}
const allProducts = [];
let pnlVisibleMids = [];
const mk = (mid, wk, o) => Object.assign({ master_id: mid, week_start: wk, region: 'US',
  currency: 'USD', net_sales: 100, net_units_sold: 10 }, o);
const ROWS = [
  // Fulfilment every week; storage ONCE, four weeks ago; aged twice.
  mk('M1', '2026-10-26', { fba_fulfillment_fee_total: 100 }),
  mk('M1', '2026-10-19', { fba_fulfillment_fee_total: 100, aged_inventory_fee_total: 40 }),
  mk('M1', '2026-10-12', { fba_fulfillment_fee_total: 100 }),
  mk('M1', '2026-10-05', { fba_fulfillment_fee_total: 100, fba_storage_fee_total: 476,
                           aged_inventory_fee_total: 10 }),
  // Another region's weeks must not count towards the cadence.
  Object.assign(mk('M9', '2026-09-28', { fba_storage_fee_total: 999 }), { region: 'CA' }),
];
// Jason's own window: one week, and it holds no storage billing week.
let WIN = { from: '2026-10-25', to: '2026-10-31' };
const getPnlDateRange = () => WIN;
const getPnlSource = () => ({ rows: ROWS, regionMatches: (r) => r === 'US' });
""" + fn("pnlRowFx") + "\n" + fn("amzFeeStamp") + "\n" + fn("amzFeeAgg") + "\n" + fn("amzFeeCadenceNote") + r"""
const out = {};
let A = amzFeeAgg();
out.weeksLoaded = A.weeksLoaded;
out.storage = A.cadence.fba_storage_fee_total;
out.aged = A.cadence.aged_inventory_fee_total;
out.fba = A.cadence.fba_fulfillment_fee_total;
out.never = A.cadence.refund_admin_fee_total;
out.storageInWindow = A.tot.fba_storage_fee_total;
out.noteStorage = amzFeeCadenceNote(A, 'fba_storage_fee_total');
out.noteFba = amzFeeCadenceNote(A, 'fba_fulfillment_fee_total');
out.noteNever = amzFeeCadenceNote(A, 'refund_admin_fee_total');
out.noteNoAgg = amzFeeCadenceNote(null, 'fba_storage_fee_total');
// A window that DOES contain the billing week reports it normally.
WIN = { from: '2026-10-01', to: '2026-10-31' };
A = amzFeeAgg();
out.wideStorage = A.tot.fba_storage_fee_total;
out.wideCadence = A.cadence.fba_storage_fee_total;
console.log(JSON.stringify(out));
""")

eq("G1  four US weeks are loaded; the CA week is not one of them",
   G["weeksLoaded"], 4)
eq("G2  storage was charged in ONE of them", G["storage"]["weeks"], 1)
eq("G3  ...and the tab knows which", G["storage"]["last"], "2026-10-05")
eq("G4  aged in two", G["aged"]["weeks"], 2)
eq("G5  fulfilment in all four", G["fba"]["weeks"], 4)
eq("G6  a line never charged has no history and is never surfaced",
   G["never"], {"weeks": 0, "last": ""})
eq("G7  /!\\ and in Jason's own window storage totals ZERO",
   G["storageInWindow"], 0)
ok("1 of 4 weeks" in G["noteStorage"] and "2026-10-05" in G["noteStorage"],
   "G8  so the note names the cadence AND the last billing week", G["noteStorage"])
eq("G9  a line charged every week says nothing - it would be noise",
   G["noteFba"], "")
eq("G10 neither does a line never charged", G["noteNever"], "")
eq("G11 no aggregate at all is silent, not a throw", G["noteNoAgg"], "")
eq("G12 a window containing the billing week reports it in full",
   G["wideStorage"], 476)
eq("G13 ...and the cadence does not move with the window",
   G["wideCadence"], G["storage"])

# The composition table lists it rather than dropping it.
ok("const unseen = AMZ_FEE_LINES" in js,
   "G14 the composition builds the not-in-window list")
ok(".filter(l => l.cad.weeks > 0)" in js,
   "G15 ...and ONLY for a line with real history, never an invented row")
ok("not in window" in js, "G16 the row says what it is")
rf = fn("renderAmazonFees")
ok("amzFeeCadenceNote(A, l.k)" in rf,
   "G17 and the per-SKU column header carries the same fact")
eq("G18 exactly ONE spelling of the note", NC.count("function amzFeeCadenceNote"), 1)

print("\n" + "-" * 68)
print("  passed %d   failed %d" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
