#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.94 - the fee levers become actions, on the surface that already has them.

Jason, on the Fees tab: "this still isn't telling me how to action."

  * A  static: five fee rules inside the engine that already emits actions,
       one floor, and removal deliberately absent with its reason.
  * B  the real pnlOpportunityEngine driven: each rule fires on the shape it
       is for, the floor holds, and IDLE does not double up on AGED.
  * C  the real amzFeeWidenPeriod on a pinned clock.
  * D  the aggregation carries the fee lines, through the ONE fx spelling.
  * E  /!\ THE WINDOW THAT CANNOT SEE A LEVER. Month-to-date on the 10th
       holds one week and $0.84 of avoidable fee - measured on the live
       table - so the panel read `0.0% avoidable`.
  * F  the strip's glyphs are unique, and the chip agrees with CLAUDE.md.
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
    """Slice by the closing brace at column 0.

    /!\\ NOT by brace balance: the IDLE SHELF headline is a template literal
    with another template literal inside it, and a matcher that treats a
    backtick as a plain string ends the slice in the wrong place (v11.91).
    """
    i = js.index("function " + name + "(")
    return js[i:js.index("\n}", i) + 2]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v11.94  the fee levers, as actions")
print("=" * 68)

ENG  = nocomment(fn_flat("pnlOpportunityEngine"))
FEES = nocomment(fn_flat("renderAmazonFees"))

# ===========================================================================
print("\nA. five rules, in the engine that already emits actions")
# ===========================================================================
RULES = ['placement', 'aged', 'lowinv', 'idle', 'feeload']
for t in RULES:
    ok("type: '%s'" % t in ENG, "A1  the %s rule is in pnlOpportunityEngine" % t)

# /!\ HARD RULE #1: NOT A SECOND ACTION LIST. The Fees tab must not grow its
# own cards - it ranks, the engine acts.
ok("headline:" not in FEES and "signals:" not in FEES,
   "A2  /!\\ the Fees tab did NOT grow a second action list")
ok("switchPnlAmazonView('opportunities')" in s,
   "A3  ...it points at the one that exists")

# One floor, read by all of them, rather than five magic numbers.
eq("A4  /!\\ the floor is declared once", ENG.count("const FEE_OPP_MIN = 25;"), 1)
ok(ENG.count("FEE_OPP_MIN") >= 5, "A5  ...and every rule reads it")
# The outlier is measured against the catalogue, not against a typed number.
ok("medianFeePct" in ENG and "medianOf(" in ENG,
   "A6  the fee-load outlier is measured against the fleet median")

# /!\ REMOVAL IS DELIBERATELY NOT A RULE, and the reason is recorded beside
# the rules rather than left for someone to re-derive.
ok("type: 'removal'" not in ENG, "A7  /!\\ removal is not a rule")
ok("REMOVAL IS DELIBERATELY NOT A RULE" in fn_flat("pnlOpportunityEngine"),
   "A8  ...and the reason is written where the rules are")

# The impact note is a PARAMETER, not a second card renderer (v10.60).
ok("o.impactNote || 'est. impact / mo'" in js,
   "A9  /!\\ the card's impact note is parameterised, not forked")
# /!\ SIX SINCE v11.98, which added the SIZE TIER rule.
ok(ENG.count("impactNote:") == 6, "A10 ...and every fee rule sets its own")
# /!\ AND THE STRIP HEADER CANNOT CARRY ONE, because it is one figure over
# several cards - so it stops claiming a period rather than claiming the
# wrong one. Caught in a browser: it read `$1882/mo total upside` over a
# modelled monthly lift PLUS a fee charged in this window.
# /!\ SCOPED TO THIS HEADER. `total upside` also appears in the Growth
# Model's tooltip, where it is correct and unrelated - my first assertion
# swept the whole file and failed on it.
ok("/mo total upside" not in js, "A9b /!\\ the header stopped claiming a month")
ok("total impact</div>" in js, "A9c ...and names what it actually sums")
# A fee rule must not borrow the ads rules' modelled lift.
# /!\ SPLIT ON THE RAW TEXT, not on ENG: the marker is a COMMENT, and
# nocomment() had already removed it - so the split was a no-op and this
# assertion was reading the whole engine. My bug, not the code's.
ok("MARGINAL_ROAS" not in fn_flat("pnlOpportunityEngine").split("THE FEE LEVERS, AS ACTIONS")[-1],
   "A11 /!\\ no marginal-ROAS assumption inside a fee rule")

