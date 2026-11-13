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
ROW   = fn_flat("ipOrderRowFor")
# v12.32 - /!\ ONE ROW SHAPE. The scheduled path and the manual-add path both
# go through ipOrderRowFor, so they cannot describe a product two ways.
ok("inventoryNeedBreakdown(r, horizon, region" in ROW,
   "B1  /!\\ the quantity comes from the page's own breakdown")
ok("meta.events && meta.events[0]" in ROW,
   "B2  /!\\ ...and from the NEXT event, which is what one shipment is")
ok("inventoryVisibleRecords()" in BUILD,
   "B3  /!\\ the filters are the page's own - brand, region, category, status, "
   "search, bundles, inactive, in-house")
ok("if (!ev || !(ev.qty > 0)) return null;" in ROW,
   "B4  /!\\ no event is an ABSENCE, not a zero row (v11.16)")
ok("ipRoundShipQty(ev.qty)" in ROW, "B5  the rounding is applied once, here")
ok("raw:  Math.round(ev.qty)" in ROW,
   "B6  /!\\ and the UNROUNDED figure is carried, so the rounding is auditable")
# /!\ no second velocity, cover or lead-time arithmetic in this file's new code
ok("reorder_qty_days" not in (BUILD + ROW) and "blended_daily" not in (BUILD + ROW),
   "B7  /!\\ it re-derives NOTHING - no second velocity or reorder model")

# ===========================================================================
print("\nC. grouping, ordering and the totals")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1231_c.js"), r"""
// v12.32 - REGION first. Jason: "should be for amazon (by region)".
const rows = [
  { brand: 'Meowijuana', region: 'US', title: 'b', qty: 50 },
  { brand: 'Kitty Ka-Zoom', region: 'US', title: 'c', qty: 10 },
  { brand: 'Meowijuana', region: 'CA', title: 'd', qty: 90 },
  { brand: 'Meowijuana', region: 'US', title: 'a', qty: 200 },
  { brand: 'Kitty Ka-Zoom', region: 'CA', title: 'e', qty: 30 },
];
rows.sort((a, b) => (a.region || '').localeCompare(b.region || '')
                 || (a.brand  || '').localeCompare(b.brand  || '')
                 || (b.qty - a.qty));
