#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.00 - TACoS on the Amazon Ads tab.

Jason: "on amazon p&L - i need a TACOS % scorecard as well (this will need to
come from sku economics data unless it can be derived)"

/!\ THE ANSWER TO HIS PARENTHETICAL IS NO, AND IT WAS MEASURED FIRST.
sku_economics carries exactly one ad column, `sponsored_products_total`.
US, trailing 90 days, by ad product:

    sponsored_products  $44,250   |  sponsored_display  $1,753
    sponsored_brands    $10,337   |  sponsored_tv       $1,739

SP is 76% of spend. Over 12 full weeks an SP-only TACoS reads 12.4% against
a real 16.5% - it would hide a quarter of the spend on the one card whose
job is to report what advertising costs in TOTAL.

/!\ AND TACoS ALREADY EXISTED, on the Page Performance tile, as
`ad spend / net sales`. This suite pins the two to one arithmetic (rule 3a).
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


def nocomment(t):
    return re.sub(r"(?m)^\s*//.*$", "", t)


def line_of(pat):
    for ln in js.split(chr(10)):
        if pat in ln:
            return ln
    raise SystemExit('not found: ' + pat)


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
print("  v12.00  TACoS: ad spend over TOTAL sales")
print("=" * 68)

TAC = fn_flat("adsTacosFor")

# ===========================================================================
print("\nA. one definition, not a second spelling")
# ===========================================================================
eq("A1  adsTacosFor is declared exactly once",
   len(re.findall(r"function adsTacosFor\(", js)), 1)

# The Page Performance tile that already carries this measure.
ok("const tacosPct      = totalNetSales > 0 ? (totalAdSpend / totalNetSales * 100) : 0;" in js,
   "A2  the existing Page Performance TACoS is still there")
ok("tile('TACoS'," in js, "A3  ...and still labelled TACoS")

# /!\ SAME ARITHMETIC. spend / netSales * 100, both of them.
ok("(spend || 0) / ns * 100" in TAC,
   "A4  /!\\ the new card uses the SAME arithmetic: spend / net sales * 100")

# /!\ AND IT IS NOT DERIVED FROM THE SP COLUMN. That was the whole question.
ok("sponsored_products_total" not in TAC,
   "A5  /!\\ the helper never reads sponsored_products_total (SP is 76% of spend)")
ok("sponsored" not in nocomment(TAC),
   "A6  /!\\ ...nor any other single ad product: the numerator is total Ad Spend")

# Both source tables are named on the card, because it joins two feeds.
# v12.08 - RE-POINTED. The sources are a per-channel registry now: the
# literal list was Amazon's, and it rendered on every channel, so the
# Walmart tab cited Amazon's feeds under a card that could never hold a
# number. The guarantee is unchanged - this card joins TWO feeds and names
# both - so it is asserted against the registry's Amazon entry.
ok("src: TACOS_SRC[channel]," in js,
   "A7a the card's sources follow the channel")
SRCREG = js[js.index("const TACOS_SRC = {"):]
SRCREG = SRCREG[:SRCREG.index("\n};") + 3]
ok("amazon:  ['amazon_ad_spend', 'sku_economics']" in SRCREG,
   "A7  the card names BOTH feeds it joins")

