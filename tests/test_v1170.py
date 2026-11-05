#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.70 - the Amazon Fees tab: per SKU and at the account level.

Jason: "i need a new section here around amazon fees - a new tab. i need to
reduce fees by 5% next year, so i need to analyze all of the amazon costs per
sku and at the account level."
...and then: "Is there a cost area in amazon we aren't capturing?"

  * A  ONE fee registry. FEE_FIELDS was declared twice and named nothing; both
       sites read the registry now, and the derived list is BYTE-IDENTICAL to
       the one that was spelled there - which is the only form in which "no
       existing number moved" is checkable.
  * B  the real amzFeeAgg: totals, per product, the avoidable bucket, the
       percentages derived from sums, and the costs OUTSIDE the total.
  * C  /!\ the ordering defect a browser caught: the excluded totals were
       seeded AFTER the loop that fills them, so the one thing the tab exists
       to say rendered as nothing.
  * D  the real CSV: every line, the excluded ones, per product AND in total.
  * E  static: the tab is registered everywhere a tab has to be registered.
"""
import io, os, re, sys, json, subprocess

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


def _bal(i):
    k, n = i, len(js)
    depth, started, prev = 0, False, ""
    while k < n:
        c = js[k]
        if c == "/" and k + 1 < n and js[k + 1] == "/":
            while k < n and js[k] != "\n":
                k += 1
            continue
        if c == "/" and k + 1 < n and js[k + 1] == "*":
            k = js.index("*/", k) + 2
            continue
        # /!\ A REGEX LITERAL CAN CONTAIN A QUOTE. downloadAmazonFeesCSV's
        # escaper is /[",\n]/ - read as a string start, the matcher swallows
        # the rest of the function and reports "unbalanced" 40k chars later.
        if c == "/" and prev in "(,=:[!&|?{};+-*%~^<>":
            k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == "[":
                    while k < n and js[k] != "]":
                        k += 2 if js[k] == "\\" else 1
                if js[k] == "/":
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = "x"
            continue
        if c in "\"'`":
            q = c; k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = "x"
            continue
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise SystemExit("unbalanced at %d" % i)


def fn(name):
    i = js.index("function " + name + "(")
    while i > 0 and js[i - 1] != "\n":
        i -= 1
    return js[i:js.index("{", js.index("function " + name + "("))] \
         + _bal(js.index("{", js.index("function " + name + "(")))


def const_arr(name):
    i = js.index("const %s = [" % name)
    j, d = js.index("[", i), 0
    k = j
    while k < len(js):
        if js[k] == "[":
            d += 1
        elif js[k] == "]":
            d -= 1
            if d == 0:
                return "const %s = %s;" % (name, js[j:k + 1])
        k += 1
    raise SystemExit("unbalanced %s" % name)


def const_obj(name):
    i = js.index("const %s = {" % name)
    return "const %s = %s;" % (name, _bal(js.index("{", i)))


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v11.70  the Amazon Fees tab")
print("=" * 68)

NC = nocomment(js)

# The list that WAS spelled at both call sites, pinned here so "nothing moved"
# is a measurement rather than a claim.
RETIRED = ['fba_fulfillment_fee_total', 'fba_storage_fee_total', 'inbound_placement_fee_total',
           'inbound_transport_fee_total', 'low_inventory_fee_total', 'aged_inventory_fee_total',
           'removal_fee_total', 'storage_util_surcharge', 'referral_fee_total',
           'referral_fee_refunds_total', 'refund_admin_fee_total']


# ===========================================================================
print("\nA. ONE registry, and it reproduces the list it replaced")
# ===========================================================================
A = run_node(os.path.join(SP, "_v1170_a.js"),
    const_arr("AMZ_FEE_LINES") + "\n" + const_arr("AMZ_FEE_OUTSIDE") + "\n"
    + const_obj("AMZ_FEE_LEVER") + "\n"
    + "console.log(JSON.stringify({ keys: AMZ_FEE_LINES.map(l => l.k),\n"
    + "  levers: AMZ_FEE_LINES.map(l => l.lever),\n"
    + "  labels: AMZ_FEE_LINES.map(l => l.label),\n"
    + "  outside: AMZ_FEE_OUTSIDE.map(o => o.k),\n"
    + "  leverKeys: Object.keys(AMZ_FEE_LEVER) }));\n")

# /!\ SET equality, not order: the two retired lists were summed, so order was
# never a guarantee - but membership was, and a dropped key silently lowers
# every fee total in the app.
eq("A1  /!\\ the derived list is exactly the retired one",
   sorted(A["keys"]), sorted(RETIRED))
eq("A1b and nothing was added to it", len(A["keys"]), len(RETIRED))
eq("A2  both old call sites read the registry",
   NC.count("const FEE_FIELDS = AMZ_FEE_LINES.map(l => l.k);"), 2)
eq("A2b and no literal fee list survives", NC.count("'fba_fulfillment_fee_total','fba_storage"), 0)
# Every line is classified, and only into the three declared buckets.
ok(all(l in A["leverKeys"] for l in A["levers"]),
   "A3  every fee declares a lever, and only a declared one", A["levers"])
eq("A3b three buckets, no more", sorted(A["leverKeys"]), ["avoidable", "fixed", "rate"])
# /!\ The classification is the tab's reason to exist: ranked by SIZE the top
# three include Referral, which is a percentage of price nobody can move.
eq("A4  /!\\ referral is FIXED, so the tab cannot send you chasing it",
   A["levers"][A["keys"].index("referral_fee_total")], "fixed")
eq("A4b and FBA fulfilment is a RATE, which moves when the packaging does",
   A["levers"][A["keys"].index("fba_fulfillment_fee_total")], "rate")
for k in ("aged_inventory_fee_total", "low_inventory_fee_total",
          "inbound_placement_fee_total", "removal_fee_total", "storage_util_surcharge"):
    eq("A4c %s is avoidable" % k, A["levers"][A["keys"].index(k)], "avoidable")
# /!\ AD SPEND IS NOT A FEE HERE, because the scorecard this tab decomposes
# excludes it. Folding it in would make the tab disagree with the card above.
ok("sponsored_products_total" not in A["keys"],
   "A5  /!\\ ad spend is NOT in the fee total - the card excludes it too")
eq("A6  the excluded costs are declared, not discovered",
   A["outside"], ["awd_transport_fee_total", "awd_storage_fee_total", "fba_reimbursement_total"])


# ===========================================================================
print("\nB. the real amzFeeAgg, driven")
# ===========================================================================
AGG = run_node(os.path.join(SP, "_v1170_b.js"),
    const_arr("AMZ_FEE_LINES") + "\n" + const_arr("AMZ_FEE_OUTSIDE") + "\n" + r"""
