#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.57 - row selection on the SEO breakdown tables.

Jason: "like other charts, i need to be able to click a checkbox next to the
listed items here to select them."
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1157_")
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
    start = js.index("function " + name + "(")
    i = start - 6 if js[start - 6:start] == "async " else start
    d, started, k = 0, False, js.index("{", start)
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


print("\n" + "=" * 62)
print("  v11.57  tick a breakdown row, get a series on the chart")
print("=" * 62)

ROWS = r"""
const DAYS = [];
for (let i = 0; i < 28; i++) { const d = new Date(2026, 9, 1); d.setDate(d.getDate() + i);
  DAYS.push(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`); }
const row = (day, extra, n) => Object.assign({ day, sessions: n, new_users: n, engaged_sessions: Math.round(n*.6),
  revenue: n * 2, transactions: 1, total_users: n, purchasers: 1 }, extra);
// /!\ A GA4 channel group is an arbitrary string. This one is the test.
const NASTY = `O'Brien "x" <b>bold</b>`;
const CHANS = ['Organic Search', 'Direct', NASTY];
const DEVS  = ['mobile', 'desktop'];
const SEO_TR = {
  days:  DAYS.map(d => row(d, {}, 100)),
  chan:  DAYS.flatMap(d => CHANS.map((c, i) => row(d, { channel: c }, 50 - i * 10))),
  dev:   DAYS.flatMap(d => DEVS.map((v, i) => row(d, { device: v }, 60 - i * 20))),
  pages: [],
  prev:  DAYS.map(d => row(d, {}, 80)),
};
"""

# ---------------------------------------------------------------------------
# A. The real seoTrRenderBreakdowns, driven.
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, "a.js"), ROWS + r"""
let PICKED = false;
function seoTrScopePicked() { return PICKED; }
let seoTrSel = { dim: '', keys: new Set() };
const _seoTrRendered = { channel: [], device: [] };
const seoTr = SEO_TR;
const EL = {};
globalThis.document = { getElementById: (id) => (EL[id] || (EL[id] = { id, innerHTML: '' })) };
""" + fn("esc2") + "\n" + fn("seoTrSelNoun") + "\n" + fn("seoTrRenderBreakdowns") + r"""
const out = {};
const html = (id) => EL[id] ? EL[id].innerHTML : null;
const count = (h, re) => (h.match(re) || []).length;

seoTrRenderBreakdowns({ sessions: 1 });
let h = html('seo-tr-chan-tbl');
out.plain = {
  // /!\ `<th` also matches `<thead>`. Count the TAG.
  headerCells: count(h, /<th[ >]/g),
  headerCheckboxes: count(h, /<thead>[\s\S]*?<\/thead>/)
    ? (h.slice(0, h.indexOf('</thead>')).match(/<input/g) || []).length : 0,
  rowCheckboxes: (h.slice(h.indexOf('<tbody>')).match(/<input/g) || []).length,
  cellsPerRow: ((h.slice(h.indexOf('<tbody>')).match(/<tr[\s\S]*?<\/tr>/) || [''])[0].match(/<td/g) || []).length,
  checked: count(h, / checked/g),
  disabled: count(h, / disabled/g),
  toggleCalls: (h.match(/seoTrToggleRow\('channel',\d+\)/g) || []),
  toggleAll: (h.match(/seoTrToggleAll\('[a-z]+'\)/g) || []),
  rendered: _seoTrRendered.channel,
  clear: html('seo-tr-selclear'),
};
// /!\ Nothing out of GA4 reaches an attribute.
out.nasty = {
  escapedInCell: h.includes('O&#39;Brien') || h.includes('O&#x27;Brien') || h.includes('&quot;'),
  rawInHtml: h.includes(`O'Brien "x" <b>bold</b>`),
  boldTags: count(h, /<b>/g),
};

// With a selection.
seoTrSel = { dim: 'channel', keys: new Set(['Direct']) };
seoTrRenderBreakdowns({ sessions: 1 });
h = html('seo-tr-chan-tbl');
out.selected = {
  checked: count(h, / checked/g),
  tinted: count(h, /rgba\(127,211,42,0\.10\)/g),
  dataSel1: count(h, /data-sel="1"/g),
  clear: html('seo-tr-selclear'),
  otherTableChecked: count(html('seo-tr-dev-tbl'), / checked/g),
};

// Every row ticked -> the header box is checked too.
seoTrSel = { dim: 'channel', keys: new Set(_seoTrRendered.channel) };
seoTrRenderBreakdowns({ sessions: 1 });
h = html('seo-tr-chan-tbl');
out.allChecked = { header: h.slice(0, h.indexOf('</thead>')).includes(' checked'),
                   clear: html('seo-tr-selclear') };

// LOCKED by a dropdown pick.
PICKED = true;
seoTrRenderBreakdowns({ sessions: 1 });
h = html('seo-tr-chan-tbl');
out.locked = { disabled: count(h, / disabled/g),
               rowOnclick: count(h, /<tr[^>]*onclick=/g),
               cursor: count(h, /cursor:pointer/g),
               notAllowed: count(h, /cursor:not-allowed/g),
               clear: html('seo-tr-selclear'),
               headerTitleMentionsFilter: /Channel \/ Device filter above/.test(h) };
PICKED = false;

// EMPTY breakdown: the message must span the NEW column count.
const keep = seoTr.dev;
seoTr.dev = [];
seoTrSel = { dim: '', keys: new Set() };
seoTrRenderBreakdowns({ sessions: 1 });
out.empty = { colspan: (html('seo-tr-dev-tbl').match(/colspan="(\d+)"/) || [])[1] };
seoTr.dev = keep;
console.log(JSON.stringify(out));
""")

