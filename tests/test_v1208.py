#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.08 - TACoS on Walmart and Chewy, divided by OUR revenue.

Jason asked for this, answered the one question it needed - our revenue, not
retail - and then watched v12.07 HIDE the card on those two tabs instead of
giving it a denominator. This is that, built.

/!\ THE BASIS IS THE WHOLE POINT. On Amazon, net sales IS what we receive. On
Walmart and Chewy we are 1P: the sales number those feeds report is RETAIL,
which the app already calls "a vanity. We never see this money." Measured on
the live database, 2026-08-11 -> 2026-11-09:

    Walmart retail $16,579   our revenue $6,179   (we keep ~37%)

Dividing by retail would make Walmart look roughly TWICE as efficient as
Amazon for the same dollars, under a label that already means something else
one tab over.

/!\ AND A PARTIAL NUMERATOR OVER A FULL DENOMINATOR READS LOW. Same live data:

    90-day window   spend $1,021 over SIX days / revenue $6,179 over 13 weeks
                    -> 16.5%, which looks healthy
    the one week both feeds cover
                    -> spend $1,179.44 / our revenue $651.95 = 180.9%

Same channel, same month. Section D is that guard.
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


def const_obj(name):
    i = js.index("const " + name + " = {")
    return js[i:js.index("\n};", i) + 3]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.08  TACoS on the 1P channels, on our revenue")
print("=" * 70)

DRIVER = r"""
'use strict';
let pnlRegion = 'US';
__COVER__
__ISYMD__
__DAYS__
__OURREVKEY__
const _adsOurRev = {};
__OURREVFOR__
__TACOS__
function amzFeeAgg(range) { return { tot: { netSales: 118023 }, from: range.from, to: '2026-11-08' }; }

const out = {};
const FULL = { from: '2026-11-04', to: '2026-11-10' };
const FULLSPAN = { from: '2026-11-04', to: '2026-11-10' };

// --- A the live Walmart week, both feeds covering the same ground ---------
_adsOurRev['walmart|2026-11-04|2026-11-10'] = {
  rev: 651.9482, retail: 1669.89, priced: 23, unpricedSkus: 0, unpricedUnits: 0,
  from: '2026-11-07', to: '2026-11-07', why: null };
let a = adsTacosFor('walmart', null, 1179.44, FULL, FULLSPAN);
out.wm = { pct: a.pct == null ? null : +a.pct.toFixed(1), basis: a.basis,
           ns: a.netSales == null ? null : +a.netSales.toFixed(2), retail: a.retail };

// ...and what RETAIL would have said, which is the whole reason for the basis
out.wmOnRetail = +((1179.44 / 1669.89) * 100).toFixed(1);

// --- B Chewy, same shape -------------------------------------------------
_adsOurRev['chewy|2026-08-11|2026-10-25'] = {
  rev: 106327.24, retail: 236282.76, priced: 119, unpricedSkus: 23, unpricedUnits: 916,
  from: '2026-08-17', to: '2026-10-26', why: null };
a = adsTacosFor('chewy', null, 15976.77, { from: '2026-08-11', to: '2026-10-25' },
                { from: '2026-08-11', to: '2026-10-25' });
out.chewy = { pct: a.pct == null ? null : +a.pct.toFixed(1), basis: a.basis,
              unpricedSkus: a.unpricedSkus, unpricedUnits: a.unpricedUnits };

// --- C Amazon is untouched ------------------------------------------------
a = adsTacosFor('amazon', null, 20312, { from: '2026-10-12', to: '2026-11-09' },
                { from: '2026-10-12', to: '2026-11-09' });
out.amazon = { pct: +a.pct.toFixed(2), basis: a.basis || null };

// --- D /!\ THE COVERAGE GUARD, on the real live spans ---------------------
_adsOurRev['walmart|2026-08-11|2026-11-09'] = {
  rev: 6178.5614, retail: 16579.07, priced: 30, unpricedSkus: 0, unpricedUnits: 0,
  from: '2026-08-15', to: '2026-11-07', why: null };
a = adsTacosFor('walmart', null, 1021.35, { from: '2026-08-11', to: '2026-11-09' },
                { from: '2026-11-04', to: '2026-11-09' });
out.thin = { pct: a.pct, why: a.why };
// What it WOULD have reported without the guard - the number this refuses.
out.thinWouldBe = +((1021.35 / 6178.5614) * 100).toFixed(1);

// Just inside the threshold: 80% of the window is accepted.
a = adsTacosFor('walmart', null, 500, { from: '2026-11-01', to: '2026-11-10' },
                { from: '2026-11-03', to: '2026-11-10' });
out.eighty = a.why == null || a.why.indexOf('covers only') < 0;

// --- E the refusals it keeps ----------------------------------------------
out.noRange   = adsTacosFor('walmart', null, 10, null, null).why;
out.selection = adsTacosFor('walmart', [{}], 10, FULL, FULLSPAN).why;
out.otherChan = adsTacosFor('shopify', null, 10, FULL, FULLSPAN).why;
out.notLoaded = adsTacosFor('walmart', null, 10,
                  { from: '1999-01-01', to: '1999-01-07' },
                  { from: '1999-01-01', to: '1999-01-07' }).why;
_adsOurRev['walmart|1999-02-01|1999-02-07'] = { pending: true };
let p = adsTacosFor('walmart', null, 10, { from: '1999-02-01', to: '1999-02-07' },
                    { from: '1999-02-01', to: '1999-02-07' });
out.pending = { pct: p.pct, pending: p.pending };
_adsOurRev['walmart|1999-03-01|1999-03-07'] = { rev: 0, why: null };
out.zeroRev = adsTacosFor('walmart', null, 10, { from: '1999-03-01', to: '1999-03-07' },
                          { from: '1999-03-01', to: '1999-03-07' }).why;

console.log(JSON.stringify(out));
"""

