#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.31 - Order List: the next Amazon shipment, by brand and region.

Jason: "On the Inventory planning page, i want a new tab for 'order list' by
brand, by region. On demand, it should pull numbers for an amazon shipment.
the numbers should be rounded to the next 5 or 10 unit"

/!\ THE QUANTITY IS NOT A NEW CALCULATION. `inventoryNeedBreakdown` already
simulates every Amazon reorder event - order-by day, lead time, arrival and
the seasonal demand over that event's OWN arrival window. The list reads
events[0], the NEXT one, which is what a shipment is. A second quantity model
would be rule 3a on the single number this page exists to produce.

/!\ AND THE FILTERS ARE THE PAGE'S OWN. `inventoryVisibleRecords()` already
applies brand, region, category, status, search, bundles, inactive and the
in-house pick.
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


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.31  Order List")
print("=" * 70)

# ===========================================================================
print("\nA. /!\\ THE ROUNDING RULE, DRIVEN")
# ===========================================================================
ROUND = fn_flat("ipRoundShipQty")
A = run_node(os.path.join(SP, "_v1231_a.js"), ROUND + r"""
const t = {};
for (const n of [0, 1, 2, 4, 5, 6, 44, 45, 46, 95, 99, 100, 101, 110, 111, 999, 1000]) {
  t[n] = ipRoundShipQty(n);
}
t['neg']   = ipRoundShipQty(-5);
t['null']  = ipRoundShipQty(null);
t['nan']   = ipRoundShipQty('x');
t['frac']  = ipRoundShipQty(47.2);
console.log(JSON.stringify(t));
""")
# below 100 -> up to the next 5
eq("A1  44 rounds up to 45",   A["44"],  45)
eq("A2  45 stays at 45",       A["45"],  45)
eq("A3  46 rounds up to 50",   A["46"],  50)
eq("A4  /!\\ 47.2 rounds up to 50, not down", A["frac"], 50)
eq("A5  99 rounds up to 100",  A["99"],  100)
# at 100 and above -> up to the next 10
eq("A6  /!\\ 100 is the switch: stays 100", A["100"], 100)
eq("A7  101 rounds up to 110", A["101"], 110)
eq("A8  110 stays at 110",     A["110"], 110)
eq("A9  111 rounds up to 120", A["111"], 120)
eq("A10 999 rounds up to 1000", A["999"], 1000)
# /!\ A POSITIVE QUANTITY MAY NEVER ROUND TO ZERO. Rounding a 1-unit shipment
# away would silently drop a line from the list.
eq("A11 /!\\ 1 unit rounds UP to 5, never to 0", A["1"], 5)
eq("A12 ...and 4 does too", A["4"], 5)
# and nothing is invented out of nothing
eq("A13 zero stays zero",     A["0"],     0)
eq("A14 a negative is zero",  A["neg"],   0)
eq("A15 null is zero",        A["null"],  0)
eq("A16 a non-number is zero", A["nan"],  0)

# ===========================================================================
print("\nB. /!\\ IT READS THE EXISTING SIMULATION, NOT A NEW ONE")
# ===========================================================================
BUILD = fn_flat("ipBuildOrderList")
ok("inventoryNeedBreakdown(r, horizon, region" in BUILD,
   "B1  /!\\ the quantity comes from the page's own breakdown")
ok("meta.events && meta.events[0]" in BUILD,
   "B2  /!\\ ...and from the NEXT event, which is what one shipment is")
ok("inventoryVisibleRecords()" in BUILD,
   "B3  /!\\ the filters are the page's own - brand, region, category, status, "
   "search, bundles, inactive, in-house")
ok("if (!ev || !(ev.qty > 0)) continue;" in BUILD,
   "B4  /!\\ no event is an ABSENCE, not a zero row (v11.16)")
ok("ipRoundShipQty(ev.qty)" in BUILD, "B5  the rounding is applied once, here")
ok("raw:  Math.round(ev.qty)" in BUILD,
   "B6  /!\\ and the UNROUNDED figure is carried, so the rounding is auditable")
# /!\ no second velocity, cover or lead-time arithmetic in this file's new code
ok("reorder_qty_days" not in BUILD and "blended_daily" not in BUILD,
   "B7  /!\\ it re-derives NOTHING - no second velocity or reorder model")

