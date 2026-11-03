#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.49 - a target price on the New Product Launch scenario.

Jason: "on this pricing scenario, i can't set a target msrp to run the
scenario."

pricingNewRender is a 61KB function gated on `pnlData`, a module-scope `let`
that injected browser scope cannot set (the v10.93 rule), and signing in with
production credentials to exercise it is not something a test should do. So
the two blocks this release ADDS are sliced out of the shipped file and driven
directly, with their locals supplied - the real source, not a re-derivation.
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1149_")
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


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


def slice_between(start, end, label):
    i = js.index(start)
    j = js.index(end, i)
    return js[i:j]


# The two blocks this release adds, lifted out of the shipped file.
def slice_block(start):
    """Brace-matched slice, so inserting code AFTER the block cannot drag
    unrelated statements into it. v11.50 added platformAtPrice between this
    block and the anchor this used to end on, and the harness then died on an
    undefined `cogs` - an end-anchor is only as stable as its neighbour."""
    i = js.index(start)
    d, started, k = 0, False, js.index("{", i)
    while k < len(js):
        if js[k] == "{":
            d += 1; started = True
        elif js[k] == "}":
            d -= 1
            if started and d == 0:
                return js[i:k + 1]
        k += 1
    raise SystemExit("unbalanced block at %s" % start[:40])


LADDER = slice_block("      if (targetPrice > 0) {")
HEAD = slice_between("      const tgtPay = targetPrice > 0",
                     "      recBlock = `<div", "headline")

print("\n" + "=" * 62)
print("  v11.49  a target price on the pricing scenario")
print("=" * 62)

# ---------------------------------------------------------------------------
# A. The input exists, is wired, and is read ONCE.
# ---------------------------------------------------------------------------
eq("A1 one Target price input in the markup", s.count('id="pnew-target-price"'), 1)
_inp = re.search(r'<input[^>]*id="pnew-target-price"[^>]*>', s).group(0)
ok('oninput="pricingNewRender()"' in _inp, "A1b wired to the same render as every other Step 1 field")
ok('type="number"' in _inp and 'min="0"' in _inp, "A1c numeric, no negative price")
ok('title="' in _inp and "WHOLE listing" in _inp,
   "A1d and the per-listing basis is on a TOOLTIP, not printed on the page (rule 1a)")
_lbl = s[s.rindex("<label", 0, s.index('id="pnew-target-price"')):s.index('id="pnew-target-price"')]
ok("Target price (MSRP)" in _lbl, "A1e labelled in Jason's own words")
eq("A2 read exactly once", nocomment(js).count("pnew-target-price"), 1)
ok("Math.max(0, parseFloat" in nocomment(js), "A2b and clamped at zero")

# ---------------------------------------------------------------------------
# B. THE LADDER. The target is a rung through the SAME renderer.
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, "b.js"), """
function mk(targetPrice, base) {
  let scenarios = JSON.parse(JSON.stringify(base));
""" + LADDER + """
  return scenarios;
}
const BASE = [
  { label: 'Your cost floor', price: 1.53, rec: false },
  { label: 'Undercut market -10%', price: 2.00, rec: false },
  { label: 'At market', price: 2.22, rec: true },
  { label: 'Premium +10%', price: 2.44, rec: false },
];
const FLOOR_ONLY = [
  { label: 'Min viable', price: 1.53, rec: true },
  { label: '+10%', price: 1.68, rec: false },
];
console.log(JSON.stringify({
  none:   mk(0, BASE).map(x => [x.label, x.price, !!x.rec]),
  mid:    mk(2.10, BASE).map(x => [x.label, x.price, !!x.rec]),
  below:  mk(1.00, FLOOR_ONLY).map(x => [x.label, x.price, !!x.rec]),
  above:  mk(9.99, BASE).map(x => [x.label, x.price, !!x.rec]),
  marked: mk(2.10, BASE).filter(x => x.isTarget).length,
}));
""")

eq("B1 no target price leaves the ladder byte-identical",
   B["none"], [["Your cost floor", 1.53, False], ["Undercut market -10%", 2.0, False],
               ["At market", 2.22, True], ["Premium +10%", 2.44, False]])
ok(["Your target price", 2.1, True] in B["mid"],
   "B2 a target price becomes its own rung, highlighted", B["mid"])
eq("B2b and it sorts into position by price",
   [r[0] for r in B["mid"]],
   ["Your cost floor", "Undercut market -10%", "Your target price", "At market", "Premium +10%"])
eq("B3 exactly ONE highlighted row - two would be two recommendations",
   sum(1 for r in B["mid"] if r[2]), 1)
ok(not any(r[2] for r in B["mid"] if r[0] == "At market"),
   "B3b and the old recommendation gives up the highlight")
eq("B4 a target BELOW the floor still sorts first, not dropped",
   [r[0] for r in B["below"]], ["Your target price", "Min viable", "+10%"])
eq("B4b and still carries the highlight",
   [r[2] for r in B["below"]], [True, False, False])
eq("B5 a target far above every rung sorts last",
   B["above"][-1][0], "Your target price")
eq("B6 the rung is marked so the renderer can tell it apart", B["marked"], 1)

