#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.95 - the Fees column is the sum of the columns beside it.

Jason: "on the fees, the biggest bucket is 'fees' column, which isn't broken
out further."

/!\ IT WAS 96.8% OF THE NUMBER. Measured on the live table, US:

    last 30d        fees $58,175   with a column beside them  $1,881   3.2%
    last 90d        fees $160,018                             $3,712   2.3%
    trailing 365d   fees $632,176                            $40,571   6.4%

v11.71 gave a column to FBA Storage plus every AVOIDABLE line - six of
eleven, and those six are the small ones.

  * A  all eleven lines declare a column, and the picker follows.
  * B  /!\ THE TIE-OUT, driven on the real amzFeeAgg: every product's Fees
       equals its eleven line columns summed, and so does the footer.
  * C  /!\ THE DEFECT REPRODUCED: v11.71's six-column rule run beside the
       shipped one on the same rows.
  * D  nothing else about the table moved.
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
    b = js.index("{", js.index("function " + name + "("))
    return js[i:b] + _bal(b)


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


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v11.95  the Fees column, broken out")
print("=" * 68)

REND = nocomment(fn_flat("renderAmazonFees"))

# ===========================================================================
print("\nA. every line declares a column")
# ===========================================================================
blk = js[js.index("const AMZ_FEE_LINES = ["):]
blk = blk[:blk.index("\n];")]
lines = [(m.group(1), m.group(3), m.group(4)) for m in re.finditer(
    r"\{ k: '([a-z_]+)',\s*label: '([^']+)',\s*lever: '([a-z]+)'(?:, sku: '([^']+)')?", blk)]
eq("A1  eleven fee lines", len(lines), 11)
missing = [k for k, _, sku in lines if not sku]
eq("A2  /!\\ not one of them is without a column", missing, [])
# The five this release added, by name, so a silent revert fails here.
for k, h in (('fba_fulfillment_fee_total', 'FBA $'), ('referral_fee_total', 'Referral'),
             ('referral_fee_refunds_total', 'Ref Refunds'),
             ('inbound_transport_fee_total', 'Transport'),
             ('refund_admin_fee_total', 'Refund Adm')):
    ok((k, [x[2] for x in lines if x[0] == k][0]) == (k, h),
       "A3  %s carries '%s'" % (k, h))
# /!\ RULE 3a: THE THREE FBA COLUMNS ARE THREE DIFFERENT MEASURES, each
# named by its own arithmetic. A header that repeated another would be the
# one-label-two-measures defect.
hdrs = [x[2] for x in lines] + ['Product', 'Units', 'Net Sales', 'Fees', 'Fee %',
                                'FBA $/u', 'FBA %', 'Held', 'Cu Ft', 'Units/Held', 'Avoidable']
eq("A4  /!\\ every column header is unique", len(hdrs), len(set(hdrs)))
# The picker is derived from the same field, so it cannot fall behind.
ok("AMZ_FEE_LINES.filter(l => l.sku).map(l => ({ k: l.k, h: l.sku }))" in js,
   "A5  the picker still derives from `sku`")
ok("const SKU_LINES = AMZ_FEE_LINES.filter(l => l.sku);" in REND,
   "A6  ...and so does the table")

# ===========================================================================
print("\nB. /!\\ the tie-out, on the real amzFeeAgg")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1195_b.js"),
    const_arr("AMZ_FEE_LINES") + "\n" + const_arr("AMZ_FEE_OUTSIDE") + "\n" + r"""
let pnlCurrencyMode = 'usd', pnlFxRate = 1.35, pnlFxGbp = 1.25, pnlFxEur = 1.1;
let amzCuFtByMid = {}, _amzCuFtLoading = false;
// v11.98 - amzFeeAgg stamps the Fee Preview pack onto every product,
// so the index and the gap rule have to be in scope. Sliced below.
let amzPackByMid = {};

const pnlRegion = 'US';
let records = [];
const allProducts = [];
let pnlVisibleMids = [];
const mk = (mid, wk, o) => Object.assign({ master_id: mid, week_start: wk, region: 'US',
  currency: 'USD', net_sales: 0, net_units_sold: 0 }, o);
const ROWS = [
  mk('M1', '2026-10-05', { net_sales: 79298, net_units_sold: 5001,
     fba_fulfillment_fee_total: 21500, referral_fee_total: 9800,
     referral_fee_refunds_total: -210, inbound_transport_fee_total: 940,
     inbound_placement_fee_total: 820, fba_storage_fee_total: 410,
     aged_inventory_fee_total: 90, low_inventory_fee_total: 0,
     removal_fee_total: 40, storage_util_surcharge: 0, refund_admin_fee_total: 12 }),
  mk('M2', '2026-10-12', { net_sales: 53242, net_units_sold: 5939,
     fba_fulfillment_fee_total: 17000, referral_fee_total: 7900,
     referral_fee_refunds_total: -95, inbound_transport_fee_total: 600,
     aged_inventory_fee_total: 1140, low_inventory_fee_total: 310,
     fba_storage_fee_total: 260, refund_admin_fee_total: 5 }),
  // A CAD row, so the tie-out has to hold THROUGH the conversion.
  Object.assign(mk('M3', '2026-10-12', { net_sales: 1350, net_units_sold: 100,
     fba_fulfillment_fee_total: 540, referral_fee_total: 135,
     removal_fee_total: 27 }), { currency: 'CAD' }),
];
let WIN = { from: '2026-10-01', to: '2026-10-31' };
const getPnlDateRange = () => WIN;
const getPnlSource = () => ({ rows: ROWS, regionMatches: r => r === 'US' });
function amzUnitsHeld() { return null; }
""" + fn("pnlRowFx") + "\n" + fn("amzFeeStamp") + "\n" + fn("amzFeeSumRows") + "\n"
    + re.search(r"(?m)^const AMZ_SMALL_STD = .*$", js).group(0) + "\n" + fn("amzSmallStdGap") + "\n" + fn("amzFeeAgg") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const r2 = v => Math.round(v * 100) / 100;