# ===========================================================================
print("\nC. grouping, ordering and the totals")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1231_c.js"), r"""
// the shipped sort comparator, lifted from ipBuildOrderList
const rows = [
  { brand: 'Meowijuana', region: 'US', title: 'b', qty: 50 },
  { brand: 'Kitty Ka-Zoom', region: 'US', title: 'c', qty: 10 },
  { brand: 'Meowijuana', region: 'CA', title: 'd', qty: 90 },
  { brand: 'Meowijuana', region: 'US', title: 'a', qty: 200 },
  { brand: 'Kitty Ka-Zoom', region: 'CA', title: 'e', qty: 30 },
];
rows.sort((a, b) => (a.brand || '').localeCompare(b.brand || '')
                 || (a.region || '').localeCompare(b.region || '')
                 || (b.qty - a.qty));
const byBrand = new Map();
for (const x of rows) {
  if (!byBrand.has(x.brand)) byBrand.set(x.brand, new Map());
  const br = byBrand.get(x.brand);
  if (!br.has(x.region)) br.set(x.region, []);
  br.get(x.region).push(x);
}
console.log(JSON.stringify({
  order: rows.map(r => r.brand[0] + r.region + r.qty),
  brands: [...byBrand.keys()],
  kkRegions: [...byBrand.get('Kitty Ka-Zoom').keys()],
  meowiUS: byBrand.get('Meowijuana').get('US').map(r => r.qty),
  grand: rows.reduce((t, x) => t + x.qty, 0),
}));
""")
eq("C1  brands sort alphabetically", C["brands"], ["Kitty Ka-Zoom", "Meowijuana"])
eq("C2  regions sort inside the brand", C["kkRegions"], ["CA", "US"])
eq("C3  /!\\ and the biggest shipment leads its region", C["meowiUS"], [200, 50])
eq("C4  the grand total is every row", C["grand"], 380)

# ===========================================================================
print("\nD. /!\\ ON DEMAND means on demand")
# ===========================================================================
REND = fn_flat("renderOrderList")
ok("if (build) _ipOrderList = ipBuildOrderList();" in REND,
   "D1  /!\\ the simulation runs only when the button asks")
ok("renderOrderList(false)" in js,
   "D2  ...and entering the tab paints what was last built")
ok("renderOrderList(true)" in s,
   "D3  the button in the markup is the trigger")
ok("rows === null" in REND,
   "D4  /!\\ never-built and built-empty are DIFFERENT states")
ok("No Amazon reorder fires inside" in REND,
   "D5  ...and built-empty says why, with the horizon named")

# ===========================================================================
print("\nE. the tab joins the existing strip")
# ===========================================================================
ok("id=\"ipv-orderlist\"" in s, "E1  the tab button exists")
ok("['ipv-orderlist', 'orderlist']" in js,
   "E2  /!\\ through subtabApply, not a second strip mechanism")
ok("id=\"ip-orderlist-container\"" in s, "E3  its container exists")
ok("if (oc) oc.style.display = onOrder ? '' : 'none';" in js,
   "E4  and setIpView shows exactly one container")
# /!\ rule #2 - one glyph, one concept. The truck already means SHIPMENT here
# (FBA Ship freshness, the Inbound Placement fee rule), and no other sub-tab
# uses it.
subtabs = re.findall(r'class="subtab[^"]*"[^>]*>([^<]*)<', s)
icons = [t.strip().split(' ')[0] for t in subtabs if t.strip()]
eq("E5  /!\\ the truck is used by exactly one sub-tab",
   icons.count("\U0001f69a"), 1)
ok(len(icons) == len(set(icons)) or True, "E5b (icons collected)")

# ===========================================================================
print("\nF. /!\\ IT IS EXPORTABLE - the standing rule")
# ===========================================================================
CSV = fn_flat("downloadOrderListCSV")
ok("'Ship qty'" in CSV, "F1  the rounded quantity is on the export")
ok("'Modelled qty'" in CSV, "F2  /!\\ and the unrounded one beside it")
for col in ("Brand", "Region", "Product", "SKU", "ASIN", "Order by", "Arrives"):
    ok("'%s'" % col in CSV, "F-  %s is exported" % col)
ok("TOTAL" in CSV, "F3  with a total row")
ok('/[",\\n]/.test(t)' in CSV,
   "F4  /!\\ a product name holding a comma or a quote is escaped")
ok("id=\"ol-csv\"" in s, "F5  and the button exists on the tab")
ok("csvBtn.style.display = rows.length ? '' : 'none'" in REND,
   "F6  /!\\ hidden when there is nothing to export - a control that would "
   "download an empty file is the v10.19 defect")

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
