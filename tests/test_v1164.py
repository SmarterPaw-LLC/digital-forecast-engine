#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.64 - In-House Production is a sub-tab, and it owns its own columns.

Jason: "for consistency, would you make In-House Production a tab like on other
pages? it makes more sense to do it this way since it is a unique view. the
column view should be based on the saved settings. make sure exports works the
same way."

It had been one of four options on the Status-by dropdown, and it never
answered that dropdown's question. Its three siblings pick which inventory pool
drives the badge; this one NARROWS the grid to in-house SKUs, opens the weekly
production panel and changes what the export carries.

This suite owns three guarantees:
  * the tab REPLACED the option - it did not join it (one concept, one control)
  * the per-view column store cannot clobber the other view's set
  * the exports follow the tab, because they read the same getStatusMode()
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1164_")
s = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

FACTORY = chr(0x1F3ED)       # /!\ via chr(), never pasted and never escaped (v11.41)

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
    # /!\ LINE comments only. Stripping BLOCK comments from this file eats
    # 824,674 characters, because once the `//` lines are gone a `/*` inside a
    # string or regex literal pairs with a distant `*/` (v11.63). Every
    # explanation here is a `//` line, so this is both sufficient and safe.
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


print("\n" + "=" * 66)
print("  v11.64  In-House Production is a tab, with its own column set")
print("=" * 66)

NC = nocomment(js)
RAW_NC = nocomment(s)


# ===========================================================================
print("\nA. static - the tab REPLACED the option, it did not join it")
# ===========================================================================
btn = re.search(r'<button[^>]*id="ipv-inhouse"[^>]*>([^<]*)</button>', s)
ok(btn is not None, "A1  the In-House Production tab exists")
tag = re.search(r'<button[^>]*id="ipv-inhouse"[^>]*>', s)
tag = tag.group(0) if tag else ""
ok('class="subtab"' in tag, "A2  it is a .subtab, not a bespoke button", tag[:90])
ok(" style=" not in tag, "A3  it carries no inline style to override the class")
ok(btn is not None and btn.group(1).strip().startswith(FACTORY),
   "A4  it carries the in-house glyph the rest of the app already uses",
   btn.group(1) if btn else None)
eq("A5  it is wired to setIpView('inhouse')",
   len(re.findall(r"id=\"ipv-inhouse\" onclick=\"setIpView\('inhouse'\)\"", s)), 1)

# /!\ THE WHOLE POINT. A tab beside a dropdown option that does the same thing
# is the rule #1 divergence this release exists to remove.
status_sel = re.search(r'<select id="ip-status-source".*?</select>', s, re.S)
ok(status_sel is not None, "A6  the Status-by select is still there")
sel_txt = status_sel.group(0) if status_sel else ""
eq("A7  /!\\ 'in_house' is GONE from the Status-by dropdown",
   sel_txt.count('value="in_house"'), 0)
eq("A7b and the three pools that DO answer that question remain",
   [v for v in re.findall(r'<option value="([^"]*)"', sel_txt)],
   ["warehouse", "amazon", "combined"])

# The production-origin FILTER is a different control (it also offers
# "External only") and is deliberately untouched.
ih_sel = re.search(r'<select id="ip-in-house-filter".*?</select>', s, re.S)
ok(ih_sel is not None and 'value="in_house"' in ih_sel.group(0),
   "A8  the production-origin filter keeps its own in_house option")

eq("A9  all three views are handed to subtabApply, once",
   NC.count("[['ipv-planning', 'planning'], ['ipv-inhouse', 'inhouse'], ['ipv-reorder', 'reorder']]"), 1)
eq("A9b and the two-view list is gone, not left beside it",
   NC.count("[['ipv-planning', 'planning'], ['ipv-reorder', 'reorder']]"), 0)


# ===========================================================================
print("\nB. the REAL getStatusMode / setStatusMode, driven")
# ===========================================================================
MODE = fn("ipViewStatusMode") + "\n" + fn("getStatusMode") + "\n" + fn("setStatusMode")

# The view has to be consulted BEFORE the dropdown, or the dropdown wins and
# the tab is decoration.
ok(MODE.index("ipViewStatusMode()") < MODE.index("getElementById('ip-status-source')"),
   "B0  the view is read before the dropdown")

