#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.52 - Walmart ad ROAS is judged against break-even, not against 1.0.

Jason: "i need to be able to analyze walmart.com ads and make decisions about
what changes to make."

The fixture rows are the REAL figures the live feeds return, so the 3.21
break-even this suite asserts is the one the app will compute.
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1152_")
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
    for pre in ("async function ", "function "):
        i = js.find(pre + name + "(")
        if i >= 0:
            break
    if i < 0:
        raise SystemExit("missing %s" % name)
    d, started, k = 0, False, js.index("{", i)
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


DEFS = "\n".join(fn(n) for n in
                 ("adsBrandFilterValue", "adsRoasFloor", "adsBreakEvenNote", "adsLoadBreakEven"))

# The REAL per-brand rollup the derivation query returns today.
ROWS = [
    {"brand": "Kitty Ka-Zoom", "retail": 42402.04, "wholesale": 22309.45, "cogs": 9107.02},
    {"brand": "Doggijuana", "retail": 7321.50, "wholesale": 5435.91, "cogs": 1988.31},
    {"brand": "Meowijuana", "retail": 3300.00, "wholesale": 2600.00, "cogs": 767.52},
]

print("\n" + "=" * 62)
print("  v11.52  break-even ROAS on a 1P channel")
print("=" * 62)

A = run_node(os.path.join(SP, "a.js"), """
globalThis._adsBreakEven = {};
const ROWS = """ + json.dumps(ROWS) + r""";
let FAIL = false, CALLS = 0;
globalThis.getSB = async () => ({
  rpc: async (_f, a) => {
    CALLS++;
    if (FAIL) return { data: null, error: { message: 'boom' } };
    globalThis.LAST_SQL = a.query;
    return { data: ROWS, error: null };
  },
});
console.warn = () => {};
""" + DEFS + r"""
(async () => {
  const out = {};
  // Before the derivation lands, the floor must be the old 1.0.
  out.beforeFloor = adsRoasFloor('walmart', '');
  out.beforeNote = adsBreakEvenNote('walmart', '');

  await adsLoadBreakEven('walmart');
  out.overall = _adsBreakEven.walmart.overall;
  out.kk = _adsBreakEven.walmart.byBrand['Kitty Ka-Zoom'];
  out.floorAll = adsRoasFloor('walmart', '');
  out.floorKK = adsRoasFloor('walmart', 'Kitty Ka-Zoom');
  out.floorUnknownBrand = adsRoasFloor('walmart', 'Nope');
  out.note = adsBreakEvenNote('walmart', 'Kitty Ka-Zoom');
  out.sqlHasJoins = ['walmart_sales_weekly', 'walmart_cost_per_each', 'product_cogs']
    .every(t => LAST_SQL.includes(t));
  out.callsAfterSecond = (await adsLoadBreakEven('walmart'), CALLS);

  // Other channels: never queried, floor stays 1.0.
  const before = CALLS;
  await adsLoadBreakEven('amazon');
  out.amazonQueried = CALLS > before;
  out.floorAmazon = adsRoasFloor('amazon', '');
  out.noteAmazon = adsBreakEvenNote('amazon', '');

  // A failed derivation must fall back to 1.0, not to a guess.
  delete _adsBreakEven.chewy;
  FAIL = true;
  _adsBreakEven.walmart = undefined;
  await adsLoadBreakEven('walmart');
  out.floorAfterFail = adsRoasFloor('walmart', '');
  out.noteAfterFail = adsBreakEvenNote('walmart', '');
  console.log(JSON.stringify(out));
})();
""")

# ---------------------------------------------------------------------------
# A. The arithmetic.  1 / (share x GM)
# ---------------------------------------------------------------------------
# KK: 22309.45 / 42402.04 = 52.6% kept;  (22309.45-9107.02)/22309.45 = 59.2% GM
ok(abs(A["kk"]["sharePct"] - 52.6) < 0.1,
   "A1 we keep 52.6%% of retail on Kitty Ka-Zoom", A["kk"]["sharePct"])
