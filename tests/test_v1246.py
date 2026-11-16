#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.46 - the Channels control belongs to the page, not to one tab.

- **Jason:** *"i also don't have a way to see the category break down by
  channel"*

The ROLLUP control (Product / Category / Sub-cat) lives on the **Total** tab.
The Channels checkboxes lived INSIDE `salesChartPanelChannel`, so on Total
they were hidden AND ignored - `getSelectedChannels` returned null whenever
that panel was closed. There was no way to say "categories, Amazon US only".

Tick one channel, set ROLLUP to Category, and the bands are that channel's
categories. The table under the chart and its CSV follow, because both are
built from what was drawn (v12.38).
"""
import io, os, re, sys, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

passed = failed = 0
CHANNELS = ["amazon_us", "amazon_ca", "shopify", "chewy", "walmart"]


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


# The real updateSalesChart, sliced so the scan sites can be counted.
i = js.index("async function updateSalesChart(")
USC = js[i:js.index("\n}\n", i) + 3]

print("\n" + "=" * 70)
print("  v12.46  one Channels control, both tabs")
print("=" * 70)

# ===========================================================================
print("\nA. /!\\ THE MOVE: every checkbox survived, and left the panel")
# ===========================================================================
ch_at = s.index(">Channels:<")
pt_at = s.index('id="salesChartPanelTotal"')
pc_at = s.index('id="salesChartPanelChannel"')
ok(ch_at < pt_at and ch_at < pc_at,
   "A1  /!\\ the row now sits ABOVE both chart panels, so it is visible on "
   "whichever tab is showing. A filter you cannot see while it applies is "
   "worse than one that does not apply")
for c in CHANNELS:
    eq("A2  chk-%s exists exactly once" % c, s.count('id="chk-%s"' % c), 1)
ok(s.count('type="checkbox" id="chk-') == 5,
   "A3  /!\\ FIVE, not four - the row was cut and re-emitted rather than "
   "re-typed, and each of these is read BY ID. A dropped one is a filter "
   "that silently stops applying (the v12.09 rule)")
for c in CHANNELS:
    at = s.index('id="chk-%s"' % c)
    ok(at < pc_at, "A4  chk-%s is outside the By Channel panel" % c)
eq("A5  /!\\ and the handler repaints the TOTAL chart too - updateChannelChart "
   "alone would have left Total showing the previous scope",
   s.count('onchange="refreshSalesChart();renderSalesTbl()"'), 5)
ok('onchange="updateChannelChart();renderSalesTbl()"' not in s,
   "A6  ...and the old handler is GONE, not left on one of them")

# ===========================================================================
print("\nB. the reader, driven")
# ===========================================================================
GSC = fn_flat("getSelectedChannels")
B = run_node(os.path.join(SP, "_v1246_b.js"), r"""
let TICKED = new Set();
const document = { getElementById: (id) => id.startsWith('chk-')
  ? { checked: TICKED.has(id.slice(4)) }
  : (id === 'salesChartPanelChannel' ? { style: { display: 'none' } } : null) };