B = run_node(os.path.join(SP, "b.js"), r"""
const LS = {};
const localStorage = {
  getItem: k => (k in LS ? LS[k] : null),
  setItem: (k, v) => { LS[k] = String(v); },
};
let SEL = { value: 'warehouse' };
const document = { getElementById: id => (id === 'ip-status-source' ? SEL : null) };
let renders = 0, switched = [];
function renderInventoryTbl() { renders++; }
function setIpView(v) { switched.push(v); ipView = v; }
let ipView = 'planning';
""" + MODE + r"""
const out = {};
out.planning = getStatusMode();
ipView = 'reorder';           SEL.value = 'amazon';
out.reorderReadsDropdown = getStatusMode();
ipView = 'inhouse';
out.inhouseWinsOverDropdown = getStatusMode();
ipView = 'planning'; SEL.value = 'warehouse';

renders = 0; switched = [];
setStatusMode('in_house');
out.legacyRoutes = { switched: switched.slice(), stored: LS.ipStatusMode ?? null, renders };

ipView = 'inhouse'; renders = 0; switched = [];
setStatusMode('amazon');
out.refusedOnTab = { stored: LS.ipStatusMode ?? null, renders, mode: getStatusMode() };

ipView = 'planning'; renders = 0;
setStatusMode('amazon');
out.acceptedOnPlanning = { stored: LS.ipStatusMode ?? null, renders };

SEL = null;                    // no select in the DOM at all
ipView = 'inhouse';  out.noDomTab = getStatusMode();
ipView = 'planning'; out.noDomFallsBack = getStatusMode();
console.log(JSON.stringify(out));
""")

eq("B1  Planning reads the dropdown", B["planning"], "warehouse")
eq("B2  Reorder Setup reads the dropdown too", B["reorderReadsDropdown"], "amazon")
eq("B3  /!\\ the In-House tab WINS over the dropdown", B["inhouseWinsOverDropdown"], "in_house")
eq("B4  a pre-v11.64 saved view's 'in_house' routes to the tab",
   B["legacyRoutes"]["switched"], ["inhouse"])
eq("B4b and writes no mode the dropdown could not show",
   B["legacyRoutes"]["stored"], None)
# /!\ BOTH HALVES REFUSE. The dropdown is disabled on that tab, and a disabled
# control is bypassable from the console (v10.19 / v11.57).
eq("B5  /!\\ setStatusMode is REFUSED on the In-House tab",
   B["refusedOnTab"], {"stored": None, "renders": 0, "mode": "in_house"})
eq("B6  and accepted on Planning", B["acceptedOnPlanning"], {"stored": "amazon", "renders": 1})
eq("B7  with no select at all the tab still answers", B["noDomTab"], "in_house")
eq("B7b and Planning falls back to the stored mode", B["noDomFallsBack"], "amazon")

# /!\ `ipView` is declared further down the file than getStatusMode, so an
# unguarded read during module evaluation throws a TDZ ReferenceError rather
# than answering. Reproduced, so the try/catch is a measurement not a habit.
T = run_node(os.path.join(SP, "tdz.js"), r"""
const out = {};
""" + fn("ipViewStatusMode") + r"""
function unguarded() { return ipView === 'inhouse' ? 'in_house' : null; }
try { out.unguarded = unguarded(); } catch (e) { out.unguarded = 'THREW ' + e.constructor.name; }
out.guarded = ipViewStatusMode();
let ipView = 'planning';
console.log(JSON.stringify(out));
""")
eq("B8  /!\\ an unguarded read in the dead zone THROWS", T["unguarded"], "THREW ReferenceError")
eq("B8b the shipped guard answers null instead", T["guarded"], None)


# ===========================================================================
print("\nC. the REAL per-view column store, driven")
# ===========================================================================
COLS = (fn("ipColStoreKey") + "\n" + fn("ipSaveVisible") + "\n"
        + fn("ipLoadVisibleFor") + "\n" + fn("setIpView") + "\n"
        + fn("ipSyncInhouseControls") + "\n" + fn("ipInHousePick"))

