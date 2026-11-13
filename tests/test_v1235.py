#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.35 - the Units Sold chart bands by CATEGORY and measures OUR REVENUE.

Jason: "let me sort the graph by category and sub category (so i can see
category sales instead of specific product sales stacked). this is in
addition to what's there now. i should see the categories or sub-categories
stacked in the 'total' view when selected, or by channel as it exists
today." ... "let me see dollar sales here as well in addition to unit sales
(our sales, not retailer sales). can this be done?"

/!\ "OUR SALES, NOT RETAILER SALES" IS THE WHOLE DESIGN OF THE SECOND HALF.
On Amazon and Shopify the shopper pays US, so our revenue is net sales. On
Walmart and Chewy we are 1P: the retail the shopper paid is never ours, and
what reaches us is units x the wholesale per-each price. Measured on the
live database, Chewy's retail is $1,940,100 and our revenue on the same rows
is $854,899 - a 2.3x difference, which is how wrong the obvious column would
have been.
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
        print("  FAIL  %s%s" % (label, ("  got: %s" % extra) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


def fn_flat(name):
    i = js.index("function " + name + "(")
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def const_obj(name):
    i = js.index("const " + name + " = ")
    return js[i:js.index("\n};", i) + 3]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


SALES = fn_flat("updateSalesChart")
CHAN  = fn_flat("updateChannelChart")

print("\n" + "=" * 70)
print("  v12.35  rollup bands + our-revenue measure on Units Sold")
print("=" * 70)

# ===========================================================================
print("\nA. /!\\ THE BANDS - a category is a band, uncategorised is a band too")
# ===========================================================================
# 618 of 667 products carry a category_id; 49 do not, and every one of those
# 49 has sold nothing so far - which is exactly why silently dropping them
# would never have been noticed until one of them sold.
BAND = fn_flat("salesBandOf") + "\n" + fn_flat("salesCatRow") + "\n" \
     + fn_flat("salesSubcatAmbiguous") + "\n" + fn_flat("salesChartBands") + "\n" \
     + const_obj("SALES_ROLLUPS") + "\n" \
     + js[js.index("const SALES_BAND_NONE"):js.index("\n", js.index("const SALES_BAND_NONE")) + 1]

A = run_node(os.path.join(SP, "_v1235_a.js"), BAND + r"""
const allCategories = [
  { id: 1, category: 'Toys',       subcategory: 'Plush' },
  { id: 2, category: 'Toys',       subcategory: 'Kickers' },
  { id: 3, category: 'Blends',     subcategory: 'Jar' },
  { id: 4, category: 'Clamshells', subcategory: 'Jar' },   // /!\ same NAME
];
const allProducts = [
  { master_id: 'A', short_name: 'Plushy',  category_id: 1 },
  { master_id: 'B', short_name: 'Plushy2', category_id: 1 },
  { master_id: 'C', short_name: 'Kicker',  category_id: 2 },
  { master_id: 'D', short_name: 'BlendJar', category_id: 3 },
  { master_id: 'E', short_name: 'ClamJar',  category_id: 4 },
  { master_id: 'F', short_name: 'Orphan' },                 // no category_id
];
const mids = ['A','B','C','D','E','F'];
const out = {};
for (const r of ['product','category','subcategory']) {
  out[r] = salesChartBands(mids, r).map(b => ({ label: b.label, key: b.key, mids: b.mids }));
}
out.ambig = [...salesSubcatAmbiguous()];
out.tails = Object.keys(SALES_ROLLUPS).map(k => SALES_ROLLUPS[k].tail);
console.log(JSON.stringify(out));
""")

eq("A1  product gives one band per master_id, in the order handed over",
   [b["label"] for b in A["product"]], ["Plushy", "Plushy2", "Kicker", "BlendJar", "ClamJar", "Orphan"])
eq("A2  ...and each holds exactly its own product",
   [b["mids"] for b in A["product"]], [["A"], ["B"], ["C"], ["D"], ["E"], ["F"]])
eq("A3  /!\\ category collapses the products into their categories",
   [b["label"] for b in A["category"]], ["Toys", "Blends", "Clamshells", "(uncategorised)"])
eq("A4  ...and Toys carries BOTH plushies and the kicker",
   A["category"][0]["mids"], ["A", "B", "C"])
eq("A5  /!\\ UNCATEGORISED IS A BAND, not a drop - 49 products have no category",
   A["category"][3]["mids"], ["F"])
eq("A6  sub-category splits Toys back into two",
   [b["label"] for b in A["subcategory"]][:2], ["Plush", "Kickers"])
eq("A7  /!\\ an AMBIGUOUS sub-category name is qualified by its category",
   [b["label"] for b in A["subcategory"]][2:4], ["Blends · Jar", "Clamshells · Jar"])
eq("A8  ...and that is detected from the catalogue, not hardcoded", A["ambig"], ["Jar"])
ok(A["subcategory"][2]["key"] != A["subcategory"][3]["key"],
   "A9  /!\\ ...keyed on the PAIR, so two same-named sub-categories never merge")
eq("A10 the uncategorised band survives sub-category too",
   A["subcategory"][-1]["label"], "(uncategorised)")
eq("A11 /!\\ the Other band is named for what the bands ARE",
   A["tails"], ["SKUs", "categories", "sub-categories"])

# ===========================================================================
print("\nB. /!\\ OUR REVENUE - the money that reaches us, never the retail")
# ===========================================================================
REV = fn_flat("salesRevFx") + "\n" + fn_flat("salesRowVal") + "\n" \
    + fn_flat("salesFmtVal") + "\n" + fn_flat("salesMeasureUnit") + "\n" \
    + fn_flat("chewyCatalogPricePerEach") + "\n" + fn_flat("salesEnsureRevenue") + "\n" \
    + fn_flat("salesRevNote")

HARNESS = r"""
let pnlFxRate = 1.40, pnlFxGbp = 1.25, pnlFxEur = 1.10;   // CAD per USD; USD per unit
let _salesRev = null;
const console_warn = console.warn; console.warn = () => {};
async function fetchFxRate() {}
async function fetchEuFxRates() {}
async function loadChewyCatalog() {}
const allProducts = [
  { master_id: 'AMZ', case_qty: null },
  { master_id: 'WMT', case_qty: null },
  { master_id: 'CHW', case_qty: 12 },     // a CASE row - cost / 12
  { master_id: 'CHX', case_qty: null },   // a CASE row with NO case qty
  { master_id: 'SHP', case_qty: null },
  { master_id: 'GB',  case_qty: null },
];
const chewyCatalogByMaster = {
  CHW: { cost: 24, purchase_uom: 'CS' },
  CHX: { cost: 18, purchase_uom: 'CS' },
};
const salesData = {
  AMZ: [ { channel: 'amazon_us', region: 'US', week_start: '2026-01-05', units_ordered: 10 },
         { channel: 'amazon_ca', region: 'CA', week_start: '2026-01-05', units_ordered:  5 } ],
  WMT: [ { channel: 'walmart',   region: 'US', week_start: '2026-01-05', units_ordered: 100 } ],
  CHW: [ { channel: 'chewy',     region: 'US', week_start: '2026-01-05', units_ordered: 50, retailSales: 400 } ],
  CHX: [ { channel: 'chewy',     region: 'US', week_start: '2026-01-05', units_ordered:  7, retailSales:  60 } ],
  SHP: [ { channel: 'shopify',   region: 'US', week_start: '2026-01-05', units_ordered:  3, revenue: 42.5 } ],
  GB:  [ { channel: 'amazon_gb', region: 'GB', week_start: '2026-01-05', units_ordered:  2, revenue: 20 } ],
};
const _SE = [
  { master_id: 'AMZ', region: 'US', week_start: '2026-01-05', net_sales: 100, currency: 'USD' },
  { master_id: 'AMZ', region: 'US', week_start: '2026-01-05', net_sales:  50, currency: 'USD' },  // 2 SKUs, 1 mid
  { master_id: 'AMZ', region: 'CA', week_start: '2026-01-05', net_sales:  70, currency: 'CAD' },
];
const _WM = [ { master_id: 'WMT', cost_per_each: 2.5 } ];
async function sbPageAll(table, opts) {
  if (table === 'sku_economics') return _SE;
  if (table === 'walmart_cost_per_each') return _WM;
  throw new Error('unexpected table ' + table);
}
"""

B = run_node(os.path.join(SP, "_v1235_b.js"), REV + HARNESS + r"""
(async () => {
  const st = await salesEnsureRevenue();
  const pick = (m, i) => salesData[m][i].ourRevUsd;
  const out = {
    ok: !!st.ok,
    amzUs: pick('AMZ', 0),
    amzCa: pick('AMZ', 1),
    walmart: pick('WMT', 0),
    chewy: pick('CHW', 0),
    chewyGap: pick('CHX', 0),
    shopify: pick('SHP', 0),
    gb: pick('GB', 0),
    chewyMids: [...st.gap.chewyMids],
    chewyUnits: st.gap.chewyUnits,
    wmMids: [...st.gap.wmMids],
    amzMiss: st.gap.amzMiss,
    note: salesRevNote(),
    fx: [salesRevFx('CAD'), salesRevFx('GBP'), salesRevFx('EUR'), salesRevFx('USD'),
         salesRevFx('ZZZ'), salesRevFx(null), salesRevFx(undefined)],
    rowUnits: salesRowVal(salesData.WMT[0], 'units'),
    rowRev:   salesRowVal(salesData.WMT[0], 'revenue'),
    rowNull:  salesRowVal(salesData.CHX[0], 'revenue'),
    fmt: [salesFmtVal(1234.6, 'units'), salesFmtVal(1234.6, 'revenue'),
          salesFmtVal(null, 'revenue'), salesFmtVal(NaN, 'units')],
    unit: [salesMeasureUnit('units'), salesMeasureUnit('revenue')],
    cached: (await salesEnsureRevenue()) === st,
  };
  console.log(JSON.stringify(out));
})();
""")

ok(B["ok"], "B1  the pass completes")
eq("B2  /!\\ Amazon US sums the SEVERAL sku_economics rows that share a mid+week",
   B["amzUs"], 150)
eq("B3  /!\\ Amazon CA is CAD and is CONVERTED - 70 / 1.40", B["amzCa"], 50)
eq("B4  /!\\ Walmart is units x WHOLESALE, not the retail shopper price",
   B["walmart"], 250)
eq("B5  /!\\ Chewy is units x the CASE price per each - 50 x (24/12)",
   B["chewy"], 100)
eq("B6  /!\\ a Chewy SKU with no case qty is null, NEVER 0 - a zero would read "
   "as 'sold for nothing' and quietly deflate its band", B["chewyGap"], None)
eq("B7  Shopify is its own net sales, already USD", B["shopify"], 42.5)
eq("B8  an EU row converts at the GBP rate - 20 x 1.25", B["gb"], 25)
eq("B9  /!\\ the unpriced Chewy SKU is NAMED, not swallowed", B["chewyMids"], ["CHX"])
eq("B10 ...with its units counted", B["chewyUnits"], 7)
eq("B11 nothing is missing on Walmart here", B["wmMids"], [])
eq("B12 and no Amazon week went unmatched", B["amzMiss"], 0)
ok("Chewy 1 SKU unpriced (7 units)" in B["note"],
   "B13 /!\\ and the sub-line SAYS what it had to leave out", B["note"])
eq("B14 the three rates, and anything else is 1x",
   B["fx"], [1 / 1.40, 1.25, 1.10, 1, 1, 1, 1])
eq("B15 salesRowVal reads units", B["rowUnits"], 100)
eq("B16 ...and dollars", B["rowRev"], 250)
eq("B17 /!\\ a null basis sums as 0 rather than throwing", B["rowNull"], 0)
eq("B18 the formatter", B["fmt"], ["1,235", "$1,235", "$0", "0"])
eq("B19 the sub-line's own unit names the basis",
   B["unit"], [" units", " our revenue"])
ok(B["cached"], "B20 /!\\ fetched ONCE - the second call returns the same state")

# ===========================================================================
print("\nC. the refusals and the gap states")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1235_c.js"),
             fn_flat("salesRevNote") + r"""
let _salesRev = null;
const out = { never: salesRevNote() };
_salesRev = { pending: true };      out.pending = salesRevNote();
_salesRev = { err: 'boom' };        out.err = salesRevNote();
_salesRev = { ok: true, gap: { chewyMids: new Set(), chewyUnits: 0,
                               wmMids: new Set(), wmUnits: 0, amzMiss: 0,
                               otherChannels: new Set(), otherUnits: 0 } };
out.clean = salesRevNote();
_salesRev = { ok: true, gap: { chewyMids: new Set(['a','b']), chewyUnits: 1234,
                               wmMids: new Set(['c']), wmUnits: 9, amzMiss: 3,
                               otherChannels: new Set(['tiktok']), otherUnits: 11 } };
out.full = salesRevNote();
console.log(JSON.stringify(out));
""")
ok("not loaded" in C["never"], "C1  never asked says so, rather than printing a clean total")
ok("reading revenue" in C["pending"], "C2  in flight is a STATE, not an answer (v12.23)")
ok("boom" in C["err"], "C3  a failure carries its own message up")
eq("C4  /!\\ a clean read adds NOTHING - no noise on a complete window", C["clean"], "")
ok("Chewy 2 SKUs unpriced (1,234 units)" in C["full"]
   and "Walmart 1 SKU unpriced (9 units)" in C["full"]
   and "3 Amazon week(s)" in C["full"]
   and "tiktok" in C["full"],
   "C5  /!\\ every gap is named and counted", C["full"])

# ===========================================================================
print("\nD. the controls")
# ===========================================================================
ok("salesMeasureHtml(measure)" in SALES, "D1  the MEASURE control is injected")
ok(SALES.index("salesMeasureHtml(measure)") < SALES.index("pnlGrainStepperHtml("),
   "D2  /!\\ ...FIRST, because it says what the Y axis IS")
ok("salesRollupHtml(rollup, _rollupWhy)" in SALES, "D3  the ROLLUP control is injected")
ok("salesCurrentTab === 'channel'" in SALES and "its bands ARE the channels" in SALES,
   "D4  /!\\ ...and is DISABLED on By Channel, with the reason, not hidden")
RHTML = fn_flat("salesRollupHtml")
ok("disabled" in RHTML and "cursor:${dis ? 'not-allowed'" in RHTML,
   "D5  ...a disabled rollup button has its onclick STRIPPED, not just greyed")
ok("onclick=\"salesSetChartRollup" in RHTML and RHTML.count("${dis ? ' disabled'") == 1,
   "D6  one button renderer, not three copies")
MHTML = fn_flat("salesMeasureHtml")
ok("Our Revenue" in MHTML and "wholesale per-each price" in MHTML,
   "D7  /!\\ the basis is on the tooltip, in the app's own words")
ok("Not profit" in MHTML,
   "D8  /!\\ ...and it says what it is NOT - Amazon's fees come out afterwards")

ok(js.count("function salesRollupHtml") == 1 and js.count("function salesMeasureHtml") == 1,
   "D9  one renderer each")
_names = set(re.findall(r"pnl(?:GrainStepper|BandsStepper|FillToggle|ScaleToggle|CompareToggle)Html\('([A-Za-z]+)'", SALES))
eq("D10 /!\\ every shared control re-renders through the one function that "
   "rebuilds salesRawWeekData", sorted(_names), ["refreshSalesChart"])
REFRESH = fn_flat("refreshSalesChart")
ok("await updateSalesChart();" in REFRESH and "salesCurrentTab === 'channel'" in REFRESH,
   "D11 /!\\ ...which runs the Total build FIRST and the channel repaint after")

# ===========================================================================
print("\nE. what a dollar axis may not carry")
# ===========================================================================
ok("(measure === 'units') ? salesGoalDatasets(weeks, null, 'total') : []" in SALES,
   "E1  /!\\ unit GOALS are not drawn against a dollar axis")
ok("(measure === 'units')" in CHAN and "salesGoalDatasets(weeks, activeChannels" in CHAN,
   "E2  ...on the By Channel tab either")
GT = fn_flat("syncSalesGoalsToggle")
ok("salesChartMeasure() === 'revenue'" in GT and "b.disabled = true" in GT
   and "Switch Measure back to Units" in GT,
   "E3  /!\\ and the control says so rather than looking live (v10.19)")
ok("b.disabled = false" in GT,
   "E4  ...and is re-enabled coming back, not left stuck")
ok("const doAttr = !!doAttrReq && measure !== 'revenue';" in SALES,
   "E5  /!\\ BUNDLE ATTRIBUTION IS A UNITS IDEA - multiplying a bundle's "
   "DOLLARS by the component qty would invent revenue nobody was paid")
ok("bundle attribution is not applied to revenue" in SALES,
   "E6  ...and the sub-line says so when the box is ticked")

# ===========================================================================
print("\nF. /!\\ THE LOCALS - declared before they are read")
# ===========================================================================
# v12.25's lesson, applied to this release's own additions. The orphan census
# in test_v1225 proves a name is declared SOMEWHERE in the file; these pin
# each new local inside updateSalesChart, before its first read. `measure`
# and `rollup` are both also locals of OTHER functions, which is exactly the
# case that census cannot see.
#
# /!\ COMMENTS STRIPPED FIRST. The block explaining why `measure` is resolved
# at the top sits ABOVE the declaration and mentions it by name, so the raw
# text reports a read before the declaration that does not exist in the code
# (the v12.15 A7 trap, same shape).
SALES_NC = re.sub(r"(?m)//.*$", " ", re.sub(r"/\*[\s\S]*?\*/", " ", SALES))
for name, decl in (("measure", "const measure = salesChartMeasure();"),
                   ("rollup",  "const rollup = salesChartRollup();"),
                   ("bands",   "const bands = salesChartBands(chartMids, rollup);"),
                   ("rolledUp", "const rolledUp = rollup !== 'product';"),
                   ("_bandsBite", "let _bandsBite = false;"),
                   ("doAttrReq", "const doAttrReq = document.getElementById('salesBundleAttr')?.checked;")):
    here = decl in SALES_NC
    first = SALES_NC.index(decl) if here else -1
    reads = [m.start() for m in re.finditer(r"(?<![.\w$])" + re.escape(name) + r"(?![\w$])", SALES_NC)]
    ok(here and reads and first <= min(reads),
       "F-%s  declared in updateSalesChart, before its first read" % name)

ok("const measure = salesChartMeasure();" in CHAN,
   "F-chan  /!\\ and By Channel reads the SAME control, not a second one")
ok("salesRowVal(" not in CHAN,
   "F-raw   /!\\ ...without re-deriving the value: salesRawWeekData already "
   "holds the measure, so the two tabs cannot disagree")

# ===========================================================================
print("\nG. the two tabs print the same unit")
# ===========================================================================
ok("salesFmtVal(periodTotal, measure)" in SALES, "G1  Total's headline carries the measure")
ok("salesFmtVal(chanTotal, measure)" in CHAN,    "G2  ...and By Channel's")
ok(SALES.count("salesFmtVal(ctx.parsed.y, measure)") == 1
   and CHAN.count("salesFmtVal(ctx.parsed.y, measure)") == 1,
   "G3  both tooltips, through the one formatter")
ok(SALES.count("callback: v => salesFmtVal(v, measure)") == 1
   and CHAN.count("callback: v => salesFmtVal(v, measure)") == 1,
   "G4  both Y axes too - a dollar axis reads in dollars")
ok("salesRevNote()" in CHAN, "G5  and By Channel names the same gaps")

# ===========================================================================
print("\nH. /!\\ `revenue` STOPPED MEANING TWO THINGS")
# ===========================================================================
# Chewy stamped `revenue` from merch_sales, which is Chewy's cash register -
# retail dollars we never see. Shopify's and EU Amazon's are OUR money. One
# field name, two opposite bases, is rule 3a on the one number this release
# adds.
ok("retailSales:    Number(r.merch_sales) || 0," in js,
   "H1  Chewy's retail figure is named retailSales")
ok("revenue:        Number(r.merch_sales)" not in js,
   "H2  /!\\ ...and no longer `revenue`")
ok("revenue:       Number(r.net_sales) || 0," in js,
   "H3  Shopify's OUR-money figure keeps the name")
ok("'master_id, day, units_sold, net_sales'" in js,
   "H4  ...and rides the select that was already being made")
ok("'master_id, week_start, units_ordered, channel, region, revenue'" in js,
   "H5  so does the EU dollar column")

# ===========================================================================
print("\nI. on demand, and paged deterministically")
# ===========================================================================
ENS = fn_flat("salesEnsureRevenue")
ok("if (_salesRev && (_salesRev.pending || _salesRev.ok)) return _salesRev;" in ENS,
   "I1  /!\\ fetched once per session - the page already loads ~43k rows and "
   "'it takes SO LONG whenever i refresh' is a standing complaint")
ok("order: { column: 'id', ascending: true }" in ENS,
   "I2  /!\\ 41k rows is 41 pages, and an unordered paged select can repeat "
   "or skip a row across a boundary - `id` is the unique PK")
ok("chewyCatalogPricePerEach(" in ENS,
   "I3  /!\\ Chewy's per-each price is the EXISTING helper, never re-spelled")
ok(js.count("function chewyCatalogPricePerEach") == 1, "I4  ...of which there is one")
ok("await salesEnsureRevenue();" in SALES
   and SALES.index("await salesEnsureRevenue();") < SALES.index("salesRowVal(r, measure)"),
   "I5  /!\\ AWAITED BEFORE THE FIRST READER. The measure is persisted, so a "
   "reload can land on Our Revenue with nothing fetched (the v12.23 defect)")
ok("r.ourRevUsd = null;" in ENS,
   "I6  /!\\ a row with no price basis is null, never 0 (v11.16)")

# ===========================================================================
print("\nJ. /!\\ THE WHOLE PAGE READS IN ONE MEASURE")
# ===========================================================================
# A dollar chart under a scorecard reading `Units Sold - 30d  454,997` is
# half a feature: the page's headline and the chart beneath it would say two
# different things at a glance.
TBL = fn_flat("renderSalesTbl")
ok("const measure = salesChartMeasure();" in TBL,
   "J1  the table reads the chart's own control")
ok("sumUnits(rows, from, to, channels, measure)" in TBL
   and "sumUnits(rows, null, null, channels, measure)" in TBL,
   "J2  both columns go through the one aggregator")
SUM = fn_flat("sumUnits")
ok("function sumUnits(rows, fromDate, toDate, channels, measure)" in SUM
   and "salesRowVal(r, measure)" in SUM,
   "J3  /!\\ ONE AGGREGATOR - no sumRevenue twin to disagree with it")
ok("r.units_ordered || 0" not in SUM,
   "J4  ...and the old inline sum is GONE, not left standing beside it")
ok(js.count("function sumUnits") == 1, "J5  of which there is exactly one")
ok("${_mspec.card}" in TBL and "salesFmtVal(totalPeriod, measure)" in TBL
   and "salesFmtVal(totalAlltime, measure)" in TBL,
   "J6  both scorecards carry the measure's own name and format")
ok("srcChip(_mspec.src)" in TBL,
   "J7  /!\\ ...and its own PROVENANCE - the chips cannot name the units "
   "feeds under a number that came from sku_economics")
ok("const _msuf = (measure === 'revenue') ? ' $' : '';" in TBL
   and "salesColAlltime" in TBL and 'id="salesColAlltime"' in s,
   "J8  /!\\ both column headers say which measure they hold")
ok("salesFmtVal(periodUnits, measure)" in TBL and "salesFmtVal(alltimeUnits, measure)" in TBL,
   "J9  ...and so do the cells")
ok("const doAttr = !!doAttrReq && measure !== 'revenue';" in TBL,
   "J10 bundle attribution is units-only here too, for the same reason")

LOADER = fn_flat("loadSalesAnalytics")
ok("if (salesChartMeasure() === 'revenue') {" in LOADER
   and LOADER.index("salesEnsureRevenue") < LOADER.index("renderSalesTbl();"),
   "J11 /!\\ a reload that lands on Our Revenue fetches BEFORE the first "
   "paint, so the table does not draw a column of dashes and then jump")

SETTER = fn_flat("salesSetChartMeasure")
ok("renderSalesTbl();" in SETTER and "refreshSalesChart();" in SETTER,
   "J12 switching the measure repaints the table as well as the chart")

# ===========================================================================
print("\nK. the export cannot mislabel what it carries")
# ===========================================================================
# /!\ `} else if (tab === 'sales') {` appears TWICE - the first is a row
# count in another function. Anchored on the export's own local.
_i = js.index("const salesHideBundlesExp")
EXP = js[_i:js.index("smarterpaw-", _i) + 400]
ok("const salesExpMeasure = salesChartMeasure();" in EXP,
   "K1  the export reads the same control")
ok("sumUnits(rows, from, to, null, salesExpMeasure)" in EXP,
   "K2  ...and the Everything branch totals in it")
ok("'Our_Revenue_USD' : 'Units'" in EXP and "${salesExpCol}_${periodLabel}" in EXP,
   "K3  /!\\ the HEADER names the measure - `filtered` writes the visible "
   "rows straight out, so dollars under `Units_30d` was one keystroke away")
ok("'our-revenue' : 'units-sold'" in EXP, "K4  ...and so does the filename")
ok("Master_ID,Brand,Category,Subcategory,Title" in EXP,
   "K5  the two band columns ship too - a chart cut by category should "
   "export that way")
ok("salesCatRow(p)" in EXP,
   "K6  /!\\ through the same resolver the bands use, not a second lookup")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