# ---------------------------------------------------------------------------
# C. THE HEADLINE. It must READ the ladder row, never recompute.
# ---------------------------------------------------------------------------
C = run_node(os.path.join(SP, "c.js"), """
globalThis.skumigEsc = (v) => String(v == null ? '' : v)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
function headline(targetPrice, pay, opts) {
  const targetContrib = opts.targetContrib, packSize = opts.packSize;
  const cogs = opts.cogs, cogsPerUnit = opts.cogsPerUnit, feePct = opts.feePct;
  const platformUsed = opts.platformUsed, adPct = opts.adPct, minPrice = opts.minPrice;
  const hasMarket = opts.hasMarket, marketRateForMySize = opts.marketRateForMySize;
  const mySizeLabelLong = opts.mySizeLabelLong;
  // v11.51 put the wholesale block inside this slice. Zero keeps it inert, so
  // these assertions stay about the HEADLINE; test_v1151 drives the block.
  const wholesalePerUnit = opts.wholesalePerUnit || 0;
  const pricingLadderPayloads = pay;
  let frameColor = 'var(--sp-green)', frameBg = 'x';
  let headline = 'UNCHANGED', headSub = 'UNCHANGED';
""" + HEAD + """
  return { headline, headSub, frameColor, frameBg };
}
const OPTS = { targetContrib: 15, packSize: 6, cogs: 0.60, cogsPerUnit: 0.10,
  feePct: 45.8, platformUsed: 45.8, adPct: 0, minPrice: 1.53,
  hasMarket: false, marketRateForMySize: null, mySizeLabelLong: '6 count' };
// Jason's own scenario: COGS $0.10/unit x 6, 45.8% fees, 15% floor.
const PAY = [
  { price: 1.53, proceeds: 0.83, contribAbs: 0.23, contribPct: 15.0 },
  { price: 2.49, proceeds: 1.35, contribAbs: 0.75, contribPct: 30.12 },
  { price: 1.00, proceeds: 0.54, contribAbs: -0.06, contribPct: -6.0 },
];
const MKT = Object.assign({}, OPTS, { hasMarket: true, marketRateForMySize: 2.22 });
console.log(JSON.stringify({
  none:   headline(0, PAY, OPTS),
  clears: headline(2.49, PAY, OPTS),
  short:  headline(1.00, PAY, OPTS),
  market: headline(2.49, PAY, MKT),
  missing: headline(7.77, PAY, OPTS),
}));
""")

eq("C1 no target price leaves the headline untouched",
   [C["none"]["headline"], C["none"]["headSub"]], ["UNCHANGED", "UNCHANGED"])
eq("C1b and a price with no matching rung changes nothing either",
   C["missing"]["headline"], "UNCHANGED")

_c = C["clears"]["headline"]
ok("At $2.49" in _c, "C2 the headline names the price asked about", _c)
ok("30.1% contribution" in _c, "C2b and the contribution it yields", _c)
ok("$0.75" in _c, "C2c in dollars as well as percent", _c)
ok("clears your 15% floor" in _c, "C2d with the verdict against the floor", _c)
ok("$0.42/unit" in _c and "6-pack" in _c,
   "C2e and the per-unit price, since the input is per LISTING", _c)
eq("C2f green frame when it clears", C["clears"]["frameColor"], "var(--sp-green)")

_s = C["short"]["headline"]
ok("short of your 15% floor" in _s, "C3 a price under the floor says so", _s)
ok("-6.0% contribution" in _s or "−6.0" in _s,
   "C3b and reports the NEGATIVE contribution rather than clamping it", _s)
eq("C3c red frame", C["short"]["frameColor"], "var(--sp-red)")
# The figure and the word are separated by markup, so assert both.
ok("$0.53" in C["short"]["headSub"] and "short" in C["short"]["headSub"],
   "C3d the sub-line quantifies the gap to the floor", C["short"]["headSub"])
ok("Cut COGS" in C["short"]["headSub"], "C3e and says what to do about it")

ok("$0.27" in C["market"]["headSub"] and "above it" in C["market"]["headSub"],
   "C4 with competitors, it also says where the price sits vs market",
   C["market"]["headSub"])
ok("not the market" in C["none"]["headSub"] or
   "checked against your cost only" in C["clears"]["headSub"],
   "C4b and with none, it says the check is cost-only", C["clears"]["headSub"])

# ⚠ The headline must not be a second calculator sitting above the table.
_h = nocomment(HEAD)
for bad in ("proceeds - cogs", "contribAbs =", "contribPct ="):
    ok(bad not in _h, "C5 the headline does not recompute (%s)" % bad)
for good in ("tgtPay.contribPct", "tgtPay.contribAbs", "tgtPay.proceeds", "tgtPay.price"):
    ok(good in _h, "C5b it reads %s off the ladder row" % good)

# ---------------------------------------------------------------------------
# D. Structure.
# ---------------------------------------------------------------------------
for phrase in ("A TARGET PRICE CHANGES THE QUESTION",
               "The figures are READ BACK OFF THE LADDER ROW, never recomputed",
               "Two highlighted rows would be two"):
    ok(phrase in js, "D1 the reasoning survives: %s" % phrase[:38])

eq("D2 version chip", len(re.findall(r">v11\.\d+ · [\d-]+<", s)), 1)
# ⚠ index.html has carried 2 more "<label" than "</label>" since long
# before this release (HEAD measures the same 2), because the string appears
# inside JS as well as markup. The guarantee worth asserting is that THIS
# change added a balanced pair, not that a pre-existing skew is zero.
eq("D3 this change left the label skew exactly as it found it",
   s.count("<label") - s.count("</label>"), 2)

print("\n" + "=" * 62)
print("  v11.49  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