C = run_node(os.path.join(SP, "c.js"), r"""
const LS = {};
const localStorage = {
  getItem: k => (k in LS ? LS[k] : null),
  setItem: (k, v) => { LS[k] = String(v); },
};
const mkEl = (extra) => Object.assign({ value: '', title: '', disabled: false,
                                        style: {}, dataset: {} }, extra || {});
const EL = {
  'ip-planning-container': mkEl(),
  'ip-reorder-container':  mkEl(),
  'ip-status-source':      mkEl({ title: 'POOL TIP', value: 'warehouse' }),
  'ip-in-house-filter':    mkEl({ title: 'ORIGIN TIP', value: 'external' }),
};
const document = { getElementById: id => EL[id] || null };
let painted = [];
function subtabApply() {}
function renderInventoryTbl() { painted.push('planning'); }
function renderEventsList() {}
function renderReorderGrid() { painted.push('reorder'); }
let ipView = 'planning';
let ipVisibleCols = ['a', 'b', 'c'];
""" + COLS + r"""
const out = {};
out.keys = { planning: ipColStoreKey('planning'), inhouse: ipColStoreKey('inhouse'),
             reorder: ipColStoreKey('reorder'), junk: ipColStoreKey('nope') };

out.loadAbsent = ipLoadVisibleFor('inhouse');
LS.ipVisibleColsInhouse = JSON.stringify([]);        out.loadEmpty = ipLoadVisibleFor('inhouse');
LS.ipVisibleColsInhouse = JSON.stringify({ x: 1 });  out.loadNotArray = ipLoadVisibleFor('inhouse');
LS.ipVisibleColsInhouse = 'not json at all';         out.loadJunk = ipLoadVisibleFor('inhouse');
delete LS.ipVisibleColsInhouse;

// Planning is the starting state, and the first entry to In-House SEEDS from it.
setIpView('planning');
out.planningStored = JSON.parse(LS.ipVisibleCols);
setIpView('inhouse');
out.seeded = ipVisibleCols.slice();
out.inhouseStored = JSON.parse(LS.ipVisibleColsInhouse);

// Edit the In-House set, then round-trip through Planning.
ipVisibleCols = ['a', 'need30'];  ipSaveVisible();
setIpView('planning');  out.backOnPlanning = ipVisibleCols.slice();
setIpView('inhouse');   out.backOnInhouse  = ipVisibleCols.slice();

// /!\ THE CLOBBER CASE. Reorder Setup has no IP_COLUMNS table, so it shares
// Planning's key - which is what stops a switch THROUGH it writing In-House's
// columns over Planning's.
setIpView('reorder');
out.afterReorder = { live: ipVisibleCols.slice(), planning: JSON.parse(LS.ipVisibleCols) };
setIpView('planning');
out.planningSurvived = ipVisibleCols.slice();

// The containers, and which renderer each view runs.
painted = []; setIpView('inhouse');
out.inhouseShowsPlanning = { pc: EL['ip-planning-container'].style.display,
                             rc: EL['ip-reorder-container'].style.display,
                             painted: painted.slice() };
painted = []; setIpView('reorder');
out.reorderSwaps = { pc: EL['ip-planning-container'].style.display,
                     rc: EL['ip-reorder-container'].style.display,
                     painted: painted.slice() };

// The two controls the tab takes over.
setIpView('planning');
out.tipsOnPlanning = { pool: EL['ip-status-source'].title, origin: EL['ip-in-house-filter'].title,
                       poolOff: EL['ip-status-source'].disabled,
                       originOff: EL['ip-in-house-filter'].disabled,
                       pick: ipInHousePick() };
setIpView('inhouse');
out.tipsOnInhouse = { poolOff: EL['ip-status-source'].disabled,
                      originOff: EL['ip-in-house-filter'].disabled,
                      cursor: EL['ip-status-source'].style.cursor,
                      poolSaysWhy: /In-House Production tab/.test(EL['ip-status-source'].title),
                      originSaysWhy: /in-house SKUs only/.test(EL['ip-in-house-filter'].title),
                      pick: ipInHousePick() };
setIpView('inhouse');   // twice: the stash must not capture the DISABLED text
setIpView('planning');
out.tipsRestored = { pool: EL['ip-status-source'].title, origin: EL['ip-in-house-filter'].title };

// A column set the store hands back must be a COPY.
LS.ipVisibleColsInhouse = JSON.stringify(['x', 'y']);
const got = ipLoadVisibleFor('inhouse'); got.push('MUTATED');
out.copyNotRef = JSON.parse(LS.ipVisibleColsInhouse);
console.log(JSON.stringify(out));
""")