A = run_node(os.path.join(SP, "_v1208_a.js"),
             DRIVER.replace("__COVER__", line_of("const TACOS_MIN_COVERAGE"))
                   .replace("__DAYS__", fn_flat("_adsDayCount"))
                   # v12.22 - the narrowing validates the ad span with this.
                   .replace("__ISYMD__", fn_flat("_adsIsYmd"))
                   .replace("__OURREVKEY__", fn_flat("_adsOurRevKey"))
                   .replace("__OURREVFOR__", fn_flat("adsOurRevFor"))
                   .replace("__TACOS__", fn_flat("adsTacosFor")))

# ===========================================================================
print("\nA. Walmart, on the live week where both feeds cover the same ground")
# ===========================================================================
eq("A1  /!\\ v12.21 - $1,179.44 over $1,669.89 of SELL-THROUGH is 70.6%",
   A["wm"]["pct"], 70.6)
eq("A2  the denominator is our revenue, and says so", A["wm"]["basis"], "ourRev")
eq("A3  ...the channel's own sell-through, $1,669.89", A["wm"]["ns"], 1669.89)
# /!\ AND OUR REVENUE IS NOT LOST - it decides whether to spend, so it
# rides the result and reaches the tooltip.
ok("ourRev: r.rev" in fn_flat("adsTacosFor"),
   "A3b /!\\ ...with our revenue still carried on the result")
eq("A4  and the retail figure is carried for the tooltip", A["wm"]["retail"], 1669.89)
# /!\ THE WHOLE REASON FOR THE BASIS. Retail would have said 70.6% - a number
# that is not comparable with the Amazon tab's TACoS of the same name.
eq("A5  /!\\ retail would have reported 70.6% for the same dollars", A["wmOnRetail"], 70.6)
# /!\ The gap is the point, whichever way round the card reports it: the
# two bases are 2.6x apart, so a label meaning one on Amazon and the
# other here is the rule 3a defect v12.21 fixed.
ok(round((1179.44 / 651.9482) * 100, 1) > A["wm"]["pct"] * 2,
   "A6  /!\\ the two bases are more than 2x apart - which is why one label "
   "could not carry both")

