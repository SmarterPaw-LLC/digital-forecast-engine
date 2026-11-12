#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.19 - the number attribution cannot move, and tooltips that stop arguing.

Jason: "i DO NOT understand why the sales figures are different here" ...
"wtf. i need this data to be usable. stop with the excuses and fix it" ...
"what is with this tooltip? how many times have i begged you not to do this?"

Walmart's 14-day attribution claims 197% of everything the channel sold, so
the ROAS beside it (3.02x against a 2.90x floor) could not be checked against
anything.

CEILING ROAS is the question that does not depend on attribution: if EVERY
sale the channel made were ad-driven, what would ROAS be? Total sell-through
over ad spend, on the same retail basis as the floor.

    sell-through  $16,579        ad spend  $10,828
    CEILING ROAS  1.53x          break-even  2.90x

/!\ The best case is 47% SHORT of break-even. Attributed sales can be wrong by
any factor and this number does not move.
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


print("\n" + "=" * 70)
print("  v12.19  ceiling ROAS, the deflator, and tooltips that stop arguing")
print("=" * 70)

STAMP = fn_flat("adsStampBreakEven")

# ===========================================================================
print("\nA. /!\\ THE CEILING, AND WHY IT IS A PROOF")
# ===========================================================================
DRIVER = r"""
'use strict';
// Live figures, 2026-08-14 -> 2026-11-12.
const RETAIL = 16579.07, SPEND = 10828.27, ATTRIB = 32671.64, FLOOR = 2.90;
const ceiling = RETAIL / SPEND;
const deflate = RETAIL / ATTRIB;
// the five campaigns, as the feed holds them
const C = [
  ['SP - AUTO - CATCH ALL - Kitty Ka zoom', 4854.00, 16956.00],
  ['Kitty Ka Zoom - Manual',                 null,    null],
];
console.log(JSON.stringify({
  ceiling: +ceiling.toFixed(2),
  floor: FLOOR,
  // /!\ THE WHOLE POINT: the BEST case is short of break-even.
  shortOfFloor: ceiling < FLOOR,
  gapPct: Math.round((1 - ceiling / FLOOR) * 100),
  deflate: +deflate.toFixed(4),
  attribPct: Math.round(100 * ATTRIB / RETAIL),
  // the headline campaign, before and after
  roas:    +(16956.00 / 4854.00).toFixed(2),
  roasAdj: +((16956.00 / 4854.00) * deflate).toFixed(2),
}));
"""
A = run_node(os.path.join(SP, "_v1219_a.js"), DRIVER)

eq("A1  /!\\ CEILING ROAS is 1.53x on the live window", A["ceiling"], 1.53)
ok(A["shortOfFloor"],
   "A2  /!\\ and it is BELOW the 2.90x break-even - the best case does not pay")
eq("A3  ...by 47%", A["gapPct"], 47)
eq("A4  attribution claims 197% of what the channel sold", A["attribPct"], 197)
eq("A5  so the deflator is 0.5074", A["deflate"], 0.5074)
# /!\ The top campaign read 3.49x and cleared the floor. It does not.
eq("A6  the headline campaign reads 3.49x", A["roas"], 3.49)
eq("A7  /!\\ ...and 1.77x once deflated, which is UNDER break-even",
   A["roasAdj"], 1.77)

# ===========================================================================
print("\nB. the ceiling does NOT use the attributed figure")
# ===========================================================================
# This is the guarantee the card exists for. If it ever divides by `t.sales`
# it becomes another number attribution can move, and it is worth nothing.
i = js.index("let ceilRoas =")
CEIL = js[i:js.index("\n  const cards =", i)]
ok("tacos.retail / t.spend" in CEIL,
   "B1  /!\\ sell-through over SPEND, never over attributed sales")
ok(re.search(r"roas:\s*t\.sales", CEIL) is None,
   "B2  /!\\ and `t.sales` is never its numerator")
ok("attribPct" in CEIL,
   "B3  the over-claim is carried as a READING, not used in the ratio")
ok("adsRoasFloorKnown" in CEIL,
   "B4  /!\\ the floor is only drawn when it was actually derived - a 1.0 "
   "fallback would colour the card against a line nobody computed")
