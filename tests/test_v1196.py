#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.96 - the actions come to the Fees page, and the row opens.

Jason: "and the fees are still a lump number. i have no idea how to action
the fee table. the 'action' button goes to the opportunities page, which is
set up for sales"

  * A  ONE card renderer, two hosts - and exactly one copy of the markup.
  * B  the real amzFeeActions: the fee rules over this tab's rows, and the
       ads rules filtered out rather than relied on not to fire.
  * C  the real amzFeeRowBreakdown: what the lump is made of.
  * D  the row opens, and the button that left the page is gone.
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
    d, k = 0, js.index("{", i)
    j = k
    while k < len(js):
        if js[k] == "{":
            d += 1
        elif js[k] == "}":
            d -= 1
            if d == 0:
                return "const %s = %s;" % (name, js[j:k + 1])
        k += 1
    raise SystemExit("unbalanced %s" % name)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v11.96  the actions on the Fees page, and the row that opens")
print("=" * 68)

REND = nocomment(fn_flat("renderAmazonFees"))
OPPR = nocomment(fn_flat("renderPnlOpportunities"))

# ===========================================================================
print("\nA. one card renderer, two hosts")
# ===========================================================================
ok("function pnlOppCardHtml(o) {" in js, "A1  the card is a function")
ok("const cards = cardsSet.map(o => pnlOppCardHtml(o)).join('');" in OPPR,
   "A2  /!\\ the Opportunities page calls it")
ok("OPS.map(o => pnlOppCardHtml(o)).join('')" in REND,
   "A3  /!\\ ...and so does the Fees tab")
# /!\ EXACTLY ONE COPY OF THE MARKUP. A second card look is the thing hard
# rule #1 exists to stop, and this release is the one that could create it.
eq("A4  /!\\ one copy of the card markup, app-wide",
   js.count("border-left:4px solid ${o.color}"), 1)
eq("A5  ...and one `Action:` block", js.count("Action:</strong> ${o.action}"), 1)
# Moved verbatim: the impact note parameter from v11.94 came with it.
ok("o.impactNote || 'est. impact / mo'" in fn_flat("pnlOppCardHtml"),
   "A6  the card kept its impact-note parameter")

# ===========================================================================
print("\nB. the real amzFeeActions")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1196_b.js"),
    const_arr("AMZ_FEE_LINES") + "\n"
    + re.search(r"(?m)^const AMZ_FEE_OPP_TYPES\s*=.*$", js).group(0) + "\n" + r"""
const pnlRegion = 'US';
let records = [], amzCuFtByMid = {};
const allProducts = [{ master_id: 'M1', short_name: 'Pawty Mix', brand: 'Meowijuana', asin: 'B01' }];
""" + fn_flat("amzUnitsHeld") + "\n" + fn_flat("pnlOpportunityEngine") + "\n"
    + fn_flat("amzFeeActions") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const prod = (mid, o) => Object.assign({ mid, name: mid, units: 100, netSales: 5000, fees: 2000 }, o);
const A = { prods: [
  prod('M1', { inbound_placement_fee_total: 820 }),
  prod('M2', { aged_inventory_fee_total: 884, netSales: 1774, units: 12 }),
  prod('M3', { }),
] };
const ops = amzFeeActions(A);
// /!\ MY EXPECTATION WAS WRONG, NOT THE CODE: M2 carries $2,000 of fees on
// $1,774 of sales, which is 113% against a fleet median of 40% - so the
// FEE LOAD OUTLIER rule is right to fire on it as well.
t('B1  the fee rules fire over this tab’s rows',
  ops.map(o => o.type).sort().join(','), 'aged,feeload,placement');
t('B2  /!\\ the card carries the product the Fees tab knows',
  ops.find(o => o.type === 'placement').product.master_id, 'M1');
t('B3  ...and its asin, for the card subtitle',
  ops.find(o => o.type === 'placement').product.asin, 'B01');

// /!\ THE ADS RULES MUST NOT APPEAR, and the filter is what guarantees it -
// not the hope that a missing figure reads as "no signal".
t('B4  /!\\ every card is a fee type',
  ops.every(o => AMZ_FEE_OPP_TYPES.has(o.type)), true);
const raw = pnlOpportunityEngine([{ master_id: 'X', title: 'x', units: 1, net_sales: 5000,
  fees: 0, sponsored: 400, net_proceeds: 100, cogs_total: 900, has_traffic: true,
  sessions: 500, traffic_units_ordered: 2, buy_box_pct: 50 }], null);
t('B5  /!\\ the engine DOES emit ads cards on an ads row',
  raw.some(o => !AMZ_FEE_OPP_TYPES.has(o.type)), true);
t('B6  ...and the Fees tab would drop every one of them',
  raw.filter(o => AMZ_FEE_OPP_TYPES.has(o.type)).length, 0);