print("\nB. Chewy, same basis, and the unpriced gap surfaced")
eq("B1  /!\\ Chewy on the same basis: $15,977 over $236,283 of sell-through",
   A["chewy"]["pct"], 6.8)
eq("B2  on our revenue", A["chewy"]["basis"], "ourRev")
# /!\ 23 SKUs sold in that window with no cost-per-each on record. Their sales
# are NOT in the denominator, so TACoS reads HIGH - and the card says so
# rather than quietly understating the sales side.
eq("B3  /!\\ the 23 unpriced SKUs are carried, not swallowed", A["chewy"]["unpricedSkus"], 23)
eq("B4  ...with their units", A["chewy"]["unpricedUnits"], 916)

print("\nC. Amazon is untouched")
eq("C1  still 17.21% on the live window", A["amazon"]["pct"], 17.21)
eq("C2  /!\\ and carries NO ourRev basis - its net sales already are ours",
   A["amazon"]["basis"], None)

# ===========================================================================
print("\nD. the coverage guard - a partial numerator over a full denominator")
# ===========================================================================
# v12.22 - /!\ PARTIAL COVERAGE NARROWS, IT NO LONGER REFUSES. The weekly
# rows are in hand, so both sides are taken over the span the ads ran.
# The fixture here carries no `weeks`, so there is nothing to narrow TO and
# it falls back to the window - which is why the counts it would need are
# asserted on the RESULT rather than in a refusal message.
ok(A["thin"]["pct"] is not None,
   "D1  /!\\ a 6-day ad feed in a 91-day window reports rather than refusing")
ok("narrowed, adDays, winDays," in fn_flat("adsTacosFor"),
   "D2  ...carrying how many days the ads ran and how many the window holds")
ok("tacos.adDays" in js and "tacos.winDays" in js,
   "D3  ...and both reach the card, where the old refusal used to say them")
# /!\ AND THE NARROWING IS WHAT KEEPS A PARTIAL NUMERATOR OFF A FULL
# DENOMINATOR - the defect this section has always been about.
TACF = fn_flat("adsTacosFor")
ok("w.w >= adSpan.from && w.w <= adSpan.to" in TACF,
   "D4  /!\\ the denominator is summed over the AD SPAN's own weeks")
ok("if (sum > 0) { denom = sum" in TACF,
   "D4b ...and only when those weeks actually hold sales")
# /!\ THE NUMBER THE OLD GUARD REFUSED TO PRINT, kept as the reading it is:
# 16.5% beside the 70.6% of A1 - same channel, same month, only the window
# differs, which is why narrowing rather than refusing is the fix.
eq("D5  /!\\ unnarrowed it would read 16.5%", A["thinWouldBe"], 16.5)
ok(A["thinWouldBe"] < A["wm"]["pct"],
   "D6  /!\\ far below the week both feeds cover - which is what narrowing "
   "corrects")
ok(A["eighty"], "D7  80% coverage is accepted - the threshold is not a trap")

print("\nE. every refusal it keeps")
ok("no date range" in (A["noRange"] or ""), "E1  a null window", A["noRange"])
ok("Organic sales" in (A["selection"] or ""),
   "E2  /!\\ a campaign selection still cannot narrow the sales side")
ok("no feed carrying them" in (A["otherChan"] or ""),
   "E3  a channel with no sales feed", A["otherChan"])
ok("not loaded yet" in (A["notLoaded"] or ""), "E4  a window nothing has fetched")
eq("E5  /!\\ a FETCH IN FLIGHT is not a refusal - it says so and repaints",
   [A["pending"]["pct"], A["pending"]["pending"]], [None, True])
ok("no denominator" in (A["zeroRev"] or ""), "E6  zero revenue", A["zeroRev"])

# ===========================================================================
print("\nF. the card, and the sources that caused this")
# ===========================================================================
SRC = const_obj("TACOS_SRC")
for c in ("amazon", "walmart", "chewy"):
    ok(c + ":" in SRC, "F1  %s has its own source list" % c)
