#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.51 - a wholesale price on the New Product Launch scenario.

Jason: "allow me to add a wholesale price for these scenarios."

The block is sliced out of the shipped file and driven with its locals
supplied, for the reason test_v1149 records: pricingNewRender is gated on
pnlData, a module-scope `let` that injected browser scope cannot set.
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1151_")
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


# Slice forward from the block's own first statement to the statement that
# follows it. (recBlock appears EARLIER in this function too, so the search
# has to start inside the block - the trap that cost v11.49 and v11.51 a
# round each.)
_i = js.index("      let wholesaleBlock = '';")
BLOCK = js[_i:js.index("      recBlock = `<div", _i)]

print("\n" + "=" * 62)
print("  v11.51  a wholesale price on the launch scenario")
print("=" * 62)

# ---------------------------------------------------------------------------
# A. The input.
# ---------------------------------------------------------------------------
eq("A1 one Wholesale input in the markup", s.count('id="pnew-wholesale"'), 1)
_inp = re.search(r'<input[^>]*id="pnew-wholesale"[^>]*>', s).group(0)
ok('oninput="pricingNewRender()"' in _inp, "A1b wired to the same render as every other Step 1 field")
ok('type="number"' in _inp and 'min="0"' in _inp, "A1c numeric, no negative invoice")
_lbl = s[s.rindex("<label", 0, s.index('id="pnew-wholesale"')):s.index('id="pnew-wholesale"')]
# ⚠ rule 3a / rule #3: the Chewy tab already calls this exact thing
# "Wholesale price per unit". A second wording for one concept is the defect.
ok("Wholesale price per unit" in _lbl,
   "A2 labelled VERBATIM as the Chewy tab labels it", _lbl[-60:])
ok(s.count("WHOLESALE PRICE PER UNIT") + s.count("Wholesale price per unit") >= 2,
   "A2b so both tabs carry the same words")
eq("A3 read exactly once", nocomment(js).count("pnew-wholesale"), 1)
ok("Math.max(0, parseFloat" in nocomment(js), "A3b and clamped at zero")

# ---------------------------------------------------------------------------
# B. The arithmetic, driven.
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, "b.js"), """
globalThis.skumigEsc = (v) => String(v == null ? '' : v)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
function block(wholesalePerUnit, o) {
  const packSize = o.packSize, cogs = o.cogs, targetContrib = o.targetContrib;
  const targetPrice = o.targetPrice || 0;
""" + BLOCK + """
  return wholesaleBlock;
}
const text = (h) => h.replace(/<[^>]*>/g, ' ').replace(/\\s+/g, ' ').trim();
const tip = (h) => (h.match(/title="([^"]*)"/) || [])[1] || '';
// Jason's own scenario shape: 6-pack, COGS $0.10/unit = $0.60 a listing.
const SIX = { packSize: 6, cogs: 0.60, targetContrib: 15, targetPrice: 9.99 };
const ONE = { packSize: 1, cogs: 0.60, targetContrib: 15, targetPrice: 0 };
console.log(JSON.stringify({
  off:      block(0, SIX),
  healthy:  { html: block(0.75, SIX), text: text(block(0.75, SIX)), tip: tip(block(0.75, SIX)) },
  thin:     { text: text(block(0.11, SIX)) },
  single:   { text: text(block(2.00, ONE)) },
  noMsrp:   { text: text(block(0.75, Object.assign({}, SIX, { targetPrice: 0 }))) },
}));
""")

eq("B1 no wholesale price renders NOTHING, so every existing scenario is "
   "byte-identical", B["off"], "")

_h = B["healthy"]["text"]
ok("$0.75/unit" in _h, "B2 the per-unit invoice price is shown", _h)
# 0.75 x 6 = 4.50 invoiced, less 0.60 COGS = 3.90 GM = 86.7%
ok("$4.50/listing" in _h, "B2b multiplied out by the bundle", _h)
ok("$3.90" in _h, "B2c GM $ = invoiced less COGS", _h)
ok("86.7%" in _h, "B2d GM % on the wholesale basis", _h)
ok("8% of your $9.99 MSRP" in _h or "45% of your" in _h or "% of your $9.99 MSRP" in _h,
   "B3 and where it sits against the MSRP you named", _h)
ok("% of your" not in B["noMsrp"]["text"],
   "B3b which is omitted when no MSRP was named", B["noMsrp"]["text"])
ok("/listing" not in B["single"]["text"],
   "B4 a single item shows no per-listing figure - it would be the same number",
   B["single"]["text"])

# 0.11 x 6 = 0.66 invoiced, less 0.60 = 0.06 = 9.1%, under the 15% floor.
ok("9.1%" in B["thin"]["text"], "B5 a thin margin reports its real number", B["thin"]["text"])
ok("var(--sp-red)" in BLOCK and "var(--sp-green)" in BLOCK,
   "B5b and the block has both a pass and a fail colour")

# ---------------------------------------------------------------------------
# C. RULE 3a. Two bases on one page must never share a word.
# ---------------------------------------------------------------------------
_wb = nocomment(BLOCK).replace("targetContrib", "").replace("contribPct", "")
ok("Contribution" not in _wb and "Contrib" not in _wb,
   "C1 the wholesale block never says Contribution - that is the RETAIL basis")
ok("GM" in _wb, "C1b it uses GM, the declared WHOLESALE pair (v10.53)")
ok("Contribution" in s or "Contrib" in s,
   "C1c while the retail ladder still says Contribution")

_tip = B["healthy"]["tip"]
ok("WHOLESALE basis" in _tip, "C2 the tooltip names the basis", _tip)
ok("no platform fees" in _tip,
   "C2b and says WHY it differs - a wholesale invoice carries none", _tip)
# ⚠ v11.30: Chewy's GM nets allowances and this one cannot, so the shared
# prefix must not be left to imply a deduction we are not making.
ok("Allowances are NOT deducted" in _tip and "Chewy" in _tip,
   "C3 and names the exclusion against the Chewy tab's GM by name", _tip)
ok(str(15) in _tip and "floor" in _tip,
   "C3b and which floor it is checked against", _tip)

# ---------------------------------------------------------------------------
# D. It is a SECOND basis, not a rung. It must not touch the ladder.
# ---------------------------------------------------------------------------
ok("scenarios" not in _wb and "pricingLadderPayloads" not in _wb,
   "D1 the wholesale basis never reaches the retail ladder")
ok("platformAtPrice" not in _wb and "feePct" not in _wb,
   "D1b and no platform fee is applied to an invoice price")
code = nocomment(js)
eq("D2 rendered in exactly one place", code.count("${wholesaleBlock}"), 1)
ok("let wholesaleBlock = '';" in code and "if (wholesalePerUnit > 0) {" in code,
   "D3 opt-in, so the default page is unchanged")

for phrase in ("THE WHOLESALE BASIS, stated separately on purpose",
               "it is NOT the Chewy tab's GM"):
    ok(phrase in js, "D4 the reasoning survives: %s" % phrase[:36])

eq("D5 version chip", len(re.findall(r">v11\.\d+ · [\d-]+<", s)), 1)

print("\n" + "=" * 62)
print("  v11.51  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