eq("A1 six header cells - the five it had plus the checkbox column",
   A["plain"]["headerCells"], 6)
eq("A1b one select-all checkbox in the header", A["plain"]["headerCheckboxes"], 1)
eq("A1c one checkbox per row", A["plain"]["rowCheckboxes"], 3)
eq("A1d six cells per row", A["plain"]["cellsPerRow"], 6)
eq("A2 nothing ticked to start", A["plain"]["checked"], 0)
eq("A2b and nothing disabled", A["plain"]["disabled"], 0)
eq("A3 each row addresses itself by INDEX", A["plain"]["toggleCalls"],
   ["seoTrToggleRow('channel',0)", "seoTrToggleRow('channel',0)",
    "seoTrToggleRow('channel',1)", "seoTrToggleRow('channel',1)",
    "seoTrToggleRow('channel',2)", "seoTrToggleRow('channel',2)"])
eq("A3b the row and its checkbox call the SAME toggle, twice per row",
   len(A["plain"]["toggleCalls"]), 6)
eq("A3c and the header calls the select-all", A["plain"]["toggleAll"],
   ["seoTrToggleAll('channel')"])
eq("A4 the rendered order is published for the index to resolve against",
   A["plain"]["rendered"], ["Organic Search", "Direct", "O'Brien \"x\" <b>bold</b>"])

ok(A["nasty"]["escapedInCell"],
   "A5 /!\\ a GA4 string with quotes and markup renders ESCAPED")
ok(not A["nasty"]["rawInHtml"], "A5b it never appears raw")
eq("A5c and leaves no <b> behind", A["nasty"]["boldTags"], 0)

eq("A6 one ticked row is checked", A["selected"]["checked"], 1)
eq("A6b and tinted with the Ads table's own selected-row colour",
   A["selected"]["tinted"], 1)
eq("A6c carrying data-sel so a hover cannot wipe the tint",
   A["selected"]["dataSel1"], 1)
ok("Clear 1" in A["selected"]["clear"], "A6d and the way back appears",
   A["selected"]["clear"])
eq("A6e the OTHER table shows nothing ticked - one selection, one dimension",
   A["selected"]["otherTableChecked"], 0)
eq("A7 every row ticked checks the header box too", A["allChecked"]["header"], True)
ok("Clear 3" in A["allChecked"]["clear"], "A7b and the count is right",
   A["allChecked"]["clear"])

eq("A8 a dropdown pick disables every checkbox", A["locked"]["disabled"], 4)
eq("A8b and takes the row click away entirely", A["locked"]["rowOnclick"], 0)
# Found by this assertion: the disabled boxes still claimed a pointer cursor,
# which is a control saying "click me" while refusing to be clicked.
eq("A8c and nothing claims a pointer cursor", A["locked"]["cursor"], 0)
eq("A8c2 every disabled box says not-allowed instead", A["locked"]["notAllowed"], 4)
eq("A8d and hides the Clear button", A["locked"]["clear"], "")
ok(A["locked"]["headerTitleMentionsFilter"],
   "A8e the header tooltip says WHY it is disabled")

eq("A9 the empty state spans the new column count", A["empty"]["colspan"], "6")