let pnlCurrencyMode = 'usd', pnlFxRate = 1.35, pnlFxGbp = 1.25, pnlFxEur = 1.1;
const allProducts = [{ master_id: 'M1', short_name: 'Catnip Spray' }];
// M4 is the CAD row - it has to be VISIBLE for the conversion to be exercised.
let VIS = ['M1', 'M2', 'M3', 'M4'];
let pnlVisibleMids = VIS;
const mk = (mid, wk, o) => Object.assign({ master_id: mid, week_start: wk, region: 'US',
  currency: 'USD', net_sales: 0, net_units_sold: 0 }, o);
const ROWS = [
  mk('M1', '2026-07-06', { net_sales: 10000, net_units_sold: 1000, fba_fulfillment_fee_total: 2900,
      referral_fee_total: 1500, low_inventory_fee_total: 200, inbound_placement_fee_total: 150,
      awd_transport_fee_total: 12, fba_reimbursement_total: -80 }),
  mk('M2', '2026-07-06', { net_sales: 2000, net_units_sold: 400, fba_fulfillment_fee_total: 1120,
      referral_fee_total: 300, aged_inventory_fee_total: 450, removal_fee_total: 60,
      storage_util_surcharge: 15, fba_storage_fee_total: 90, awd_storage_fee_total: 7 }),
  mk('M3', '2026-07-13', { net_sales: 500, net_units_sold: 50, fba_fulfillment_fee_total: 200,
      referral_fee_total: 75, aged_inventory_fee_total: 600, refund_admin_fee_total: 5 }),
  // Outside the window, and a different region: neither may be counted.
  mk('M1', '2026-06-01', { net_sales: 9999, fba_fulfillment_fee_total: 9999 }),
  Object.assign(mk('M1', '2026-07-06', { fba_fulfillment_fee_total: 777 }), { region: 'CA' }),
  // CAD, to exercise the shared conversion.
  Object.assign(mk('M4', '2026-07-06', { net_sales: 135, fba_fulfillment_fee_total: 135 }),
                { currency: 'CAD' }),
];
let WIN = { from: '2026-07-01', to: '2026-07-31' };
const getPnlDateRange = () => WIN;
const getPnlSource = () => ({ rows: ROWS, regionMatches: (r) => r === 'US' });
""" + fn("pnlRowFx") + "\n" + fn("amzFeeAgg") + r"""
const out = {};
let A = amzFeeAgg();
out.fees = Math.round(A.tot.fees * 100) / 100;
out.netSales = Math.round(A.tot.netSales * 100) / 100;
out.avoidable = Math.round(A.tot.avoidable * 100) / 100;
out.feePct = Math.round(A.tot.feePct * 100) / 100;
out.fbaPerU = Math.round(A.tot.fbaPerU * 1000) / 1000;
out.prods = A.prods.map(p => [p.mid, Math.round(p.fees * 100) / 100,
                              Math.round(p.avoidable * 100) / 100]).sort();