// A tab with nothing loaded answers an empty list rather than throwing.
t('B7  no rows, no cards', amzFeeActions({ prods: [] }).length, 0);
t('B8  ...and no aggregate at all is the same', amzFeeActions(null).length, 0);
console.log(JSON.stringify(out));
""")
for c in B:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nC. the real amzFeeRowBreakdown")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1196_c.js"),
    const_arr("AMZ_FEE_LINES") + "\n" + const_obj("AMZ_FEE_LEVER") + "\n"
    + "const esc2 = x => String(x == null ? '' : x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/\"/g,'&quot;');\n"
    + fn_flat("amzFeeRowBreakdown") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const p = { name: 'Pawty Mix', fees: 33402,
  fba_fulfillment_fee_total: 21500, referral_fee_total: 9800,
  referral_fee_refunds_total: -210, inbound_transport_fee_total: 940,
  inbound_placement_fee_total: 820, fba_storage_fee_total: 410,
  aged_inventory_fee_total: 90, low_inventory_fee_total: 0,
  removal_fee_total: 40, storage_util_surcharge: 0, refund_admin_fee_total: 12 };
const h = amzFeeRowBreakdown(p, 22);
t('C1  it is one row, spanning the table', /^<tr><td colspan="22"/.test(h), true);
// /!\ PINNED AND SIZED TO THE PANEL. The cell spans a 22-column table wider
// than its panel, so a plain block stretched to the TABLE's width and put
// the dollars, the share and the lever off the right-hand edge - this row's
// own defect, reproduced inside it. Caught in a browser at 603px.
t('C1b /!\\ the breakdown is pinned to the scroll-left edge',
  h.indexOf('position:sticky;left:0') >= 0, true);
t('C1c ...and sized to the panel, not to the table',
  h.indexOf('width:532px;max-width:100%') >= 0, true);
t('C1d ...with no free column that could stretch it',
  h.indexOf('1fr') < 0, true);
// /!\ A LINE CHARGED NOTHING IS LEFT OUT - a breakdown says where the money
// went, and two rows of dashes under every product is what v11.72 fixed.
t('C2  /!\\ the two zero lines are not listed',
  h.indexOf('Low Inventory') < 0 && h.indexOf('Storage Surcharge') < 0, true);
t('C3  ...so nine lines are', (h.match(/cursor:help;color:var\(--text2\)/g) || []).length, 9);
// Biggest first, so the eye lands on the line that is the lump.
const order = [...h.matchAll(/text-overflow:ellipsis">([^<]+)</g)].map(m => m[1]);
t('C4  /!\\ ranked by size', order[0], 'FBA Fulfilment');
t('C5  ...then the second biggest', order[1], 'Referral');
t('C6  a refund keeps its sign and its place by MAGNITUDE',
  order.indexOf('Referral Refunds') >= 0 && h.indexOf('$-210.00') >= 0, true);
// The shares are of the product's own fees, so they read as "of this row".
t('C7  the biggest line carries its share', h.indexOf('>64%<') >= 0, true);
// Each line carries the lever it carries on the composition panel.
t('C8  /!\\ the lever comes from the one registry',
  h.indexOf('Avoidable') >= 0 && h.indexOf('Rate') >= 0 && h.indexOf('Fixed') >= 0, true);
// A product with no fee line at all says so rather than rendering an empty box.
const none = amzFeeRowBreakdown({ name: 'x', fees: 0 }, 22);
t('C9  a product with no fee line says so',
  none.indexOf('No fee line charged against this product') >= 0, true);
t('C10 ...and still spans the table', /colspan="22"/.test(none), true);
// The product name is escaped - it is a title, not markup.
const xss = amzFeeRowBreakdown({ name: '<b>x</b>', fees: 1, removal_fee_total: 50 }, 3);
t('C11 /!\\ the product name is escaped', xss.indexOf('<b>x</b>') < 0, true);
console.log(JSON.stringify(out));
""")
for c in C:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nD. the row opens, and the page keeps you on it")
# ===========================================================================
ok("const open = amzFeeOpenRows.has(p.mid);" in REND, "D1  the row knows whether it is open")
ok("amzFeeToggleRow('${String(p.mid).replace(/'/g, '')}')" in REND,
   "D2  /!\\ clicking the row toggles it")
ok("open ? amzFeeRowBreakdown(p, COLS.length) : ''" in REND,
   "D3  ...and the breakdown spans the columns actually shown")
ok("let amzFeeOpenRows = new Set();" in js,
   "D4  more than one row can be open at a time")

# /!\ THE BUTTON THAT LEFT THE PAGE WAS THE COMPLAINT.
# /!\ SCOPED TO THE FEES PANEL. The sub-tab strip still has an Opportunities
# button and should - what went was the one INSIDE the Fees controls, whose
# whole job was to send him off the page he was working on.
_wrap = s[s.index('<div id="pnl-amzn-fees-wrap"'):]
_wrap = _wrap[:_wrap.index('<!-- v11.96')]
ok("switchPnlAmazonView('opportunities')" not in _wrap,
   "D5  /!\\ the cross-tab Actions button is gone from the Fees controls")
eq("D5b ...and the sub-tab strip still has its own",
   s.count("switchPnlAmazonView('opportunities')"), 1)
ok('id="amzfee-actions"' in s, "D6  the cards have a host on this page")
ok('id="amzfee-act-sub"' in s, "D7  ...and a sub-line that says what is at stake")
ok("What to do about it" in s, "D8  the panel is titled in plain words")
# The empty state must point at the control that would fix it.
ok("widen the period on the panel above" in REND,
   "D9  /!\\ an empty window points at the widen control rather than stopping")

# The Opportunities page is untouched: it still renders every type.
ok("_pnlOppsFilter" in OPPR, "D10 the Opportunities page keeps its own filter")
ok("AMZ_FEE_OPP_TYPES" not in OPPR,
   "D11 /!\\ ...and is NOT narrowed to fees by this change")

chip = re.search(r'margin-left:4px">v(\d+\.\d+)', s).group(1)
cmd = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", errors="replace").read()
doc = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cmd).group(1)
eq("D12 the chip and CLAUDE.md agree", doc, chip)

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