# ===========================================================================
print("\nB. the real adsTacosFor, driven")
# ===========================================================================
DRIVER = r"""
'use strict';
let pnlRegion = 'US';
let aggImpl = () => ({ tot: { netSales: 118023 }, from: '2026-10-12', to: '2026-11-08' });
function amzFeeAgg(range) { return aggImpl(range); }
let seenRange = null;

__COVER__
__DAYS__
__TAC__

const R = { from: '2026-10-12', to: '2026-11-09' };
const out = {};

// --- B1 the live window, measured off the database -----------------------
aggImpl = (r) => { seenRange = r; return { tot: { netSales: 118023 }, from: '2026-10-12', to: '2026-11-08' }; };
let a = adsTacosFor('amazon', null, 20312, R);
out.pct = +a.pct.toFixed(2);
out.ns = a.netSales;
out.from = a.from; out.to = a.to; out.why = a.why;
out.rangePassedThrough = seenRange;

// --- B2 a campaign selection refuses outright ----------------------------
a = adsTacosFor('amazon', [{ x: 1 }], 20312, R);
out.selPct = a.pct; out.selWhy = a.why;
// ...and an EMPTY selection array is not a selection.
a = adsTacosFor('amazon', [], 20312, R);
out.emptySelPct = +a.pct.toFixed(2);

// --- B3 another channel --------------------------------------------------
a = adsTacosFor('chewy', null, 20312, R);
out.chewyPct = a.pct; out.chewyWhy = a.why;

// --- B4 EU, where no Amazon ad spend is loaded ---------------------------
pnlRegion = 'EU';
a = adsTacosFor('amazon', null, 20312, R);
out.euPct = a.pct; out.euWhy = a.why;
pnlRegion = 'US';

// --- B5 no sales in the window -------------------------------------------
aggImpl = () => ({ tot: { netSales: 0 }, from: R.from, to: R.to });
a = adsTacosFor('amazon', null, 20312, R);
out.noSalesPct = a.pct; out.noSalesWhy = a.why;

// --- B6 the aggregator throws --------------------------------------------
aggImpl = () => { throw new Error('statement timeout'); };
a = adsTacosFor('amazon', null, 20312, R);
out.threwPct = a.pct; out.threwWhy = a.why;

// --- B7 zero spend is a READING, not a refusal ---------------------------
aggImpl = () => ({ tot: { netSales: 5000 }, from: R.from, to: R.to });
a = adsTacosFor('amazon', null, 0, R);
out.zeroSpendPct = a.pct;
// ...and so is a missing spend figure.
a = adsTacosFor('amazon', null, null, R);
out.nullSpendPct = a.pct;

// --- B8 a malformed aggregate is a refusal, not a crash ------------------
aggImpl = () => ({});
a = adsTacosFor('amazon', null, 20312, R);
out.noTotPct = a.pct;

console.log(JSON.stringify(out));
"""

R = run_node(os.path.join(SP, "_v1200_a.js"), DRIVER.replace("__COVER__", line_of("const TACOS_MIN_COVERAGE"))
                                                     .replace("__DAYS__", fn_flat("_adsDayCount"))
                                                     .replace("__TAC__", TAC))

# B1 - the live numbers, read off the database on 2026-11-11.
eq("B1  /!\\ 20,312 spend over 118,023 net sales reads 17.21%", R["pct"], 17.21)
eq("B2  ...on the net sales it was given", R["ns"], 118023)
eq("B3  no refusal reason on the happy path", R["why"], None)
# /!\ THE SALES WINDOW IS THE AGGREGATOR'S, NOT THE AD WINDOW. sku_economics
# is weekly, so a 29-day ad window buys whole weeks - and the card reports
# the days its SALES actually cover rather than implying they match.
eq("B4  /!\\ the card reports the SALES window", [R["from"], R["to"]],
   ["2026-10-12", "2026-11-08"])
eq("B5  ...and the ad window is passed through untouched",
   R["rangePassedThrough"], {"from": "2026-10-12", "to": "2026-11-09"})

# B2 - a selection cannot narrow the denominator, so there is NO ANSWER.
eq("B6  /!\\ a campaign selection yields no number", R["selPct"], None)
ok("cannot narrow the sales side" in (R["selWhy"] or ""),
   "B7  ...and says why, naming organic sales", R["selWhy"])
eq("B8  an EMPTY selection array is not a selection", R["emptySelPct"], 17.21)

# B3/B4 - the two scopes with no feed behind them.
# v12.08 - RE-POINTED. Chewy HAS a denominator now (its own revenue, from
# chewy_sales_weekly x chewy_catalog), so it no longer refuses for lack of
# a feed - it refuses because this harness has fetched nothing. The
# guarantee is unchanged for a channel that genuinely has none.
eq("B9  a channel with no sales feed yields no number", R["chewyPct"], None)
ok("not loaded yet" in (R["chewyWhy"] or ""),
   "B10 /!\\ Chewy is SUPPORTED now - it waits on its denominator rather "
   "than refusing outright", R["chewyWhy"])
eq("B11 /!\\ EU yields no number", R["euPct"], None)
ok("No EU Amazon ad spend" in (R["euWhy"] or ""),
   "B12 ...because a EU TACoS would read 0.0% against real sales", R["euWhy"])