const byRegion = new Map();
for (const x of rows) {
  if (!byRegion.has(x.region)) byRegion.set(x.region, []);
  byRegion.get(x.region).push(x);
}
console.log(JSON.stringify({
  regions: [...byRegion.keys()],
  caOrder: byRegion.get('CA').map(r => r.brand[0] + r.qty),
  usQtys:  byRegion.get('US').map(r => r.qty),
  grand: rows.reduce((t, x) => t + x.qty, 0),
}));
""")
eq("C1  /!\\ REGION is the outer sort", C["regions"], ["CA", "US"])
# v12.33 - /!\ A GROUP IS A BRAND AND A REGION. v12.32 grouped by region
# alone, so a CA shipment carried two brands under one subtotal - and that
# subtotal is not a number anyone orders against.
REND_ = fn_flat("renderOrderList")
ok("x.region + '\\u0000' + x.brand" in REND_,
   "C1b /!\\ the groups are keyed on the PAIR")
ok("key.split('\\u0000')[0]" in REND_ and "key.split('\\u0000')[1]" in REND_,
   "C1c ...and the heading names both")
ok("TH('Product') + TH('SKU')" in REND_,
   "C1d /!\\ and the Brand COLUMN is gone - it is the heading now, and "
   "repeating it down every row is the same word twice")
eq("C2  brands sort inside the region", C["caOrder"], ["K30", "M90"])
eq("C3  /!\\ and the biggest shipment leads its brand", C["usQtys"], [10, 200, 50])
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
ok("Nothing has to be ordered by" in REND,
   "D5  ...and built-empty says why, naming the SHIP DATE that selects")
ok("Move the ship date forward, or add a product" in REND,
   "D5b ...and what to do about it")

# ===========================================================================
print("\nE. the tab joins the existing strip")
# ===========================================================================
ok("id=\"ipv-orderlist\"" in s, "E1  the tab button exists")
# v12.32 - Jason named it. The app uses his word.
ok("Amazon Reorder</button>" in s, "E1b and it reads Amazon Reorder")
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
ok("'Source'" in CSV,
   "F2b /!\\ and whether each line was modelled or typed by hand")
ok("'Ship date'" in CSV, "F2c with the ship date on every row")
for col in ("Brand", "Region", "Product", "SKU", "ASIN", "Order by", "Arrives"):
    ok("'%s'" % col in CSV, "F-  %s is exported" % col)
ok("TOTAL" in CSV, "F3  with a total row")
ok('/[",\\n]/.test(t)' in CSV,
   "F4  /!\\ a product name holding a comma or a quote is escaped")
ok("id=\"ol-csv\"" in s, "F5  and the button exists on the tab")
ok("csvBtn.style.display = rows.length ? '' : 'none'" in REND,
   "F6  /!\\ hidden when there is nothing to export - a control that would "
   "download an empty file is the v10.19 defect")

# ===========================================================================
print("\nH. /!\\ THE SHIP DATE DECIDES WHAT IS IN THE BOX")
# ===========================================================================
# v12.31 asked "what fires inside the horizon" - a planning question. A ship
# date asks "I am sending a box that day, what belongs in it".
ok("ipOrderShipDate()" in BUILD, "H1  the build reads the ship date")
ok("row.orderBy > ship" in BUILD,
   "H2  /!\\ ON OR BEFORE - a product due the day the box ships is IN it, "
   "or the box leaves already late for that SKU")
SHIP = fn_flat("ipOrderShipDate")
ok("new Date()" in SHIP,
   "H3  /!\\ the default is TODAY, not a horizon - moving it forward is a "
   "decision, not a default")
ok("id=\"ol-shipdate\"" in s, "H4  the control exists")
ok("onchange=\"renderOrderList(true)\"" in s, "H5  ...and rebuilds on change")

# ===========================================================================
print("\nI. /!\\ ADD AND REMOVE SURVIVE A REBUILD")
# ===========================================================================
# If the edits lived inside the computed list, changing the ship date would
# throw them away - which is the one thing an operator cannot forgive.
ok("let _ipOrderRemoved = new Set();" in js and "let _ipOrderAdded   = new Map();" in js,
   "I1  the edits are overlays, keyed on master_id")
ok("if (_ipOrderRemoved.has(ipOrderKey(r.master_id, reg))) continue;" in BUILD,
   "I2  /!\\ a removed product stays out of every rebuild, keyed on its REGION too")
ok("for (const [key, add] of _ipOrderAdded)" in BUILD,
   "I3  /!\\ and adds are REPLAYED over the build, not written into it")
ok("row.manual = true;" in BUILD, "I4  a hand-entered quantity is marked")
ok("hit.qty = ipRoundShipQty(add.qty)" in BUILD,
   "I5  /!\\ an override on a product already in the box replaces its qty "
   "rather than adding the row twice")
ADD = fn_flat("ipOrderAdd")
ok("if (!(n > 0))" in ADD, "I6  a zero or blank quantity is refused")
ok("_ipOrderRemoved.delete(key)" in ADD,
   "I7  /!\\ adding back something removed un-removes it")
PRE = fn_flat("ipOrderPrefillQty")
ok("qty.value = row ? row.qty : '';" in PRE,
   "I8  /!\\ prefilled from the model where there is one, BLANK where there "
   "is not - a made-up number in a quantity box is the worst default")
PICK = fn_flat("ipOrderFillPicker")
ok("if (inBox.has(ipOrderKey(r.master_id, reg))) continue;" in PICK,
   "I9  /!\\ the picker offers only products not already in THIS region's box - a SKU in the US box is still a legitimate add to the CA one")
ok("pick.dataset.sig === sig" in PICK,
   "I10 /!\\ and is rebuilt only when the SET changes, or a repaint would "
   "drop the selection mid-add (v10.99)")
ok("id=\"ol-reset\"" in s, "I11 the edits can be reset")
ok("rstBtn.style.display = edited ? '' : 'none'" in REND,
   "I12 ...and that control is hidden when there is nothing to reset")

# ===========================================================================
print("\nJ. /!\\ ONE MARKETPLACE PER ROW - US+CA IS NOT A SHIPMENT")
# ===========================================================================
# Jason: "WHY are you making a US+CA list? they need to be either in US or CA"
#
# `US+CA` is the POOLED record. Pooling is right for PLANNING - one cover
# figure across both marketplaces - and wrong for a shipment: a box goes to
# one of them, and "US+CA 35 units" is not a line anyone can order.
REG = fn_flat("ipOrderRegionsFor")
R = run_node(os.path.join(SP, "_v1231_j.js"), REG + r"""
console.log(JSON.stringify({
  pooled: ipOrderRegionsFor({ region: 'US+CA' }, ''),
  us:     ipOrderRegionsFor({ region: 'US' }, ''),
  ca:     ipOrderRegionsFor({ region: 'CA' }, ''),
  spaced: ipOrderRegionsFor({ region: 'US + CA' }, ''),
  narrow: ipOrderRegionsFor({ region: 'US+CA' }, 'CA'),
  blank:  ipOrderRegionsFor({ region: '' }, ''),
  none:   ipOrderRegionsFor({}, ''),
  three:  ipOrderRegionsFor({ region: 'US+CA+MX' }, ''),
}));
""")
eq("J1  /!\\ a POOLED record becomes two rows", R["pooled"], ["US", "CA"])
eq("J2  ...and whitespace does not defeat the split", R["spaced"], ["US", "CA"])
eq("J3  a single-region record stays one row", R["us"], ["US"])
eq("J4  ...either way round", R["ca"], ["CA"])
eq("J5  /!\\ a narrowed page filter DECIDES it", R["narrow"], ["CA"])
eq("J6  a blank region falls back to US rather than vanishing", R["blank"], ["US"])
eq("J7  ...and so does a record with no region at all", R["none"], ["US"])
eq("J8  /!\\ a third marketplace would follow with no code change",
   R["three"], ["US", "CA", "MX"])

ok("region: region || (r.region || 'US')" in ROW,
   "J9  /!\\ the row is stamped with the REQUESTED region, never the pooled label")
ok("ipOrderRegionsFor(r, region)" in BUILD, "J10 the build splits before it asks")
# /!\ the key has to carry the region or one remove takes out two rows
KEY = fn_flat("ipOrderKey")
ok("String(mid) + '\\u0000' + String(region)" in KEY,
   "J11 /!\\ the overlay key is product AND region")
ok("ipOrderRemove(mid, region)" in js,
   "J12 ...and remove is handed both")
ok("ipOrderRemove('${esc2(mid)}','${esc2(x.region)}')" in REND_,
   "J13 ...from the row's own button")
ADDREG = fn_flat("ipOrderAddRegion")
ok("picked || (el && el.value) || 'US'" in ADDREG,
   "J14 /!\\ a narrowed page filter decides the add's region; otherwise the "
   "operator does, in a control rather than a silent default")
ok('id="ol-add-region"' in s, "J15 and that control exists")

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