ok(abs(A["kk"]["gmPct"] - 59.2) < 0.1,
   "A1b and make 59.2%% GM on that wholesale dollar", A["kk"]["gmPct"])
ok(abs(A["kk"]["roas"] - 3.21) < 0.02,
   "A2 so BREAK-EVEN is 3.21x, not 1.00x", A["kk"]["roas"])
ok(A["overall"]["roas"] < A["kk"]["roas"],
   "A3 and the blended figure is LOWER, which is why the floor follows the brand",
   [A["overall"]["roas"], A["kk"]["roas"]])

# ---------------------------------------------------------------------------
# B. The floor, and what it is applied to.
# ---------------------------------------------------------------------------
eq("B1 before the derivation lands the floor is the old 1.0", A["beforeFloor"], 1)
eq("B1b and nothing is claimed on the coverage line", A["beforeNote"], "")
ok(abs(A["floorKK"] - 3.21) < 0.02, "B2 the brand filter picks that brand's floor", A["floorKK"])
ok(A["floorAll"] != A["floorKK"], "B2b All brands uses the blended one")
ok(abs(A["floorUnknownBrand"] - A["floorAll"]) < 1e-9,
   "B3 an unrecognised brand falls back to the blend, never to 1.0")

ok("3.21x" in A["note"], "B4 the coverage line states the line being judged against", A["note"])
# 52.6 rounds to 53 on the note, which is what toFixed(0) should do.
ok("53% of retail" in A["note"] and "59% GM" in A["note"],
   "B4b and the two inputs it came from, so it can be argued with", A["note"])

# ---------------------------------------------------------------------------
# C. Every other channel is byte-identical to v11.51.
# ---------------------------------------------------------------------------
ok(A["amazonQueried"] is False, "C1 a non-1P channel runs NO derivation query")
eq("C1b and keeps the 1.0 floor", A["floorAmazon"], 1)
eq("C1c and adds nothing to its coverage line", A["noteAmazon"], "")

# ---------------------------------------------------------------------------
# D. Failure, and the loop that must not happen.
# ---------------------------------------------------------------------------
eq("D1 a derivation that throws falls back to 1.0", A["floorAfterFail"], 1)
eq("D1b and claims no break-even it could not compute", A["noteAfterFail"], "")
eq("D2 a second call does not re-query", A["callsAfterSecond"], 1)
ok(A["sqlHasJoins"],
   "D3 the derivation reads the three live feeds, not a stored constant")

# ---------------------------------------------------------------------------
# E. Structure.
# ---------------------------------------------------------------------------
code = nocomment(js)
ok("F === 'x' && v < 1)" not in code, "E1 the flat 1.0 threshold is gone from the cell renderer")
ok("adsRoasFloor(channel, adsBrandFilterValue(ch))" in code,
   "E1b and the cell is coloured against the channel's floor")
eq("E2 the kick-off is guarded exactly once",
   code.count("_adsBreakEven[channel] === undefined"), 1)
_be = nocomment(fn("adsLoadBreakEven"))
ok("{ pending: true }" in _be,
   "E2b and marks itself in flight BEFORE the await, so it cannot loop")
ok(not re.search(r"roas\s*[:=]\s*3\.2", code),
   "E3 the break-even is DERIVED - no 3.21 is typed anywhere")
# ⚠ Share and margin must come from one joined population.
ok("group by 1" in _be and "net_sales > 0" in _be,
   "E4 one grouped pass, so share and margin describe the same rows")

for phrase in ("1.0 is the wrong line on a 1P channel", "DERIVED, NEVER TYPED",
               "Share and margin are computed over the SAME joined rows"):
    ok(phrase in js, "E5 the reasoning survives: %s" % phrase[:34])

eq("E6 version chip", len(re.findall(r">v11\.\d+ · [\d-]+<", s)), 1)

print("\n" + "=" * 62)
print("  v11.52  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