const A = amzFeeAgg();
const COLS = AMZ_FEE_LINES.filter(l => l.sku).map(l => l.k);
t('B1  /!\\ all eleven lines have a column', COLS.length, 11);

// /!\ THE WHOLE POINT: the cell equals the cells beside it, per product.
for (const p of A.prods) {
  const sum = COLS.reduce((a, k) => a + (p[k] || 0), 0);
  t('B2  ' + p.mid + ': Fees === the line columns summed', r2(p.fees), r2(sum));
}
// ...and on the footer, which sums the rows SHOWN (v11.91).
const foot = amzFeeSumRows(A.prods);
t('B3  /!\\ and the TOTAL row ties out too',
  r2(foot.fees), r2(COLS.reduce((a, k) => a + (foot[k] || 0), 0)));
t('B4  the window total agrees with the footer over the same rows',
  r2(A.tot.fees), r2(foot.fees));

// Avoidable is a ROLL-UP of five of those lines, not a twelfth line - so it
// must not be in the tie-out, and it must still equal its own five.
const AV = AMZ_FEE_LINES.filter(l => l.lever === 'avoidable').map(l => l.k);
t('B5  /!\\ Avoidable is still exactly its five lines',
  r2(foot.avoidable), r2(AV.reduce((a, k) => a + (foot[k] || 0), 0)));
t('B6  ...and is a SUBSET of Fees, never an addition',
  foot.avoidable < foot.fees, true);

// The CAD row: the conversion happens once, before the split.
const m3 = A.prods.find(p => p.mid === 'M3');
t('B7  /!\\ a CAD row is converted and still ties out',
  r2(m3.fees), r2(COLS.reduce((a, k) => a + (m3[k] || 0), 0)));
t('B8  ...at the shared rate, not at face value', r2(m3.fees) === r2(702), false);
console.log(JSON.stringify(out));
""")
for c in B:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nC. /!\\ the defect reproduced")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1195_c.js"), const_arr("AMZ_FEE_LINES") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
// v11.71's rule, restated: FBA Storage plus every avoidable line.
const v1171 = AMZ_FEE_LINES.filter(l => l.lever === 'avoidable' || l.k === 'fba_storage_fee_total')
  .map(l => l.k);
const v1195 = AMZ_FEE_LINES.filter(l => l.sku).map(l => l.k);
t('C1  /!\\ v11.71 gave a column to six of eleven lines', v1171.length, 6);
t('C2  v11.95 gives one to all eleven', v1195.length, 11);
t('C3  /!\\ ...and the six it had are all still there',
  v1171.every(k => v1195.includes(k)), true);

// Measured on the live table (US) on 2026-11-10, so these are readings.
const LIVE = [
  { win: 'last 30d',      fees: 58175,  covered: 1881 },
  { win: 'last 90d',      fees: 160018, covered: 3712 },
  { win: 'trailing 365d', fees: 632176, covered: 40571 },
];
for (const L of LIVE) {
  const pct = Math.round(L.covered / L.fees * 1000) / 10;
  t('C4  ' + L.win + ': the six columns covered ' + pct + '% of Fees', pct < 7, true);
}
t('C5  /!\\ so on a 30-day window 96.8% of the cell was off screen',
  Math.round((1 - 1881 / 58175) * 1000) / 10, 96.8);
// The two lines that were missing are the two that matter.
const BIG = ['fba_fulfillment_fee_total', 'referral_fee_total'];
t('C6  /!\\ and neither of the two biggest lines had one',
  BIG.some(k => v1171.includes(k)), false);
t('C7  ...both do now', BIG.every(k => v1195.includes(k)), true);
console.log(JSON.stringify(out));
""")
for c in C:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nD. nothing else about the table moved")
# ===========================================================================
ok("const VIS = amzFeeVisibleCols();" in REND, "D1  the view still decides what shows")
ok("NOCHARGE" in REND, "D2  a line this window did not charge still says so")
ok("AMZ_FEE_DELTA_NONE.has(c.k)" in REND, "D3  the suppressed chips are unchanged")
ok("amzFeeFocusLine" in REND, "D4  the composition row still opens its column")
# /!\ AND NOW EVERY COMPOSITION ROW CAN BE OPENED, because `canOpen` reads
# the same `sku` field. That is a consequence of this change, not a new rule.
ok("const canOpen = !!l.sku;" in REND,
   "D5  /!\\ ...which is now true for all eleven lines")
ok("the eleven line columns to the right, summed" in js,
   "D6  the Fees tooltip says what it is made of")

chip = re.search(r'margin-left:4px">v(\d+\.\d+)', s).group(1)
cmd = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", errors="replace").read()
doc = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cmd).group(1)
eq("D7  the chip and CLAUDE.md agree", doc, chip)

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