# ===========================================================================
print("\nB. the real engine, driven")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1194_b.js"), r"""
const pnlRegion = 'US';
let records = [];
let amzCuFtByMid = {};
""" + fn_flat("amzUnitsHeld") + "\n" + fn_flat("pnlOpportunityEngine") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const base = (o) => Object.assign({
  master_id: 'M?', asin: 'B0', brand: 'Meowijuana', title: 'x', units: 10,
  net_sales: 1000, sponsored: 0, net_proceeds: 600, cogs_total: 300,
  has_traffic: false, sessions: 0, traffic_units_ordered: 0, buy_box_pct: 100,
  fees: 400, inbound_placement_fee_total: 0, aged_inventory_fee_total: 0,
  low_inventory_fee_total: 0, removal_fee_total: 0, fba_storage_fee_total: 0,
  storage_util_surcharge: 0,
}, o);
const typesFor = rows => {
  const o = pnlOpportunityEngine(rows, null);
  return o.filter(x => ['placement','aged','lowinv','idle','feeload'].includes(x.type));
};

// --- the floor ------------------------------------------------------------
t('B1  /!\\ a $24 placement charge is below the floor',
  typesFor([base({ master_id: 'A', inbound_placement_fee_total: 24 })]).length, 0);
const p25 = typesFor([base({ master_id: 'A', inbound_placement_fee_total: 820 })]);
t('B2  ...$820 is a card', p25.length, 1);
t('B3  priced at the fee itself, not a modelled lift', Math.round(p25[0].impact), 820);
t('B4  ...and the card says so rather than claiming a month',
  p25[0].impactNote, 'fee charged in window');
t('B5  with a verb in it', /Split the next shipment/.test(p25[0].action), true);

// --- aged: the escalation is the SHARE, not the size ----------------------
const bigSeller = typesFor([base({ master_id: 'A', aged_inventory_fee_total: 90,
                                   net_sales: 24000, units: 2100 })]);
t('B6  a small share on a big seller is priority 1', bigSeller[0].priority, 1);
const eaten = typesFor([base({ master_id: 'A', aged_inventory_fee_total: 884,
                               net_sales: 1774, units: 12 })]);
t('B7  /!\\ 50% of net sales escalates it to priority 0', eaten[0].priority, 0);
t('B8  ...and the headline carries the share',
  /50% of what this product earned/.test(eaten[0].headline), true);

// --- idle shelf -----------------------------------------------------------
records = [{ master_id: 'IDLE', region: 'US', fba_available: 980, fba_inbound: 0 }];
amzCuFtByMid = { 'IDLE|US': 0.051 };
const idle = typesFor([base({ master_id: 'IDLE', units: 0, net_sales: 0, fees: 0 })]);
t('B9  /!\\ stock held, nothing sold, and the volume is measured',
  idle.filter(o => o.type === 'idle').length, 1);
t('B10 ...the cu ft is on the headline',
  /50 cu ft/.test(idle.find(o => o.type === 'idle').headline), true);

// /!\ AND IT DOES NOT FIRE WHERE AGED ALREADY DID - one decision, one card.
const both = typesFor([base({ master_id: 'IDLE', units: 0, net_sales: 0, fees: 884,
                              aged_inventory_fee_total: 884 })]);
t('B11 /!\\ AGED wins, and IDLE stays quiet',
  both.map(o => o.type).sort().join(','), 'aged');

// A product that IS selling is never idle, however much it holds.
const selling = typesFor([base({ master_id: 'IDLE', units: 400, net_sales: 4000 })]);
t('B12 a product that sold is not idle',
  selling.filter(o => o.type === 'idle').length, 0);
// Nothing held: nothing to say.
records = [];
t('B13 no inventory figure, no card',
  typesFor([base({ master_id: 'IDLE', units: 0, net_sales: 0, fees: 0 })])
    .filter(o => o.type === 'idle').length, 0);

// --- fee load outlier -----------------------------------------------------
// A fleet at 40% with one product at 70%.
const fleet = [];
for (let i = 0; i < 9; i++) fleet.push(base({ master_id: 'F' + i, net_sales: 1000, fees: 400 }));
fleet.push(base({ master_id: 'OUT', net_sales: 1000, fees: 700 }));
const fl = typesFor(fleet).filter(o => o.type === 'feeload');
t('B14 /!\\ exactly one product is an outlier', fl.length, 1);
t('B15 ...and it is the one at 70%', fl[0].product.master_id, 'OUT');
t('B16 priced as the gap to the median, on this window’s sales',
  Math.round(fl[0].impact), 300);
t('B17 /!\\ a product under $250 of sales is not an outlier',
  typesFor(fleet.concat([base({ master_id: 'TINY', net_sales: 100, fees: 90 })]))
    .filter(o => o.type === 'feeload').map(o => o.product.master_id).join(','), 'OUT');

// --- nothing moved for the rules that already existed ---------------------
const adsOnly = pnlOpportunityEngine([base({
  master_id: 'BLEED', net_sales: 1000, net_proceeds: 200, cogs_total: 400,
  sponsored: 300, fees: 0 })], null);
t('B18 /!\\ the ads rules still fire', adsOnly.some(o => o.type === 'bleed'), true);
t('B19 ...and a row with no fees emits no fee card',
  adsOnly.some(o => ['placement','aged','lowinv','idle','feeload'].includes(o.type)), false);
console.log(JSON.stringify(out));
""")
for c in B:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nC. the real amzFeeWidenPeriod, on a pinned clock")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1194_c.js"), fn_flat("amzFeeWidenPeriod") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const NOW = '2026-11-10';
t('C1  /!\\ a charge 15 days back fits the 30-day period',
  amzFeeWidenPeriod('2026-10-26', NOW), '30');