eq("C1  Planning and In-House keep separate keys",
   [C["keys"]["planning"], C["keys"]["inhouse"]], ["ipVisibleCols", "ipVisibleColsInhouse"])
eq("C1b Reorder Setup shares Planning's key, on purpose",
   [C["keys"]["reorder"], C["keys"]["junk"]], ["ipVisibleCols", "ipVisibleCols"])
for key, why in [("loadAbsent", "nothing stored"), ("loadEmpty", "an empty list"),
                 ("loadNotArray", "a non-array"), ("loadJunk", "unparseable junk")]:
    eq("C2  null for %s, so the caller can seed" % why, C[key], None)
eq("C3  the first entry to In-House SEEDS from what is on screen",
   C["seeded"], ["a", "b", "c"])
eq("C3b and stores it under its own key", C["inhouseStored"], ["a", "b", "c"])
eq("C4  switching back restores Planning's set", C["backOnPlanning"], ["a", "b", "c"])
eq("C4b and switching forward restores the edited In-House set",
   C["backOnInhouse"], ["a", "need30"])
# /!\ The one way a shared key could have lost a column set.
eq("C5  /!\\ a switch THROUGH Reorder Setup does not clobber Planning's set",
   C["afterReorder"], {"live": ["a", "b", "c"], "planning": ["a", "b", "c"]})
eq("C5b and Planning still reads its own", C["planningSurvived"], ["a", "b", "c"])
eq("C6  In-House shows the PLANNING container and paints that table",
   C["inhouseShowsPlanning"], {"pc": "", "rc": "none", "painted": ["planning"]})
eq("C6b Reorder Setup still swaps containers and paints its grid",
   C["reorderSwaps"], {"pc": "none", "rc": "", "painted": ["reorder"]})
eq("C7  on Planning both controls are live with the markup's own tooltips",
   C["tipsOnPlanning"], {"pool": "POOL TIP", "origin": "ORIGIN TIP",
                         "poolOff": False, "originOff": False, "pick": "external"})
eq("C8  /!\\ on the In-House tab both are disabled AND say why",
   C["tipsOnInhouse"], {"poolOff": True, "originOff": True, "cursor": "not-allowed",
                        "poolSaysWhy": True, "originSaysWhy": True, "pick": ""})
# A disabled control saying "click me" is the v11.57 defect; a stash that
# captured the disabled text would never give the real tooltip back.
eq("C9  leaving the tab restores the markup's tooltips, not the disabled ones",
   C["tipsRestored"], {"pool": "POOL TIP", "origin": "ORIGIN TIP"})
eq("C10 the store hands back a copy, not its own array", C["copyNotRef"], ["x", "y"])


# ===========================================================================
print("\nD. /!\\ THE VIEW FIRST, THEN THE COLUMNS")
# ===========================================================================
APPLY = fn("ipApplyView")
eq("D1  the statusMode restore appears exactly once", APPLY.count("if (v.statusMode) {"), 1)
ok(APPLY.index("v.statusMode") < APPLY.index("ipVisibleCols = v.cols.slice()"),
   "D2  the view switch runs BEFORE the columns are applied")
ok("setIpView(wantInhouse ? 'inhouse' : 'planning')" in APPLY,
   "D3  and it switches in BOTH directions, not just into the tab")

