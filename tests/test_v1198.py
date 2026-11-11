#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.98 - the size tier on the Fees table, and what it would be worth.

Jason: "i also need to see the units size tier on this to see if there are
potential savings options"

Measured on the live Fee Preview, US, newest snapshot per SKU:

    UsLargeStandardSize   119 SKUs   avg $5.13/unit
    UsSmallStandardSize     5 SKUs   avg $3.08/unit

  * A  static: a tier BOUNDARY is written down, a RATE is not.
  * B  the real amzSmallStdGap: all four limits, not just the thin one.
  * C  the real amzSmallStdFee: the median of our OWN Small Standard rows.
  * D  the real rule, driven - including the cases it must refuse.
  * E  the columns, the picker and the export.
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


def fn_flat(name):
    i = js.index("function " + name + "(")
    return js[i:js.index("\n}", i) + 2]


def line_of(pat):
    return re.search(pat, js, re.M).group(0)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v11.98  the size tier, and what it is worth")
print("=" * 68)

REND = nocomment(fn_flat("renderAmazonFees"))
ENG  = nocomment(fn_flat("pnlOpportunityEngine"))
LOAD = nocomment(fn_flat("amzLoadCuFt"))

# ===========================================================================
print("\nA. a boundary is written down, a rate is not")
# ===========================================================================
ok("const AMZ_SMALL_STD = { longest: 15, median: 12, shortest: 0.75, lbs: 1 };" in js,
   "A1  the Small Standard limits are declared once")
ok("Source: Amazon US FBA product size tiers, read 2026-11-11" in js,
   "A2  /!\\ ...with their source and the date they were read")
# /!\ AND NO FEE IS HARDCODED. v11.72 refused a rate card because the rates
# change annually; the Small Standard figure is derived from our own rows.
ok("function amzSmallStdFee(" in js, "A3  the Small Standard fee is DERIVED")
FEEFN = nocomment(fn_flat("amzSmallStdFee"))
ok(not re.search(r"\b[0-9]+\.[0-9]{2}\b", FEEFN),
   "A4  /!\\ no dollar literal anywhere in the derivation")
ok("tier !== 'UsSmallStandardSize'" in FEEFN,
   "A5  ...read off the SKUs already in that tier")
ok("fees.sort" in FEEFN, "A6  ...as a median, so one odd row cannot move it")

# ONE fetch, two indexes - not a second round trip.
eq("A7  /!\\ still one Fee Preview request", LOAD.count(".from('fba_fee_preview')"), 1)
ok("product_size_tier, item_package_weight, unit_of_weight, expected_fulfillment_fee_per_unit" in LOAD,
   "A8  ...with the tier, the weight and Amazon's own fee on it")
ok("amzPackByMid = pk;" in LOAD, "A9  and it publishes the second index")
ok("amzPackByMid = {};" in LOAD,
   "A10 /!\\ a failed read yields {} so it cannot retry for ever")

# ===========================================================================
print("\nB. the real amzSmallStdGap")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1198_b.js"),
    line_of(r"^const AMZ_SMALL_STD = .*$") + "\n" + fn_flat("amzSmallStdGap") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const pk = o => Object.assign({ tier: 'UsLargeStandardSize', lng: 11.85, med: 10,
                                shrt: 1.42, lbs: 0.86, fee: 5.53 }, o);
// The live candidate: Juananip Bites Duo Pack.
t('B1  /!\\ the shortest side is the only limit it misses',
  amzSmallStdGap(pk()), 0.67);
t('B2  ...and a thinner pack needs less off', amzSmallStdGap(pk({ shrt: 0.94 })), 0.19);

// /!\ ALL FOUR LIMITS, not just the thin one. A pack over ANY other limit is
// not a candidate however thin it is - saying otherwise sends him at a pack
// change that cannot pay.
t('B3  /!\\ too long is not a candidate', amzSmallStdGap(pk({ lng: 16 })), null);
t('B4  /!\\ too wide is not a candidate', amzSmallStdGap(pk({ med: 12.5 })), null);
t('B5  /!\\ too heavy is not a candidate', amzSmallStdGap(pk({ lbs: 1.2 })), null);
t('B6  exactly on a limit still qualifies',
  amzSmallStdGap(pk({ lng: 15, med: 12, lbs: 1 })), 0.67);
// Already there, or already thin enough: nothing to claim.
t('B7  a Small Standard pack has no gap',
  amzSmallStdGap(pk({ tier: 'UsSmallStandardSize' })), null);
t('B8  a pack already at the limit has none either',
  amzSmallStdGap(pk({ shrt: 0.75 })), null);
// /!\ WITHIN REACH, caught in a browser: Buds Jar is a 4.50 cube at 0.6 lb,
// so it misses ONLY the shortest side - by 3.75 inches. The rule was right
// and the card was absurd. One limit's worth is the bar.
t('B8b /!\\ a 4.5" cube is NOT one trim from Small Standard',
  amzSmallStdGap(pk({ lng: 4.5, med: 4.5, shrt: 4.5, lbs: 0.6 })), null);