# ---------------------------------------------------------------------------
# B. The real state machine.
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, "b.js"), r"""
let PICKED = false;
function seoTrScopePicked() { return PICKED; }
let seoTrSel = { dim: '', keys: new Set() };
const _seoTrRendered = { channel: ['Organic Search', 'Direct', 'Email'], device: ['mobile', 'desktop'] };
let RENDERS = 0;
function renderSeoTraffic() { RENDERS++; }
""" + fn("seoTrToggleRow") + "\n" + fn("seoTrToggleAll") + "\n" + fn("seoTrClearSel") + r"""
const snap = () => ({ dim: seoTrSel.dim, keys: [...seoTrSel.keys], renders: RENDERS });
const out = {};
seoTrToggleRow('channel', 0); out.one = snap();
seoTrToggleRow('channel', 1); out.two = snap();
seoTrToggleRow('channel', 0); out.untick = snap();
seoTrToggleRow('channel', 1); out.emptied = snap();     // last one off
seoTrToggleRow('channel', 0);
seoTrToggleRow('device', 1);  out.switched = snap();     // the OTHER table
seoTrToggleAll('channel');    out.allChannels = snap();
seoTrToggleAll('channel');    out.allOff = snap();
seoTrToggleAll('device');     out.allDevices = snap();
seoTrClearSel();              out.cleared = snap();
// Out of range is a no-op, not a throw.
const before = RENDERS;
seoTrToggleRow('channel', 99); out.outOfRange = { ...snap(), fired: RENDERS > before };
// LOCKED: the handlers refuse even when called directly.
PICKED = true;
const lockedBefore = RENDERS;
seoTrToggleRow('channel', 0);
seoTrToggleAll('device');
out.locked = { ...snap(), fired: RENDERS > lockedBefore };
console.log(JSON.stringify(out));
""")

eq("B1 ticking a row records it", [B["one"]["dim"], B["one"]["keys"]],
   ["channel", ["Organic Search"]])
eq("B1b a second joins it", B["two"]["keys"], ["Organic Search", "Direct"])
eq("B1c ticking again removes it", B["untick"]["keys"], ["Direct"])
eq("B2 emptying the set drops the DIMENSION with it",
   [B["emptied"]["dim"], B["emptied"]["keys"]], ["", []])

eq("B3 /!\\ ticking in the OTHER table REPLACES, never intersects",
   [B["switched"]["dim"], B["switched"]["keys"]], ["device", ["desktop"]])

eq("B4 the header box takes every row", [B["allChannels"]["dim"], B["allChannels"]["keys"]],
   ["channel", ["Organic Search", "Direct", "Email"]])
eq("B4b and clears when they are all on", [B["allOff"]["dim"], B["allOff"]["keys"]], ["", []])
eq("B4c on the other table it switches dimension too", B["allDevices"]["dim"], "device")
eq("B5 clear empties both", [B["cleared"]["dim"], B["cleared"]["keys"]], ["", []])

eq("B6 an out-of-range index is a no-op, not a throw",
   [B["outOfRange"]["keys"], B["outOfRange"]["fired"]], [[], False])
eq("B7 /!\\ while a dropdown pick is active the handlers REFUSE",
   [B["locked"]["dim"], B["locked"]["keys"], B["locked"]["fired"]], ["", [], False])

# ---------------------------------------------------------------------------
# C. The real seoTrRenderChart: what the selection actually draws.
# ---------------------------------------------------------------------------
C = run_node(os.path.join(SP, "c.js"), ROWS + r"""
let MODE = 'line';
let seoTrSel = { dim: '', keys: new Set() };
let seoTrChart = null;
const seoTr = SEO_TR;
let CFG = null;
const pnlChartMode = () => MODE;
const pnlChartBands = () => 8;
const pnlInjectChartModeToggle = () => {};
const pnlTrendRender = async (cfg) => { CFG = cfg; return { destroy() {} }; };
const seoTrWindow = () => ({ from: '2026-10-01', to: '2026-10-28', label: 'x' });
const EL = {};
globalThis.document = { getElementById: (id) => (EL[id] || (EL[id] = { id, textContent: '', innerHTML: '' })) };
""" + fn("seoTrSelNoun") + "\n" + fn("seoTrRenderChart") + r"""
const shot = () => ({ labels: CFG.datasets.map(d => d.label),
                      fills: CFG.datasets.map(d => !!d.fill),
                      widths: CFG.datasets.map(d => d.borderWidth),
                      stacks: CFG.datasets.map(d => d.stack || null),
                      mode: CFG.mode,
                      sub: EL['seo-tr-sub'].textContent });
(async () => {
  const out = {};
  await seoTrRenderChart(seoTr.days, '');        out.lineNoSel = shot();
  MODE = 'stacked';
  await seoTrRenderChart(seoTr.days, '');        out.stackedNoSel = shot();

  seoTrSel = { dim: 'channel', keys: new Set(['Direct', 'Organic Search']) };
  await seoTrRenderChart(seoTr.days, '');        out.stackedSel = shot();
  MODE = 'line';
  await seoTrRenderChart(seoTr.days, '');        out.lineSel = shot();

  seoTrSel = { dim: 'device', keys: new Set(['mobile']) };
  await seoTrRenderChart(seoTr.days, '');        out.deviceSel = shot();

  // A DROPDOWN pick wins: the selection must not reach the chart.
  seoTrSel = { dim: 'channel', keys: new Set(['Direct']) };
  await seoTrRenderChart(seoTr.chan.filter(r => r.channel === 'Direct'), 'Direct');
  out.scoped = shot();
  console.log(JSON.stringify(out));
})();
""")

