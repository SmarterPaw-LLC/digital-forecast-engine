#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.01 - the TACoS card took the whole Ads tab down.

Jason, on the Amazon P&L -> Ads tab, one release after v12.00 shipped:

    X Cannot read properties of undefined (reading 'from')

...and NOTHING else rendered. Not the six cards that pre-date TACoS, not the
chart, not the campaign table.

/!\ MINE, AND ONE LINE OLD. `getPnlPrevDateRange(cur)` REQUIRES the current
range - it reads `cur.from` on its third line. v12.00 called it with no
argument at all.

/!\ WHY NO TEST OF MINE CAUGHT IT: test_v1200 drove `adsTacosFor` over twelve
shapes and asserted the card's markup as TEXT. It never executed the four
lines of the RENDERER that call them, so the one call with a wrong signature
sat in the only part of the change nothing ran. A helper proven in isolation
says nothing about the code that calls it.
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
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v12.01  one card may not take down the tab")
print("=" * 68)

TAC  = fn_flat("adsTacosFor")
PREV = fn_flat("getPnlPrevDateRange")

# The renderer's TACoS block, sliced from the real file.
BLOCK = js[js.index("  let tacos = { pct: null"):js.index("  const cards = document.getElementById(ch.host + '-cards');")]

# ===========================================================================
print("\nA. THE DEFECT REPRODUCED")
# ===========================================================================
REPRO = r"""
'use strict';
__PREV__
const out = {};

// --- A1 the v12.00 call: no argument at all ------------------------------
try { getPnlPrevDateRange(); out.bareThrew = false; }
catch (e) { out.bareThrew = true; out.bareMsg = e.message; }

// --- A2 the shipped call: the current range ------------------------------
const r = getPnlPrevDateRange({ from: '2026-11-02', to: '2026-11-08' });
out.prev = r;

// --- A3 a one-day window still has a previous day ------------------------
out.oneDay = getPnlPrevDateRange({ from: '2026-11-08', to: '2026-11-08' });

console.log(JSON.stringify(out));
"""
A = run_node(os.path.join(SP, "_v1201_a.js"), REPRO.replace("__PREV__", PREV))

ok(A["bareThrew"], "A1  /!\\ getPnlPrevDateRange() with no argument THROWS")
ok("reading 'from'" in A.get("bareMsg", ""),
   "A2  /!\\ ...with Jason's exact message", A.get("bareMsg"))
eq("A3  given the range, it returns the week before",
   A["prev"], {"from": "2026-10-26", "to": "2026-11-01"})
eq("A4  a one-day window yields the day before",
   A["oneDay"], {"from": "2026-11-07", "to": "2026-11-07"})

# ===========================================================================
print("\nB. the renderer passes the range, and cannot throw")
# ===========================================================================
ok("getPnlPrevDateRange(tacosRange)" in js,
   "B1  /!\\ the prev range is computed FROM the current one")
eq("B2  /!\\ and the argument-less call is gone",
   len(re.findall(r"getPnlPrevDateRange\(\s*\)", js)), 0)

# /!\ THE BLAST RADIUS, not just the bug. Six cards that pre-date TACoS went
# dark because of this one. A scorecard must not be able to destroy its page.
ok("try {" in BLOCK and "} catch (e) {" in BLOCK,
   "B3  /!\\ the whole TACoS computation is guarded")
ok("console.warn('TACoS card:'" in BLOCK,
   "B4  ...and a throw is reported, not swallowed")
ok("tacos = { pct: null, why: 'TACoS could not be computed: '" in BLOCK,
   "B5  ...and degrades to a dash WITH its reason on the tooltip")
# The seeds must be declared before the try, or the catch leaves them undefined
# and the card strip throws on `tacos.pct` instead - the same defect moved.
ok(BLOCK.index("let tacos = { pct: null") < BLOCK.index("try {"),
   "B6  /!\\ both are seeded BEFORE the try, so the catch cannot leave a hole")
ok(BLOCK.index("let tacosPrev = { pct: null };") < BLOCK.index("try {"),
   "B7  ...including the prev-period one")

# ===========================================================================
print("\nC. the helper refuses a window it was not given")
# ===========================================================================
DRIVER = r"""
'use strict';
let pnlRegion = 'US';
let aggCalls = [];
function amzFeeAgg(range) {
  aggCalls.push(range);
  // /!\ This is what the REAL amzFeeAgg does with no range: it falls back to
  // getPnlDateRange(), i.e. a DIFFERENT window than the ad spend beside it.
  if (!range) return { tot: { netSales: 999999 }, from: 'FALLBACK', to: 'FALLBACK' };
  return { tot: { netSales: 118023 }, from: range.from, to: '2026-11-08' };
}
__TAC__
const out = {};
let a;

a = adsTacosFor('amazon', null, 20312, null);
out.nullRange = a.pct; out.nullWhy = a.why;

a = adsTacosFor('amazon', null, 20312, {});
out.emptyRange = a.pct;

a = adsTacosFor('amazon', null, 20312, { from: '2026-10-12' });
out.halfRange = a.pct;

out.aggNeverCalledWithoutRange = aggCalls.every(r => r && r.from && r.to);

a = adsTacosFor('amazon', null, 20312, { from: '2026-10-12', to: '2026-11-09' });
out.goodPct = +a.pct.toFixed(2);

console.log(JSON.stringify(out));
"""
C = run_node(os.path.join(SP, "_v1201_b.js"), DRIVER.replace("__TAC__", TAC))

eq("C1  /!\\ a null range yields no number", C["nullRange"], None)
ok("cannot match its sales to its spend" in (C["nullWhy"] or ""),
   "C2  ...and says the two sides would not match", C["nullWhy"])
eq("C3  an empty range object also refuses", C["emptyRange"], None)
eq("C4  a half-filled range also refuses", C["halfRange"], None)
# /!\ THE POINT OF C1-C4: amzFeeAgg falls back to getPnlDateRange() when it
# is handed nothing, which would have measured sales over one window and
# spend over another, in a single ratio, with nothing on screen saying so.
ok(C["aggNeverCalledWithoutRange"],
   "C5  /!\\ the aggregator is NEVER reached without an explicit window")
eq("C6  a real range still works", C["goodPct"], 17.21)

# ===========================================================================
print("\nD. the chip agrees with CLAUDE.md")
# ===========================================================================
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip is not None and cur is not None, "D1  both declare a version")
eq("D2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