# Reproduced, so "the old order lost the columns" is a measurement. With a
# per-view store, applying cols first writes them under the tab being LEFT and
# the switch then loads the other tab's set straight over them.
D = run_node(os.path.join(SP, "d.js"), r"""
const LS = {};
const localStorage = {
  getItem: k => (k in LS ? LS[k] : null),
  setItem: (k, v) => { LS[k] = String(v); },
};
const mkEl = () => ({ value: '', title: '', disabled: false, style: {}, dataset: {} });
const EL = { 'ip-planning-container': mkEl(), 'ip-reorder-container': mkEl(),
             'ip-status-source': mkEl(), 'ip-in-house-filter': mkEl() };
const document = { getElementById: id => EL[id] || null };
function subtabApply() {}
function renderInventoryTbl() {}
function renderEventsList() {}
function renderReorderGrid() {}
let ipView = 'planning';
let ipVisibleCols = ['a', 'b', 'c'];
""" + COLS + r"""
const SAVED = { cols: ['need30', 'need60'], statusMode: 'in_house' };
// The realistic state: you are on Planning and the In-House tab ALREADY has a
// column set of its own. That stored set is what the switch loads straight
// over anything an apply wrote a moment earlier.
const reset = () => {
  ipView = 'planning'; ipVisibleCols = ['a', 'b', 'c'];
  for (const k of Object.keys(LS)) delete LS[k];
  LS.ipVisibleCols = JSON.stringify(['a', 'b', 'c']);
  LS.ipVisibleColsInhouse = JSON.stringify(['stale1', 'stale2']);
};

reset();                                   // the OLD order: columns, then view
ipVisibleCols = SAVED.cols.slice(); ipSaveVisible();
setIpView('inhouse');
const before = ipVisibleCols.slice();
const planningAfterOld = JSON.parse(LS.ipVisibleCols);

reset();                                   // the SHIPPED order: view, then columns
setIpView('inhouse');
ipVisibleCols = SAVED.cols.slice(); ipSaveVisible();
const after = ipVisibleCols.slice();
const planningAfterNew = JSON.parse(LS.ipVisibleCols);

console.log(JSON.stringify({ before, after, want: SAVED.cols,
                             planningAfterOld, planningAfterNew }));
""")
eq("D4  /!\\ columns-then-view LOSES the saved columns", D["before"], ["stale1", "stale2"])
eq("D4b and writes them over PLANNING's set on the way past",
   D["planningAfterOld"], ["need30", "need60"])
eq("D4c view-then-columns keeps them", D["after"], D["want"])
eq("D4d and leaves Planning's set alone", D["planningAfterNew"], ["a", "b", "c"])


# ===========================================================================
print("\nE. one reader for the production-origin filter, where there were four")
# ===========================================================================
eq("E1  ipInHousePick is declared once", NC.count("function ipInHousePick("), 1)
# 5 = the declaration itself plus the four filter sites that now share it.
eq("E2  and read by all four filter sites", NC.count("ipInHousePick()"), 5)
eq("E2b /!\\ the old spelling survives in exactly ONE place - inside the reader",
   NC.count("getElementById('ip-in-house-filter')?.value"), 1)
ok("getElementById('ip-in-house-filter')?.value" in fn("ipInHousePick"),
   "E2c and that one place IS the reader")
# The restore in switchForecastView reads the ELEMENT, not its value, and is a
# different job (it writes the persisted pick back onto the control).
eq("E3  the persisted-pick restore is untouched",
   NC.count("const sel = document.getElementById('ip-in-house-filter');"), 1)


# ===========================================================================
print("\nF. the exports follow the tab, and the filename slug has ONE spelling")
# ===========================================================================
EXPORT = fn("downloadInventoryCSV")
ok("const statusMode = (typeof getStatusMode === 'function') ? getStatusMode() : 'warehouse';" in EXPORT,
   "F1  the CSV reads the same getStatusMode the tab drives")
ok("const includeWeekly = statusMode === 'in_house';" in EXPORT,
   "F1b so the weekly production block still keys off it")
ok(": ipVisibleColumns();" in EXPORT,
   "F1c and the column set is the view's, through ipVisibleColumns")
ok("getStatusMode() === 'in_house'" in fn("showExportDialog"),
   "F1d the export dialog's weekly section reads it too")

eq("F2  ipStatusModeSlug is declared once", NC.count("function ipStatusModeSlug("), 1)
eq("F2b and called by both writers", NC.count("ipStatusModeSlug(statusMode)"), 2)
# /!\ The ternary was spelled TWICE inside one function before this release -
# once for the xlsx branch, once for the csv one.
eq("F2c /!\\ the slug ternary is spelled ONCE (it was spelled twice)",
   len(re.findall(r"=== 'in_house' \? 'in-house-production'", NC)), 1)