# /!\ THE BUG JASON SAW: `amazon_ad_spend` chips under a card on the WALMART
# tab. The sources follow the channel now.
ok("amazon_ad_spend" not in SRC.split("walmart:")[1].split("\n")[0],
   "F2  /!\\ the Walmart entry cites no Amazon feed")
ok("walmart_sales_weekly" in SRC and "walmart_cost_per_each" in SRC,
   "F3  ...it cites the two the denominator is actually built from")
ok("chewy_catalog" in SRC,
   "F4  and Chewy cites the catalog its per-each price comes from")
ok("src: TACOS_SRC[channel]," in js, "F5  the card reads the registry")
ok("].concat(TACOS_SRC[channel] ? [{" in js,
   "F6  /!\\ and a channel absent from it gets no card, so the registry and "
   "the helper cannot disagree")
ok("channel === 'amazon' ? [{" not in js,
   "F7  /!\\ v12.07's Amazon-only gate is gone")

# The basis has to be visible on the card itself, not only the tooltip.
ok("' sell-through' : ' net sales'" in js,
   "F8  /!\\ the sub-line names the basis - sell-through on 1P, net sales on "
   "Amazon, which are the same measure under each channel's own word")
# v12.19 - the paragraph arguing the basis was right is gone (Jason). The
# tooltip states the ARITHMETIC instead, which is the thing only it can say.
ok("the channel\\u2019s own sell-through" in js,
   "F9  ...and the tooltip names the denominator in the channel's own word")
# /!\ v12.21 - an unpriced SKU no longer skews TACoS: the retail
# denominator does not use cost_per_each at all. It still skews the
# our-revenue clause the tooltip reports, so the count still rides the
# result - what changed is that it stopped caveating a number it cannot
# affect.
ok("unpricedSkus: r.unpricedSkus" in js,
   "F10 /!\\ the unpriced count still rides the result, for the figure it does skew")

print("\nG. the loader")
LOAD = fn_flat("adsLoadOurRev")
ok("_adsOurRev[k] = { pending: true };" in LOAD,
   "G1  /!\\ the entry is written BEFORE the await, so the repaint cannot loop")
ok("console.warn('ads our-revenue unavailable" in LOAD,
   "G2  a failure is reported, not swallowed")
ok("Sales could not be read: " in LOAD,
   "G3  ...and its reason reaches the card")
# /!\ The window reaches a SQL string, so its shape is checked.
ok("_adsIsYmd(range.from)" in LOAD and "_adsIsYmd(range.to)" in LOAD,
   "G4  /!\\ both dates are shape-checked before they reach a query")
# /!\ `exec_sql` wraps the query as `json_agg(t)`, so a column aliased `t`
# collides with the subquery alias and the whole row collapses to that one
# value. Cost a debugging round; pinned so it cannot come back.
ok(" t\n" not in LOAD and " t," not in LOAD.replace("row.units", ""),
   "G5  /!\\ no column is aliased `t` - exec_sql wraps as json_agg(t)")
# v12.15 - the queries group BY WEEK now and select week_start directly,
# so there is no min()/max() left to alias. G5 above still pins the
# guarantee: no column is aliased `t`.
ok("week_start" in LOAD, "G6  ...the week comes back on every row")
# Chewy's per-each price is NOT re-spelled in SQL.
ok("chewyCatalogPricePerEach" in LOAD,
   "G7  /!\\ Chewy's per-each price comes from the EXISTING helper, not a "
   "second spelling of cost / case_qty in SQL")
ok("loadChewyCatalog" in LOAD, "G8  ...and the catalog is loaded first")

ok("_adsOurRev[_adsOurRevKey(channel, win)] === undefined" in js,
   "G9  the fetch is guarded on the cache entry, like the break-even one")
ok("adsLoadOurRev(channel, { from: win.from, to: win.to }).then(() => {" in js,
   "G10 ...and repaints when it lands")

print("\nH. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "H1  both declare a version")
eq("H2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