ok("catch (e)" in CEIL,
   "B5  /!\\ and a throw costs this card its number, not the tab (v12.01)")

# ===========================================================================
print("\nC. the deflator is MEASURED, and only when it corrects something")
# ===========================================================================
ok("deflate > 0 && deflate < 1" in STAMP,
   "C1  /!\\ only below 1 - attribution claiming LESS than the channel sold is "
   "a healthy state with nothing to correct")
ok("c.roasAdj     = (d != null && c.roas != null) ? c.roas * d : null;" in STAMP,
   "C2  it is a SCALAR on the existing ROAS, so the ranking cannot move")
ok("c.roasAdjVsBe" in STAMP, "C3  ...and the gap to the floor rides with it")
ok("res.totals.sales > _r.retail" in js,
   "C4  /!\\ the factor comes from the two feeds, not from a constant")
ok("_adsDeflate = _r.retail / res.totals.sales;" in js,
   "C5  ...sell-through over attributed sales")
ok("adsStampBreakEven(res.campaigns, channel, adsBrandFilterValue(ch), _adsDeflate);" in js
   and "adsStampBreakEven([res.totals], channel, adsBrandFilterValue(ch), _adsDeflate);" in js,
   "C6  /!\\ BOTH call sites pass it - the footer and the rows must agree")

# ===========================================================================
print("\nD. the columns exist on every Walmart campaign view")
# ===========================================================================
for k in ("roasAdj", "roasAdjVsBe"):
    eq("D-%s  declared in both column lists" % k,
       len(re.findall(r"\{ k: '" + k + r"'", js)), 2)
    ok("WM_ADS_TIP." + k in js, "D-%s  ...with a tooltip" % k)

# ===========================================================================
print("\nE. /!\\ TOOLTIPS SAY HOW, NOT WHY")
# ===========================================================================
# Jason, on the TACoS tooltip: "how many times have i begged you not to do
# this?" Five paragraphs, of which one was derivation. The rest argued that
# the basis was right, compared it with the Amazon tab, and explained what
# attribution does to the cards BESIDE it.
i = js.index("      tip: tacos.pct == null\n        ? tacos.why")
TIP = js[i:js.index("\n    }] : []).concat((TACOS_SRC[channel]", i)]
lits = re.findall(r"'((?:[^'\\]|\\.)*)'", TIP)
chars = sum(len(x) for x in lits)
ok(chars < 420, "E1  /!\\ the TACoS tooltip is under 420 characters of prose", chars)
# /!\ THE JUSTIFICATION IS GONE, named phrase by phrase so a rewrite that
# re-adds any of it fails rather than merely growing the count back.
for gone, why in (
    ("NOT the sales figure", "it argued the basis was right"),
    ("Amazon tab", "it compared another tab"),
    ("Nothing is prorated", "it answered a question nobody asked"),
    ("cannot be reconciled", "it explained the cards beside it"),
    ("recorded when the file was uploaded", "provenance is not derivation"),
):
    ok(gone not in TIP, "E-  /!\\ gone: %s (%s)" % (gone, why))
# ...and what MUST survive is the arithmetic and the two skew warnings.
ok("Ad spend \\u00f7 our revenue" in TIP, "E2  the operands are named")
ok("sell-through units \\u00d7 cost-per-each" in TIP,
   "E3  ...and so is how the denominator is built")
ok("reads high" in TIP and "reads low" in TIP,
   "E4  /!\\ both skew warnings survive - they say which way the number is wrong")

j = js.index("      tip: ceilRoas.roas == null ? ceilRoas.why")
CTIP = js[j:js.index("\n    }] : []).concat(COLS.some(c => c.k === 'orders')", j)]
clits = re.findall(r"'((?:[^'\\]|\\.)*)'", CTIP)
cchars = sum(len(x) for x in clits)
ok(cchars < 220, "E5  /!\\ and the NEW card's tooltip was written short too", cchars)
ok("AN UPPER BOUND, NOT A FORECAST" not in CTIP,
   "E6  /!\\ ...including the paragraph I had just bloated it with")
ok("Credits ads with every sale" in CTIP,
   "E7  the one thing a reader has to know survives, in a clause")

print("\nF. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "F1  both declare a version")
eq("F2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
