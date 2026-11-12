#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.20 - ONE ROAS. The floor moves, not the ratio.

Jason, on v12.19: "there are now two ROAS numbers here - the ROAS is already
an ad driven result, so why include ceiling roas? the tacos number STILL does
not match sales" ... "this is becoming infuriating"

/!\ v12.19 ANSWERED AN INFLATED RATIO BY ADDING MORE RATIOS. Ceiling ROAS on
the strip, Adj ROAS and Adj vs BE in the table - three more numbers for one
question, shipped by the release that was meant to make the page usable. That
is the rule 3a defect committed at its most expensive.

The ratio was never the broken thing. ROAS is Walmart's own number and has to
keep matching their console. What was broken is that it was being compared
against a break-even derived from REAL sales while itself being measured on
ATTRIBUTED sales worth 197% of them.

    break-even on actual sales      2.90x
    attribution claims              197%
    break-even on the SAME basis    5.72x

One ROAS, one floor, and `vs Break-Even` finally means something.

And the TACoS denominator had no visible source: the strip showed $32,672 of
attributed sales and $6,179 of our revenue with nothing between them. The
channel's own sell-through is that rung.
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
print("  v12.20  one ROAS, one floor")
print("=" * 70)

# ===========================================================================
print("\nA. /!\\ v12.19's EXTRA RATIOS ARE GONE, not left standing beside it")
# ===========================================================================
# A cleanup that leaves copies behind is not a cleanup (hard rule #1).
# /!\ CODE, NOT COMMENTS. v12.25 records why the block was deleted in a
# comment that names it, and that note is worth keeping (test_v1215 A7).
import re as _re
_code = _re.sub(r"(?m)//.*$", " ", _re.sub(r"/\*[\s\S]*?\*/", " ", js))
ok("Ceiling ROAS" not in _code, "A1  /!\\ no Ceiling ROAS card")
ok("ceilRoas" not in js, "A2  ...and none of its machinery survives")
ok("roasAdj" not in js, "A3  /!\\ no Adj ROAS column")
ok("roasAdjVsBe" not in js, "A4  ...and no Adj vs BE")
# /!\ ONE card and ONE column may carry a multiple.
eq("A5  exactly one ROAS card on the strip",
   len(re.findall(r"label: colLabel\('roas', 'ROAS'\)", js)), 1)

# ===========================================================================
print("\nB. /!\\ THE FLOOR MOVES ONTO THE RATIO'S OWN BASIS")
# ===========================================================================
FLOOR = fn_flat("adsRoasFloor")
ok("_adsAttribDeflate[channel]" in FLOOR,
   "B1  the floor reads the measured over-claim")
ok("row.roas / d" in FLOOR, "B2  /!\\ ...and DIVIDES by it, so the floor rises")
ok("d > 0 && d < 1" in FLOOR,
   "B3  /!\\ only below 1 - attribution claiming LESS than the channel sold is "
   "healthy and must not move the floor")
# /!\ THE RATIO ITSELF IS UNTOUCHED. It is Walmart's own number and has to
# keep matching their console; a dashboard that silently restates a vendor's
# figure is unreconcilable with the vendor.
STAMP = fn_flat("adsStampBreakEven")
ok("c.roas * d" not in STAMP and "deflate" not in STAMP,
   "B4  /!\\ the ROAS is NOT scaled - only what it is measured against")
eq("B5  the stamp is back to three arguments",
   "function adsStampBreakEven(rows, channel, brand) {" in js, True)

D = run_node(os.path.join(SP, "_v1220_b.js"), r"""
'use strict';
// Live, 2026-08-14 -> 2026-11-12.
const SELLTHRU = 16579.07, ATTRIB = 32671.64, BE_REAL = 2.90;
const d = SELLTHRU / ATTRIB;
const beAttrib = BE_REAL / d;
const rows = [
  ['SP - AUTO - CATCH ALL - Kitty Ka zoom', 16956.00, 4854.00],
  ['Kitty Ka Zoom - Manual',                11934.00, 4220.00],
  ['SBV - KW - Mixed - Kitty Ka Zoom',       2734.00, 1325.00],
  ['SP - KW - MIXED - DOGGIJUANA',            495.00,  229.00],
];
console.log(JSON.stringify({
  claimPct: Math.round(100 / d),
  beAttrib: +beAttrib.toFixed(2),
  // the totals row
  totRoas: +(ATTRIB / 10828.27).toFixed(2),
  totVsBe: +((ATTRIB / 10828.27) - beAttrib).toFixed(2),
  rows: rows.map(([n, sales, spend]) => ({
    n, roas: +(sales / spend).toFixed(2),
    vsBe: +((sales / spend) - beAttrib).toFixed(2),
  })),
  // /!\ and against the OLD floor every one of them cleared
  clearedBefore: rows.filter(([, sa, sp]) => (sa / sp) >= BE_REAL).length,
  clearsNow: rows.filter(([, sa, sp]) => (sa / sp) >= beAttrib).length,
}));
""")

eq("B6  attribution claims 197% of what the channel sold", D["claimPct"], 197)
eq("B7  /!\\ so the break-even on the ROAS's own basis is 5.71x", D["beAttrib"], 5.71)
eq("B8  the window's ROAS is 3.02x", D["totRoas"], 3.02)
eq("B9  /!\\ ...which is 2.70x SHORT, where it used to read +0.12x", D["totVsBe"], -2.70)
# /!\ THE REGRESSION, in one pair of numbers.
eq("B10 /!\\ campaigns clearing the OLD floor", D["clearedBefore"], 1)
eq("B11 /!\\ ...and clearing the honest one", D["clearsNow"], 0)

# ===========================================================================
print("\nC. /!\\ FOUR CONSUMERS, ONE SETTING (rule #5)")
# ===========================================================================
# The stamp, the TOTAL row, the sub-floor red colour and the break-even note
# all read adsRoasFloor. Setting the deflator in one place converts all four;
# converting them one at a time is how the colour and the column disagree.
eq("C1  the deflator is assigned in exactly one place",
   len(re.findall(r"_adsAttribDeflate\[channel\] = _r\.retail", js)), 1)
ok("_adsAttribDeflate[channel] = null;" in js,
   "C2  /!\\ and RESET first - a stale factor from the last window would "
   "scale this one")
# the four readers
eq("C3  only adsRoasFloor, the note and the one assignment read it",
   len(re.findall(r"_adsAttribDeflate\[channel\]", js)), 5)
NOTE = fn_flat("adsBreakEvenNote")
ok("on actual sales" in NOTE,
   "C4  /!\\ the note carries BOTH figures, so the 2.90x is not lost")
ok("attribution claims" in NOTE, "C5  ...and says why the floor moved")

# ===========================================================================
print("\nD. the missing rung: Sell-Through")
# ===========================================================================
# Jason: "the tacos number STILL does not match sales". $32,672 of attributed
# sales and $6,179 of our revenue, 5x apart, with nothing between them.
ok("label: 'Sell-Through'" in js, "D1  the channel's own sales are on the strip")
ok("$0(_adsSellThru.retail)" in js,
   "D2  /!\\ at RETAIL, the same basis as Ad Sales beside it")
ok("ads claim ' + Math.round(100 * t.sales / _adsSellThru.retail)" in js,
   "D3  /!\\ with the over-claim stated as a share, which is the reconciliation")
ok("...(_adsSellThru ? [{" in js,
   "D4  a spread, so a missing feed costs the card and not the strip")
ok("_adsSellThru = null;" in js,
   "D5  /!\\ and it is reset per render, never carried between windows")

print("\nE. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "E1  both declare a version")
eq("E2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