t('B8c ...double the limit still is', amzSmallStdGap(pk({ shrt: 1.5 })), 0.75);
t('B8d ...and a hair over double is not', amzSmallStdGap(pk({ shrt: 1.51 })), null);
// /!\ AN UNREPORTED WEIGHT IS NOT A DISQUALIFIER, because the feed reports
// some rows in another unit and we refuse to convert on a guess (v11.72).
t('B9  /!\\ an unknown weight does not kill the candidate',
  amzSmallStdGap(pk({ lbs: null })), 0.67);
// Missing dimensions answer null rather than NaN.
t('B10 no dimensions, no answer', amzSmallStdGap(pk({ shrt: null })), null);
t('B11 no pack at all', amzSmallStdGap(null), null);
console.log(JSON.stringify(out));
""")
for c in B:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nC. the real amzSmallStdFee")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1198_c.js"),
    "let amzPackByMid = null;\n" + fn_flat("amzSmallStdFee") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
// The five SKUs we really have in Small Standard, US.
amzPackByMid = {
  'A|US': { region:'US', tier:'UsSmallStandardSize', fee: 2.71 },
  'B|US': { region:'US', tier:'UsSmallStandardSize', fee: 2.71 },
  'C|US': { region:'US', tier:'UsSmallStandardSize', fee: 2.71 },
  'D|US': { region:'US', tier:'UsSmallStandardSize', fee: 3.63 },
  'E|US': { region:'US', tier:'UsSmallStandardSize', fee: 3.63 },
  'F|US': { region:'US', tier:'UsLargeStandardSize', fee: 5.53 },
  'G|CA': { region:'CA', tier:'UsSmallStandardSize', fee: 9.99 },
};
t('C1  /!\\ the median of our own Small Standard rows', amzSmallStdFee('US'), 2.71);
t('C2  /!\\ a Large Standard row is not in it',
  amzSmallStdFee('US') === 5.53, false);
t('C3  /!\\ nor is another region\u2019s', amzSmallStdFee('US') === 9.99, false);
t('C4  ...and that region answers for itself', amzSmallStdFee('CA'), 9.99);
// An even count averages the middle two.
amzPackByMid = { 'A|US': { region:'US', tier:'UsSmallStandardSize', fee: 2 },
                 'B|US': { region:'US', tier:'UsSmallStandardSize', fee: 4 } };
t('C5  an even count takes the middle two', amzSmallStdFee('US'), 3);
// /!\ NO SMALL STANDARD SKUs, NO FIGURE - and then no card claims a saving.
amzPackByMid = { 'F|US': { region:'US', tier:'UsLargeStandardSize', fee: 5.53 } };
t('C6  /!\\ nothing in that tier answers null, never zero', amzSmallStdFee('US'), null);
amzPackByMid = null;
t('C7  ...and so does an unloaded feed', amzSmallStdFee('US'), null);
console.log(JSON.stringify(out));
""")
for c in C:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nD. the real rule, driven")
# ===========================================================================
D = run_node(os.path.join(SP, "_v1198_d.js"),
    line_of(r"^const AMZ_SMALL_STD = .*$") + "\n"
    + "const pnlRegion = 'US';\nlet records = [], amzCuFtByMid = {};\nlet amzPackByMid = {};\n"
    + fn_flat("amzSmallStdGap") + "\n" + fn_flat("amzSmallStdFee") + "\n"
    + fn_flat("amzUnitsHeld") + "\n" + fn_flat("pnlOpportunityEngine") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const row = o => Object.assign({ master_id: 'M1', asin: 'B0', brand: 'Meowijuana',
  title: 'Juananip Bites Duo', units: 1571, net_sales: 20000, fees: 7155,
  sponsored: 0, net_proceeds: 0, cogs_total: 0, has_traffic: false, sessions: 0,
  traffic_units_ordered: 0, buy_box_pct: 100, fba_fulfillment_fee_total: 7155,
  referral_fee_total: 0, referral_fee_refunds_total: 0, inbound_transport_fee_total: 0,
  inbound_placement_fee_total: 0, fba_storage_fee_total: 0, aged_inventory_fee_total: 0,
  low_inventory_fee_total: 0, removal_fee_total: 0, storage_util_surcharge: 0,
  refund_admin_fee_total: 0 }, o);
const PACK = { region:'US', tier:'UsLargeStandardSize', lng:11.85, med:10, shrt:1.42, lbs:0.86, fee:5.53 };
const SMALL = { region:'US', tier:'UsSmallStandardSize', lng:7, med:3, shrt:0.5, lbs:0.07, fee:2.71 };
amzPackByMid = { 'M1|US': PACK, 'S1|US': SMALL, 'S2|US': SMALL, 'S3|US': SMALL };
const tier = rows => pnlOpportunityEngine(rows, null).filter(o => o.type === 'sizetier');

const one = tier([row()]);
t('D1  /!\\ the candidate is flagged', one.length, 1);
// 5.53 - 2.71 = 2.82 a unit, over 1,571 units.
t('D2  /!\\ priced at our own tier gap, not a rate card',
  Math.round(one[0].impact), 4430);
t('D3  ...and says the volume it was priced at',
  one[0].impactNote, 'at this window\u2019s volume');
t('D4  the action names the inches to take off',
  /0\.67/.test(one[0].action), true);
t('D5  ...and the two fees it compared',
  /\$2\.71\/unit/.test(one[0].signals.join(' ')), true);

// /!\ NO SMALL STANDARD SKUs IN THIS REGION: nothing to compare with, so no
// card - rather than a saving measured against a number we do not have.
amzPackByMid = { 'M1|US': PACK };
t('D6  /!\\ no Small Standard rows, no card', tier([row()]).length, 0);
amzPackByMid = { 'M1|US': PACK, 'S1|US': SMALL, 'S2|US': SMALL, 'S3|US': SMALL };

// A pack over another limit is not a candidate, even on huge volume.
amzPackByMid['M1|US'] = Object.assign({}, PACK, { lng: 17 });
t('D7  /!\\ an over-long pack is never flagged', tier([row()]).length, 0);
amzPackByMid['M1|US'] = PACK;

// Below the floor: a trickle of units is not an action.
t('D8  /!\\ under the $25 floor it is not a card',
  tier([row({ units: 5 })]).length, 0);
// Nothing sold: there is no volume to price the change at.
t('D9  no units, no saving', tier([row({ units: 0 })]).length, 0);
// A SKU with no Fee Preview row at all.
t('D10 no pack, no card', tier([row({ master_id: 'ZZ' })]).length, 0);
console.log(JSON.stringify(out));
""")
for c in D:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nE. the columns, the picker and the export")
# ===========================================================================
fixed = re.search(r"const AMZ_FEE_FIXED_COLS = \[([\s\S]*?)\n\];", js).group(1)
pick = [(m.group(1), m.group(2)) for m in
        re.finditer(r"\{\s*k:\s*'([A-Za-z0-9_]+)',\s*h:\s*'([^']*)'\s*\}", fixed)]
allc = REND[REND.index("const ALLCOLS = ["):]
tbl = [(m.group(1), m.group(2)) for m in
       re.finditer(r"\{\s*k:\s*'([A-Za-z0-9_]+)',\s*h:\s*'([^']*)'", allc)]
tbl_fixed = [x for x in tbl if x[0] in dict(pick)]
eq("E1  /!\\ the picker's keys still match the table's",
   [k for k, _ in pick], [k for k, _ in tbl_fixed])
eq("E2  ...and the headers", [h for _, h in pick], [h for _, h in tbl_fixed])
for k, h in (('tier', 'Size Tier'), ('shrt', 'Short in'), ('lbs', 'Pack lb')):
    ok((k, h) in pick, "E3  %s is in the declared pair as '%s'" % (k, h))
eq("E4  /!\\ every column header is still unique",
   len([h for _, h in tbl]), len(set(h for _, h in tbl)))

# The asterisk is the candidate mark, and the Short in cell is what reddens.
ok("p.tierGap != null ? '*' : ''" in REND, "E5  a candidate is marked on the tier")
ok("red: p => p.tierGap != null," in REND, "E6  ...and the side that causes it reddens")
# /!\ AND THE PACK COLUMNS CARRY NO DELTA CHIP. They are STATES - what the
# pack IS - so the previous window has no pack to compare and every row read
# `new - no prior data`. Same class as Held and Cu Ft (v11.93).
ok("const AMZ_FEE_DELTA_NONE = new Set(['held', 'cuft', 'sellThru', 'tier', 'shrt', 'lbs']);" in js,
   "E6b /!\\ the three pack columns are suppressed")

CSV = nocomment(fn_flat("downloadAmazonFeesCSV"))
for h in ("Size Tier", "Shortest in", "Pack lb", "Fee Preview $/unit",
          "Shortest in over Small Standard"):
    ok("'%s'" % h in CSV, "E7  the CSV carries %s" % h)
# The header and every row must stay the same width.
head_n = len(re.findall(r"'[^']+'", CSV[CSV.index("const head = ["):CSV.index("const n2")]))
ok(head_n > 0, "E8  the CSV header parses")

ok("const AMZ_FEE_OPP_TYPES = new Set(['placement', 'aged', 'lowinv', 'idle', 'feeload', 'sizetier']);" in js,
   "E9  /!\\ the Fees tab shows the new card too")

# Rule #2: the new glyph is not already an opportunity type's.
ic = re.findall(r"type: '([a-z]+)', icon: '([^']+)'", js)
seen = {}
for t_, i_ in ic:
    seen.setdefault(i_, []).append(t_)
eq("E10 /!\\ one glyph, one opportunity type", {k: v for k, v in seen.items() if len(v) > 1}, {})
eq("E11 ...across all fifteen rules", len(ic), 15)

chip = re.search(r'margin-left:4px">v(\d+\.\d+)', s).group(1)
cmd = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", errors="replace").read()
doc = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cmd).group(1)
eq("E12 the chip and CLAUDE.md agree", doc, chip)

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
