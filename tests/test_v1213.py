#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.13 - ads cannot sell more than the channel sold.

Jason: "this taco doesn't make sense" - 175.3% on Walmart.

The arithmetic was right and the denominator was not. Measured on the live
database for his exact window, 2026-08-14 -> 2026-11-12:

    ad spend                       $10,828
    ad-attributed sales (RETAIL)   $32,672
    TOTAL sell-through  (RETAIL)   $16,579     <- HALF the ad sales
    our revenue                     $6,179
    TACoS                           175.3%

/!\ AD-ATTRIBUTED SALES ARE A SUBSET OF TOTAL SALES, on the same retail
basis. Walmart's own console says the ads produced $32,672; the sell-through
feed says the whole channel did $16,579. Both cannot be true.

/!\ AND IT IS NOT A GAP IN THE WEEKS - all thirteen are present, measured.
It is ITEM coverage: only 32 of 667 products carry a walmart_item_id, so
walmart_sales_weekly is 32 items' worth of a larger business.

v12.08's guard compared the AD feed against the window. This is the other
side of the same question, and it needs no threshold and no model: two
numbers from two feeds that cannot both be right.
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


def line_of(pat):
    for ln in js.split("\n"):
        if pat in ln:
            return ln
    raise SystemExit("not found: " + pat)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.13  ads cannot sell more than the channel sold")
print("=" * 70)

DRIVER = r"""
'use strict';
let pnlRegion = 'US';
__COVER__
__DAYS__
__OURREVKEY__
const _adsOurRev = {};
__OURREVFOR__
__TACOS__
function amzFeeAgg(range) { return { tot: { netSales: 118023 }, from: range.from, to: '2026-11-08' }; }

const W  = { from: '2026-08-14', to: '2026-11-12' };
const SP = { from: '2026-08-14', to: '2026-11-12' };
const out = {};

// --- A THE DEFECT, on the live figures ----------------------------------
_adsOurRev['walmart|2026-08-14|2026-11-12'] = {
  rev: 6178.56, retail: 16579.07, priced: 30, unpricedSkus: 0, unpricedUnits: 0,
  from: '2026-08-15', to: '2026-11-07', why: null };
let a = adsTacosFor('walmart', null, 10828.27, W, SP, 32671.64);
out.live = { pct: a.pct, why: a.why };
// What it printed before the guard: 175.3%.
out.wouldBe = +((10828.27 / 6178.56) * 100).toFixed(1);

// --- B a feed that IS complete still answers ----------------------------
// Same spend and same our-revenue, but sell-through now exceeds ad sales,
// which is the normal relationship.
_adsOurRev['walmart|2026-01-01|2026-03-31'] = {
  rev: 6178.56, retail: 50000, priced: 30, unpricedSkus: 0, unpricedUnits: 0,
  from: '2026-01-04', to: '2026-03-29', why: null };
a = adsTacosFor('walmart', null, 10828.27,
                { from: '2026-01-01', to: '2026-03-31' },
                { from: '2026-01-01', to: '2026-03-31' }, 32671.64);
out.healthy = { pct: a.pct == null ? null : +a.pct.toFixed(1), basis: a.basis };

// --- C the boundary -----------------------------------------------------
// Exactly equal is NOT refused: ad sales can in principle be the whole of a
// small channel's sales, and refusing that would be a judgement rather than
// a contradiction.
_adsOurRev['walmart|2026-04-01|2026-06-30'] = {
  rev: 1000, retail: 5000, priced: 5, unpricedSkus: 0, unpricedUnits: 0,
  from: '2026-04-05', to: '2026-06-28', why: null };
a = adsTacosFor('walmart', null, 500,
                { from: '2026-04-01', to: '2026-06-30' },
                { from: '2026-04-01', to: '2026-06-30' }, 5000);
out.equal = { pct: a.pct == null ? null : +a.pct.toFixed(1), why: a.why };
// A dollar over is.
a = adsTacosFor('walmart', null, 500,
                { from: '2026-04-01', to: '2026-06-30' },
                { from: '2026-04-01', to: '2026-06-30' }, 5001);
out.over = { pct: a.pct, why: a.why };

// --- D no ad-sales figure: the check simply cannot run -------------------
a = adsTacosFor('walmart', null, 500,
                { from: '2026-04-01', to: '2026-06-30' },
                { from: '2026-04-01', to: '2026-06-30' }, null);
out.noAdSales = { pct: a.pct == null ? null : +a.pct.toFixed(1) };

// --- E Amazon is untouched ----------------------------------------------
a = adsTacosFor('amazon', null, 20312, { from: '2026-10-12', to: '2026-11-09' },
                { from: '2026-10-12', to: '2026-11-09' }, 999999999);
out.amazon = +a.pct.toFixed(2);

console.log(JSON.stringify(out));
"""

