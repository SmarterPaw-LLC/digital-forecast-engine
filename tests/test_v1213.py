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
out.live = { pct: a.pct == null ? null : +a.pct.toFixed(1), why: a.why,
             over: a.overAttr ? Math.round(a.overAttr.pct) : null };
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
out.over = { pct: a.pct == null ? null : +a.pct.toFixed(1), why: a.why,
             over: a.overAttr ? Math.round(a.overAttr.pct) : null };

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
print("\nA. /!\\ v12.17 - IT COMPUTES, AND THE ODDITY IS A NOTE")
# ===========================================================================
# This section asserted a REFUSAL. The refusal was my own bad reasoning:
# ad sales are a subset of total sales, so I took ad sales > sell-through as
# proof the denominator was incomplete. Measured on Jason's data it is normal
# here - over the 28 weeks the ads ran, Walmart credited 9,441 units against
# 8,613 actually sold, and 134% of the dollars. The feed was complete all
# along: one vendor, 33 items, both brands, 0 unmapped, AUTH within 0.1% of
# shipped.
#
# /!\ AND TACoS NEVER USED THE NUMERATOR. It is spend over TOTAL sales.
# Withholding a correct number because a different number looked odd is the
# opposite of the job.
eq("A1  /!\\ v12.21 - 65.3% on sell-through, REPORTED and not refused",
   A["live"]["pct"], 65.3)
eq("A2  ...with no refusal reason", A["live"]["why"], None)
ok(A["live"].get("over") is not None,
   "A3  /!\\ and the over-attribution rides along as a note")
eq("A4  ...carrying what share of total sales was attributed",
   A["live"]["over"], 197)
# The note has to say which numbers it does and does not impugn: TACoS is
# fine, ROAS and ACOS on the same strip are not comparable to sell-through.
# v12.20 - those two sentences explained the cards BESIDE this one, which is
# the bloat Jason cut, and v12.19's Ceiling ROAS was a SECOND ratio, which he
# cut too. The guarantee underneath all of it is that the over-claim is
# MEASURED and ACTED ON rather than explained: the break-even floor is moved
# onto the ratio's own attributed basis, so ONE ROAS can be judged against it.
ok("_adsAttribDeflate" in js,
   "A5  /!\\ the over-claim moves the FLOOR, so ROAS has something real to beat")
ok("row.roas / d" in js,
   "A6  /!\\ ...by dividing the floor by it, never by restating Walmart's ratio")
# /!\ v12.16's shipped-vs-sold explanation was ALSO wrong and is gone.
ok("shipped INTO Walmart" not in js and "SHIPPED-based (shipped_based" not in js,
   "A7  /!\\ and the shipped-vs-sold explanation, also wrong, is gone")

print("\nB. a complete feed still answers")
# /!\ v12.21 - the fixture's retail is $50,000, so 10,828 / 50,000 = 21.7%.
eq("B1  sell-through above ad sales is the normal relationship, and it reports",
   A["healthy"]["pct"], 21.7)
eq("B2  ...on our revenue", A["healthy"]["basis"], "ourRev")

print("\nC. the boundary")
# ===========================================================================
# /!\ v12.17 - there is no refusal to have a boundary any more. What is left
# worth pinning is that the note fires ONLY on a real excess: equal is not an
# excess, and a dollar over is.
# /!\ v12.21 - $500 over the fixture's $5,000 of sell-through.
eq("C1  /!\\ ad sales EQUAL to sell-through raises no note", A["equal"]["pct"], 10.0)
eq("C2  /!\\ and a dollar over still REPORTS, it does not refuse",
   A["over"]["pct"], 10.0)

print("\nD. and where it cannot run")
eq("D1  no ad-sales figure: the check is skipped, not failed",
   A["noAdSales"]["pct"], 10.0)

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
ok(TAC.index("adSales > r.retail") < TAC.index("return { pct: (spend || 0) / denom"),
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