t('C2  one 45 days back needs 60', amzFeeWidenPeriod('2026-09-26', NOW), '60');
t('C3  ...71 days needs 90', amzFeeWidenPeriod('2026-08-31', NOW), '90');
t('C4  ...and a year-old charge needs 365',
  amzFeeWidenPeriod('2025-12-29', NOW), '365');
// /!\ OLDER THAN EVERY FIXED PERIOD: the control is NOT offered, because a
// period that still would not hold the charge is a button that does nothing.
t('C5  /!\\ older than 365 days offers nothing',
  amzFeeWidenPeriod('2025-01-05', NOW), null);
t('C6  no last-charged week, no control', amzFeeWidenPeriod('', NOW), null);
t('C7  junk answers null rather than NaN days',
  amzFeeWidenPeriod('not-a-date', NOW), null);
t('C8  the derivation reads the week START, so a charge today still fits 30',
  amzFeeWidenPeriod('2026-11-09', NOW), '30');
console.log(JSON.stringify(out));
""")
for c in C:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nD. the aggregation carries the fees, through one fx spelling")
# ===========================================================================
OPP = nocomment(fn_flat("renderPnlOpportunities"))
ok("for (const l of AMZ_FEE_LINES) a[l.k] = 0;" in OPP,
   "D1  /!\\ the fee keys are seeded from the registry, not listed")
ok("for (const l of AMZ_FEE_LINES) { const fv = (row[l.k] || 0) * fx; a[l.k] += fv; a.fees += fv; }" in OPP,
   "D2  ...and accumulated in the same pass as the rest of the row")
# /!\ THE THIRD FX COPY IS GONE. It was CAD-only, so a GBP or EUR row counted
# at face value.
ok("const fx = pnlRowFx(row);" in OPP,
   "D3  /!\\ the aggregation uses the ONE fx helper")
ok("row.currency === 'CAD'" not in OPP,
   "D4  ...and the CAD-only copy is gone")
# No chart or tab may now hold a fourth one.
eq("D5  pnlRowFx is the only fx spelling left in the P&L",
   len(re.findall(r"currency === 'CAD'\) \? \(1 / ", js)), 0)

# ===========================================================================
print("\nE. /!\\ the window that could not see a lever")
# ===========================================================================
# Measured on the live table on 2026-11-10: US, 2026-11-01 -> 11-10 is ONE
# week of rows, 259 products, $34,615 net sales and $0.84 of avoidable fee.
# /!\ THE TEST IS PER LINE, NOT ON THE TOTAL - and that is the correction a
# browser made to my first cut. His own window carried $0.84 of Removal, so
# the newest avoidable billing week was INSIDE it while three other lines
# were behind it; a total-based test would have stayed silent on exactly the
# window it was built for.
ok("const avBlind = PLAN.target > 0 && !PLAN.covered && avUnseen.length > 0;" in FEES,
   "E1  /!\\ a line whose last charge is behind the window is detected")
ok(".filter(x => x.last && x.last < A.from)" in FEES,
   "E2  ...per LINE, and only when it HAS been charged before")
ok("PLAN.covered" in FEES.split("const AV_LINES")[1][:400],
   "E2b /!\\ ...and only while the target is not already covered")
ok("amzFeeWidenPeriod(avNewest)" in FEES,
   "E3  the period offered is derived from the newest such billing week")
ok("pnlSetPeriod('${avWiden}')" in FEES,
   "E4  /!\\ and it is a control, not a sentence telling him to change it")
ok("avWiden ?" in FEES,
   "E5  ...offered only when a period exists that would hold it (v10.19)")
ok("comp.innerHTML = avHtml +" in FEES,
   "E6  it renders above the table it explains")
# One spelling of setting the period.
ok("function pnlSetPeriod(v) {" in js, "E7  one period setter")
ok("onPnlPeriodChange()" in nocomment(fn_flat("pnlSetPeriod")),
   "E8  ...which goes through the page's own handler, not a second render")

# ===========================================================================
print("\nF. the strip, and the chip")
# ===========================================================================
ic = re.findall(r"type: '([a-z]+)', icon: '([^']+)'", js)
seen = {}
for t_, i_ in ic:
    seen.setdefault(i_, []).append(t_)
dupes = {k: v for k, v in seen.items() if len(v) > 1}
eq("F1  /!\\ one glyph, one opportunity type (rule #2)", dupes, {})
# /!\ FIFTEEN SINCE v11.98. The guarantee is UNIQUENESS, above; the count
# is a census and grows with the engine.
eq("F2  ...across every rule the engine declares", len(ic), 15)
# /!\ FIXED ON THE WAY PAST, NOT CAUSED HERE: `invest` and `headroom` both
# carried the rocket since v8.85, and they render as chips in one strip.
ok("type: 'headroom', icon: '\U0001f4c8'" in js,
   "F3  the second rocket became its own glyph")

chip = re.search(r'margin-left:4px">v(\d+\.\d+)', s).group(1)
cmd = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", errors="replace").read()
doc = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cmd).group(1)
# /!\ NOT A LITERAL VERSION (the v11.93 lesson, applied here before it bit):
# a suite that pins the chip goes red on the next release for doing its job.
ok(re.match(r"^11\.\d+$", chip) is not None, "F4  the chip carries a v11.x version", chip)
eq("F5  /!\\ ...and CLAUDE.md agrees with it", doc, chip)
ok("## v11.94 - the fee levers become actions" in cmd,
   "F6  /!\\ ...and v11.94's own entry is still on record")

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