# B5/B6 - an empty or broken denominator.
eq("B13 no net sales yields no number", R["noSalesPct"], None)
ok("no denominator" in (R["noSalesWhy"] or ""), "B14 ...and offers a wider period")
eq("B15 an aggregator that throws yields no number", R["threwPct"], None)
ok("statement timeout" in (R["threwWhy"] or ""),
   "B16 /!\\ ...carrying the real reason rather than a bare dash", R["threwWhy"])

# B7 - zero is a measurement. Refusing it would hide a real state.
eq("B17 /!\\ zero spend is 0.0%, not a refusal", R["zeroSpendPct"], 0)
eq("B18 a missing spend figure is also 0.0%", R["nullSpendPct"], 0)
eq("B19 a malformed aggregate refuses rather than throwing", R["noTotPct"], None)

# ===========================================================================
print("\nC. where the card sits, and which way is good")
# ===========================================================================
# v12.07 - /!\ TACoS MOVED OUT OF THE ARRAY LITERAL into a channel gate:
#   ].concat(channel === 'amazon' ? [{ ...TACoS... }] : [])
# because on Walmart and Chewy it rendered a permanent dash with
# `amazon_ad_spend` chips under it. The slice runs to the END of the
# strip expression now, so the card is inside it.
STRIP = js[js.index("cards.innerHTML = selBanner + pnlCardStrip(["):]
STRIP = STRIP[:STRIP.index("\n  }\n")]

ok("label: 'TACoS %'" in STRIP, "C1  the card is on the Ads strip")
# /!\ BESIDE ACOS: same question, two denominators.
ok(STRIP.index("colLabel('acos'") < STRIP.index("label: 'TACoS %'"),
   "C2  /!\\ it still follows ACOS - same question, two denominators")
# /!\ AND IT IS GATED ON THE ONE CHANNEL THAT CAN COMPUTE IT. adsTacosFor
# refuses every other, so anywhere else the card is a permanent dash
# citing another channel's feeds - which is what Jason saw on Walmart.
# v12.08 - RE-POINTED. v12.07 gated this card to Amazon because elsewhere
# it rendered a permanent dash citing `amazon_ad_spend`. That fixed the
# symptom and removed the feature Jason had asked for. It renders wherever
# a denominator exists now, and the SOURCES follow the channel - which is
# what actually fixes the chips.
ok("].concat(TACOS_SRC[channel] ? [{" in STRIP,
   "C2b /!\\ it renders on every channel the registry declares")
ok("channel === 'amazon' ? [{" not in STRIP,
   "C2c /!\\ ...and the Amazon-only gate is gone")

CARD = STRIP[STRIP.index("label: 'TACoS %'"):STRIP.index("}] : []).concat(")]
# Good when DOWN and reported in POINTS - the two things ACOS also does.
ok("chip(tacos.pct, tacosPrev.pct, false, true)" in CARD,
   "C3  /!\\ good when DOWN (false) and in POINTS (true), like ACOS")
# /!\ BOTH sides are guarded, not just this period's. A prev period that
# refused (EU, a selection, an empty window) has no TACoS to compare against,
# and chipping against a null would print a 100% move every time.
ok("(tacos.pct == null || tacosPrev.pct == null) ? null" in CARD,
   "C4  no delta chip unless BOTH periods produced a number")

# /!\ THE SCOPE TOTAL, NOT THE SELECTION-AWARE ONE. Pairing selected spend
# with catalogue-wide sales would read far too low and would move on every
# tick - the two sides must describe one population.
ok("adsTacosFor(channel, selRows, t && t.spend" in js,
   "C5  /!\\ the numerator is the SCOPE total `t`, never `cardT`")
ok("cardT" not in CARD, "C6  ...and the card never reaches for cardT")

# The refusal reason becomes the tooltip, so a dash is never unexplained.
ok("tip: tacos.pct == null\n          ? tacos.why" in CARD or "? tacos.why" in CARD,
   "C7  a dash carries its reason on the tooltip")
ok("whole weeks only" in CARD,
   "C8  /!\\ the tooltip says the sales side is whole weeks")
ok("Nothing is prorated" in CARD,
   "C9  /!\\ ...and that nothing is prorated, because there are no daily sales")

# ===========================================================================
print("\nD. the chip agrees with CLAUDE.md (v11.63's rule)")
# ===========================================================================
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
ok(chip is not None, "D1  the version chip is in the markup")
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(cur is not None, "D2  CLAUDE.md declares a current version")
eq("D3  the chip and CLAUDE.md name the SAME release", chip.group(1), cur.group(1))

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