# The no-selection output is the v11.56 output, which is the only form in
# which "nothing changed for anyone not using this" is checkable.
eq("C1 no selection, line: the single total series, as before",
   C["lineNoSel"]["labels"], ["Sessions", "Sessions (prior year)"])
eq("C1b and its subtitle is byte-identical to v11.56",
   C["lineNoSel"]["sub"],
   "daily · 28 buckets · prior year shifted 364d (52 whole weeks)")
eq("C2 no selection, stacked: the ranked bands, as before",
   C["stackedNoSel"]["labels"],
   ["O'Brien \"x\" <b>bold</b>", "Direct", "Organic Search", "Sessions (prior year)"])
ok("stacked by channel group" in C["stackedNoSel"]["sub"],
   "C2b and the ranked subtitle survives", C["stackedNoSel"]["sub"])

eq("C3 a selection draws ONE BAND PER TICKED ROW, biggest on top",
   C["stackedSel"]["labels"], ["Direct", "Organic Search", "Sessions (prior year)"])
eq("C3b filled, because this is the stacked view",
   C["stackedSel"]["fills"], [True, True, False])
eq("C3c and the subtitle names it",
   C["stackedSel"]["sub"],
   "daily · 28 buckets · stacked · 2 channel groups selected"
   " · prior year shifted 364d (52 whole weeks)")

eq("C4 the same selection in LINE mode draws lines, not bands",
   C["lineSel"]["fills"], [False, False, False])
eq("C4b at the line weight", C["lineSel"]["widths"], [2, 2, 1])
eq("C4c and says line rather than stacked",
   C["lineSel"]["sub"],
   "daily · 28 buckets · 2 channel groups selected"
   " · prior year shifted 364d (52 whole weeks)")

eq("C5 a DEVICE selection draws devices", C["deviceSel"]["labels"],
   ["mobile", "Sessions (prior year)"])
ok("1 device selected" in C["deviceSel"]["sub"],
   "C5b singular, not '1 devices'", C["deviceSel"]["sub"])

eq("C6 /!\\ the comparison line survives a selection (v11.56's rule)",
   C["stackedSel"]["stacks"][-1], "_prev")

eq("C7 a dropdown pick wins: the selection does not reach the chart",
   C["scoped"]["labels"], ["Sessions"])
ok("selected" not in C["scoped"]["sub"],
   "C7b and is not named in the subtitle", C["scoped"]["sub"])

# ---------------------------------------------------------------------------
# D. Static.
# ---------------------------------------------------------------------------
code = nocomment(js)
for f in ("seoTrToggleRow", "seoTrToggleAll", "seoTrClearSel", "seoTrScopePicked", "seoTrSelNoun"):
    eq("D1 %s defined once" % f, code.count("function %s(" % f), 1)
eq("D2 one selection state", code.count("let seoTrSel ="), 1)
eq("D2b one rendered cache", code.count("const _seoTrRendered ="), 1)
ok("_seoTrRendered[dim] = list.map" in code,
   "D3 the cache is published by the renderer that produced the order")
eq("D4 the noun has one definition and two readers", code.count("seoTrSelNoun("), 3)
eq("D5 version chip", len(re.findall(r">v11\.\d+ · [\d-]+<", s)), 1)
for phrase in ("ONE SELECTION, ONE DIMENSION", "they are excluded",
               "a selection is a view of"):
    ok(phrase in js, "D6 the reasoning survives: %s" % phrase[:38])

print("\n" + "=" * 62)
print("  v11.57  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