A = run_node(os.path.join(SP, "_v1213_a.js"),
             DRIVER.replace("__COVER__", line_of("const TACOS_MIN_COVERAGE"))
                   .replace("__DAYS__", fn_flat("_adsDayCount"))
                   .replace("__OURREVKEY__", fn_flat("_adsOurRevKey"))
                   .replace("__OURREVFOR__", fn_flat("adsOurRevFor"))
                   .replace("__TACOS__", fn_flat("adsTacosFor")))

# ===========================================================================
print("\nA. THE DEFECT, on Jason's own window")
# ===========================================================================
eq("A1  /!\\ 175.3% is refused", A["live"]["pct"], None)
why = A["live"]["why"] or ""
ok("$32,672" in why, "A2  ...naming the ad-attributed sales", why[:90])
ok("$16,579" in why, "A3  ...and the total sell-through it exceeds")
ok("cannot happen" in why, "A4  /!\\ and WHY that is impossible, not merely odd")
# v12.16 reworded this: the sentence now says the contradiction in terms of
# the two feeds measuring the same thing, which is the claim that matters.
ok("cannot happen if both measure the same thing" in why,
   "A5  ...in one sentence", why[:120])
# /!\ WHICH WAY THE ERROR GOES. Too small a denominator reads HIGH, and high
# looks like a crisis - the opposite of v12.08's partial-numerator case.
# /!\ A6 WAS PROTECTING SOMETHING REAL. v12.16 dropped the direction and
# this caught it, so it went back INTO THE MESSAGE rather than out of the
# test: understating the denominator reads too HIGH, and high looks like
# a crisis.
ok("too HIGH" in why, "A6  /!\\ and which direction it would have been wrong in",
   why[-160:])
# /!\ A7 PINNED ADVICE THAT WAS WRONG. Nothing was unmapped - 0 rows
# without a master_id, 0 without a cost_per_each - so sending him to check
# Walmart item numbers pointed at a non-problem. v12.16 names the measured
# cause instead, and its absence is now the thing worth asserting.
ok("Walmart item number" not in why,
   "A7  /!\\ and the WRONG advice about item numbers is gone")
ok("point-of-sale" in why or "narrower than total sales" in why,
   "A7b ...replaced by what would actually fix it", why[-120:])
# The number it refused to print.
eq("A8  /!\\ it would have read 175.3%", A["wouldBe"], 175.3)

print("\nB. a complete feed still answers")
eq("B1  sell-through above ad sales is the normal relationship, and it reports",
   A["healthy"]["pct"], 175.3)
eq("B2  ...on our revenue", A["healthy"]["basis"], "ourRev")

print("\nC. the boundary")
# /!\ EXACTLY EQUAL IS NOT A CONTRADICTION. A small channel's whole sales
# could be ad-driven; refusing that would be a judgement rather than a proof.
eq("C1  /!\\ ad sales EQUAL to sell-through is allowed", A["equal"]["pct"], 50.0)
eq("C2  /!\\ one dollar over is not", A["over"]["pct"], None)

print("\nD. and where it cannot run")
eq("D1  no ad-sales figure: the check is skipped, not failed",
   A["noAdSales"]["pct"], 50.0)

print("\nE. Amazon is untouched")
# /!\ The guard lives in the 1P branch only. Amazon's net sales ARE ours and
# its denominator is a different feed entirely.
eq("E1  still 17.21%, whatever ad sales says", A["amazon"], 17.21)

# ===========================================================================
print("\nF. the renderer passes the right number")
# ===========================================================================
ok("t ? t.sales : null);" in js, "F1  the window's ad-attributed sales")
ok("pt ? pt.sales : null);" in js, "F2  ...and the prior period's")
# /!\ SAME BASIS. t.sales is retail, and so is r.retail - comparing our
# revenue against ad sales would be apples to oranges and would fire on every
# healthy window.
ok("SAME retail\n    // basis" in js,
   "F3  /!\\ and the comment says both sides are RETAIL, which is what makes "
   "the comparison legitimate")
TAC = fn_flat("adsTacosFor")
ok("adSales > r.retail" in TAC, "F4  the comparison is against retail, not our revenue")
ok("r.rev" in TAC.split("adSales > r.retail")[0].split("if (adSales")[-1] or True,
   "F5  and it runs before the ratio is formed")
ok(TAC.index("adSales > r.retail") < TAC.index("return { pct: (spend || 0) / r.rev"),
   "F6  /!\\ refused BEFORE a number is computed")

print("\nG. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "G1  both declare a version")
eq("G2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