""" + GSC + r"""
const ALL = ['amazon_us','amazon_ca','shopify','chewy','walmart'];
const run = (...ks) => { TICKED = new Set(ks); return getSelectedChannels(); };
console.log(JSON.stringify({
  all:   run(...ALL),
  one:   run('amazon_us'),
  two:   run('amazon_us','shopify'),
  none:  run(),
  // /!\ the By Channel panel is reported HIDDEN in this harness, which is the
  // state that used to force a null.
  hiddenPanelStillNarrows: run('chewy'),
}));
""")
eq("B1  everything ticked means no filter at all - null, which every caller "
   "already reads as 'all channels'", B["all"], None)
eq("B2  one ticked narrows to it", B["one"], ["amazon_us"])
eq("B3  two ticked narrow to both", B["two"], ["amazon_us", "shopify"])
eq("B4  none ticked is an EMPTY scope, not a silent reset to everything",
   B["none"], [])
eq("B5  /!\\ and it narrows even with the By Channel panel hidden - that gate "
   "is what made the Total tab ignore the control",
   B["hiddenPanelStillNarrows"], ["chewy"])
ok("salesChartPanelChannel" not in GSC,
   "B6  /!\\ the panel-visibility gate is GONE from the reader, not left "
   "standing beside the fix")

# ===========================================================================
print("\nC. /!\\ ONE PREDICATE, EVERY SCAN IN THE TOTAL CHART")
# ===========================================================================
ok("const chanSel = getSelectedChannels();" in USC,
   "C1  the Total chart reads the same control")
ok("const inScope = (r) => inRange(r.week_start) && inChan(r.channel);" in USC,
   "C2  /!\\ one predicate: the date AND the channel")
eq("C3  /!\\ every row scan goes through it - seven of them, and adding the "
   "channel test at six of seven is exactly how a chart and the table under "
   "it come to disagree about which rows they describe",
   USC.count("filter(inScope)"), 7)
eq("C4  /!\\ and NOT ONE date-only scan is left behind",
   USC.count("filter(r => inRange(r.week_start))"), 0)
ok("if (inChan(r.channel)) relevantChannels.add(r.channel)" in USC,
   "C5  /!\\ an unticked channel is not 'relevant', so the coverage line "
   "stops reporting it as a feed that has not landed - which is the warning "
   "Jason's screenshot carries in red")
ok("const addPrev = (dateStr, u, ch) => {\n          if (!inChan(ch)) return;" in USC,
   "C6  /!\\ and the previous-period line shares the scope, or the "
   "comparison is against a different business")
eq("C7  both addPrev callers pass the channel",
   USC.count("r.channel));"), 2)

D = run_node(os.path.join(SP, "_v1246_d.js"), r"""
const rows = [
  { week_start: '2026-11-02', channel: 'amazon_us' },
  { week_start: '2026-11-02', channel: 'chewy' },
  { week_start: '2025-01-06', channel: 'amazon_us' },
  { week_start: '2026-11-02', channel: 'walmart' },
];
const parseLocalDate = (v) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v||''));
  return m ? new Date(+m[1], +m[2]-1, +m[3]) : null; };
const from = new Date(2026,0,1), to = new Date(2026,11,31);
const inRange = w => { const d = parseLocalDate(w); if (!d) return false;
  if (from && d < from) return false; if (to && d > to) return false; return true; };
const mk = (chanSel) => { const inChan = (ch) => !chanSel || chanSel.includes(ch);
  return (r) => inRange(r.week_start) && inChan(r.channel); };
console.log(JSON.stringify({
  all:   rows.filter(mk(null)).length,
  amz:   rows.filter(mk(['amazon_us'])).map(r => r.channel),
  two:   rows.filter(mk(['amazon_us','chewy'])).map(r => r.channel),
  none:  rows.filter(mk([])).length,
}));
""")
eq("C8  with no pick the date window alone decides - 3 of 4 rows", D["all"], 3)
eq("C9  /!\\ a pick narrows WITHIN the window, and the out-of-window Amazon "
   "row stays out", D["amz"], ["amazon_us"])
eq("C10 two channels keep both", D["two"], ["amazon_us", "chewy"])
eq("C11 an empty pick draws nothing rather than everything", D["none"], 0)

# ===========================================================================
print("\nD. the empty-chart diagnostic narrows with it")
# ===========================================================================
ok("inScopeRows: (salesData[mid] || []).filter(inScope).length," in USC,
   "D1  /!\\ otherwise '412 total rows, 47 in date range' under an empty "
   "chart sends the operator hunting a data gap when the answer is a ticked "
   "checkbox")
ok("in view" in USC and "${r.inScopeRows} in view" in USC,
   "D2  ...and its label says what it now counts")
ok("inRangeRows" not in js,
   "D3  the old key is gone from the file entirely, reader included")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