out.outsideTot = AMZ_FEE_OUTSIDE.map(o => Math.round((A.tot[o.k] || 0) * 100) / 100);
out.outsideM1 = AMZ_FEE_OUTSIDE.map(o => Math.round((A.prods.find(p => p.mid === 'M1')[o.k] || 0) * 100) / 100);
out.name = A.prods.find(p => p.mid === 'M1').name;
out.unmatchedName = A.prods.find(p => p.mid === 'M2').name;
// A per-product percentage comes from THAT product's own sales.
const m3 = A.prods.find(p => p.mid === 'M3');
out.m3FeePct = Math.round(m3.feePct * 10) / 10;
// /!\ The visible-products filter, and the fallback when nothing is loaded.
pnlVisibleMids = ['M2'];
out.scopedFees = Math.round(amzFeeAgg().tot.fees * 100) / 100;
pnlVisibleMids = [];
out.fallbackProds = amzFeeAgg().prods.length;
pnlVisibleMids = VIS;
// An empty window yields zeroes, not NaN.
WIN = { from: '2030-01-01', to: '2030-01-31' };
const E = amzFeeAgg();
out.emptyFees = E.tot.fees;
out.emptyPct = E.tot.feePct;
out.emptyProds = E.prods.length;
console.log(JSON.stringify(out));
""")

# 4750 + 2035 + 880 = 7665, plus the CAD row at 135/1.35 = 100.
eq("B1  fees total over the window", AGG["fees"], 7765.0)
eq("B1b net sales too (the CAD row converted)", AGG["netSales"], 12600.0)
ok("9999" not in str(AGG["fees"]), "B2  a row outside the window is not counted")
eq("B2b and a row from another region is not either",
   AGG["prods"], [["M1", 4750.0, 350.0], ["M2", 2035.0, 525.0],
                  ["M3", 880.0, 600.0], ["M4", 100.0, 0]])
# 200 + 150 + 450 + 60 + 15 + 600
eq("B3  /!\\ the avoidable bucket is the five avoidable lines", AGG["avoidable"], 1475.0)
# /!\ Derived from the SUMS: 7765/12600, never an average of per-product rates.
eq("B4  /!\\ the fee percentage comes from the sums", AGG["feePct"], 61.63)
# 4,320 of FBA over 1,450 units. The CAD row adds fee but no units, which is
# exactly why this is derived from the sums rather than averaged over SKUs.
eq("B4b and so does FBA per unit", AGG["fbaPerU"], 2.979)
eq("B5  a product's own percentage uses its OWN sales", AGG["m3FeePct"], 176.0)
# The costs the total excludes, in total AND per product.
eq("B6  /!\\ the excluded costs are totalled", AGG["outsideTot"], [12.0, 7.0, -80.0])
eq("B6b and carried per product", AGG["outsideM1"], [12.0, 0, -80.0])
eq("B7  a matched product is named from the catalog", AGG["name"], "Catnip Spray")
eq("B7b an unmatched one falls back to its id, never blank", AGG["unmatchedName"], "M2")
eq("B8  the visible-product filter scopes it", AGG["scopedFees"], 2035.0)
# /!\ Without the fallback, opening Fees before Summary reports $0 and reads
# as "no fees" rather than as "nothing loaded".
eq("B8b /!\\ and an EMPTY visible list falls back to every product",
   AGG["fallbackProds"], 4)
eq("B9  an empty window is zero, not NaN", AGG["emptyFees"], 0)
eq("B9b and a percentage with no denominator is null", AGG["emptyPct"], None)
eq("B9c with no products", AGG["emptyProds"], 0)


# ===========================================================================
print("\nC. /!\\ the ordering defect, reproduced")
# ===========================================================================
# A browser run caught this: the excluded totals were seeded AFTER the loop
# that accumulates into them, so every one went NaN on the first row and was
# then wiped to zero - and the tab's whole answer to "what are we not
# capturing" rendered as nothing at all.
C = run_node(os.path.join(SP, "_v1170_c.js"), r"""
const OUT = [{ k: 'awd' }, { k: 'reimb' }];
const ROWS = [{ awd: 12, reimb: -80 }, { awd: 3, reimb: -20 }];
const run = (seedFirst) => {
  const tot = {};
  if (seedFirst) for (const o of OUT) tot[o.k] = 0;
  for (const row of ROWS) for (const o of OUT) tot[o.k] += (row[o.k] || 0);
  if (!seedFirst) for (const o of OUT) tot[o.k] = 0;
  return OUT.map(o => (Number.isNaN(tot[o.k]) ? 'NaN' : tot[o.k]));
};
console.log(JSON.stringify({ before: run(false), after: run(true) }));
""")
eq("C1  /!\\ seeded after the loop: every excluded total is wiped to zero",
   C["before"], [0, 0])
eq("C2  seeded before it: the real amounts", C["after"], [15, -100])
# And the shipped order is the right one.
agg = fn("amzFeeAgg")
ok(agg.index("for (const o of AMZ_FEE_OUTSIDE) tot[o.k] = 0;")
   < agg.index("for (const o of AMZ_FEE_OUTSIDE) { const v ="),
   "C3  the shipped code seeds BEFORE it accumulates")


# ===========================================================================
print("\nD. the CSV carries every line")
# ===========================================================================
csv = fn("downloadAmazonFeesCSV")
ok("AMZ_FEE_LINES.map(l => l.label)" in csv,
   "D1  every fee line is its own column")
eq("D1b including the excluded ones, labelled as such",
   csv.count("AMZ_FEE_OUTSIDE.map"), 3)
ok("'(outside total)'" in csv or "(outside total)" in csv,
   "D1c and the header says they are outside the total")
ok("TOTAL" in csv, "D2  with a TOTAL row")
ok("pnlRegion" in csv and "A.from" in csv and "A.to" in csv,
   "D3  and a filename that states the region and window")
# v11.57's rule, one tab over: the screen is for scanning, the export for work.
ok("A.prods" in csv and "amzFeeAgg()" in csv,
   "D4  the export re-reads the aggregate rather than scraping the table")


# ===========================================================================
print("\nE. the tab is registered everywhere a tab has to be")
# ===========================================================================
ok('id="pnl-amzn-tab-fees"' in s, "E1  the strip has the button")
ok('id="pnl-amzn-fees-wrap"' in s, "E1b and the page has its wrap")
ok("'fees'" in NC[NC.index("function switchPnlAmazonView("):][:2000],
   "E2  the switcher accepts it")
ok("['pnl-amzn-tab-fees',       'fees']" in js,
   "E2b and the shared sub-tab strip knows it (v10.17)")
ok("if (feeWrap)  feeWrap.style.display" in js, "E2c the wrap is shown and hidden")
ok("if (view === 'fees') renderAmazonFees();" in js, "E2d and the renderer runs on entry")
# /!\ v10.3: an unmapped sub-view search leaves the top bar reading "No search
# on this page" while a live box sits below it.
ok("pnl_amazon_fees: { id: 'amzfee-search' }" in js,
   "E3  /!\\ the global search bar is mapped in the same commit")
ok("if (av === 'fees')      return 'pnl_amazon_fees';" in js,
   "E3b and the key resolver returns it")
# Rule #2: one concept, one glyph. The Fees tab must not borrow one.
strip_glyphs = re.findall(r'class="subtab[^"]*"[^>]*>\s*(\S)', s)
coin = chr(0x1FA99)
eq("E4  the tab's glyph is used by exactly one sub-tab", strip_glyphs.count(coin[0]), 1)
for f in ("amzFeeAgg", "renderAmazonFees", "downloadAmazonFeesCSV", "pnlRowFx"):
    eq("E5  %s defined once" % f, NC.count("function %s(" % f), 1)
# The chart's own copy of the conversion converged on the shared one.
eq("E6  one spelling of the multi-currency conversion",
   NC.count("pnlCurrencyMode === 'usd') ? (1 / pnlFxRate)\n"), 1)

r = subprocess.run(["node", "--check", os.path.join(SP, "_v1170_b.js")],
                   capture_output=True, text=True)
ok(r.returncode == 0, "E8  the sliced source parses", r.stderr[-300:])

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