ok(re.search(r"=== 'in_house' \? 'in-house-production'", nocomment(fn("ipStatusModeSlug"))) is not None,
   "F2d and that one spelling is the helper's own")
eq("F2e so no literal slug is left in the writers",
   len(re.findall(r"'in-house-production'", nocomment(fn("downloadInventoryCSV")))), 0)

F = run_node(os.path.join(SP, "f.js"), "\n" + fn("ipStatusModeSlug") + r"""
const old = (statusMode) => statusMode === 'in_house' ? 'in-house-production'
                          : statusMode === 'amazon'   ? 'amazon-fba'
                          : statusMode === 'combined' ? 'combined'
                          : 'warehouse';
const modes = ['in_house', 'amazon', 'combined', 'warehouse', 'something-else', '', null];
console.log(JSON.stringify({
  now: modes.map(ipStatusModeSlug),
  was: modes.map(old),
}));
""")
eq("F3  the helper is byte-identical to the retired ternary", F["now"], F["was"])
eq("F3b including the In-House filename the production team sorts by",
   F["now"][0], "in-house-production")


# ===========================================================================
print("\nG. the stale-mode trap the removed option opens")
# ===========================================================================
# A value with no matching option BLANKS a select. getStatusMode would then
# fall through to the same stale localStorage entry and run the in-house scope
# on the Planning tab, with an empty dropdown as the only clue.
RENDER = fn("renderInventoryTbl")
ok("[...srcSel.options].some(o => o.value === _m)" in RENDER,
   "G1  the restore refuses a mode this select has no option for")
G = run_node(os.path.join(SP, "g.js"), r"""
const run = (stored) => {
  const srcSel = { value: '', options: [{ value: 'warehouse' }, { value: 'amazon' },
                                        { value: 'combined' }] };
  const localStorage = { getItem: () => stored };
  const _m = localStorage.getItem('ipStatusMode') || 'warehouse';
  const shipped = [...srcSel.options].some(o => o.value === _m) ? _m : 'warehouse';
  const sel2 = { value: '' };
  sel2.value = stored || 'warehouse';          // the pre-v11.64 line, on a real
  const legacy = ['warehouse','amazon','combined'].includes(sel2.value) ? sel2.value : '';
  return { shipped, legacy };
};
console.log(JSON.stringify({ stale: run('in_house'), ordinary: run('amazon') }));
""")
eq("G2  /!\\ the pre-v11.64 line would have BLANKED the select on a stale mode",
   G["stale"]["legacy"], "")
eq("G2b the shipped line falls back to warehouse instead", G["stale"]["shipped"], "warehouse")
eq("G3  and an ordinary stored mode is unaffected",
   [G["ordinary"]["shipped"], G["ordinary"]["legacy"]], ["amazon", "amazon"])


# ===========================================================================
print("\nH. the reasoning survives in the source, and the file parses")
# ===========================================================================
# /!\ Every guard above runs against COMMENT-STRIPPED source, so the comments
# that explain each trap have to be required back explicitly - otherwise a
# sweep that deletes them passes (the v11.18 trap, seven times and counting).
for phrase, why in [
    ("is a VIEW now, not a Status-by option", "why the option left the dropdown"),
    ("BOTH HALVES REFUSE", "why the setter refuses as well as the control"),
    ("temporal dead zone", "why the ipView read is guarded"),
    ("COLUMNS ARE PER VIEW", "why there are two column stores"),
    ("THE VIEW FIRST, THEN THE COLUMNS", "why ipApplyView switches before it applies"),
    ("ONE reader for the production-origin filter", "why four spellings became one"),
    ("spelled TWICE inside", "why the filename slug is a function"),
]:
    ok(phrase in js, "H1  the source still explains %s" % why)

io.open(os.path.join(SP, "check.js"), "w", encoding="utf-8", newline="\n").write(js)
r = subprocess.run(["node", "--check", os.path.join(SP, "check.js")],
                   capture_output=True, text=True, encoding="utf-8")
ok(r.returncode == 0, "H2  node --check is clean", (r.stderr or "")[-300:])


print("\n" + "=" * 66)
print("  %d passed, %d failed" % (passed, failed))
print("=" * 66)
sys.exit(1 if failed else 0)
